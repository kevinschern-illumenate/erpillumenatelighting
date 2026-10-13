"""Native Material Requests and Production Plans around the builds a Sales Order pins.

Sales Order submit already creates draft Work Orders for configured lines, and each
line pins its BOM (``ill_bom``, or ``bom_no``). ERPNext's planning tools do not know
either fact: a Production Plan counts only submitted Work Orders as covered, and
"Request for Raw Materials" explodes each Item's default BOM. These hooks keep both
tools on the pinned build and stop them from planning a second set of Work Orders.
"""

import frappe
from frappe import _


def pinned_bom(row):
	return row.get("ill_bom") or row.get("bom_no")


def default_bom(item_code):
	# The same lookup "Request for Raw Materials" uses, so the check matches what it explodes.
	from erpnext.stock.get_item_details import get_default_bom

	return get_default_bom(item_code)


def bom_mismatches(sales_order):
	"""Order lines whose Item default BOM is not the build the line pinned."""
	rows = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order, "parenttype": "Sales Order"},
		fields=["idx", "item_code", "ill_bom", "bom_no"],
		order_by="idx asc",
	)
	mismatches = []
	for row in rows:
		pinned = pinned_bom(row)
		if not pinned:
			continue
		default = default_bom(row.item_code)
		if default and default != pinned:
			mismatches.append({"idx": row.idx, "item_code": row.item_code, "pinned": pinned, "default": default})
	return mismatches


def validate_material_request(doc, method=None):
	"""A Sales Order's raw-material request must explode the builds the order pinned.

	ERPNext's "Request for Raw Materials" uses each Item's default BOM. Production
	Plan rows carry their own BOM, so requests raised from a plan are not checked.
	"""
	if doc.get("material_request_type") != "Purchase":
		return
	orders = sorted(
		{row.sales_order for row in doc.get("items") or [] if row.get("sales_order") and not row.get("production_plan")}
	)
	for order in orders:
		mismatches = bom_mismatches(order)
		if mismatches:
			lines = ", ".join(
				_("row {0} ({1}: default {2}, pinned {3})").format(m["idx"], m["item_code"], m["default"], m["pinned"])
				for m in mismatches
			)
			frappe.throw(
				_(
					"Sales Order {0} pins a different BOM than the Item default on {1}. Request materials "
					"through a Production Plan, which uses the pinned BOM, or ask Engineering to reconcile the default."
				).format(order, lines)
			)


def validate_production_plan(doc, method=None):
	"""Plan each Sales Order row with the BOM that row pinned."""
	for row in doc.get("po_items") or []:
		if not row.get("sales_order_item"):
			continue
		line = frappe.db.get_value(
			"Sales Order Item", row.sales_order_item, ["item_code", "ill_bom", "bom_no"], as_dict=True
		)
		if not line or line.item_code != row.item_code:
			continue  # Packed bundle members reference their own rows.
		pinned = pinned_bom(line)
		if pinned and row.get("bom_no") != pinned:
			row.bom_no = pinned


def guard_planned_work_order(doc, method=None):
	"""A Production Plan may plan materials, but not a second Work Order for an order line.

	Draft Work Orders created at Sales Order submit are not yet counted by ERPNext as
	covering the order, so a plan made before they are submitted would duplicate them.
	"""
	if not doc.get("production_plan") or not doc.get("sales_order"):
		return
	or_filters = {"production_item": doc.production_item}
	if doc.get("sales_order_item"):
		or_filters["sales_order_item"] = doc.sales_order_item
	existing = frappe.get_all(
		"Work Order",
		filters={
			"sales_order": doc.sales_order,
			"docstatus": ["<", 2],
			"production_plan": ["is", "not set"],
		},
		or_filters=or_filters,
		pluck="name",
		limit=1,
	)
	if existing:
		frappe.throw(
			_(
				"Sales Order {0} already has Work Order {1} for {2}. Configured builds get their Work Orders "
				"when the order is submitted; use Production Plan {3} for materials only."
			).format(doc.sales_order, existing[0], doc.production_item, doc.production_plan)
		)
