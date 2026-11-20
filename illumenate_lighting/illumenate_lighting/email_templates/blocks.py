# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""HTML pieces every email reuses: line tables, buttons, the signature. No Frappe imports.

Templates keep the wording; these keep the markup. Each returns "" when it has nothing
to show, so a template can print ``{{ c.blocks.lines }}`` without an ``{% if %}``.
Styles are inline because most mail clients drop <style> blocks.

Tables must also survive the Desk composer's rich-text editor (Quill), which takes over
the email when someone switches "Use HTML editor" off, and whatever it shows is what gets
sent. Quill has no header cells and makes a new cell at every line break, so:

- header rows are ``<td>`` cells with ``<strong>`` text (``_head``), never ``<th>``:
  Quill runs every ``<th>`` of a row together into one cell;
- a cell holds one line: no ``<br>``, ``<div>`` or ``<p>`` inside a ``<td>``, or the row
  gains cells and its columns shift;
- templates never put one table straight after another: Quill joins them into one table.
"""

from html import escape

TABLE = 'style="border-collapse:collapse;width:100%;max-width:640px;margin:8px 0 16px;font-size:14px"'
TH = 'style="text-align:left;padding:6px 8px;border-bottom:2px solid #d1d5db;color:#374151;font-weight:600"'
TH_RIGHT = (
	'style="text-align:right;padding:6px 8px;border-bottom:2px solid #d1d5db;color:#374151;font-weight:600"'
)
TD = 'style="padding:6px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top"'
TD_RIGHT = 'style="padding:6px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top;text-align:right;white-space:nowrap"'
MUTED = 'style="color:#6b7280;font-size:12px"'
BUTTON = (
	'style="display:inline-block;padding:10px 20px;background:#111827;color:#ffffff;'
	'text-decoration:none;border-radius:4px;font-weight:600"'
)


def e(value):
	return escape(str(value)) if value not in (None, "") else ""


def button(url, label):
	"""A call-to-action link styled as a button; "" without a URL."""
	if not url:
		return ""
	return f'<p style="margin:16px 0"><a href="{e(url)}" {BUTTON}>{e(label)}</a></p>'


def link(url, label):
	if not url:
		return ""
	return f'<a href="{e(url)}">{e(label)}</a>'


def _more(count, where="the PDF"):
	if not count:
		return ""
	noun = "line" if count == 1 else "lines"
	return f"<p {MUTED}>…and {count} more {noun} in {e(where)}.</p>"


def _head(*columns):
	"""The header row: ``columns`` are labels, or (label, "right") for a right-aligned one.

	Bold ``<td>`` cells rather than ``<th>``, which Quill runs together into one cell.
	"""
	cells = []
	for column in columns:
		label, align = column if isinstance(column, tuple) else (column, "left")
		style = TH_RIGHT if align == "right" else TH
		cells.append(f"<td {style}><strong>{e(label)}</strong></td>")
	return f"<tr>{''.join(cells)}</tr>"


def _with_detail(main, detail):
	"""Bold text with a muted detail after it, on the same line (a cell holds one line)."""
	main = f"<strong>{e(main)}</strong>"
	return f"{main} <span {MUTED}>&middot; {e(detail)}</span>" if detail else main


def _label_cell(line):
	return _with_detail(line.get("label"), line.get("detail"))


def lines_table(lines, more=0, amounts=True):
	"""Item summary for quotes, orders and invoices."""
	if not lines:
		return ""
	head = _head("Item", ("Qty", "right"), *([("Amount", "right")] if amounts else []))
	rows = []
	for line in lines:
		qty = f"{e(line.get('qty'))} {e(line.get('uom'))}".strip()
		row = f"<tr><td {TD}>{_label_cell(line)}</td><td {TD_RIGHT}>{qty}</td>"
		row += f"<td {TD_RIGHT}>{e(line.get('amount'))}</td></tr>" if amounts else "</tr>"
		rows.append(row)
	return f"<table {TABLE}>{head}{''.join(rows)}</table>" + _more(more)


def supplier_lines_table(lines, more=0, amounts=True):
	"""Purchase Order / RFQ lines: our item code, the supplier's part number, qty, required-by date."""
	if not lines:
		return ""
	head = _head(
		"Item",
		"Your part #",
		("Qty", "right"),
		("Needed by", "right"),
		*([("Rate", "right")] if amounts else []),
	)
	rows = []
	for line in lines:
		code, label = line.get("item_code"), line.get("label")
		item = _with_detail(code, label if label and label != code else "")
		qty = f"{e(line.get('qty'))} {e(line.get('uom'))}".strip()
		rows.append(
			f"<tr><td {TD}>{item}</td><td {TD}>{e(line.get('supplier_part_no'))}</td>"
			f"<td {TD_RIGHT}>{qty}</td><td {TD_RIGHT}>{e(line.get('required_by'))}</td>"
			+ (f"<td {TD_RIGHT}>{e(line.get('rate'))}</td>" if amounts else "")
			+ "</tr>"
		)
	return f"<table {TABLE}>{head}{''.join(rows)}</table>" + _more(more)


