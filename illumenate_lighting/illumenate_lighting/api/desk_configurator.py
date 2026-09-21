# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Desk "Configure & Add Fixture" backend for Quotation / Sales Order.

Server builds, client inserts: every write that is independent of the
transaction (configured record, Item, BOM, MSRP Item Price and the
fixture-schedule line) happens here, and a fully priced ``row_values`` dict is
returned for the desk form to insert with ``frm.add_child('items', values)``.
That keeps the tool usable on brand-new, unsaved documents.

Internal users only — dealers never use the desk tool (see
``_require_internal_user``).
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from illumenate_lighting.illumenate_lighting.api import led_sheet_configurator, tape_neon_configurator
from illumenate_lighting.illumenate_lighting.api.configured_product_builder import (
	_coerce_dict,
	_dispatch_save,
	_ensure_fixture_artifacts,
	_ensure_tape_neon_artifacts,
	_error_text_from_messages,
	_fixture_payload_from_portal_selections,
	_tape_neon_payload_from_portal_selections,
)
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
	ensure_configured_item_price,
)
from illumenate_lighting.illumenate_lighting.api.quote_order_configurator import (
	PRODUCT_TYPE_FIXTURE,
	PRODUCT_TYPE_NEON,
	PRODUCT_TYPE_SHEET,
	PRODUCT_TYPE_TAPE,
	_apply_artifact_to_row,
	_ensure_configured_artifacts,
	_normalize_product_type,
	_serialize_json,
	_set_child_value,
)
from illumenate_lighting.illumenate_lighting.api.webflow_schedule import (
	_get_next_fixture_type_id,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
	_is_internal_user,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
	has_permission as project_has_permission,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
	EDITABLE_STATUSES,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
	has_permission as schedule_has_permission,
)

PARENT_DOCTYPES = {"Quotation", "Sales Order"}
SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"
PROJECT_DOCTYPE = "ilL-Project"
EDITABLE_SCHEDULE_STATUSES = tuple(EDITABLE_STATUSES)
DESK_PRODUCT_TYPES = (PRODUCT_TYPE_FIXTURE, PRODUCT_TYPE_TAPE, PRODUCT_TYPE_NEON, PRODUCT_TYPE_SHEET)
DEFAULT_SCHEDULE_NAME = "Main Schedule"
SCHEDULE_LINE_SAVEPOINT = "ill_desk_cfg_line"

# Child-row keys that must never be handed back to ``frm.add_child``.
ROW_VALUE_EXCLUDED_KEYS = {
	"name",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
	"docstatus",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"__islocal",
	"__unsaved",
	"__run_link_triggers",
}

# Header fields the client may pass so pricing runs with the document's context.
SAFE_HEADER_FIELDS = (
	"customer",
	"party_name",
	"quotation_to",
	"company",
	"currency",
	"price_list_currency",
	"selling_price_list",
	"conversion_rate",
	"plc_conversion_rate",
	"transaction_date",
	"delivery_date",
	"customer_group",
	"territory",
	"ignore_pricing_rule",
)


# ═══════════════════════════════════════════════════════════════════════
# GUARDS
# ═══════════════════════════════════════════════════════════════════════


def _require_internal_user() -> None:
	"""The desk tool is for ilLumenate staff only; dealers use the portal."""
	if frappe.session.user == "Guest" or not _is_internal_user(frappe.session.user):
		frappe.throw(_("The desk configurator is available to internal users only."), frappe.PermissionError)


def _require_parent_doctype(parent_doctype: str) -> None:
	if parent_doctype not in PARENT_DOCTYPES:
		frappe.throw(_("Configured products can only be added to Quotations and Sales Orders."))
	if not frappe.has_permission(parent_doctype, "write"):
		frappe.throw(_("You do not have write permission on {0}.").format(parent_doctype), frappe.PermissionError)


def _error(message: str, **extra) -> dict[str, Any]:
	result = {"success": False, "error": message}
	result.update(extra)
	return result


def _schedule_summary(schedule) -> dict[str, Any]:
	project_name = None
	if schedule.ill_project:
		project_name = frappe.db.get_value(PROJECT_DOCTYPE, schedule.ill_project, "project_name")
	return {
		"name": schedule.name,
		"schedule_name": schedule.schedule_name,
		"status": schedule.status,
		"is_locked": cint(schedule.get("is_locked")),
		"is_editable": _schedule_is_editable(schedule),
		"ill_project": schedule.ill_project,
		"project_name": project_name or schedule.ill_project,
		"customer": schedule.customer,
		"version": schedule.get("version") or 1,
	}


