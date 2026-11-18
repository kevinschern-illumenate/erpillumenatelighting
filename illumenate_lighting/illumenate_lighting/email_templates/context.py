# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""``ill_email_context(doctype, name)``: everything a customer or supplier email prints.

Email Templates are rendered on five screens with five different contexts (Desk
composer, Notification, Helpdesk saved reply, CRM, Request for Quotation), and the
last three of those render with restricted globals where ``frappe.db`` lookups are
limited or missing. Our hook Jinja methods are available on all five, so templates
start with::

	{% set c = ill_email_context(doctype, name) %}          {# any ERPNext document #}
	{% set c = ill_email_context("Sales Order", ill_sales_order) %}   {# Helpdesk #}

and print ``c.*``. Every key in ``skeleton()`` is always present: Frappe renders with
Jinja's DebugUndefined, which prints a missing key as literal ``{{ c.x }}`` text, so
a template must never reach for a key that might not exist. Values are pre-formatted
strings ("November 18, 2026", "$1,234.00"), "" when blank, never None.

Lookups run as the person rendering the template: a document they cannot read gives
the empty skeleton (``c.found`` false) rather than an error, and PDF links come from
``ill_print_pdf_url``, which applies the same rule.
"""

import copy

import frappe

from illumenate_lighting.illumenate_lighting.email_templates import blocks
from illumenate_lighting.illumenate_lighting.email_templates import formatting as fmt
from illumenate_lighting.illumenate_lighting.email_templates.settings import get_settings

SCHEDULE = "ilL-Project-Fixture-Schedule"
PROJECT = "ilL-Project"

PRINT_FORMATS = {
	"Quotation": "ilL Quotation",
	"Sales Order": "ilL Sales Order",
	"Sales Invoice": "ilL Sales Invoice",
	"Delivery Note": "ilL Delivery Note",
	"Purchase Order": "ilL Purchase Order",
	"Packing Slip": "Packing Slip",
}

# Who signs the email when the document names no one.
PURCHASING_DOCTYPES = {
	"Purchase Order",
	"Request for Quotation",
	"Supplier Quotation",
	"Purchase Receipt",
}

SYSTEM_USERS = {"Administrator", "Guest"}


def skeleton():
	"""Every key a template may print, with its blank value."""
	return copy.deepcopy(_SKELETON)


_SKELETON = {
	"found": False,
	"doctype": "",
	"name": "",
	"docstatus": 0,
	"is_cancelled": False,
	"company": "ilLumenate Lighting",
	"currency": "USD",
	"party_name": "",
	"greeting_name": "there",
	"contact_email": "",
	"date": "",
	"grand_total": "",
	"po_no": "",
	"po_date": "",
	"project_name": "",
	"schedule_name": "",
	"job_name": "",
	"portal_url": "",
	"is_dealer": False,
	"portal": {"home": "", "orders": "", "drawings": "", "support": ""},
	"lines": [],
	"lines_more": 0,
	"poc": {"name": "", "email": "", "phone": "", "title": ""},
	"pdf": {"quote": "", "so": "", "si": "", "dn": "", "packing": "", "po": "", "rfq": "", "sq": ""},
	"pay_link": "",
	"pay_instructions": "",
	"sales_orders": [],
	"quote": {
		"number": "",
		"date": "",
		"valid_till": "",
		"days_left": None,
		"expires_in": "",
		"expired": False,
		"status": "",
		"total": "",
		"revised_from": "",
		"lost_reason": "",
		"crm_deal": "",
	},
	"order": {
		"date": "",
		"status": "",
		"progress": "",
		"total": "",
		"ship_date": "",
		"ship_date_label": "",
		"delivery_promise": "",
		"delivery_promise_label": "",
		"requested_date": "",
		"shipping_address": "",
		"receiving_instructions": "",
		"shipping_instructions": "",
		"on_hold": False,
		"hold_message": "",
		"will_call": False,
		"proforma": False,
		"per_delivered": 0,
		"partly_shipped": False,
		"fully_shipped": False,
		"advance_paid": "",
		"payment_terms": "",
		"schedule": [],
		"payment_due": {"label": "", "amount": "", "due_date": "", "portion": ""},
		"shipments": [],
		"invoices": [],
	},
	"invoice": {
		"date": "",
		"due_date": "",
		"days_to_due": None,
		"days_overdue": 0,
		"overdue_stage": "",
		"status": "",
		"total": "",
		"outstanding": "",
		"paid_to_date": "",
		"has_balance": False,
		"is_partly_paid": False,
		"is_paid": False,
		"is_return": False,
		"return_against": "",
		"billing_address": "",
		"payment_terms": "",
		"schedule": [],
		"payments": [],
		"delivery_notes": [],
	},
	"shipment": {
		"date": "",
		"carrier": "",
		"number": "",
		"url": "",
		"is_return": False,
		"partial": False,
		"shipping_address": "",
		"instructions": "",
		"packing_slips": [],
	},
	"purchase": {
		"date": "",
		"required_by": "",
		"ship_to": "",
		"incoterm": "",
		"named_place": "",
		"freight_mode": "",
		"payment_terms": "",
		"schedule": [],
		"vendor_order_no": "",
		"promised_ship_date": "",
		"eta": "",
		"sent_on": "",
		"days_since_sent": None,
		"confirmed": False,
		"drop_ship_customer": "",
		"to_email": "",
		"received_pct": 0,
		"revised_from": "",
		"total": "",
	},
	"rfq": {
		"date": "",
		"required_by": "",
		"reply_by": "",
		"incoterm": "",
		"named_place": "",
		"ship_to": "",
	},
	"supplier_quote": {
		"date": "",
		"valid_till": "",
		"expires_in": "",
		"expired": False,
		"total": "",
		"rfqs": [],
	},
	"receipt": {
		"date": "",
		"supplier_delivery_note": "",
		"rejected": [],
		"purchase_orders": [],
	},
	"payment": {
		"date": "",
		"amount": "",
		"method": "",
		"reference": "",
		"is_supplier": False,
		"applied": [],
		"unallocated": "",
		"remaining_balance": "",
		"has_remaining_balance": False,
	},
	"customer": {"has_portal": False, "portal_url": "", "purchasing_contact": ""},
	"deal": {
		"organization": "",
		"status": "",
		"next_step": "",
		"expected_closure_date": "",
		"lost_reason": "",
		"has_quote": False,
	},
	"settings": {"pickup_address": "", "pickup_hours": ""},
	"blocks": {
		"lines": "",
		"lines_no_prices": "",
		"supplier_lines": "",
		"supplier_lines_no_prices": "",
		"order_schedule": "",
		"invoice_schedule": "",
		"purchase_schedule": "",
		"payments": "",
		"applied": "",
		"rejected": "",
		"tracking": "",
		"pay_button": "",
		"signature": "",
		"shipping_address": "",
		"billing_address": "",
		"ship_to": "",
		"pickup_address": "",
	},
}


# ---------------------------------------------------------------------------
# Jinja methods
# ---------------------------------------------------------------------------


def ill_email_context(doctype=None, name=None):
	"""Jinja: the email context for one document. Never raises."""
	doctype, name = _plain(doctype), _plain(name)
	c = skeleton()
	c["doctype"], c["name"] = doctype or "", name or ""
	settings = get_settings()
	try:
		if doctype and name and _readable(doctype, name):
			doc = frappe.get_doc(doctype, name)
			_common(c, doc, settings)
			builder = BUILDERS.get(doctype)
			if builder:
				builder(c, doc, settings)
			c["found"] = True
	except Exception:
		frappe.log_error(title=f"ilL email context: {doctype} {name}")
	if not c["poc"]["email"]:
		c["poc"] = _fallback_contact(doctype, settings)
	try:
		_finish(c, settings)
	except Exception:
		frappe.log_error(title=f"ilL email blocks: {doctype} {name}")
	return c


def ill_tracking(delivery_note):
	"""Jinja: {"carrier", "number", "url"} for a Delivery Note name, doc or dict."""
	from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import tracking

	empty = {"carrier": None, "number": None, "url": None}
	try:
		delivery_note = _plain(delivery_note) if isinstance(delivery_note, str) else delivery_note
		if isinstance(delivery_note, str):
			if not _readable("Delivery Note", delivery_note):
				return empty
			delivery_note = frappe.get_doc("Delivery Note", delivery_note)
		return tracking(delivery_note) if delivery_note else empty
	except Exception:
		frappe.log_error(title="ilL email: tracking lookup failed")
		return empty


def ill_money(value, currency="USD"):
	"""Jinja: '$1,234.00'."""
	return fmt.fmt_money(value, _plain(currency) or "USD")


def ill_date(value):
	"""Jinja: 'November 18, 2026'; '' when blank."""
	return fmt.fmt_date(_plain(value))


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------


def _plain(value):
	"""Jinja's Undefined (a field missing from the render context) counts as blank."""
	if value is None or type(value).__name__.endswith("Undefined"):
		return None
	if isinstance(value, str):
		return value.strip() or None
	return value


def _readable(doctype, name):
	return bool(frappe.db.exists(doctype, name)) and bool(frappe.has_permission(doctype, "read", name))


def _has_field(doctype, fieldname):
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


def _fields(doctype, wanted):
	"""The subset of ``wanted`` that exists on ``doctype`` (custom fields can be missing before migrate)."""
	return [f for f in wanted if f in ("name", "docstatus") or _has_field(doctype, f)]


def _value(doctype, name, field):
	if not name or not _has_field(doctype, field):
		return None
	return frappe.db.get_value(doctype, name, field)


def pdf_url(doctype, name, print_format=None):
	"""A share-key PDF link, "" when the document is missing, unreadable or cancelled."""
	from illumenate_lighting.illumenate_lighting.helpdesk_links import ill_print_pdf_url

	if not name:
		return ""
	try:
		return ill_print_pdf_url(doctype, name, print_format or PRINT_FORMATS.get(doctype)) or ""
	except Exception:
		frappe.log_error(title=f"ilL email: PDF link for {doctype} {name}")
		return ""


def _money(c, value):
	return fmt.fmt_money(value, c["currency"])


def _today():
	return frappe.utils.nowdate()


def _total(doc):
	return doc.get("rounded_total") or doc.get("grand_total") or 0


def _rows(doc, table):
	return list(doc.get(table) or [])


def _common(c, doc, settings):
	c["docstatus"] = doc.get("docstatus") or 0
	c["is_cancelled"] = c["docstatus"] == 2
	c["company"] = doc.get("company") or c["company"]
	c["currency"] = doc.get("currency") or c["currency"]
	c["party_name"] = fmt.clean(
		doc.get("customer_name")
		or doc.get("supplier_name")
		or doc.get("organization")
		or doc.get("organization_name")
		or (doc.get("party_name") if doc.doctype == "Payment Entry" else None)
		or doc.get("lead_name")
	)
	c["contact_email"] = fmt.clean(doc.get("contact_email"))
	c["date"] = fmt.fmt_date(doc.get("transaction_date") or doc.get("posting_date"))
	if doc.get("grand_total") is not None:
		c["grand_total"] = _money(c, _total(doc))
	c["po_no"] = fmt.clean(doc.get("po_no"))
	c["po_date"] = fmt.fmt_date(doc.get("po_date"))
	c["greeting_name"] = _greeting(doc, c["party_name"])
	_portal(c, doc)
	_job(c, doc)
	c["poc"] = point_of_contact(doc, settings)
	limit = settings.get("max_lines") or 15
	if doc.meta.has_field("items"):
		c["lines"], c["lines_more"] = fmt.summarize_lines(
			_rows(doc, "items"),
			limit=limit,
			currency=c["currency"],
			with_amounts=doc.doctype not in ("Delivery Note", "Request for Quotation", "Purchase Receipt"),
		)


def _greeting(doc, party_name):
	"""First name of the document's contact, else the contact's display name, else the company."""
	if doc.doctype == "Contact":
		return fmt.clean(doc.get("first_name")) or fmt.clean(doc.get("full_name")) or "there"
	contact = doc.get("contact_person")
	if not contact and doc.doctype == "Customer":
		contact = doc.get("ill_purchasing_contact") or doc.get("customer_primary_contact")
	if contact:
		first = frappe.db.get_value("Contact", contact, "first_name")
		if fmt.clean(first):
			return fmt.clean(first)
	if doc.doctype in ("CRM Deal", "CRM Lead") and fmt.clean(doc.get("first_name")):
		return fmt.clean(doc.get("first_name"))
	return fmt.clean(doc.get("contact_display")) or party_name or "there"


def _customer_of(doc):
	if doc.doctype == "Customer":
		return doc.name
	if doc.doctype == "Quotation":
		return doc.get("party_name") if doc.get("quotation_to") == "Customer" else None
	if doc.doctype == "Payment Entry":
		return doc.get("party") if doc.get("party_type") == "Customer" else None
	return doc.get("customer") if doc.doctype in ("Sales Order", "Sales Invoice", "Delivery Note") else None


def _portal(c, doc):
	"""Dealer portal links, only for a customer with a portal account (others would hit a login page)."""
	if not _customer_has_portal(_customer_of(doc)):
		return
	c["is_dealer"] = True
	for key, path in (
		("home", "/portal"),
		("orders", "/portal/orders"),
		("drawings", "/portal/drawings"),
		("support", "/portal/support"),
	):
		c["portal"][key] = frappe.utils.get_url(path)


def _job(c, doc):
	"""Project and fixture schedule names: the job name customers recognize."""
	schedule = doc.get("ill_fixture_schedule")
	if not schedule and doc.meta.has_field("items"):
		schedule = next(
			(r.get("ill_fixture_schedule") for r in _rows(doc, "items") if r.get("ill_fixture_schedule")),
			None,
		)
	if not schedule or not frappe.db.exists(SCHEDULE, schedule):
		return
	row = frappe.db.get_value(SCHEDULE, schedule, ["schedule_name", "ill_project"], as_dict=True) or {}
	c["schedule_name"] = fmt.clean(row.get("schedule_name"))
	if row.get("ill_project"):
		c["project_name"] = fmt.clean(frappe.db.get_value(PROJECT, row.get("ill_project"), "project_name"))
	c["job_name"] = c["project_name"] or c["schedule_name"]


# ---------------------------------------------------------------------------
# Point of contact
# ---------------------------------------------------------------------------


def point_of_contact(doc, settings):
	"""Who signs the email, in this order:

	1. the document's Company Contact Person (our side's Contact),
	2. the first Sales Team member with an email (Sales Person -> Employee -> user),
	3. the Customer's Account Manager, the CRM deal/lead owner, or the document's
	   creator, when that is an enabled staff (System) user and not an integration user,
	4. ilL-Email-Settings' sales or purchasing contact.
	"""
	contact = doc.get("company_contact_person")
	if contact:
		row = frappe.db.get_value(
			"Contact",
			contact,
			["full_name", "first_name", "last_name", "email_id", "phone", "mobile_no", "designation"],
			as_dict=True,
		)
		if row and row.email_id:
			name = row.full_name or " ".join(p for p in (row.first_name, row.last_name) if p)
			return _poc(name, row.email_id, row.phone or row.mobile_no, row.designation)
	for member in _rows(doc, "sales_team"):
		poc = _sales_person_contact(member.get("sales_person"))
		if poc:
			return poc
	for field in ("account_manager", "deal_owner", "lead_owner", "owner"):
		poc = _staff_user_contact(doc.get(field))
		if poc:
			return poc
	return _fallback_contact(doc.doctype, settings)


def _poc(name, email, phone=None, title=None):
	return {
		"name": fmt.clean(name),
		"email": fmt.clean(email),
		"phone": fmt.clean(phone),
		"title": fmt.clean(title),
	}


def _sales_person_contact(sales_person):
	if not sales_person:
		return None
	employee = frappe.db.get_value("Sales Person", sales_person, "employee")
	if not employee or not frappe.db.exists("DocType", "Employee"):
		return None
	row = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "user_id", "company_email", "prefered_email", "cell_number", "designation"],
		as_dict=True,
	)
	if not row:
		return None
	user = _staff_user_contact(row.user_id)
	email = row.prefered_email or row.company_email or (user or {}).get("email")
	if not email:
		return None
	return _poc(
		row.employee_name or (user or {}).get("name"),
		email,
		row.cell_number or (user or {}).get("phone"),
		row.designation,
	)


