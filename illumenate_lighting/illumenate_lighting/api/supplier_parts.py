# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Supplier part numbers and descriptions, edited on Purchase Orders and RFQs, kept on the Item.

The Item's Supplier Items table (``Item Supplier``) is the source: one row per supplier with
``supplier_part_no`` and the site custom field ``custom_supplier_description``. ERPNext prints
and emails an RFQ with each supplier's part number from there, and a new PO line fetches it.

Purchase Order and Request for Quotation lines show both values (``supplier_part_no`` and
``ill_supplier_description``; see ``patches/add_supplier_part_line_fields.py``):

- On save, a blank line value is filled from the Item for the document's supplier.
- After save, a line value that differs from the Item is written back to the Item, for users
  who can edit Items. A blank line value never clears the Item; the Supplier Parts dialog can.
- An RFQ has one supplier for this when it lists exactly one. With several, its lines are
  left alone and the dialog sets the values per supplier.
"""

import json

import frappe
from frappe import _
from frappe.utils import escape_html

# Site custom field on Item Supplier, shown on the ilL Purchase Order print format.
ITEM_DESCRIPTION = "custom_supplier_description"
# The same value on a Purchase Order / RFQ line.
LINE_DESCRIPTION = "ill_supplier_description"
DOCTYPES = ("Purchase Order", "Request for Quotation")


def _clean(value) -> str:
	return "" if value is None else str(value).strip()


def _parse(value):
	return json.loads(value) if isinstance(value, str) else (value or [])


def _has_item_description() -> bool:
	return bool(frappe.get_meta("Item Supplier").has_field(ITEM_DESCRIPTION))


def _has_line_description(doctype) -> bool:
	return bool(frappe.get_meta(f"{doctype} Item").has_field(LINE_DESCRIPTION))


def _check_doctype(doctype):
	if doctype not in DOCTYPES:
		frappe.throw(_("Supplier parts are edited from a Purchase Order or Request for Quotation."))


def document_supplier(doc):
	"""The one supplier whose part numbers a document's lines carry, or None."""
	if doc.get("doctype") == "Request for Quotation":
		suppliers = {row.get("supplier") for row in doc.get("suppliers") or [] if row.get("supplier")}
		return suppliers.pop() if len(suppliers) == 1 else None
	return doc.get("supplier") or None


def item_supplier_values(supplier, codes, has_description=None) -> dict:
	"""``{item_code: {supplier_part_no, supplier_description, found}}`` from Supplier Items."""
	if has_description is None:
		has_description = _has_item_description()
	codes = [code for code in dict.fromkeys(codes) if code]
	values = {code: {"supplier_part_no": "", "supplier_description": "", "found": False} for code in codes}
	if not codes or not supplier:
		return values
	fields = ["parent", "supplier_part_no"] + ([ITEM_DESCRIPTION] if has_description else [])
	rows = frappe.get_all(
		"Item Supplier",
		filters={"parenttype": "Item", "parent": ["in", codes], "supplier": supplier},
		fields=fields,
		order_by="idx asc",
	)
	for row in rows:
		entry = values.get(row.get("parent"))
		if entry is None or entry["found"]:
			continue  # the first row per supplier is the one prints and new lines read
		entry.update(
			supplier_part_no=row.get("supplier_part_no") or "",
			supplier_description=row.get(ITEM_DESCRIPTION) or "",
			found=True,
		)
	return values


def _apply_to_item(item, supplier, part_no, description, has_description) -> bool:
	"""Set the supplier row on ``item``, adding one if needed; ``None`` leaves a value as is.

	Returns whether anything changed.
	"""
	if not has_description:
		description = None
	row = next((r for r in item.get("supplier_items") or [] if r.get("supplier") == supplier), None)
	if row is None:
		if not part_no and not description:
			return False
		values = {"supplier": supplier, "supplier_part_no": part_no or ""}
		if has_description:
			values[ITEM_DESCRIPTION] = description or ""
		item.append("supplier_items", values)
		return True
	changed = False
	if part_no is not None and _clean(row.get("supplier_part_no")) != part_no:
		row.supplier_part_no = part_no
		changed = True
	if description is not None and _clean(row.get(ITEM_DESCRIPTION)) != description:
		setattr(row, ITEM_DESCRIPTION, description)
		changed = True
	return changed