def _schedule_is_editable(schedule) -> bool:
	return not cint(schedule.get("is_locked")) and schedule.status in EDITABLE_SCHEDULE_STATUSES


def _schedule_not_editable_reason(schedule) -> str:
	if cint(schedule.get("is_locked")):
		return _("Fixture Schedule {0} is locked. Create a new version to keep configuring.").format(schedule.name)
	return _(
		"Fixture Schedule {0} is {1}; only DRAFT or READY schedules accept new lines. "
		"Create a new version to keep configuring."
	).format(schedule.name, schedule.status)


def _load_schedule(schedule_name: str | None, ptype: str = "write"):
	"""Return ``(schedule_doc, error_dict)``; exactly one is set."""
	if not schedule_name:
		return None, _error(_("Please select a Fixture Schedule."))
	if not frappe.db.exists(SCHEDULE_DOCTYPE, schedule_name):
		return None, _error(_("Fixture Schedule {0} was not found.").format(schedule_name))
	schedule = frappe.get_doc(SCHEDULE_DOCTYPE, schedule_name)
	if not schedule_has_permission(schedule, ptype, frappe.session.user):
		return None, _error(_("You do not have {0} permission on Fixture Schedule {1}.").format(ptype, schedule_name))
	return schedule, None


def _coerce_list(value) -> list:
	if value is None or value == "":
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except json.JSONDecodeError:
			return []
	return list(value) if isinstance(value, (list, tuple, set)) else []


def _next_fixture_type(schedule, used_ids) -> str:
	"""Next free ``A1``-style id across the schedule lines and the form rows."""
	existing = {str(v).strip() for v in used_ids or [] if v}
	for line in (getattr(schedule, "lines", None) or []) if schedule else []:
		if line.line_id:
			existing.add(line.line_id.strip())

	probe = frappe._dict(lines=[frappe._dict(line_id=v) for v in existing])
	return _get_next_fixture_type_id(probe)


# ═══════════════════════════════════════════════════════════════════════
# BOOTSTRAP / PICKERS
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def get_desk_context(
	parent_doctype: str,
	customer: str | None = None,
	linked_schedule: str | None = None,
) -> dict[str, Any]:
	"""Bootstrap payload for the dialog's project/schedule step."""
	_require_internal_user()
	_require_parent_doctype(parent_doctype)

	linked = None
	if linked_schedule:
		schedule, err = _load_schedule(linked_schedule, "read")
		if err:
			return err
		linked = _schedule_summary(schedule)
		linked["can_write"] = schedule_has_permission(schedule, "write", frappe.session.user)
		linked["not_editable_reason"] = None if linked["is_editable"] else _schedule_not_editable_reason(schedule)
		customer = customer or schedule.customer

	filters: dict[str, Any] = {"is_active": 1}
	if customer:
		filters["customer"] = customer
	projects = frappe.get_all(
		PROJECT_DOCTYPE,
		filters=filters,
		fields=["name", "project_name", "customer"],
		order_by="project_name asc",
		limit=500,
	)

	return {
		"success": True,
		"customer": customer,
		"linked_schedule": linked,
		"projects": [
			{"value": p.name, "label": p.project_name or p.name, "customer": p.customer} for p in projects
		],
		"product_types": [{"value": pt, "label": _(pt)} for pt in DESK_PRODUCT_TYPES],
		"can_create_project": bool(frappe.has_permission(PROJECT_DOCTYPE, "create")),
		"can_create_schedule": bool(frappe.has_permission(SCHEDULE_DOCTYPE, "create")),
	}