def _service_user_emails():
	try:
		from illumenate_lighting.illumenate_lighting.portal.service_users import SERVICE_USERS, service_user

		return {service_user(key) for key in SERVICE_USERS} | {s["email"] for s in SERVICE_USERS.values()}
	except Exception:
		return set()


def _staff_user_contact(user):
	if not user or user in SYSTEM_USERS or user in _service_user_emails():
		return None
	row = frappe.db.get_value(
		"User", user, ["full_name", "email", "mobile_no", "phone", "user_type", "enabled"], as_dict=True
	)
	if not row or not row.enabled or row.user_type != "System User" or not row.email:
		return None
	return _poc(row.full_name, row.email, row.mobile_no or row.phone)


def _fallback_contact(doctype, settings):
	side = "purchasing" if doctype in PURCHASING_DOCTYPES else "sales"
	return _poc(
		settings.get(f"{side}_contact_name"),
		settings.get(f"{side}_contact_email"),
		settings.get(f"{side}_contact_phone"),
	)


def _customer_has_portal(customer):
	"""True when an enabled Website User is a Contact of the Customer (a dealer portal account)."""
	if not customer:
		return False
	contacts = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
		pluck="parent",
	)
	if not contacts:
		return False
	users = frappe.get_all("Contact", filters={"name": ["in", contacts], "user": ["is", "set"]}, pluck="user")
	if not users:
		return False
	return bool(
		frappe.get_all(
			"User",
			filters={"name": ["in", users], "enabled": 1, "user_type": "Website User"},
			limit=1,
			pluck="name",
		)
	)


