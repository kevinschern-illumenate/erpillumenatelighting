# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Supplies eligible for a set of runs (plan §10.1, H6 ``eligible_supplies``, WP-3.4).

A supply qualifies when it is a complete constant-voltage catalog supply at the runs' voltage, is
allowed for every configured product's template (``ilL-Rel-Driver-Eligibility``), accepts the
supply-dimmed protocol each product needs, and is rated for the cabinet's location. Results carry the
catalog ``rank`` only (D6): no cost, no price, and no order that a client could turn into one.
"""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design import access, catalog, expansion
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

DRIVER = "ilL-Spec-Driver"
MAX_RUN_KEYS = 1000
LOCATION_ORDER = {"Dry": 0, "Damp": 1, "Wet": 2}
SUPPLY_DIMMED = {"phase-forward", "phase-reverse", "0-10V", "DALI-2"}
# Configured doctype → (template doctype, template field). A group names its own template.
TEMPLATE_FIELDS = {
	expansion.FIXTURE: ("ilL-Fixture-Template", "fixture_template"),
	expansion.TAPE_NEON: ("ilL-Tape-Neon-Template", "tape_neon_template"),
	expansion.SHEET: ("ilL-LED-Sheet-Template", "sheet_template"),
}


def parse_run_keys(run_keys):
	if isinstance(run_keys, str):
		try:
			run_keys = json.loads(run_keys)
		except ValueError:
			run_keys = None
	if (
		not isinstance(run_keys, list)
		or not run_keys
		or len(run_keys) > MAX_RUN_KEYS
		or not all(isinstance(key, str) and key.count(":") == 2 for key in run_keys)
	):
		raise DesignError("INVALID", _("Choose the runs to find supplies for"))
	return sorted(set(run_keys))


def location_rank(rating):
	return LOCATION_ORDER.get(rating or "Dry", 0)


def requirements(run_keys, lines, builds, items):
	"""One requirement per schedule line the runs come from: voltage, template and protocols."""
	by_key = {line["key"]: line for line in lines}
	found = {}
	for run_key in run_keys:
		line_key = run_key.split(":", 1)[0]
		line = by_key.get(line_key)
		if not line or line_key in found:
			if not line:
				raise DesignError("INVALID", _("Run {0} is not on this schedule").format(run_key))
			continue
		if line["kind"] == "third-party":
			data = line.get("thirdParty") or {}
			if data.get("voltageClass") == "Line Voltage":
				raise DesignError(
					"INVALID",
					_("Line {0} is line voltage; feed it from a panel circuit, not a supply").format(
						line.get("lineId") or line_key
					),
				)
			dimming = data.get("dimming")
			found[line_key] = {
				"voltage": data.get("inputVoltageV"),
				"template": None,
				"protocols": [dimming] if dimming in SUPPLY_DIMMED else [],
			}
			continue
		ref = line.get("configured")
		build = (builds.get(ref["doctype"]) or {}).get(ref["name"]) if ref else None
		if not build:
			raise DesignError(
				"INVALID", _("Line {0} has no configured build").format(line.get("lineId") or line_key)
			)
		tape = (items.get(build.get("catalogId")) or {}).get("specs") or {}
		found[line_key] = {
			"voltage": tape.get("voltage") if tape.get("kind") == "tape" else None,
			"template": build.get("template"),
			"protocols": [p for p in build.get("protocols") or [] if p in SUPPLY_DIMMED],
		}
	return list(found.values())


def eligible(reqs, items, allowed_by_template, location_by_spec, location_rating=None):
	"""Catalog supplies meeting every requirement, as ``{catalog_id, item_code, rank, location_rating}``.

	``allowed_by_template`` maps a ``(template doctype, template)`` pair to the driver specs allowed for
	it; a requirement without a template (third-party low voltage) takes any supply that fits.
	"""
	result = []
	for item in items.values():
		specs = item.get("specs") or {}
		if specs.get("kind") != "psu" or specs.get("outputType") != "CV" or item.get("isExample"):
			continue
		spec_name = (item.get("sourceData") or {}).get("name")
		rating = location_by_spec.get(spec_name) or "Dry"
		if location_rating and location_rank(rating) < location_rank(location_rating):
			continue
		ok = True
		for req in reqs:
			if req["voltage"] is not None and specs.get("outputV") != req["voltage"]:
				ok = False
			elif req["template"] is not None and spec_name not in allowed_by_template.get(
				req["template"], set()
			):
				ok = False
			elif req["protocols"] and not set(req["protocols"]) & set(specs.get("dimming") or []):
				ok = False
			if not ok:
				break
		if ok:
			result.append(
				{
					"catalog_id": item["id"],
					"item_code": item.get("erpItemCode"),
					"rank": item.get("rank"),
					"location_rating": rating,
				}
			)
	return sorted(result, key=lambda row: (row["rank"] is None, row["rank"] or 0, row["catalog_id"]))


def _templates(builds):
	"""Attach ``template`` to each build from its configured record, in one query per doctype."""
	for doctype, by_name in builds.items():
		names = list(by_name)
		if doctype == expansion.GROUP:
			rows = frappe.get_all(
				doctype, filters={"name": ["in", names]}, fields=["name", "template_type", "template"]
			)
			for row in rows:
				if row.get("template_type") and row.get("template"):
					by_name[row["name"]]["template"] = (row["template_type"], row["template"])
			continue
		if doctype not in TEMPLATE_FIELDS:
			continue
		template_doctype, field = TEMPLATE_FIELDS[doctype]
		for row in frappe.get_all(doctype, filters={"name": ["in", names]}, fields=["name", field]):
			if row.get(field):
				by_name[row["name"]]["template"] = (template_doctype, row[field])


def _allowed(templates):
	allowed = {template: set() for template in templates}
	if not templates:
		return allowed
	for row in frappe.get_all(
		"ilL-Rel-Driver-Eligibility",
		filters={
			"is_allowed": 1,
			"is_active": 1,
			"fixture_template": ["in", sorted({name for _doctype, name in templates})],
		},
		fields=["template_type", "fixture_template", "driver_spec"],
	):
		key = (row["template_type"], row["fixture_template"])
		if key in allowed:
			allowed[key].add(row["driver_spec"])
	return allowed


def eligible_supplies(schedule, run_keys, location_rating=None):
	doc = access.require_read(schedule)
	from illumenate_lighting.illumenate_lighting.system_design.designs import require_designer

	require_designer()
	keys = parse_run_keys(run_keys)
	if location_rating not in (None, "", *LOCATION_ORDER):
		raise DesignError("INVALID", _("Choose Dry, Damp or Wet"))
	payload = catalog.get_snapshot(catalog.current_snapshot_hash()) or {"items": []}
	items = {item["id"]: item for item in payload["items"]}
	lines, builds, _readiness = expansion.expand_schedule(
		doc, {k: v["specs"]["kind"] for k, v in items.items()}
	)
	_templates(builds)
	reqs = requirements(keys, lines, builds, items)
	templates = {req["template"] for req in reqs if req["template"]}
	specs = [
		(item.get("sourceData") or {}).get("name")
		for item in items.values()
		if (item.get("specs") or {}).get("kind") == "psu"
	]
	locations = (
		{
			row["name"]: row["location_rating"]
			for row in frappe.get_all(
				DRIVER, filters={"name": ["in", [s for s in specs if s]]}, fields=["name", "location_rating"]
			)
		}
		if specs
		else {}
	)
	return eligible(reqs, items, _allowed(templates), locations, location_rating or None)
