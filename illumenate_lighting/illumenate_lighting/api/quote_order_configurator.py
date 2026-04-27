# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Desk APIs for adding configured products to Quotations and Sales Orders."""

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
	DEFAULT_SELLING_PRICE_LIST,
	DEFAULT_UOM,
	_create_or_get_bom,
	_create_or_get_configured_item,
	_create_or_get_configured_tape_neon_item,
	build_fixture_bom_items,
)


PARENT_DOCTYPES = {"Quotation", "Sales Order"}
PRODUCT_TYPE_FIXTURE = "Linear Fixture"
PRODUCT_TYPE_TAPE = "LED Tape"
PRODUCT_TYPE_NEON = "LED Neon"
PRODUCT_TYPES = {PRODUCT_TYPE_FIXTURE, PRODUCT_TYPE_TAPE, PRODUCT_TYPE_NEON}


@frappe.whitelist()
def get_product_types() -> list[dict[str, str]]:
	"""Return product types supported by the quote/order configurator shell."""
	return [
		{"label": PRODUCT_TYPE_FIXTURE, "value": PRODUCT_TYPE_FIXTURE, "bom_status": "available"},
		{"label": PRODUCT_TYPE_TAPE, "value": PRODUCT_TYPE_TAPE, "bom_status": "pending_builder"},
		{"label": PRODUCT_TYPE_NEON, "value": PRODUCT_TYPE_NEON, "bom_status": "pending_builder"},
	]


@frappe.whitelist()
def get_bom_preview(
	product_type: str,
	configured_fixture: str | None = None,
	configured_tape_neon: str | None = None,
	bom: str | None = None,
) -> dict[str, Any]:
	"""Preview the BOM rows for a configured product without modifying quote/order docs."""
	product_type = _normalize_product_type(product_type)

	if bom:
		return _preview_existing_bom(product_type, bom)

	if product_type == PRODUCT_TYPE_FIXTURE:
		fixture = _get_required_doc("ilL-Configured-Fixture", configured_fixture, "configured_fixture")
		if fixture.bom and frappe.db.exists("BOM", fixture.bom):
			return _preview_existing_bom(product_type, fixture.bom, configured_fixture=fixture.name)

		return {
			"success": True,
			"product_type": product_type,
			"configured_fixture": fixture.name,
			"configured_tape_neon": None,
			"item_code": fixture.configured_item or fixture.name,
			"bom": None,
			"bom_status": "preview",
			"messages": [],
			"items": _format_bom_items(build_fixture_bom_items(fixture)),
		}

	configured = _get_required_doc("ilL-Configured-Tape-Neon", configured_tape_neon, "configured_tape_neon")
	if configured.bom and frappe.db.exists("BOM", configured.bom):
		return _preview_existing_bom(product_type, configured.bom, configured_tape_neon=configured.name)

	return {
		"success": True,
		"product_type": product_type,
		"configured_fixture": None,
		"configured_tape_neon": configured.name,
		"item_code": configured.configured_item or configured.part_number,
		"bom": None,
		"bom_status": "pending_builder",
		"messages": [{
			"severity": "warning",
			"text": _("Tape/neon BOM preview is not available until the tape/neon BOM builder is implemented."),
		}],
		"items": [],
	}


