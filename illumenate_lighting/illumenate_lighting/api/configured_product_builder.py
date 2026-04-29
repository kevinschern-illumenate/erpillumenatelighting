# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Builder module for the Quotation/Sales-Order "Build / Add Configured
Product" tool.

This sits in front of the existing engines:
    - ``configurator_engine``        (Linear Fixture)
    - ``tape_neon_configurator``     (LED Tape, LED Neon)
    - ``tape_neon_bom``              (tape/neon BOM)
    - ``manufacturing_generator``    (fixture Item / BOM)

It exposes three whitelisted entry points for the UI:

* :func:`calculate_and_lookup` — dry-run the engine (no record persisted),
  hash the configuration, and tell the caller whether an existing
  ilL-Configured-Fixture / ilL-Configured-Tape-Neon already matches.  This
  enables the "build new" vs. "reuse existing" branch in the tool.
* :func:`preview_bom` — return BOM rows for a configured record (or for the
  candidate selections, by first persisting the configured record).
* :func:`save_and_apply` — persist the configured record (creating a variant
  ``-V(XXXX)`` when ``parent_configured_*`` is supplied), build/reuse its
  Item + BOM, and write it onto a Quotation/Sales-Order row.

The lineage helpers live here too so other modules can locate the root
ancestor for an existing configured product.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from illumenate_lighting.illumenate_lighting.api import (
    configurator_engine,
    tape_neon_bom,
    tape_neon_configurator,
)
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
    _create_or_get_bom,
    _create_or_get_configured_item,
    _create_or_get_configured_tape_neon_item,
    _ensure_item_group_exists,
    CONFIGURED_ITEM_GROUP,
    CONFIGURED_NEON_ITEM_GROUP,
    CONFIGURED_TAPE_ITEM_GROUP,
)
from illumenate_lighting.illumenate_lighting.api.quote_order_configurator import (
    PRODUCT_TYPES,
    PRODUCT_TYPE_FIXTURE,
    PRODUCT_TYPE_NEON,
    PRODUCT_TYPE_TAPE,
    _apply_artifact_to_row,
    _get_editable_parent,
    _get_or_add_item_row,
    _get_required_doc,
    _line_description_from_item,
    _normalize_product_type,
    _serialize_json,
)


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def calculate_and_lookup(
    product_type: str,
    payload_json: str | dict[str, Any] | None = None,
    parent_configured_fixture: str | None = None,
    parent_configured_tape_neon: str | None = None,
    tape_neon_template: str | None = None,
) -> dict[str, Any]:
    """Run a dry-run validation and return existing-record lookup info.

    The engine is invoked with ``_skip_record_creation=True`` so no
    ``ilL-Configured-*`` is persisted.  The candidate config hash + part
    number returned by the engine are then used to look up any existing
    record so the UI can offer a "reuse" path.

    Args:
        product_type: ``"Linear Fixture"``, ``"LED Tape"``, or ``"LED Neon"``.
        payload_json: Engine arguments as a JSON string or dict.  Shape
            depends on ``product_type`` — see ``_dispatch_calculate``.
        parent_configured_fixture: Set when calculating a variant of an
            existing linear-fixture record.  Skips reuse-by-hash on save.
        parent_configured_tape_neon: Same idea, for tape/neon.
        tape_neon_template: When dry-running a tape/neon flow that should
            also surface a driver plan, pass the template name here.

    Returns:
        ``{
            "success": bool,
            "product_type": str,
            "is_valid": bool,
            "candidate_config_hash": str,
            "candidate_part_number": str,
            "existing_record": str | None,
            "validation": dict,   # raw engine response
            "messages": list,
        }``
    """
    product_type = _normalize_product_type(product_type)
    payload = _coerce_dict(payload_json) or {}

    validation = _dispatch_calculate(
        product_type,
        payload,
        parent_configured_fixture=parent_configured_fixture,
        parent_configured_tape_neon=parent_configured_tape_neon,
        tape_neon_template=tape_neon_template,
    )

    if not validation.get("is_valid"):
        return {
            "success": False,
            "product_type": product_type,
            "is_valid": False,
            "candidate_config_hash": None,
            "candidate_part_number": None,
            "existing_record": None,
            "validation": validation,
            "messages": validation.get("messages") or [],
            "error": validation.get("error"),
        }

    candidate_hash = validation.get("candidate_config_hash")
    candidate_part_number = validation.get("candidate_part_number") or validation.get("part_number")

    existing_record = None
    if candidate_hash and not (parent_configured_fixture or parent_configured_tape_neon):
        if product_type == PRODUCT_TYPE_FIXTURE:
            existing_record = frappe.db.get_value(
                "ilL-Configured-Fixture", {"config_hash": candidate_hash}, "name"
            )
        else:
            existing_record = frappe.db.get_value(
                "ilL-Configured-Tape-Neon", {"config_hash": candidate_hash}, "name"
            )

    return {
        "success": True,
        "product_type": product_type,
        "is_valid": True,
        "candidate_config_hash": candidate_hash,
        "candidate_part_number": candidate_part_number,
        "existing_record": existing_record,
        "validation": validation,
        "messages": validation.get("messages") or [],
    }


