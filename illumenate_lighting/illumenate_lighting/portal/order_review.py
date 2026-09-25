"""Durable commercial intake and a shared native Sales Order approval guard."""

import json

import frappe
from frappe.utils import now

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.portal.access import get_actor
from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

DOCTYPE = "ilL-Order-Intake"
APPROVER_ROLE = "ilL Order Approver"
REVIEW_ROLE = "ilL Sales Review"


def snapshot(order):
	fields = (
		"customer",
		"company",
		"currency",
		"selling_price_list",
		"po_no",
		"po_date",
		"terms",
		"grand_total",
		"customer_address",
		"shipping_address_name",
		"contact_person",
		"ill_quote_offer",
		"ill_requested_delivery_date",
		"ill_confirmed_delivery_date",
		"address_display",
		"shipping_address",
		"contact_display",
		"contact_email",
		"contact_mobile",
		"ill_receiving_instructions",
		"ill_shipping_instructions",
	)
	line_fields = (
		"name",
		"item_code",
		"qty",
		"uom",
		"conversion_factor",
		"rate",
		"amount",
		"description",
		"delivery_date",
		"ill_fixture_type",
		"ill_section_label",
		"additional_notes",
		"ill_schedule_line_id",
		"ill_configurator_request",
		"ill_configured_group",
		"ill_configured_fixture",
		"ill_configured_tape_neon",
		"ill_configured_led_sheet",
		"ill_bom",
		"ill_configuration_json",
	)
	# Convert Frappe dates/Decimals with its serializer before canonical hashing.
	return json.loads(
		frappe.as_json(
			{
				"schema_version": 1,
				**{key: order.get(key) for key in fields},
				"items": [{key: row.get(key) for key in line_fields} for row in order.items],
			}
		)
	)


def _staff(order, *, approve=False):
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	allowed = {"System Manager", APPROVER_ROLE} if approve else {"System Manager", APPROVER_ROLE, REVIEW_ROLE}
	if user != "Administrator" and (
		not roles.intersection(allowed)
		or frappe.db.get_value("User", user, "user_type") != "System User"
		or not frappe.db.get_value("User", user, "enabled")
	):
		frappe.throw("Staff review access required", frappe.PermissionError)
	if not frappe.has_permission("Sales Order", "submit" if approve else "write", doc=order):
		frappe.throw("ERP Sales Order permission required", frappe.PermissionError)


def capture(order, requested_by=None):
	"""Called inside the order creation transaction, with the schedule lock held."""
	existing = frappe.db.get_value(DOCTYPE, {"sales_order": order.name}, "name")
	if existing:
		return existing
	data = snapshot(order)
	intake_context = frappe.flags.get("ill_order_intake_context") or {}
	actor = get_actor(requested_by)
	buyer_submitted = actor.is_company_dealer_for(order.customer)
	request = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"sales_order": order.name,
			"schedule": order.get("ill_fixture_schedule"),
			"customer": order.customer,
			"requested_by": requested_by or frappe.session.user,
			"state": "SUBMITTED" if buyer_submitted else "UNDER_REVIEW",
			"intake_key": intake_context.get("key"),
			"intake_hash": intake_context.get("hash"),
			"intake_json": canonical_json(intake_context["data"]) if intake_context.get("data") else None,
			"request_snapshot": canonical_json(data),
			"request_hash": fingerprint(data),
			"acknowledged_hash": None,
			"acknowledged_by": None,
			"acknowledged_on": None,
		}
	).insert(ignore_permissions=True)
	return request.name


def lock_orders(*order_names):
	"""Use the conversion lock order: schedules, then orders, then intake/requests."""
	names = sorted({name for name in order_names if name})
	schedules = {name: frappe.db.get_value("Sales Order", name, "ill_fixture_schedule") for name in names}
	for schedule in sorted({value for value in schedules.values() if value}):
		frappe.db.sql("select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", schedule)
	for name in names:
		frappe.db.sql("select name from `tabSales Order` where name=%s for update", name)
		if frappe.db.get_value("Sales Order", name, "ill_fixture_schedule") != schedules[name]:
			frappe.throw("The order's source schedule changed. Reload and retry.")


