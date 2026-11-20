"""Import an AutoCAD drawing package (``ilq/2``) into a schedule (draw-to-quote plan 2.1-2.6).

The CAD toolkit sends what was drawn: runs with a style (a configuration preset, or a template and
its selections), raw path lengths, rooms, cabinets, PSU locations and wire paths. The server decides
everything else, exactly as for a run configured by hand:

- every tape/neon or linear run is planned through ``portal.configuration.calculate`` (the
  configurators snap cuts, split runs, add leaders and make the part number); an extrusion kit run is a
  kit line (``validate_kit_configuration``, one kit per profile stock length) plus a tape build;
- the dry run (:func:`preview_drawing_import`) marks each run ``ok``, ``needs_choice`` (an option the
  style leaves open) or ``error``, and lists drawn against server length, splits and watts;
- the commit (:func:`commit_drawing_import`) plans again, then saves every build through
  ``portal.configuration.save`` / ``portal.kit_configuration.save`` (receipts keep retries idempotent)
  and adds other-manufacturer lines through ``line_add.append_line``, all in one transaction.

Lines keep the run's CAD id in ``cad_run_id``. A re-import matches lines by that id (or the
``erp.line_key`` the receipt wrote into the drawing) and updates them in place; lines whose run is
gone are removed only when the user confirms. A locked or quoted schedule imports into a new version.
The package, receipt and the design site (rooms, cabinets, measured home runs) are kept on an
``ilL-CAD-Import`` record; the System Designer applies the site to a new design.

Prices never enter or leave this module (D6): selections are price-stripped on the way in and only
lengths, splits, watts and part numbers are returned.
"""

import base64
import binascii
import hashlib
import json
import math
import uuid

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build

DOCTYPE = "ilL-CAD-Import"
CONTROLLER = "ilL-Spec-Controller"
SCHEDULE = "ilL-Project-Fixture-Schedule"
MAX_BYTES = 5 * 1024 * 1024
EXTENSIONS = ("json", "ilq", "dxf")
MAX_DXF_BYTES = 20 * 1024 * 1024
MM_PER_IN = 25.4
MM_PER_FT = 304.8
TAPE_FAMILIES = ("LED Tape", "COB Tape", "LED Neon")
KIT = "Extrusion Kit"
LINEAR = "Linear Fixture"
KIT_SUFFIX = ".K"
OTHER_PREFIX = "OTHER."
CATALOG_STALE_DAYS = 30
LENGTH_TOLERANCE_IN = 0.05
RECEIPT_SCHEMA = "ilq-receipt/1"
SITE_SCHEMA = "cad-site/1"
EDITABLE = ("DRAFT", "READY")
# CAD feed direction → configurator segment keys per family (tape: inches, linear: millimetres).
TAPE_SEGMENT_KEYS = (
	"start_feed_direction",
	"start_lead_length_inches",
	"end_type",
	"end_feed_direction",
	"end_feed_length_inches",
)
LINEAR_START_KEYS = ("start_feed_direction", "start_power_feed_type", "start_leader_cable_length_mm")
LINEAR_END_KEYS = ("end_feed_direction", "end_power_feed_type", "end_jumper_cable_length_mm")


# --- Reading the package -----------------------------------------------------------------------


