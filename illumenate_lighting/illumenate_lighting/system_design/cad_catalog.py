# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The CAD catalog (``cad-catalog/1``): what the AutoCAD toolkit needs to draw, never to price.

A projection of the same spec doctypes and the same Design Catalog snapshot the System Designer uses
(CAD toolkit plan 1.3), so a drawing and a design made on one snapshot agree:

- ``templates``: tape and neon templates with their selectable options and every (spec, offering)
  variant's W/ft, cut interval, max runs, reel, width and bend radius, all in inches;
- ``fixture_templates`` and ``kit_templates``: linear fixture and extrusion kit templates with their
  default profile (drawn outline only; sticks, caps and clips come from the build on import);
- ``profiles``: width, stock length, curve capability and the cross-section outline;
- ``drivers``, ``controllers`` and ``wires``: the designer snapshot's items, for PSU location tags;
- ``styles``: the user's own and company-shared configuration presets (run styles, plan 3.5).

D6: no cost, price, MSRP, adder or supply rank. :func:`forbidden_keys` walks every payload.
Dealers see Active templates; staff also see Internal Only ones (``portal_listing``).
The pure ``build_*`` functions take loaded rows; only ``load_*`` touch the database.
"""

import hashlib
import json

import frappe

from illumenate_lighting.illumenate_lighting.system_design import catalog, units

SCHEMA = "cad-catalog/1"
TAPE_TEMPLATE = "ilL-Tape-Neon-Template"
FIXTURE_TEMPLATE = "ilL-Fixture-Template"
KIT_TEMPLATE = "ilL-Extrusion-Kit-Template"
PROFILE = "ilL-Spec-Profile"
TAPE = "ilL-Spec-LED Tape"
OFFERING = "ilL-Rel-Tape Offering"
PRESET = "ilL-Configuration-Preset"
CAD_FORBIDDEN_KEYS = catalog.FORBIDDEN_KEYS | frozenset(
	{
		"msrp",
		"msrp_adder",
		"base_price_msrp",
		"price_per_ft_msrp",
		"price",
		"rate",
		"rank",
		"unit_price",
		"selling_rate",
	}
)
# Tape template option type -> (child row field, configurator selection key, label).
TAPE_OPTIONS = {
	"Environment Rating": ("environment_rating", "environment_rating", "Environment"),
	"CCT": ("cct", "cct", "CCT"),
	"Output Level": ("output_level", "output_level", "Output"),
	"Lens Appearance": ("lens_appearance", "lens_appearance", "Lens"),
	"Power Feed Type": ("power_feed_type", "feed_type", "Feed type"),
	"PCB Mounting": ("pcb_mounting", "pcb_mounting", "PCB mounting"),
	"PCB Finish": ("pcb_finish", "pcb_finish", "PCB finish"),
	"Mounting Method": ("mounting_method", "mounting_method", "Mounting"),
	"Finish": ("finish", "finish", "Finish"),
	"Endcap Style": ("endcap_style", "endcap_style", "Endcap"),
	"Feed Direction": ("feed_direction", "feed_direction", "Feed direction"),
}
OPTION_ORDER = list(TAPE_OPTIONS)
SETTINGS_KEYS = (
	"vd_target_class2_pct",
	"vd_target_line_pct",
	"vd_target_landscape_pct",
	"wire_waste_pct",
	"plan_route_slack_pct",
	"max_watts_per_run_fallback",
)
STALE_DAYS = 30
# tape_neon_configurator.MAX_WATTS_PER_RUN; tests/portal_unit/test_cad_subset.py keeps them equal.
CONFIGURATOR_MAX_WATTS_PER_RUN = 85.0


# --- Pure helpers ------------------------------------------------------------------------------


def _num(value):
	return catalog._num(value)


def _inches(mm):
	value = _num(mm)
	return units.mm_to_in(value) if value else None


def _feet(m):
	value = _num(m)
	return units.m_to_ft(value) if value else None


def _compact(values):
	return {key: value for key, value in values.items() if value not in (None, [], "")}


def bend_radius_in(spec, template):
	"""The tape's minimum inside bend radius in inches: spec radius first, else half the template's
	side-bend diameter, else ``None`` (unknown, so ILCHECK skips the bend check)."""
	radius = _num((spec or {}).get("min_bend_radius_mm"))
	if not radius:
		diameter = _num((template or {}).get("minimum_side_bend_diameter_mm"))
		radius = diameter / 2 if diameter else None
	return units.mm_to_in(radius) if radius else None


def tape_variant(spec, offering, environment, voltages, template):
	"""One drawable variant: the spec's figures with the offering's W/ft and cut overrides."""
	watts, cut_mm = catalog.tape_group(spec, offering or {})
	volts = voltages.get(spec.get("input_voltage"))
	free = bool(spec.get("is_free_cutting") or (template or {}).get("is_free_cutting"))
	pixels = None
	if spec.get("pixel_protocol") not in (None, "", "None") and _num(spec.get("pixels_per_m")):
		pixels = units.per_m_to_per_ft(spec["pixels_per_m"])
	return _compact(
		{
			"id": f"{spec['name']}|{(offering or {}).get('name') or ''}",
			"spec": spec["name"],
			"item": spec.get("item"),
			"environment_rating": environment or None,
			"cct": (offering or {}).get("cct"),
			"output_level": (offering or {}).get("output_level"),
			"voltage": _num(volts),
			"w_per_ft": watts,
			"free_cut": free,
			"cut_mm": None if free else cut_mm,
			"cut_in": None if free or not cut_mm else units.mm_to_in(cut_mm),
			"max_run_single_ft": _num(spec.get("max_run_single_feed_ft"))
			or _num(spec.get("voltage_drop_max_run_length_ft")),
			"max_run_double_ft": _num(spec.get("max_run_double_feed_ft")),
			# What the tape configurator splits on (with 85 W per run); the LISP hint mirrors it.
			"max_run_vd_ft": _num(spec.get("voltage_drop_max_run_length_ft")),
			"reel_ft": _feet(spec.get("reel_length_m")),
			"width_in": _inches(spec.get("tape_width_mm")),
			"min_bend_radius_in": bend_radius_in(spec, template),
			"pixel_protocol": spec.get("pixel_protocol") if pixels else None,
			"pixels_per_ft": pixels,
		}
	)


def template_options(rows):
	"""Active allowed-option rows as ``[{key, label, values, default}]`` in a stable order."""
	grouped = {}
	for row in rows:
		option_type = row.get("option_type")
		if option_type not in TAPE_OPTIONS or not row.get("is_active", 1):
			continue
		field, key, label = TAPE_OPTIONS[option_type]
		value = row.get(field)
		if not value:
			continue
		entry = grouped.setdefault(option_type, {"key": key, "label": label, "values": [], "default": None})
		if value not in entry["values"]:
			entry["values"].append(value)
		if row.get("is_default") and not entry["default"]:
			entry["default"] = value
	options = []
	for option_type in OPTION_ORDER:
		entry = grouped.get(option_type)
		if entry:
			entry["default"] = entry["default"] or entry["values"][0]
			options.append(entry)
	return options


def tape_template(template, allowed_specs, option_rows, specs, offerings, voltages):
	"""A tape/neon template with its options and variants (one per allowed spec and offering)."""
	variants = []
	rows = allowed_specs or (
		[{"tape_spec": template.get("default_tape_spec"), "is_default": 1}]
		if template.get("default_tape_spec")
		else []
	)
	default_variant = None
	for row in rows:
		spec = specs.get(row.get("tape_spec"))
		if not spec:
			continue
		for offering in offerings.get(spec["name"]) or [None]:
			variant = tape_variant(spec, offering, row.get("environment_rating"), voltages, template)
			variants.append(variant)
			if default_variant is None and (
				row.get("is_default") or spec["name"] == template.get("default_tape_spec")
			):
				default_variant = variant["id"]
	if variants and default_variant is None:
		default_variant = variants[0]["id"]
	return _compact(
		{
			"family": template.get("product_category") or "LED Tape",
			"code": template.get("template_code") or template["name"],
			"name": template.get("template_name") or template.get("template_code") or template["name"],
			"status": template.get("product_status"),
			"free_cut": bool(template.get("is_free_cutting")),
			"leader_allowance_in": _inches(template.get("leader_allowance_mm_per_fixture")),
			"options": template_options(option_rows),
			"default_variant": default_variant,
			"variants": variants,
		}
	)


def outline(cross_section_json):
	"""The profile body outline in inches (``cross_section_json`` is in 1/1000 in), else ``None``."""
	if not cross_section_json:
		return None
	try:
		data = json.loads(cross_section_json) if isinstance(cross_section_json, str) else cross_section_json
	except ValueError:
		return None
	result = {}
	for part in ("body", "lens"):
		points = data.get(part) if isinstance(data, dict) else None
		if isinstance(points, list) and len(points) >= 6 and len(points) % 2 == 0:
			try:
				result[part] = [round(float(value) / 1000, 4) for value in points]
			except (TypeError, ValueError):
				continue
	return result or None


def profile_row(profile):
	return _compact(
		{
			"code": profile["name"],
			"item": profile.get("item"),
			"family": profile.get("family"),
			"width_in": _inches(profile.get("width_mm")),
			"height_in": _inches(profile.get("height_mm")),
			"stock_length_in": _inches(profile.get("stock_length_mm")),
			"max_assembled_in": _inches(profile.get("max_assembled_length_mm")),
			"curve_capable": bool(profile.get("is_curve_capable")),
			"outline": outline(profile.get("cross_section_json")),
		}
	)


def fixture_template(template):
	return _compact(
		{
			"family": "Linear Fixture",
			"code": template["name"],
			"name": template.get("template_name") or template["name"],
			"status": template.get("product_status"),
			"profile": template.get("default_profile_spec"),
			"stock_length_in": _inches(template.get("default_profile_stock_len_mm")),
			"max_assembled_in": _inches(template.get("assembled_max_len_mm")),
			"min_bend_radius_in": bend_radius_in(None, template),
		}
	)


def kit_template(template):
	return _compact(
		{
			"family": "Extrusion Kit",
			"code": template["name"],
			"name": template.get("template_name") or template["name"],
			"status": template.get("product_status"),
			"profile": template.get("default_profile_spec"),
			"stock_length_in": _inches(template.get("profile_stock_length_mm")),
		}
	)


def design_items(snapshot):
	"""Drivers, controllers and wires from the designer snapshot, trimmed to what CAD tags show."""
	drivers, controllers = [], []
	for item in (snapshot or {}).get("items") or []:
		specs = item.get("specs") or {}
		kind = specs.get("kind")
		if kind in ("psu", "driver"):
			outputs = specs.get("outputs") or []
			drivers.append(
				_compact(
					{
						"id": item["id"],
						"code": item.get("erpItemCode"),
						"model": item.get("model"),
						"kind": kind,
						"output_v": specs.get("outputV"),
						"rated_w": specs.get("ratedW"),
						"outputs": len(outputs) or None,
						"per_output_w": outputs[0].get("maxW") if outputs else None,
						"class2": bool(outputs and all(output.get("class2") for output in outputs)),
						"usable_load_factor": specs.get("usableLoadFactor"),
						"dimming": specs.get("dimming"),
					}
				)
			)
		elif kind in ("controller", "decoder"):
			controllers.append(
				_compact(
					{
						"id": item["id"],
						"code": item.get("erpItemCode"),
						"model": item.get("model"),
						"category": item.get("category"),
						"protocol_in": specs.get("protocolIn"),
						"protocol_out": specs.get("protocolOut"),
					}
				)
			)
	wires = [
		_compact(
			{
				"id": wire["id"],
				"code": wire.get("erpItemCode"),
				"name": wire.get("name"),
				"category": wire.get("category"),
				"awg": next((row.get("awg") for row in wire.get("conductors") or [] if row.get("awg")), None),
				"verify": bool(wire.get("verify")),
			}
		)
		for wire in (snapshot or {}).get("wires") or []
	]
	return drivers, controllers, wires


def style_row(preset, request):
	"""A run style from a configuration preset (``request`` already re-checked and price-free)."""
	return _compact(
		{
			"id": f"preset:{preset['name']}",
			"label": preset.get("label"),
			"family": request.get("family") or preset.get("family"),
			"template": request.get("template") or preset.get("template"),
			"selections": request.get("selections") or {},
			"segments": request.get("segments"),
			"shared": bool(preset.get("shared_with_company")),
		}
	)


def body_hash(payload):
	"""Hash of the catalog content (everything but who downloaded it and when)."""
	body = {key: value for key, value in payload.items() if key not in ("hash", "generated_at", "styles")}
	return hashlib.sha256(catalog.payload_json(body).encode("utf-8")).hexdigest()


def build_payload(data):
	"""Pure: the ``cad-catalog/1`` document from loaded rows (see :func:`load_data`)."""
	specs = {spec["name"]: spec for spec in data["tapes"]}
	templates = [
		tape_template(
			template,
			data["allowed_specs"].get(template["name"], []),
			data["allowed_options"].get(template["name"], []),
			specs,
			data["offerings"],
			data["voltages"],
		)
		for template in data["tape_templates"]
	]
	drivers, controllers, wires = design_items(data.get("snapshot"))
	payload = {
		"schema": SCHEMA,
		"snapshot_hash": data["snapshot_hash"],
		"generated_at": data.get("generated_at"),
		"engine_contract": catalog.ENGINE_CONTRACT_VERSION,
		"code_tables_version": catalog.CODE_TABLES_VERSION,
		"units": "in",
		"settings": {
			**{key: data["settings"].get(key) for key in SETTINGS_KEYS},
			"max_watts_per_run": CONFIGURATOR_MAX_WATTS_PER_RUN,
			"stale_days": STALE_DAYS,
		},
		"templates": sorted(templates, key=lambda row: (row["family"], row["code"])),
		"fixture_templates": sorted(
			(fixture_template(row) for row in data["fixture_templates"]), key=lambda row: row["code"]
		),
		"kit_templates": sorted(
			(kit_template(row) for row in data["kit_templates"]), key=lambda row: row["code"]
		),
		"profiles": sorted((profile_row(row) for row in data["profiles"]), key=lambda row: row["code"]),
		"drivers": sorted(drivers, key=lambda row: row["id"]),
		"controllers": sorted(controllers, key=lambda row: row["id"]),
		"wires": sorted(wires, key=lambda row: row["id"]),
		"styles": sorted(data.get("styles") or [], key=lambda row: (row.get("label") or "").lower()),
	}
	payload["hash"] = body_hash(payload)
	found = forbidden_keys(payload)
	if found:
		raise ValueError(f"CAD catalog carries forbidden keys: {', '.join(sorted(found))}")
	return payload


def forbidden_keys(value):
	"""Every price or cost key at any depth (D6), including keys inside run style selections."""
	found = set()
	if isinstance(value, dict):
		for key, child in value.items():
			if (
				str(key).lower() in CAD_FORBIDDEN_KEYS
				or "price" in str(key).lower()
				or "cost" in str(key).lower()
			):
				found.add(key)
			found |= forbidden_keys(child)
	elif isinstance(value, list):
		for child in value:
			found |= forbidden_keys(child)
	return found


def template_index(payload):
	"""``{(family, code)}`` of every template a catalog offers, for the import's staleness check."""
	index = {(row["family"], row["code"]) for row in payload.get("templates") or []}
	index |= {("Linear Fixture", row["code"]) for row in payload.get("fixture_templates") or []}
	index |= {("Extrusion Kit", row["code"]) for row in payload.get("kit_templates") or []}
	return index


