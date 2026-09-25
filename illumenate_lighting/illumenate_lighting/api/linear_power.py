"""Linear fixture adapter for the common actual-circuit power planner."""

from illumenate_lighting.illumenate_lighting.api.tape_neon_power import select_plan


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
