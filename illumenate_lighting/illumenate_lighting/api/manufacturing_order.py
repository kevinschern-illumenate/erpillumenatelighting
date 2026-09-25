"""Create demand-scoped draft Work Orders from verified, pinned order builds."""

import html

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import assert_bom, atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import finite_number

SOURCES = (
	("ill_configured_group", "ilL-Configured-Group", "fixture_group_bom"),
	("ill_configured_fixture", "ilL-Configured-Fixture", "linear_build"),
	("ill_configured_tape_neon", "ilL-Configured-Tape-Neon", "tape_neon_build"),
	("ill_configured_led_sheet", "ilL-Configured-LED-Sheet", "led_sheet_bundle"),
)


def pinned_build(row):
	from importlib import import_module

	for field, doctype, module in SOURCES:
		if not row.get(field):
			continue
		doc = frappe.get_doc(doctype, row.get(field))
		if (
			doctype != "ilL-Configured-Group"
			and doc.get("build_schema_version") != 2
			and doc.get("engine_version") != "led-sheet-2"
		):
			return None  # Historical single fixtures retain their existing adapter.
		build = import_module("illumenate_lighting.illumenate_lighting.api." + module).snapshot(doc)
		if row.item_code != doc.configured_item or (row.get("ill_bom") or row.get("bom_no")) != doc.bom:
			raise ValueError("Order Item/BOM must match its pinned configured build")
		assert_bom(row.item_code, build["components"], frappe.get_doc("BOM", doc.bom))
		return doc, build
	return None


def traveler(build):
	"""All dimensions and physical cable pieces remain visible after BOM aggregation."""
	parts = [
		"Pinned manufacturing instructions. Quantities below are for one complete build; multiply by Work Order quantity."
	]
	members = build.get("members") or [{"member_key": "Fixture", "build": build}]
	for member in members:
		value = member["build"]
		parts.append(member["member_key"])
		computed = value.get("computed") or value
		for segment in computed.get("segments") or computed.get("user_segments") or []:
			length = segment.get("manufacturable_length_mm") or segment.get(
				"manufacturable_overall_length_mm"
			)
			parts.append(
				f"Segment {segment.get('segment_index', '')}: manufactured length {length} mm; end {segment.get('end_type', '')}"
			)
		if value.get("panels_needed"):
			parts.append(
				f"Area {value.get('coverage_width_ft')} x {value.get('coverage_height_ft')} ft; {value['panels_needed']} panels"
			)
		for cable in value.get("cables", []):
			parts.append(
				f"{cable.get('role', 'Cable')} / segment {cable.get('segment', '')}: {cable.get('item_code', '')}; cut {cable.get('length_mm')} mm"
			)
		for group in value.get("groups", []):
			parts.append(
				f"Feed {group.get('group_number')}: {group.get('sheet_count')} panels; {group.get('group_watts')} W; one leader"
			)
	plan = build.get("power_plan") or (build.get("resolved_items") or {}).get("driver_plan") or {}
	parts.append(
		"External power required" if plan.get("status") == "excluded" else "Included power allocation"
	)
	for row in plan.get("allocations", []):
		parts.append(
			f"Circuit {row['run_key']}: {row['watts']} W -> supply {row['supply']} ({row['item_code']}), output {row['output']}"
		)
	return "<br>".join(html.escape(str(p)) for p in parts)


@atomic_build
def create_for_line(order, row):
	"""Caller holds the Sales Order lock. Existing draft demand also counts as covered."""
	pinned = pinned_build(row)
	if pinned is None:
		return None
	doc, build = pinned
	qty = finite_number(row.qty, minimum=1, field="complete build quantity")
	if not qty.is_integer() or float(row.get("conversion_factor") or 1) != 1:
		raise ValueError("Configured builds require whole quantities in their stock UOM")
	existing = frappe.get_all(
		"Work Order",
		filters={"sales_order": order.name, "sales_order_item": row.name, "docstatus": ["<", 2]},
		fields=["name", "production_item", "bom_no", "qty", "status"],
	)
	if any(
		w.production_item != row.item_code or w.bom_no != doc.bom or w.status == "Stopped" for w in existing
	):
		raise ValueError(
			"Existing production differs or is stopped; Manufacturing must reconcile this order line"
		)
	remaining = qty - sum(float(w.qty) for w in existing)
	if remaining < 0:
		raise ValueError("Planned production exceeds this order line; Manufacturing must reconcile demand")
	if remaining == 0:
		return {
			"success": True,
			"created": {"work_order": False},
			"work_orders": [w.name for w in existing],
			"messages": [],
		}
	field = next(field for field, doctype, _ in SOURCES if doctype == doc.doctype)
	data = {
		"doctype": "Work Order",
		"company": order.company,
		"production_item": row.item_code,
		"bom_no": doc.bom,
		"qty": remaining,
		"use_multi_level_bom": 0,
		"sales_order": order.name,
		"sales_order_item": row.name,
		"remarks": traveler(build),
	}
	if frappe.get_meta("Work Order").has_field(field):
		data[field] = doc.name
	work = frappe.get_doc(data)
	work.insert(ignore_permissions=True)
	return {"success": True, "created": {"work_order": True}, "work_orders": [work.name], "messages": []}