def _load(order_name):
	lock_orders(order_name)
	order = frappe.get_doc("Sales Order", order_name)
	name = frappe.db.get_value(DOCTYPE, {"sales_order": order_name}, "name")
	if not name:
		frappe.throw("This order has no portal intake. Staff must reconcile its request before approval.")
	frappe.db.sql("select name from `tabilL-Order-Intake` where name=%s for update", name)
	return order, frappe.get_doc(DOCTYPE, name)


def record_buyer_po_edit(order, previous_hash, user):
	actor = get_actor(user)
	if not actor.is_company_dealer_for(order.customer):
		return
	name = frappe.db.get_value(DOCTYPE, {"sales_order": order.name}, "name")
	if not name:
		return
	request = frappe.get_doc(DOCTYPE, name)
	if request.state in ("REJECTED", "WITHDRAWN", "APPROVED"):
		frappe.throw("This order request is no longer editable")
	if request.acknowledged_hash == previous_hash:
		current = fingerprint(snapshot(order))
		request.acknowledged_hash, request.acknowledged_by, request.acknowledged_on = (
			current,
			actor.user,
			now(),
		)
		request.append(
			"decisions",
			{"action": "PO_UPDATED", "actor": actor.user, "recorded_on": now(), "revision_hash": current},
		)
		request.save(ignore_permissions=True)


def before_submit(order, method=None):
	if not order.get("ill_fixture_schedule"):
		return
	_staff(order, approve=True)
	_, request = _load(order.name)
	if not request.get("intake_json"):
		frappe.throw("Complete the buyer's PO, address and receiving intake before approval")
	if not order.get("ill_confirmed_delivery_date") or not order.get("ill_delivery_confirmed_by"):
		frappe.throw(
			"Authorized staff must confirm the delivery date before buyer acknowledgment and approval"
		)
	from illumenate_lighting.illumenate_lighting.portal.accounts import require_owned

	for field, doctype in (
		("customer_address", "Address"),
		("shipping_address_name", "Address"),
		("contact_person", "Contact"),
	):
		if not order.get(field):
			frappe.throw("Billing, shipping and purchasing-contact context is required")
		require_owned(frappe.get_doc(doctype, order.get(field)), order.customer)
	current_hash = fingerprint(snapshot(order))
	if request.state not in ("SUBMITTED", "UNDER_REVIEW", "CHANGES_PROPOSED"):
		frappe.throw("Resolve the order intake before approval")
	if current_hash != request.acknowledged_hash:
		frappe.throw("The buyer must acknowledge the current order revision before approval")
	if not request.acknowledged_by or not get_actor(request.acknowledged_by).is_company_dealer_for(
		order.customer
	):
		frappe.throw(
			"The acknowledging buyer no longer has purchasing access; obtain a current buyer acknowledgment"
		)
	original_offer = json.loads(request.request_snapshot).get("ill_quote_offer")
	if original_offer and original_offer != order.get("ill_quote_offer"):
		frappe.throw("The accepted offer link cannot be removed from this order request")
	if order.get("ill_quote_offer"):
		offer = frappe.get_doc("ilL-Quote-Offer", order.ill_quote_offer)
		if offer.state != "ACCEPTED" or offer.sales_order != order.name or offer.customer != order.customer:
			frappe.throw("This order request no longer has a valid accepted offer")
		if frappe.db.get_value("Quotation", offer.quotation, "docstatus") != 1:
			frappe.throw("The accepted Quotation was cancelled; Sales must resolve the order request")
	for row in order.items:
		if (
			row.get("ill_configured_group")
			or row.get("ill_configured_fixture")
			or row.get("ill_configured_tape_neon")
			or row.get("ill_configured_led_sheet")
		):
			bom = row.get("ill_bom") or row.get("bom_no")
			if not bom or not frappe.db.exists(
				"BOM", {"name": bom, "item": row.item_code, "docstatus": 1, "is_active": 1}
			):
				frappe.throw(f"Row {row.idx}: an active submitted BOM for the ordered Item is required")
	# Drawing approval is deliberately checked at production release, not here.


def on_submit(order, method=None):
	if not order.get("ill_fixture_schedule"):
		return
	_, request = _load(order.name)
	request.state = "APPROVED"
	request.approved_by = frappe.session.user
	request.approved_on = now()
	request.approved_snapshot = canonical_json(snapshot(order))
	from illumenate_lighting.illumenate_lighting.portal.order_acknowledgment import create

	create(request)
	request.save(ignore_permissions=True)
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_order_review

	notify_order_review(order, request)


