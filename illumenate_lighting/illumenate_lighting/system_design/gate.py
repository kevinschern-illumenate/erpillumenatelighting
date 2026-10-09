# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""D4 review requirement before a Sales Order (plan H8.5, WP-4.4).

The gate is off unless both the Settings switch and the ``ill_system_design_review_gate`` site flag
are on; while off it always answers "not required" and never touches ordering. A required review is
satisfied by an Approved current design whose line fingerprints match the schedule, or by a staff
override recorded against the schedule's current fingerprints (so it lapses when the schedule changes).
"""

import hashlib
import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError
from illumenate_lighting.illumenate_lighting.system_design.protocols import DMX_PROTOCOLS, PHASE_PROTOCOLS

SITE_FLAG = "ill_system_design_review_gate"
EVENT_DOCTYPE = "ilL-Portal-Event"
SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"
OVERRIDE_PREFIX = "system_design_gate_override"
OVERRIDE_CAPABILITIES = ("sales", "design_review")


def gate_enabled(values):
	from illumenate_lighting.illumenate_lighting.portal.site_flags import conf_flag

	return bool(values.review_gate_enabled and conf_flag(SITE_FLAG, default=False))


def load_profile(lines, builds):
	"""Pure: ``(total connected watts, engine protocols)`` of serialized lines and builds."""
	total, protocols = 0.0, set()
	for line in lines:
		qty = line["qty"]
		if line["kind"] == "third-party" and line["thirdParty"]:
			total += (line["thirdParty"]["wattsEach"] or 0) * qty
			if line["thirdParty"]["dimming"]:
				protocols.add(line["thirdParty"]["dimming"])
		elif line["kind"] == "configured":
			ref = line["configured"]
			build = builds.get(ref["doctype"], {}).get(ref["name"])
			if build:
				total += (build.get("totalWatts") or sum(run["watts"] for run in build["runs"])) * qty
				protocols.update(build.get("protocols") or [])
	return total, protocols


def reasons_from(total, protocols, values):
	reasons = []
	if total > values.review_gate_watts:
		reasons.append({"code": "LOAD_OVER_THRESHOLD", "detail": _("{0} W").format(round(total))})
	if values.review_gate_dmx and protocols & DMX_PROTOCOLS:
		reasons.append({"code": "DMX", "detail": _("DMX control")})
	if values.review_gate_phase_dimming and protocols & PHASE_PROTOCOLS:
		reasons.append({"code": "PHASE_DIMMING", "detail": _("Phase-cut dimming")})
	return reasons


def reasons_for(lines, builds, values):
	"""Pure: H8.5 reasons from serialized lines and builds (see :mod:`.expansion`)."""
	return reasons_from(*load_profile(lines, builds), values)


def design_reasons(reasons, design, values):
	"""Pure: add the D4 reasons a saved design shows (DMX or phase-cut zones) but the lines do not."""
	codes = {reason["code"] for reason in reasons}
	extra = []
	if design and values.review_gate_dmx and design.get("uses_dmx") and "DMX" not in codes:
		extra.append({"code": "DMX", "detail": _("DMX control")})
	if (
		design
		and values.review_gate_phase_dimming
		and design.get("uses_phase_dimming")
		and "PHASE_DIMMING" not in codes
	):
		extra.append({"code": "PHASE_DIMMING", "detail": _("Phase-cut dimming")})
	return reasons + extra


def approved_match(design, prints):
	"""Pure: the design is Approved and was approved against exactly these schedule lines."""
	if not design or design.get("status") != "Approved":
		return False
	try:
		stored = json.loads(design.get("line_fingerprint_json") or "null")
	except ValueError:
		return False
	return stored == prints


def review_requirement(lines, builds, values, design=None, prints=None, override=None):
	"""H8.5: ``{required, reasons, satisfied, approved_design, override}`` for one schedule.

	``design`` is the schedule's current design (a dict or document), ``prints`` the schedule's line
	fingerprints now and ``override`` the active staff override, if any.
	"""
	if not gate_enabled(values):
		return {
			"required": False,
			"reasons": [],
			"satisfied": True,
			"approved_design": None,
			"override": None,
		}
	reasons = design_reasons(reasons_for(lines, builds, values), design, values)
	approved = approved_match(design, prints)
	return {
		"required": bool(reasons),
		"reasons": reasons,
		"satisfied": not reasons or approved or bool(override),
		"approved_design": design.get("name") if approved else None,
		"override": override if reasons else None,
	}


def fingerprint_hash(prints):
	text = json.dumps(prints, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def override_key(schedule, prints):
	return f"{OVERRIDE_PREFIX}:{schedule}:{fingerprint_hash(prints)}"


def active_override(schedule, prints):
	"""The staff override recorded for exactly these schedule lines, as ``{by, reason, on}``."""
	row = frappe.db.get_value(
		EVENT_DOCTYPE,
		{"event_key": override_key(schedule, prints)},
		["subject", "message", "creation"],
		as_dict=True,
	)
	if not row:
		return None
	return {"by": row.subject, "reason": row.message, "on": str(row.creation)}


def schedule_requirement(schedule_doc, values=None, lines=None, builds=None):
	"""The H8.5 requirement for a schedule document, with its current design, approval and override."""
	from illumenate_lighting.illumenate_lighting.system_design import expansion, reconcile
	from illumenate_lighting.illumenate_lighting.system_design.designs import current_design
	from illumenate_lighting.illumenate_lighting.system_design.settings import settings

	values = values or settings()
	if not gate_enabled(values):
		return review_requirement([], {}, values)
	if lines is None:
		lines, builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	record = current_design(schedule_doc)
	prints = reconcile.fingerprints(lines, builds)
	return review_requirement(
		lines,
		builds,
		values,
		design=record.as_dict() if record else None,
		prints=prints,
		override=active_override(schedule_doc.name, prints),
	)


def _flag_on():
	try:
		from illumenate_lighting.illumenate_lighting.portal.site_flags import conf_flag

		return bool(conf_flag(SITE_FLAG, default=False))
	except Exception:
		return False


def order_block(schedule_doc):
	"""``None`` when the D4 gate lets this schedule be ordered, else the reason to show.

	Called at the end of ``can_request_schedule_order``. With the site flag off this never blocks;
	with it on, an unexpected failure blocks with a support message (fail closed).
	"""
	if not _flag_on():
		return None
	try:
		requirement = schedule_requirement(schedule_doc)
	except Exception:
		frappe.log_error(title=f"System Designer review gate: {schedule_doc.name}"[:140])
		return _(
			"The system design review check could not run, so this schedule cannot be ordered yet. "
			"Please contact ilLumenate support."
		)
	if requirement["required"] and not requirement["satisfied"]:
		reasons = ", ".join(str(reason.get("detail") or reason["code"]) for reason in requirement["reasons"])
		return _("ilLumenate review of the system design is required before ordering: {0}").format(reasons)
	return None


def override_review_gate(schedule, reason=None):
	"""Order Approvers and Applications Engineers let a schedule be ordered without an approved design.

	Recorded as an ``ilL-Portal-Event`` keyed by the schedule's current line fingerprints, so the
	override stops applying as soon as the schedule's lines change. Repeating it is harmless.
	"""
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed
	from illumenate_lighting.illumenate_lighting.system_design import access, expansion, reconcile
	from illumenate_lighting.illumenate_lighting.system_design.settings import settings

	if not any(allowed(name) for name in OVERRIDE_CAPABILITIES):
		raise DesignError(
			"FORBIDDEN", _("Only Order Approvers and Applications Engineers can override the review")
		)
	reason = str(reason or "").strip()
	if len(reason) < 3:
		raise DesignError("INVALID", _("Give a reason for the override"))
	schedule_doc = access.require_read(schedule)
	values = settings()
	lines, builds, _readiness = expansion.expand_schedule(schedule_doc, {})
	requirement = schedule_requirement(schedule_doc, values, lines, builds)
	if not requirement["required"]:
		raise DesignError(
			"INVALID", _("This schedule does not need a review, so there is nothing to override")
		)
	prints = reconcile.fingerprints(lines, builds)
	key = override_key(schedule_doc.name, prints)
	if not frappe.db.exists(EVENT_DOCTYPE, {"event_key": key}):
		doc = frappe.get_doc(
			{
				"doctype": EVENT_DOCTYPE,
				"event_key": key,
				"reference_type": SCHEDULE_DOCTYPE,
				"reference_name": schedule_doc.name,
				"preference": "system_design",
				"subject": frappe.session.user,
				"message": reason[:1000],
			}
		)
		doc.flags.notification_service_write = True
		doc.insert(ignore_permissions=True)
	return {
		"override_id": key,
		"review_requirement": schedule_requirement(schedule_doc, values, lines, builds),
	}
