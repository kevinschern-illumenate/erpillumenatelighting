"""Helpers exposed to website templates through the ``jinja`` hook."""


def ill_can_view_catalog() -> bool:
	"""Whether the current user may open the product catalog (Dealers and internal users).

	Named with a prefix because page contexts already use ``can_view_catalog`` as a value.
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog

	return can_view_catalog()


def ill_finder_enabled() -> bool:
	import frappe

	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS

	return ill_can_view_catalog() and bool(frappe.db.get_single_value(SETTINGS, "portal_enabled"))
