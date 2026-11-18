# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Build points (manufacturing difficulty) fields, plus the warehouse ship date.

BOM carries per-unit counts of its pinned build. Sales Order Item and Work Order
carry them times quantity, and Sales Order carries the order total. All of them can
be written after submit, because BOMs and orders are submitted before they are
counted and weights can change later. The fields sit in their own section at the
end of each form so no standard field moves.

Existing BOMs and open orders are counted at the end. A failure there is logged
and does not stop the migration: run ``build_points.backfill`` again afterwards.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

COUNTS = (
	("ill_runs_2c", "2C Runs"),
	("ill_runs_3c", "3C Runs"),
	("ill_runs_4c", "4C Runs"),
	("ill_runs_5c", "5C Runs"),
	("ill_runs_6c", "6C Runs"),
	("ill_wet", "Wet-Rated Runs"),
	("ill_fmc", "FMC / Jumpers"),
	("ill_assembly", "Assemblies"),
	("ill_loose", "Loose (Bulk Reels)"),
)


OURS = {name for name, _ in COUNTS} | {
	"ill_build_points_section",
	"ill_build_points",
	"ill_build_points_stamped",
	"ill_build_points_column",
	"ill_build_points_warnings",
	"ill_build_hours",
	"ill_worth_per_point",
	"ill_estimated_ship_date",
}


def _last_field(doctype):
	"""Our block goes after the form's last field, so no standard field moves into it."""
	return [f.fieldname for f in frappe.get_meta(doctype).fields if f.fieldname not in OURS][-1]


def _block(doctype, count_type, *, extra=(), label="Build Points"):
	rows = [
		{
			"fieldname": "ill_build_points_section",
			"fieldtype": "Section Break",
			"label": label,
			"collapsible": 1,
			"insert_after": _last_field(doctype),
		},
		{
			"fieldname": "ill_build_points",
			"fieldtype": "Float",
			"label": "Build Points",
			"precision": "2",
			"insert_after": "ill_build_points_section",
			"in_list_view": 0,
		},
		*extra,
	]
	previous = rows[-1]["fieldname"]
	for i, (fieldname, title) in enumerate(COUNTS):
		if i == 5:
			rows.append(
				{"fieldname": "ill_build_points_column", "fieldtype": "Column Break", "insert_after": previous}
			)
			previous = "ill_build_points_column"
		rows.append({"fieldname": fieldname, "fieldtype": count_type, "label": title, "insert_after": previous})
		previous = fieldname
	for row in rows:
		row.update({"read_only": 1, "allow_on_submit": 1, "no_copy": 1, "print_hide": 1})
		if row["fieldtype"] == "Section Break":
			row.pop("read_only")
	return rows


def _warnings(after):
	return {
		"fieldname": "ill_build_points_warnings",
		"fieldtype": "Small Text",
		"label": "Build Point Warnings",
		"insert_after": after,
	}


def execute():
	bom = _block(
		"BOM",
		"Int",
		extra=[
			{
				"fieldname": "ill_build_points_stamped",
				"fieldtype": "Check",
				"label": "Counted",
				"insert_after": "ill_build_points",
				"description": "Set once this BOM's build has been counted.",
			}
		],
		label="Build Points (per unit)",
	)
	bom.append(_warnings("ill_loose") | {"read_only": 1, "allow_on_submit": 1, "no_copy": 1, "print_hide": 1})
	order = _block(
		"Sales Order",
		"Float",
		extra=[
			{
				"fieldname": "ill_build_hours",
				"fieldtype": "Float",
				"label": "Build Hours",
				"precision": "2",
				"insert_after": "ill_build_points",
				"description": "Build points / points per person-hour (ilL-Production-Settings).",
			},
			{
				"fieldname": "ill_worth_per_point",
				"fieldtype": "Currency",
				"label": "Worth Per Point",
				"insert_after": "ill_build_hours",
				"description": "(Net total - commission) / build points.",
			},
		],
		label="Manufacturing",
	)
	order.append(_warnings("ill_loose") | {"read_only": 1, "allow_on_submit": 1, "no_copy": 1, "print_hide": 1})
	order.append(
		{
			"fieldname": "ill_estimated_ship_date",
			"fieldtype": "Date",
			"label": "Estimated Ship Date",
			"insert_after": "ill_build_points_warnings",
			"allow_on_submit": 1,
			"no_copy": 1,
			"in_standard_filter": 1,
			"description": "The day the order leaves our warehouse. Used by the production board; blank falls back to the delivery date.",
		}
	)
	create_custom_fields(
		{
			"BOM": bom,
			"Sales Order": order,
			"Sales Order Item": _block("Sales Order Item", "Float"),
			"Work Order": [
				{
					"fieldname": "ill_build_points",
					"fieldtype": "Float",
					"label": "Build Points",
					"precision": "2",
					"insert_after": "ill_configured_fixture"
					if frappe.get_meta("Work Order").has_field("ill_configured_fixture")
					else _last_field("Work Order"),
					"read_only": 1,
					"allow_on_submit": 1,
					"no_copy": 1,
				}
			],
		},
		update=True,
	)
	frappe.clear_cache()
	try:
		from illumenate_lighting.illumenate_lighting.api import build_points

		frappe.set_user("Administrator")
		print("Build points backfill:", build_points.backfill())
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Build points backfill failed during migrate")
		print("Build points backfill failed; see Error Log and run build_points.backfill by hand.")
