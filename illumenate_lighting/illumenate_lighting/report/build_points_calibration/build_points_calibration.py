# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Build points against real labour time, and the weights the data suggests.

One row per Work Order completed in the period: its counts, build points under the
current weights, and labour minutes (typed into "Actual Build Minutes", else Job
Card time on the build operation). The summary compares planned and observed
minutes per point and lists suggested weights; "Apply suggested weights" writes
them to ilL-Production-Settings.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from illumenate_lighting.illumenate_lighting.api import build_operations, build_points

LABELS = {
	"runs_2c": "2C",
	"runs_3c": "3C",
	"runs_4c": "4C",
	"runs_5c": "5C",
	"runs_6c": "6C",
	"loose": "Loose",
	"wet": "WR",
	"fmc": "FMC",
	"assembly": "Assy",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -90))
	rows, result = build_operations.calibration(from_date, to_date)
	if filters.get("only_timed"):
		rows = [r for r in rows if r["minutes"]]
	columns = [
		{"fieldname": "work_order", "label": _("Work Order"), "fieldtype": "Link", "options": "Work Order", "width": 160},
		{"fieldname": "sales_order", "label": _("Sales Order"), "fieldtype": "Link", "options": "Sales Order", "width": 150},
		{"fieldname": "item_name", "label": _("Item"), "fieldtype": "Data", "width": 200},
		{"fieldname": "completed", "label": _("Completed"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 70},
		*[{"fieldname": k, "label": LABELS[k], "fieldtype": "Float", "width": 65} for k in build_points.COUNT_KEYS],
		{"fieldname": "points", "label": _("Points"), "fieldtype": "Float", "width": 85},
		{"fieldname": "minutes", "label": _("Labour Min"), "fieldtype": "Float", "width": 95},
		{"fieldname": "source", "label": _("Time From"), "fieldtype": "Data", "width": 90},
		{"fieldname": "minutes_per_point", "label": _("Min / Point"), "fieldtype": "Float", "width": 95},
	]
	return columns, rows, message(result), None, summary(result)


def summary(result):
	def number(label, value, indicator="Blue", datatype="Float"):
		return {"label": label, "value": value if value is not None else 0, "indicator": indicator, "datatype": datatype}

	observed, planned = result["observed_minutes_per_point"], result["planned_minutes_per_point"]
	return [
		number(_("Work Orders with time"), result["samples"], datatype="Int"),
		number(_("Planned min / point"), planned),
		number(
			_("Observed min / point"),
			observed,
			"Green" if observed and planned and observed <= planned else "Orange",
		),
		number(_("Observed points / person-day"), result["observed_points_per_person_day"]),
		number(_("Suggested points / person-day"), result["suggested_points_per_person_day"]),
	]


def message(result):
	if result["samples"] < build_operations.MIN_SAMPLES:
		return _(
			"Only {0} completed Work Orders have labour time in this period; at least {1} are needed "
			"before weights are suggested. Record time with Job Cards or Actual Build Minutes."
		).format(result["samples"], build_operations.MIN_SAMPLES)
	rows = "".join(
		f"<tr><td>{LABELS[k]}</td><td style='text-align:right'>{result['current_weights'][k]:g}</td>"
		f"<td style='text-align:right'><b>{result['suggested_weights'][k]:g}</b></td>"
		f"<td style='text-align:right'>{result['fitted_minutes'][k]:g}</td>"
		f"<td style='text-align:right'>{result['support'][k]}</td></tr>"
		for k in build_points.COUNT_KEYS
	)
	return (
		"<p>"
		+ _("Suggested weights keep the current value for any factor seen on fewer than {0} Work Orders.").format(
			build_operations.MIN_SAMPLES
		)
		+ "</p><table class='table table-bordered' style='max-width:560px'><thead><tr><th>"
		+ "</th><th>".join([_("Factor"), _("Current"), _("Suggested"), _("Fitted min / unit"), _("Work Orders")])
		+ f"</th></tr></thead><tbody>{rows}</tbody></table>"
	)
