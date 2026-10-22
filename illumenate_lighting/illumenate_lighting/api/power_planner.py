"""Exact bounded supply allocation for explicitly independent output circuits.

Per-run allocation (the default) gives each circuit its own output. Grouped
allocation lets circuits share an output when their combined load fits that
output, so fewer and smaller supplies carry the same circuits. A circuit is
never split across outputs and outputs are never implicitly paralleled. Family
engines supply actual circuit loads; an average load is not a valid substitute.
"""

from functools import cache

from illumenate_lighting.illumenate_lighting.api.configuration_contract import finite_number

MAX_CIRCUITS = 12
MAX_CANDIDATES = 32
PER_RUN, GROUPED = "per_run", "grouped"
ALLOCATION_MODES = (PER_RUN, GROUPED)


def allocation_mode(value):
	"""Canonical allocation mode; blank means the per-run default."""
	value = str(value or "").strip().lower() or PER_RUN
	if value not in ALLOCATION_MODES:
		raise ValueError("Power allocation must be per_run or grouped")
	return value


def _packing(loads, capacity):
	"""Fewest outputs of *capacity* for every subset (exact subset DP), with each item's output."""
	full = 1 << len(loads)
	# best[mask] = (outputs used, load on the last output); 0 outputs marks an impossible subset.
	best, last = [(1, 0.0)] + [None] * (full - 1), [0] * full
	for mask in range(1, full):
		choice = None
		for i in range(len(loads)):
			if not mask & (1 << i) or best[mask ^ (1 << i)] is None:
				continue
			count, fill = best[mask ^ (1 << i)]
			if loads[i] > capacity + 1e-9:
				continue
			option = (count, fill + loads[i]) if fill + loads[i] <= capacity + 1e-9 else (count + 1, loads[i])
			if choice is None or option < choice:
				choice, last[mask] = option, i
		best[mask] = choice

	def outputs(mask):
		"""Output number (1-based) for each member of *mask*, numbered by first circuit."""
		assigned = {}
		while mask:
			i = last[mask]
			assigned[i] = best[mask][0]
			mask ^= 1 << i
		order = {}
		for i in sorted(assigned):
			order.setdefault(assigned[i], len(order) + 1)
		return {i: order[output] for i, output in assigned.items()}

	return [row and row[0] for row in best], outputs


def plan_power(circuits, candidates, *, include_power=True, allocation=PER_RUN):
	allocation = allocation_mode(allocation)
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
	packings = {}
	if allocation == GROUPED:
		for driver in drivers:
			if driver["output_capacity"] not in packings:
				packings[driver["output_capacity"]] = _packing(loads, driver["output_capacity"])
	feasible = [[] for _ in loads]
	for d, driver in enumerate(drivers):
		for mask in range(1, full + 1):
			if subset_load[mask] > driver["capacity"] + 1e-9:
				continue
			members = [i for i in range(len(loads)) if mask & (1 << i)]
			if allocation == GROUPED:
				needed = packings[driver["output_capacity"]][0][mask]
				if needed is None or needed > driver["outputs_count"]:
					continue
			elif len(members) > driver["outputs_count"] or any(
				loads[i] > driver["output_capacity"] + 1e-9 for i in members
			):
				continue
			for i in members:
				feasible[i].append((mask, d))

	def rank(driver):
		# Grouping exists to shrink the supply footprint, so it ranks rated capacity ahead of cost.
		if allocation == GROUPED:
			return driver["capacity"], driver["selection_cost"], driver["priority"]
		return driver["selection_cost"], driver["priority"], driver["capacity"]

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
			a, b, c = rank(driver)
			new_score = (
				score[0] + 1,
				score[1] + a,
				score[2] + b,
				score[3] + c,
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
		members = [i for i in range(len(loads)) if mask & (1 << i)]
		if allocation == GROUPED:
			output_of = packings[driver["output_capacity"]][1](mask)
		else:
			output_of = {i: output for output, i in enumerate(members, 1)}
		for i in sorted(members, key=lambda i: (output_of[i], i)):
			allocations.append(
				{
					"supply": number,
					"item_code": item,
					"output": output_of[i],
					"run_key": keys[i],
					"watts": loads[i],
				}
			)
	plan = {
		"status": "selected",
		"drivers": [{"driver_item": item, "qty": qty} for item, qty in sorted(quantities.items())],
		"allocations": allocations,
		"requirements": circuits,
	}
	if allocation == GROUPED:
		# Only the non-default mode is recorded, so existing per-run build identities are unchanged.
		plan["allocation"] = GROUPED
	return plan
