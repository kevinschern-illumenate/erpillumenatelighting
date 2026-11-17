"""Link Helpdesk tickets (HD Ticket) to the Quotation, Sales Order and Sales Invoice they concern.

The links live on the ticket because Helpdesk renders its saved replies and
notification emails against the ticket: ``{{ ill_quotation }}`` in a saved reply,
``{{ doc.ill_quotation }}`` in an HD Settings email. The sales documents list
their tickets under Connections and get a button to link more.

Helpdesk is optional. Nothing here runs or registers until the HD Ticket DocType
exists, and the fields are created on the first migrate after Helpdesk is installed.
"""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

TICKET = "HD Ticket"

# Sales DocType -> the HD Ticket field that links to it, in sales-flow order.
LINK_FIELDS = {
	"Quotation": "ill_quotation",
	"Sales Order": "ill_sales_order",
	"Sales Invoice": "ill_sales_invoice",
}

TEMPLATE = "Default"


def helpdesk_installed() -> bool:
	return bool(frappe.db.exists("DocType", TICKET))


def ensure_fields():
	"""Create the ticket's sales-document links when Helpdesk is installed (after_migrate)."""
	if not helpdesk_installed():
		return
	meta = frappe.get_meta(TICKET)
	if not all(meta.has_field(f) for f in LINK_FIELDS.values()):
		fields = [
			{
				"fieldname": "ill_sales_documents_section",
				"fieldtype": "Section Break",
				"label": "Sales Documents",
				"insert_after": "via_customer_portal",
				"collapsible": 0,
			}
		]
		previous = "ill_sales_documents_section"
		for doctype, fieldname in LINK_FIELDS.items():
			fields.append(
				{
					"fieldname": fieldname,
					"fieldtype": "Link",
					"options": doctype,
					"label": doctype,
					"insert_after": previous,
					"search_index": 1,
					"in_standard_filter": 1,
				}
			)
			previous = fieldname
		create_custom_fields({TICKET: fields}, update=True)
	_add_to_agent_sidebar()


def _add_to_agent_sidebar():
	"""Show the links in the Helpdesk agent ticket sidebar, once.

	The Default ticket template is staff-maintained data, so only missing rows are
	added; a field an agent removed from the template is not re-added on later migrates
	because the flag below records that it was seeded.
	"""
	if not frappe.db.exists("HD Ticket Template", TEMPLATE):
		return
	if frappe.db.get_default("ill_helpdesk_sidebar_seeded"):
		return
	template = frappe.get_doc("HD Ticket Template", TEMPLATE)
	present = {row.fieldname for row in template.get("fields") or []}
	missing = [f for f in LINK_FIELDS.values() if f not in present]
	for fieldname in missing:
		template.append("fields", {"fieldname": fieldname, "required": 0, "visible_to": "Agents"})
	if missing:
		template.flags.ignore_permissions = True
		template.save()
	frappe.db.set_default("ill_helpdesk_sidebar_seeded", "1")


def fill_upstream(doc, method=None):
	"""HD Ticket validate: fill an empty Sales Order / Quotation from the document after it.

	A ticket linked to an invoice usually concerns that invoice's order and quote too,
	so templates can quote all three. Fields already set are never changed.
	"""
	if doc.get("ill_sales_invoice") and not doc.get("ill_sales_order"):
		doc.ill_sales_order = _first_value(
			"Sales Invoice Item",
			{"parent": doc.ill_sales_invoice, "sales_order": ["is", "set"]},
			"sales_order",
		)
	if doc.get("ill_sales_order") and not doc.get("ill_quotation"):
		doc.ill_quotation = _first_value(
			"Sales Order Item",
			{"parent": doc.ill_sales_order, "prevdoc_docname": ["is", "set"]},
			"prevdoc_docname",
		)


def _first_value(doctype, filters, field):
	rows = frappe.get_all(doctype, filters=filters, pluck=field, order_by="idx asc", limit=1)
	return rows[0] if rows else None


def _dashboard(doctype):
	"""override_doctype_dashboards: list linked tickets under Connections when Helpdesk is installed."""

	def override(data):
		if not helpdesk_installed():
			return data
		data = data or {}
		data.setdefault("non_standard_fieldnames", {})[TICKET] = LINK_FIELDS[doctype]
		transactions = data.setdefault("transactions", [])
		group = next((t for t in transactions if t.get("label") == _("Support")), None)
		if group is None:
			group = {"label": _("Support"), "items": []}
			transactions.append(group)
		if TICKET not in group["items"]:
			group["items"].append(TICKET)
		return data

	return override


quotation_dashboard = _dashboard("Quotation")
sales_order_dashboard = _dashboard("Sales Order")
sales_invoice_dashboard = _dashboard("Sales Invoice")


@frappe.whitelist()
def link_tickets(doctype: str, name: str, tickets: list[str] | str):
	"""Point each ticket's link for ``doctype`` at ``name`` (the sales form's Link Tickets button)."""
	if doctype not in LINK_FIELDS:
		frappe.throw(_("Tickets can only be linked to a Quotation, Sales Order or Sales Invoice."))
	if not helpdesk_installed():
		frappe.throw(_("Helpdesk is not installed on this site."))
	frappe.get_doc(doctype, name).check_permission("read")
	if isinstance(tickets, str):
		tickets = frappe.parse_json(tickets)
	fieldname = LINK_FIELDS[doctype]
	linked = []
	for ticket_name in tickets or []:
		ticket = frappe.get_doc(TICKET, ticket_name)
		ticket.check_permission("write")
		if ticket.get(fieldname) != name:
			ticket.set(fieldname, name)
			ticket.save()
		linked.append(ticket.name)
	return linked


def ill_print_pdf_url(doctype, name, print_format=None, letterhead=None) -> str:
	"""Jinja: a link anyone with the email can open to download the document as a PDF.

	For Helpdesk saved replies, e.g. ``<a href="{{ ill_print_pdf_url('Quotation', ill_quotation) }}">``.
	The link carries a Document Share Key, which expires after System Settings'
	"Document Share Key Expiry" (90 days by default). Returns "" when the field is
	empty, the DocType is not a sales document, or the person rendering the template
	cannot read the document, so a blank link never leaks a record.
	"""
	if not name or doctype not in LINK_FIELDS:
		return ""
	if not frappe.db.exists(doctype, name) or not frappe.has_permission(doctype, "read", name):
		return ""
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 2:
		return ""
	params = {"doctype": doctype, "name": name, "key": doc.get_document_share_key()}
	if print_format:
		params["format"] = print_format
	if letterhead:
		params["letterhead"] = letterhead
	return frappe.utils.get_url("/api/method/frappe.utils.print_format.download_pdf?" + urlencode(params))


def after_migrate():
	# A Helpdesk upgrade or a template problem must not fail the whole migrate.
	# No savepoint: adding a column is DDL, which commits on MariaDB.
	try:
		ensure_fields()
	except Exception:
		frappe.log_error(title="Helpdesk sales-document links", message=frappe.get_traceback())
