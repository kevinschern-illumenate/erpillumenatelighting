# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Which mounting methods ship without a separate mounting accessory.

Driven by the No Accessory Required check on ilL-Attribute-Mounting Method
(e.g. Drywall is mudded in, Direct Surface Mount screws through the profile).
"""

import frappe

DOCTYPE = "ilL-Attribute-Mounting Method"
NO_ACCESSORY_FIELD = "no_accessory_required"


def methods_without_accessory(methods=None) -> set:
	"""Mounting methods flagged as shipping without a separate mounting accessory.

	Pass ``methods`` to limit the lookup. Returns an empty set on a site whose
	schema predates the flag, so callers keep requiring an accessory there.
	"""
	if not frappe.get_meta(DOCTYPE).has_field(NO_ACCESSORY_FIELD):
		return set()
	filters = {NO_ACCESSORY_FIELD: 1}
	if methods is not None:
		methods = [m for m in methods if m]
		if not methods:
			return set()
		filters["name"] = ("in", methods)
	return set(frappe.get_all(DOCTYPE, filters=filters, pluck="name"))


def needs_accessory(method: str) -> bool:
	"""False when ``method`` is flagged No Accessory Required."""
	return not method or method not in methods_without_accessory([method])
