# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Keep the email tables whole in the Desk composer's rich-text editor.

Switching "Use HTML editor" off hands the email to Quill, which joins two tables that
touch into one (email_templates/blocks.py lists the rules). Four shipped templates had a
table straight after another; this puts a caption between them on the site's copies,
skips a details table that would have no rows, and turns the RFQ's two-row terms table
into a paragraph. The header-cell and line-break fixes live in blocks.py and need no patch.

A template changes only when every shipped snippet is still in it exactly once, so a
copy staff have edited is left alone rather than half-changed. Draft RFQs whose message
was copied from the RFQ template get the same change.
"""

import frappe

RFQ_TEMPLATE = "ilL - Request for Quotation - Request"

_ITEMS = "<p><strong>Items</strong></p>"
_SCHEDULE = "<p><strong>Payment schedule</strong></p>"
_FACTS_TABLE = '<table style="border-collapse:collapse;margin:8px 0 16px;font-size:14px">\n'

REPLACEMENTS = {
	"ilL - Purchase Order - Send to supplier": (
		(
			_FACTS_TABLE + "{% if c.purchase.required_by %}",
			"{% if c.purchase.required_by or c.purchase.incoterm or c.purchase.freight_mode "
			"or c.purchase.payment_terms %}\n" + _FACTS_TABLE + "{% if c.purchase.required_by %}",
		),
		(
			"</table>\n{{ c.blocks.supplier_lines }}\n{{ c.blocks.purchase_schedule }}\n",
			"</table>\n{% endif %}\n"
			"{% if c.blocks.supplier_lines %}" + _ITEMS + "{{ c.blocks.supplier_lines }}{% endif %}\n"
			"{% if c.blocks.purchase_schedule %}"
			+ _SCHEDULE
			+ "{{ c.blocks.purchase_schedule }}{% endif %}\n",
		),
	),
	"ilL - Sales Invoice - Invoice": (
		(
			"{{ c.blocks.invoice_schedule }}\n",
			"{% if c.blocks.invoice_schedule %}" + _SCHEDULE + "{{ c.blocks.invoice_schedule }}{% endif %}\n",
		),
	),
	"ilL - Sales Order - Order confirmation": (
		(
			"{{ c.blocks.order_schedule }}\n",
			"{% if c.blocks.order_schedule %}" + _SCHEDULE + "{{ c.blocks.order_schedule }}{% endif %}\n",
		),
		(
			"{{ c.blocks.lines }}\n",
			"{% if c.blocks.lines %}" + _ITEMS + "{{ c.blocks.lines }}{% endif %}\n",
		),
	),
	RFQ_TEMPLATE: (
		(
			_FACTS_TABLE
			+ '{% if c.rfq.incoterm %}<tr><td style="padding:4px 16px 4px 0;color:#6b7280">Incoterm</td>'
			'<td style="padding:4px 0">{{ c.rfq.incoterm }}{% if c.rfq.named_place %} {{ c.rfq.named_place }}'
			"{% endif %}</td></tr>{% endif %}\n"
			'{% if c.rfq.reply_by %}<tr><td style="padding:4px 16px 4px 0;color:#6b7280">Please reply by</td>'
			'<td style="padding:4px 0"><strong>{{ c.rfq.reply_by }}</strong></td></tr>{% endif %}\n'
			"</table>\n",
			"{% if c.rfq.incoterm or c.rfq.reply_by %}<p>"
			'{% if c.rfq.incoterm %}<span style="color:#6b7280">Incoterm:</span> {{ c.rfq.incoterm }}'
			"{% if c.rfq.named_place %} {{ c.rfq.named_place }}{% endif %}{% endif %}"
			"{% if c.rfq.incoterm and c.rfq.reply_by %}<br>{% endif %}"
			'{% if c.rfq.reply_by %}<span style="color:#6b7280">Please reply by:</span> '
			"<strong>{{ c.rfq.reply_by }}</strong>{% endif %}</p>{% endif %}\n",
		),
	),
}


def update(template, text):
	"""``text`` with the template's replacements, or unchanged when any snippet is missing or repeated."""
	pairs = REPLACEMENTS.get(template, ())
	if not text or not pairs or any(text.count(old) != 1 for old, _new in pairs):
		return text
	for old, new in pairs:
		text = text.replace(old, new)
	return text


def execute():
	updated = {"templates": [], "drafts": []}
	for template in REPLACEMENTS:
		if not frappe.db.exists("Email Template", template):
			continue
		text = frappe.db.get_value("Email Template", template, "response_html")
		changed = update(template, text)
		if changed != text:
			frappe.db.set_value("Email Template", template, "response_html", changed)
			updated["templates"].append(template)

	for rfq in frappe.get_all(
		"Request for Quotation",
		filters={"docstatus": 0, "email_template": RFQ_TEMPLATE},
		fields=["name", "mfs_html"],
	):
		changed = update(RFQ_TEMPLATE, rfq.mfs_html)
		if changed != rfq.mfs_html:
			frappe.db.set_value("Request for Quotation", rfq.name, "mfs_html", changed, update_modified=False)
			updated["drafts"].append(rfq.name)

	frappe.db.commit()
	return updated