@frappe.whitelist(methods=["POST"])
@atomic_build
def review(order_name, action, note=None, expected_modified=None):
	order = frappe.get_doc("Sales Order", order_name)
	_staff(order, approve=action == "APPROVE")
	if not order.get("ill_fixture_schedule"):
		frappe.throw("This order is not linked to a portal schedule")
	lock_orders(order_name)
	if not frappe.db.exists(DOCTYPE, {"sales_order": order_name}) and not order.docstatus:
		capture(order)
	order, request = _load(order_name)
	if action == "APPROVE" and order.docstatus == 1 and request.state == "APPROVED":
		return {"success": True, "state": "APPROVED", "sales_order": order.name, "already_existed": True}
	if order.docstatus or request.state in ("REJECTED", "WITHDRAWN", "APPROVED"):
		frappe.throw("This request is no longer editable")
	if not expected_modified or str(order.modified) != str(expected_modified):
		frappe.throw("The order changed. Reload and review the current revision before deciding.")
	if action == "APPROVE":
		order.submit()
		return {"success": True, "state": "APPROVED", "sales_order": order.name}
	states = {
		"REVIEW": "UNDER_REVIEW",
		"REQUEST_INFORMATION": "INFORMATION_NEEDED",
		"PROPOSE_CHANGES": "CHANGES_PROPOSED",
		"REJECT": "REJECTED",
	}
	if action not in states or (action != "REVIEW" and not (note or "").strip()):
		frappe.throw("Choose a review action and explain the requested change or outcome")
	request.state = states[action]
	request.customer_message = (note or "").strip()
	request.append(
		"decisions",
		{
			"action": action,
			"actor": frappe.session.user,
			"recorded_on": now(),
			"revision_hash": fingerprint(snapshot(order)),
			"note": request.customer_message,
		},
	)
	request.save(ignore_permissions=True)
	if action == "REJECT":
		mark_issue(order, request.customer_message)
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_order_review

	notify_order_review(order, request)
	return {"success": True, "state": request.state, "sales_order": order.name}


def mark_issue(order, note):
	"""Keep the rejected draft as evidence; a replacement uses a new schedule."""
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", order.ill_fixture_schedule)
	schedule.set_lifecycle_status("ISSUE", sales_order=order.name, note=note)


@frappe.whitelist(methods=["POST"])
@atomic_build
def withdraw(order_name, revision_hash, note):
	from illumenate_lighting.illumenate_lighting.portal.order_intake import _buyer

	if not load_accessible_sales_order(order_name):
		frappe.throw("Order unavailable", frappe.PermissionError)
	order, request = _load(order_name)
	_buyer(order.customer)
	if request.state == "WITHDRAWN":
		return {"success": True, "state": request.state, "already_existed": True}
	if order.docstatus or request.state in ("APPROVED", "REJECTED"):
		frappe.throw("Only a pending order request can be withdrawn")
	if fingerprint(snapshot(order)) != revision_hash:
		frappe.throw("The order changed. Reload before withdrawing.")
	if not isinstance(note, str) or not note.strip() or len(note) > 4000:
		frappe.throw("Enter a withdrawal reason of up to 4,000 characters")
	request.state, request.customer_message = "WITHDRAWN", note.strip()
	request.append(
		"decisions",
		{
			"action": "WITHDRAWN",
			"actor": frappe.session.user,
			"recorded_on": now(),
			"revision_hash": revision_hash,
			"note": note.strip(),
		},
	)
	request.save(ignore_permissions=True)
	mark_issue(order, note.strip())
	from illumenate_lighting.illumenate_lighting.portal.notifications import notify_order_review

	notify_order_review(order, request)
	return {"success": True, "state": request.state}