@frappe.whitelist()
def preview_bom(
    product_type: str,
    configured_fixture: str | None = None,
    configured_tape_neon: str | None = None,
) -> dict[str, Any]:
    """Return BOM rows for an *existing* configured record.

    For dry-run BOM previews on candidate (unsaved) configurations, the
    caller should first call :func:`save_and_apply` with a target row, or
    call this after persisting the record via the engine.
    """
    product_type = _normalize_product_type(product_type)

    if product_type == PRODUCT_TYPE_FIXTURE:
        from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
            build_fixture_bom_items,
        )

        fixture = _get_required_doc(
            "ilL-Configured-Fixture", configured_fixture, "configured_fixture"
        )
        items = build_fixture_bom_items(fixture)
        return {
            "success": True,
            "product_type": product_type,
            "configured_fixture": fixture.name,
            "configured_tape_neon": None,
            "items": _format_bom_rows(items),
            "messages": [],
        }

    configured = _get_required_doc(
        "ilL-Configured-Tape-Neon", configured_tape_neon, "configured_tape_neon"
    )
    items = tape_neon_bom.build_tape_neon_bom_items(configured)
    return {
        "success": True,
        "product_type": product_type,
        "configured_fixture": None,
        "configured_tape_neon": configured.name,
        "items": _format_bom_rows(items),
        "messages": [],
    }


@frappe.whitelist()
def save_and_apply(
    parent_doctype: str,
    parent_name: str,
    product_type: str,
    payload_json: str | dict[str, Any] | None = None,
    parent_configured_fixture: str | None = None,
    parent_configured_tape_neon: str | None = None,
    tape_neon_template: str | None = None,
    row_name: str | None = None,
    qty: float = 1,
    variant_origin: str | None = "Quotation Tool",
) -> dict[str, Any]:
    """Persist the configured record (or variant) and write it to a row.

    Workflow:
        1. Run the engine with the provided payload (record IS persisted).
        2. Build/reuse the configured Item.
        3. Build/reuse the BOM (fixture: ``_create_or_get_bom``;
           tape/neon: :func:`tape_neon_bom.create_or_get_tape_neon_bom`).
        4. Append/update the Quotation or Sales Order row via
           :func:`quote_order_configurator._apply_artifact_to_row`.

    When ``parent_configured_*`` is supplied, a variant ``-V(XXXX)`` record
    is always created (the engine layer suppresses hash-based reuse).
    """
    product_type = _normalize_product_type(product_type)
    parent_doc = _get_editable_parent(parent_doctype, parent_name)
    qty = flt(qty) or 1
    payload = _coerce_dict(payload_json) or {}

    # ── Step 1: persist the configured record via the engine ─────────
    validation = _dispatch_save(
        product_type,
        payload,
        parent_configured_fixture=parent_configured_fixture,
        parent_configured_tape_neon=parent_configured_tape_neon,
        tape_neon_template=tape_neon_template,
        variant_origin=variant_origin,
    )
    if not validation.get("is_valid"):
        return {
            "success": False,
            "product_type": product_type,
            "validation": validation,
            "messages": validation.get("messages") or [],
            "error": validation.get("error"),
        }

    if product_type == PRODUCT_TYPE_FIXTURE:
        configured_name = validation.get("configured_fixture_id")
        if not configured_name:
            frappe.throw(_("Engine did not return a configured fixture id."))
        artifact = _ensure_fixture_artifacts(configured_name)
    else:
        configured_name = validation.get("configured_tape_neon")
        if not configured_name:
            frappe.throw(_("Engine did not return a configured tape/neon id."))
        artifact = _ensure_tape_neon_artifacts(configured_name, product_type)

    # ── Step 4: write to row ─────────────────────────────────────────
    row = _get_or_add_item_row(parent_doc, row_name)
    _apply_artifact_to_row(
        parent_doc,
        row,
        artifact,
        qty,
        payload.get("configuration_json")
        or _serialize_json(artifact.get("configuration_snapshot")),
    )

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
        "messages": (validation.get("messages") or []) + (artifact.get("messages") or []),
    }


