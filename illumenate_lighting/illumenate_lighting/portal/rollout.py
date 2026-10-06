"""Optional family and named-user cohort controls for new configurations."""

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	COB_TAPE,
	FAMILY_ALIASES,
	LED_TAPE,
)
from illumenate_lighting.illumenate_lighting.portal.site_flags import conf_list


def _list(key):
	# Absent (or unreadable, which is logged) preserves existing availability.
	return conf_list(key)


def available(family, *, public=False):
	return reason(family, public=public) == "ok"


def reason(family, *, public=False):
	"""Return the stable projection reason for a family's rollout state."""
	families = _list("ill_portal_enabled_families")
	family = FAMILY_ALIASES.get(family, family)
	# COB Tape is offered wherever LED Tape is, unless the site lists it on its own.
	enabled = families is None or family in families or (family == COB_TAPE and LED_TAPE in families)
	if not enabled:
		return "family_not_enabled"
	users = _list("ill_portal_pilot_users")
	if users is None or public or frappe.flags.get("ill_product_download"):
		return "ok"
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if frappe.session.user in users or allowed("sales") or allowed("engineering"):
		return "ok"
	return "pilot_only"


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
