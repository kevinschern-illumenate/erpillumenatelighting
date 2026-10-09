# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Whitelisted System Designer endpoints (plan H6).

Every endpoint returns ``{"success": True, "data": ...}`` or
``{"success": False, "error": str, "code": str}``. Endpoints are thin: they check access through
:mod:`.access` and delegate to service modules. Wrap each in :func:`endpoint` so intentional failures
become contract errors and anything unexpected is logged and returned as a generic ``INTERNAL``.
"""

import functools
import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design.errors import CODES, DesignError


def respond(data=None):
	return {"success": True, "data": data}


def fail(code, message):
	if code not in CODES:
		raise ValueError(f"Unknown System Designer error code: {code}")
	return {"success": False, "error": str(message), "code": code}


def parse_json(value, name="payload"):
	"""Accept a dict/list or its JSON string (the ``api/portal.py`` body pattern)."""
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except (TypeError, ValueError):
		raise DesignError("INVALID", _("{0} must be valid JSON").format(name))


def endpoint(function):
	"""Turn a service function into a contract-shaped endpoint body."""

	@functools.wraps(function)
	def wrapper(*args, **kwargs):
		try:
			return respond(function(*args, **kwargs))
		except DesignError as e:
			return fail(e.code, e.message)
		except frappe.PermissionError:
			return fail("FORBIDDEN", _("You do not have access to this design"))
		except frappe.DoesNotExistError:
			return fail("NOT_FOUND", _("Not found"))
		except frappe.ValidationError as e:
			# frappe.throw() messages are written for users; show them as-is.
			return fail("INVALID", str(e))
		except Exception as e:
			try:
				frappe.log_error(
					title=f"System Designer: {function.__name__}"[:140],
					message=frappe.get_traceback() or str(e),
				)
			except Exception:
				pass
			return fail("INTERNAL", _("Something went wrong. Please try again or contact ilLumenate."))

	return wrapper


# --- Catalog (WP-2.1, H6) ------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
@endpoint
def get_catalog(hash=None):
	"""The catalog snapshot ``hash`` names (immutable, so clients cache it by hash)."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_view_catalog
	from illumenate_lighting.illumenate_lighting.system_design import catalog

	if frappe.session.user == "Guest" or not can_view_catalog():
		raise DesignError("FORBIDDEN", _("The catalog is available to dealers and ilLumenate staff"))
	return catalog.catalog_response(hash or catalog.current_snapshot_hash())


@frappe.whitelist(methods=["GET"])
@endpoint
def get_catalog_for_desktop():
	"""The current snapshot for the riser desktop app (D1): an engineering user's API token."""
	from illumenate_lighting.illumenate_lighting.system_design import catalog
	from illumenate_lighting.illumenate_lighting.system_design.access import require_capability

	require_capability("engineering")
	return catalog.catalog_response(catalog.current_snapshot_hash())


# --- Opening a schedule (WP-2.3, H6) -------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
@endpoint
def open_design(schedule=None, design=None):
	from illumenate_lighting.illumenate_lighting.system_design import designs

	return designs.open_design(schedule, design)


@frappe.whitelist(methods=["GET"])
@endpoint
def find_schedules(query=None, limit=20):
	from illumenate_lighting.illumenate_lighting.system_design import designs

	return designs.find_schedules(query, limit)


@frappe.whitelist(methods=["GET"])
@endpoint
def review_requirement(schedule=None):
	from illumenate_lighting.illumenate_lighting.system_design import access, catalog, expansion, gate
	from illumenate_lighting.illumenate_lighting.system_design.settings import settings

	doc = access.require_read(schedule)
	values = settings()
	if not gate.gate_enabled(values):
		return gate.review_requirement([], {}, values)
	lines, builds, _readiness = expansion.expand_schedule(doc, {})
	return gate.review_requirement(lines, builds, values)


# --- Saving and revisions (WP-2.4, H6) -----------------------------------------------------------


@frappe.whitelist(methods=["POST"])
@endpoint
def save_design(schedule=None, design_json=None, design_name=None, expected_modified=None):
	from illumenate_lighting.illumenate_lighting.system_design import designs

	return designs.save_design(schedule, design_json, design_name, expected_modified)


@frappe.whitelist(methods=["POST"])
@endpoint
def create_revision(design=None, note=None):
	from illumenate_lighting.illumenate_lighting.system_design import designs

	return designs.create_revision(design, note)