def packing_table(lines, more=0):
	"""What is in the box: no prices."""
	return lines_table(lines, more, amounts=False)


def schedule_table(rows):
	"""Payment schedule rows: [{label, due_date, amount, outstanding}]."""
	if not rows:
		return ""
	head = _head("Payment", "Due", ("Amount", "right"), ("Still due", "right"))
	body = "".join(
		f"<tr><td {TD}>{e(r.get('label'))}</td><td {TD}>{e(r.get('due_date'))}</td>"
		f"<td {TD_RIGHT}>{e(r.get('amount'))}</td><td {TD_RIGHT}>{e(r.get('outstanding'))}</td></tr>"
		for r in rows
	)
	return f"<table {TABLE}>{head}{body}</table>"


def payments_table(rows):
	"""Payments received: [{date, amount, method, reference}]."""
	if not rows:
		return ""
	head = _head("Date", "Method", "Reference", ("Amount", "right"))
	body = "".join(
		f"<tr><td {TD}>{e(r.get('date'))}</td><td {TD}>{e(r.get('method'))}</td>"
		f"<td {TD}>{e(r.get('reference'))}</td><td {TD_RIGHT}>{e(r.get('amount'))}</td></tr>"
		for r in rows
	)
	return f"<table {TABLE}>{head}{body}</table>"


def applied_table(rows):
	"""Where a payment went: [{label, amount, balance}]."""
	if not rows:
		return ""
	head = _head("Applied to", ("Amount", "right"), ("Balance now", "right"))
	body = "".join(
		f"<tr><td {TD}>{e(r.get('label'))}</td><td {TD_RIGHT}>{e(r.get('amount'))}</td>"
		f"<td {TD_RIGHT}>{e(r.get('balance'))}</td></tr>"
		for r in rows
	)
	return f"<table {TABLE}>{head}{body}</table>"


def rejected_table(rows):
	"""Purchase Receipt lines with a rejected quantity."""
	if not rows:
		return ""
	head = _head("Item", "Our PO", ("Received", "right"), ("Accepted", "right"), ("Rejected", "right"))
	body = "".join(
		f"<tr><td {TD}>"
		+ _with_detail(
			r.get("item_code"),
			r.get("label") if r.get("label") and r.get("label") != r.get("item_code") else "",
		)
		+ f"</td><td {TD}>{e(r.get('purchase_order'))}</td>"
		f"<td {TD_RIGHT}>{e(r.get('received'))} {e(r.get('uom'))}</td>"
		f"<td {TD_RIGHT}>{e(r.get('accepted'))}</td><td {TD_RIGHT}>{e(r.get('rejected'))}</td></tr>"
		for r in rows
	)
	return f"<table {TABLE}>{head}{body}</table>"


def tracking(shipment):
	"""Carrier and tracking number, the number linked when the carrier has a tracking page."""
	carrier, number, url = shipment.get("carrier"), shipment.get("number"), shipment.get("url")
	if not carrier and not number:
		return ""
	parts = []
	if carrier:
		parts.append(f"<strong>Carrier:</strong> {e(carrier)}")
	if number:
		shown = link(url, number) if url else e(number)
		parts.append(f"<strong>Tracking number:</strong> {shown}")
	return "<p>" + "<br>".join(parts) + "</p>"


def signature(poc, company="ilLumenate Lighting"):
	"""Sign-off with the point of contact's name, title, email and phone."""
	name = e(poc.get("name"))
	lines = [name] if name else []
	if poc.get("title"):
		lines.append(e(poc["title"]))
	lines.append(e(company or "ilLumenate Lighting"))
	if poc.get("email"):
		lines.append(link(f"mailto:{poc['email']}", poc["email"]))
	if poc.get("phone"):
		lines.append(e(poc["phone"]))
	return "<p>Thank you,<br>" + "<br>".join(lines) + "</p>"


def address(html):
	"""An address block that is already HTML (Frappe's rendered address_display)."""
	if not html:
		return ""
	return f'<p style="margin:4px 0 16px;padding-left:12px;border-left:3px solid #e5e7eb">{html}</p>'
