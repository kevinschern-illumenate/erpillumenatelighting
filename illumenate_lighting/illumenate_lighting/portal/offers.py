"""Issued ERP offers and buyer responses, separate from technical quote intake."""

import hashlib
import json

import frappe
from frappe.utils import getdate, now, nowdate

from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.portal.access import can_read_schedule, get_actor
from illumenate_lighting.illumenate_lighting.portal.offer_contract import (
	LINE_FIELDS,
	assert_conversion_matches,
	commercial_snapshot,
)
from illumenate_lighting.illumenate_lighting.portal.staff import allowed, require

DOCTYPE = "ilL-Quote-Offer"
REQUEST = "ilL-Quote-Request"
SCHEDULE = "ilL-Project-Fixture-Schedule"


def commercial_customer(schedule):
	return (
		frappe.db.get_value("ilL-Project", schedule.ill_project, "owner_customer")
		if schedule.ill_project
		else None
	) or schedule.customer


def _snapshot(quotation):
	return json.loads(frappe.as_json(commercial_snapshot(quotation, customer=quotation.party_name)))


def _scope(schedule):
	volatile = {"modified", "modified_by", "creation", "owner", "docstatus"}
	return fingerprint(
		json.loads(
			frappe.as_json(
				{
					"schedule": schedule.name,
					"project": schedule.ill_project,
					"customer": commercial_customer(schedule),
					"notes": schedule.notes,
					"lines": [
						{key: value for key, value in row.as_dict().items() if key not in volatile}
						for row in schedule.lines
					],
				}
			)
		)
	)


def _save(doc):
	doc.flags.offer_write = True
	return doc.insert(ignore_permissions=True) if doc.is_new() else doc.save(ignore_permissions=True)


def can_read(offer, user=None):
	actor = get_actor(user)
	if actor.is_guest:
		return False
	if allowed("sales", actor.user):
		return frappe.has_permission("Quotation", "read", doc=offer.quotation, user=actor.user)
	return actor.is_company_dealer_for(offer.customer) and can_read_schedule(
		frappe.get_doc(SCHEDULE, offer.schedule), actor.user
	)


def has_permission(doc, ptype="read", user=None):
	# The dealer service projects public commercial fields. Native records also
	# contain internal build snapshots and are restricted to sales staff.
	return allowed("sales", user) and ptype in ("read", "select", "print", "report") and can_read(doc, user)


def get_permission_query_conditions(user=None):
	actor = get_actor(user)
	if allowed("sales", actor.user) and frappe.has_permission("Quotation", "read", user=actor.user):
		return ""
	if actor.is_guest or not actor.is_dealer or not actor.customer:
		return "1=0"
	return "`tabilL-Quote-Offer`.customer=" + frappe.db.escape(actor.customer)


def before_submit(quotation, method=None):
	if not quotation.get("ill_quote_request"):
		return
	require("sales")
	if quotation.quotation_to != "Customer":
		frappe.throw("Portal offers must be addressed to a Customer")
	request = frappe.get_doc(REQUEST, quotation.ill_quote_request)
	schedule = frappe.get_doc(SCHEDULE, request.schedule)
	if quotation.get(
		"ill_fixture_schedule"
	) != request.schedule or quotation.party_name != commercial_customer(schedule):
		frappe.throw("Quotation customer and schedule must match the quote request's owning company")
	if request.customer != quotation.party_name:
		frappe.throw("The request's commercial customer must be reconciled before issuing this offer")
	if (
		request.state == "CLOSED"
		or schedule.is_locked
		or schedule.status in ("ORDER_REQUESTED", "ORDERED", "CLOSED", "ISSUE")
	):
		frappe.throw("Use an open request for an editable schedule revision")
	if quotation.valid_till and getdate(quotation.valid_till) < getdate(nowdate()):
		frappe.throw("An expired Quotation cannot be issued as a new portal offer")
	if not quotation.items or any(
		float(row.qty or 0) <= 0 or row.get("is_alternative") for row in quotation.items
	):
		frappe.throw("Resolve alternative and unquantified rows before issuing a portal offer")
	if not frappe.has_permission("Quotation", "submit", doc=quotation):
		frappe.throw("ERP Quotation submit permission required", frappe.PermissionError)