def _schedule_rows(c, doc):
	"""Payment schedule rows formatted for a table."""
	rows = []
	for row in _rows(doc, "payment_schedule"):
		amount = fmt.to_number(row.get("payment_amount"))
		outstanding = row.get("outstanding")
		if outstanding is None:
			outstanding = amount - fmt.to_number(row.get("paid_amount"))
		rows.append(
			{
				"label": fmt.clean(row.get("description")) or fmt.clean(row.get("payment_term")) or "Payment",
				"due_date": fmt.fmt_short_date(row.get("due_date")),
				"due_date_raw": row.get("due_date"),
				"amount": _money(c, amount),
				"outstanding": _money(c, outstanding),
				"outstanding_raw": fmt.to_number(outstanding),
				"portion": fmt.fmt_qty(row.get("invoice_portion")) + "%"
				if row.get("invoice_portion")
				else "",
			}
		)
	return rows


def _safe_pay_link(value):
	"""Only an https link on intuit.com counts (the same rule the n8n write-back enforces)."""
	from urllib.parse import urlparse

	value = fmt.clean(value)
	if not value:
		return ""
	parsed = urlparse(value)
	host = (parsed.hostname or "").lower()
	if parsed.scheme == "https" and (host == "intuit.com" or host.endswith(".intuit.com")):
		return value
	return ""