# ═══════════════════════════════════════════════════════════════════════
# LINEAGE HELPERS
# ═══════════════════════════════════════════════════════════════════════


def walk_configured_lineage(name: str, doctype: str) -> list[str]:
    """Return the ancestor chain (root → ... → name) for a configured record.

    ``doctype`` must be ``"ilL-Configured-Fixture"`` or
    ``"ilL-Configured-Tape-Neon"``.  Cycles are guarded at 16 hops.
    """
    if not name or doctype not in ("ilL-Configured-Fixture", "ilL-Configured-Tape-Neon"):
        return []
    parent_field = (
        "parent_configured_fixture"
        if doctype == "ilL-Configured-Fixture"
        else "parent_configured_tape_neon"
    )
    chain: list[str] = []
    visited: set[str] = set()
    current: str | None = name
    for _hop in range(16):
        if not current or current in visited:
            break
        visited.add(current)
        chain.append(current)
        current = frappe.db.get_value(doctype, current, parent_field)
    chain.reverse()
    return chain


def resolve_root_configured(name: str, doctype: str) -> str | None:
    """Return the root ancestor (or ``name`` itself when no parent is set)."""
    chain = walk_configured_lineage(name, doctype)
    return chain[0] if chain else None


# ═══════════════════════════════════════════════════════════════════════
# DISPATCH
# ═══════════════════════════════════════════════════════════════════════


def _dispatch_calculate(
    product_type: str,
    payload: dict[str, Any],
    *,
    parent_configured_fixture: str | None,
    parent_configured_tape_neon: str | None,
    tape_neon_template: str | None,
) -> dict[str, Any]:
    """Run the appropriate engine entry point with ``_skip_record_creation=True``."""
    if product_type == PRODUCT_TYPE_FIXTURE:
        if payload.get("segments_json") or payload.get("multi_segment"):
            return configurator_engine.validate_and_quote_multisegment(
                _skip_record_creation=True,
                parent_configured_fixture=parent_configured_fixture,
                **_fixture_multisegment_kwargs(payload),
            )
        return configurator_engine.validate_and_quote(
            _skip_record_creation=True,
            parent_configured_fixture=parent_configured_fixture,
            **_fixture_singlesegment_kwargs(payload),
        )

    selections = payload.get("selections")
    if isinstance(selections, dict):
        selections = json.dumps(selections)

    if product_type == PRODUCT_TYPE_TAPE:
        return tape_neon_configurator.validate_tape_configuration(
            selections,
            _skip_record_creation=True,
            parent_configured_tape_neon=parent_configured_tape_neon,
            include_power_supply=bool(payload.get("include_power_supply", True)),
            dimming_protocol_code=payload.get("dimming_protocol_code"),
            tape_neon_template=tape_neon_template,
        )

    # LED Neon
    segments = payload.get("segments_json") or payload.get("segments")
    if isinstance(segments, list):
        segments = json.dumps(segments)
    return tape_neon_configurator.validate_neon_configuration(
        selections,
        segments,
        _skip_record_creation=True,
        parent_configured_tape_neon=parent_configured_tape_neon,
        include_power_supply=bool(payload.get("include_power_supply", True)),
        dimming_protocol_code=payload.get("dimming_protocol_code"),
        tape_neon_template=tape_neon_template,
    )