def on_submit(quotation, method=None):
	if not quotation.get("ill_quote_request"):
		return
	before_submit(quotation)
	if frappe.db.exists(DOCTYPE, {"quotation": quotation.name}):
		return
	request = frappe.get_doc(REQUEST, quotation.ill_quote_request)
	frappe.db.sql(
		"select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", request.schedule
	)
	frappe.db.sql("select name from `tabilL-Quote-Request` where name=%s for update", request.name)
	request.reload()
	schedule = frappe.get_doc(SCHEDULE, request.schedule)
	data = _snapshot(quotation)
	data["exclusions"] = [
		{
			"line": row.name,
			"designation": row.line_id,
			"reason": "Other manufacturer specification; not offered for sale",
		}
		for row in schedule.lines
		if row.manufacturer_type == "OTHER"
		and not any(item.get("ill_schedule_line_id") == row.name for item in quotation.items)
	]
	offer = _save(
		frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"quotation": quotation.name,
				"quote_request": request.name,
				"schedule": schedule.name,
				"customer": quotation.party_name,
				"state": "ISSUED",
				"valid_until": quotation.valid_till,
				"issued_by": frappe.session.user,
				"issued_on": now(),
				"snapshot_json": canonical_json(data),
				"snapshot_hash": fingerprint(data),
				"schedule_hash": _scope(schedule),
			}
		)
	)
	# The PDF is generated once from this submitted ERP document and retained privately.
	content = frappe.get_print("Quotation", quotation.name, as_pdf=True)
	from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

	validate_content(f"{offer.name}.pdf", content)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{offer.name}.pdf",
			"content": content,
			"is_private": 1,
			"owner": "Administrator",
			"attached_to_doctype": DOCTYPE,
			"attached_to_name": offer.name,
		}
	).insert(ignore_permissions=True)
	if not file.is_private or not file.file_url.startswith("/private/files/"):
		frappe.throw("Offer PDF storage must remain private")
	offer.pdf_file, offer.pdf_sha256 = file.name, hashlib.sha256(content).hexdigest()
	_save(offer)
	if request.latest_issued_offer:
		previous = frappe.get_doc(DOCTYPE, request.latest_issued_offer)
		if previous.state == "ACCEPTED":
			frappe.throw("An accepted offer requires the order-change workflow, not silent replacement")
		if previous.state == "ISSUED":
			previous.state = "SUPERSEDED"
			_save(previous)
	request.latest_offer, request.latest_issued_offer, request.state = quotation.name, offer.name, "ISSUED"
	request.save(ignore_permissions=True)
	# This status denotes a real issued offer, never a generic quotation intake.
	schedule.status = "QUOTED"
	schedule._validate_configuration_status()
	schedule.set_lifecycle_status("QUOTED", note=f"Issued offer {offer.name}")


def on_cancel(quotation, method=None):
	name = frappe.db.get_value(DOCTYPE, {"quotation": quotation.name}, "name")
	if name:
		offer = frappe.get_doc(DOCTYPE, name)
		offer.state = "CANCELLED"
		_save(offer)


@frappe.whitelist(methods=["POST"])
def prepare_quotation(request_name, company):
	require("sales")
	if not frappe.has_permission("Quotation", "create"):
		frappe.throw("ERP Quotation creation permission required", frappe.PermissionError)
	request = frappe.get_doc(REQUEST, request_name)
	frappe.db.sql(
		"select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", request.schedule
	)
	frappe.db.sql("select name from `tabilL-Quote-Request` where name=%s for update", request.name)
	request.reload()
	existing = frappe.db.get_value(
		"Quotation", {"ill_quote_request": request.name, "docstatus": 0}, ["name", "company"], as_dict=True
	)
	if existing:
		if existing.company != company:
			frappe.throw("The existing draft Quotation uses a different selling company")
		return {"quotation": existing.name, "already_existed": True}
	if request.state in ("CLOSED", "ISSUED"):
		frappe.throw("Amend the existing offer or reopen the request before preparing another Quotation")
	schedule = frappe.get_doc(SCHEDULE, request.schedule)
	if schedule.is_locked or schedule.status not in ("DRAFT", "READY", "QUOTED"):
		frappe.throw("This schedule revision cannot be quoted")
	if request.customer != commercial_customer(schedule):
		frappe.throw("Reconcile the quote request customer before preparation")
	quotation = frappe.new_doc("Quotation")
	quotation.update(
		{
			"quotation_to": "Customer",
			"party_name": request.customer,
			"company": company,
			"order_type": "Sales",
			"transaction_date": nowdate(),
			"ill_fixture_schedule": request.schedule,
			"ill_quote_request": request.name,
		}
	)
	quotation.run_method("set_missing_values")
	counts = schedule.append_quote_lines(
		quotation,
		include_accessories=True,
		include_other=False,
		tape_neon_mode="configured_item",
		require_bom=True,
	)
	if not counts.get("rows_added"):
		frappe.throw("The request has no sellable configured lines")
	quotation.run_method("calculate_taxes_and_totals")
	quotation.insert()
	request.state, request.assigned_to = "UNDER_REVIEW", frappe.session.user
	request.save(ignore_permissions=True)
	return {"quotation": quotation.name, "already_existed": False, "warnings": counts.get("messages", [])}