@frappe.whitelist()
def get_schedule_picker_data(schedule: str, used_json: str | list | None = None) -> dict[str, Any]:
	"""Lines, distinct locations and the next free fixture type for a schedule."""
	_require_internal_user()
	doc, err = _load_schedule(schedule, "read")
	if err:
		return err

	lines = []
	locations: list[str] = []
	for idx, line in enumerate(doc.lines or []):
		if line.location and line.location not in locations:
			locations.append(line.location)
		lines.append({
			"idx": idx,
			"name": line.name,
			"line_id": line.line_id or f"Line {idx + 1}",
			"location": line.location or "",
			"qty": line.qty or 1,
			"notes": line.notes or "",
			"manufacturer_type": line.manufacturer_type or "ILLUMENATE",
			"product_type": line.product_type or None,
			"configuration_status": line.configuration_status or "Pending",
			"configured_fixture": line.configured_fixture or None,
			"configured_tape_neon": line.configured_tape_neon or None,
			"ill_item_code": line.ill_item_code or None,
			"is_pending": _line_is_pending(line),
			"summary": _line_summary(line),
		})

	summary = _schedule_summary(doc)
	summary.update({
		"success": True,
		"can_write": schedule_has_permission(doc, "write", frappe.session.user),
		"not_editable_reason": None if summary["is_editable"] else _schedule_not_editable_reason(doc),
		"lines": lines,
		"locations": locations,
		"next_fixture_type": _next_fixture_type(doc, _coerce_list(used_json)),
	})
	return summary


def _line_is_pending(line) -> bool:
	"""A line the desk tool may configure in place without destroying data."""
	if line.manufacturer_type == "OTHER":
		return True
	if line.manufacturer_type == "ACCESSORY":
		return False
	return (line.configuration_status or "Pending") != "Configured" and not (
		line.configured_fixture or line.configured_tape_neon or line.get("configured_led_sheet")
	)


def _line_summary(line) -> str:
	if line.manufacturer_type == "OTHER":
		bits = [b for b in (line.manufacturer_name, line.fixture_model_number) if b]
		return " ".join(bits) or _("Other manufacturer")
	if line.manufacturer_type == "ACCESSORY":
		return line.accessory_item_name or line.accessory_item or _("Accessory")
	if line.configured_fixture or line.configured_tape_neon:
		return line.ill_item_code or line.configured_fixture or line.configured_tape_neon
	return _("{0} (Pending)").format(line.product_type or _("ilLumenate"))


@frappe.whitelist()
def get_next_fixture_type(schedule: str | None = None, used_json: str | list | None = None) -> str:
	"""Next free fixture type across the schedule and ids already used on the form."""
	_require_internal_user()
	doc = None
	if schedule:
		doc, err = _load_schedule(schedule, "read")
		if err:
			frappe.throw(err["error"])
	return _next_fixture_type(doc, _coerce_list(used_json))


# ═══════════════════════════════════════════════════════════════════════
# PROJECT / SCHEDULE CREATE-OR-GET
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def ensure_project_and_schedule(
	customer: str,
	project: str | None = None,
	project_name: str | None = None,
	schedule: str | None = None,
	schedule_name: str | None = None,
) -> dict[str, Any]:
	"""Create-or-get the ilL-Project + ilL-Project-Fixture-Schedule pair.

	``project`` / ``schedule`` name existing records; when absent a new one is
	created from ``project_name`` / ``schedule_name``. The project's customer
	must match ``customer`` (the transaction's customer).
	"""
	_require_internal_user()

	customer = (customer or "").strip()
	if not customer:
		return _error(_("Set the Customer on the document first."))
	if not frappe.db.exists("Customer", customer):
		return _error(_("Customer {0} was not found.").format(customer))

	created_project = False
	created_schedule = False

	# ── Project ──────────────────────────────────────────────────────
	if project:
		if not frappe.db.exists(PROJECT_DOCTYPE, project):
			return _error(_("Project {0} was not found.").format(project))
		project_doc = frappe.get_doc(PROJECT_DOCTYPE, project)
		if project_doc.customer != customer:
			return _error(
				_("Project {0} belongs to customer {1}, not {2}.").format(
					project_doc.project_name or project_doc.name, project_doc.customer, customer
				)
			)
		if not project_has_permission(project_doc, "write", frappe.session.user):
			return _error(_("You do not have write permission on Project {0}.").format(project))
	else:
		project_name = (project_name or "").strip()
		if not project_name:
			return _error(_("Enter a name for the new project."))
		if not frappe.has_permission(PROJECT_DOCTYPE, "create"):
			return _error(_("You do not have permission to create projects."))
		project_doc = frappe.new_doc(PROJECT_DOCTYPE)
		project_doc.project_name = project_name
		project_doc.customer = customer
		project_doc.status = "ACTIVE"
		project_doc.is_active = 1
		project_doc.insert()
		created_project = True

	# ── Schedule ─────────────────────────────────────────────────────
	if schedule:
		schedule_doc, err = _load_schedule(schedule, "write")
		if err:
			return err
		if schedule_doc.ill_project != project_doc.name:
			return _error(
				_("Fixture Schedule {0} belongs to a different project.").format(schedule_doc.name)
			)
	else:
		if not frappe.has_permission(SCHEDULE_DOCTYPE, "create"):
			return _error(_("You do not have permission to create fixture schedules."))
		schedule_doc = frappe.new_doc(SCHEDULE_DOCTYPE)
		schedule_doc.schedule_name = (schedule_name or "").strip() or DEFAULT_SCHEDULE_NAME
		schedule_doc.ill_project = project_doc.name
		schedule_doc.customer = project_doc.customer
		schedule_doc.status = "DRAFT"
		schedule_doc.inherits_project_privacy = 1
		schedule_doc.insert()
		created_schedule = True

	return {
		"success": True,
		"customer": customer,
		"project": project_doc.name,
		"project_name": project_doc.project_name,
		"schedule": schedule_doc.name,
		"schedule_name": schedule_doc.schedule_name,
		"status": schedule_doc.status,
		"is_locked": cint(schedule_doc.get("is_locked")),
		"is_editable": _schedule_is_editable(schedule_doc),
		"not_editable_reason": None if _schedule_is_editable(schedule_doc) else _schedule_not_editable_reason(schedule_doc),
		"created_project": created_project,
		"created_schedule": created_schedule,
	}


