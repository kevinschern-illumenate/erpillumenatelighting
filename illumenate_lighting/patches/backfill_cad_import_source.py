# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Draw-to-quote WP 1.1/1.3: fill the source and scale fields on drawing imports made before them.

``toolkit_version`` ``dxf-1`` marks a DXF upload; every other package came from the AutoCAD toolkit.
The scale status is read from the stored package the same way the import computes it now. Only blank
``source_tool`` rows are touched, so a rerun changes nothing.
"""

import json

import frappe

DOCTYPE = "ilL-CAD-Import"


def source_fields(toolkit_version, package_json):
	from illumenate_lighting.illumenate_lighting.portal.drawing_import import scale_summary
	from illumenate_lighting.illumenate_lighting.system_design.ilq_schema import derived_source

	try:
		package = json.loads(package_json or "{}")
	except ValueError:
		package = {}
	package.setdefault("toolkit", {"version": toolkit_version or ""})
	source = package.get("source") or derived_source(package)
	package.setdefault("runs", [])
	package.setdefault("drawing", {})
	return {
		"source_tool": source["tool"],
		"source_version": (source.get("version") or "")[:140],
		"source_platform": (source.get("platform") or "")[:140],
		"source_input": source["input"],
		"scale_status": scale_summary(package)["status"],
	}


def execute():
	if not frappe.db.exists("DocType", DOCTYPE) or not frappe.get_meta(DOCTYPE).has_field("source_tool"):
		return 0
	rows = frappe.get_all(
		DOCTYPE,
		filters=[["source_tool", "in", ["", None]]],
		fields=["name", "toolkit_version", "package_json"],
	)
	for row in rows:
		frappe.db.set_value(
			DOCTYPE, row.name, source_fields(row.toolkit_version, row.package_json), update_modified=False
		)
	frappe.db.commit()
	return len(rows)