@frappe.whitelist()
def apply_configured_product(
	parent_doctype: str,
	parent_name: str,
	product_type: str,
	configured_fixture: str | None = None,
	configured_tape_neon: str | None = None,
	row_name: str | None = None,
	qty: float = 1,
	configuration_json: str | dict[str, Any] | None = None,
	bom_override_json: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Create/reuse configured artifacts and write the configured Item to a quote/order row."""
	if bom_override_json:
		frappe.throw(_("Edited BOM overrides are not supported in this first implementation slice."))

	product_type = _normalize_product_type(product_type)
	parent_doc = _get_editable_parent(parent_doctype, parent_name)
	qty = flt(qty) or 1

	artifact = _ensure_configured_artifacts(product_type, configured_fixture, configured_tape_neon)
	row = _get_or_add_item_row(parent_doc, row_name)
	_apply_artifact_to_row(parent_doc, row, artifact, qty, configuration_json)

	parent_doc.save(ignore_permissions=False)

	return {
		"success": True,
		"parent_doctype": parent_doc.doctype,
		"parent_name": parent_doc.name,
		"row_name": row.name,
		"product_type": product_type,
		"configured_fixture": artifact.get("configured_fixture"),
		"configured_tape_neon": artifact.get("configured_tape_neon"),
		"item_code": artifact["item_code"],
		"bom": artifact.get("bom"),
		"messages": artifact.get("messages", []),
	}


def _normalize_product_type(product_type: str) -> str:
	value = (product_type or "").strip()
	lookup = {
		"fixture": PRODUCT_TYPE_FIXTURE,
		"linear_fixture": PRODUCT_TYPE_FIXTURE,
		"linear fixture": PRODUCT_TYPE_FIXTURE,
		"led tape": PRODUCT_TYPE_TAPE,
		"tape": PRODUCT_TYPE_TAPE,
		"led_tape": PRODUCT_TYPE_TAPE,
		"led neon": PRODUCT_TYPE_NEON,
		"neon": PRODUCT_TYPE_NEON,
		"led_neon": PRODUCT_TYPE_NEON,
	}
	normalized = lookup.get(value.lower(), value)
	if normalized not in PRODUCT_TYPES:
		frappe.throw(_("Unsupported product type: {0}").format(product_type))
	return normalized


def _get_required_doc(doctype: str, name: str | None, arg_name: str):
	if not name:
		frappe.throw(_("Missing required value: {0}").format(arg_name))
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} was not found").format(doctype, name))
	return frappe.get_doc(doctype, name)


def _get_editable_parent(parent_doctype: str, parent_name: str):
	if parent_doctype not in PARENT_DOCTYPES:
		frappe.throw(_("Configured products can only be added to Quotations and Sales Orders."))
	if not frappe.db.exists(parent_doctype, parent_name):
		frappe.throw(_("{0} {1} was not found").format(parent_doctype, parent_name))

	doc = frappe.get_doc(parent_doctype, parent_name)
	doc.check_permission("write")
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Configured products can only be applied to draft Quotations and Sales Orders."))
	return doc


def _ensure_configured_artifacts(
	product_type: str,
	configured_fixture: str | None,
	configured_tape_neon: str | None,
) -> dict[str, Any]:
	if product_type == PRODUCT_TYPE_FIXTURE:
		fixture = _get_required_doc("ilL-Configured-Fixture", configured_fixture, "configured_fixture")
		item_result = _create_or_get_configured_item(fixture, skip_if_exists=True)
		if not item_result.get("success"):
			frappe.throw(_messages_to_html(item_result.get("messages")))

		bom_result = _create_or_get_bom(fixture, item_result["item_code"], skip_if_exists=True)
		if not bom_result.get("success"):
			frappe.throw(_messages_to_html(bom_result.get("messages")))

		fixture.configured_item = item_result["item_code"]
		fixture.bom = bom_result["bom_name"]
		fixture.save(ignore_permissions=True)

		return {
			"product_type": product_type,
			"source_doctype": "ilL-Configured-Fixture",
			"source_name": fixture.name,
			"configured_fixture": fixture.name,
			"configured_tape_neon": None,
			"item_code": item_result["item_code"],
			"bom": bom_result["bom_name"],
			"description": _line_description_from_item(item_result["item_code"]),
			"template_code": fixture.fixture_template,
			"requested_length_mm": fixture.requested_overall_length_mm,
			"mfg_length_mm": fixture.manufacturable_overall_length_mm,
			"runs_count": fixture.runs_count,
			"total_watts": fixture.total_watts,
			"finish": fixture.finish,
			"lens": fixture.lens_appearance,
			"engine_version": getattr(fixture, "engine_version", None),
			"configuration_snapshot": _fixture_configuration_snapshot(fixture),
			"messages": item_result.get("messages", []) + bom_result.get("messages", []),
		}

	configured = _get_required_doc("ilL-Configured-Tape-Neon", configured_tape_neon, "configured_tape_neon")
	if configured.product_category and configured.product_category != product_type:
		frappe.throw(_("Configured tape/neon product {0} is {1}, not {2}").format(
			configured.name, configured.product_category, product_type
		))
	item_result = _create_or_get_configured_tape_neon_item(configured, skip_if_exists=True)
	if not item_result.get("success"):
		frappe.throw(_messages_to_html(item_result.get("messages")))

	configured.configured_item = item_result["item_code"]
	configured.save(ignore_permissions=True)

	return {
		"product_type": product_type,
		"source_doctype": "ilL-Configured-Tape-Neon",
		"source_name": configured.name,
		"configured_fixture": None,
		"configured_tape_neon": configured.name,
		"item_code": item_result["item_code"],
		"bom": configured.bom if configured.bom and frappe.db.exists("BOM", configured.bom) else None,
		"description": _line_description_from_item(item_result["item_code"]),
		"template_code": configured.tape_neon_template,
		"requested_length_mm": configured.requested_length_mm,
		"mfg_length_mm": configured.manufacturable_length_mm,
		"runs_count": configured.total_segments,
		"total_watts": configured.total_watts,
		"finish": getattr(configured, "finish", None) or getattr(configured, "pcb_finish", None),
		"lens": None,
		"engine_version": getattr(configured, "engine_version", None),
		"configuration_snapshot": _tape_neon_configuration_snapshot(configured),
		"messages": item_result.get("messages", []) + [{
			"severity": "warning",
			"text": _("Tape/neon configured Item was applied without a BOM; the tape/neon BOM builder is still pending."),
		}],
	}


def _get_or_add_item_row(parent_doc, row_name: str | None):
	if row_name:
		for row in parent_doc.items:
			if row.name == row_name:
				return row
		frappe.throw(_("Item row {0} was not found on {1} {2}").format(row_name, parent_doc.doctype, parent_doc.name))

	return parent_doc.append("items", {})


def _apply_artifact_to_row(parent_doc, row, artifact: dict[str, Any], qty: float, configuration_json):
	item_code = artifact["item_code"]
	item_details = frappe.db.get_value(
		"Item",
		item_code,
		["item_name", "stock_uom", "description"],
		as_dict=True,
	) or {}

	row.item_code = item_code
	row.item_name = item_details.get("item_name") or item_code
	row.description = artifact.get("description") or item_details.get("description") or row.item_name
	row.qty = qty
	row.uom = item_details.get("stock_uom") or DEFAULT_UOM
	row.conversion_factor = 1
	if parent_doc.doctype == "Sales Order":
		_set_child_value(row, "delivery_date", parent_doc.get("delivery_date"))

	rate = _get_selling_rate(item_code)
	if rate is not None:
		row.rate = rate
		_set_child_value(row, "price_list_rate", rate)

	_set_child_value(row, "ill_product_type", artifact["product_type"])
	_set_child_value(row, "ill_configured_fixture", artifact.get("configured_fixture"))
	_set_child_value(row, "ill_configured_tape_neon", artifact.get("configured_tape_neon"))
	_set_child_value(row, "ill_configured_product_doctype", artifact.get("source_doctype"))
	_set_child_value(row, "ill_configured_product", artifact.get("source_name"))
	_set_child_value(row, "ill_configured_item", item_code)
	_set_child_value(row, "ill_bom", artifact.get("bom"))
	_set_child_value(row, "ill_template_code", artifact.get("template_code"))
	_set_child_value(row, "ill_requested_length_mm", artifact.get("requested_length_mm"))
	_set_child_value(row, "ill_mfg_length_mm", artifact.get("mfg_length_mm"))
	_set_child_value(row, "ill_runs_count", artifact.get("runs_count"))
	_set_child_value(row, "ill_total_watts", artifact.get("total_watts"))
	_set_child_value(row, "ill_finish", artifact.get("finish"))
	_set_child_value(row, "ill_lens", artifact.get("lens"))
	_set_child_value(row, "ill_engine_version", artifact.get("engine_version"))
	_set_child_value(row, "ill_configuration_json", _serialize_json(configuration_json or artifact["configuration_snapshot"]))
	_set_child_value(row, "ill_bom_override_json", None)

	if parent_doc.doctype == "Sales Order" and artifact.get("bom"):
		_set_child_value(row, "bom_no", artifact.get("bom"))


def _set_child_value(row, fieldname: str, value):
	try:
		if not row.meta.has_field(fieldname):
			return
	except Exception:
		pass
	row.set(fieldname, value)


def _get_selling_rate(item_code: str) -> float | None:
	prices = frappe.get_all(
		"Item Price",
		filters={"item_code": item_code, "price_list": DEFAULT_SELLING_PRICE_LIST, "selling": 1},
		fields=["price_list_rate"],
		order_by="valid_from desc, modified desc",
		limit=1,
	)
	if not prices:
		return None
	return flt(prices[0].price_list_rate)


def _line_description_from_item(item_code: str) -> str | None:
	return frappe.db.get_value("Item", item_code, "description")


def _preview_existing_bom(
	product_type: str,
	bom: str,
	configured_fixture: str | None = None,
	configured_tape_neon: str | None = None,
) -> dict[str, Any]:
	bom_doc = _get_required_doc("BOM", bom, "bom")
	return {
		"success": True,
		"product_type": product_type,
		"configured_fixture": configured_fixture,
		"configured_tape_neon": configured_tape_neon,
		"item_code": bom_doc.item,
		"bom": bom_doc.name,
		"bom_status": "existing",
		"messages": [],
		"items": _format_bom_items(bom_doc.items),
	}


def _format_bom_items(items) -> list[dict[str, Any]]:
	formatted = []
	for row in items or []:
		item_code = row.get("item_code") if hasattr(row, "get") else getattr(row, "item_code", None)
		qty = row.get("qty") if hasattr(row, "get") else getattr(row, "qty", None)
		uom = row.get("uom") if hasattr(row, "get") else getattr(row, "uom", None)
		stock_uom = row.get("stock_uom") if hasattr(row, "get") else getattr(row, "stock_uom", None)
		item_details = frappe.db.get_value(
			"Item",
			item_code,
			["item_name", "description", "stock_uom"],
			as_dict=True,
		) or {}
		formatted.append({
			"item_code": item_code,
			"item_name": item_details.get("item_name") or item_code,
			"description": item_details.get("description"),
			"qty": qty,
			"uom": uom or item_details.get("stock_uom") or DEFAULT_UOM,
			"stock_uom": stock_uom or item_details.get("stock_uom") or DEFAULT_UOM,
		})
	return formatted


def _fixture_configuration_snapshot(fixture) -> dict[str, Any]:
	return {
		"product_type": PRODUCT_TYPE_FIXTURE,
		"configured_fixture": fixture.name,
		"fixture_template": fixture.fixture_template,
		"finish": fixture.finish,
		"lens_appearance": fixture.lens_appearance,
		"mounting_method": fixture.mounting_method,
		"environment_rating": fixture.environment_rating,
		"requested_overall_length_mm": fixture.requested_overall_length_mm,
		"manufacturable_overall_length_mm": fixture.manufacturable_overall_length_mm,
	}


def _tape_neon_configuration_snapshot(configured) -> dict[str, Any]:
	return {
		"product_type": configured.product_category,
		"configured_tape_neon": configured.name,
		"tape_neon_template": configured.tape_neon_template,
		"tape_spec": configured.tape_spec,
		"tape_offering": configured.tape_offering,
		"cct": configured.cct,
		"output_level": configured.output_level,
		"requested_length_mm": configured.requested_length_mm,
		"manufacturable_length_mm": configured.manufacturable_length_mm,
	}


def _serialize_json(value) -> str:
	if isinstance(value, str):
		return value
	return json.dumps(value or {}, sort_keys=True, default=str)


def _messages_to_html(messages) -> str:
	texts = [message.get("text") for message in messages or [] if message.get("text")]
	return "<br>".join(texts) if texts else _("Configured product artifact generation failed.")