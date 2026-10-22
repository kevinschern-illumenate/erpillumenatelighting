"""Which templates and Webflow Products the dealer portal shows, and to whom.

A template is offered to dealers when its Product Status is Active. Internal Only
templates are offered to ilLumenate staff (any enabled System User) in the portal and
in Desk, and hidden from dealers, collaborators and guests. Draft, Discontinued and
Archived are offered to nobody.

A Webflow Product linked to a template follows that template's status, whether or not
it is live on the website. A listing without a template (accessories and the other
standalone listings) follows its own Active flag.

To see which products the switch shows or hides, from the System Console:

    print(frappe.call("illumenate_lighting.illumenate_lighting.portal_listing.visibility_changes"))
"""

import functools
import inspect

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_migration import LINK_FIELDS, PRODUCT, template_link
from illumenate_lighting.illumenate_lighting.web_listing_schema import ACTIVE_STATUSES

PORTAL_STATUS = "Active"


def sees_internal(user=None):
	"""Whether ``user`` is ilLumenate staff, who are also offered Internal Only products.

	Staff are Administrator and every enabled System User. Dealers and the other portal
	accounts are Website Users; guests are never staff. Cached per web request.
	"""
	user = user or getattr(getattr(frappe, "session", None), "user", None) or "Guest"
	if user == "Administrator":
		return True
	if user == "Guest":
		return False
	request = getattr(frappe.local, "request", None)
	cache = getattr(frappe.local, "ill_sees_internal", None) if request is not None else None
	if cache is not None and user in cache:
		return cache[user]
	values = frappe.db.get_value("User", user, ["user_type", "enabled"], as_dict=True) or {}
	staff = bool(values.get("enabled")) and values.get("user_type") == "System User"
	if request is not None:
		if cache is None:
			cache = frappe.local.ill_sees_internal = {}
		cache[user] = staff
	return staff


def visible_statuses(staff=None):
	"""The template statuses offered to staff (``staff=True``), dealers (False) or the session user."""
	staff = sees_internal() if staff is None else staff
	return ACTIVE_STATUSES if staff else (PORTAL_STATUS,)


def template_filters(staff=None, **filters):
	"""``frappe.get_all`` filters for the templates offered to the user, plus ``filters``."""
	return {**filters, "product_status": ["in", list(visible_statuses(staff))]}


def template_visible(doctype, name, staff=None):
	"""Whether the template ``doctype``/``name`` is offered to the user."""
	if not name:
		return False
	return frappe.db.get_value(doctype, name, "product_status") in visible_statuses(staff)


def require_template_visible(doctype, name, staff=None):
	"""Refuse a template the user is not offered, as if it did not exist."""
	if not template_visible(doctype, name, staff):
		frappe.throw(frappe._("{0} {1} not found").format(doctype, name), frappe.DoesNotExistError)


def template_scoped(doctype, argument=None, resolve=None):
	"""Refuse an endpoint call for a template the caller is not offered.

	Applied under ``@frappe.whitelist`` to configurator endpoints. The template is the
	call's ``argument``, or what ``resolve(arguments)`` returns from the bound call
	arguments. Only the method the web request was made to is checked, so server code
	calling the same function (a re-quote of a line staff added to a dealer's schedule)
	still works. A call without a known template is left to the endpoint.
	"""

	def decorate(function):
		dotted = function.__module__ + "." + function.__name__
		signature = inspect.signature(function)

		@functools.wraps(function)
		def wrapped(*args, **kwargs):
			from illumenate_lighting.illumenate_lighting.portal.configurator_access import _entry_method

			if _entry_method() == dotted:
				try:
					arguments = signature.bind_partial(*args, **kwargs).arguments
				except TypeError:
					arguments = dict(kwargs)
				name = resolve(arguments) if resolve else arguments.get(argument)
				if isinstance(name, str) and name and frappe.db.exists(doctype, name):
					require_template_visible(doctype, name)
			return function(*args, **kwargs)

		return wrapped

	return decorate