@frappe.whitelist()
def create_schedule_version(schedule: str) -> dict[str, Any]:
	"""Thin wrapper over ``create_new_version`` for locked / QUOTED schedules."""
	_require_internal_user()
	doc, err = _load_schedule(schedule, "write")
	if err:
		return err
	if cint(doc.get("is_locked")):
		# A locked schedule is already superseded; find the newest open version.
		root = doc.version_parent or doc.name
		latest = frappe.get_all(
			SCHEDULE_DOCTYPE,
			filters={"version_parent": root, "is_locked": 0},
			fields=["name"],
			order_by="version desc",
			limit=1,
		)
		if latest:
			new_doc = frappe.get_doc(SCHEDULE_DOCTYPE, latest[0].name)
			summary = _schedule_summary(new_doc)
			summary.update({"success": True, "reused_existing_version": True})
			return summary
		return _error(_("Schedule {0} is locked and has no open version to continue on.").format(doc.name))

	new_name = doc.create_new_version(version_notes=_("Created from the desk configurator"))
	new_doc = frappe.get_doc(SCHEDULE_DOCTYPE, new_name)
	summary = _schedule_summary(new_doc)
	summary.update({"success": True, "reused_existing_version": False, "previous_schedule": doc.name})
	return summary


# ═══════════════════════════════════════════════════════════════════════
# BUILD A CONFIGURED LINE
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def build_configured_line(
	parent_doctype: str,
	product_type: str,
	selections_json: str | dict[str, Any],
	header_json: str | dict[str, Any] | None = None,
	qty: float = 1,
	fixture_type: str | None = None,
	location: str | None = None,
	notes: str | None = None,
	schedule: str | None = None,
	line_idx: int | None = None,
	product_slug: str | None = None,
	segments_json: str | list | None = None,
	tape_neon_template: str | None = None,
	parent_name: str | None = None,
	variant_origin: str | None = None,
) -> dict[str, Any]:
	"""Persist the configured product (+ schedule line) and return row values.

	See the module docstring: nothing is written to the Quotation / Sales
	Order here; the client inserts ``row_values`` and sets
	``header_values.ill_fixture_schedule``.
	"""
	_require_internal_user()
	_require_parent_doctype(parent_doctype)
	if parent_name and not frappe.has_permission(parent_doctype, "write", parent_name):
		frappe.throw(_("You do not have write permission on {0} {1}.").format(parent_doctype, parent_name), frappe.PermissionError)

	product_type = _normalize_product_type(product_type)
	if product_type not in DESK_PRODUCT_TYPES:
		return _error(_("{0} is not supported by the desk configurator yet.").format(product_type))

	qty = flt(qty) or 1
	fixture_type = (fixture_type or "").strip() or None
	location = (location or "").strip() or None
	notes = (notes or "").strip() or None
	selections = _coerce_dict(selections_json) or {}
	header = _safe_header(_coerce_dict(header_json) or {})
	variant_origin = variant_origin or ("Sales Order Tool" if parent_doctype == "Sales Order" else "Quotation Tool")

	# ── 1. Schedule preflight (before any engine write) ─────────────
	schedule_doc = None
	line_idx_int: int | None = None
	if schedule:
		schedule_doc, err = _load_schedule(schedule, "write")
		if err:
			return err
		if not _schedule_is_editable(schedule_doc):
			return _error(_schedule_not_editable_reason(schedule_doc), schedule_not_editable=True, schedule=schedule_doc.name)
		if line_idx not in (None, ""):
			line_idx_int = cint(line_idx)
			if not (0 <= line_idx_int < len(schedule_doc.lines or [])):
				return _error(_("Schedule line {0} does not exist on {1}.").format(line_idx, schedule_doc.name))
		if not fixture_type:
			fixture_type = _next_fixture_type(schedule_doc, [])
	if not fixture_type:
		fixture_type = _next_fixture_type(None, [])

	# ── 2. Engine: persist the configured record ────────────────────
	try:
		if product_type == PRODUCT_TYPE_SHEET:
			validation = _save_led_sheet(selections)
		else:
			if product_type == PRODUCT_TYPE_FIXTURE:
				payload = _fixture_payload_from_portal_selections(product_slug, selections, qty)
			else:
				payload = _tape_neon_payload_from_portal_selections(product_type, selections, segments_json)
			validation = _dispatch_save(
				product_type,
				payload,
				parent_configured_fixture=None,
				parent_configured_tape_neon=None,
				tape_neon_template=tape_neon_template if product_type != PRODUCT_TYPE_FIXTURE else None,
				variant_origin=variant_origin,
			)
	except frappe.ValidationError as exc:
		return _error(str(exc))

	if not validation.get("is_valid"):
		return _error(
			validation.get("error")
			or _error_text_from_messages(validation.get("messages"))
			or _("Configuration validation failed."),
			messages=validation.get("messages") or [],
		)

	# ── 3. Item / BOM / Item Price ──────────────────────────────────
	if product_type == PRODUCT_TYPE_FIXTURE:
		configured_name = validation.get("configured_fixture_id")
		if not configured_name:
			return _error(_("The engine did not return a configured fixture id."))
		artifact = _ensure_fixture_artifacts(configured_name)
		configured_doc = frappe.get_doc("ilL-Configured-Fixture", configured_name)
	elif product_type == PRODUCT_TYPE_SHEET:
		configured_name = validation.get("configured_led_sheet")
		if not configured_name:
			return _error(_("The engine did not return a configured LED sheet id."))
		# Shared with the schedule → quote conversion: Item, BOM and MSRP Item Price.
		artifact = _ensure_configured_artifacts(PRODUCT_TYPE_SHEET, None, None, configured_name)
		configured_doc = frappe.get_doc("ilL-Configured-LED-Sheet", configured_name)
	else:
		configured_name = validation.get("configured_tape_neon")
		if not configured_name:
			return _error(_("The engine did not return a configured tape/neon id."))
		artifact = _ensure_tape_neon_artifacts(configured_name, product_type)
		configured_doc = frappe.get_doc("ilL-Configured-Tape-Neon", configured_name)

	# LED Sheet: the panel bundle MSRP lives on the configured record; cables and
	# drivers are separate accessory lines, so never use the engine's total_msrp.
	msrp_unit = flt(configured_doc.msrp) if product_type == PRODUCT_TYPE_SHEET else _resolve_msrp_unit(configured_doc, validation)
	ensure_configured_item_price(artifact["item_code"], configured_doc, msrp=msrp_unit)
	if msrp_unit is not None:
		artifact["msrp_unit"] = msrp_unit

	# ── 4. Schedule line ────────────────────────────────────────────
	line_name = None
	line_position = None
	if schedule_doc is not None:
		frappe.db.savepoint(SCHEDULE_LINE_SAVEPOINT)
		try:
			line = _write_schedule_line(
				schedule_doc,
				line_idx_int,
				product_type,
				artifact,
				validation,
				fixture_type=fixture_type,
				location=location,
				qty=qty,
				notes=notes,
				tape_neon_template=tape_neon_template,
				msrp_unit=msrp_unit,
			)
			schedule_doc.save()
			line_name = line.name
			line_position = line.idx
		except Exception as exc:  # configured record/Item/BOM are idempotent and safe to keep
			frappe.db.rollback(save_point=SCHEDULE_LINE_SAVEPOINT)
			frappe.log_error(
				title=f"Desk configurator: schedule line write failed for {schedule_doc.name}",
				message=frappe.get_traceback(),
			)
			return _error(
				_("Configured {0} was saved, but the fixture schedule line could not be written: {1}").format(
					artifact["item_code"], str(exc)
				),
				configured_fixture=artifact.get("configured_fixture"),
				configured_tape_neon=artifact.get("configured_tape_neon"),
				item_code=artifact["item_code"],
			)

	# ── 5. Row values ───────────────────────────────────────────────
	row_values = _build_row_values(
		parent_doctype,
		parent_name,
		header,
		artifact,
		qty,
		section_label=location,
		fixture_type=fixture_type,
		schedule_line_id=line_name,
		additional_notes=notes,
	)

	used_ids = [fixture_type]
	accessory_rows = []
	if product_type == PRODUCT_TYPE_SHEET:
		accessory_rows = _led_sheet_accessory_rows(
			parent_doctype, parent_name, header, configured_doc, qty,
			section_label=location, fixture_type=fixture_type, schedule_line_id=line_name,
		)
	return {
		"success": True,
		"row_values": row_values,
		"accessory_rows": accessory_rows,
		"header_values": {"ill_fixture_schedule": schedule_doc.name if schedule_doc is not None else None},
		"schedule": schedule_doc.name if schedule_doc is not None else None,
		"schedule_line_name": line_name,
		"schedule_line_idx": (line_position - 1) if line_position else None,
		"fixture_type": fixture_type,
		"location": location,
		"product_type": product_type,
		"configured_fixture": artifact.get("configured_fixture"),
		"configured_tape_neon": artifact.get("configured_tape_neon"),
		"configured_led_sheet": artifact.get("configured_led_sheet"),
		"item_code": artifact["item_code"],
		"bom": artifact.get("bom"),
		"next_fixture_type": _next_fixture_type(schedule_doc, used_ids),
		"messages": (validation.get("messages") or []) + (artifact.get("messages") or []),
	}


