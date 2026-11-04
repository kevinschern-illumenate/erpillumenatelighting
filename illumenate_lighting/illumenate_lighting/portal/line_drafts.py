"""Durable configurator drafts for schedule lines (plan 3.1).

A draft is the configurator's exported request (``{family, template, selections, segments}``)
plus the add-line metadata, kept server-side so it survives a closed tab. Drafts are
``ilL-Configurator-Session`` rows with ``schedule`` set, keyed by user + schedule + line key
(empty for a new line) + product type. They never touch the schedule itself: restoring a draft
only pre-fills the configurator, and saving still goes through ``portal.configuration.save``.
Product finder sessions leave ``schedule`` empty and are unaffected. Drafts expire with the
finder sessions (``sessions.expire_sessions``, by ``last_seen``).
"""

import json

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import now_datetime

from illumenate_lighting.illumenate_lighting.portal import site_flags
from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line, schedule_context

DOCTYPE = "ilL-Configurator-Session"
MAX_DRAFT_BYTES = 64 * 1024
PRODUCT_TYPES = frozenset(
	{"Linear Fixture", "LED Tape", "COB Tape", "LED Neon", "LED Sheet", "Extrusion Kit", "Driver", "Controller"}
)


def _scope(schedule_name, product_type, line_key):
	if frappe.session.user == "Guest":
		frappe.throw("Please log in to keep configuration drafts", frappe.PermissionError)
	if product_type not in PRODUCT_TYPES:
		raise ValueError("Unsupported product type for a configuration draft")
	schedule = schedule_context(schedule_name, write=True)
	line_key = (line_key or "").strip()
	if line_key:
		line = resolve_line(schedule, line_key)
		line_key = line.get("line_key") or line.name
	return {
		"user": frappe.session.user,
		"schedule": schedule.name,
		"line_key": line_key,
		"product_type": product_type,
		"source": "Portal",
		"status": "Active",
	}


def _current(filters):
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		fields=["name", "draft_json", "last_seen", "modified"],
		order_by="modified desc",
	)
	return rows


def _payload(draft):
	if isinstance(draft, str):
		try:
			draft = json.loads(draft)
		except ValueError:
			raise ValueError("The draft is not valid JSON") from None
	if not isinstance(draft, dict) or not isinstance(draft.get("request"), dict):
		raise ValueError("The draft must contain the configurator request")
	metadata = draft.get("metadata")
	if metadata is not None and not isinstance(metadata, dict):
		raise ValueError("Draft line details must be an object")
	encoded = json.dumps({"request": draft["request"], "metadata": metadata or {}}, separators=(",", ":"), sort_keys=True)
	if len(encoded.encode()) > MAX_DRAFT_BYTES:
		raise ValueError("The draft is too large to keep")
	return encoded


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def save_draft(schedule_name, product_type, draft, line_key=None):
	if not site_flags.durable_drafts_enabled():
		return {"success": False, "disabled": True}
	filters = _scope(schedule_name, product_type, line_key)
	encoded = _payload(draft)
	now = now_datetime()
	rows = _current(filters)
	if rows:
		frappe.db.set_value(DOCTYPE, rows[0].name, {"draft_json": encoded, "last_seen": now})
		for extra in rows[1:]:
			frappe.db.set_value(DOCTYPE, extra.name, "status", "Used")
	else:
		frappe.get_doc({"doctype": DOCTYPE, **filters, "draft_json": encoded}).insert(ignore_permissions=True)
	return {"success": True, "saved_on": str(now)}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_draft(schedule_name, product_type, line_key=None):
	if not site_flags.durable_drafts_enabled():
		return {"success": True, "draft": None, "disabled": True}
	rows = _current(_scope(schedule_name, product_type, line_key))
	if not rows or not rows[0].draft_json:
		return {"success": True, "draft": None}
	stored = rows[0].draft_json
	draft = json.loads(stored) if isinstance(stored, str) else stored
	return {"success": True, "draft": draft, "saved_on": str(rows[0].last_seen or rows[0].modified)}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
def discard_draft(schedule_name, product_type, line_key=None):
	for row in _current(_scope(schedule_name, product_type, line_key)):
		frappe.db.set_value(DOCTYPE, row.name, "status", "Used")
	return {"success": True}
