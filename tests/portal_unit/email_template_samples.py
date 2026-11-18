"""Sample render contexts for the email templates: the tests and tools/render_email_previews.py share them.

``rich()`` fills every value a template can print; ``empty()`` is what a template gets for
a missing or unreadable document. Both go through ``context._finish`` so the HTML blocks
are the real ones. The Jinja environment mirrors Frappe's: sandboxed, DebugUndefined
(a missing variable prints as literal ``{{ x }}``), no autoescape.
"""

import copy
import types

from jinja2 import DebugUndefined
from jinja2.sandbox import SandboxedEnvironment

from illumenate_lighting.illumenate_lighting.email_templates import blocks, formatting
from illumenate_lighting.illumenate_lighting.email_templates.settings import DEFAULTS

PDF = "https://illumenatelighting.v.frappe.cloud/api/method/frappe.utils.print_format.download_pdf?key=k"


def load_context_module():
	"""context.py with a stand-in ``frappe`` (it is only touched by the lookups, not by _finish)."""
	import importlib.util
	import sys
	from unittest.mock import MagicMock, patch

	fake = types.ModuleType("frappe")
	fake.db = MagicMock()
	fake.utils = MagicMock()
	fake.log_error = MagicMock()
	spec = importlib.util.spec_from_file_location(
		"isolated_email_context", "illumenate_lighting/illumenate_lighting/email_templates/context.py"
	)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe": fake}):
		spec.loader.exec_module(module)
	return module


CONTEXT = load_context_module()


def settings(**overrides):
	values = dict(DEFAULTS)
	values.update(
		pickup_address="2130 Industrial Way\nUnit B\nBellingham, WA 98226",
		pickup_hours="Mon-Fri 8am-4pm",
		sales_contact_phone="(360) 555-0100",
	)
	values.update(overrides)
	return values


def empty(doctype="", name=""):
	c = CONTEXT.skeleton()
	c["doctype"], c["name"] = doctype, name
	c["poc"] = CONTEXT._fallback_contact(doctype, settings())
	CONTEXT._finish(c, settings())
	return c


def _lines(with_amounts=True):
	rows = [
		{
			"ill_fixture_type": "Type A1",
			"ill_section_label": "Kitchen",
			"item_name": "ilL Linear 1 in. Recessed, 3000K",
			"item_code": "ILL-LIN-A1",
			"qty": 4,
			"uom": "Nos",
			"rate": 212.5,
			"amount": 850,
			"supplier_part_no": "SP-1",
			"schedule_date": "2026-12-01",
		},
		{
			"ill_fixture_type": "Type B",
			"ill_section_label": "",
			"item_name": "LED Neon Side-Bend 24V",
			"item_code": "ILL-NEON-B",
			"qty": 32.5,
			"uom": "Foot",
			"rate": 18,
			"amount": 585,
			"supplier_part_no": "",
			"schedule_date": "2026-12-01",
		},
		{
			"item_name": "Power Supply 96W 24V",
			"item_code": "PS-96-24",
			"qty": 2,
			"uom": "Nos",
			"rate": 64,
			"amount": 128,
		},
	]
	return formatting.summarize_lines(rows, limit=2, with_amounts=with_amounts)