def json_argument(arguments, argument, key):
	"""``arguments[argument][key]`` where the argument is a dict or browser JSON."""
	import json

	value = arguments.get(argument)
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			return None
	return value.get(key) if isinstance(value, dict) else None


def product_template(field):
	"""A ``template_scoped`` resolver: the ``field`` template of the call's ``product_slug``."""

	def resolve(arguments):
		slug = arguments.get("product_slug")
		return frappe.db.get_value(PRODUCT, {"product_slug": slug}, field) if slug else None

	return resolve


def template_query_conditions(doctype, user=None):
	"""List condition for a template doctype: non-staff see only Active templates."""
	if sees_internal(user):
		return ""
	return f"`tab{doctype}`.product_status = '{PORTAL_STATUS}'"


def template_has_permission(doc, ptype="read", user=None):
	"""Document permission for a template doctype: non-staff may not open a non-Active one.

	True leaves the decision to the role permissions; it never grants more than they do.
	"""
	return bool(sees_internal(user) or doc.get("product_status") == PORTAL_STATUS)


# permission_query_conditions hooks, one per template doctype (hooks.py names them).
def fixture_template_conditions(user=None):
	return template_query_conditions("ilL-Fixture-Template", user)


def tape_neon_template_conditions(user=None):
	return template_query_conditions("ilL-Tape-Neon-Template", user)


def led_sheet_template_conditions(user=None):
	return template_query_conditions("ilL-LED-Sheet-Template", user)


def extrusion_kit_template_conditions(user=None):
	return template_query_conditions("ilL-Extrusion-Kit-Template", user)


def driver_template_conditions(user=None):
	return template_query_conditions("ilL-Driver-Template", user)


def controller_template_conditions(user=None):
	return template_query_conditions("ilL-Controller-Template", user)


def on_portal(product, status_of=None, staff=None):
	"""Whether a Webflow Product (doc or dict) is shown on the portal.

	``status_of(doctype, name)`` returns a template's Product Status; pass one that reads
	preloaded rows when checking many products. ``staff`` picks the audience (True for
	staff, False for dealers); left out, it is the session user's.
	"""
	doctype, name = template_link(product)
	if not doctype:
		return bool(int(product.get("is_active") or 0))
	status_of = status_of or (lambda doctype, name: frappe.db.get_value(doctype, name, "product_status"))
	return status_of(doctype, name) in visible_statuses(staff)


def portal_condition(table="`tabilL-Webflow-Product`", staff=None):
	"""SQL condition matching ``on_portal`` for rows of the Webflow Product table."""
	statuses = ", ".join(f"'{status}'" for status in visible_statuses(staff))
	linked = [
		f"(ifnull({table}.{field}, '') != '' and exists(select 1 from `tab{doctype}` portal_template"
		f" where portal_template.name = {table}.{field}"
		f" and portal_template.product_status in ({statuses})))"
		for field, doctype in LINK_FIELDS.items()
	]
	unlinked = " and ".join(f"ifnull({table}.{field}, '') = ''" for field in LINK_FIELDS)
	return "(" + " or ".join([*linked, f"({unlinked} and {table}.is_active = 1)"]) + ")"


def portal_product(filters, staff=None):
	"""The Webflow Product matching ``filters`` if the portal shows it to the user, else None."""
	name = frappe.db.get_value(PRODUCT, filters, "name")
	if not name:
		return None
	product = frappe.get_doc(PRODUCT, name)
	return product if on_portal(product, staff=staff) else None


@frappe.whitelist()
def visibility_changes():
	"""Products dealers see or don't now that template status decides, versus Active."""
	frappe.only_for("System Manager")
	changes = []
	for row in frappe.get_all(PRODUCT, fields=["name", "is_active", *LINK_FIELDS], order_by="name asc"):
		shown = on_portal(row, staff=False)
		if shown != bool(row.is_active):
			doctype, name = template_link(row)
			status = frappe.db.get_value(doctype, name, "product_status") if doctype else None
			changes.append(
				{
					"listing": row.name,
					"now": "shown" if shown else "hidden",
					"template": f"{doctype} {name}" if doctype else None,
					"product_status": status,
				}
			)
	return changes