def _pay_instructions(company):
	return fmt.text_to_html(_value("Company", company, "custom_invoice_payment_instructions"))


# ---------------------------------------------------------------------------
# Per-DocType builders
# ---------------------------------------------------------------------------


def _quote_summary(c, doc):
	q = c["quote"]
	q["number"] = doc.name
	q["date"] = fmt.fmt_date(doc.get("transaction_date"))
	q["valid_till"] = fmt.fmt_date(doc.get("valid_till"))
	days = fmt.days_between(_today(), doc.get("valid_till"))
	q["days_left"] = days
	q["expired"] = days is not None and days < 0
	if days is not None and days >= 0:
		q["expires_in"] = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
	q["status"] = fmt.clean(doc.get("status"))
	q["total"] = _money(c, _total(doc))
	q["revised_from"] = fmt.clean(doc.get("amended_from"))
	reasons = [r.get("lost_reason") for r in _rows(doc, "lost_reasons")]
	q["lost_reason"] = fmt.clean(doc.get("order_lost_reason")) or ", ".join(fmt.unique(reasons))
	q["crm_deal"] = fmt.clean(doc.get("crm_deal")) or (
		doc.get("party_name") if doc.get("quotation_to") == "CRM Deal" else ""
	)
	c["pdf"]["quote"] = pdf_url("Quotation", doc.name)


