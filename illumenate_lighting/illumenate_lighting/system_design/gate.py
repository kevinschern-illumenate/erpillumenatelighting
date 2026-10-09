# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""D4 review requirement before a Sales Order (plan H8.5).

WP-2.3 reports the requirement to the designer. The gate is off unless both the Settings switch and
the ``ill_system_design_review_gate`` site flag are on; while off it always answers "not required".
Approval (``ilL-System-Design``, WP-2.4), overrides and the order-request integration land in WP-4.4,
so a required review is reported as not yet satisfied.
"""

from frappe import _

from illumenate_lighting.illumenate_lighting.system_design.protocols import DMX_PROTOCOLS, PHASE_PROTOCOLS

SITE_FLAG = "ill_system_design_review_gate"


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


def review_requirement(lines, builds, values):
	if not gate_enabled(values):
		return {"required": False, "reasons": [], "satisfied": True, "approved_design": None}
	reasons = reasons_for(lines, builds, values)
	return {
		"required": bool(reasons),
		"reasons": reasons,
		"satisfied": not reasons,
		"approved_design": None,
	}
