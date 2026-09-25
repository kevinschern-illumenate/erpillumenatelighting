"""Four-family schedule adapter with stable targets, concurrency and durable retries."""

import json
import uuid

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	finite_number,
)
from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule, can_read_schedule

RECEIPT = "ilL-Configuration-Receipt"
FAMILIES = {
	"Linear Fixture": ("configured_fixture", "ilL-Configured-Fixture", "fixture_template"),
	"LED Tape": ("configured_tape_neon", "ilL-Configured-Tape-Neon", "tape_neon_template"),
	"LED Neon": ("configured_tape_neon", "ilL-Configured-Tape-Neon", "tape_neon_template"),
	"LED Sheet": ("configured_led_sheet", "ilL-Configured-LED-Sheet", "led_sheet_template"),
}


def object_value(value, label):
	if isinstance(value, str):
		value = json.loads(value)
	if value is None:
		return {}
	if not isinstance(value, dict):
		raise ValueError(label + " must be an object")
	return value


def schedule_context(name, *, write=False, lock=False):
	schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", name)
	policy = can_edit_schedule if write else can_read_schedule
	if not policy(schedule):
		frappe.throw(_("Schedule is unavailable"), frappe.PermissionError)
	if lock:
		frappe.db.sql("select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", name)
		schedule.reload()
		if not policy(schedule):
			frappe.throw(_("Schedule is unavailable"), frappe.PermissionError)
	return schedule


def resolve_line(schedule, line_key=None, line_idx=None):
	if line_key:
		matches = [
			line for line in schedule.lines if line.get("line_key") == line_key or line.name == line_key
		]
		if len(matches) != 1:
			raise ValueError("The selected line changed or is unavailable; reload the schedule")
		return matches[0]
	if line_idx not in (None, "", "__new__"):
		index = finite_number(line_idx, minimum=0, field="line index")
		if not index.is_integer() or index >= len(schedule.lines):
			raise ValueError("The selected line is unavailable")
		return schedule.lines[int(index)]
	return None


def normalized_payload(family, selections, *, product_slug=None, template=None, segments=None):
	from illumenate_lighting.illumenate_lighting.api import configured_product_builder as builder

	if family not in FAMILIES:
		raise ValueError("Unsupported configured product family")
	selections = object_value(selections, "selections")
	if selections.get("group_request"):
		from illumenate_lighting.illumenate_lighting.api.group_contract import normalize

		request = object_value(selections["group_request"], "group request")
		if normalize(request)["family"] != family:
			raise ValueError("Group family does not match the selected product family")
		return {"group_request": request}
	if family == "Linear Fixture":
		return builder._fixture_payload_from_portal_selections(product_slug, selections, 1)
	if family == "LED Sheet":
		return builder._sheet_kwargs(selections)
	payload = builder._tape_neon_payload_from_portal_selections(family, selections, segments)
	# Retained outside engine kwargs so the association is always checked on save.
	payload["tape_neon_template"] = template or selections.get("tape_neon_template")
	return payload


@frappe.whitelist(methods=["POST"])
def calculate(family, selections, product_slug=None, template=None, segments=None):
	from illumenate_lighting.illumenate_lighting.api.configured_product_builder import _dispatch_calculate
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

	require_catalog_access()
	payload = normalized_payload(
		family, selections, product_slug=product_slug, template=template, segments=segments
	)
	if payload.get("group_request"):
		from illumenate_lighting.illumenate_lighting.api.fixture_group_configurator import preview

		return preview(payload["group_request"])
	result = _dispatch_calculate(
		family,
		payload,
		parent_configured_fixture=None,
		parent_configured_tape_neon=None,
		tape_neon_template=payload.get("tape_neon_template"),
	)
	return {
		"success": bool(result.get("is_valid")),
		"validation": result,
		"input_hash": fingerprint({"family": family, "payload": payload}),
	}


def persist_artifact(family, payload):
	if payload.get("group_request"):
		from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import persist

		return persist(payload["group_request"])

	from illumenate_lighting.illumenate_lighting.api.configured_product_builder import (
		_dispatch_save,
		_ensure_fixture_artifacts,
		_ensure_tape_neon_artifacts,
	)
	from illumenate_lighting.illumenate_lighting.api.quote_order_configurator import (
		_ensure_configured_artifacts,
	)

	result = _dispatch_save(
		family,
		payload,
		parent_configured_fixture=None,
		parent_configured_tape_neon=None,
		tape_neon_template=payload.get("tape_neon_template"),
		variant_origin="Portal",
	)
	if not result.get("is_valid"):
		frappe.throw(result.get("error") or _("Configuration could not be validated"))
	if family == "Linear Fixture":
		artifact = _ensure_fixture_artifacts(result["configured_fixture_id"])
	elif family == "LED Sheet":
		artifact = _ensure_configured_artifacts(family, None, None, result["configured_led_sheet"])
	else:
		artifact = _ensure_tape_neon_artifacts(result["configured_tape_neon"], family)
	return artifact