def _quotation(c, doc, settings):
	_quote_summary(c, doc)
	if (
		doc.get("quotation_to") == "CRM Deal"
		and doc.get("party_name")
		and frappe.db.exists("DocType", "CRM Deal")
	):
		deal = (
			frappe.db.get_value("CRM Deal", doc.party_name, ["organization", "first_name"], as_dict=True)
			or {}
		)
		if c["party_name"] in ("", doc.party_name) and deal.get("organization"):
			c["party_name"] = fmt.clean(deal.get("organization"))
		if c["greeting_name"] in ("there", doc.party_name) and deal.get("first_name"):
			c["greeting_name"] = fmt.clean(deal.get("first_name"))
	schedule = doc.get("ill_fixture_schedule")
	if schedule and c["is_dealer"]:
		c["portal_url"] = frappe.utils.get_url(f"/portal/schedules/{schedule}")


def _sales_order(c, doc, settings):
	o = c["order"]
	o["date"] = fmt.fmt_date(doc.get("transaction_date"))
	o["status"] = fmt.clean(doc.get("status"))
	o["total"] = _money(c, _total(doc))
	o["ship_date"], o["ship_date_label"] = fmt.ship_date(doc)
	o["delivery_promise"], o["delivery_promise_label"] = fmt.delivery_promise(doc)
	o["requested_date"] = fmt.fmt_date(doc.get("ill_requested_delivery_date"))
	o["shipping_address"] = fmt.clean(doc.get("shipping_address"))
	o["receiving_instructions"] = fmt.text_to_html(doc.get("ill_receiving_instructions"))
	o["shipping_instructions"] = fmt.text_to_html(doc.get("ill_shipping_instructions"))
	o["hold_message"] = fmt.hold_message(doc.get("ill_hold_reason"))
	o["on_hold"] = bool(o["hold_message"])
	o["will_call"] = doc.get("ill_proforma_will_call") == "Will Call"
	o["proforma"] = doc.get("ill_proforma_will_call") == "Proforma"
	per_delivered = fmt.to_number(doc.get("per_delivered"))
	o["per_delivered"] = round(per_delivered)
	o["fully_shipped"] = per_delivered >= 100
	o["partly_shipped"] = 0 < per_delivered < 100
	o["progress"] = (
		"Shipped"
		if o["fully_shipped"]
		else "Partly shipped"
		if o["partly_shipped"]
		else "On hold"
		if o["on_hold"]
		else "Closed"
		if o["status"] in ("Closed", "Cancelled")
		else "In production"
		if c["docstatus"] == 1
		else "Not yet confirmed"
	)
	if fmt.to_number(doc.get("advance_paid")):
		o["advance_paid"] = _money(c, doc.get("advance_paid"))
	o["payment_terms"] = fmt.clean(doc.get("payment_terms_template"))
	o["schedule"] = _schedule_rows(c, doc)
	o["payment_due"] = _payment_due(c, doc, o["schedule"])
	o["shipments"] = _order_shipments(doc.name)
	o["invoices"] = _order_invoices(c, doc.name)
	c["pdf"]["so"] = pdf_url("Sales Order", doc.name)
	c["sales_orders"] = [{"name": doc.name, "pdf": c["pdf"]["so"], "complete": o["fully_shipped"]}]
	c["pay_instructions"] = _pay_instructions(doc.get("company"))
	if c["is_dealer"]:
		c["portal_url"] = frappe.utils.get_url(f"/portal/orders/{doc.name}")


def _payment_due(c, doc, schedule):
	"""The payment the customer owes before we build: a deposit row, or a single row due on order.

	A schedule with more than one row means the first row is a deposit. A single row due
	within 3 days of the order date means payment in advance. Paid rows are skipped.
	"""
	due = {"label": "", "amount": "", "due_date": "", "portion": ""}
	if not schedule:
		return due
	first = schedule[0]
	if first["outstanding_raw"] <= 0:
		return due
	if len(schedule) > 1:
		label = "Deposit"
	else:
		gap = fmt.days_between(doc.get("transaction_date"), first["due_date_raw"])
		if gap is None or gap > 3:
			return due
		label = "Payment in advance"
	return {
		"label": label,
		"amount": first["outstanding"],
		"due_date": fmt.fmt_date(first["due_date_raw"]),
		"portion": first["portion"],
	}


def _order_shipments(sales_order):
	from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import tracking

	notes = fmt.unique(
		frappe.get_all(
			"Delivery Note Item",
			filters={"against_sales_order": sales_order, "docstatus": 1},
			pluck="parent",
			order_by="creation asc",
		)
	)
	if not notes:
		return []
	fields = _fields(
		"Delivery Note",
		[
			"name",
			"posting_date",
			"is_return",
			"ill_carrier",
			"ill_tracking_number",
			"transporter_name",
			"vehicle_no",
			"lr_no",
		],
	)
	out = []
	for row in frappe.get_all(
		"Delivery Note",
		filters={"name": ["in", notes], "docstatus": 1},
		fields=fields,
		order_by="posting_date asc",
	):
		if row.get("is_return"):
			continue
		track = tracking(row)
		out.append(
			{
				"name": row.name,
				"date": fmt.fmt_date(row.get("posting_date")),
				"carrier": track["carrier"] or "",
				"number": track["number"] or "",
				"url": track["url"] or "",
			}
		)
	return out


def _order_invoices(c, sales_order):
	names = fmt.unique(
		frappe.get_all(
			"Sales Invoice Item",
			filters={"sales_order": sales_order, "docstatus": 1},
			pluck="parent",
			order_by="creation asc",
		)
	)
	if not names:
		return []
	return [
		{
			"name": row.name,
			"due_date": fmt.fmt_date(row.due_date),
			"outstanding": _money(c, row.outstanding_amount),
			"is_paid": fmt.to_number(row.outstanding_amount) <= 0,
		}
		for row in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", names], "docstatus": 1, "is_return": 0},
			fields=["name", "due_date", "outstanding_amount"],
			order_by="posting_date asc",
		)
	]