# --- Database ----------------------------------------------------------------------------------


def _present(doctype, fields):
	"""Fields that exist on the site (the live-only field guard: new fields arrive by migration)."""
	return [field for field in fields if frappe.db.has_column(doctype, field)]


def _children(doctype, parenttype, parents, fields):
	rows = {}
	if not parents:
		return rows
	for row in frappe.get_all(
		doctype,
		filters={"parenttype": parenttype, "parent": ["in", parents]},
		fields=["parent", *fields],
		order_by="idx asc",
		ignore_permissions=True,
	):
		rows.setdefault(row["parent"], []).append(row)
	return rows


def load_styles(user=None):
	"""The user's usable presets as run styles; unusable presets are left out."""
	from illumenate_lighting.illumenate_lighting.portal import presets, site_flags
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	if not site_flags.presets_enabled() or not frappe.db.exists("DocType", PRESET):
		return []
	actor = get_actor(user)
	fields = [
		"name",
		"label",
		"user",
		"customer",
		"shared_with_company",
		"family",
		"template",
		"request_json",
	]
	rows = {row.name: row for row in frappe.get_all(PRESET, filters={"user": actor.user}, fields=fields)}
	if actor.customer and not actor.is_internal:
		for row in frappe.get_all(
			PRESET, filters={"customer": actor.customer, "shared_with_company": 1}, fields=fields
		):
			rows.setdefault(row.name, row)
	styles = []
	for row in rows.values():
		try:
			stored = json.loads(row.request_json or "{}")
		except ValueError:
			continue
		if not isinstance(stored, dict):
			continue
		request, _problems = presets.revalidate(stored)
		if request is not None:
			styles.append(style_row(row, request))
	return styles