def _save_led_sheet(selections: dict[str, Any]) -> dict[str, Any]:
	"""Persist an ilL-Configured-LED-Sheet from the wizard payload (no schedule write here).

	Returns an engine-shaped dict (``is_valid`` / ``configured_led_sheet`` / the
	validation result) so ``build_configured_line`` treats it like the other types.
	"""
	required = ("template", "spec")
	missing = [k for k in required if not selections.get(k)]
	if missing:
		return {"is_valid": False, "error": _("Missing LED Sheet selection: {0}").format(", ".join(missing))}
	kwargs = {
		"template": selections["template"],
		"spec": selections["spec"],
		"options": selections.get("options") or {},
		"coverage_width_ft": selections.get("coverage_width_ft") or 0,
		"coverage_height_ft": selections.get("coverage_height_ft") or 0,
		"coverage_width_value": selections.get("coverage_width_value"),
		"coverage_width_unit": selections.get("coverage_width_unit") or "ft",
		"coverage_height_value": selections.get("coverage_height_value"),
		"coverage_height_unit": selections.get("coverage_height_unit") or "ft",
		"include_power_supply": selections.get("include_power_supply", 1),
	}
	result = led_sheet_configurator.validate_sheet_configuration(**kwargs)
	saved = led_sheet_configurator.save_sheet_configuration(**kwargs)
	result.update({"is_valid": True, "configured_led_sheet": saved["configured_led_sheet"], "messages": []})
	return result


