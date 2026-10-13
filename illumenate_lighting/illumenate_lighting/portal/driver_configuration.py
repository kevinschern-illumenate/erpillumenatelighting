"""Portal power supply save: an ilL-Driver-Template configuration becomes a scheduled ilL-Spec-Driver Item.

A configured power supply has no build of its own. The line is a standard ACCESSORY
line on the resolved variant's Item (so quotes and orders treat it like any other
SKU) that also keeps its ``driver_template`` and the validated configuration in
``variant_selections``, so the line reopens in the configurator and its spec
submittal is filled from the template's ilL-Driver-Submittal-Mapping rows.
"""

import json
import uuid

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	finite_number,
)
from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access
from illumenate_lighting.illumenate_lighting.portal.configuration import (
	RECEIPT,
	object_value,
	resolve_line,
	schedule_context,
)
from illumenate_lighting.illumenate_lighting.portal.line_fields import LINE_PRODUCT_FIELDS


def driver_configuration(line):
	"""The validated power supply configuration stored on a schedule line, or None."""
	if (
		not line.get("driver_template")
		or not line.get("accessory_item")
		or not line.get("variant_selections")
	):
		return None
	raw = line.variant_selections
	try:
		stored = json.loads(raw) if isinstance(raw, str) else raw
	except (TypeError, ValueError):
		return None
	return stored if isinstance(stored, dict) and stored.get("product_category") == "Driver" else None


def selection_labels(selections):
	"""Stored driver selections keyed by their step labels, e.g. {"Wattage": "96 W"}, for display."""
	from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import DRIVER_STEPS

	labels = {}
	for step in DRIVER_STEPS:
		value = selections.get(step["name"])
		if value in (None, ""):
			continue
		if step["name"] == "wattage":
			try:
				value = f"{float(value):g} W"
			except (TypeError, ValueError):
				pass
		labels[step["label"]] = str(value)
	return labels


def line_description(template_name, part_number, item_name=None):
	"""What a power supply line is called: the template name first, then its part number."""
	parts = [template_name, part_number]
	if item_name and item_name not in parts:
		parts.append(item_name)
	return " · ".join(part for part in parts if part)


def write_line(line, result):
	"""Write a fresh server validation onto a schedule line, replacing whatever product it had."""
	for field in LINE_PRODUCT_FIELDS:
		line.set(field, None)
	variant = result["variant"]
	line.manufacturer_type = "ACCESSORY"
	line.configuration_status = "Configured"
	line.driver_template = result["template_code"]
	line.accessory_item = variant["item"]
	line.accessory_item_name = line_description(
		result.get("template_name"), result.get("part_number"), variant.get("item_name")
	)
	line.accessory_product_type = frappe.db.get_value("Item", variant["item"], "item_group")
	line.variant_selections = canonical_json(
		{
			"product_category": "Driver",
			"template": result["template_code"],
			"template_name": result.get("template_name"),
			"selections": result.get("selections") or {},
			"part_number": result.get("part_number"),
			"variant_name": variant.get("variant_name"),
			"variant_code": variant.get("variant_code"),
			"spec_name": variant.get("spec_name"),
			"item_code": variant["item"],
		}
	)
	return line


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
@atomic_build
def save(
	schedule_name,
	template,
	selections,
	idempotency_key,
	expected_modified,
	line_key=None,
	line_idx=None,
	metadata=None,
	finder=None,
):
	from illumenate_lighting.illumenate_lighting.api.driver_controller_configurator import (
		DRIVER_STEPS,
		_validate_configuration,
	)
	from illumenate_lighting.illumenate_lighting.portal.product_finder import sessions, verification
	from illumenate_lighting.illumenate_lighting.portal.rollout import require_family

	require_catalog_access()
	require_family("Driver")
	if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
		frappe.throw("A save retry key is required")
	submitted = object_value(selections, "selections")
	clean = {
		step["name"]: submitted[step["name"]]
		for step in DRIVER_STEPS
		if submitted.get(step["name"]) not in (None, "")
	}
	metadata = object_value(metadata, "metadata")
	schedule = schedule_context(schedule_name, write=True, lock=True)
	key = fingerprint(
		{"actor": frappe.session.user, "schedule": schedule_name, "kind": "driver", "key": idempotency_key}
	)
	digest = fingerprint(
		{
			"template": template,
			"selections": clean,
			"line_key": line_key,
			"line_idx": line_idx,
			"metadata": metadata,
			"modified": str(expected_modified),
			"finder": finder,
		}
	)
	old = frappe.db.get_value(RECEIPT, {"request_key": key}, ["request_hash", "response_json"], as_dict=True)
	if old:
		if old.request_hash != digest:
			frappe.throw("This save key was used for different content")
		return {**sessions.decoded(old.response_json), "already_existed": True}
	if (
		str(schedule.modified) != str(expected_modified)
		or schedule.is_locked
		or schedule.status not in ("DRAFT", "READY")
	):
		frappe.throw("The schedule changed. Reload before saving this power supply.")
	result = _validate_configuration("Driver", None, canonical_json(clean), template)
	if not result.get("success") or not (result.get("variant") or {}).get("item"):
		frappe.throw(result.get("error") or "This power supply has no orderable Item")
	from illumenate_lighting.illumenate_lighting.api.portal import orderable_item_problem

	problem = orderable_item_problem(result["variant"]["item"])
	if problem:
		frappe.throw(problem)
	line = resolve_line(schedule, line_key, line_idx)
	if line is None:
		line = schedule.append("lines", {"line_key": str(uuid.uuid4()), "qty": 1})
	write_line(line, result)
	for field in ("line_id", "location", "notes"):
		if field in metadata:
			value = str(metadata[field] or "").strip()
			if len(value) > (4000 if field == "notes" else 140):
				frappe.throw("Line metadata is too long")
			# A blank fixture type keeps the one the line already has.
			if value or field != "line_id":
				line.set(field, value)
	if not line.line_id:
		frappe.throw("Enter a fixture type")
	quantity = finite_number(metadata.get("qty", line.qty or 1), minimum=1, field="quantity")
	if not quantity.is_integer():
		frappe.throw("Enter a whole number of power supplies")
	line.qty = int(quantity)
	if finder:
		verification.apply_to_line(schedule, line, verification.product_name("Driver", template), finder)
		sessions.mark_used(finder)
	schedule.save(ignore_permissions=True)
	response = {
		"success": True,
		"schedule_name": schedule.name,
		"line_key": line.line_key,
		"modified": str(schedule.modified),
		"item_code": line.accessory_item,
	}
	receipt = frappe.get_doc(
		{
			"doctype": RECEIPT,
			"schedule": schedule.name,
			"actor": frappe.session.user,
			"request_key": key,
			"request_hash": digest,
			"response_json": canonical_json(response),
		}
	)
	receipt.flags.configuration_service_write = True
	receipt.insert(ignore_permissions=True)
	return response
