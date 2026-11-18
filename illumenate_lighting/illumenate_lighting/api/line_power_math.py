# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Spec and load for a catalog LED Tape / Neon / Sheet row on a Quotation or Sales Order.

Pure functions, no ``frappe`` import: :mod:`line_power` resolves specs and stamps rows.

A row's length comes from the physical meaning of its UOM ("Feet" is 1 ft, "16.4ft Reel"
is 16.4 ft), not from the row's ``conversion_factor``: older rows carry ``Feet`` and reel
UOMs at a factor of 1.0, which would understate the load 12x or 197x. A factor that
disagrees with the UOM by more than 2 % is reported in ``ill_lp_note``.
"""

from __future__ import annotations

import re

# Every row field this module writes. All are returned by compute_row, None when unset,
# so a row that stops being tape clears its old values.
LP_FIELDS = (
	"ill_lp_spec_doctype",
	"ill_lp_spec",
	"ill_lp_family",
	"ill_lp_input_voltage",
	"ill_lp_watts_per_ft",
	"ill_lp_max_run_ft",
	"ill_lp_max_run_double_ft",
	"ill_lp_watts_per_sqft",
	"ill_lp_watts_per_sheet",
	"ill_lp_max_sqft_per_100w",
	"ill_lp_length_ft",
	"ill_lp_area_sqft",
	"ill_lp_watts",
	"ill_lp_summary",
	"ill_lp_note",
)

FAMILY_TAPE = "Tape"
FAMILY_SHEET = "Sheet"
NO_SPEC_NOTE = "No LED spec on file"

FT_PER_UOM = {
	"inch": 1 / 12,
	"inches": 1 / 12,
	"in": 1 / 12,
	"foot": 1.0,
	"feet": 1.0,
	"ft": 1.0,
	"yard": 3.0,
	"meter": 3.280839895,
	"metre": 3.280839895,
	"centimeter": 0.03280839895,
	"millimeter": 0.003280839895,
}
COUNT_UOMS = frozenset(("ea", "each", "nos", "unit", "units", "pcs"))
# "16.4ft Reel", "50ft Reel", "3.28ft Piece", "1,000ft"
_LENGTH_UOM = re.compile(r"^\s*(\d[\d,]*(?:\.\d+)?)\s*(?:ft|feet|foot)\b", re.IGNORECASE)
# "1ft x 2ft Sheet"
_SHEET_UOM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*ft\s*x\s*(\d+(?:\.\d+)?)\s*ft\b", re.IGNORECASE)
# Within this the row's factor agrees with its UOM (196.8 vs 196.85, 11.999999695 vs 12).
FACTOR_TOLERANCE = 0.02


def _num(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _fmt(value) -> str:
	"""A spec value as entered: 3.05, 16.4, 24 (no trailing zeros)."""
	return f"{round(_num(value), 4):g}"


def uom_length_ft(uom) -> float | None:
	"""Feet in one ``uom``, or ``None`` when the UOM is not a length."""
	if not uom:
		return None
	name = str(uom).strip()
	known = FT_PER_UOM.get(name.lower())
	if known is not None:
		return known
	match = _LENGTH_UOM.match(name)
	if match:
		feet = _num(match.group(1).replace(",", ""))
		return feet or None
	return None


def sheet_uom_area_sqft(uom) -> float | None:
	"""Square feet in one ``uom`` such as "1ft x 2ft Sheet", else ``None``."""
	match = _SHEET_UOM.match(str(uom or ""))
	if not match:
		return None
	return _num(match.group(1)) * _num(match.group(2)) or None


def row_length_ft(qty, uom, conversion_factor, stock_uom) -> tuple[float | None, str | None]:
	"""``(feet, warning)`` for a row; feet is ``None`` when its UOM is not a length."""
	qty = _num(qty)
	per_uom = uom_length_ft(uom)
	per_stock = uom_length_ft(stock_uom)
	if per_uom is not None:
		feet = qty * per_uom
	elif per_stock is not None:
		feet = qty * _num(conversion_factor or 1) * per_stock
	else:
		return None, None
	warning = None
	if per_uom is not None and per_stock is not None and uom != stock_uom:
		expected = per_uom / per_stock
		factor = _num(conversion_factor)
		if abs(factor - expected) / expected > FACTOR_TOLERANCE:
			warning = (
				f"UOM {uom} should convert at {_fmt(expected)} {stock_uom}; "
				f"this row uses {_fmt(factor)}. Load uses {_fmt(expected)}."
			)
	return feet, warning


def _sheet_area_each(spec) -> float:
	area = _num(spec.get("sheet_area_sqft"))
	if not area:
		area = _num(spec.get("sheet_width_ft")) * _num(spec.get("sheet_height_ft"))
	return area


def row_area_sqft(qty, uom, conversion_factor, stock_uom, spec) -> tuple[float | None, str | None]:
	"""``(sq ft, warning)`` for an LED Sheet row; the stock unit is one sheet."""
	qty = _num(qty)
	per_uom = sheet_uom_area_sqft(uom)
	if per_uom is not None:
		return qty * per_uom, None
	each = _sheet_area_each(spec)
	if not each:
		return None, "Sheet size missing on spec"
	return qty * _num(conversion_factor or 1) * each, None


def _empty() -> dict:
	return dict.fromkeys(LP_FIELDS)


def _identity(values, spec, family) -> None:
	values.update(
		{
			"ill_lp_spec_doctype": spec.get("spec_doctype"),
			"ill_lp_spec": spec.get("spec_name"),
			"ill_lp_family": family,
			"ill_lp_input_voltage": spec.get("input_voltage") or None,
		}
	)


def _tape(values, row, spec, notes) -> list[str]:
	_identity(values, spec, FAMILY_TAPE)
	per_ft = _num(spec.get("watts_per_foot"))
	max_run = _num(spec.get("max_run_ft"))
	double = _num(spec.get("max_run_double_ft"))
	values["ill_lp_watts_per_ft"] = per_ft or None
	values["ill_lp_max_run_ft"] = max_run or None
	values["ill_lp_max_run_double_ft"] = double or None

	parts = [spec.get("input_voltage")] if spec.get("input_voltage") else []
	if per_ft:
		parts.append(f"{_fmt(per_ft)} W/ft")
	if max_run:
		run = f"Max run {_fmt(max_run)} ft"
		if double and double != max_run:
			run += f" ({_fmt(double)} ft double feed)"
		parts.append(run)

	feet, warning = row_length_ft(
		row.get("qty"), row.get("uom"), row.get("conversion_factor"), row.get("stock_uom")
	)
	if warning:
		notes.append(warning)
	if feet is None:
		notes.append(f"Can't convert {row.get('uom') or 'this UOM'} to feet")
		return parts
	values["ill_lp_length_ft"] = round(feet, 2)
	parts.append(f"Length {feet:.2f} ft")
	if not per_ft:
		notes.append("Spec has no W/ft")
		return parts
	watts = round(feet * per_ft, 1)
	values["ill_lp_watts"] = watts
	parts.append(f"Load {watts:.1f} W")
	return parts


def _sheet(values, row, spec, notes) -> list[str]:
	_identity(values, spec, FAMILY_SHEET)
	per_sqft = _num(spec.get("watts_per_sqft"))
	each = _sheet_area_each(spec)
	per_sheet = _num(spec.get("total_sheet_watts")) or (per_sqft * each)
	per_100w = _num(spec.get("max_sqft_per_100w"))
	panels = _num(spec.get("max_panels_per_feed"))
	values["ill_lp_watts_per_sqft"] = per_sqft or None
	values["ill_lp_watts_per_sheet"] = round(per_sheet, 2) or None
	values["ill_lp_max_sqft_per_100w"] = per_100w or None

	parts = [spec.get("input_voltage")] if spec.get("input_voltage") else []
	if per_sqft:
		parts.append(f"{_fmt(per_sqft)} W/sq ft")
	if per_sheet:
		parts.append(f"{_fmt(per_sheet)} W/sheet")
	if per_100w:
		parts.append(f"Max {_fmt(per_100w)} sq ft per 100 W")
	if panels:
		parts.append(f"Max {_fmt(panels)} panels per feed")

	sqft, warning = row_area_sqft(
		row.get("qty"), row.get("uom"), row.get("conversion_factor"), row.get("stock_uom"), spec
	)
	if warning:
		notes.append(warning)
	if sqft is None:
		return parts
	values["ill_lp_area_sqft"] = round(sqft, 2)
	parts.append(f"Area {sqft:.2f} sq ft")
	if per_sqft:
		watts = sqft * per_sqft
	elif per_sheet and each:
		watts = sqft / each * per_sheet
	else:
		notes.append("Spec has no W/sq ft")
		return parts
	watts = round(watts, 1)
	values["ill_lp_watts"] = watts
	parts.append(f"Load {watts:.1f} W")
	return parts


def compute_row(row, spec, tape_like: bool = False) -> dict:
	"""Every ``ill_lp_*`` value for one row.

	``row`` holds ``qty``, ``uom``, ``conversion_factor`` and ``stock_uom``. ``spec`` is a
	resolved spec (see ``line_power.resolve_specs``) or ``None``; ``tape_like`` says the
	Item belongs to an LED family, so a missing spec is worth a note.
	"""
	values = _empty()
	if not spec:
		if tape_like:
			values["ill_lp_note"] = NO_SPEC_NOTE
		return values
	notes: list[str] = []
	if spec.get("family") == FAMILY_SHEET:
		parts = _sheet(values, row, spec, notes)
	else:
		parts = _tape(values, row, spec, notes)
	values["ill_lp_summary"] = " · ".join(str(part) for part in parts if part) or None
	values["ill_lp_note"] = "; ".join(notes) or None
	return values


def document_total_watts(rows) -> float:
	"""Connected load of a document's rows; alternatives are not part of the order."""
	total = 0.0
	for row in rows or []:
		if row.get("is_alternative"):
			continue
		total += _num(row.get("ill_lp_watts"))
	return round(total, 1)