def _led_sheet_accessory_rows(
	parent_doctype: str,
	parent_name: str | None,
	header: dict[str, Any],
	sheet_doc,
	qty: float,
	*,
	section_label: str | None,
	fixture_type: str | None,
	schedule_line_id: str | None,
) -> list[dict[str, Any]]:
	"""Jumper / leader / power-supply rows for a configured LED Sheet bundle.

	Same quantities the portal writes as ACCESSORY schedule lines
	(``build_accessory_lines`` scaled by the bundle qty), returned as ready-to-
	insert child rows so the quote carries the full system, not just the panels.
	"""
	rows = []
	for spec in led_sheet_configurator._configured_sheet_accessory_specs(sheet_doc, cint(qty) or 1):
		is_power_supply = str(spec.get("notes", "")).startswith("Power supplies")
		artifact = {
			"product_type": PRODUCT_TYPE_SHEET,
			"item_code": spec["item_code"],
			"configured_led_sheet": sheet_doc.name,
			"source_doctype": "ilL-Configured-LED-Sheet",
			"source_name": sheet_doc.name,
			"template_code": sheet_doc.sheet_template,
			"configuration_snapshot": {
				"product_type": PRODUCT_TYPE_SHEET,
				"configured_led_sheet": sheet_doc.name,
				"accessory_for": sheet_doc.name,
				"notes": spec.get("notes"),
			},
			"power_supply": {
				"is_power_supply_line": is_power_supply,
				"power_supply_for": sheet_doc.name if is_power_supply else None,
			},
		}
		rows.append(
			_build_row_values(
				parent_doctype,
				parent_name,
				header,
				artifact,
				spec["qty"],
				section_label=section_label,
				fixture_type=fixture_type,
				schedule_line_id=schedule_line_id,
				additional_notes=spec.get("notes"),
			)
		)
	return rows


