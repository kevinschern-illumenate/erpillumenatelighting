# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""HTML pieces every email reuses: line tables, buttons, the signature. No Frappe imports.

Templates keep the wording; these keep the markup. Each returns "" when it has nothing
to show, so a template can print ``{{ c.blocks.lines }}`` without an ``{% if %}``.
Styles are inline because most mail clients drop <style> blocks.
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


def _label_cell(line):
	label = e(line.get("label"))
	detail = e(line.get("detail"))
	return f"<strong>{label}</strong>" + (f"<br><span {MUTED}>{detail}</span>" if detail else "")


def lines_table(lines, more=0, amounts=True):
	"""Item summary for quotes, orders and invoices."""
	if not lines:
		return ""
	head = f"<tr><th {TH}>Item</th><th {TH_RIGHT}>Qty</th>"
	head += f"<th {TH_RIGHT}>Amount</th></tr>" if amounts else "</tr>"
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
	head = (
		f"<tr><th {TH}>Item</th><th {TH}>Your part #</th><th {TH_RIGHT}>Qty</th>"
		f"<th {TH_RIGHT}>Needed by</th>" + (f"<th {TH_RIGHT}>Rate</th>" if amounts else "") + "</tr>"
	)
	rows = []
	for line in lines:
		code = e(line.get("item_code"))
		label = e(line.get("label"))
		item = f"<strong>{code}</strong>" + (
			f"<br><span {MUTED}>{label}</span>" if label and label != code else ""
		)
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
	head = (
		f"<tr><th {TH}>Payment</th><th {TH}>Due</th><th {TH_RIGHT}>Amount</th>"
		f"<th {TH_RIGHT}>Still due</th></tr>"
	)
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
	head = f"<tr><th {TH}>Date</th><th {TH}>Method</th><th {TH}>Reference</th><th {TH_RIGHT}>Amount</th></tr>"
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
	head = f"<tr><th {TH}>Applied to</th><th {TH_RIGHT}>Amount</th><th {TH_RIGHT}>Balance now</th></tr>"
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
	head = (
		f"<tr><th {TH}>Item</th><th {TH}>Our PO</th><th {TH_RIGHT}>Received</th>"
		f"<th {TH_RIGHT}>Accepted</th><th {TH_RIGHT}>Rejected</th></tr>"
	)
	body = "".join(
		f"<tr><td {TD}><strong>{e(r.get('item_code'))}</strong>"
		+ (
			f"<br><span {MUTED}>{e(r.get('label'))}</span>"
			if r.get("label") and r.get("label") != r.get("item_code")
			else ""
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
