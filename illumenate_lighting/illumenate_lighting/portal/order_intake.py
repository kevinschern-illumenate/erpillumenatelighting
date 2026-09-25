"""Reviewed PO context around the existing draft Sales Order, with durable retry identity."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	parse_bool,
)
from illumenate_lighting.illumenate_lighting.portal.access import get_actor
from illumenate_lighting.illumenate_lighting.portal.accounts import require_owned, selections

FIELDS = {
	"po_no",
	"customer_address",
	"shipping_address_name",
	"contact_person",
	"requested_date",
	"receiving_instructions",
	"shipping_instructions",
	"file_ids",
	"acknowledge_scope",
	"scope_hash",
	"expected_modified",
}


def _buyer(customer):
	if not get_actor().is_company_dealer_for(customer):
		frappe.throw(
			"Only a current buyer for the ordering company may submit intake", frappe.PermissionError
		)


def _schedule(name, *, lock=False):
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		can_request_schedule_order,
	)
	from illumenate_lighting.illumenate_lighting.portal.offers import commercial_customer

	if lock:
		frappe.db.sql("select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", name)
	doc = frappe.get_doc("ilL-Project-Fixture-Schedule", name)
	allowed, reason = can_request_schedule_order(doc, frappe.session.user)
	if not allowed:
		frappe.throw(reason, frappe.PermissionError)
	customer = commercial_customer(doc)
	_buyer(customer)
	return doc, customer


def scope(schedule):
	return {
		"schedule": schedule.name,
		"lines": [
			{
				key: line.get(key)
				for key in (
					"line_key",
					"name",
					"line_id",
					"manufacturer_type",
					"product_type",
					"qty",
					"location",
					"notes",
					"configured_group",
					"configured_fixture",
					"configured_tape_neon",
					"configured_led_sheet",
					"accessory_item",
					"ill_item_code",
				)
			}
			for line in schedule.lines
		],
		"basis": "Estimate subject to staff review. OTHER manufacturer lines are excluded from the sellable order and retained in the schedule and packet.",
	}


@frappe.whitelist()
def prepare(schedule_name=None, order_name=None):
	from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

	if order_name:
		order = load_accessible_sales_order(order_name)
		if not order or order.docstatus:
			frappe.throw("Draft order unavailable", frappe.PermissionError)
		_buyer(order.customer)
		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", order.ill_fixture_schedule)
		customer, revision = order.customer, str(order.modified)
		defaults = {
			key: order.get(key)
			for key in ("po_no", "customer_address", "shipping_address_name", "contact_person")
		}
		defaults["requested_date"] = str(order.get("ill_requested_delivery_date") or "")
	else:
		schedule, customer = _schedule(schedule_name)
		revision, defaults = str(schedule.modified), {}
	data = scope(schedule)
	return {
		"success": True,
		"scope": data,
		"scope_hash": fingerprint(data),
		"expected_modified": revision,
		"customer": customer,
		"choices": selections(customer),
		"defaults": defaults,
		"purchasing_contact": frappe.db.get_value("Customer", customer, "ill_purchasing_contact"),
	}


def normalize(envelope):
	data = json.loads(envelope) if isinstance(envelope, str) else envelope
	if not isinstance(data, dict) or set(data) - FIELDS:
		raise ValueError("Use the displayed order intake fields")
	data = dict(data)
	if not parse_bool(data.get("acknowledge_scope")):
		raise ValueError("Review and acknowledge the sellable scope and exclusions")
	data["acknowledge_scope"] = True
	for key in FIELDS - {"file_ids", "acknowledge_scope"}:
		data[key] = str(data.get(key) or "").strip()
		if len(data[key]) > (4000 if key.endswith("instructions") else 140):
			raise ValueError(f"Shorten {key.replace('_', ' ')}")
	files = data.get("file_ids") or []
	if not isinstance(files, list) or len(files) > 10 or any(not isinstance(value, str) for value in files):
		raise ValueError("Choose up to 10 verified files")
	data["file_ids"] = sorted(set(files))
	if data["requested_date"]:
		data["requested_date"] = str(frappe.utils.getdate(data["requested_date"]))
	return data


def validate_context(customer, data):
	for field, doctype in (
		("customer_address", "Address"),
		("shipping_address_name", "Address"),
		("contact_person", "Contact"),
	):
		if not data[field]:
			raise ValueError("Billing address, shipping address and purchasing contact are required")
		require_owned(frappe.get_doc(doctype, data[field]), customer)
	if not data["requested_date"] or frappe.utils.getdate(data["requested_date"]) < frappe.utils.getdate(
		frappe.utils.nowdate()
	):
		raise ValueError("Choose a requested delivery date on or after today")
	data["requested_date"] = str(frappe.utils.getdate(data["requested_date"]))


def apply_header(order, data):
	from frappe.contacts.doctype.address.address import get_address_display

	from illumenate_lighting.illumenate_lighting.portal.accounts import require_owned

	for field in ("po_no", "customer_address", "shipping_address_name", "contact_person"):
		order.set(field, data[field])
	# Capture the selected records at intake. A link alone does not populate
	# native ERP display fields during server-side creation or replace stale text.
	for source, target in (
		("customer_address", "address_display"),
		("shipping_address_name", "shipping_address"),
	):
		address = require_owned(frappe.get_doc("Address", data[source]), order.customer)
		order.set(target, get_address_display(address.as_dict()))
	contact = require_owned(frappe.get_doc("Contact", data["contact_person"]), order.customer)
	order.contact_display = contact.get("full_name") or " ".join(
		filter(None, (contact.get("first_name"), contact.get("last_name")))
	)
	order.contact_email, order.contact_mobile = (
		contact.get("email_id"),
		contact.get("mobile_no") or contact.get("phone"),
	)
	order.ill_requested_delivery_date = data["requested_date"]
	order.delivery_date = data["requested_date"]
	order.ill_receiving_instructions = data["receiving_instructions"]
	order.ill_shipping_instructions = data["shipping_instructions"]
	for row in order.items or []:
		row.delivery_date = data["requested_date"]


def _files(intake, data):
	from illumenate_lighting.illumenate_lighting.portal.files import finalize_files

	files = finalize_files(data["file_ids"], "ilL-Order-Intake", intake.name, allow_unbound=True)
	frappe.db.set_value("ilL-Order-Intake", intake.name, "files_json", canonical_json(files))


@frappe.whitelist(methods=["POST"])
@atomic_build
def submit(schedule_name, envelope, idempotency_key):
	data = normalize(envelope)
	schedule, customer = _schedule(schedule_name, lock=True)
	if not idempotency_key or len(idempotency_key) > 140:
		raise ValueError("A valid request key is required")
	key = fingerprint({"actor": frappe.session.user, "schedule": schedule_name, "key": idempotency_key})
	digest = fingerprint(data)
	old = frappe.db.get_value(
		"ilL-Order-Intake", {"intake_key": key}, ["name", "sales_order", "intake_hash"], as_dict=True
	)
	if old:
		if old.intake_hash != digest:
			raise ValueError("This request key was already used with different intake. Reload the order.")
		return {"success": True, "sales_order": old.sales_order, "intake": old.name, "already_existed": True}
	if schedule.get_linked_sales_order():
		raise ValueError(
			"This schedule already has an order request. Complete or review its intake on the order page."
		)
	if (
		str(schedule.modified) != data["expected_modified"]
		or fingerprint(scope(schedule)) != data["scope_hash"]
	):
		raise ValueError("Schedule scope changed. Reload and review before submitting.")
	validate_context(customer, data)
	previous = frappe.flags.get("ill_order_intake_context")
	try:
		frappe.flags.ill_order_intake_context = {"data": data, "key": key, "hash": digest}
		result = schedule.create_sales_order_result(include_other=False)
	finally:
		frappe.flags.ill_order_intake_context = previous
	intake = frappe.get_doc("ilL-Order-Intake", {"sales_order": result["sales_order"]})
	_files(intake, data)
	return {
		"success": True,
		"sales_order": result["sales_order"],
		"intake": intake.name,
		"already_existed": False,
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def complete(order_name, envelope):
	"""Fill quote-led or historical draft intake once without changing the original receipt."""
	from illumenate_lighting.illumenate_lighting.portal.order_review import _load
	from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

	if not load_accessible_sales_order(order_name):
		frappe.throw("Order unavailable", frappe.PermissionError)
	order, intake = _load(order_name)
	_buyer(order.customer)
	data = normalize(envelope)
	digest = fingerprint(data)
	if intake.get("intake_hash"):
		if intake.intake_hash == digest:
			return {"success": True, "sales_order": order.name, "already_existed": True}
		raise ValueError("Intake was already submitted. Propose a change through the order review.")
	if order.docstatus or intake.state in ("REJECTED", "WITHDRAWN", "APPROVED"):
		raise ValueError("This request is no longer editable")
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", order.ill_fixture_schedule)
	if str(order.modified) != data["expected_modified"] or fingerprint(scope(schedule)) != data["scope_hash"]:
		raise ValueError("Order scope changed. Reload before submitting intake.")
	validate_context(order.customer, data)
	apply_header(order, data)
	order.save(ignore_permissions=True)
	intake.intake_hash, intake.intake_json = digest, canonical_json(data)
	intake.acknowledged_hash, intake.state = None, "UNDER_REVIEW"
	intake.append(
		"decisions",
		{
			"action": "INTAKE_COMPLETED",
			"actor": frappe.session.user,
			"recorded_on": frappe.utils.now(),
			"revision_hash": digest,
		},
	)
	intake.save(ignore_permissions=True)
	_files(intake, data)
	return {"success": True, "sales_order": order.name}


def can_access(intake, ptype="read", user=None):
	from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

	order = load_accessible_sales_order(intake.sales_order, user)
	if not order:
		return False
	return ptype in ("read", "select", "report", "print") or (
		ptype == "write" and not order.docstatus and intake.state not in ("REJECTED", "WITHDRAWN", "APPROVED")
	)