def _dispatch_save(
    product_type: str,
    payload: dict[str, Any],
    *,
    parent_configured_fixture: str | None,
    parent_configured_tape_neon: str | None,
    tape_neon_template: str | None,
    variant_origin: str | None,
) -> dict[str, Any]:
    """Run the engine with persistence enabled."""
    if product_type == PRODUCT_TYPE_FIXTURE:
        if payload.get("segments_json") or payload.get("multi_segment"):
            return configurator_engine.validate_and_quote_multisegment(
                _skip_record_creation=False,
                parent_configured_fixture=parent_configured_fixture,
                variant_origin=variant_origin,
                **_fixture_multisegment_kwargs(payload),
            )
        return configurator_engine.validate_and_quote(
            _skip_record_creation=False,
            parent_configured_fixture=parent_configured_fixture,
            variant_origin=variant_origin,
            **_fixture_singlesegment_kwargs(payload),
        )

    selections = payload.get("selections")
    if isinstance(selections, dict):
        selections = json.dumps(selections)

    if product_type == PRODUCT_TYPE_TAPE:
        return tape_neon_configurator.validate_tape_configuration(
            selections,
            _skip_record_creation=False,
            parent_configured_tape_neon=parent_configured_tape_neon,
            include_power_supply=bool(payload.get("include_power_supply", True)),
            dimming_protocol_code=payload.get("dimming_protocol_code"),
            variant_origin=variant_origin,
            tape_neon_template=tape_neon_template,
        )

    segments = payload.get("segments_json") or payload.get("segments")
    if isinstance(segments, list):
        segments = json.dumps(segments)
    return tape_neon_configurator.validate_neon_configuration(
        selections,
        segments,
        _skip_record_creation=False,
        parent_configured_tape_neon=parent_configured_tape_neon,
        include_power_supply=bool(payload.get("include_power_supply", True)),
        dimming_protocol_code=payload.get("dimming_protocol_code"),
        variant_origin=variant_origin,
        tape_neon_template=tape_neon_template,
    )


# ═══════════════════════════════════════════════════════════════════════
# ARTIFACT ENSURING
# ═══════════════════════════════════════════════════════════════════════


def _ensure_fixture_artifacts(configured_fixture: str) -> dict[str, Any]:
    """Build/reuse Item + BOM for a saved fixture and return the artifact dict."""
    fixture = frappe.get_doc("ilL-Configured-Fixture", configured_fixture)

    # Idempotently ensure the Configured Fixtures Item Group exists before
    # the Item is written.  ``_create_or_get_configured_item`` already does
    # this internally, but it is cheap to assert here so the qoc tool can
    # be called in fresh sites without the group pre-loaded.
    _ensure_item_group_exists(CONFIGURED_ITEM_GROUP)

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
        "product_type": PRODUCT_TYPE_FIXTURE,
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
        "parent_configured_fixture": getattr(fixture, "parent_configured_fixture", None),
        "configuration_snapshot": _fixture_configuration_snapshot(fixture),
        "messages": (item_result.get("messages") or []) + (bom_result.get("messages") or []),
    }