def rich(doctype="Sales Order", name="ilL-SAL-ORD-Acme Integration-00012", **flags):
	"""A context with every optional value filled. ``flags`` switch the variants on."""
	c = CONTEXT.skeleton()
	lines, more = _lines(with_amounts=doctype not in ("Delivery Note", "Request for Quotation"))
	schedule = [
		{
			"label": "Deposit",
			"due_date": "Nov 18, 2026",
			"due_date_raw": "2026-11-18",
			"amount": "$781.50",
			"outstanding": "$781.50",
			"outstanding_raw": 781.5,
			"portion": "50%",
		},
		{
			"label": "Balance before shipping",
			"due_date": "Dec 9, 2026",
			"due_date_raw": "2026-12-09",
			"amount": "$781.50",
			"outstanding": "$781.50",
			"outstanding_raw": 781.5,
			"portion": "50%",
		},
	]
	c.update(
		found=True,
		doctype=doctype,
		name=name,
		docstatus=2 if flags.get("cancelled") else 1,
		is_cancelled=bool(flags.get("cancelled")),
		party_name="Acme Integration",
		greeting_name="Jane",
		contact_email="jane@acme.example",
		date="November 18, 2026",
		grand_total="$1,563.00",
		po_no="" if flags.get("no_po") else "4471-B",
		po_date="November 17, 2026",
		project_name="Harbor View Residence",
		schedule_name="Main floor",
		job_name="Harbor View Residence",
		portal_url="https://illumenatelighting.v.frappe.cloud/portal/orders/" + name,
		is_dealer=True,
		lines=lines,
		lines_more=more,
		poc={
			"name": "Sam Rivera",
			"email": "sam@illumenate.lighting",
			"phone": "(360) 555-0101",
			"title": "Dealer Sales",
		},
		pay_link="" if flags.get("no_pay_link") else "https://connect.intuit.com/pay/abc",
		pay_instructions="ACH: Bank of Example, routing 000000000<br>Checks payable to ilLumenate Lighting",
		sales_orders=[
			{"name": "ilL-SAL-ORD-Acme Integration-00012", "pdf": PDF, "complete": not flags.get("partial")},
			{"name": "ilL-SAL-ORD-Acme Integration-00013", "pdf": PDF, "complete": True},
		],
	)
	c["portal"] = {
		k: f"https://illumenatelighting.v.frappe.cloud/portal/{k}"
		for k in ("home", "orders", "drawings", "support")
	}
	c["pdf"] = {k: PDF for k in c["pdf"]}
	c["quote"].update(
		number="ilL-SAL-QTN-Acme Integration-00031",
		date="November 10, 2026",
		valid_till="December 10, 2026",
		days_left=-2 if flags.get("expired") else 22,
		expires_in="" if flags.get("expired") else "in 22 days",
		expired=bool(flags.get("expired")),
		status="Open",
		total="$1,563.00",
		revised_from="ilL-SAL-QTN-Acme Integration-00030",
		lost_reason="Price",
		crm_deal="CRM-DEAL-2026-00032",
	)
	hold = flags.get("hold", "")
	c["order"].update(
		date="November 18, 2026",
		status="To Deliver and Bill",
		progress="Partly shipped" if flags.get("partial") else "In production",
		total="$1,563.00",
		ship_date="December 9, 2026",
		ship_date_label="Estimated ship date",
		delivery_promise="December 12, 2026" if flags.get("confirmed", True) else "",
		delivery_promise_label="Confirmed delivery date" if flags.get("confirmed", True) else "",
		requested_date="December 5, 2026",
		shipping_address="Acme Integration<br>1200 Harbor Ave<br>Seattle, WA 98101",
		receiving_instructions="Dock 3, call 30 min ahead",
		shipping_instructions="Liftgate required",
		on_hold=bool(hold),
		hold_message=formatting.hold_message(hold),
		will_call=True,
		proforma=True,
		per_delivered=40 if flags.get("partial") else 0,
		partly_shipped=bool(flags.get("partial")),
		fully_shipped=False,
		advance_paid="$0.00",
		payment_terms="50% deposit, 50% before shipping",
		schedule=schedule,
		payment_due={
			"label": "Deposit",
			"amount": "$781.50",
			"due_date": "November 18, 2026",
			"portion": "50%",
		},
		shipments=[
			{
				"name": "ilL-MAT-DN-Acme Integration-00004",
				"date": "November 20, 2026",
				"carrier": "UPS",
				"number": "1Z999",
				"url": "https://www.ups.com/track?tracknum=1Z999",
			}
		],
		invoices=[
			{
				"name": "ilL-ACC-SINV-Acme Integration-00020",
				"due_date": "December 18, 2026",
				"outstanding": "$781.50",
				"is_paid": False,
			}
		],
	)
	days_overdue = flags.get("days_overdue", 0)
	paid = bool(flags.get("paid"))
	c["invoice"].update(
		date="November 18, 2026",
		due_date="December 18, 2026",
		days_to_due=-days_overdue if days_overdue else 30,
		days_overdue=days_overdue,
		overdue_stage=formatting.overdue_stage(days_overdue),
		status="Paid" if paid else "Unpaid",
		total="$1,563.00",
		outstanding="$0.00" if paid else "$781.50",
		paid_to_date="$1,563.00" if paid else "$781.50",
		has_balance=not paid,
		is_partly_paid=not paid,
		is_paid=paid,
		is_return=bool(flags.get("is_return")),
		return_against="ilL-ACC-SINV-Acme Integration-00019" if flags.get("is_return") else "",
		billing_address="Acme Integration<br>PO Box 77<br>Seattle, WA 98111",
		payment_terms="Net 30",
		schedule=schedule,
		payments=[{"date": "Nov 18, 2026", "amount": "$781.50", "method": "ACH", "reference": "TRX-55"}],
		delivery_notes=["ilL-MAT-DN-Acme Integration-00004"],
	)
	c["shipment"].update(
		date="November 20, 2026",
		carrier="UPS",
		number="1Z999",
		url="https://www.ups.com/track?tracknum=1Z999",
		is_return=bool(flags.get("is_return")),
		partial=bool(flags.get("partial")),
		shipping_address="Acme Integration<br>1200 Harbor Ave<br>Seattle, WA 98101",
		instructions="Liftgate required",
		packing_slips=[{"name": "MAT-PAC-2026-00013", "pdf": PDF}],
	)
	c["purchase"].update(
		date="November 18, 2026",
		required_by="December 1, 2026",
		ship_to="ilLumenate Lighting<br>2130 Industrial Way<br>Bellingham, WA 98226",
		incoterm="FOB",
		named_place="Shenzhen",
		freight_mode="Ocean LCL",
		payment_terms="30% deposit, 70% before shipping",
		schedule=schedule,
		vendor_order_no="" if flags.get("unconfirmed") else "SO-88812",
		promised_ship_date="" if flags.get("no_promise") else "November 28, 2026",
		eta="December 20, 2026",
		sent_on="November 18, 2026",
		days_since_sent=3,
		confirmed=not flags.get("unconfirmed"),
		drop_ship_customer="Acme Integration",
		to_email="orders@vendor.example",
		received_pct=25,
		revised_from="PUR-ORD-2026-00056",
		total="$4,210.00",
	)
	c["rfq"].update(
		date="November 18, 2026",
		required_by="December 15, 2026",
		reply_by="November 25, 2026",
		incoterm="EXW",
		named_place="Dongguan",
		ship_to="ilLumenate Lighting<br>2130 Industrial Way",
	)
	c["supplier_quote"].update(
		date="November 19, 2026",
		valid_till="December 19, 2026",
		expires_in="in 31 days",
		total="$3,980.00",
		rfqs=["PUR-RFQ-2026-00003"],
	)
	c["receipt"].update(
		date="November 21, 2026",
		supplier_delivery_note="DN-7781",
		purchase_orders=["PUR-ORD-2026-00057"],
		rejected=[
			{
				"label": "Aluminum channel 2m",
				"item_code": "EXT-2M",
				"received": "200",
				"accepted": "180",
				"rejected": "20",
				"uom": "Nos",
				"purchase_order": "PUR-ORD-2026-00057",
			}
		],
	)
	c["payment"].update(
		date="November 18, 2026",
		amount="$781.50",
		method="ACH",
		reference="TRX-55",
		is_supplier=doctype == "Payment Entry" and flags.get("supplier", False),
		applied=[
			{
				"label": "Invoice ilL-ACC-SINV-Acme Integration-00020",
				"amount": "$781.50",
				"balance": "$781.50",
			}
		],
		unallocated="$20.00",
		remaining_balance="$781.50",
		has_remaining_balance=True,
	)
	c["customer"].update(
		has_portal=True,
		portal_url="https://illumenatelighting.v.frappe.cloud/portal",
		purchasing_contact="Jane Doe",
	)
	c["deal"].update(
		organization="Acme Integration",
		status="Proposal/Quotation",
		next_step="Send samples",
		expected_closure_date="December 1, 2026",
		lost_reason="Price",
		has_quote=not flags.get("no_quote"),
	)
	CONTEXT._finish(c, settings())
	return c


