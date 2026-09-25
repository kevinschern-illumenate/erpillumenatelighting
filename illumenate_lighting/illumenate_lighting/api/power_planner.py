"""Exact bounded supply allocation for explicitly independent output circuits.

Each circuit uses one output. Outputs are never implicitly paralleled. Family
engines supply actual circuit loads; an average load is not a valid substitute.
"""

from functools import cache

from illumenate_lighting.illumenate_lighting.api.configuration_contract import finite_number

MAX_CIRCUITS = 12
MAX_CANDIDATES = 32


def plan_power(circuits, candidates, *, include_power=True):
	loads = [finite_number(row["watts"], minimum=0, field="circuit watts") for row in circuits]
	if not loads or any(load <= 0 for load in loads):
		raise ValueError("Every electrical circuit must have a positive load")
	keys = [row["run_key"] for row in circuits]
	if len(set(keys)) != len(keys):
		raise ValueError("Electrical run keys must be unique")
	if not include_power:
		return {"status": "excluded", "drivers": [], "allocations": [], "requirements": circuits}
	if len(loads) > MAX_CIRCUITS or len(candidates) > MAX_CANDIDATES:
		raise ValueError("Power plan exceeds the supported search size; engineering review is required")
	drivers = []
	for candidate in sorted(candidates, key=lambda row: row["item_code"]):
		factor = finite_number(candidate["usable_load_factor"], minimum=0)
		outputs = finite_number(candidate["outputs_count"], minimum=1)
		if factor <= 0 or factor > 1 or not outputs.is_integer():
			raise ValueError("Driver load factor or output count is invalid")
		drivers.append(
			{
				**candidate,
				"capacity": finite_number(candidate["max_wattage"], minimum=0) * factor,
				"output_capacity": finite_number(candidate["max_wattage_per_output"], minimum=0) * factor,
				"outputs_count": int(outputs),
				"priority": finite_number(candidate.get("priority", 0)),
				"selection_cost": finite_number(candidate.get("cost", 0), minimum=0),
			}
		)
	full = (1 << len(loads)) - 1
	subset_load = [sum(loads[i] for i in range(len(loads)) if mask & (1 << i)) for mask in range(full + 1)]
	feasible = [[] for _ in loads]
	for d, driver in enumerate(drivers):
		for mask in range(1, full + 1):
			members = [i for i in range(len(loads)) if mask & (1 << i)]
			if len(members) > driver["outputs_count"] or subset_load[mask] > driver["capacity"] + 1e-9:
				continue
			if any(loads[i] > driver["output_capacity"] + 1e-9 for i in members):
				continue
			for i in members:
				feasible[i].append((mask, d))

	@cache
	def solve(remaining):
		if not remaining:
			return (0, 0, 0, 0, ()), ()
		first = (remaining & -remaining).bit_length() - 1
		best = None
		for mask, d in feasible[first]:
			if mask & remaining != mask:
				continue
			tail = solve(remaining ^ mask)
			if tail is None:
				continue
			score, selection = tail
			driver = drivers[d]
			new_score = (
				score[0] + 1,
				score[1] + driver["selection_cost"],
				score[2] + driver["priority"],
				score[3] + driver["capacity"],
				tuple(sorted((*score[4], driver["item_code"]))),
			)
			result = new_score, ((d, mask), *selection)
			if best is None or new_score < best[0]:
				best = result
		return best

	solution = solve(full)
	if solution is None:
		raise ValueError(
			"No compatible supply allocation can carry every circuit within total and per-output limits"
		)
	quantities, allocations = {}, []
	for number, (d, mask) in enumerate(solution[1], 1):
		driver = drivers[d]
		item = driver["item_code"]
		quantities[item] = quantities.get(item, 0) + 1
		for output, i in enumerate((i for i in range(len(loads)) if mask & (1 << i)), 1):
			allocations.append(
				{"supply": number, "item_code": item, "output": output, "run_key": keys[i], "watts": loads[i]}
			)
	return {
		"status": "selected",
		"drivers": [{"driver_item": item, "qty": qty} for item, qty in sorted(quantities.items())],
		"allocations": allocations,
		"requirements": circuits,
	}
