# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The shipped email templates, Helpdesk saved replies and Notifications.

Bodies live in ``bodies/<slug>.html`` (Helpdesk replies in ``bodies/helpdesk/``) so they
read as HTML in review. ``seed`` copies them into the site once; after that the site's
copy is the one staff edit, and migrations never overwrite it.

Every Email Template starts with ``{% set c = ill_email_context(doctype, name) %}``, so
the same text works in the Desk composer, a Notification and Frappe CRM, which all put
the document's fields at the top level of the context.
"""

import os
from dataclasses import dataclass

BODIES = os.path.join(os.path.dirname(__file__), "bodies")
PREFIX = "ilL - "

# Frappe sends a Notification (and the app's auto-sends) without a container, the same way
# as a person's composer email, so the wrapper can't tell them apart. Templates sent
# automatically start with this marker, and templates/emails/standard.html puts any email
# that carries it in the ilLumenate card.
CARD_MARKER = "<!-- ill:card -->"


@dataclass(frozen=True)
class Template:
	slug: str
	doctype: str  # reference_doctype; "" for a template offered on every DocType
	title: str
	subject: str
	trigger: str  # how it is sent, for the docs and the Desk description
	to: str  # who it goes to
	attach: str = ""  # print format attached when a Notification or auto-send sends it
	audience: str = "customer"

	@property
	def name(self):
		return f"{PREFIX}{self.doctype} - {self.title}" if self.doctype else f"{PREFIX}{self.title}"

	@property
	def path(self):
		return os.path.join(BODIES, f"{self.slug}.html")

	def body(self):
		with open(self.path, encoding="utf-8") as handle:
			text = handle.read()
		return f"{CARD_MARKER}\n{text}" if self.slug in automatic_slugs() else text


@dataclass(frozen=True)
class SavedReply:
	slug: str
	title: str
	uses: str  # the HD Ticket link it reads

	@property
	def name(self):
		return f"{PREFIX}{self.title}"

	@property
	def path(self):
		return os.path.join(BODIES, "helpdesk", f"{self.slug}.html")

	def body(self):
		with open(self.path, encoding="utf-8") as handle:
			return handle.read()


@dataclass(frozen=True)
class NotificationRule:
	title: str
	template: str  # Template.slug
	document_type: str
	event: str
	condition: str
	date_changed: str = ""
	days_in_advance: int = 0
	value_changed: str = ""
	recipient_field: str = "contact_email"
	attach_print: str = ""

	@property
	def name(self):
		return f"{PREFIX}{self.title}"


MANUAL = "Manual: pick it in the email composer"

TEMPLATES = [
	# --- Quotation -------------------------------------------------------------
	Template(
		"quote_sent",
		"Quotation",
		"Quote sent",
		"Your ilLumenate Lighting quote {{ name }}",
		MANUAL,
		"contact_email",
		"ilL Quotation",
	),
	Template(
		"quote_followup",
		"Quotation",
		"Quote follow-up",
		"Following up on quote {{ name }}",
		"Notification: 3 days after the quote date while Open",
		"contact_email",
	),
	Template(
		"quote_expiring",
		"Quotation",
		"Quote expiring soon",
		"Quote {{ name }} pricing expires {{ ill_date(valid_till) }}",
		"Notification: 7 days before Valid Till while Open",
		"contact_email",
	),
	Template(
		"quote_expired",
		"Quotation",
		"Quote expired, refresh pricing",
		"Quote {{ name }} has expired: want updated pricing?",
		"Notification: 1 day after Valid Till while Open or Expired",
		"contact_email",
	),
	Template(
		"quote_revised",
		"Quotation",
		"Quote revised",
		"Revised quote {{ name }}",
		MANUAL + " on the amended quote; fill in what changed",
		"contact_email",
		"ilL Quotation",
	),
	Template(
		"quote_lost",
		"Quotation",
		"Quote lost check-in",
		"Thanks for considering us: quote {{ name }}",
		MANUAL + " once the quote is marked Lost",
		"contact_email",
	),
	Template(
		"quote_submittal",
		"Quotation",
		"Submittal package ready",
		"Submittal package for quote {{ name }}",
		MANUAL + "; attach the submittal PDF",
		"contact_email",
	),
	# --- CRM -------------------------------------------------------------------
	Template(
		"deal_quote_followup",
		"CRM Deal",
		"Quote follow-up",
		"Following up on your ilLumenate Lighting quote",
		"Manual in Frappe CRM (deal email)",
		"deal email",
	),
	Template(
		"deal_lost",
		"CRM Deal",
		"Lost check-in",
		"Thanks for considering ilLumenate Lighting",
		"Manual in Frappe CRM after the deal is Lost",
		"deal email",
	),
	# --- Sales Order -----------------------------------------------------------
	Template(
		"so_confirmation",
		"Sales Order",
		"Order confirmation",
		"Order confirmed: {{ name }}{% if po_no %} (your PO {{ po_no }}){% endif %}",
		"Automatic on submit when ilL-Email-Settings allows; or manual",
		"contact_email (portal dealers skipped)",
		"ilL Sales Order",
	),
	Template(
		"so_deposit",
		"Sales Order",
		"Deposit request",
		"Deposit due for order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL,
		"contact_email",
		"ilL Sales Order",
	),
	Template(
		"so_on_hold",
		"Sales Order",
		"On hold, action needed",
		"Action needed on order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL + " after setting Hold Reason",
		"contact_email",
	),
	Template(
		"so_ship_date",
		"Sales Order",
		"Ship date update",
		"Ship date for order {{ name }}: {{ ill_date(ill_estimated_ship_date) }}",
		"Notification: Estimated Ship Date changes on a submitted order",
		"contact_email",
	),
	Template(
		"so_delay",
		"Sales Order",
		"Ship date changed",
		"Updated ship date for order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL + " after changing the ship date; add the reason",
		"contact_email",
	),
	Template(
		"so_will_call",
		"Sales Order",
		"Ready for pickup",
		"Ready for pickup: order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL + " (Will Call orders)",
		"contact_email",
	),
	Template(
		"so_proforma",
		"Sales Order",
		"Proforma, pay before shipping",
		"Proforma for order {{ name }}: payment due before shipping",
		MANUAL + " (Proforma orders)",
		"contact_email",
		"ilL Sales Order",
	),
	Template(
		"so_partial",
		"Sales Order",
		"Partial shipment",
		"Partial shipment: order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL,
		"contact_email",
	),
	Template(
		"so_change",
		"Sales Order",
		"Order change confirmed",
		"Order {{ name }} updated{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL + "; fill in what changed",
		"contact_email",
		"ilL Sales Order",
	),
	Template(
		"so_status",
		"Sales Order",
		"Status update",
		"Status of order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL,
		"contact_email",
	),
	Template(
		"drawings_ready",
		"Sales Order",
		"Drawings ready for approval",
		"Drawings ready for approval: order {{ name }}{% if po_no %} (PO {{ po_no }}){% endif %}",
		MANUAL + "; attach the drawings for non-portal customers",
		"contact_email",
	),
	# --- Delivery Note ---------------------------------------------------------
	Template(
		"dn_shipped",
		"Delivery Note",
		"Shipped",
		"{% if is_return %}Return recorded{% else %}Your order has shipped{% endif %}{% if po_no %} (PO {{ po_no }}){% endif %}",
		"Automatic on submit when ilL-Email-Settings allows; or manual",
		"contact_email (portal dealers skipped)",
		"ilL Delivery Note",
	),
	Template(
		"dn_checkin",
		"Delivery Note",
		"Delivery check-in",
		"How did your order arrive?{% if po_no %} (PO {{ po_no }}){% endif %}",
		"Notification: 5 days after shipping, not returns",
		"contact_email",
	),
	Template(
		"dn_return",
		"Delivery Note",
		"Return received",
		"We received your return",
		MANUAL + " on a return Delivery Note",
		"contact_email",
	),
	# --- Sales Invoice ---------------------------------------------------------
	Template(
		"si_invoice",
		"Sales Invoice",
		"Invoice",
		"Invoice {{ name }} from ilLumenate Lighting{% if po_no %} (PO {{ po_no }}){% endif %}",
		"Notification: 1 day after the invoice date (after the QuickBooks pay link arrives); or manual",
		"contact_email",
		"ilL Sales Invoice",
	),
	Template(
		"si_reminder",
		"Sales Invoice",
		"Payment reminder",
		"Reminder: invoice {{ name }} is due {{ ill_date(due_date) }}",
		"Notification: 3 days before the due date with a balance",
		"contact_email",
	),
	Template(
		"si_overdue",
		"Sales Invoice",
		"Past due",
		"Past due: invoice {{ name }} ({{ ill_money(outstanding_amount, currency) }})",
		"Notifications: 1, 15 and 30 days after the due date with a balance",
		"contact_email",
		"ilL Sales Invoice",
	),
	Template(
		"si_paid",
		"Sales Invoice",
		"Paid in full receipt",
		"{% if outstanding_amount <= 0 %}Paid in full{% else %}Payment received{% endif %}: invoice {{ name }}",
		MANUAL,
		"contact_email",
		"ilL Sales Invoice",
	),
	Template(
		"si_credit_note",
		"Sales Invoice",
		"Credit note",
		"Credit note {{ name }} from ilLumenate Lighting",
		MANUAL + " on a return invoice",
		"contact_email",
		"ilL Sales Invoice",
	),
	# --- Payment Entry ---------------------------------------------------------
	Template(
		"pe_receipt",
		"Payment Entry",
		"Payment received",
		"Payment received, thank you ({{ ill_money(paid_amount, paid_from_account_currency) }})",
		"Notification: on submit of a customer receipt",
		"contact_email",
	),
	Template(
		"pe_remittance",
		"Payment Entry",
		"Remittance advice",
		"Remittance advice from ilLumenate Lighting ({{ ill_money(received_amount or paid_amount, paid_to_account_currency) }})",
		MANUAL + " on a supplier payment",
		"contact_email",
		audience="supplier",
	),
	# --- Customer --------------------------------------------------------------
	Template(
		"customer_welcome",
		"Customer",
		"Dealer welcome",
		"Welcome to ilLumenate Lighting",
		MANUAL,
		"purchasing contact",
	),
	# --- Supplier side ---------------------------------------------------------
	Template(
		"po_send",
		"Purchase Order",
		"Send to supplier",
		"Purchase order {{ name }} from ilLumenate Lighting",
		MANUAL + "; sending marks the PO Sent",
		"Supplier purchasing email, else contact_email",
		"ilL Purchase Order",
		"supplier",
	),
	Template(
		"po_confirm_chase",
		"Purchase Order",
		"Confirmation chase",
		"Please confirm purchase order {{ name }}",
		"Notification: 3 days after Sent On with no confirmation",
		"contact_email",
		audience="supplier",
	),
	Template(
		"po_eta",
		"Purchase Order",
		"Ship date and ETA check",
		"Ship date update for purchase order {{ name }}",
		"Notification: 1 day after Promised Ship Date, not received; or manual",
		"contact_email",
		audience="supplier",
	),
	Template(
		"po_change",
		"Purchase Order",
		"Change or cancellation",
		"{% if docstatus == 2 %}Cancelled{% else %}Revised{% endif %}: purchase order {{ name }}",
		MANUAL + " on the amended or cancelled PO",
		"contact_email",
		"ilL Purchase Order",
		"supplier",
	),
	Template(
		"rfq_request",
		"Request for Quotation",
		"Request",
		"Request for quotation {{ name }} from ilLumenate Lighting",
		"Set as the RFQ's Email Template; ERPNext sends it per supplier",
		"each supplier row's email",
		audience="supplier",
	),
	Template(
		"rfq_reminder",
		"Request for Quotation",
		"No response reminder",
		"Reminder: request for quotation {{ name }}",
		MANUAL + " to suppliers who have not quoted",
		"supplier email",
		audience="supplier",
	),
	Template(
		"sq_followup",
		"Supplier Quotation",
		"Questions and expiry",
		"Questions on your quotation {{ name }}",
		MANUAL + "; fill in the questions",
		"contact_email",
		audience="supplier",
	),
	Template(
		"pr_discrepancy",
		"Purchase Receipt",
		"Receiving discrepancy",
		"Receiving issue on {{ supplier_delivery_note or name }}",
		MANUAL + "; describe the issue and attach photos",
		"contact_email",
		audience="supplier",
	),
	# --- Any DocType -----------------------------------------------------------
	Template(
		"general_followup",
		"",
		"General follow-up",
		"Following up",
		MANUAL + " on any document",
		"anyone",
	),
	Template(
		"general_received",
		"",
		"We received your message",
		"We received your message",
		MANUAL + " on any document",
		"anyone",
	),
	Template(
		"general_holiday",
		"",
		"Holiday hours",
		"ilLumenate Lighting holiday hours",
		MANUAL + "; fill in the dates",
		"anyone",
	),
]

SAVED_REPLIES = [
	SavedReply("order_status", "Order status", "ill_sales_order"),
	SavedReply("invoice_copy", "Invoice copy and payment link", "ill_sales_invoice"),
	SavedReply("quote_copy", "Quote copy", "ill_quotation"),
	SavedReply("warranty_claim", "Warranty claim: what we need", "ill_sales_order"),
	SavedReply("damage_in_transit", "Damaged in transit", "ill_sales_order"),
	SavedReply("resolved", "Resolved, anything else?", ""),
]

_OPEN_QUOTE = 'doc.docstatus == 1 and doc.status == "Open"'
_INVOICE_BALANCE = "doc.docstatus == 1 and not doc.is_return and doc.outstanding_amount > 0"

NOTIFICATIONS = [
	NotificationRule(
		"Quote follow-up",
		"quote_followup",
		"Quotation",
		"Days After",
		_OPEN_QUOTE,
		date_changed="transaction_date",
		days_in_advance=3,
	),
	NotificationRule(
		"Quote expiring soon",
		"quote_expiring",
		"Quotation",
		"Days Before",
		_OPEN_QUOTE,
		date_changed="valid_till",
		days_in_advance=7,
	),
	NotificationRule(
		"Quote expired",
		"quote_expired",
		"Quotation",
		"Days After",
		'doc.docstatus == 1 and doc.status in ("Open", "Expired")',
		date_changed="valid_till",
		days_in_advance=1,
	),
	NotificationRule(
		"Ship date update",
		"so_ship_date",
		"Sales Order",
		"Value Change",
		"doc.docstatus == 1 and doc.ill_estimated_ship_date and doc.per_delivered < 100",
		value_changed="ill_estimated_ship_date",
	),
	NotificationRule(
		"Delivery check-in",
		"dn_checkin",
		"Delivery Note",
		"Days After",
		"doc.docstatus == 1 and not doc.is_return",
		date_changed="posting_date",
		days_in_advance=5,
	),
	NotificationRule(
		"Invoice",
		"si_invoice",
		"Sales Invoice",
		"Days After",
		_INVOICE_BALANCE,
		date_changed="posting_date",
		days_in_advance=1,
		attach_print="ilL Sales Invoice",
	),
	NotificationRule(
		"Invoice due soon",
		"si_reminder",
		"Sales Invoice",
		"Days Before",
		_INVOICE_BALANCE,
		date_changed="due_date",
		days_in_advance=3,
	),
	NotificationRule(
		"Invoice past due 1 day",
		"si_overdue",
		"Sales Invoice",
		"Days After",
		_INVOICE_BALANCE,
		date_changed="due_date",
		days_in_advance=1,
	),
	NotificationRule(
		"Invoice past due 15 days",
		"si_overdue",
		"Sales Invoice",
		"Days After",
		_INVOICE_BALANCE,
		date_changed="due_date",
		days_in_advance=15,
	),
	NotificationRule(
		"Invoice past due 30 days",
		"si_overdue",
		"Sales Invoice",
		"Days After",
		_INVOICE_BALANCE,
		date_changed="due_date",
		days_in_advance=30,
		attach_print="ilL Sales Invoice",
	),
	NotificationRule(
		"Payment received",
		"pe_receipt",
		"Payment Entry",
		"Submit",
		'doc.payment_type == "Receive" and doc.party_type == "Customer"',
	),
	NotificationRule(
		"PO confirmation chase",
		"po_confirm_chase",
		"Purchase Order",
		"Days After",
		'doc.docstatus == 1 and doc.ill_vendor_status == "Sent" and not doc.ill_vendor_confirmed_on and not doc.ill_vendor_order_no',
		date_changed="ill_sent_on",
		days_in_advance=3,
	),
	NotificationRule(
		"PO late shipment",
		"po_eta",
		"Purchase Order",
		"Days After",
		'doc.docstatus == 1 and doc.per_received < 100 and doc.ill_vendor_status not in ("Shipped", "Delivered")',
		date_changed="ill_promised_ship_date",
		days_in_advance=1,
	),
]

BY_SLUG = {t.slug: t for t in TEMPLATES}

# Sent by the app after submit (email_templates/auto_send.py JOBS).
AUTO_SEND_SLUGS = ("so_confirmation", "dn_shipped")


def automatic_slugs():
	"""Templates sent with nobody at the keyboard: Notifications and the app's auto-sends."""
	return {rule.template for rule in NOTIFICATIONS} | set(AUTO_SEND_SLUGS)


def template_name(slug):
	return BY_SLUG[slug].name
