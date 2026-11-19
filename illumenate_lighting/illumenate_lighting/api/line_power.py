# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Spec and load under catalog LED Tape / COB / Neon / Sheet rows (Quotation, Sales Order).

A row ordering a catalog tape, neon or sheet Item (not a configured build) carries its
spec's input voltage, W/ft (or W/sq ft) and max run, the row's length (or area) worked
out from its quantity and UOM, and the resulting load in watts. The print formats show
these under the item; the desk shows them in the row, a Load (W) column and a panel
under the Items grid.

Specs are found by Item: ``ilL-Spec-LED Tape`` is named by its Item, and
``ilL-Spec-LED-Sheet`` links one. A variant never borrows its template's spec: one
template covers outputs from 0.8 to 14.4 W/ft, so its values would misstate the load.
The Item's *current* group decides whether a missing spec is worth a note; the group
copied onto old rows is not trusted (sheets once sat in "LED Tape").

These are derived values: schedule sync, build links and commercial lineage ignore
them, and ``ill_total_watts`` (configured builds) is left alone.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

from illumenate_lighting.illumenate_lighting.api.line_power_math import (
	FAMILY_SHEET,
	FAMILY_TAPE,
	LP_FIELDS,
	compute_row,
	document_total_watts,
)

TAPE_SPEC = "ilL-Spec-LED Tape"
SHEET_SPEC = "ilL-Spec-LED-Sheet"
LED_GROUPS = ("LED Tape", "COB Tape", "LED Neon", "LED Sheet")
CHILD_DOCTYPES = {"Quotation": "Quotation Item", "Sales Order": "Sales Order Item"}
# A row carrying any of these orders a configured build, which has its own watts.
CONFIGURED_FIELDS = (
	"ill_configured_fixture",
	"ill_configured_tape_neon",
	"ill_configured_led_sheet",
	"ill_configured_group",
	"ill_configured_product",
)
ROW_INPUTS = ("item_code", "qty", "uom", "conversion_factor", "stock_uom", "is_alternative")
TAPE_FIELDS = (
	"name",
	"input_voltage",
	"watts_per_foot",
	"voltage_drop_max_run_length_ft",
	"max_run_single_feed_ft",
	"max_run_double_feed_ft",
)
SHEET_FIELDS = (
	"name",
	"item",
	"input_voltage",
	"sheet_area_sqft",
	"sheet_width_ft",
	"sheet_height_ft",
	"watts_per_sqft",
	"total_sheet_watts",
	"max_sqft_per_100w",
	"max_panels_per_feed",
)
MAX_PREVIEW_ROWS = 500
# Frappe creates these columns NOT NULL; the backfill writes 0 where a value is unset.
NUMERIC_FIELDTYPES = ("Check", "Int", "Currency", "Float", "Percent")
MAX_LOGGED_PARENTS = 50


# ═══════════════════════════════════════════════════════════════════════
# SPEC RESOLUTION
# ═══════════════════════════════════════════════════════════════════════


def _tape_spec(record) -> dict:
	return {
		"family": FAMILY_TAPE,
		"spec_doctype": TAPE_SPEC,
		"spec_name": record.get("name"),
		"input_voltage": record.get("input_voltage"),
		"watts_per_foot": record.get("watts_per_foot"),
		# The configurator's run limit; single-feed max where that is unset.
		"max_run_ft": record.get("voltage_drop_max_run_length_ft") or record.get("max_run_single_feed_ft"),
		"max_run_double_ft": record.get("max_run_double_feed_ft"),
	}


def _sheet_spec(record) -> dict:
	spec = {key: record.get(key) for key in SHEET_FIELDS if key not in ("name", "item")}
	spec.update(
		{
			"family": FAMILY_SHEET,
			"spec_doctype": SHEET_SPEC,
			"spec_name": record.get("name"),
		}
	)
	return spec


