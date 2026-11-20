# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Who may use the draw-to-quote CAD toolkit (CAD toolkit plan 2.9).

Rollout: ilLumenate staff first (applications engineering, engineering, sales), then pilot dealers,
then every dealer. All of it sits behind the ``ill_cad_import`` site flag, default off:

- staff with the ``engineering``, ``design_review`` or ``sales`` capability;
- users of a customer in ``ill_cad_pilot_customers`` (site config) or in the System Designer's
  pilot customers, since a CAD job continues in the designer;
- every catalog user once ``ill_cad_all_dealers`` is set.

Schedule rights are checked separately (the import needs edit rights on the schedule).
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

STAFF_CAPABILITIES = ("engineering", "design_review", "sales")


def is_cad_staff(user=None):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return any(allowed(name, user) for name in STAFF_CAPABILITIES)


def pilot_customers():
	from illumenate_lighting.illumenate_lighting.portal import site_flags
	from illumenate_lighting.illumenate_lighting.system_design.settings import pilot_customers as designer

	return sorted({*site_flags.cad_pilot_customers(), *designer()})


def enabled_for(user=None):
	"""Whether ``user`` may download the CAD catalog and import drawings at all."""
	from illumenate_lighting.illumenate_lighting.portal import site_flags
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog, get_actor

	user = user or frappe.session.user
	if user == "Guest" or not site_flags.cad_import_enabled():
		return False
	if is_cad_staff(user):
		return True
	if not can_view_catalog(user):
		return False
	if site_flags.cad_all_dealers_enabled():
		return True
	actor = get_actor(user)
	return bool(actor.customer and actor.customer in pilot_customers())


def require_cad(user=None):
	if (user or frappe.session.user) == "Guest":
		raise DesignError("FORBIDDEN", _("Please log in to continue"))
	if not enabled_for(user):
		raise DesignError("FORBIDDEN", _("The CAD toolkit is not available for your account yet"))