@frappe.whitelist(methods=["POST"])
def acknowledge(order_name, revision_hash):
	actor = get_actor()
	if not actor.is_dealer or not load_accessible_sales_order(order_name):
		frappe.throw("Order not found", frappe.PermissionError)
	order, request = _load(order_name)
	if not actor.is_company_dealer_for(order.customer):
		frappe.throw("Purchasing access for this customer is required", frappe.PermissionError)
	if (
		not order.docstatus
		and request.state == "UNDER_REVIEW"
		and request.acknowledged_hash == revision_hash
		and fingerprint(snapshot(order)) == revision_hash
	):
		return {"success": True, "state": request.state, "already_existed": True}
	if (
		not load_accessible_sales_order(order_name)
		or order.docstatus
		or request.state not in ("CHANGES_PROPOSED", "SUBMITTED", "UNDER_REVIEW")
	):
		frappe.throw("This proposed revision cannot be acknowledged")
	if not request.get("intake_json") or not order.get("ill_confirmed_delivery_date"):
		frappe.throw("Complete intake and wait for staff's confirmed delivery date before acknowledgment")
	current = fingerprint(snapshot(order))
	if revision_hash != current:
		frappe.throw("The order changed. Reload and review the current revision.")
	request.acknowledged_hash, request.acknowledged_by, request.acknowledged_on = current, actor.user, now()
	request.append(
		"decisions",
		{"action": "ACKNOWLEDGED", "actor": actor.user, "recorded_on": now(), "revision_hash": current},
	)
	request.state = "UNDER_REVIEW"
	request.save(ignore_permissions=True)
	return {"success": True, "state": request.state}


def detail(order_name):
	order = load_accessible_sales_order(order_name)
	if not order:
		return None
	name = frappe.db.get_value(DOCTYPE, {"sales_order": order_name}, "name")
	if not name:
		return None
	request = frappe.get_doc(DOCTYPE, name)
	current = snapshot(order)
	return {
		"name": name,
		"state": request.state,
		"message": request.customer_message,
		"revision_hash": fingerprint(current),
		"original": json.loads(request.request_snapshot),
		"current": current,
		"approved_on": request.approved_on,
		"can_acknowledge": not order.docstatus
		and request.state in ("CHANGES_PROPOSED", "SUBMITTED", "UNDER_REVIEW")
		and bool(request.get("intake_json"))
		and bool(order.get("ill_confirmed_delivery_date"))
		and request.acknowledged_hash != fingerprint(current)
		and get_actor().is_dealer,
		"needs_intake": not order.docstatus and not request.get("intake_json"),
		"acknowledgment_available": bool(request.get("acknowledgment_file")),
		"requested_date": order.get("ill_requested_delivery_date"),
		"confirmed_date": order.get("ill_confirmed_delivery_date"),
		"can_withdraw": not order.docstatus
		and request.state not in ("APPROVED", "REJECTED", "WITHDRAWN")
		and get_actor().is_dealer,
		"can_replace": request.state in ("REJECTED", "WITHDRAWN") and get_actor().is_dealer,
	}


def validate_order(order, method=None):
	"""Record who made a delivery promise, including native Desk edits."""
	if not order.get("ill_fixture_schedule"):
		return
	old = order.get_doc_before_save()
	if not old and order.get("amended_from"):
		_staff(order)
		# A cancelled order's offer acceptance and delivery promise belong to
		# that order. The amendment gets a fresh intake and buyer acknowledgment.
		order.ill_quote_offer = None
		order.ill_confirmed_delivery_date = None
	changed = order.get("ill_confirmed_delivery_date") != (
		old.get("ill_confirmed_delivery_date") if old else None
	)
	if changed:
		_staff(order)
		if order.docstatus == 1:
			frappe.throw("Use an approved order-change workflow to change a submitted delivery promise")
		if order.get("ill_confirmed_delivery_date") and frappe.utils.getdate(
			order.ill_confirmed_delivery_date
		) < frappe.utils.getdate(frappe.utils.nowdate()):
			frappe.throw("A new delivery promise cannot be in the past")
		order.ill_delivery_confirmed_by = frappe.session.user if order.ill_confirmed_delivery_date else None
		order.ill_delivery_confirmed_on = now() if order.ill_confirmed_delivery_date else None
		if order.ill_confirmed_delivery_date:
			order.delivery_date = order.ill_confirmed_delivery_date
			for row in order.get("items") or []:
				row.delivery_date = order.ill_confirmed_delivery_date
	elif old:
		order.ill_delivery_confirmed_by = old.get("ill_delivery_confirmed_by")
		order.ill_delivery_confirmed_on = old.get("ill_delivery_confirmed_on")
	else:
		order.ill_delivery_confirmed_by = None
		order.ill_delivery_confirmed_on = None