def resolve_specs(item_codes) -> dict[str, dict]:
	"""``{item_code: {"spec": dict | None, "tape_like": bool, "stock_uom": str}}``.

	Three queries for any number of Items: the Items, their tape specs, their sheet specs.
	"""
	codes = sorted({code for code in item_codes or [] if code})
	if not codes:
		return {}
	items = {
		row.get("name"): row
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", codes]},
			fields=["name", "item_group", "stock_uom"],
		)
	}
	tape = {
		row.get("name"): row
		for row in frappe.get_all(TAPE_SPEC, filters={"name": ["in", codes]}, fields=list(TAPE_FIELDS))
	}
	sheet: dict = {}
	for row in frappe.get_all(
		SHEET_SPEC,
		filters={"item": ["in", codes]},
		fields=list(SHEET_FIELDS),
		order_by="is_active desc, modified desc",
	):
		sheet.setdefault(row.get("item"), row)

	resolved = {}
	for code in codes:
		item = items.get(code) or {}
		spec = None
		if code in sheet:
			spec = _sheet_spec(sheet[code])
		elif code in tape:
			spec = _tape_spec(tape[code])
		resolved[code] = {
			"spec": spec,
			"tape_like": item.get("item_group") in LED_GROUPS,
			"stock_uom": item.get("stock_uom"),
		}
	return resolved


# ═══════════════════════════════════════════════════════════════════════
# ROW STAMPING
# ═══════════════════════════════════════════════════════════════════════


def eligible(row) -> bool:
	"""A catalog row whose spec and load we show (not a configured build, not a supply)."""
	if not row.get("item_code") or cint(row.get("ill_is_power_supply_line")):
		return False
	return not any(row.get(field) for field in CONFIGURED_FIELDS)


def _row_input(row, info) -> dict:
	return {
		"qty": row.get("qty"),
		"uom": row.get("uom"),
		"conversion_factor": row.get("conversion_factor"),
		"stock_uom": row.get("stock_uom") or (info or {}).get("stock_uom"),
	}


def values_for(row, resolved) -> dict:
	"""Every ``ill_lp_*`` value ``row`` should carry (all ``None`` for other rows)."""
	info = resolved.get(row.get("item_code")) if eligible(row) else None
	if not info:
		return compute_row({}, None)
	return compute_row(_row_input(row, info), info["spec"], info["tape_like"])


def _has_field(row, fieldname) -> bool:
	try:
		return bool(row.meta.has_field(fieldname))
	except AttributeError:
		return True


def stamp_rows(rows) -> int:
	"""Set (or clear) every row's ``ill_lp_*`` fields; returns how many rows changed."""
	rows = list(rows or [])
	resolved = resolve_specs([row.get("item_code") for row in rows if eligible(row)])
	changed = 0
	for row in rows:
		values = values_for(row, resolved)
		dirty = False
		for field, value in values.items():
			if (row.get(field) or None) == (value or None) or not _has_field(row, field):
				continue
			row.set(field, value)
			dirty = True
		changed += dirty
	return changed


def _skip_globally() -> bool:
	flags = frappe.flags
	return bool(
		flags.get("in_import") or flags.get("in_migrate") or flags.get("in_install") or flags.get("in_patch")
	)


def stamp_line_power(doc, method=None):
	"""Quotation / Sales Order ``validate`` (and Sales Order ``before_update_after_submit``).

	Runs after schedule sync, which can rescale row quantities. Never blocks a save:
	a failure is logged and the rows keep their previous values.
	"""
	if cint(doc.get("docstatus")) == 2 or _skip_globally():
		return
	try:
		stamp_rows(doc.get("items"))
	except Exception:
		frappe.log_error(title=f"Line power: {doc.doctype} {doc.name}", message=frappe.get_traceback())


# ═══════════════════════════════════════════════════════════════════════
# DESK
# ═══════════════════════════════════════════════════════════════════════


@frappe.whitelist()
def preview(rows):
	"""Values for unsaved rows, so the form shows them before saving. Writes nothing.

	``rows``: ``[{key, item_code, qty, uom, conversion_factor, stock_uom, is_alternative,
	ill_is_power_supply_line, ill_configured_*}]``. Returns ``{"rows": {key: values},
	"total_watts": float}``.
	"""
	if not (frappe.has_permission("Quotation", "read") or frappe.has_permission("Sales Order", "read")):
		frappe.throw(_("Not permitted to read Quotations or Sales Orders."), frappe.PermissionError)
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	rows = [row for row in rows or [] if isinstance(row, dict)]
	if len(rows) > MAX_PREVIEW_ROWS:
		frappe.throw(_("Too many rows to preview at once ({0}).").format(len(rows)))
	resolved = resolve_specs([row.get("item_code") for row in rows if eligible(row)])
	result, combined = {}, []
	for row in rows:
		values = values_for(row, resolved)
		if row.get("key"):
			result[str(row["key"])] = values
		combined.append({**row, **values})
	return {"rows": result, "total_watts": document_total_watts(combined)}