def apply_artifact(schedule, line, family, artifact, metadata):
	from illumenate_lighting.illumenate_lighting.api.led_sheet_configurator import (
		remove_sheet_accessories_for_line,
	)

	if line is None:
		line = schedule.append("lines", {"qty": 1, "line_key": uuid.uuid4().hex})
	remove_sheet_accessories_for_line(schedule, line)
	for field in (
		"configured_group",
		"configured_fixture",
		"configured_tape_neon",
		"configured_led_sheet",
		"fixture_template",
		"tape_neon_template",
		"led_sheet_template",
		"accessory_item",
		"accessory_item_name",
		"accessory_product_type",
		"variant_selections",
		"kit_template",
		"manufacturer_name",
		"fixture_model_number",
		"trim_info",
		"housing_model_number",
		"driver_model_number",
		"lamp_info",
		"dimming_protocol",
		"input_voltage",
		"other_finish",
	):
		line.set(field, None)
	link, _doctype, template_field = FAMILIES[family]
	line.set(
		"configured_group" if artifact.get("configured_group") else link,
		artifact.get("configured_group") or artifact[link],
	)
	line.set(template_field, artifact.get("template_code"))
	line.manufacturer_type, line.product_type = "ILLUMENATE", family
	line.configuration_status = "Configured"
	line.ill_item_code, line.ill_bom = artifact["item_code"], artifact.get("bom")
	line.manufacturable_length_mm = artifact.get("mfg_length_mm")
	for field in ("line_id", "location", "notes"):
		if field in metadata:
			line.set(field, str(metadata[field] or "").strip())
	if "qty" in metadata:
		qty = finite_number(metadata["qty"], minimum=1, field="quantity")
		if not qty.is_integer():
			raise ValueError("Quantity must be a positive whole number of complete builds")
		line.qty = int(qty)
	return line


@frappe.whitelist(methods=["POST"])
@atomic_build
def save(
	schedule_name,
	family,
	selections,
	idempotency_key,
	expected_modified,
	line_key=None,
	line_idx=None,
	metadata=None,
	product_slug=None,
	template=None,
	segments=None,
):
	"""Calculate and attach once; a failed artifact cannot leave an empty new line."""
	if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
		raise ValueError("A save request key is required")
	selections, metadata = object_value(selections, "selections"), object_value(metadata, "metadata")
	schedule = schedule_context(schedule_name, write=True, lock=True)
	request_hash = fingerprint(
		{
			"family": family,
			"selections": selections,
			"metadata": metadata,
			"line_key": line_key,
			"line_idx": line_idx,
			"product_slug": product_slug,
			"template": template,
			"segments": segments,
			"expected_modified": str(expected_modified),
		}
	)
	key = fingerprint({"actor": frappe.session.user, "schedule": schedule_name, "key": idempotency_key})
	existing = frappe.db.get_value(
		RECEIPT, {"request_key": key}, ["request_hash", "response_json"], as_dict=True
	)
	if existing:
		if existing.request_hash != request_hash:
			raise ValueError("This save request key was already used with different content")
		return {**json.loads(existing.response_json), "already_existed": True}
	if not expected_modified or str(schedule.modified) != str(expected_modified):
		raise ValueError("The schedule changed; reload it before saving this configuration")
	if schedule.get("is_locked") or schedule.status not in {"DRAFT", "READY"}:
		raise ValueError("Create an editable schedule version before changing its configuration")
	line = resolve_line(schedule, line_key, line_idx)
	payload = normalized_payload(
		family, selections, product_slug=product_slug, template=template, segments=segments
	)
	artifact = persist_artifact(family, payload)
	line = apply_artifact(schedule, line, family, artifact, metadata)
	line.ill_configurator_request = canonical_json(
		{
			"schema_version": 2,
			"family": family,
			"template": template,
			"product_slug": product_slug,
			"selections": object_value(selections, "selections"),
			"segments": json.loads(segments) if isinstance(segments, str) else segments,
		}
	)
	schedule.save(ignore_permissions=True)  # Scoped write policy was rechecked under the schedule lock.
	response = {
		"success": True,
		"schedule_name": schedule.name,
		"line_key": line.get("line_key") or line.name,
		"line_idx": schedule.lines.index(line),
		"modified": str(schedule.modified),
		"item_code": artifact["item_code"],
		"bom": artifact.get("bom"),
		"already_existed": False,
	}
	receipt = frappe.get_doc(
		{
			"doctype": RECEIPT,
			"schedule": schedule.name,
			"actor": frappe.session.user,
			"request_key": key,
			"request_hash": request_hash,
			"response_json": canonical_json(response),
		}
	)
	receipt.flags.configuration_service_write = True
	receipt.insert(ignore_permissions=True)
	return response