def read_package(filename, content, options=None):
	"""The checked package and its SHA-256 from an uploaded file (base64 ``content``).

	A ``.ilq.json`` file is the CAD toolkit's package. A ``.dxf`` is a drawing made without the toolkit
	(plan 6.1): ``dxf_ingest`` turns its ``ILM-*`` layers into a package, using ``options`` for the
	preset and schedule Type of each layer.
	"""
	from illumenate_lighting.illumenate_lighting.system_design.ilq_schema import PackageError, parse_package

	name = str(filename or "").strip().lower()
	extension = name.rsplit(".", 1)[-1] if "." in name else ""
	if extension not in EXTENSIONS:
		frappe.throw(_("Upload the .ilq.json file the CAD toolkit wrote (ILQUOTE), or an ASCII .dxf"))
	limit = MAX_DXF_BYTES if extension == "dxf" else MAX_BYTES
	if not isinstance(content, str) or not content:
		frappe.throw(_("The file is empty"))
	if len(content) > (limit * 4) // 3 + 4:
		frappe.throw(_("The file is larger than {0} MB").format(limit // (1024 * 1024)))
	try:
		data = base64.b64decode(content, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The file could not be read"))
	if not data:
		frappe.throw(_("The file is empty"))
	if extension == "dxf":
		from illumenate_lighting.illumenate_lighting.portal.dxf_ingest import DxfError, package_from_dxf

		try:
			data_package = package_from_dxf(data, str(filename), _options(options))
		except DxfError as error:
			frappe.throw(str(error))
	else:
		data_package = data
	try:
		package = parse_package(data_package)
	except PackageError as error:
		frappe.throw(_("This is not a valid drawing package: {0}").format("; ".join(error.problems[:5])))
	except UnicodeDecodeError:
		frappe.throw(_("The file could not be read"))
	return package, hashlib.sha256(data).hexdigest()


def _options(value):
	if value in (None, ""):
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid DXF options"))
	if not isinstance(value, dict):
		frappe.throw(_("Invalid DXF options"))
	return value


def clean_selections(selections):
	"""``(selections, dropped keys)``: price, MSRP and cost keys never reach the configurator (D6)."""
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import is_price_key, strip_prices

	selections = selections if isinstance(selections, dict) else {}
	dropped = sorted(key for key in selections if is_price_key(key))
	return strip_prices(selections), dropped


# --- Segments: drawn geometry → configurator segments ----------------------------------------


def drawn_length_in(run):
	return round(sum(float(segment["path_length_in"]) for segment in run["segments"]), 4)


def _style_segment(style, index):
	defaults = [item for item in (style.get("segments") or []) if isinstance(item, dict)]
	if not defaults:
		return {}
	return dict(defaults[min(index, len(defaults) - 1)])


def tape_segments(run, style):
	"""Tape/neon ``segments_json``: lengths in inches; feeds and leaders from CAD, else the style."""
	result = []
	for index, segment in enumerate(run["segments"]):
		base = _style_segment(style, index)
		item = {key: base[key] for key in TAPE_SEGMENT_KEYS if base.get(key) not in (None, "")}
		item["tape_length_value"] = round(float(segment["path_length_in"]), 4)
		item["tape_length_unit"] = "in"
		if index == 0:
			if segment.get("start_feed"):
				item["start_feed_direction"] = segment["start_feed"]
			if segment.get("lead_length_in") is not None:
				item["start_lead_length_inches"] = float(segment["lead_length_in"])
		else:
			item.pop("start_feed_direction", None)
			item.pop("start_lead_length_inches", None)
		jumper = segment.get("end_type") == "JUMPER" and index < len(run["segments"]) - 1
		item["end_type"] = "Jumper" if jumper else "Endcap"
		if jumper:
			if segment.get("jumper_length_in") is not None:
				item["end_feed_length_inches"] = float(segment["jumper_length_in"])
			item.setdefault("end_feed_direction", item.get("start_feed_direction") or "End")
		else:
			item.pop("end_feed_direction", None)
			item.pop("end_feed_length_inches", None)
		result.append(item)
	return result


def linear_segments(run, style):
	"""Linear fixture engine segments: whole millimetres; start/end details from CAD, else the style."""
	result = []
	count = len(run["segments"])
	for index, segment in enumerate(run["segments"]):
		base = _style_segment(style, index)
		item = {
			"segment_index": index,
			"requested_length_mm": round(float(segment["path_length_in"]) * MM_PER_IN),
		}
		if index == 0:
			item.update({key: base[key] for key in LINEAR_START_KEYS if base.get(key) not in (None, "")})
			if segment.get("start_feed"):
				item["start_feed_direction"] = segment["start_feed"]
			if segment.get("lead_length_in") is not None:
				item["start_leader_cable_length_mm"] = round(float(segment["lead_length_in"]) * MM_PER_IN)
		jumper = segment.get("end_type") == "JUMPER" and index < count - 1
		item["end_type"] = "Jumper" if jumper else "Endcap"
		if jumper:
			item.update({key: base[key] for key in LINEAR_END_KEYS if base.get(key) not in (None, "")})
			if segment.get("jumper_length_in") is not None:
				item["end_jumper_cable_length_mm"] = round(float(segment["jumper_length_in"]) * MM_PER_IN)
		result.append(item)
	return result


def kit_quantity(length_in, stock_length_mm):
	"""Kits for a drawn run: whole profile sticks covering it (the kit is one stick and its parts)."""
	if not stock_length_mm or stock_length_mm <= 0:
		return None
	return max(1, math.ceil(length_in * MM_PER_IN / float(stock_length_mm) - 1e-9))


def requests_for(run):
	"""``[(part, request)]`` the run saves: one configured build, or a kit plus its tape build."""
	style = run["style"]
	selections, _dropped = clean_selections(style.get("selections"))
	if style["family"] == KIT:
		tape = style["tape"]
		tape_selections, _dropped = clean_selections(tape.get("selections"))
		kit = {
			"kit_template": style["template"],
			**{k: v for k, v in selections.items() if k != "kit_template"},
		}
		return [
			(
				"tape",
				{
					"family": tape["family"],
					"template": tape["template"],
					"selections": tape_selections,
					"segments": tape_segments(run, {}),
				},
			),
			("kit", {"family": KIT, "template": style["template"], "selections": kit}),
		]
	if style["family"] == LINEAR:
		return [
			(
				"build",
				{
					"family": LINEAR,
					"template": style["template"],
					"selections": {
						**selections,
						"fixture_template_code": selections.get("fixture_template_code") or style["template"],
						"segments": linear_segments(run, style),
					},
					"segments": None,
				},
			)
		]
	return [
		(
			"build",
			{
				"family": style["family"],
				"template": style["template"],
				"selections": selections,
				"segments": tape_segments(run, style),
			},
		)
	]


def cad_id(run_id, part):
	return run_id + KIT_SUFFIX if part == "kit" else run_id


def request_fingerprint(request):
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

	return fingerprint({key: request.get(key) for key in ("family", "template", "selections", "segments")})


# --- Planning ----------------------------------------------------------------------------------


def _messages(result):
	texts = []
	for message in result.get("messages") or []:
		text = message.get("text") if isinstance(message, dict) else str(message)
		if text and (
			not isinstance(message, dict) or message.get("severity") in (None, "warning", "error", "info")
		):
			texts.append(str(text))
	return texts[:8]


def summarize_build(family, result):
	"""Lengths, splits, watts and part number from a configurator result; never prices."""
	validation = result.get("validation") or result
	computed = validation.get("computed") or {}
	if family == LINEAR:
		length_mm = computed.get("manufacturable_overall_length_mm") or 0
	else:
		length_mm = computed.get("manufacturable_length_mm") or 0
	segments = []
	for segment in computed.get("segments") or []:
		# Tape/neon: each drawn segment's built length. Linear: each profile/lens stick cut.
		mm = segment.get("manufacturable_length_mm") or segment.get("profile_cut_len_mm")
		if mm:
			segments.append(round(float(mm) / MM_PER_IN, 2))
	runs = []
	for item in computed.get("runs") or []:
		mm = item.get("run_len_mm") or item.get("tape_length_mm")
		if mm:
			runs.append(round(float(mm) / MM_PER_IN, 2))
	return {
		"part_number": validation.get("part_number") or result.get("part_number"),
		"server_length_in": round(float(length_mm) / MM_PER_IN, 2) if length_mm else None,
		"segments_in": segments,
		"runs_count": computed.get("runs_count") or (len(runs) or None),
		"runs_in": runs,
		"max_run_ft": computed.get("max_run_ft_effective"),
		"watts": computed.get("total_watts"),
		"assembly_mode": computed.get("assembly_mode"),
		"input_hash": result.get("input_hash"),
	}


class Planner:
	"""Plans a package against a schedule; lookups are shared across runs."""

	def __init__(self, schedule, package, is_sales_staff, choices=None):
		self.schedule = schedule
		self.package = package
		self.is_sales_staff = is_sales_staff
		self.choices = choices or {}
		self.templates = {}
		self.kit_stock = {}
		self.controls = {}
		self.by_cad_id = {}
		self.by_line_key = {}
		for line in schedule.lines:
			if line.get("cad_run_id"):
				self.by_cad_id.setdefault(line.cad_run_id, line)
			if line.get("line_key"):
				self.by_line_key[line.line_key] = line

	# The template must still be offered to this user (D: plan "unknown templates are errors").
	def template_problem(self, family, template):
		key = (family, template)
		if key not in self.templates:
			from illumenate_lighting.illumenate_lighting.portal.presets import (
				FAMILY_DOCTYPES,
				template_problem,
			)

			if family not in FAMILY_DOCTYPES:
				self.templates[key] = _("{0} is not a product family the drawing import can build").format(
					family
				)
			else:
				self.templates[key] = template_problem(family, template)
		return self.templates[key]

	def kit_stock_length(self, template):
		if template not in self.kit_stock:
			self.kit_stock[template] = frappe.db.get_value(
				"ilL-Extrusion-Kit-Template", template, "profile_stock_length_mm"
			)
		return self.kit_stock[template]

	def match(self, run, part):
		"""The existing line this run (or its kit part) updates, or ``None``."""
		line = self.by_cad_id.get(cad_id(run["id"], part))
		if line is None and part != "kit":
			key = (run.get("erp") or {}).get("line_key")
			candidate = self.by_line_key.get(key) if key else None
			if candidate is not None and not candidate.get("cad_run_id"):
				line = candidate
		return line

	def calculate(self, request):
		from illumenate_lighting.illumenate_lighting.portal import configuration

		return configuration.calculate(
			request["family"],
			request["selections"],
			template=request["template"],
			segments=request.get("segments"),
		)

	def validate_kit(self, selections):
		from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
			validate_kit_configuration,
		)

		return validate_kit_configuration(dict(selections))

	def apply_choices(self, run, request):
		chosen = self.choices.get(run["id"]) or {}
		if isinstance(chosen, dict):
			clean, _dropped = clean_selections(chosen)
			request["selections"] = {
				**request["selections"],
				**{k: v for k, v in clean.items() if v not in (None, "")},
			}
		return request

	def plan_run(self, run):
		row = {
			"id": run["id"],
			"handle": run["handle"],
			"fixture_type": run["fixture_type"],
			"room": run.get("room"),
			"family": run["style"]["family"],
			"template": run["style"]["template"],
			"style": run["style"].get("preset") or run["style"]["template"],
			"drawn_length_in": drawn_length_in(run),
			"status": "ok",
			"messages": [],
			"parts": [],
		}
		_selections, dropped = clean_selections(run["style"].get("selections"))
		if dropped:
			row["messages"].append(_("Ignored price fields in the style: {0}").format(", ".join(dropped)))
		saves = []
		for part, request in requests_for(run):
			request = self.apply_choices(run, request) if part != "kit" else request
			problem = self.template_problem(request["family"], request["template"])
			line = self.match(run, part)
			entry = {
				"part": part,
				"family": request["family"],
				"template": request["template"],
				"cad_run_id": cad_id(run["id"], part),
				"line_key": line.get("line_key") if line is not None else None,
				"action": "update" if line is not None else "add",
			}
			if problem:
				row["status"] = "error"
				row["messages"].append(problem)
				row["parts"].append(entry)
				continue
			if part == "kit":
				result = self.validate_kit(request["selections"])
				qty = kit_quantity(row["drawn_length_in"], self.kit_stock_length(request["template"]))
				if not result.get("is_valid"):
					row["status"] = "error"
					row["messages"].append(result.get("error") or _("The kit could not be validated"))
				elif not qty:
					row["status"] = "error"
					row["messages"].append(
						_("Kit {0} has no profile stock length").format(request["template"])
					)
				else:
					entry.update(part_number=result.get("part_number"), qty=qty)
					row["messages"].append(
						_("{0} kits of {1} cover {2} in").format(
							qty, request["template"], row["drawn_length_in"]
						)
					)
			else:
				result = self.calculate(request)
				validation = result.get("validation") or {}
				if not result.get("success"):
					missing = validation.get("missing_fields") or []
					row["status"] = "needs_choice" if missing and row["status"] != "error" else "error"
					if missing:
						entry["missing"] = list(missing)
						row["messages"].append(_("Choose {0} for this run").format(", ".join(missing)))
					else:
						row["messages"].append(
							validation.get("error") or _("This run could not be configured")
						)
				else:
					entry.update(summarize_build(request["family"], result))
					row["messages"].extend(_messages(validation))
					server = entry.get("server_length_in")
					if server is not None:
						entry["delta_in"] = round(row["drawn_length_in"] - server, 2)
						if abs(entry["delta_in"]) > LENGTH_TOLERANCE_IN and part != "kit":
							row["messages"].append(
								_("Builds {0} in for {1} in drawn (cut to the nearest increment)").format(
									server, row["drawn_length_in"]
								)
							)
					if (entry.get("runs_count") or 1) > 1:
						row["messages"].append(
							_("Splits into {0} runs (max run {1} ft)").format(
								entry["runs_count"], entry.get("max_run_ft")
							)
						)
			if line is not None and entry["action"] == "update" and _same_meta(line, run):
				if part == "kit":
					same = line.get("ill_item_code") == entry.get("part_number") and int(
						line.get("qty") or 0
					) == entry.get("qty")
				else:
					same = _same_request(line.get("ill_configurator_request") or "", request)
				if same:
					entry["action"] = "unchanged"
			row["parts"].append(entry)
			saves.append({"part": part, "request": request, "entry": entry, "run": run})
		if row["status"] == "error":
			return row, []
		if row["status"] == "needs_choice":
			return row, []
		build = next((entry for entry in row["parts"] if entry["part"] != "kit"), {})
		row["server_length_in"] = build.get("server_length_in")
		row["action"] = (
			"add"
			if all(entry["action"] == "add" for entry in row["parts"])
			else "unchanged"
			if all(entry["action"] == "unchanged" for entry in row["parts"])
			else "update"
		)
		return row, saves

	def plan_other(self, other):
		key = (OTHER_PREFIX + other["fixture_type"])[:40]
		line = self.by_cad_id.get(key)
		row = {
			"id": key,
			"fixture_type": other["fixture_type"],
			"family": "OTHER",
			"status": "ok",
			"messages": [],
			"action": "update" if line is not None else "add",
			"summary": " ".join(
				filter(None, (other.get("manufacturer_name"), other.get("fixture_model_number")))
			),
		}
		line_data = {
			"line_id": other["fixture_type"],
			"qty": other["qty"],
			"location": other.get("location") or None,
			"manufacturer_type": "OTHER",
			"manufacturer_name": other["manufacturer_name"],
			"fixture_model_number": other.get("fixture_model_number"),
			"notes": other.get("notes"),
			"watts_each": other.get("watts_each"),
			"input_voltage_v": other.get("input_voltage_v"),
			"voltage_class": other.get("voltage_class"),
		}
		return row, {"cad_run_id": key, "line": line, "line_data": line_data}

	def control_spec(self, code):
		"""The active ``ilL-Spec-Controller`` of an Item, with its port names, or ``None``."""
		if code not in self.controls:
			spec = frappe.db.get_value(
				CONTROLLER,
				{"item": code, "is_active": 1},
				["name", "controller_type", "output_dimming"],
				as_dict=True,
			)
			if spec:
				spec["ports"] = {
					row.port_name: row.protocol
					for row in frappe.get_all(
						"ilL-Child-Controller-Port",
						filters={"parent": spec.name, "parenttype": CONTROLLER},
						fields=["port_name", "protocol"],
					)
				}
			self.controls[code] = spec
		return self.controls[code]

	def plan_control(self, control, rooms):
		"""A control placed in CAD: an accessory line for its Item, plus its place in the design."""
		from illumenate_lighting.illumenate_lighting.api.portal import (
			is_power_supply_group,
			orderable_item_problem,
		)

		key = control["id"]
		line = self.by_cad_id.get(key)
		row = {
			"id": key,
			"fixture_type": key,
			"family": "CONTROL",
			"status": "ok",
			"messages": [],
			"action": "update" if line is not None else "add",
			"summary": control["item_code"],
		}
		code = control["item_code"]
		problem = orderable_item_problem(code, self.is_sales_staff)
		spec = None if problem else self.control_spec(code)
		if problem or not spec:
			row["status"] = "error"
			row["messages"].append(
				problem or _("{0} is not a control in the ilLumenate catalog").format(code)
			)
			return row, None
		item = frappe.db.get_value("Item", code, ["item_name", "item_group"], as_dict=True) or {}
		row["summary"] = item.get("item_name") or code
		if control.get("dmx"):
			address = control["dmx"].get("start_address")
			row["messages"].append(
				_("Universe {0}, address {1}").format(
					control["dmx"]["universe"], address if address != "auto" else _("auto")
				)
			)
		location = (rooms.get(control.get("room") or "") or {}).get("name") or control.get("cabinet")
		line_data = {
			"line_id": key,
			"qty": 1,
			"location": location,
			"manufacturer_type": "ACCESSORY",
			"accessory_item": code,
			"accessory_item_name": item.get("item_name") or code,
			"notes": control.get("notes"),
		}
		if not is_power_supply_group(item.get("item_group")):
			line_data["accessory_product_type"] = item.get("item_group")
		from illumenate_lighting.illumenate_lighting.system_design.readiness import controller_category

		meta = {
			"catalogId": f"ctl:{spec.name}",
			"category": controller_category(spec.controller_type, spec.output_dimming) or "dmx-controller",
			"cabinet": control.get("cabinet"),
			"room": (rooms.get(control.get("room") or "") or {}).get("name"),
			"dmx": control.get("dmx"),
			"controlFrom": control.get("control_from"),
		}
		return row, {
			"cad_run_id": key,
			"line": line,
			"line_data": line_data,
			"kind": "control",
			"control": meta,
		}

	def zone_problems(self):
		"""Zones whose control output is not a port of that control, as ``(zone id, text)``."""
		controls = {control["id"]: control for control in self.package.get("controls") or []}
		problems = []
		for zone in self.package.get("zones") or []:
			target = zone.get("control")
			if not target:
				continue
			control = controls.get(target["id"])
			spec = self.control_spec(control["item_code"]) if control else None
			if spec and target["port"] not in spec["ports"]:
				problems.append(
					(
						zone["id"],
						_("{0} has no output {1} (it has {2})").format(
							target["id"], target["port"], ", ".join(sorted(spec["ports"])) or _("no ports")
						),
					)
				)
		return problems

	def removals(self, kept):
		"""Lines an earlier import made whose run is no longer in the drawing."""
		rows = []
		for line in self.schedule.lines:
			key = line.get("cad_run_id")
			if key and key not in kept:
				rows.append(
					{
						"id": key,
						"line_key": line.get("line_key"),
						"fixture_type": line.get("line_id"),
						"action": "remove",
						"status": "ok",
						"messages": [_("This run is no longer in the drawing")],
					}
				)
		return rows

	def plan(self):
		rows, saves, others = [], [], []
		for run in self.package["runs"]:
			row, run_saves = self.plan_run(run)
			rows.append(row)
			saves.extend(run_saves)
		other_rows = []
		for other in self.package.get("other_lines") or []:
			row, data = self.plan_other(other)
			other_rows.append(row)
			others.append(data)
		rooms = {room["id"]: room for room in self.package.get("rooms") or []}
		for control in self.package.get("controls") or []:
			row, data = self.plan_control(control, rooms)
			other_rows.append(row)
			if data:
				others.append(data)
		for zone_id, text in self.zone_problems():
			other_rows.append(
				{
					"id": zone_id,
					"fixture_type": zone_id,
					"family": "ZONE",
					"status": "error",
					"messages": [text],
				}
			)
		kept = {cad_id(run["id"], part) for run in self.package["runs"] for part, _r in requests_for(run)}
		kept |= {data["cad_run_id"] for data in others}
		kept |= {control["id"] for control in self.package.get("controls") or []}
		return rows, other_rows, self.removals(kept), saves, others


def _same_request(stored, request):
	try:
		stored = json.loads(stored) if stored else {}
	except ValueError:
		return False
	if not isinstance(stored, dict):
		return False
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json

	keys = ("family", "template", "selections", "segments")
	return canonical_json({key: stored.get(key) for key in keys}) == canonical_json(
		{key: request.get(key) for key in keys}
	)


def _same_meta(line, run):
	return (line.get("line_id") or "") == run["fixture_type"] and (line.get("location") or "") == (
		_location(run) or ""
	)


def _location(run):
	return run.get("location") or None


# --- Site (rooms, cabinets, measured home runs) ---------------------------------------------


def site_seed(package, line_keys, import_name=None, controls=None):
	"""The ``cad-site/1`` document the System Designer applies to a new design (plan 2.3).

	Spaces are named by room (the import sets each line's location to its room, and the designer makes
	one space per location). Home-run length is the longest low-voltage wire path into the run, in feet,
	raw: the designer adds its route slack and wire waste (``plan_route_slack_pct``, ``wire_waste_pct``).
	"""
	rooms = {room["id"]: room for room in package.get("rooms") or []}
	wires = {}
	for wire in package.get("wire_paths") or []:
		if wire["kind"] != "lv":
			continue
		for end in (wire["from"], wire["to"]):
			wires[end] = max(wires.get(end, 0), float(wire["path_length_in"]))
	lines = {}
	for run in package["runs"]:
		key = line_keys.get(run["id"])
		if not key:
			continue
		room = rooms.get(run.get("room") or "")
		entry = {
			"runId": run["id"],
			"room": room["name"] if room else None,
			"cabinet": run.get("cabinet") or None,
			"feedMethod": (run.get("feed") or {}).get("method") or "end",
		}
		if run["id"] in wires:
			entry["homeRunLengthFt"] = round(wires[run["id"]] / 12, 2)
		lines[key] = entry
	return {
		"schema": SITE_SCHEMA,
		"import": import_name,
		"drawing": {key: package["drawing"].get(key) for key in ("file", "rev", "hash")},
		"rooms": [
			{
				"id": room["id"],
				"name": room["name"],
				"level": room.get("level") or "",
				"envChoice": room.get("env"),
			}
			for room in package.get("rooms") or []
		],
		"cabinets": [
			{
				"id": cabinet["id"],
				"room": (rooms.get(cabinet.get("room") or "") or {}).get("name"),
				"locationRating": cabinet.get("location_rating") or "Dry",
				"accessNote": cabinet.get("access_note") or "",
				"feedLengthFt": round(
					max(
						(
							float(wire["path_length_in"])
							for wire in package.get("wire_paths") or []
							if wire["kind"] == "line" and cabinet["id"] in (wire["from"], wire["to"])
						),
						default=0,
					)
					/ 12,
					2,
				),
			}
			for cabinet in package.get("cabinets") or []
		],
		"lines": lines,
		# Controls in v1: each control's schedule line, catalog item, cabinet and DMX address, and the
		# zones that group runs (by their lines) under a control output.
		"controls": {key: value for key, value in (controls or {}).items() if value.get("lineKey")},
		"zones": [
			{
				"id": zone["id"],
				"name": zone["name"],
				"method": zone["method"],
				"control": zone.get("control"),
				"lines": [line_keys[run] for run in zone.get("runs") or [] if line_keys.get(run)],
			}
			for zone in package.get("zones") or []
		],
	}


# --- Access and freshness --------------------------------------------------------------------


def _require_enabled():
	from illumenate_lighting.illumenate_lighting.system_design.cad_access import enabled_for

	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to import a drawing"), frappe.PermissionError)
	if not enabled_for():
		frappe.throw(_("Drawing import is not available for your account yet"), frappe.PermissionError)


def _schedule(schedule, lock=False):
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	_require_enabled()
	return schedule_context(schedule, write=True, lock=lock)


def _editable_problem(doc):
	if doc.get("is_locked"):
		return _("This schedule version is locked")
	if doc.get("status") not in EDITABLE:
		return _("This schedule is {0}").format(doc.get("status") or _("not editable"))
	return None


def _sales_staff():
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return allowed("sales")


def _catalog_check(package, schedule_name=None):
	"""Warnings about the catalog the drawing was made on: unknown snapshot, or older than 30 days."""
	from frappe.utils import date_diff, getdate, nowdate

	from illumenate_lighting.illumenate_lighting.system_design import catalog

	warnings = []
	snapshot = package["catalog"]["snapshot_hash"]
	generated = frappe.db.get_value(catalog.SNAPSHOT_DOCTYPE, snapshot, "generated_on")
	if not generated:
		warnings.append(_("The drawing's catalog is not one this server built; download the current catalog"))
	elif snapshot != catalog.current_snapshot_hash():
		try:
			age = date_diff(nowdate(), getdate(generated))
		except Exception:
			age = 0
		if age > CATALOG_STALE_DAYS:
			warnings.append(
				_("The drawing's catalog is {0} days old; download the current one and run ILCHECK").format(
					age
				)
			)
	target = package.get("target") or {}
	if target.get("schedule") and schedule_name and target["schedule"] != schedule_name:
		warnings.append(
			_("The drawing was set up for schedule {0}; it is being imported into {1}").format(
				target["schedule"], schedule_name
			)
		)
	return warnings


def _toolkit_check(package):
	check = package["check"]
	problems = []
	if check["errors"]:
		problems.append(
			_(
				"The drawing has {0} ILCHECK errors; fix or override them in AutoCAD, then run ILQUOTE again"
			).format(check["errors"])
		)
	return problems


def _counts(rows, other_rows, removals):
	counts = {
		"ok": 0,
		"needs_choice": 0,
		"error": 0,
		"add": 0,
		"update": 0,
		"unchanged": 0,
		"remove": len(removals),
	}
	for row in rows + other_rows:
		counts[row["status"]] += 1
		if row.get("action") in counts and row["status"] == "ok":
			counts[row["action"]] += 1
	return counts


def _plan(doc, package, choices):
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import FLAG

	# The configurators check access again; an editor of this schedule may configure for it.
	frappe.flags[FLAG] = doc.name
	return Planner(doc, package, _sales_staff(), choices).plan()


def _choices(value):
	if value in (None, ""):
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("Invalid choices"))
	if not isinstance(value, dict):
		frappe.throw(_("Invalid choices"))
	return value


def _truthy(value):
	return str(value or "").strip().lower() in ("1", "true", "yes", "on")


# --- Endpoints -------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def preview_drawing_import(schedule, filename, content, choices=None, options=None):
	"""Dry run: every run's planned build and status, the lines to remove and the design delta."""
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import strip_prices

	doc = _schedule(schedule)
	package, digest = read_package(filename, content, options)
	rows, other_rows, removals, _saves, _others = _plan(doc, package, _choices(choices))
	problem = _editable_problem(doc)
	return strip_prices(
		{
			"success": True,
			"schedule": doc.name,
			"package_sha256": digest,
			"drawing": package["drawing"],
			"rows": rows,
			"other_lines": other_rows,
			"removals": removals,
			"counts": _counts(rows, other_rows, removals),
			"warnings": _catalog_check(package, doc.name),
			"blocking": _toolkit_check(package),
			"new_version_required": bool(problem),
			"locked_reason": problem,
			"site": {
				"rooms": len(package.get("rooms") or []),
				"cabinets": len(package.get("cabinets") or []),
				"wire_paths": len(package.get("wire_paths") or []),
				"psus": len(package.get("psus") or []),
			},
			"modified": str(doc.modified),
		}
	)


def _new_version(doc):
	"""Lock ``doc`` and continue in a new editable version (PR #375: lines keep ``line_key``)."""
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	name = doc.create_new_version(version_notes=_("Drawing import"))
	return schedule_context(name, write=True, lock=True)


def _idempotency_key(digest, schedule_name, start_modified, cad_key):
	"""Stable for a retry of the same commit (same package, same schedule state), new otherwise."""
	text = f"cad:{digest}:{schedule_name}:{start_modified}:{cad_key}"
	return hashlib.sha256(text.encode()).hexdigest()[:64]


def _save_build(schedule_name, request, entry, run, digest, start_modified, expected_modified):
	from illumenate_lighting.illumenate_lighting.portal import configuration, kit_configuration

	metadata = {"line_id": run["fixture_type"], "location": _location(run) or "", "qty": 1}
	if run.get("notes"):
		metadata["notes"] = run["notes"]
	key = _idempotency_key(digest, schedule_name, start_modified, entry["cad_run_id"])
	if request["family"] == KIT:
		metadata["qty"] = entry["qty"]
		return kit_configuration.save(
			schedule_name,
			request["selections"],
			key,
			expected_modified,
			line_key=entry.get("line_key"),
			metadata=metadata,
		)
	segments = request.get("segments")
	return configuration.save(
		schedule_name,
		request["family"],
		request["selections"],
		key,
		expected_modified,
		line_key=entry.get("line_key"),
		metadata=metadata,
		template=request["template"],
		segments=json.dumps(segments) if segments is not None else None,
	)


OTHER_FIELDS = ("qty", "location", "manufacturer_name", "fixture_model_number", "notes")


def update_other_line(line, line_data):
	"""Apply a re-imported other-manufacturer line to its existing row."""
	from illumenate_lighting.illumenate_lighting.system_design import dealer_data

	for field in OTHER_FIELDS:
		if field in line_data:
			line.set(field, line_data[field])
	dealer_data.apply(line, line_data)


CONTROL_FIELDS = (
	"qty",
	"location",
	"accessory_item",
	"accessory_item_name",
	"accessory_product_type",
	"notes",
)


def update_control_line(line, line_data):
	"""Apply a re-imported control to its existing accessory line."""
	for field in CONTROL_FIELDS:
		if field in line_data:
			line.set(field, line_data[field])


def _remove_lines(doc, keys):
	"""Remove lines by ``line_key``, with the supply lines that belong to them."""
	keys = set(keys)
	doc.lines = [
		line
		for line in doc.lines
		if line.get("line_key") not in keys and line.get("power_supply_for_line") not in keys
	]
	for index, line in enumerate(doc.lines, start=1):
		line.idx = index


MAX_PDF_BYTES = 20 * 1024 * 1024


def read_plan_pdf(plan_pdf):
	"""The optional plotted plan: checked PDF bytes, or ``None``."""
	from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

	if not plan_pdf:
		return None
	if not isinstance(plan_pdf, str) or len(plan_pdf) > (MAX_PDF_BYTES * 4) // 3 + 4:
		frappe.throw(_("The plan PDF is larger than 20 MB"))
	try:
		data = base64.b64decode(plan_pdf, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The plan PDF could not be read"))
	try:
		validate_content("plan.pdf", data)
	except ValueError as error:
		frappe.throw(str(error))
	return data


def store_plan_pdf(record, doc, data):
	"""Keep the plan on the import and, when the schedule has a design, in its documentation (4.6)."""
	from illumenate_lighting.illumenate_lighting.system_design import deliverables, designs
	from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

	digest = hashlib.sha256(data).hexdigest()
	stem = (record.drawing_file or "plan").rsplit(".", 1)[0]
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{stem}-rev{record.drawing_rev or 0}.pdf",
			"content": data,
			"is_private": 1,
			"attached_to_doctype": DOCTYPE,
			"attached_to_name": record.name,
			"attached_to_field": "plan_pdf",
		}
	)
	file.flags.ignore_permissions = True
	file.insert()
	record.db_set({"plan_pdf": file.file_url, "plan_pdf_sha256": digest}, update_modified=False)
	design = designs.current_design(doc)
	if design is None:
		return None
	try:
		return deliverables.upload_deliverable(
			design.name,
			"Plan PDF",
			f"rev{record.drawing_rev or 0}",
			digest,
			content=data,
			filename="plan.pdf",
		)
	except DesignError as error:
		frappe.throw(error.message)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
