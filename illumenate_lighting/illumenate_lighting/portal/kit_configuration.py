"""Portal kit save with stable lines, optimistic concurrency, and durable receipts."""

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


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
@atomic_build
def save(
	schedule_name,
	selections,
	idempotency_key,
	expected_modified,
	line_key=None,
	line_idx=None,
	metadata=None,
	finder=None,
):
	from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
		KIT_SELECTION_KEYS,
		_write_kit_line,
		validate_kit_configuration,
	)
	from illumenate_lighting.illumenate_lighting.portal.product_finder import sessions, verification
	from illumenate_lighting.illumenate_lighting.portal.rollout import require_family

	require_catalog_access()
	require_family("Extrusion Kit")
	if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
		frappe.throw("A save retry key is required")
	submitted = object_value(selections, "selections")
	clean = {k: str(submitted[k]) for k in KIT_SELECTION_KEYS if submitted.get(k) not in (None, "")}
	metadata = object_value(metadata, "metadata")
	schedule = schedule_context(schedule_name, write=True, lock=True)
	key = fingerprint(
		{"actor": frappe.session.user, "schedule": schedule_name, "kind": "kit", "key": idempotency_key}
	)
	digest = fingerprint(
		{
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
		frappe.throw("The schedule changed. Reload before saving this kit.")
	result = validate_kit_configuration(clean)
	if not result.get("is_valid"):
		frappe.throw(result.get("error") or "The kit could not be validated")
	line = resolve_line(schedule, line_key, line_idx)
	if line is None:
		line = schedule.append("lines", {"line_key": str(uuid.uuid4()), "qty": 1})
	_write_kit_line(schedule, line, result)
	for field in ("line_id", "location", "notes"):
		if field in metadata:
			value = str(metadata[field] or "").strip()
			if len(value) > (4000 if field == "notes" else 140):
				frappe.throw("Line metadata is too long")
			line.set(field, value)
	quantity = finite_number(metadata.get("qty", line.qty or 1), minimum=1, field="quantity")
	if not quantity.is_integer():
		frappe.throw("Enter a whole number of kits")
	line.qty = int(quantity)
	if finder:
		verification.apply_to_line(
			schedule, line, verification.product_name("Extrusion Kit", result["kit_template"]["name"]), finder
		)
		sessions.mark_used(finder)
	schedule.save(ignore_permissions=True)
	response = {
		"success": True,
		"schedule_name": schedule.name,
		"line_key": line.line_key,
		"modified": str(schedule.modified),
		"item_code": result["part_number"],
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