def _sales_invoice(c, doc, settings):
	inv = c["invoice"]
	inv["date"] = fmt.fmt_date(doc.get("posting_date"))
	inv["due_date"] = fmt.fmt_date(doc.get("due_date"))
	days = fmt.days_between(_today(), doc.get("due_date"))
	inv["days_to_due"] = days
	inv["status"] = fmt.clean(doc.get("status"))
	total = fmt.to_number(_total(doc))
	outstanding = fmt.to_number(doc.get("outstanding_amount"))
	inv["total"] = _money(c, total)
	inv["outstanding"] = _money(c, outstanding)
	inv["is_return"] = bool(doc.get("is_return"))
	inv["return_against"] = fmt.clean(doc.get("return_against"))
	inv["has_balance"] = outstanding > 0 and not inv["is_return"]
	inv["is_paid"] = c["docstatus"] == 1 and outstanding <= 0 and not inv["is_return"]
	inv["is_partly_paid"] = inv["has_balance"] and outstanding < total
	if inv["is_partly_paid"] or inv["is_paid"]:
		inv["paid_to_date"] = _money(c, total - max(outstanding, 0))
	if inv["has_balance"] and days is not None and days < 0:
		inv["days_overdue"] = -days
	inv["overdue_stage"] = fmt.overdue_stage(inv["days_overdue"])
	inv["billing_address"] = fmt.clean(doc.get("address_display"))
	inv["payment_terms"] = fmt.clean(doc.get("payment_terms_template"))
	schedule = _schedule_rows(c, doc)
	inv["schedule"] = schedule if len(schedule) > 1 else []
	inv["payments"] = _invoice_payments(c, doc)
	items = _rows(doc, "items")
	inv["delivery_notes"] = fmt.unique(r.get("delivery_note") for r in items)
	c["sales_orders"] = [
		{"name": so, "pdf": pdf_url("Sales Order", so), "complete": False}
		for so in fmt.unique(r.get("sales_order") for r in items)
	]
	c["pdf"]["si"] = pdf_url("Sales Invoice", doc.name)
	if inv["has_balance"]:
		c["pay_link"] = _safe_pay_link(doc.get("custom_qbo_payment_link"))
	c["pay_instructions"] = _pay_instructions(doc.get("company"))


def _invoice_payments(c, doc):
	from illumenate_lighting.illumenate_lighting.api.invoice_payments import ill_invoice_payments

	return [
		{
			"date": fmt.fmt_short_date(row.get("date")),
			"amount": _money(c, row.get("amount")),
			"method": fmt.clean(row.get("method")),
			"reference": fmt.clean(row.get("reference")),
		}
		for row in ill_invoice_payments(doc)
	]


def _delivery_note(c, doc, settings):
	from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import tracking

	sh = c["shipment"]
	sh["date"] = fmt.fmt_date(doc.get("posting_date"))
	track = tracking(doc)
	sh["carrier"], sh["number"], sh["url"] = track["carrier"] or "", track["number"] or "", track["url"] or ""
	sh["is_return"] = bool(doc.get("is_return"))
	sh["shipping_address"] = fmt.clean(doc.get("shipping_address"))
	sh["instructions"] = fmt.text_to_html(doc.get("instructions"))
	orders = fmt.unique(r.get("against_sales_order") for r in _rows(doc, "items"))
	c["sales_orders"] = []
	for so in orders:
		per_delivered = fmt.to_number(frappe.db.get_value("Sales Order", so, "per_delivered"))
		c["sales_orders"].append(
			{"name": so, "pdf": pdf_url("Sales Order", so), "complete": per_delivered >= 100}
		)
	sh["partial"] = any(not row["complete"] for row in c["sales_orders"])
	c["pdf"]["dn"] = pdf_url("Delivery Note", doc.name)
	slips = frappe.get_all(
		"Packing Slip",
		filters={"delivery_note": doc.name, "docstatus": 1},
		pluck="name",
		order_by="from_case_no asc",
	)
	sh["packing_slips"] = [{"name": slip, "pdf": pdf_url("Packing Slip", slip)} for slip in slips]
	first_slip = next((slip["pdf"] for slip in sh["packing_slips"] if slip["pdf"]), "")
	c["pdf"]["packing"] = first_slip or c["pdf"]["dn"]
	if len(orders) == 1 and c["is_dealer"]:
		c["portal_url"] = frappe.utils.get_url(f"/portal/orders/{orders[0]}")