def environment(context_for):
	"""A Jinja environment like Frappe's, with our Jinja methods; ``context_for(doctype, name)`` supplies c."""
	env = SandboxedEnvironment(undefined=DebugUndefined)
	env.filters.update({"len": len, "int": int, "str": str, "flt": float})
	env.globals.update(
		ill_email_context=lambda doctype=None, name=None: copy.deepcopy(
			context_for(CONTEXT._plain(doctype), CONTEXT._plain(name))
		),
		ill_money=lambda value, currency="USD": formatting.fmt_money(
			CONTEXT._plain(value), CONTEXT._plain(currency) or "USD"
		),
		ill_date=lambda value: formatting.fmt_date(CONTEXT._plain(value)),
		ill_print_pdf_url=lambda *args, **kwargs: PDF,
	)
	return env


# Fields each DocType's document dict carries in Frappe (subjects read them at the top level).
DOC_FIELDS = {
	"Quotation": {"valid_till": "2026-12-10", "customer_name": "Acme Integration", "po_no": None},
	"Sales Order": {
		"po_no": "4471-B",
		"ill_estimated_ship_date": "2026-12-09",
		"customer_name": "Acme Integration",
	},
	"Delivery Note": {"po_no": "4471-B", "is_return": 0},
	"Sales Invoice": {
		"po_no": "4471-B",
		"due_date": "2026-12-18",
		"outstanding_amount": 781.5,
		"currency": "USD",
	},
	"Payment Entry": {
		"paid_amount": 781.5,
		"received_amount": 781.5,
		"paid_from_account_currency": "USD",
		"paid_to_account_currency": "USD",
	},
	"Purchase Order": {"docstatus": 1},
	"Purchase Receipt": {"supplier_delivery_note": "DN-7781"},
	"CRM Deal": {"organization": "Acme Integration"},
}


def doc_dict(doctype, name):
	values = {"doctype": doctype or "Note", "name": name, "docstatus": 1, "owner": "sam@illumenate.lighting"}
	values.update(DOC_FIELDS.get(doctype, {}))
	return values
