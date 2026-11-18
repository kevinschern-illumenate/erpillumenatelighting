"""Build points as ERPNext operation time, and calibrating the weights against real time.

Operations
    With "Add Build Operation to Work Orders" on (ilL-Production-Settings), each new
    Work Order gets one operation on the build workstation whose time is
    ``build points x minutes per point`` (minutes per point = 60 / points per
    person-hour). ERPNext then plans it on the workstation and makes a Job Card for it
    on submit, so its own capacity planning and labour tracking work.

    The time goes on the Work Order, not the BOM: BOMs are submitted, pinned builds
    that cannot change, while weights and points per person per day can.

Calibration
    Completed Work Orders with known labour time (Job Card time on the build
    operation, or minutes typed into "Actual Build Minutes") are fitted to their
    counts: minutes = sum(count_k x minutes_k). The fit is pulled toward the current
    weights (ridge), so a factor with few examples barely moves. Suggested weights are
    the fitted minutes relative to a 2C run; suggested points per person per day is
    what the crew actually achieved under the suggested weights.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api import build_points

MIN_SAMPLES = 5  # Work Orders containing a factor before its weight is re-suggested.
RIDGE = 0.1
ACTUAL_FIELD = "ill_actual_build_minutes"


# ---------------------------------------------------------------------------
# Pure maths
# ---------------------------------------------------------------------------


def minutes_per_point(values):
	per_hour = build_points.points_per_hour(values)
	return 60 / per_hour if per_hour else 0


def solve(matrix, vector):
	"""Gaussian elimination with partial pivoting; ``None`` when singular."""
	n = len(vector)
	a = [[*row, vector[i]] for i, row in enumerate(matrix)]
	for col in range(n):
		pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
		if abs(a[pivot][col]) < 1e-12:
			return None
		a[col], a[pivot] = a[pivot], a[col]
		for r in range(n):
			if r != col:
				factor = a[r][col] / a[col][col]
				for c in range(col, n + 1):
					a[r][c] -= factor * a[col][c]
	return [a[i][n] / a[i][i] for i in range(n)]


def fit(samples, prior, ridge=None):
	"""Minutes per unit of each factor.

	``samples``: [(counts, minutes)]. ``prior``: {factor: minutes per unit} the fit is
	pulled toward. Solves (X'X + L)b = X'y + L·prior, with L scaled to the data, and
	clamps at zero.
	"""
	keys = build_points.COUNT_KEYS
	n = len(keys)
	xtx = [[0.0] * n for _ in range(n)]
	xty = [0.0] * n
	for counts, minutes in samples:
		x = [float(counts.get(k) or 0) for k in keys]
		for i in range(n):
			xty[i] += x[i] * minutes
			for j in range(n):
				xtx[i][j] += x[i] * x[j]
	ridge = RIDGE if ridge is None else ridge
	scale = ridge * (sum(xtx[i][i] for i in range(n)) / n or 1)
	for i in range(n):
		xtx[i][i] += scale
		xty[i] += scale * prior[keys[i]]
	beta = solve(xtx, xty) or [prior[k] for k in keys]
	return {k: max(b, 0.0) for k, b in zip(keys, beta, strict=True)}


def suggest(samples, values):
	"""Observed throughput and suggested settings from (counts, minutes) samples."""
	keys = build_points.COUNT_KEYS
	current = build_points.weights(values)
	per_point = minutes_per_point(values)
	paid_hours = build_points._number(values, "paid_hours_per_day", build_points.DEFAULT_PAID_HOURS)
	support = {k: sum(1 for counts, _ in samples if counts.get(k)) for k in keys}
	total_minutes = sum(m for _, m in samples)
	total_points = sum(build_points.score(c, current) for c, _ in samples)
	observed_per_point = total_minutes / total_points if total_points else None

	minutes = fit(samples, {k: current[k] * (observed_per_point or per_point) for k in keys})
	base = minutes["runs_2c"] if support["runs_2c"] >= MIN_SAMPLES and minutes["runs_2c"] else None
	suggested = {}
	for k in keys:
		if support[k] < MIN_SAMPLES or not base:
			suggested[k] = current[k]  # Not enough evidence (or no 2C baseline): keep.
		else:
			suggested[k] = round(minutes[k] / base, 2)
	new_points = sum(build_points.score(c, suggested) for c, _ in samples)
	suggested_ppd = round(new_points / total_minutes * paid_hours * 60, 2) if total_minutes else None
	return {
		"samples": len(samples),
		"support": support,
		"total_minutes": round(total_minutes, 1),
		"total_points": round(total_points, 2),
		"observed_minutes_per_point": round(observed_per_point, 2) if observed_per_point else None,
		"planned_minutes_per_point": round(per_point, 2),
		"observed_points_per_person_day": round(paid_hours * 60 / observed_per_point, 2)
		if observed_per_point
		else None,
		"fitted_minutes": {k: round(v, 2) for k, v in minutes.items()},
		"current_weights": current,
		"suggested_weights": suggested,
		"suggested_points_per_person_day": suggested_ppd,
	}


# ---------------------------------------------------------------------------
# Work Order operation
# ---------------------------------------------------------------------------


def operation_row(points, values):
	return {
		"operation": values.get("build_operation"),
		"workstation": values.get("build_workstation"),
		"time_in_mins": round(float(points) * minutes_per_point(values), 2),
		"description": f"Build: {float(points):g} build points",
		"sequence_id": 1,
	}


def _enabled(values):
	return (
		str(values.get("add_build_operation") or "0") in ("1", "True", "true")
		and values.get("build_operation")
		and values.get("build_workstation")
	)


def add_build_operation(doc, method=None):
	"""Doc event (Work Order before_insert, after its points are set)."""
	values = build_points.settings()
	points = float(doc.get(build_points.POINTS_FIELD) or 0)
	if not _enabled(values) or points <= 0 or doc.get("operations"):
		return
	doc.append("operations", operation_row(points, values))


@frappe.whitelist(methods=["POST"])
def apply_to_open_work_orders():
	"""Give draft Work Orders without operations the build operation."""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	values = build_points.settings()
	if not _enabled(values):
		frappe.throw("Turn on Add Build Operation and set the operation and workstation first.")
	done, errors = 0, []
	for name in frappe.get_all("Work Order", filters={"docstatus": 0}, pluck="name"):
		doc = frappe.get_doc("Work Order", name)
		points = float(doc.get(build_points.POINTS_FIELD) or 0)
		if doc.operations or points <= 0:
			continue
		try:
			doc.append("operations", operation_row(points, values))
			doc.save()
			done += 1
		except Exception as error:
			errors.append(f"{name}: {error}")
	return {"updated": done, "errors": errors[:50]}


# ---------------------------------------------------------------------------
# Calibration data
# ---------------------------------------------------------------------------


def completed_work_orders(from_date, to_date):
	fields = ["name", "sales_order", "production_item", "item_name", "qty", "produced_qty", "bom_no", "actual_end_date"]
	if frappe.get_meta("Work Order").has_field(ACTUAL_FIELD):
		fields.append(ACTUAL_FIELD)
	return frappe.get_all(
		"Work Order",
		filters={
			"docstatus": 1,
			"status": "Completed",
			"actual_end_date": ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]],
		},
		fields=fields,
		order_by="actual_end_date asc",
		limit_page_length=0,
	)


def job_card_minutes(work_orders, operation):
	if not work_orders:
		return {}
	filters = {"work_order": ["in", work_orders], "docstatus": 1}
	if operation:
		filters["operation"] = operation
	out = {}
	for row in frappe.get_all("Job Card", filters=filters, fields=["work_order", "total_time_in_mins"], limit_page_length=0):
		out[row.work_order] = out.get(row.work_order, 0) + float(row.total_time_in_mins or 0)
	return out


def samples(from_date, to_date, values=None):
	"""Rows for the calibration report: per completed Work Order, counts and actual minutes."""
	values = build_points.settings() if values is None else values
	weights = build_points.weights(values)
	orders = completed_work_orders(from_date, to_date)
	logged = job_card_minutes([w.name for w in orders], values.get("build_operation"))
	rows = []
	for wo in orders:
		per_unit = build_points.bom_counts(wo.bom_no) or {}
		qty = float(wo.produced_qty or wo.qty or 0)
		counts = build_points.add(build_points.empty(), per_unit, qty)
		manual = float(wo.get(ACTUAL_FIELD) or 0)
		minutes, source = (manual, "Entered") if manual else (logged.get(wo.name, 0), "Job Card")
		points = build_points.score(counts, weights)
		rows.append(
			{
				"work_order": wo.name,
				"sales_order": wo.sales_order,
				"item": wo.production_item,
				"item_name": wo.item_name,
				"completed": wo.actual_end_date,
				"qty": qty,
				**counts,
				"points": points,
				"minutes": round(minutes, 1),
				"source": source if minutes else "No time",
				"minutes_per_point": round(minutes / points, 2) if minutes and points else None,
			}
		)
	return rows


def calibration(from_date, to_date, values=None):
	values = build_points.settings() if values is None else values
	rows = samples(from_date, to_date, values)
	usable = [
		({k: r[k] for k in build_points.COUNT_KEYS}, r["minutes"]) for r in rows if r["minutes"] > 0 and r["points"] > 0
	]
	return rows, suggest(usable, values)


@frappe.whitelist(methods=["POST"])
def apply_calibration(from_date, to_date):
	"""Write the suggested weights and points per person per day to the settings."""
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	_, result = calibration(from_date, to_date)
	if result["samples"] < MIN_SAMPLES:
		frappe.throw(f"Need at least {MIN_SAMPLES} completed Work Orders with labour time; found {result['samples']}.")
	settings = frappe.get_single(build_points.SETTINGS)
	for key, weight in result["suggested_weights"].items():
		settings.set(build_points.WEIGHT_FIELDS[key], weight)
	if result["suggested_points_per_person_day"]:
		settings.points_per_person_day = result["suggested_points_per_person_day"]
	settings.save()  # on_update re-scores stored counts.
	return result