@atomic_build
def commit_drawing_import(
	schedule,
	filename,
	content,
	expected_modified=None,
	choices=None,
	confirm_removals=None,
	new_version=None,
	plan_pdf=None,
	options=None,
):
	"""Plan again and apply the drawing to ``schedule`` in one transaction, all or nothing.

	Returns the receipt the toolkit reads back (``ILRECEIPT``), or ``{"success": False, ...}`` with the
	rows to fix. ``new_version`` imports into a new version when the schedule is locked or quoted.
	"""
	from illumenate_lighting.illumenate_lighting.portal.line_add import append_line
	from illumenate_lighting.illumenate_lighting.portal.schedule_lines import require_fresh

	doc = _schedule(schedule, lock=True)
	require_fresh(doc, expected_modified)
	package, digest = read_package(filename, content, options)
	plan = read_plan_pdf(plan_pdf)
	blocking = _toolkit_check(package)
	if blocking:
		return {"success": False, "error": blocking[0], "blocking": blocking}
	problem = _editable_problem(doc)
	if problem:
		if not _truthy(new_version):
			return {"success": False, "error": problem, "new_version_required": True}
		doc = _new_version(doc)
	choices = _choices(choices)
	rows, other_rows, removals, saves, others = _plan(doc, package, choices)
	counts = _counts(rows, other_rows, removals)
	if counts["error"] or counts["needs_choice"]:
		return {
			"success": False,
			"error": _("Fix the runs with errors or choices before importing"),
			"rows": rows,
			"counts": counts,
		}
	if removals and not _truthy(confirm_removals):
		return {
			"success": False,
			"error": _("Confirm removing {0} lines whose runs are no longer in the drawing").format(
				len(removals)
			),
			"removals": removals,
			"confirm_removals_required": True,
		}
	modified = start_modified = str(doc.modified)
	line_keys, results = {}, {}
	for save in saves:
		entry = save["entry"]
		if entry["action"] == "unchanged":
			line_keys[entry["cad_run_id"]] = entry["line_key"]
			continue
		response = _save_build(
			doc.name, save["request"], entry, save["run"], digest, start_modified, modified
		)
		if not response.get("success"):
			frappe.throw(
				_("Run {0}: {1}").format(save["run"]["id"], response.get("error") or _("could not be saved"))
			)
		modified = response["modified"]
		line_keys[entry["cad_run_id"]] = response["line_key"]
		results[entry["cad_run_id"]] = response
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	doc = schedule_context(doc.name, write=True, lock=True)
	by_key = {line.get("line_key"): line for line in doc.lines}
	for cad_key, line_key in line_keys.items():
		line = by_key.get(line_key)
		if line is not None:
			line.cad_run_id = cad_key
	for data in others:
		line = next((item for item in doc.lines if item.get("cad_run_id") == data["cad_run_id"]), None)
		if line is not None:
			# Update in place: the line keeps its line_key, so quotes and orders stay linked.
			if data.get("kind") == "control":
				update_control_line(line, data["line_data"])
			else:
				update_other_line(line, data["line_data"])
		else:
			error = append_line(doc, data["line_data"], _sales_staff())
			if error:
				frappe.throw(_("Line {0}: {1}").format(data["line_data"]["line_id"], error))
			line = doc.lines[-1]
			line.cad_run_id = data["cad_run_id"]
			if not line.get("line_key"):
				line.line_key = uuid.uuid4().hex
		line_keys[data["cad_run_id"]] = line.line_key
	removed_keys = [row["line_key"] for row in removals if row.get("line_key")]
	if removed_keys:
		_remove_lines(doc, removed_keys)
	doc.save(ignore_permissions=True)
	record = _store(doc, package, digest, rows, other_rows, removals, line_keys, others)
	if plan is not None:
		store_plan_pdf(record, doc, plan)
	receipt = json.loads(record.receipt_json)
	from illumenate_lighting.illumenate_lighting.system_design import telemetry

	telemetry.record(
		"cad_import",
		doc.name,
		details={
			"import": record.name,
			"runs": len(package["runs"]),
			"added": record.runs_added,
			"updated": record.runs_updated,
		},
	)
	return {
		"success": True,
		"schedule": doc.name,
		"modified": str(doc.modified),
		"receipt": receipt,
		"import": record.name,
	}