def load_data(staff, user=None):
	from illumenate_lighting.illumenate_lighting.portal_listing import template_filters
	from illumenate_lighting.illumenate_lighting.system_design import readiness
	from illumenate_lighting.illumenate_lighting.system_design.settings import settings

	tape_templates = frappe.get_all(
		TAPE_TEMPLATE,
		filters=template_filters(staff, is_active=1),
		fields=[
			"name",
			"template_code",
			"template_name",
			"product_category",
			"product_status",
			"is_free_cutting",
			"default_tape_spec",
			"leader_allowance_mm_per_fixture",
			"minimum_side_bend_diameter_mm",
		],
		order_by="template_code asc",
		ignore_permissions=True,
	)
	names = [row["name"] for row in tape_templates]
	allowed_specs = _children(
		"ilL-Child-Tape-Neon-Allowed-Spec",
		TAPE_TEMPLATE,
		names,
		["tape_spec", "environment_rating", "is_default"],
	)
	option_fields = sorted({field for field, _key, _label in TAPE_OPTIONS.values()})
	allowed_options = _children(
		"ilL-Child-Tape-Neon-Allowed-Option",
		TAPE_TEMPLATE,
		names,
		["option_type", "is_default", "is_active", *option_fields],
	)
	spec_names = {row["tape_spec"] for rows in allowed_specs.values() for row in rows if row.get("tape_spec")}
	spec_names |= {row["default_tape_spec"] for row in tape_templates if row.get("default_tape_spec")}
	tapes = []
	if spec_names:
		tapes = frappe.get_all(
			TAPE,
			filters={"name": ["in", sorted(spec_names)]},
			fields=[
				*readiness.TAPE_FIELDS,
				"tape_width_mm",
				*_present(TAPE, readiness.OPTIONAL_TAPE_FIELDS),
			],
			ignore_permissions=True,
		)
	offerings = {}
	if tapes:
		for row in frappe.get_all(
			OFFERING,
			filters={"is_active": 1, "tape_spec": ["in", [spec["name"] for spec in tapes]]},
			fields=[
				"name",
				"tape_spec",
				"cct",
				"output_level",
				"watts_per_ft_override",
				"cut_increment_mm_override",
			],
			order_by="name asc",
			ignore_permissions=True,
		):
			offerings.setdefault(row["tape_spec"], []).append(row)
	fixture_templates = frappe.get_all(
		FIXTURE_TEMPLATE,
		filters=template_filters(staff, is_active=1),
		fields=[
			"name",
			"template_name",
			"product_status",
			"default_profile_spec",
			"default_profile_stock_len_mm",
			"assembled_max_len_mm",
			"minimum_side_bend_diameter_mm",
		],
		ignore_permissions=True,
	)
	kit_templates = frappe.get_all(
		KIT_TEMPLATE,
		filters=template_filters(staff, is_active=1),
		fields=["name", "template_name", "product_status", "default_profile_spec", "profile_stock_length_mm"],
		ignore_permissions=True,
	)
	profiles = frappe.get_all(
		PROFILE,
		filters={"is_active": 1},
		fields=[
			"name",
			"item",
			"family",
			"width_mm",
			"height_mm",
			"stock_length_mm",
			"max_assembled_length_mm",
			"cross_section_json",
			*_present(PROFILE, ("is_curve_capable",)),
		],
		ignore_permissions=True,
	)
	snapshot_hash = catalog.current_snapshot_hash()
	return {
		"snapshot_hash": snapshot_hash,
		"snapshot": catalog.get_snapshot(snapshot_hash),
		"generated_at": str(frappe.utils.now_datetime()),
		"settings": settings(),
		"voltages": readiness.voltages(),
		"tape_templates": tape_templates,
		"allowed_specs": allowed_specs,
		"allowed_options": allowed_options,
		"tapes": tapes,
		"offerings": offerings,
		"fixture_templates": fixture_templates,
		"kit_templates": kit_templates,
		"profiles": profiles,
		"styles": load_styles(user),
	}


def cad_catalog(user=None):
	"""The ``cad-catalog/1`` document for ``user`` (templates they are offered, their run styles)."""
	from illumenate_lighting.illumenate_lighting.portal_listing import sees_internal

	user = user or frappe.session.user
	return build_payload(load_data(sees_internal(user), user))


def filename(payload):
	return f"illumenate_catalog_{payload['hash'][:8]}.json"
