"""Linear fixture adapter for the common actual-circuit power planner."""

import frappe

from illumenate_lighting.illumenate_lighting.api.tape_neon_power import select_plan

# Historic per-run ceiling; a run is never longer than this even when a bigger supply is eligible.
MAX_WATTS_PER_RUN = 85.0


def run_watt_limit(template, offering, protocol=None, ceiling=MAX_WATTS_PER_RUN):
	"""Largest load one eligible supply output carries, so no run outgrows every output.

	Runs are split by watts before a supply is chosen. Splitting at a fixed 85 W left runs
	that no 100 W supply (80 W usable per output) could carry, so the planner refused the build.
	"""
	from illumenate_lighting.illumenate_lighting.api import driver_catalog

	try:
		spec = frappe.get_doc("ilL-Spec-LED Tape", offering.tape_spec)
		found, _ = driver_catalog.candidates(
			"ilL-Fixture-Template", template, spec.input_voltage, spec.input_protocol, protocol
		)
		usable = [
			min(float(d["max_wattage"]), float(d["max_wattage_per_output"])) * float(d["usable_load_factor"])
			for d in found
		]
	except (AttributeError, KeyError, TypeError, ValueError, frappe.ValidationError):
		# Supply selection reports bad driver data itself; keep splitting by the historic ceiling.
		return ceiling
	usable = [watts for watts in usable if watts > 0]
	return min(ceiling, max(usable)) if usable else ceiling


def select(template, runs_count, total_watts, offering, protocol=None, runs=None):
	if runs is None:
		raise ValueError("Actual run wattages are required for linear supply selection")
	plan, messages = select_plan(
		template,
		runs_count,
		total_watts,
		offering,
		protocol,
		run_loads=[run["run_watts"] for run in runs],
		template_type="ilL-Fixture-Template",
	)
	# Preserve the existing linear UI/child-table projection; allocations remain authoritative.
	for row in plan["drivers"]:
		item = row["driver_item"]
		spec = plan["dependency_revisions"][item]
		allocations = [a for a in plan["allocations"] if a["item_code"] == item]
		usable = float(spec["max_wattage"]) * float(spec["usable_load_factor"])
		row.update(
			{
				"item_code": item,
				"driver_spec": spec["name"],
				"outputs_per_driver": spec["outputs_count"],
				"outputs_used": len(allocations),
				"w_usable_per_driver": usable,
				"total_w_usable": usable * row["qty"],
				"mapping_notes": "; ".join(
					f"Run {a['run_key']} -> Supply {a['supply']} Output {a['output']}" for a in allocations
				),
			}
		)
	plan["requested_protocol"] = protocol
	return plan, messages


def excluded(runs, protocol=None):
	return {
		"status": "excluded",
		"drivers": [],
		"allocations": [],
		"requested_protocol": protocol,
		"requirements": [{"run_key": str(row["run_index"]), "watts": row["run_watts"]} for row in runs],
	}