# --- Receipt and record ------------------------------------------------------------------------


def _configured_link(line):
	for field, doctype in (
		("configured_tape_neon", "ilL-Configured-Tape-Neon"),
		("configured_fixture", "ilL-Configured-Fixture"),
		("configured_group", "ilL-Configured-Group"),
	):
		if line.get(field):
			return doctype, line.get(field)
	return None, None


def receipt_for(doc, package, rows, removals, line_keys, import_name):
	"""What ILRECEIPT stamps back into the drawing, per run: keys, part numbers, server lengths."""
	by_key = {line.get("line_key"): line for line in doc.lines}
	runs = []
	plans = {row["id"]: row for row in rows}
	for run in package["runs"]:
		row = plans.get(run["id"]) or {}
		parts = []
		for entry in row.get("parts") or []:
			line = by_key.get(line_keys.get(entry["cad_run_id"]))
			doctype, name = _configured_link(line) if line is not None else (None, None)
			config_hash = (
				frappe.db.get_value(doctype, name, "config_hash")
				if doctype and doctype != "ilL-Configured-Group"
				else None
			)
			parts.append(
				{
					"part": entry["part"],
					"cad_run_id": entry["cad_run_id"],
					"line_key": line.get("line_key") if line is not None else None,
					"configured_doctype": doctype,
					"configured_name": name,
					"config_hash": config_hash,
					"part_number": (line.get("group_part_number") or line.get("ill_item_code"))
					if line is not None
					else entry.get("part_number"),
					"qty": entry.get("qty") or 1,
					"server_length_in": entry.get("server_length_in"),
					"segments_in": entry.get("segments_in") or [],
					"runs_in": entry.get("runs_in") or [],
					"watts": entry.get("watts"),
				}
			)
		build = next((part for part in parts if part["part"] != "kit"), parts[0] if parts else {})
		runs.append(
			{
				"id": run["id"],
				"handle": run["handle"],
				"fixture_type": run["fixture_type"],
				"line_key": build.get("line_key"),
				"configured_doctype": build.get("configured_doctype"),
				"configured_name": build.get("configured_name"),
				"config_hash": build.get("config_hash"),
				"part_number": build.get("part_number"),
				"server_length_in": build.get("server_length_in"),
				"drawn_length_in": row.get("drawn_length_in"),
				"cut_list_in": build.get("runs_in") or build.get("segments_in") or [],
				"parts": parts,
			}
		)
	return {
		"schema": RECEIPT_SCHEMA,
		"import": import_name,
		"schedule": doc.name,
		"schedule_version": doc.get("version") or 0,
		"modified": str(doc.modified),
		"drawing": package["drawing"],
		"runs": runs,
		"removed": [row["id"] for row in removals],
		"other_lines": {key: line_keys.get(key) for key in line_keys if key.startswith(OTHER_PREFIX)},
		"controls": {
			control["id"]: line_keys.get(control["id"]) for control in package.get("controls") or []
		},
	}


