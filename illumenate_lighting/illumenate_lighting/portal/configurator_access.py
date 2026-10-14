# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Who may run the portal configurator, and what it may show them.

Dealers and ilLumenate staff (``access.can_view_catalog``) configure anything
and see pricing. Anyone else may configure only for a schedule they can edit
(an EDIT collaborator such as the lighting designer), and never sees prices:
the configurator endpoints strip price, MSRP and cost fields from what they
return to such a user, so hiding the price UI is only cosmetic.

The schedule reaches an endpoint in one of three ways, most specific first:
an explicit argument, ``frappe.flags.ill_config_schedule`` (set by a server
path that already authorised the schedule, such as a save), or the
``config_schedule`` request parameter that the configurator page adds to
every call it makes.
"""

import functools

import frappe

SCHEDULE = "ilL-Project-Fixture-Schedule"
SCHEDULE_PARAM = "config_schedule"
FLAG = "ill_config_schedule"

# Key fragments and exact keys that carry prices in configurator responses.
_PRICE_FRAGMENTS = ("price", "pricing", "msrp", "cost")
_PRICE_KEYS = frozenset(
	{
		"adder_breakdown",
		"adder_breakdown_json",
		"amount",
		"default_adder",
		"line_total",
		"option_adders",
		"rate",
	}
)
_PRICE_PREFIXES = ("tier_", "discount_")
_PRICE_SUFFIXES = ("_adder", "_adders")


def pricing_allowed(user=None) -> bool:
	"""Configurator pricing is for the users who may see the catalog and its MSRP."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog

	return bool(can_view_catalog(user) if user else can_view_catalog())


def requested_schedule(schedule=None):
	"""The schedule a configurator call is made for, if any."""
	if schedule:
		return schedule
	flagged = frappe.flags.get(FLAG)
	if flagged:
		return flagged
	form = getattr(frappe, "form_dict", None) or {}
	return form.get(SCHEDULE_PARAM)


def schedule_grant(schedule=None, user=None) -> bool:
	"""True when ``user`` may edit the schedule this configurator call is made for."""
	name = requested_schedule(schedule)
	if not name or not isinstance(name, str):
		return False
	if not frappe.db.exists(SCHEDULE, name):
		return False
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule

	return bool(can_edit_schedule(frappe.get_doc(SCHEDULE, name), user))


def can_configure(schedule=None, user=None) -> bool:
	return pricing_allowed(user) or schedule_grant(schedule, user)


def require_configurator(schedule=None, user=None) -> None:
	"""Catalog access, or else edit rights on the schedule being configured for."""
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

	try:
		if user:
			require_catalog_access(user)
		else:
			require_catalog_access()
	except frappe.PermissionError:
		if not schedule_grant(schedule, user):
			raise


def is_price_key(key) -> bool:
	name = str(key).lower()
	return (
		name in _PRICE_KEYS
		or any(fragment in name for fragment in _PRICE_FRAGMENTS)
		or name.startswith(_PRICE_PREFIXES)
		or name.endswith(_PRICE_SUFFIXES)
	)


def strip_prices(value):
	"""A copy of ``value`` with every price, MSRP and cost field removed, at any depth."""
	if isinstance(value, dict):
		cleaned = {key: strip_prices(item) for key, item in value.items() if not is_price_key(key)}
		try:
			return type(value)(cleaned)
		except TypeError:
			return cleaned
	if isinstance(value, list):
		return [strip_prices(item) for item in value]
	if isinstance(value, tuple):
		return tuple(strip_prices(item) for item in value)
	return value


def _entry_method():
	"""The whitelisted method this web request was made to, if any."""
	form = getattr(frappe, "form_dict", None) or {}
	cmd = form.get("cmd")
	if cmd:
		return str(cmd)
	request = getattr(getattr(frappe, "local", None), "request", None)
	path = str(getattr(request, "path", "") or "")
	marker = "/method/"
	return path.split(marker, 1)[1].strip("/") if marker in path else None


def price_scoped(function):
	"""Strip prices from an endpoint's response for a signed-in user without pricing rights.

	Applied under ``@frappe.whitelist``. Only the response of the method the
	request was made to is stripped; server code that calls the same function
	internally (a save that reads the engine's pricing) gets the full result.
	Guests are left as they were: the public product pages call some of these.
	"""
	dotted = function.__module__ + "." + function.__name__

	@functools.wraps(function)
	def wrapped(*args, **kwargs):
		result = function(*args, **kwargs)
		session = getattr(frappe, "session", None)
		user = getattr(session, "user", None) or "Guest"
		if user == "Guest" or _entry_method() != dotted or pricing_allowed():
			return result
		return strip_prices(result)

	return wrapped