def _load(name):
	offer = frappe.get_doc(DOCTYPE, name)
	if not can_read(offer):
		frappe.throw("Offer unavailable", frappe.PermissionError)
	return offer


def _current(offer):
	quotation = frappe.get_doc("Quotation", offer.quotation)
	request = frappe.get_doc(REQUEST, offer.quote_request)
	schedule = frappe.get_doc(SCHEDULE, offer.schedule)
	if (
		offer.state != "ISSUED"
		or request.latest_issued_offer != offer.name
		or quotation.docstatus != 1
		or quotation.status in ("Lost", "Expired", "Cancelled")
	):
		frappe.throw("This offer is no longer open for response")
	if offer.valid_until and getdate(offer.valid_until) < getdate(nowdate()):
		frappe.throw("This offer has expired; request an updated Quotation")
	if schedule.is_locked or _scope(schedule) != offer.schedule_hash:
		frappe.throw("The schedule revision changed; Sales must issue an updated offer")
	if commercial_customer(schedule) != offer.customer or quotation.party_name != offer.customer:
		frappe.throw("Offer customer changed; contact Sales")
	frozen = json.loads(offer.snapshot_json)
	live = _snapshot(quotation)
	if any(live.get(key) != value for key, value in frozen.items() if key != "exclusions"):
		frappe.throw("The ERP Quotation no longer matches the issued terms")
	return quotation, request, schedule, frozen


