"""Approved catalog SKU choices become standard schedule lines with durable save receipts."""

import json
import uuid

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	finite_number,
)
from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule, require_catalog_access
from illumenate_lighting.illumenate_lighting.portal.configuration import RECEIPT, schedule_context


def choices(product):
	if not product.is_active:
		return []
	candidates = []
	if product.get("portal_item"):
		candidates.append((product.portal_item, product.product_name))
	for kind in ("Driver", "Controller", "Accessory"):
		if product.product_type != kind:
			continue
		prefix = kind.lower()
		if product.get(prefix + "_spec"):
			spec = frappe.get_doc("ilL-Spec-" + kind, product.get(prefix + "_spec"))
			if not spec.meta.has_field("is_active") or spec.is_active:
				candidates.append((spec.get("item"), spec.name))
		if product.get(prefix + "_template"):
			template = frappe.get_doc("ilL-" + kind + "-Template", product.get(prefix + "_template"))
			if template.is_active:
				for row in template.variants or []:
					if row.is_active:
						spec = frappe.get_doc("ilL-Spec-" + kind, row.get(prefix + "_spec"))
						if not spec.meta.has_field("is_active") or spec.is_active:
							candidates.append((spec.get("item"), row.variant_code or spec.name))
	result, seen = [], set()
	for code, label in candidates:
		if not code or code in seen:
			continue
		seen.add(code)
		item = frappe.db.get_value(
			"Item",
			code,
			["name", "item_name", "stock_uom", "disabled", "has_variants", "is_sales_item"],
			as_dict=True,
		)
		if item and not item.disabled and not item.has_variants and item.is_sales_item:
			result.append(
				{"item_code": code, "label": f"{label} · {item.item_name}", "stock_uom": item.stock_uom}
			)
	return result


def _product(slug):
	name = frappe.db.get_value("ilL-Webflow-Product", {"product_slug": slug, "is_active": 1}, "name")
	if not name:
		frappe.throw("Product unavailable")
	return frappe.get_doc("ilL-Webflow-Product", name)


@frappe.whitelist()
def prepare(product_slug, search=None):
	require_catalog_access()
	filters = {"status": ["in", ["DRAFT", "READY"]], "is_locked": 0}
	if search:
		filters["schedule_name"] = ["like", "%" + str(search)[:100] + "%"]
	schedules = frappe.get_list(
		"ilL-Project-Fixture-Schedule",
		filters=filters,
		fields=["name", "schedule_name", "modified"],
		order_by="modified desc, name desc",
		limit_page_length=100,
	)
	return {
		"choices": choices(_product(product_slug)),
		"schedules": [
			row
			for row in schedules
			if can_edit_schedule(frappe.get_doc("ilL-Project-Fixture-Schedule", row.name))
		],
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def add(
	product_slug,
	item_code,
	schedule_name,
	quantity,
	line_id,
	expected_modified,
	idempotency_key,
	location=None,
	notes=None,
):
	require_catalog_access()
	quantity = finite_number(quantity, minimum=1, field="quantity")
	if not quantity.is_integer():
		frappe.throw("Enter a whole number in the Item stock UOM")
	if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
		frappe.throw("A save retry key is required")
	if not line_id or len(line_id) > 140 or len(location or "") > 140 or len(notes or "") > 4000:
		frappe.throw("Enter a designation and use at most 140 characters for location and 4,000 for notes")
	schedule = schedule_context(schedule_name, write=True, lock=True)
	body = {
		"product": product_slug,
		"item": item_code,
		"quantity": int(quantity),
		"line_id": line_id,
		"location": location,
		"notes": notes,
		"modified": str(expected_modified),
	}
	digest = fingerprint(body)
	key = fingerprint(
		{"actor": frappe.session.user, "schedule": schedule_name, "kind": "standard", "key": idempotency_key}
	)
	old = frappe.db.get_value(RECEIPT, {"request_key": key}, ["request_hash", "response_json"], as_dict=True)
	if old:
		if old.request_hash != digest:
			frappe.throw("This save key was used for different content")
		return {**json.loads(old.response_json), "already_existed": True}
	if (
		str(schedule.modified) != str(expected_modified)
		or schedule.is_locked
		or schedule.status not in ("DRAFT", "READY")
	):
		frappe.throw("The schedule changed. Reload before adding this Item.")
	selected = next((row for row in choices(_product(product_slug)) if row["item_code"] == item_code), None)
	if not selected:
		frappe.throw("This SKU is no longer an approved orderable choice for this product")
	line = schedule.append(
		"lines",
		{
			"line_key": str(uuid.uuid4()),
			"line_id": line_id,
			"qty": int(quantity),
			"location": location,
			"notes": notes,
			"manufacturer_type": "ACCESSORY",
			"configuration_status": "Configured",
			"accessory_item": item_code,
			"accessory_item_name": selected["label"],
			"variant_selections": canonical_json({"product_slug": product_slug, "item_code": item_code}),
		},
	)
	schedule.save(ignore_permissions=True)
	response = {
		"success": True,
		"schedule_name": schedule.name,
		"line_key": line.line_key,
		"modified": str(schedule.modified),
		"item_code": item_code,
	}
	doc = frappe.get_doc(
		{
			"doctype": RECEIPT,
			"schedule": schedule.name,
			"actor": frappe.session.user,
			"request_key": key,
			"request_hash": digest,
			"response_json": canonical_json(response),
		}
	)
	doc.flags.configuration_service_write = True
	doc.insert(ignore_permissions=True)
	return response