def _purchase_order(c, doc, settings):
	p = c["purchase"]
	p["date"] = fmt.fmt_date(doc.get("transaction_date"))
	p["required_by"] = fmt.fmt_date(doc.get("schedule_date"))
	p["ship_to"] = fmt.clean(doc.get("shipping_address_display"))
	p["incoterm"] = fmt.clean(doc.get("incoterm"))
	p["named_place"] = fmt.clean(doc.get("named_place"))
	p["freight_mode"] = fmt.clean(doc.get("ill_freight_mode"))
	p["payment_terms"] = fmt.clean(doc.get("payment_terms_template"))
	p["schedule"] = _schedule_rows(c, doc)
	p["vendor_order_no"] = fmt.clean(doc.get("ill_vendor_order_no") or doc.get("order_confirmation_no"))
	p["promised_ship_date"] = fmt.fmt_date(doc.get("ill_promised_ship_date"))
	p["eta"] = fmt.fmt_date(doc.get("ill_eta"))
	p["sent_on"] = fmt.fmt_date(doc.get("ill_sent_on"))
	p["days_since_sent"] = fmt.days_between(doc.get("ill_sent_on"), _today())
	p["confirmed"] = bool(doc.get("ill_vendor_confirmed_on") or p["vendor_order_no"])
	p["drop_ship_customer"] = fmt.clean(doc.get("customer_name")) if doc.get("customer") else ""
	p["to_email"] = (
		fmt.clean(_value("Supplier", doc.get("supplier"), "ill_purchasing_email")) or c["contact_email"]
	)
	p["received_pct"] = round(fmt.to_number(doc.get("per_received")))
	p["revised_from"] = fmt.clean(doc.get("amended_from"))
	p["total"] = _money(c, _total(doc))
	c["pdf"]["po"] = pdf_url("Purchase Order", doc.name)


def _request_for_quotation(c, doc, settings):
	r = c["rfq"]
	r["date"] = fmt.fmt_date(doc.get("transaction_date"))
	r["required_by"] = fmt.fmt_date(doc.get("schedule_date"))
	start = fmt.as_date(doc.get("transaction_date")) or fmt.as_date(_today())
	if start:
		from datetime import timedelta

		r["reply_by"] = fmt.fmt_date(start + timedelta(days=int(settings.get("rfq_reply_days") or 7)))
	r["incoterm"] = fmt.clean(doc.get("incoterm"))
	r["named_place"] = fmt.clean(doc.get("named_place"))
	r["ship_to"] = fmt.clean(doc.get("shipping_address_display"))
	c["pdf"]["rfq"] = pdf_url("Request for Quotation", doc.name)


def _supplier_quotation(c, doc, settings):
	sq = c["supplier_quote"]
	sq["date"] = fmt.fmt_date(doc.get("transaction_date"))
	sq["valid_till"] = fmt.fmt_date(doc.get("valid_till"))
	days = fmt.days_between(_today(), doc.get("valid_till"))
	sq["expired"] = days is not None and days < 0
	if days is not None and days >= 0:
		sq["expires_in"] = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
	sq["total"] = _money(c, _total(doc))
	sq["rfqs"] = fmt.unique(r.get("request_for_quotation") for r in _rows(doc, "items"))
	c["pdf"]["sq"] = pdf_url("Supplier Quotation", doc.name)


def _purchase_receipt(c, doc, settings):
	rec = c["receipt"]
	rec["date"] = fmt.fmt_date(doc.get("posting_date"))
	rec["supplier_delivery_note"] = fmt.clean(doc.get("supplier_delivery_note"))
	items = _rows(doc, "items")
	rec["purchase_orders"] = fmt.unique(r.get("purchase_order") for r in items)
	rec["rejected"] = [
		{
			"label": fmt.clean(r.get("item_name")) or fmt.clean(r.get("item_code")),
			"item_code": fmt.clean(r.get("item_code")),
			"received": fmt.fmt_qty(r.get("received_qty")),
			"accepted": fmt.fmt_qty(r.get("qty")),
			"rejected": fmt.fmt_qty(r.get("rejected_qty")),
			"uom": fmt.clean(r.get("uom")),
			"purchase_order": fmt.clean(r.get("purchase_order")),
		}
		for r in items
		if fmt.to_number(r.get("rejected_qty")) > 0
	]


def _payment_entry(c, doc, settings):
	pay = c["payment"]
	pay["is_supplier"] = doc.get("party_type") == "Supplier"
	if doc.get("payment_type") == "Pay":
		c["currency"] = doc.get("paid_to_account_currency") or c["currency"]
		amount = doc.get("received_amount") or doc.get("paid_amount")
	else:
		c["currency"] = doc.get("paid_from_account_currency") or c["currency"]
		amount = doc.get("paid_amount")
	pay["date"] = fmt.fmt_date(doc.get("posting_date"))
	pay["amount"] = _money(c, amount)
	pay["method"] = fmt.clean(doc.get("custom_qbo_payment_method") or doc.get("mode_of_payment"))
	reference = fmt.clean(doc.get("custom_qbo_payment_ref_num"))
	if not reference:
		reference = fmt.clean(doc.get("reference_no"))
		if reference.startswith("QBO-"):
			reference = ""
	pay["reference"] = reference
	labels = {
		"Sales Invoice": "Invoice",
		"Purchase Invoice": "Your invoice",
		"Sales Order": "Order",
		"Purchase Order": "Purchase order",
	}
	remaining = 0.0
	for row in _rows(doc, "references"):
		ref_type, ref_name = row.get("reference_doctype"), row.get("reference_name")
		label = labels.get(ref_type, ref_type or "")
		if ref_type == "Purchase Invoice":
			bill_no = frappe.db.get_value("Purchase Invoice", ref_name, "bill_no")
			shown = f"{label} {bill_no} ({ref_name})" if bill_no else f"{label} {ref_name}"
		else:
			shown = f"{label} {ref_name}"
		balance = ""
		if ref_type in ("Sales Invoice", "Purchase Invoice"):
			value = fmt.to_number(frappe.db.get_value(ref_type, ref_name, "outstanding_amount"))
			remaining += max(value, 0)
			balance = "Paid in full" if value <= 0 else _money(c, value)
		pay["applied"].append(
			{"label": shown, "amount": _money(c, row.get("allocated_amount")), "balance": balance}
		)
	if fmt.to_number(doc.get("unallocated_amount")) > 0:
		pay["unallocated"] = _money(c, doc.get("unallocated_amount"))
	pay["has_remaining_balance"] = remaining > 0
	if remaining > 0:
		pay["remaining_balance"] = _money(c, remaining)