def _resolve_msrp_unit(configured_doc, validation: dict[str, Any]) -> float | None:
	snapshot = getattr(configured_doc, "pricing_snapshot", None) or []
	if snapshot and getattr(snapshot[-1], "msrp_unit", None) is not None:
		return flt(snapshot[-1].msrp_unit)
	pricing = validation.get("pricing") or {}
	for key in ("msrp_unit", "total_msrp", "total_price_msrp"):
		if pricing.get(key):
			return flt(pricing[key])
	computed = validation.get("computed") or {}
	if computed.get("total_price_msrp"):
		return flt(computed["total_price_msrp"])
	return None


def _write_schedule_line(
	schedule_doc,
	line_idx: int | None,
	product_type: str,
	artifact: dict[str, Any],
	validation: dict[str, Any],
	*,
	fixture_type: str,
	location: str | None,
	qty: float,
	notes: str | None,
	tape_neon_template: str | None,
	msrp_unit: float | None,
):
	"""Append or overwrite the schedule line for the configured product (no save)."""
	line = schedule_doc.lines[line_idx] if line_idx is not None else schedule_doc.append("lines", {})

	if product_type == PRODUCT_TYPE_FIXTURE:
		line.manufacturer_type = "ILLUMENATE"
		line.product_type = PRODUCT_TYPE_FIXTURE
		line.fixture_template = artifact.get("template_code")
		line.configured_fixture = artifact["configured_fixture"]
		line.configured_tape_neon = None
		line.tape_neon_template = None
		line.variant_selections = None
		line.configuration_status = "Configured"
		line.ill_item_code = artifact["item_code"]
		line.manufacturable_length_mm = artifact.get("mfg_length_mm")
		line.notes = notes or ""
	elif product_type == PRODUCT_TYPE_SHEET:
		line.manufacturer_type = "ILLUMENATE"
		line.product_type = PRODUCT_TYPE_SHEET
		line.led_sheet_template = artifact.get("template_code")
		line.configured_led_sheet = artifact["configured_led_sheet"]
		line.configured_fixture = None
		line.fixture_template = None
		line.configured_tape_neon = None
		line.tape_neon_template = None
		line.variant_selections = None
		line.configuration_status = "Configured"
		line.ill_item_code = artifact["item_code"]
		line.manufacturable_length_mm = None
		line.notes = notes or (
			f"Configured LED Sheet {artifact['configured_led_sheet']} | {validation.get('part_number', '')} | "
			f"{validation.get('panels_wide')}x{validation.get('panels_tall')} panels, "
			f"{validation.get('total_groups')} group(s)"
		)
	else:
		result = dict(validation)
		computed = dict(result.get("computed") or {})
		if msrp_unit is not None and not computed.get("total_price_msrp"):
			computed["total_price_msrp"] = msrp_unit
		result["computed"] = computed
		result["configured_tape_neon"] = artifact["configured_tape_neon"]
		template_name = tape_neon_template or artifact.get("template_code")
		tape_neon_configurator._write_tape_neon_line(
			line,
			result,
			template_name=template_name,
			variant_extra={
				"template_code": template_name,
				"pricing": {"total_price_msrp": computed.get("total_price_msrp", 0)},
			},
		)
		line.configured_fixture = None
		line.fixture_template = None
		line.ill_item_code = artifact["item_code"]
		if notes:
			line.notes = notes

	line.line_id = fixture_type
	line.location = location
	line.qty = cint(qty) or 1
	# Clear OTHER-manufacturer data when overriding such a line with an ilLumenate product.
	for field in ("manufacturer_name", "fixture_model_number", "accessory_item", "accessory_product_type"):
		if line.meta.has_field(field):
			line.set(field, None)
	if product_type == PRODUCT_TYPE_SHEET:
		# Jumper / leader / power-supply ACCESSORY rows scaled by the bundle qty,
		# exactly as the portal LED Sheet configurator writes them.
		led_sheet_configurator.resync_led_sheet_line_accessories(schedule_doc, line, cint(qty) or 1)
	return line