def _save_items(supplier, wanted, has_description) -> tuple[list, list]:
	"""Write ``{item_code: (part_no, description)}`` onto each Item. Returns (updated, unchanged)."""
	updated, unchanged = [], []
	for code, (part_no, description) in wanted.items():
		item = frappe.get_doc("Item", code)
		if not _apply_to_item(item, supplier, part_no, description, has_description):
			unchanged.append(code)
			continue
		try:
			item.save()
		except frappe.ValidationError as error:
			frappe.throw(_("Could not update item {0}: {1}").format(code, error))
		updated.append(code)
	return updated, unchanged


# Desk: the Supplier Parts dialog --------------------------------------------------------


@frappe.whitelist()
def get_supplier_part_info(supplier, item_codes, doctype="Purchase Order") -> dict:
	"""Each Item's part number and description for ``supplier``, from its Supplier Items rows.

	Returns ``{"has_description": bool, "items": {item_code: {...}}}``; an item with no row
	for the supplier comes back with blank values.
	"""
	_check_doctype(doctype)
	frappe.has_permission(doctype, "read", throw=True)
	supplier = _clean(supplier)
	if not supplier:
		frappe.throw(_("Choose a supplier first."))
	has_description = _has_item_description()
	codes = [_clean(code) for code in _parse(item_codes)]
	return {
		"has_description": has_description,
		"items": item_supplier_values(supplier, codes, has_description),
	}


@frappe.whitelist(methods=["POST"])
def update_supplier_part_info(supplier, rows, doctype="Purchase Order", name=None) -> dict:
	"""Save supplier part numbers and descriptions from a PO or RFQ back onto its Items.

	``rows`` is a list of ``{item_code, supplier_part_no, supplier_description}``; a blank value
	clears the Item's. Each Item's Supplier Items row for ``supplier`` is updated, or added when
	the Item has none. The user needs write access to ``doctype`` and to every Item in ``rows``;
	nothing is saved unless they can edit all of them.

	When ``name`` is a submitted Purchase Order for this supplier, its lines are corrected too,
	so a reprint shows the new values. Draft lines are updated in the form and saved with it.
	"""
	_check_doctype(doctype)
	frappe.has_permission(doctype, "write", throw=True)
	frappe.has_permission("Item", "write", throw=True)
	supplier = _clean(supplier)
	if not supplier or not frappe.db.exists("Supplier", supplier):
		frappe.throw(_("Choose a valid supplier first."))
	has_description = _has_item_description()

	wanted = {}
	for entry in _parse(rows):
		code = _clean(entry.get("item_code"))
		if code:
			wanted[code] = (
				_clean(entry.get("supplier_part_no")),
				_clean(entry.get("supplier_description")) if has_description else None,
			)

	# Check every Item before saving any, so a partial update can't happen.
	for code in wanted:
		frappe.has_permission("Item", "write", doc=code, throw=True)

	updated, unchanged = _save_items(supplier, wanted, has_description)
	lines = []
	if name and doctype == "Purchase Order":
		lines = _update_submitted_lines(name, supplier, wanted)
	return {"updated": updated, "unchanged": unchanged, "lines": lines}