def _customer(c, doc, settings):
	cust = c["customer"]
	cust["has_portal"] = c["is_dealer"]
	cust["portal_url"] = frappe.utils.get_url("/portal")
	contact = doc.get("ill_purchasing_contact")
	if contact:
		cust["purchasing_contact"] = fmt.clean(frappe.db.get_value("Contact", contact, "full_name"))
	c["party_name"] = fmt.clean(doc.get("customer_name")) or doc.name


def _crm_deal(c, doc, settings):
	deal = c["deal"]
	deal["organization"] = fmt.clean(doc.get("organization") or doc.get("organization_name"))
	deal["status"] = fmt.clean(doc.get("status"))
	deal["next_step"] = fmt.clean(doc.get("next_step"))
	deal["expected_closure_date"] = fmt.fmt_date(doc.get("expected_closure_date"))
	deal["lost_reason"] = fmt.clean(doc.get("lost_reason"))
	c["party_name"] = deal["organization"] or c["party_name"]
	quote = _latest_deal_quote(doc.name)
	if quote:
		_quote_summary(c, frappe.get_doc("Quotation", quote))
		deal["has_quote"] = True


def _latest_deal_quote(deal):
	"""The newest submitted, not-cancelled Quotation for a CRM Deal (via crm_deal or quotation_to)."""
	filters = {"docstatus": 1}
	names = []
	if _has_field("Quotation", "crm_deal"):
		names += frappe.get_all(
			"Quotation", filters={**filters, "crm_deal": deal}, pluck="name", order_by="transaction_date desc"
		)
	names += frappe.get_all(
		"Quotation",
		filters={**filters, "quotation_to": "CRM Deal", "party_name": deal},
		pluck="name",
		order_by="transaction_date desc",
	)
	for name in names:
		if frappe.has_permission("Quotation", "read", name):
			return name
	return None


def _crm_lead(c, doc, settings):
	c["party_name"] = fmt.clean(doc.get("organization")) or c["party_name"]
	c["deal"]["organization"] = c["party_name"]
	c["deal"]["status"] = fmt.clean(doc.get("status"))


BUILDERS = {
	"Quotation": _quotation,
	"Sales Order": _sales_order,
	"Sales Invoice": _sales_invoice,
	"Delivery Note": _delivery_note,
	"Purchase Order": _purchase_order,
	"Request for Quotation": _request_for_quotation,
	"Supplier Quotation": _supplier_quotation,
	"Purchase Receipt": _purchase_receipt,
	"Payment Entry": _payment_entry,
	"Customer": _customer,
	"CRM Deal": _crm_deal,
	"CRM Lead": _crm_lead,
}


def _finish(c, settings):
	"""Render the HTML blocks from the finished context."""
	c["settings"]["pickup_address"] = fmt.text_to_html(settings.get("pickup_address"))
	c["settings"]["pickup_hours"] = fmt.text_to_html(settings.get("pickup_hours"))
	b = c["blocks"]
	b["lines"] = blocks.lines_table(c["lines"], c["lines_more"], amounts=True)
	b["lines_no_prices"] = blocks.lines_table(c["lines"], c["lines_more"], amounts=False)
	b["supplier_lines"] = blocks.supplier_lines_table(c["lines"], c["lines_more"], amounts=True)
	b["supplier_lines_no_prices"] = blocks.supplier_lines_table(c["lines"], c["lines_more"], amounts=False)
	b["order_schedule"] = blocks.schedule_table(
		c["order"]["schedule"] if len(c["order"]["schedule"]) > 1 else []
	)
	b["invoice_schedule"] = blocks.schedule_table(c["invoice"]["schedule"])
	b["purchase_schedule"] = blocks.schedule_table(
		c["purchase"]["schedule"] if len(c["purchase"]["schedule"]) > 1 else []
	)
	b["payments"] = blocks.payments_table(c["invoice"]["payments"])
	b["applied"] = blocks.applied_table(c["payment"]["applied"])
	b["rejected"] = blocks.rejected_table(c["receipt"]["rejected"])
	b["tracking"] = blocks.tracking(c["shipment"])
	b["pay_button"] = blocks.button(c["pay_link"], "Pay this invoice online")
	b["signature"] = blocks.signature(c["poc"], c["company"])
	b["shipping_address"] = blocks.address(
		c["order"]["shipping_address"] or c["shipment"]["shipping_address"]
	)
	b["billing_address"] = blocks.address(c["invoice"]["billing_address"])
	b["ship_to"] = blocks.address(c["purchase"]["ship_to"] or c["rfq"]["ship_to"])
	b["pickup_address"] = blocks.address(c["settings"]["pickup_address"])
