# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import escape_html

# Site custom field on Item Supplier, shown on the ilL Purchase Order print format.
SUPPLIER_DESCRIPTION = "custom_supplier_description"


def allow_blank_schedule_date(doc, method=None):
	"""Suppress ERPNext's BuyingController.validate_schedule_date() so that
	Purchase Orders can be saved and submitted without a 'Required By' date.

	The Property Setter patch (make_po_schedule_date_optional) removes the UI
	red asterisk; this hook prevents the identical server-side check from
	throwing a validation error when the field is blank.
	"""
	doc.validate_schedule_date = lambda: None


def _has_description_field() -> bool:
	return bool(frappe.get_meta("Item Supplier").has_field(SUPPLIER_DESCRIPTION))


def _clean(value) -> str:
	return "" if value is None else str(value).strip()


def _parse(value):
	return json.loads(value) if isinstance(value, str) else (value or [])


@frappe.whitelist()
def get_supplier_part_info(supplier, item_codes) -> dict:
	"""Each Item's part number and description for ``supplier``, from its Supplier Items rows.

	Returns ``{"has_description": bool, "items": {item_code: {...}}}``; an item with no row
	for the supplier comes back with blank values.
	"""
	frappe.has_permission("Purchase Order", "read", throw=True)
	codes = [code for code in dict.fromkeys(_clean(code) for code in _parse(item_codes)) if code]
	supplier = _clean(supplier)
	if not supplier:
		frappe.throw(_("Choose a supplier first."))
	has_description = _has_description_field()
	items = {code: {"supplier_part_no": "", "supplier_description": "", "found": False} for code in codes}
	if codes:
		fields = ["parent", "supplier_part_no"] + ([SUPPLIER_DESCRIPTION] if has_description else [])
		rows = frappe.get_all(
			"Item Supplier",
			filters={"parenttype": "Item", "parent": ["in", codes], "supplier": supplier},
			fields=fields,
			order_by="idx asc",
		)
		for row in rows:
			entry = items.get(row.get("parent"))
			if entry is None or entry["found"]:
				continue  # the first row per supplier is the one the print format reads
			entry.update(
				supplier_part_no=row.get("supplier_part_no") or "",
				supplier_description=row.get(SUPPLIER_DESCRIPTION) or "",
				found=True,
			)
	return {"has_description": has_description, "items": items}


def _apply_to_item(item, supplier, part_no, description, has_description) -> bool:
	"""Set the supplier row on ``item`` (adding one if needed). Returns whether anything changed."""
	row = next((r for r in item.get("supplier_items") or [] if r.get("supplier") == supplier), None)
	if row is None:
		if not part_no and not description:
			return False
		values = {"supplier": supplier, "supplier_part_no": part_no}
		if has_description:
			values[SUPPLIER_DESCRIPTION] = description
		item.append("supplier_items", values)
		return True
	changed = False
	if _clean(row.get("supplier_part_no")) != part_no:
		row.supplier_part_no = part_no
		changed = True
	if has_description and _clean(row.get(SUPPLIER_DESCRIPTION)) != description:
		setattr(row, SUPPLIER_DESCRIPTION, description)
		changed = True
	return changed


@frappe.whitelist(methods=["POST"])
def update_supplier_part_info(supplier, rows, purchase_order=None) -> dict:
	"""Save supplier part numbers and descriptions from a Purchase Order back onto its Items.

	``rows`` is a list of ``{item_code, supplier_part_no, supplier_description}``. Each Item's
	Supplier Items row for ``supplier`` is updated, or added when the Item has none. Buyers
	who can write Purchase Orders may do this without write access to Items.

	When ``purchase_order`` is a submitted PO for this supplier, its lines' Supplier Part
	Number is corrected too, so a reprint shows the new number. Draft lines are updated in
	the form instead and saved with the PO.
	"""
	frappe.has_permission("Purchase Order", "write", throw=True)
	supplier = _clean(supplier)
	if not supplier or not frappe.db.exists("Supplier", supplier):
		frappe.throw(_("Choose a valid supplier first."))
	has_description = _has_description_field()

	wanted = {}
	for entry in _parse(rows):
		code = _clean(entry.get("item_code"))
		if code:
			wanted[code] = (
				_clean(entry.get("supplier_part_no")),
				_clean(entry.get("supplier_description")) if has_description else "",
			)

	updated, unchanged = [], []
	for code, (part_no, description) in wanted.items():
		frappe.has_permission("Item", "read", doc=code, throw=True)
		item = frappe.get_doc("Item", code)
		if not _apply_to_item(item, supplier, part_no, description, has_description):
			unchanged.append(code)
			continue
		item.flags.ignore_permissions = True
		try:
			item.save()
		except frappe.ValidationError as error:
			frappe.throw(_("Could not update item {0}: {1}").format(code, error))
		updated.append(code)

	lines = _update_submitted_lines(purchase_order, supplier, wanted) if purchase_order else []
	return {"updated": updated, "unchanged": unchanged, "lines": lines}


def _update_submitted_lines(purchase_order, supplier, wanted) -> list:
	"""Correct Supplier Part Number on a submitted PO's lines; returns the changed line names."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	if po.docstatus != 1 or po.supplier != supplier:
		return []
	changed, notes = [], []
	for line in po.get("items") or []:
		if line.item_code not in wanted:
			continue
		part_no = wanted[line.item_code][0]
		before = _clean(line.get("supplier_part_no"))
		if before == part_no:
			continue
		frappe.db.set_value(
			"Purchase Order Item", line.name, "supplier_part_no", part_no, update_modified=False
		)
		changed.append(line.name)
		notes.append(f"{line.item_code}: {before or '—'} → {part_no or '—'}")
	if notes:
		po.add_comment(
			"Info",
			_("Supplier part numbers updated after submit: {0}").format(
				", ".join(escape_html(note) for note in dict.fromkeys(notes))
			),
		)
	return changed