@frappe.whitelist()
def missing_specs():
	"""Enabled, sellable LED Items with no spec of their own."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can list missing specs."), frappe.PermissionError)
	items = frappe.get_all(
		"Item",
		filters={
			"item_group": ["in", list(LED_GROUPS)],
			"disabled": 0,
			"is_sales_item": 1,
			"has_variants": 0,
		},
		fields=["name", "item_name", "item_group", "variant_of"],
		order_by="item_group asc, name asc",
		limit_page_length=0,
	)
	resolved = resolve_specs([item.get("name") for item in items])
	return [item for item in items if not (resolved.get(item.get("name")) or {}).get("spec")]


# ═══════════════════════════════════════════════════════════════════════
# BACKFILL
# ═══════════════════════════════════════════════════════════════════════


def _candidate_items() -> list[str]:
	"""Items that can carry a spec line: LED groups, plus anything a spec names."""
	codes = set(frappe.get_all("Item", filters={"item_group": ["in", list(LED_GROUPS)]}, pluck="name"))
	codes |= set(frappe.get_all(TAPE_SPEC, pluck="name"))
	codes |= {code for code in frappe.get_all(SHEET_SPEC, pluck="item") if code}
	return sorted(codes)


def _numeric_fields(meta) -> set[str]:
	"""``ill_lp_*`` fields stored as NOT NULL numbers, which take 0 instead of ``None``.

	``doc.save`` does this for a normal save; ``frappe.db.set_value`` writes ``None`` as
	NULL, which those columns refuse.
	"""
	numeric = set()
	for field in LP_FIELDS:
		docfield = meta.get_field(field)
		if docfield and docfield.fieldtype in NUMERIC_FIELDTYPES:
			numeric.add(field)
	return numeric


def _log_failures(failed: list[str], counts: dict, traceback: str | None) -> None:
	"""One Error Log for the whole run, naming up to ``MAX_LOGGED_PARENTS`` documents."""
	shown = failed[:MAX_LOGGED_PARENTS]
	lines = [f"Counts: {counts}", "", f"Documents with failed rows ({len(failed)}):", *shown]
	if len(failed) > len(shown):
		lines.append(f"... and {len(failed) - len(shown)} more")
	lines += ["", "First failure:", traceback or ""]
	frappe.log_error(title="Line power backfill: rows failed", message="\n".join(lines))


def backfill() -> dict:
	"""Stamp existing draft and submitted rows in place (``update_modified=False``).

	Returns ``{child doctype: {"stamped": n, "failed": m}}``. Failed rows are left as they
	were and reported in one Error Log at the end.
	"""
	codes = _candidate_items()
	counts = {}
	if not codes:
		return counts
	resolved = resolve_specs(codes)
	failed_parents: dict[str, None] = {}
	first_traceback = None
	for parent, child in CHILD_DOCTYPES.items():
		meta = frappe.get_meta(child)
		if not meta.has_field("ill_lp_watts"):
			counts[child] = "fields missing"
			continue
		numeric = _numeric_fields(meta)
		fields = ["name", "parent", "ill_is_power_supply_line", *ROW_INPUTS, *CONFIGURED_FIELDS]
		fields = [
			field for field in dict.fromkeys(fields) if field in ("name", "parent") or meta.has_field(field)
		]
		rows = frappe.get_all(
			child,
			filters={"parenttype": parent, "item_code": ["in", codes], "docstatus": ["<", 2]},
			fields=fields,
			limit_page_length=0,
		)
		stamped = failed = 0
		for row in rows:
			try:
				values = {
					field: value
					for field, value in values_for(row, resolved).items()
					if meta.has_field(field)
				}
				if not any(value is not None for value in values.values()):
					continue
				values = {
					field: 0 if value is None and field in numeric else value
					for field, value in values.items()
				}
				frappe.db.set_value(child, row.get("name"), values, update_modified=False)
				stamped += 1
			except Exception:
				failed += 1
				failed_parents[f"{parent} {row.get('parent')}"] = None
				first_traceback = first_traceback or frappe.get_traceback()
		counts[child] = {"stamped": stamped, "failed": failed}
	if failed_parents:
		_log_failures(list(failed_parents), counts, first_traceback)
	return counts