def _safe_header(header: dict[str, Any]) -> dict[str, Any]:
	return {k: header.get(k) for k in SAFE_HEADER_FIELDS if header.get(k) not in (None, "")}


def _build_row_values(
	parent_doctype: str,
	parent_name: str | None,
	header: dict[str, Any],
	artifact: dict[str, Any],
	qty: float,
	*,
	section_label: str | None,
	fixture_type: str | None,
	schedule_line_id: str | None,
	additional_notes: str | None,
) -> dict[str, Any]:
	"""Run the shared row writer against an in-memory parent and return child values."""
	tmp = frappe.new_doc(parent_doctype)
	tmp.update(header)
	if parent_name:
		tmp.name = parent_name
	row = tmp.append("items", {})
	_apply_artifact_to_row(
		tmp,
		row,
		artifact,
		qty,
		_serialize_json(artifact.get("configuration_snapshot")),
		section_label=section_label,
		fixture_type=fixture_type,
		schedule_line_id=schedule_line_id,
		additional_notes=additional_notes,
	)
	_set_child_value(row, "stock_uom", frappe.db.get_value("Item", artifact["item_code"], "stock_uom") or row.get("uom"))
	_set_child_value(row, "stock_qty", flt(qty) * flt(row.get("conversion_factor") or 1))
	_set_child_value(row, "amount", flt(row.get("rate")) * flt(qty))

	child_meta = frappe.get_meta(f"{parent_doctype} Item")
	values = {}
	for key, value in row.as_dict().items():
		if key in ROW_VALUE_EXCLUDED_KEYS or value is None or key.startswith("__"):
			continue
		if not child_meta.has_field(key):
			continue
		values[key] = value
	return values


# ═══════════════════════════════════════════════════════════════════════
# QUOTATION LIFECYCLE HOOKS
# ═══════════════════════════════════════════════════════════════════════


def on_quotation_submit(doc, method=None):
	"""A submitted Quotation marks its DRAFT / READY schedule as QUOTED."""
	name = doc.get("ill_fixture_schedule")
	if not name or not frappe.db.exists(SCHEDULE_DOCTYPE, name):
		return
	schedule = frappe.get_doc(SCHEDULE_DOCTYPE, name)
	if cint(schedule.get("is_locked")) or schedule.status not in EDITABLE_SCHEDULE_STATUSES:
		return

	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		transition_schedule_status,
	)

	try:
		if schedule.status == "DRAFT":
			# The state machine only allows READY -> QUOTED; stepping through READY
			# keeps the "all lines configured" validation in force.
			transition_schedule_status(schedule, "READY")
			schedule.reload()
		transition_schedule_status(schedule, "QUOTED")
		schedule.add_comment("Info", _("Marked QUOTED by Quotation {0}").format(doc.name))
	except Exception:  # never block the Quotation submit on schedule bookkeeping
		frappe.log_error(
			title=f"Schedule QUOTED transition failed for Quotation {doc.name}",
			message=frappe.get_traceback(),
		)
		frappe.msgprint(
			_("Quotation submitted, but Fixture Schedule {0} could not be marked QUOTED. See Error Log.").format(name),
			indicator="orange",
			alert=True,
		)


def on_quotation_cancel(doc, method=None):
	"""Cancelling a Quotation leaves the schedule status untouched; log only."""
	name = doc.get("ill_fixture_schedule")
	if not name or not frappe.db.exists(SCHEDULE_DOCTYPE, name):
		return
	frappe.get_doc(SCHEDULE_DOCTYPE, name).add_comment(
		"Info", _("Quotation {0} was cancelled; schedule status left unchanged.").format(doc.name)
	)