def _store(doc, package, digest, rows, other_rows, removals, line_keys, others=()):
	from frappe.utils import now_datetime

	from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json

	previous = frappe.get_all(DOCTYPE, filters={"schedule": doc.name, "status": "Committed"}, pluck="name")
	for name in previous:
		frappe.db.set_value(DOCTYPE, name, "status", "Superseded", update_modified=False)
	run_line_keys = {run["id"]: line_keys.get(run["id"]) for run in package["runs"]}
	counts = _counts(rows, other_rows, removals)
	record = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"schedule": doc.name,
			"schedule_version": doc.get("version") or 0,
			"status": "Committed",
			"imported_by": frappe.session.user,
			"imported_on": now_datetime(),
			"drawing_file": package["drawing"]["file"][:140],
			"drawing_rev": package["drawing"]["rev"],
			"drawing_hash": package["drawing"]["hash"],
			"toolkit_version": package["toolkit"]["version"],
			"catalog_snapshot": package["catalog"]["snapshot_hash"],
			"runs_added": counts["add"],
			"runs_updated": counts["update"],
			"runs_unchanged": counts["unchanged"],
			"lines_removed": counts["remove"],
			"other_lines": len(other_rows),
			"check_errors": package["check"]["errors"],
			"check_warnings": package["check"]["warnings"],
			"package_sha256": digest,
			"package_json": canonical_json(package),
		}
	)
	record.flags.cad_import_service_write = True
	record.insert(ignore_permissions=True)
	receipt = receipt_for(doc, package, rows, removals, line_keys, record.name)
	record.receipt_json = canonical_json(receipt)
	controls = {
		data["cad_run_id"]: {**data["control"], "lineKey": line_keys.get(data["cad_run_id"])}
		for data in others
		if data.get("kind") == "control"
	}
	record.site_json = canonical_json(site_seed(package, run_line_keys, record.name, controls))
	record.flags.cad_import_service_write = True
	record.save(ignore_permissions=True)
	return record


