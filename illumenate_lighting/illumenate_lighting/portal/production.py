"""Line demand coverage, independent of framework and commercial status."""

from collections import Counter


def production_coverage(lines, work_orders):
	lines = list(lines)
	by_name = {line["name"]: line for line in lines}
	counts = Counter(line.get("item_code") for line in lines)
	by_item = {line.get("item_code"): line["name"] for line in lines if counts[line.get("item_code")] == 1}
	planned, produced, unmapped = {}, {}, []
	for work in work_orders:
		key = work.get("sales_order_item") or by_item.get(work.get("production_item"))
		if key not in by_name:
			unmapped.append(work.get("name"))
			continue
		planned[key] = planned.get(key, 0) + float(work.get("qty") or 0)
		produced[key] = produced.get(key, 0) + float(work.get("produced_qty") or 0)
	required, rows = [], []
	for line in lines:
		key = line["name"]
		factor = float(line.get("conversion_factor") or 1)
		demand = float(line.get("qty") or 0) * factor
		manufactured = (
			any(
				line.get(field)
				for field in (
					"ill_configured_group",
					"ill_configured_fixture",
					"ill_configured_tape_neon",
					"ill_configured_led_sheet",
					"ill_bom",
					"bom_no",
				)
			)
			or key in planned
		)
		complete = demand > 0 and produced.get(key, 0) >= demand
		row = {
			"line": key,
			"path": "manufacturing" if manufactured else "standard_item",
			"stock_demand": demand,
			"planned_stock_qty": planned.get(key, 0),
			"produced_qty": produced.get(key, 0) / factor,
			"complete": complete if manufactured else None,
		}
		rows.append(row)
		if manufactured:
			required.append(row)
	return {
		"lines": rows,
		"unmapped_work_orders": unmapped,
		"complete": bool(required) and not unmapped and all(row["complete"] for row in required),
	}