def _update_submitted_lines(purchase_order, supplier, wanted) -> list:
	"""Correct a submitted PO's line values; returns the changed line names."""
	po = frappe.get_doc("Purchase Order", purchase_order)
	po.check_permission("read")
	if po.docstatus != 1 or po.supplier != supplier:
		return []
	has_line_description = _has_line_description("Purchase Order")
	changed, notes = [], []
	for line in po.get("items") or []:
		if line.item_code not in wanted:
			continue
		part_no, description = wanted[line.item_code]
		values = {}
		before = _clean(line.get("supplier_part_no"))
		if before != part_no:
			values["supplier_part_no"] = part_no
			notes.append(f"{line.item_code}: {before or '—'} → {part_no or '—'}")
		if (
			has_line_description
			and description is not None
			and _clean(line.get(LINE_DESCRIPTION)) != description
		):
			values[LINE_DESCRIPTION] = description
		if values:
			frappe.db.set_value("Purchase Order Item", line.name, values, update_modified=False)
			changed.append(line.name)
	if notes:
		po.add_comment(
			"Info",
			_("Supplier part numbers updated after submit: {0}").format(
				", ".join(escape_html(note) for note in dict.fromkeys(notes))
			),
		)
	return changed


# Document events on Purchase Order and Request for Quotation ---------------------------


def fill_line_supplier_parts(doc, method=None):
	"""validate: fill each line's blank part number / description from the Item."""
	if doc.get("docstatus") != 0:
		return
	supplier = document_supplier(doc)
	lines = [line for line in doc.get("items") or [] if line.get("item_code")]
	if not supplier or not lines:
		return
	has_line_description = _has_line_description(doc.doctype)
	needs = [
		line
		for line in lines
		if not _clean(line.get("supplier_part_no"))
		or (has_line_description and not _clean(line.get(LINE_DESCRIPTION)))
	]
	if not needs:
		return
	saved = item_supplier_values(supplier, [line.item_code for line in needs])
	for line in needs:
		values = saved.get(line.item_code) or {}
		if not _clean(line.get("supplier_part_no")) and values.get("supplier_part_no"):
			line.supplier_part_no = values["supplier_part_no"]
		if (
			has_line_description
			and not _clean(line.get(LINE_DESCRIPTION))
			and values.get("supplier_description")
		):
			setattr(line, LINE_DESCRIPTION, values["supplier_description"])


def save_line_supplier_parts(doc, method=None):
	"""on_update: write line values that differ from the Item back onto the Item.

	Skipped for Items the user cannot edit (the values stay on the document, and a message
	says which Items were not updated).
	"""
	if doc.get("docstatus") != 0 or doc.flags.get("ill_skip_supplier_parts"):
		return
	supplier = document_supplier(doc)
	lines = [line for line in doc.get("items") or [] if line.get("item_code")]
	if not supplier or not lines:
		return
	has_item_description = _has_item_description()
	has_line_description = has_item_description and _has_line_description(doc.doctype)

	wanted = {}
	for line in lines:
		part_no = _clean(line.get("supplier_part_no")) or None
		description = (_clean(line.get(LINE_DESCRIPTION)) or None) if has_line_description else None
		if part_no is None and description is None:
			continue
		# The first line wins when an item appears twice with different values.
		wanted.setdefault(line.item_code, (part_no, description))
	if not wanted:
		return

	saved = item_supplier_values(supplier, list(wanted), has_item_description)
	changes = {}
	for code, (part_no, description) in wanted.items():
		current = saved.get(code) or {}
		part_no = part_no if part_no is not None and part_no != current.get("supplier_part_no") else None
		if description is not None and description == current.get("supplier_description"):
			description = None
		if part_no is not None or description is not None:
			changes[code] = (part_no, description)
	if not changes:
		return

	allowed = {
		code: value for code, value in changes.items() if frappe.has_permission("Item", "write", doc=code)
	}
	skipped = [code for code in changes if code not in allowed]
	if allowed:
		_save_items(supplier, allowed, has_item_description)
		frappe.msgprint(
			_("Saved supplier part details to {0} item(s) for {1}: {2}").format(
				len(allowed), escape_html(supplier), escape_html(", ".join(allowed))
			),
			alert=True,
			indicator="green",
		)
	if skipped:
		frappe.msgprint(
			_(
				"You can't edit these items, so their supplier part details were not saved to the Item: {0}"
			).format(escape_html(", ".join(skipped))),
			indicator="orange",
		)
