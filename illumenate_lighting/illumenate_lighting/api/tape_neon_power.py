"""Driver schema adapter. Uses actual runs; never derives loads by averaging."""

import json
import math

import frappe

from illumenate_lighting.illumenate_lighting.api.power_planner import plan_power


def connected_runs(computed):
	"""An outgoing jumper and the next segment's first run share one output."""
	segments = computed.get("segments") or []
	if not segments:
		return computed.get("runs") or []
	runs = []
	for index, segment in enumerate(segments):
		segment_runs = [dict(run) for run in segment.get("runs") or []]
		if not segment_runs:
			raise ValueError("Every segment needs a computed electrical run plan")
		if index and segments[index - 1].get("end_type") == "Jumper":
			first = segment_runs.pop(0)
			joined = runs[-1]
			joined["run_watts"] += first["run_watts"]
			joined["run_len_mm"] += first["run_len_mm"]
			limit = computed.get("max_run_ft_effective")
			if not limit or joined["run_len_mm"] > float(limit) * 304.8 + 1e-6:
				raise ValueError(
					"Jumper-connected length exceeds the approved run limit; use independent feeds"
				)
			joined["run_len_in"] = joined["run_len_mm"] / 25.4
			joined["run_len_ft"] = joined["run_len_mm"] / 304.8
		runs.extend(segment_runs)
	for index, run in enumerate(runs, 1):
		run["run_index"] = index
	return runs


def select_plan(
	template,
	runs_count,
	total_watts,
	offering,
	protocol=None,
	run_loads=None,
	template_type="ilL-Tape-Neon-Template",
):
	if isinstance(run_loads, str):
		run_loads = json.loads(run_loads)
	if run_loads is None:
		if int(runs_count) != 1:
			raise ValueError("Actual per-run loads are required; average sizing is unsupported")
		run_loads = [total_watts]
	circuits = [{"run_key": str(i + 1), "watts": load} for i, load in enumerate(run_loads)]
	if len(circuits) != int(runs_count) or not math.isclose(sum(run_loads), float(total_watts), abs_tol=0.1):
		raise ValueError("Run loads do not reconcile to total fixture watts")
	if not offering or not offering.get("tape_spec"):
		raise ValueError("A resolved tape specification is required for electrical compatibility")
	spec = frappe.get_doc("ilL-Spec-LED Tape", offering.tape_spec)
	if not spec.input_voltage or not spec.input_protocol:
		raise ValueError("Tape voltage and input protocol are required")
	from illumenate_lighting.illumenate_lighting.api.driver_catalog import candidates as catalog_candidates

	candidates, revisions = catalog_candidates(
		template_type, template, spec.input_voltage, spec.input_protocol, protocol
	)
	plan = plan_power(circuits, candidates)
	plan["dependency_revisions"] = {
		row["driver_item"]: revisions[row["driver_item"]] for row in plan["drivers"]
	}
	return plan, []


def resolve_before_save(result, template, offering, include_power, protocol):
	result["include_power_supply"] = include_power
	result["dimming_protocol_code"] = protocol
	try:
		runs = connected_runs(result["computed"])
		result["computed"]["runs"] = runs
		result["computed"]["runs_count"] = len(runs)
		if not include_power:
			result["resolved_items"]["driver_plan"] = plan_power(
				[{"run_key": str(r["run_index"]), "watts": r["run_watts"]} for r in runs],
				[],
				include_power=False,
			)
			return
		if not template:
			raise ValueError("Select an engineering-approved template for included power")
		plan, messages = select_plan(
			template,
			len(runs),
			result["computed"]["total_watts"],
			offering,
			protocol,
			run_loads=[run["run_watts"] for run in runs],
		)
		result["resolved_items"]["driver_plan"] = plan
		result["messages"].extend(messages)
	except (ValueError, frappe.ValidationError) as exc:
		result.update({"success": False, "is_valid": False, "error": str(exc)})
		result["messages"].append({"severity": "error", "text": str(exc)})
