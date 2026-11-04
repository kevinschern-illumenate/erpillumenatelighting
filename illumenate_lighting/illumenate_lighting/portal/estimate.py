"""Configurator estimate panel (plan 3.8).

Every configurator result shows its part number, price (only where the user may see pricing),
stock and lead-time class, all labelled as an estimate that the quote confirms. Price and stock come
from the configurators' own validation responses; this module adds what they lack:

* ``lead_time`` resolves the ``ilL-Attribute-Lead Time Class`` for a configured product: the tape
  offering's ``lead_time_class_override`` (tape, neon and linear fixtures) or the template's
  ``lead_time_class`` (LED Sheet, Driver, Controller).
* ``attach_tape_neon_estimate`` prices a validated tape/neon result with the same
  ``tape_neon_pricing.price_result`` the save path uses, on a copy, so validation output is unchanged.

Read-only. Nothing here writes a document, and issued quotes are never re-priced.
"""

import copy

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal import site_flags

LEAD_TIME = "ilL-Attribute-Lead Time Class"
TAPE_OFFERING = "ilL-Rel-Tape Offering"
# Families whose template carries its own lead-time class.
TEMPLATES = {
	"led_sheet": "ilL-LED-Sheet-Template",
	"driver": "ilL-Driver-Template",
	"controller": "ilL-Controller-Template",
}
# Families whose lead time comes from the resolved tape offering.
OFFERING_FAMILIES = ("fixture", "tape_neon")
FAMILIES = (*TEMPLATES, *OFFERING_FAMILIES, "kit")


def _clean(value):
	value = str(value or "").strip()
	return value or None


def _days(value):
	try:
		days = int(value)
	except (TypeError, ValueError):
		return None
	return days if days >= 0 else None


def lead_time_class(name):
	"""``{code, label, days_min, days_max}`` of the lead-time class ``name``, or None."""
	if not name:
		return None
	row = frappe.db.get_value(LEAD_TIME, name, ["name", "code", "label", "days_min", "days_max"], as_dict=True)
	if not row:
		return None
	days_min, days_max = _days(row.get("days_min")), _days(row.get("days_max"))
	if days_min is not None and days_max is not None and days_max < days_min:
		days_min, days_max = days_max, days_min
	return {
		"code": row.get("code") or row.get("name"),
		"label": row.get("label") or row.get("code") or row.get("name"),
		"days_min": days_min,
		"days_max": days_max,
	}


def offering_lead_time(offering):
	"""The lead-time class of an active tape offering, or None."""
	if not offering:
		return None
	row = frappe.db.get_value(TAPE_OFFERING, offering, ["is_active", "lead_time_class_override"], as_dict=True)
	if not row or not row.get("is_active"):
		return None
	return lead_time_class(row.get("lead_time_class_override"))


@frappe.whitelist(methods=["GET"])
def lead_time(family=None, template=None, tape_offering=None, schedule_name=None):
	"""The estimated lead-time class for a configured product.

	``family`` is one of fixture, tape_neon, led_sheet, kit, driver, controller. Template families
	need ``template`` (refused as not found unless the user is offered it); tape families need the
	resolved ``tape_offering``. Returns ``{"success": True, "lead_time": {code, label, days_min,
	days_max} | None}``; None means no class is recorded and the quote states the lead time.
	"""
	if not site_flags.live_estimate_enabled():
		frappe.throw(_("Configurator estimates are not available"), frappe.PermissionError)
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to see lead times"), frappe.PermissionError)
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import require_configurator

	require_configurator(_clean(schedule_name))
	family = _clean(family)
	if family not in FAMILIES:
		frappe.throw(_("Unknown product family"))
	template, tape_offering = _clean(template), _clean(tape_offering)
	result = None
	if family in TEMPLATES and template:
		from illumenate_lighting.illumenate_lighting.portal_listing import require_template_visible

		doctype = TEMPLATES[family]
		require_template_visible(doctype, template)
		result = lead_time_class(frappe.db.get_value(doctype, template, "lead_time_class"))
	elif family in OFFERING_FAMILIES:
		result = offering_lead_time(tape_offering)
	return {"success": True, "lead_time": result}


def requested(value):
	"""Whether an optional ``include_estimate`` form value asks for an estimate."""
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool

	try:
		return parse_bool(value, default=False)
	except ValueError:
		return False


def attach_tape_neon_estimate(result, template=None, include=True):
	"""Add ``estimate`` to a valid tape/neon validation ``result`` when ``include`` asks for it.

	``estimate.total_price_msrp`` is the price the save path would record (None when a component has
	no current selling price); ``price_scoped`` strips it for users without pricing. ``estimate.lead_time``
	is the tape offering's lead-time class. A pricing failure never invalidates the configuration.
	"""
	if not requested(include) or not result or not result.get("is_valid"):
		return result
	if not site_flags.live_estimate_enabled():
		return result
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import price_result

	total = None
	try:
		priced = price_result(copy.deepcopy(result), template)
		total = (priced.get("computed") or {}).get("total_price_msrp")
	except (ValueError, KeyError, TypeError, frappe.ValidationError):
		total = None
	offering = (result.get("resolved_items") or {}).get("tape_offering")
	result["estimate"] = {"total_price_msrp": total, "lead_time": offering_lead_time(offering)}
	return result
