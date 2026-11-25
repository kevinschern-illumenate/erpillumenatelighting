# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Supplier part numbers and descriptions, edited from purchasing and sales documents, kept on the Item.

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

The Supplier Parts dialog is also on the documents in ``ITEM_ONLY_DOCTYPES`` (Material Request,
Quotation, Sales Order, ...). Their lines carry no supplier values, so the dialog only reads and
writes the Items, for a supplier the user picks (``get_item_suppliers`` suggests the ones already
set on those Items) or the document's own supplier.
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
# Documents whose Supplier Parts dialog edits the Items only; their lines are left alone.
ITEM_ONLY_DOCTYPES = (
	"Material Request",
	"Quotation",
	"Sales Order",
	"Supplier Quotation",
	"Purchase Receipt",
	"Purchase Invoice",
)
# Rolls back one Item's failed save when a PO / RFQ save writes line values back to its Items.
ITEM_SAVEPOINT = "supplier_parts_item"


def _clean(value) -> str:
	return "" if value is None else str(value).strip()


def _parse(value):
	return json.loads(value) if isinstance(value, str) else (value or [])


def _has_item_description() -> bool:
	return bool(frappe.get_meta("Item Supplier").has_field(ITEM_DESCRIPTION))


def _has_line_description(doctype) -> bool:
	return bool(frappe.get_meta(f"{doctype} Item").has_field(LINE_DESCRIPTION))


def _check_doctype(doctype):
	if doctype not in DOCTYPES and doctype not in ITEM_ONLY_DOCTYPES:
		frappe.throw(_("Supplier parts can't be edited from a {0}.").format(doctype))


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


def _save_items(supplier, wanted, has_description, failed=None) -> tuple[list, list]:
	"""Write ``{item_code: (part_no, description)}`` onto each Item. Returns (updated, unchanged).

	An Item that fails validation stops the call, unless ``failed`` is a list: then that Item's
	save is rolled back to a savepoint, its error messages are dropped, ``(item_code, reason)``
	is added to ``failed`` and the other Items are still saved.
	"""
	updated, unchanged = [], []
	for code, (part_no, description) in wanted.items():
		item = frappe.get_doc("Item", code)
		if not _apply_to_item(item, supplier, part_no, description, has_description):
			unchanged.append(code)
			continue
		if failed is None:
			try:
				item.save()
			except frappe.ValidationError as error:
				frappe.throw(_("Could not update item {0}: {1}").format(code, error))
			updated.append(code)
			continue
		messages = getattr(frappe.local, "message_log", None)
		mark = len(messages) if messages is not None else 0
		frappe.db.savepoint(ITEM_SAVEPOINT)
		try:
			item.save()
		except frappe.ValidationError as error:
			frappe.db.rollback(save_point=ITEM_SAVEPOINT)
			if messages is not None:
				del messages[mark:]  # the summary message names it instead of a raw error
			failed.append((code, _clean(error) or type(error).__name__))
			continue
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
		"supplier_name": frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier,
		"items": item_supplier_values(supplier, codes, has_description),
	}


@frappe.whitelist()
def get_item_suppliers(item_codes, doctype="Sales Order") -> list:
	"""The suppliers already set on these Items, most items first.

	Reads each Item's Supplier Items rows and its default supplier (Item Defaults). Returns
	``[{supplier, supplier_name, items}]``, where ``items`` counts the Items that name it; the
	Supplier Parts dialog offers these when the document has no supplier of its own.
	"""
	_check_doctype(doctype)
	frappe.has_permission(doctype, "read", throw=True)
	codes = [code for code in dict.fromkeys(_clean(code) for code in _parse(item_codes)) if code]
	if not codes:
		return []
	found = {}  # supplier -> item codes, in first-seen order
	rows = frappe.get_all(
		"Item Supplier",
		filters={"parenttype": "Item", "parent": ["in", codes]},
		fields=["parent", "supplier"],
		order_by="idx asc",
	)
	defaults = frappe.get_all(
		"Item Default",
		filters={"parenttype": "Item", "parent": ["in", codes], "default_supplier": ["is", "set"]},
		fields=["parent", "default_supplier as supplier"],
	)
	for row in [*rows, *defaults]:
		if row.get("supplier"):
			found.setdefault(row["supplier"], set()).add(row.get("parent"))
	if not found:
		return []
	names = {
		row.get("name"): row.get("supplier_name")
		for row in frappe.get_all(
			"Supplier", filters={"name": ["in", list(found)]}, fields=["name", "supplier_name"]
		)
	}
	order = list(found)
	result = [
		{"supplier": supplier, "supplier_name": names.get(supplier) or supplier, "items": len(parents)}
		for supplier, parents in found.items()
	]
	result.sort(key=lambda entry: (-entry["items"], order.index(entry["supplier"])))
	return result


@frappe.whitelist(methods=["POST"])
def update_supplier_part_info(supplier, rows, doctype="Purchase Order", name=None) -> dict:
	"""Save supplier part numbers and descriptions from a PO or RFQ back onto its Items.

	``rows`` is a list of ``{item_code, supplier_part_no, supplier_description}``; a blank value
	clears the Item's. Each Item's Supplier Items row for ``supplier`` is updated, or added when
	the Item has none. The user needs write access to every Item in ``rows`` (nothing is saved
	unless they can edit all of them), and to ``doctype`` when it is a Purchase Order or RFQ;
	from the documents in ``ITEM_ONLY_DOCTYPES``, read access to it is enough.

	When ``name`` is a submitted Purchase Order for this supplier, its lines are corrected too,
	so a reprint shows the new values. Draft lines are updated in the form and saved with it.
	"""
	_check_doctype(doctype)
	frappe.has_permission(doctype, "write" if doctype in DOCTYPES else "read", throw=True)
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

	Skipped for Items the user cannot edit or that fail to save (the values stay on the
	document, and one message lists the Items not updated with the reason). A failing Item
	never stops the document's own save.
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
	# (item_code, reason): Items left as they are. The document's own save always goes ahead.
	skipped = [(code, _("you can't edit this item")) for code in changes if code not in allowed]
	if allowed:
		failed = []
		_save_items(supplier, allowed, has_item_description, failed)
		skipped.extend(failed)
		saved = [code for code in allowed if code not in dict(failed)]
		if saved:
			frappe.msgprint(
				_("Saved supplier part details to {0} item(s) for {1}: {2}").format(
					len(saved), escape_html(supplier), escape_html(", ".join(saved))
				),
				alert=True,
				indicator="green",
			)
	if skipped:
		frappe.msgprint(
			_(
				"These items were not updated, so their supplier part details are saved on this document only: {0}"
			).format(escape_html("; ".join(f"{code} ({reason})" for code, reason in skipped))),
			indicator="orange",
		)
