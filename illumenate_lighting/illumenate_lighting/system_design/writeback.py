# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design-owned schedule lines: supplies, controls, wire Items and accessories (plan H8.6, WP-4.1).

The design's equipment and wire become ACCESSORY lines on its schedule, keyed
``design_line_key = "<role>:<item_code>"`` and marked with ``system_design`` and ``design_line_role``.
A preview lists what would be added, changed and removed; applying writes only the changes the user
accepted, in one transaction. Lines without ``design_line_role`` are never touched, except the
configurator's own supply lines for builds the design now powers, which are removed after the user
confirms (consolidation, plan §14.6). Prices appear only for users with ``Can View Pricing``, and only
as selling prices; costs never leave the server (D6).

Equipment comes from the saved design and the catalog snapshot it was built against. Wire footage
comes from the designer's engine (wire selection for every run type lives in the browser); the server
checks each wire is a catalog wire with an Item and that the footage is sensible, and rounds it to
whole feet or spools (D7).
"""

import json
import math
import uuid

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design import (
	access,
	catalog,
	expansion,
	reconcile,
	telemetry,
)
from illumenate_lighting.illumenate_lighting.system_design.design_schema import canonical_json
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

DESIGN_DOCTYPE = "ilL-System-Design"
EDITABLE_SCHEDULE_STATUSES = ("DRAFT", "READY")
ROLES = ("Supply", "Controller", "Wire", "Accessory")
ROLE_BY_KIND = {
	"psu": "Supply",
	"driver": "Supply",
	"decoder": "Controller",
	"controller": "Controller",
	"accessory": "Accessory",
}
LINE_PREFIX = {"Supply": "PS", "Controller": "CTRL", "Wire": "WIRE", "Accessory": "ACC"}
MAX_WIRE_FT = 1_000_000
MAX_KEYS = 500
WIRE_LOCATION = "Field wire"
REPLACE_PREFIX = "replace:"
PRICE_LIST = "Standard Selling"


# --- Pure planning --------------------------------------------------------------------------------


def _role(item):
	specs = item.get("specs") or {}
	kind = specs.get("intendedKind") if specs.get("kind") == "incomplete" else specs.get("kind")
	return ROLE_BY_KIND.get(kind)


def _join(values, limit=140):
	text = ", ".join(sorted({value for value in values if value}))
	return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_wire_feet(value):
	"""``{wire id: feet}`` from the designer; raises ``INVALID`` for anything else."""
	if value in (None, ""):
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			raise DesignError("INVALID", _("wire_feet must be valid JSON"))
	if not isinstance(value, dict) or len(value) > MAX_KEYS:
		raise DesignError("INVALID", _("wire_feet must be an object of wire ids and feet"))
	feet = {}
	for wire_id, amount in value.items():
		if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
			raise DesignError("INVALID", _("Wire footage must be a number"))
		if amount < 0 or amount > MAX_WIRE_FT:
			raise DesignError("INVALID", _("Wire footage is out of range"))
		if amount > 0:
			feet[str(wire_id)] = float(amount)
	return feet


def wire_quantity(feet, wire):
	"""Whole feet, or whole spools when the Item is sold by the spool (H8.6). ``feet`` includes waste."""
	spool = wire.get("spoolLengthFt")
	if wire.get("salesUom") == "spool" and spool:
		return math.ceil(round(feet / spool, 6))
	return math.ceil(round(feet, 6))


def desired_lines(design, snapshot, wire_feet):
	"""``(desired, blocked)``: the lines the design wants, keyed by ``design_line_key``, and what it can't add.

	Pure. ``snapshot`` is the catalog payload the design was built against; ``wire_feet`` maps catalog
	wire ids to engine footage including waste.
	"""
	items = {item["id"]: item for item in snapshot.get("items") or []}
	wires = {wire["id"]: wire for wire in snapshot.get("wires") or []}
	cabinets = {cabinet["id"]: cabinet for cabinet in (design.get("site") or {}).get("cabinets") or []}
	desired, blocked = {}, []
	for entity in (design.get("project") or {}).get("equipment") or []:
		item = items.get(entity.get("catalogId"))
		role = _role(item) if item else None
		code = (item or {}).get("erpItemCode")
		if not item or not role or not code or item.get("isExample"):
			blocked.append(
				{
					"ref": entity.get("tag") or entity.get("id"),
					"reason": _("{0} is not an orderable ilLumenate product").format(
						entity.get("tag") or entity.get("catalogId")
					),
				}
			)
			continue
		cabinet = cabinets.get(entity.get("enclosure") or "")
		location = (cabinet or {}).get("name") or entity.get("location") or ""
		key = f"{role}:{code}"
		row = desired.setdefault(
			key, {"key": key, "role": role, "item_code": code, "qty": 0, "locations": set(), "tags": []}
		)
		row["qty"] += max(int(entity.get("qty") or 0), 0)
		row["locations"].add(location)
		row["tags"].append(entity.get("tag") or entity.get("id"))
	for wire_id, feet in sorted(wire_feet.items()):
		wire = wires.get(wire_id)
		code = (wire or {}).get("erpItemCode")
		if not wire or not code or wire.get("isExample"):
			blocked.append({"ref": wire_id, "reason": _("{0} is not an orderable wire").format(wire_id)})
			continue
		key = f"Wire:{code}"
		row = desired.setdefault(
			key,
			{
				"key": key,
				"role": "Wire",
				"item_code": code,
				"qty": 0,
				"locations": {WIRE_LOCATION},
				"tags": [],
			},
		)
		row["feet"] = row.get("feet", 0) + feet
		row["qty"] = wire_quantity(row["feet"], wire)
		row["unit"] = "spool" if wire.get("salesUom") == "spool" and wire.get("spoolLengthFt") else "ft"
	for row in desired.values():
		row["location"] = _join(row.pop("locations"))
		row["tags"] = sorted(tag for tag in row["tags"] if tag)
	return {key: row for key, row in desired.items() if row["qty"] > 0}, blocked


def powered_owner_keys(runs, lines):
	"""Raw ``line_key`` of every schedule line with a run the design assigns to its own equipment."""
	by_key = {line["key"]: line for line in lines}
	owners = set()
	for run in runs or ():
		if isinstance(run.get("assignment"), dict):
			line = by_key.get(run.get("lineKey"))
			if line and line.get("lineKey"):
				owners.add(line["lineKey"])
	return owners


def plan_changes(desired, owned, configurator_lines, owners):
	"""Pure H8.6 diff. ``owned``: existing design lines ``{key: {qty, location, line_id, item_code}}``.

	``configurator_lines``: ``[{line_key, line_id, item_code, qty, for_line}]`` with ``for_line`` the
	owner's ``line_key``; those under ``owners`` are replaced, grouped per owner as ``replace:<owner>``.
	"""
	add, update, remove = [], [], []
	for key, row in sorted(desired.items()):
		current = owned.get(key)
		entry = {k: row[k] for k in ("key", "role", "item_code", "qty", "location", "tags") if k in row}
		if "unit" in row:
			entry["unit"] = row["unit"]
		if current is None:
			add.append(entry)
		elif current["qty"] != row["qty"] or (current.get("location") or "") != row["location"]:
			update.append({**entry, "from_qty": current["qty"], "line_id": current.get("line_id")})
	for key, current in sorted(owned.items()):
		if key not in desired:
			remove.append(
				{
					"key": key,
					"item_code": current.get("item_code"),
					"qty": current["qty"],
					"line_id": current.get("line_id"),
				}
			)
	groups = {}
	for line in configurator_lines:
		if line.get("for_line") in owners:
			groups.setdefault(line["for_line"], []).append(line)
	replaces = [
		{
			"key": f"{REPLACE_PREFIX}{owner}",
			"for_line": owner,
			"line_id": rows[0].get("line_id"),
			"lines": [{"item_code": row.get("item_code"), "qty": row.get("qty") or 0} for row in rows],
		}
		for owner, rows in sorted(groups.items())
	]
	return {"add": add, "update": update, "remove": remove, "replaces_configurator_lines": replaces}


def change_keys(plan):
	return {
		entry["key"]
		for part in ("add", "update", "remove", "replaces_configurator_lines")
		for entry in plan[part]
	}


def price_delta(plan, prices):
	"""Selling-price change of applying every change; ``prices`` maps item code → unit price."""
	total, unpriced = 0.0, set()

	def add(code, qty):
		nonlocal total
		if not qty:
			return
		if code in prices:
			total += prices[code] * qty
		else:
			unpriced.add(code)

	for entry in plan["add"]:
		add(entry["item_code"], entry["qty"])
	for entry in plan["update"]:
		add(entry["item_code"], entry["qty"] - entry["from_qty"])
	for entry in plan["remove"]:
		add(entry["item_code"], -entry["qty"])
	for group in plan["replaces_configurator_lines"]:
		for row in group["lines"]:
			add(row["item_code"], -row["qty"])
	return {"amount": round(total, 2), "price_list": PRICE_LIST, "unpriced": sorted(unpriced)}


def next_line_id(prefix, taken):
	"""``PS1``, ``PS2`` … the first id no line on the schedule uses."""
	index = 1
	while f"{prefix}{index}" in taken:
		index += 1
	line_id = f"{prefix}{index}"
	taken.add(line_id)
	return line_id


# --- Schedule access ------------------------------------------------------------------------------


def _owned(schedule_doc):
	owned = {}
	for line in schedule_doc.lines:
		if line.get("design_line_role") and line.get("design_line_key"):
			owned[line.design_line_key] = {
				"qty": int(line.get("qty") or 0),
				"location": line.get("location") or "",
				"line_id": line.get("line_id"),
				"item_code": line.get("accessory_item"),
			}
	return owned


def _configurator_lines(schedule_doc):
	from illumenate_lighting.illumenate_lighting.api.power_supply_lines import OWNER_FIELD

	return [
		{
			"line_key": line.get("line_key"),
			"line_id": line.get("line_id"),
			"item_code": line.get("accessory_item"),
			"qty": int(line.get("qty") or 0),
			"for_line": line.get(OWNER_FIELD),
		}
		for line in schedule_doc.lines
		if line.get(OWNER_FIELD) and not line.get("design_line_role")
	]


def _prices(codes):
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item Price",
		filters={"item_code": ["in", sorted(codes)], "price_list": PRICE_LIST, "selling": 1},
		fields=["item_code", "price_list_rate"],
	)
	return {row.item_code: float(row.price_list_rate) for row in rows if row.price_list_rate}


def _item_names(codes):
	if not codes:
		return {}
	rows = frappe.get_all("Item", filters={"name": ["in", sorted(codes)]}, fields=["name", "item_name"])
	return {row.name: row.item_name or row.name for row in rows}


def _context(design, build_hash=None, wire_feet=None, edit=False):
	"""Load and check everything a preview or apply needs."""
	record = access.require_design(design)
	schedule_doc = (
		access.require_edit(record.fixture_schedule) if edit else access.require_read(record.fixture_schedule)
	)
	if not record.is_current or record.schedule_version != (schedule_doc.get("version") or 0):
		raise DesignError("CONFLICT", _("Open the current revision of this design to add it to the schedule"))
	if build_hash and build_hash != record.build_hash:
		raise DesignError("CONFLICT", _("Save the design before adding it to the schedule"))
	lines, builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	stored = json.loads(record.line_fingerprint_json or "{}")
	design_doc = json.loads(record.design_json or "{}")
	if not reconcile.diff(stored, lines, builds, design_doc.get("runs") or [])["in_sync"]:
		raise DesignError(
			"CONFLICT", _("The schedule changed since this design was saved; review the changes first")
		)
	snapshot = catalog.get_snapshot(record.catalog_snapshot) or {"items": [], "wires": []}
	desired, blocked = desired_lines(design_doc, snapshot, parse_wire_feet(wire_feet))
	owners = powered_owner_keys(design_doc.get("runs"), lines)
	plan = plan_changes(desired, _owned(schedule_doc), _configurator_lines(schedule_doc), owners)
	return record, schedule_doc, plan, blocked


def preview(design, wire_feet=None, build_hash=None):
	"""H6 ``writeback_preview``: the changes applying would make, with item names; prices only for pricing."""
	from illumenate_lighting.illumenate_lighting.system_design.designs import require_designer

	record, schedule_doc, plan, blocked = _context(design, build_hash, wire_feet)
	require_designer()
	codes = {entry["item_code"] for part in ("add", "update", "remove") for entry in plan[part]}
	codes |= {row["item_code"] for group in plan["replaces_configurator_lines"] for row in group["lines"]}
	names = _item_names({code for code in codes if code})
	for part in ("add", "update", "remove"):
		for entry in plan[part]:
			entry["item_name"] = names.get(entry["item_code"], entry["item_code"])
	for group in plan["replaces_configurator_lines"]:
		for row in group["lines"]:
			row["item_name"] = names.get(row["item_code"], row["item_code"])
	result = {
		**plan,
		"blocked": blocked,
		"error_count": int(record.get("error_count") or 0),
		"can_apply": bool(
			not schedule_doc.get("is_locked") and schedule_doc.get("status") in EDITABLE_SCHEDULE_STATUSES
		),
	}
	if "Can View Pricing" in frappe.get_roles():
		result["price_delta"] = price_delta(plan, _prices({code for code in codes if code}))
	return result


def _orderable_problem(item_code):
	from illumenate_lighting.illumenate_lighting.api.portal import orderable_item_problem
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return orderable_item_problem(item_code, allowed("sales"))


def parse_keys(value):
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			raise DesignError("INVALID", _("accepted_keys must be valid JSON"))
	if not isinstance(value, list) or len(value) > MAX_KEYS or not all(isinstance(key, str) for key in value):
		raise DesignError("INVALID", _("accepted_keys must be a list of change keys"))
	return set(value)


def _add_line(schedule_doc, entry, record, taken, names):
	line = schedule_doc.append("lines", {})
	line.line_key = uuid.uuid4().hex
	line.line_id = next_line_id(LINE_PREFIX[entry["role"]], taken)
	line.qty = entry["qty"]
	line.location = entry["location"]
	line.manufacturer_type = "ACCESSORY"
	line.configuration_status = "Configured"
	line.accessory_item = entry["item_code"]
	line.accessory_item_name = names.get(entry["item_code"], entry["item_code"])
	line.system_design = record.name
	line.design_line_role = entry["role"]
	line.design_line_key = entry["key"]
	if entry.get("tags"):
		line.notes = _("System design {0}: {1}").format(record.revision, ", ".join(entry["tags"]))[:500]


def apply(design, accepted_keys, wire_feet=None, build_hash=None):
	"""H6 ``writeback_apply``: write the accepted changes in one transaction (H8.6)."""
	from illumenate_lighting.illumenate_lighting.api.power_supply_lines import clear_power_lines
	from illumenate_lighting.illumenate_lighting.system_design.designs import require_designer

	record, schedule_doc, plan, _blocked = _context(design, build_hash, wire_feet, edit=True)
	require_designer()
	if schedule_doc.get("status") not in EDITABLE_SCHEDULE_STATUSES:
		raise DesignError("INVALID", _("Lines can only be added to a schedule in Draft or Ready"))
	accepted = parse_keys(accepted_keys)
	unknown = accepted - change_keys(plan)
	if unknown:
		raise DesignError("CONFLICT", _("The design changed since the preview; review the changes again"))
	adds = [entry for entry in plan["add"] if entry["key"] in accepted]
	updates = [entry for entry in plan["update"] if entry["key"] in accepted]
	removes = {entry["key"] for entry in plan["remove"] if entry["key"] in accepted}
	replaces = [group for group in plan["replaces_configurator_lines"] if group["key"] in accepted]
	problems = [
		f"{entry['item_code']}: {problem}"
		for entry in adds + updates
		if (problem := _orderable_problem(entry["item_code"]))
	]
	if problems:
		raise DesignError("INVALID", "; ".join(problems[:5]))
	names = _item_names({entry["item_code"] for entry in adds})
	try:
		by_key = {line.design_line_key: line for line in schedule_doc.lines if line.get("design_line_role")}
		for entry in updates:
			line = by_key[entry["key"]]
			line.qty = entry["qty"]
			line.location = entry["location"]
			line.system_design = record.name
		schedule_doc.lines[:] = [
			line
			for line in schedule_doc.lines
			if not (line.get("design_line_role") and line.get("design_line_key") in removes)
		]
		owners = {line.get("line_key"): line for line in schedule_doc.lines if line.get("line_key")}
		for group in replaces:
			owner = owners.get(group["for_line"])
			if owner is not None:
				clear_power_lines(schedule_doc, owner)
		taken = {line.get("line_id") for line in schedule_doc.lines if line.get("line_id")}
		for entry in adds:
			_add_line(schedule_doc, entry, record, taken, names)
		for index, line in enumerate(schedule_doc.lines, 1):
			line.idx = index
		schedule_doc.save()
		# The design produced these changes, so it stays in step with its schedule.
		lines, builds, _readiness = expansion.expand_schedule(schedule_doc, {})
		frappe.db.set_value(
			DESIGN_DOCTYPE,
			record.name,
			"line_fingerprint_json",
			canonical_json(reconcile.fingerprints(lines, builds)),
			update_modified=False,
		)
	except DesignError:
		frappe.db.rollback()
		raise
	except frappe.ValidationError:
		frappe.db.rollback()
		raise
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"System Designer write-back: {record.name}"[:140])
		raise DesignError("INTERNAL", _("The schedule could not be updated. Nothing was changed."))
	result = {
		"added": len(adds),
		"updated": len(updates),
		"removed": len(removes),
		"replaced": len(replaces),
	}
	telemetry.record("written_back", record.fixture_schedule, record.name, result)
	return result
