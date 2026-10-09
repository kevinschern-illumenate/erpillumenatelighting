# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Pilot telemetry (WP-3.9, plan §23): ``ilL-Portal-Event`` rows keyed ``system_design:<event>:…``.

The server records ``opened``, ``saved`` and stored riser exports itself. The browser reports what
only it sees: a riser downloaded without being stored, checks fixed, and the feedback prompt. Rows
carry who, which schedule and design, and small details; never prices or costs (D6). No delivery
rows are written, so nothing is emailed. Telemetry never blocks the work it describes.
"""

import json
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime

from illumenate_lighting.illumenate_lighting.system_design import access
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

EVENT_DOCTYPE = "ilL-Portal-Event"
PREFERENCE = "system_design"
CLIENT_EVENTS = frozenset({"riser_exported", "check_fixed", "feedback"})
MAX_DETAIL_BYTES = 2000
# Details the browser may send, by event; anything else is dropped.
CLIENT_DETAILS = {
	"riser_exported": {"kind": str, "sheet": str, "stored": bool},
	"check_fixed": {"codes": list},
	"feedback": {"rating": int, "comment": str},
}


def event_key(event, name):
	"""``system_design:<event>:<design or schedule>:<timestamp>:<nonce>``, unique per row."""
	stamp = str(now_datetime()).replace(" ", "T")
	return f"system_design:{event}:{name}:{stamp}:{secrets.token_hex(3)}"[:140]


def record(event, schedule, design=None, details=None):
	"""Insert one event row; a failure is logged and never raised."""
	savepoint = "system_design_telemetry"
	try:
		frappe.db.savepoint(savepoint)
		doc = frappe.get_doc(
			{
				"doctype": EVENT_DOCTYPE,
				"event_key": event_key(event, design or schedule),
				"reference_type": "ilL-System-Design" if design else "ilL-Project-Fixture-Schedule",
				"reference_name": design or schedule,
				"preference": PREFERENCE,
				"subject": frappe.session.user,
				"message": json.dumps(
					{"event": event, "schedule": schedule, "design": design, **(details or {})},
					sort_keys=True,
					separators=(",", ":"),
				),
			}
		)
		doc.flags.notification_service_write = True
		doc.insert(ignore_permissions=True)
		return doc.event_key
	except Exception:
		try:
			# Keep the caller's work: undo only the failed telemetry insert.
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(title=f"System Designer telemetry: {event}"[:140])
		except Exception:
			pass
		return None


def clean_details(event, details):
	"""Keep only the known fields of a browser event, with their types and sizes checked."""
	if details in (None, ""):
		details = {}
	if isinstance(details, str):
		try:
			details = json.loads(details)
		except ValueError:
			raise DesignError("INVALID", _("details must be valid JSON"))
	if not isinstance(details, dict):
		raise DesignError("INVALID", _("details must be an object"))
	kept = {}
	for key, kind in CLIENT_DETAILS[event].items():
		value = details.get(key)
		if value is None:
			continue
		if kind is int and (isinstance(value, bool) or not isinstance(value, int)):
			raise DesignError("INVALID", _("{0} must be a whole number").format(key))
		if kind is not int and not isinstance(value, kind):
			raise DesignError("INVALID", _("{0} has the wrong type").format(key))
		if kind is str:
			value = value.strip()[:500]
		if kind is list:
			value = [str(item)[:60] for item in value[:20]]
		kept[key] = value
	if event == "feedback" and not 1 <= kept.get("rating", 0) <= 5:
		raise DesignError("INVALID", _("Choose a rating from 1 to 5"))
	if len(json.dumps(kept)) > MAX_DETAIL_BYTES:
		raise DesignError("INVALID", _("details are too long"))
	return kept


def log_event(schedule, event, design=None, details=None):
	"""Record an event the browser reports (H6 telemetry)."""
	from illumenate_lighting.illumenate_lighting.system_design.designs import require_designer

	if event not in CLIENT_EVENTS:
		raise DesignError("INVALID", _("Unknown event"))
	doc = access.require_read(schedule)
	require_designer()
	if design:
		access.require_design(design, doc.name)
	kept = clean_details(event, details)
	return {"event_key": record(event, doc.name, design or None, kept)}