@frappe.whitelist(methods=["POST"])
def respond(offer_name, action, expected_hash, note=None, po_no=None, requested_date=None):
	offer = _load(offer_name)
	if not get_actor().is_company_dealer_for(offer.customer):
		frappe.throw("Only a buyer for this company may respond", frappe.PermissionError)
	if action not in ("ACCEPT", "DECLINE", "REQUEST_REVISION"):
		frappe.throw("Choose an offer response")
	if action != "ACCEPT" and not (note or "").strip():
		frappe.throw("Add a note for Sales")
	if len(note or "") > 4000 or len(po_no or "") > 140:
		frappe.throw("Shorten the response note or PO number")
	requested_date = str(getdate(requested_date)) if requested_date else None
	frappe.db.sql(
		"select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", offer.schedule
	)
	frappe.db.sql("select name from `tabilL-Quote-Request` where name=%s for update", offer.quote_request)
	frappe.db.sql("select name from `tabQuotation` where name=%s for update", offer.quotation)
	frappe.db.sql("select name from `tabilL-Quote-Offer` where name=%s for update", offer.name)
	offer = _load(offer_name)
	if not get_actor().is_company_dealer_for(offer.customer):
		frappe.throw("Only a current buyer for this company may respond", frappe.PermissionError)
	if expected_hash != offer.snapshot_hash:
		frappe.throw("Review the current offer before responding")
	body_hash = fingerprint(
		{
			"action": action,
			"hash": expected_hash,
			"note": (note or "").strip(),
			"po_no": (po_no or "").strip(),
			"requested_date": requested_date or None,
		}
	)
	if offer.response_hash:
		if offer.response_hash != body_hash:
			frappe.throw("This offer already has a different buyer response")
		return {
			"offer": offer.name,
			"state": offer.state,
			"sales_order": offer.sales_order,
			"already_existed": True,
		}
	quotation, request, schedule, frozen = _current(offer)
	if action == "ACCEPT":
		if schedule.get_linked_sales_order():
			frappe.throw("This schedule already has an order request; review that request with Sales")
		if not requested_date or getdate(requested_date) < getdate(nowdate()):
			frappe.throw("Choose a requested delivery date on or after today")
		from erpnext.selling.doctype.quotation.quotation import _make_sales_order

		from illumenate_lighting.illumenate_lighting.portal.order_review import capture

		order = _make_sales_order(quotation.name, ignore_permissions=True)
		order.ill_fixture_schedule, order.ill_quote_offer = schedule.name, offer.name
		order.po_no, order.delivery_date = (po_no or "").strip(), requested_date
		order.ill_requested_delivery_date = requested_date
		by_source = {row.name: row for row in quotation.items}
		for row in order.items:
			source = by_source.get(row.quotation_item)
			if not source:
				frappe.throw("ERP conversion returned an unrelated quotation row")
			for key in LINE_FIELDS:
				if key.startswith("ill_") and row.meta.has_field(key):
					row.set(key, source.get(key))
			row.delivery_date = requested_date
		order.insert(ignore_permissions=True)
		mapped = json.loads(frappe.as_json(commercial_snapshot(order, customer=order.customer)))
		try:
			assert_conversion_matches(frozen, mapped)
		except ValueError as exc:
			frappe.throw(str(exc))
		capture(order)
		offer.sales_order, offer.state = order.name, "ACCEPTED"
		schedule.set_lifecycle_status("ORDER_REQUESTED", sales_order=order.name)
		request.state = "CLOSED"
	else:
		offer.state = "DECLINED" if action == "DECLINE" else "REVISION_REQUESTED"
		request.state = "CLOSED" if action == "DECLINE" else "UNDER_REVIEW"
	offer.response_hash, offer.responded_by, offer.responded_on = body_hash, frappe.session.user, now()
	offer.response_note = (note or "").strip()
	_save(offer)
	request.save(ignore_permissions=True)
	return {
		"offer": offer.name,
		"state": offer.state,
		"sales_order": offer.sales_order,
		"already_existed": False,
	}


@frappe.whitelist()
def detail(offer_name):
	offer = _load(offer_name)
	data = json.loads(offer.snapshot_json)
	public_line_fields = {
		"item_code",
		"item_name",
		"description",
		"qty",
		"uom",
		"rate",
		"amount",
		"ill_section_label",
		"ill_fixture_type",
		"additional_notes",
	}
	data["items"] = [
		{key: value for key, value in row.items() if key in public_line_fields} for row in data["items"]
	]
	data["taxes"] = [
		{key: row.get(key) for key in ("description", "rate", "tax_amount", "total")} for row in data["taxes"]
	]
	can_respond = get_actor().is_company_dealer_for(offer.customer) and offer.state == "ISSUED"
	reason = None
	if can_respond:
		try:
			_current(offer)
		except frappe.ValidationError as exc:
			can_respond, reason = False, str(exc)
	file_url = frappe.db.get_value("File", offer.pdf_file, "file_url") if offer.pdf_file else None
	return {
		"name": offer.name,
		"quotation": offer.quotation,
		"state": offer.state,
		"valid_until": offer.valid_until,
		"issued_on": offer.issued_on,
		"snapshot_hash": offer.snapshot_hash,
		"snapshot": data,
		"pdf_url": file_url,
		"sales_order": offer.sales_order,
		"response_note": offer.response_note,
		"can_respond": can_respond,
		"unavailable_reason": reason,
	}


@frappe.whitelist()
def list_offers(after=None, limit=20):
	actor = get_actor()
	if actor.is_guest:
		frappe.throw("Sign in to view quotes", frappe.PermissionError)
	filters = {}
	if not (allowed("sales") and frappe.has_permission("Quotation", "read")):
		if not actor.is_dealer or not actor.customer:
			return {"offers": [], "next_cursor": None}
		filters["customer"] = actor.customer
	if after:
		filters["name"] = ["<", after]
	limit = max(1, min(int(limit), 50))
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		fields=["name", "quotation", "customer", "schedule", "state", "valid_until", "issued_on"],
		order_by="name desc",
		limit_page_length=limit + 1,
	)
	return {
		"offers": [row for row in rows[:limit] if can_read(row)],
		"next_cursor": rows[limit - 1].name if len(rows) > limit else None,
	}
