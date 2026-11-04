"""Recently used products for the schedule's Add Line picker (plan 3.7).

Lists the product templates most recently put on schedules the user can read, newest schedule
first and, within a schedule, the last lines first. Only templates that the Add Line pickers offer
right now (``portal_listing.template_filters`` and the family rollout) are returned, each with its
D1 main image from ``product_projection.resolve_product_images``. Read-only: choosing a card only
pre-selects the same picker the dealer would use by hand.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal import site_flags

SCHEDULE = "ilL-Project-Fixture-Schedule"
LINE = "ilL-Child-Fixture-Schedule-Line"
MAX_SCHEDULES = 20
MAX_LINES = 2000
DEFAULT_LIMIT = 8
MAX_LIMIT = 24
TAPE_NEON = "ilL-Tape-Neon-Template"
# (picker family, schedule line field, template doctype, rollout family)
FAMILIES = (
	("fixture", "fixture_template", "ilL-Fixture-Template", "Linear Fixture"),
	("tape_neon", "tape_neon_template", TAPE_NEON, None),
	("led_sheet", "led_sheet_template", "ilL-LED-Sheet-Template", "LED Sheet"),
	("kit", "kit_template", "ilL-Extrusion-Kit-Template", "Extrusion Kit"),
	("driver", "driver_template", "ilL-Driver-Template", "Driver"),
)
SCHEDULE_FIELDS = ["name", "owner", "ill_project", "customer", "inherits_project_privacy", "is_private"]


def _limit(value):
	try:
		limit = int(value)
	except (TypeError, ValueError):
		return DEFAULT_LIMIT
	return max(1, min(limit, MAX_LIMIT))


def _schedules(schedule_name):
	"""Names of the schedules to look at: ``schedule_name`` first, then the newest readable ones."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule

	rows = frappe.get_list(
		SCHEDULE, fields=SCHEDULE_FIELDS, order_by="modified desc", limit_page_length=MAX_SCHEDULES
	)
	names = [row.name for row in rows if can_read_schedule(row)]
	if schedule_name:
		names = [schedule_name, *[name for name in names if name != schedule_name]]
	return names


def _candidates(schedules):
	"""``[(family, template)]`` in recency order, without repeats."""
	if not schedules:
		return []
	rank = {name: index for index, name in enumerate(schedules)}
	lines = frappe.get_all(
		LINE,
		filters={"parenttype": SCHEDULE, "parent": ["in", schedules], "manufacturer_type": "ILLUMENATE"},
		fields=["parent", "idx", *[field for _family, field, _doctype, _rollout in FAMILIES]],
		limit_page_length=MAX_LINES,
		ignore_permissions=True,
	)
	lines.sort(key=lambda line: (rank.get(line.parent, len(rank)), -(line.idx or 0)))
	seen = []
	for line in lines:
		for family, field, _doctype, _rollout in FAMILIES:
			template = line.get(field)
			if template and (family, template) not in seen:
				seen.append((family, template))
	return seen


def _offered(doctype, names):
	"""Rows of the ``names`` templates the Add Line picker offers the user, with their main image."""
	from illumenate_lighting.illumenate_lighting.portal_listing import template_filters
	from illumenate_lighting.templates.pages.configure import attach_images

	fields = ["name", "template_code", "template_name"]
	if doctype == TAPE_NEON:
		fields.append("product_category")
	rows = frappe.get_all(
		doctype,
		filters=template_filters(name=["in", sorted(set(names))]),
		fields=fields,
		ignore_permissions=True,
	)
	attach_images(doctype, rows)
	return {row.name: row for row in rows}


@frappe.whitelist()
def recent_products(schedule_name=None, limit=None):
	"""Up to ``limit`` product templates the user recently used, for the Add Line picker.

	Returns ``{"success": True, "products": [{family, doctype, name, template_code, template_name,
	category, image, image_alt}]}``; ``family`` is the Add Line picker that offers the template.
	"""
	if not site_flags.recent_products_enabled():
		frappe.throw(_("Recently used products are not available"), frappe.PermissionError)
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to see recently used products"), frappe.PermissionError)
	from illumenate_lighting.illumenate_lighting.portal import rollout
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import require_configurator

	schedule_name = str(schedule_name or "").strip() or None
	require_configurator(schedule_name)
	limit = _limit(limit)
	candidates = _candidates(_schedules(schedule_name))
	info = {family: (doctype, rollout_family) for family, _field, doctype, rollout_family in FAMILIES}
	offered = {}
	for family, (doctype, _rollout) in info.items():
		names = [template for kind, template in candidates if kind == family]
		offered[family] = _offered(doctype, names) if names else {}

	products = []
	for family, template in candidates:
		row = offered[family].get(template)
		if not row:
			continue
		doctype, rollout_family = info[family]
		category = row.get("product_category") or ""
		if not rollout.available(rollout_family or category or "LED Tape"):
			continue
		products.append({
			"family": family,
			"doctype": doctype,
			"name": row.name,
			"template_code": row.get("template_code") or row.name,
			"template_name": row.get("template_name") or row.name,
			"category": category,
			"image": row.get("image") or "",
			"image_alt": row.get("image_alt") or "",
		})
		if len(products) >= limit:
			break
	return {"success": True, "products": products}