def _ensure_tape_neon_artifacts(configured_tape_neon: str, product_type: str) -> dict[str, Any]:
    """Build/reuse Item + BOM for a saved tape/neon record."""
    configured = frappe.get_doc("ilL-Configured-Tape-Neon", configured_tape_neon)

    if configured.product_category and configured.product_category != product_type:
        frappe.throw(_("Configured tape/neon product {0} is {1}, not {2}").format(
            configured.name, configured.product_category, product_type
        ))

    is_neon = product_type == PRODUCT_TYPE_NEON
    _ensure_item_group_exists(
        CONFIGURED_NEON_ITEM_GROUP if is_neon else CONFIGURED_TAPE_ITEM_GROUP
    )

    item_result = _create_or_get_configured_tape_neon_item(configured, skip_if_exists=True)
    if not item_result.get("success"):
        frappe.throw(_messages_to_html(item_result.get("messages")))

    configured.configured_item = item_result["item_code"]
    configured.save(ignore_permissions=True)

    bom_result = tape_neon_bom.create_or_get_tape_neon_bom(
        configured, item_result["item_code"], skip_if_exists=True
    )
    bom_messages = bom_result.get("messages") or []
    bom_name = bom_result.get("bom_name")

    return {
        "product_type": product_type,
        "source_doctype": "ilL-Configured-Tape-Neon",
        "source_name": configured.name,
        "configured_fixture": None,
        "configured_tape_neon": configured.name,
        "item_code": item_result["item_code"],
        "bom": bom_name,
        "description": _line_description_from_item(item_result["item_code"]),
        "template_code": configured.tape_neon_template,
        "requested_length_mm": configured.requested_length_mm,
        "mfg_length_mm": configured.manufacturable_length_mm,
        "runs_count": configured.total_segments,
        "total_watts": configured.total_watts,
        "finish": getattr(configured, "finish", None) or getattr(configured, "pcb_finish", None),
        "lens": None,
        "engine_version": getattr(configured, "engine_version", None),
        "parent_configured_tape_neon": getattr(configured, "parent_configured_tape_neon", None),
        "configuration_snapshot": _tape_neon_configuration_snapshot(configured),
        "messages": (item_result.get("messages") or []) + bom_messages,
    }


# ═══════════════════════════════════════════════════════════════════════
# PAYLOAD HELPERS
# ═══════════════════════════════════════════════════════════════════════


_FIXTURE_SINGLE_KEYS = (
    "fixture_template_code",
    "finish_code",
    "lens_appearance_code",
    "mounting_method_code",
    "endcap_style_start_code",
    "endcap_style_end_code",
    "endcap_color_code",
    "power_feed_type_code",
    "environment_rating_code",
    "tape_offering_id",
    "requested_overall_length_mm",
    "dimming_protocol_code",
    "qty",
    "start_feed_direction_code",
    "end_feed_direction_code",
    "start_leader_len_mm",
    "end_leader_len_mm",
    "include_power_supply",
)


_FIXTURE_MULTI_KEYS = (
    "fixture_template_code",
    "finish_code",
    "lens_appearance_code",
    "mounting_method_code",
    "endcap_color_code",
    "environment_rating_code",
    "tape_offering_id",
    "segments_json",
    "dimming_protocol_code",
    "qty",
    "include_power_supply",
)


def _fixture_singlesegment_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: payload[k] for k in _FIXTURE_SINGLE_KEYS if k in payload}


def _fixture_multisegment_kwargs(payload: dict[str, Any]) -> dict[str, Any]:
    kwargs = {k: payload[k] for k in _FIXTURE_MULTI_KEYS if k in payload}
    segments = kwargs.get("segments_json")
    if isinstance(segments, list):
        kwargs["segments_json"] = json.dumps(segments)
    return kwargs


def _coerce_dict(value) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            frappe.throw(_("Invalid JSON payload"))
    return None


def _format_bom_rows(rows) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for row in rows or []:
        item_code = row.get("item_code") if isinstance(row, dict) else getattr(row, "item_code", None)
        details = (
            frappe.db.get_value("Item", item_code, ["item_name", "description", "stock_uom"], as_dict=True)
            or {}
        )
        formatted.append({
            "item_code": item_code,
            "item_name": details.get("item_name") or item_code,
            "description": details.get("description"),
            "qty": row.get("qty") if isinstance(row, dict) else getattr(row, "qty", None),
            "uom": (row.get("uom") if isinstance(row, dict) else getattr(row, "uom", None))
                   or details.get("stock_uom"),
            "stock_uom": (row.get("stock_uom") if isinstance(row, dict) else getattr(row, "stock_uom", None))
                         or details.get("stock_uom"),
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
        "parent_configured_fixture": getattr(fixture, "parent_configured_fixture", None),
        "variant_suffix": getattr(fixture, "variant_suffix", None),
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
        "parent_configured_tape_neon": getattr(configured, "parent_configured_tape_neon", None),
        "variant_suffix": getattr(configured, "variant_suffix", None),
    }


def _messages_to_html(messages) -> str:
    texts = [m.get("text") for m in messages or [] if m.get("text")]
    return "<br>".join(texts) if texts else _("Configured product artifact generation failed.")
