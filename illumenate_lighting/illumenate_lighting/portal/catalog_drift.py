"""Stale configuration badge (plan 3.9).

A schedule line keeps the configuration it was saved with. When the catalog moves on, the line
is flagged "Catalog updated — review" so the dealer can reopen it in the configurator, which
validates against the current catalog. Nothing here changes a line, build or document.

A line is flagged when:

* its template is gone, inactive or no longer offered to the user, or a linear option or tape
  offering it uses is no longer offered (the same checks a preset gets, ``portal.presets``);
* a power supply its power plan chose changed: the plan records each supply's electrical
  specification (``dependency_revisions``), compared here with the current ``ilL-Spec-Driver``.
"""

import copy
import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal import site_flags

MAX_LINES = 500
DRIVER_SPEC = "ilL-Spec-Driver"
# The electrical fields driver_catalog records for each chosen supply.
REVISION_FIELDS = (
	"voltage_output",
	"output_type",
	"output_protocol",
	"max_wattage",
	"max_wattage_per_output",
	"usable_load_factor",
	"independent_outputs_count",
)
# Line link -> (configured doctype, field holding the power plan)
PLAN_SOURCES = {
	"configured_fixture": ("ilL-Configured-Fixture", "power_plan_json"),
	"configured_tape_neon": ("ilL-Configured-Tape-Neon", "power_plan_json"),
	"configured_led_sheet": ("ilL-Configured-LED-Sheet", "build_snapshot_json"),
}


def _object(value):
	if isinstance(value, dict):
		return value
	try:
		parsed = json.loads(value or "{}")
	except (TypeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}


def stored_revisions(value):
	"""``{driver item: revision}`` from a stored power plan or a build snapshot holding one."""
	data = _object(value)
	plan = data if "dependency_revisions" in data else data.get("power_plan") or data.get("driver_plan")
	revisions = plan.get("dependency_revisions") if isinstance(plan, dict) else None
	if not isinstance(revisions, dict):
		return {}
	return {item: revision for item, revision in revisions.items() if isinstance(revision, dict)}


def _plans(lines):
	plans = {}
	for link, (doctype, field) in PLAN_SOURCES.items():
		names = sorted({line.get(link) for line in lines if line.get(link)})
		if not names:
			continue
		for row in frappe.get_all(
			doctype, filters={"name": ["in", names]}, fields=["name", field], limit_page_length=0
		):
			plans[(link, row.get("name"))] = stored_revisions(row.get(field))
	return plans


def _driver_specs(plans):
	names = sorted(
		{revision.get("name") for plan in plans for revision in plan.values() if revision.get("name")}
	)
	if not names:
		return {}
	rows = frappe.get_all(
		DRIVER_SPEC,
		filters={"name": ["in", names]},
		fields=["name", *REVISION_FIELDS],
		limit_page_length=0,
	)
	return {row.get("name"): row for row in rows}


def _same(stored, current):
	if stored in (None, "") and current in (None, ""):
		return True
	try:
		return float(stored) == float(current)
	except (TypeError, ValueError):
		return str(stored if stored is not None else "") == str(current if current is not None else "")


def driver_problems(revisions, specs):
	"""Why the supplies recorded in ``revisions`` no longer match ``specs`` (current rows by name)."""
	problems = []
	for item in sorted(revisions):
		stored = revisions[item]
		spec = specs.get(stored.get("name"))
		if spec is None:
			problems.append(_("Power supply {0} is no longer in the catalog").format(item))
		elif any(key in stored and not _same(stored[key], spec.get(key)) for key in REVISION_FIELDS):
			problems.append(_("Power supply {0} specification changed").format(item))
	return problems


def catalog_problems(line, templates):
	"""What the catalog no longer offers for ``line``. ``templates`` memoizes template checks."""
	from illumenate_lighting.illumenate_lighting.portal import presets
	from illumenate_lighting.illumenate_lighting.portal.configuration_reopen import for_line
	from illumenate_lighting.illumenate_lighting.portal_listing import template_visible

	try:
		request = for_line(line)
	except (frappe.DoesNotExistError, ValueError, KeyError, TypeError):
		return [_("The saved configuration can no longer be read")]
	if not isinstance(request, dict):
		return []
	family, template = request.get("family"), request.get("template")
	if family not in presets.FAMILY_DOCTYPES:
		return [_("This product family is no longer offered")] if family else []
	if not template:
		return []
	key = (family, template)
	if key not in templates:
		doctype = presets.FAMILY_DOCTYPES[family]
		name = presets._template_name(family, template)
		offered = name and frappe.db.get_value(doctype, name, "is_active") and template_visible(doctype, name)
		templates[key] = None if offered else _("{0} is no longer offered").format(template)
	if templates[key]:
		return [templates[key]]
	if family == "Linear Fixture" and not (request.get("selections") or {}).get("group_request"):
		return presets._linear_problems(copy.deepcopy(request))
	return []


def line_problems(lines):
	"""``{line_key: [problem, ...]}`` for the lines the catalog has moved past."""
	lines = list(lines)[:MAX_LINES]
	plans = _plans(lines)
	specs = _driver_specs(plans.values())
	templates, result = {}, {}
	for line in lines:
		problems = catalog_problems(line, templates)
		for link in PLAN_SOURCES:
			if line.get(link):
				problems += driver_problems(plans.get((link, line.get(link))) or {}, specs)
		if problems:
			result[line.get("line_key") or line.get("name")] = list(dict.fromkeys(problems))
	return result


@frappe.whitelist(methods=["GET"])
def check(schedule_name):
	"""The schedule's lines that need a review against the current catalog. Read-only."""
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	if not site_flags.stale_badge_enabled():
		return {"enabled": False, "lines": {}}
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to view this schedule"), frappe.PermissionError)
	schedule = schedule_context(schedule_name)
	return {"enabled": True, "lines": line_problems(schedule.get("lines") or [])}
