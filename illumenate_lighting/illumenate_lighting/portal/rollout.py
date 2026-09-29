"""Optional family and named-user cohort controls for new configurations."""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES
from illumenate_lighting.illumenate_lighting.portal.site_flags import conf_list


def _list(key):
	# Absent (or unreadable, which is logged) preserves existing availability.
	return conf_list(key)


def available(family, *, public=False):
	families = _list("ill_portal_enabled_families")
	family = FAMILY_ALIASES.get(family, family)
	if families is not None and family not in families:
		return False
	users = _list("ill_portal_pilot_users")
	if users is None or public or frappe.flags.get("ill_product_download"):
		return True
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return frappe.session.user in users or allowed("sales") or allowed("engineering")


def require_family(family, *, public=False):
	if not available(family, public=public):
		frappe.throw(
			"This product family is available by inquiry for your account. Contact Sales for assistance.",
			frappe.PermissionError,
		)


def require_configuration(family):
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

	if not frappe.flags.get("ill_product_download"):
		require_catalog_access()
	require_family(family)