def latest_site(schedule_name):
	"""The design site of the schedule's current drawing import, or ``None`` (System Designer open)."""
	if not frappe.db.exists("DocType", DOCTYPE):
		return None
	rows = frappe.get_all(
		DOCTYPE,
		filters={"schedule": schedule_name, "status": "Committed"},
		fields=["name", "site_json"],
		order_by="creation desc",
		limit=1,
	)
	if not rows or not rows[0].site_json:
		return None
	try:
		return json.loads(rows[0].site_json)
	except ValueError:
		return None


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_drawing_receipt(schedule, cad_import=None):
	"""The receipt of the schedule's latest (or the named) drawing import, as a download for ILRECEIPT."""
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	_require_enabled()
	doc = schedule_context(schedule)
	filters = {"schedule": doc.name}
	if cad_import:
		filters["name"] = cad_import
	rows = frappe.get_all(
		DOCTYPE, filters=filters, fields=["name", "receipt_json"], order_by="creation desc", limit=1
	)
	if not rows:
		frappe.throw(_("This schedule has no drawing import yet"), frappe.DoesNotExistError)
	return {"success": True, "import": rows[0].name, "receipt": json.loads(rows[0].receipt_json or "{}")}


@frappe.whitelist(methods=["GET"])
def list_drawing_imports(schedule):
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	_require_enabled()
	doc = schedule_context(schedule)
	return {
		"success": True,
		"imports": frappe.get_all(
			DOCTYPE,
			filters={"schedule": doc.name},
			fields=[
				"name",
				"status",
				"drawing_file",
				"drawing_rev",
				"imported_by",
				"imported_on",
				"runs_added",
				"runs_updated",
				"runs_unchanged",
				"lines_removed",
			],
			order_by="creation desc",
			limit=20,
		),
	}
