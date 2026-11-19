"""Spec and load under catalog LED Tape / Neon / Sheet rows (api/line_power.py).

Numbers come from live specs and rows (2026-11-18): Cowlitz neon at 2.74 W/ft, Dim to
Warm COB at 6.67 W/ft sold by the 16.4 ft reel, and Sales Order rows in ``Feet`` or
reels at a conversion factor of 1.0.
"""

import ast
import io
import itertools
import json
import pathlib
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock

from test_schedule_sync import Row
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api import line_power_math as lpm

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOK = ROOT + ".api.line_power.stamp_line_power"

COWLITZ = {
	"family": "Tape",
	"spec_doctype": "ilL-Spec-LED Tape",
	"spec_name": "NON-COW-SW-67-27K-150",
	"input_voltage": "24VDC",
	"watts_per_foot": 2.74,
	"max_run_ft": 16.4,
	"max_run_double_ft": 32.8,
}
SHEET = {
	"family": "Sheet",
	"spec_doctype": "ilL-Spec-LED-Sheet",
	"spec_name": "LED-SNF-SW-O-27K-10W-3M-WH",
	"input_voltage": "24VDC",
	"sheet_area_sqft": 2.0,
	"sheet_width_ft": 1.0,
	"sheet_height_ft": 2.0,
	"watts_per_sqft": 5.0,
	"total_sheet_watts": 10.0,
	"max_sqft_per_100w": 16.0,
}


def tape_row(qty, uom="Inch", cf=1.0, stock_uom="Inch"):
	return {"qty": qty, "uom": uom, "conversion_factor": cf, "stock_uom": stock_uom}


class UomParsing(unittest.TestCase):
	def test_length_uoms(self):
		cases = {
			"Inch": 1 / 12,
			"Foot": 1,
			"Feet": 1,
			"foot": 1,
			"Meter": 3.280839895,
			"16.4ft Reel": 16.4,
			"50ft Reel": 50,
			"70ft Reel": 70,
			"100ft Reel": 100,
			"1,000ft": 1000,
			"3.28ft Piece": 3.28,
		}
		for uom, feet in cases.items():
			with self.subTest(uom):
				self.assertAlmostEqual(lpm.uom_length_ft(uom), feet)
		for uom in ("Ea", "Box", "Foot/Minute", "Square Foot", "", None):
			with self.subTest(uom):
				self.assertIsNone(lpm.uom_length_ft(uom))

	def test_sheet_uoms(self):
		self.assertEqual(lpm.sheet_uom_area_sqft("1ft x 2ft Sheet"), 2)
		self.assertEqual(lpm.sheet_uom_area_sqft("1ft x 1ft Sheet"), 1)
		self.assertIsNone(lpm.sheet_uom_area_sqft("Ea"))


class RowLength(unittest.TestCase):
	CASES = (
		# qty, uom, cf, stock_uom, feet, warns
		(864, "Inch", 1, "Inch", 72.0, False),
		(10, "Foot", 11.999999695, "Inch", 10.0, False),
		(10, "Feet", 1.0, "Inch", 10.0, True),
		(1, "16.4ft Reel", 196.8, "Inch", 16.4, False),
		(1, "16.4ft Reel", 1.0, "Inch", 16.4, True),
		(0.5, "16.4ft Reel", 1.0, "Inch", 8.2, True),
		(2, "Meter", 39.37, "Inch", 6.5617, False),
		(24, "Pack", 12, "Inch", 24.0, False),  # Unknown UOM: falls back to factor x stock.
	)

	def test_live_cases(self):
		for qty, uom, cf, stock, feet, warns in self.CASES:
			with self.subTest(qty=qty, uom=uom, cf=cf):
				got, warning = lpm.row_length_ft(qty, uom, cf, stock)
				self.assertAlmostEqual(got, feet, places=3)
				self.assertEqual(bool(warning), warns, warning)

	def test_warning_names_both_factors(self):
		_feet, warning = lpm.row_length_ft(10, "Feet", 1.0, "Inch")
		self.assertIn("should convert at 12 Inch", warning)
		self.assertIn("uses 1", warning)

	def test_count_uoms_have_no_length(self):
		self.assertEqual(lpm.row_length_ft(1, "Ea", 1, "Ea"), (None, None))


class ComputeTape(unittest.TestCase):
	def test_cowlitz_by_the_inch(self):
		values = lpm.compute_row(tape_row(864), COWLITZ)
		self.assertEqual(values["ill_lp_length_ft"], 72.0)
		self.assertEqual(values["ill_lp_watts"], 197.3)
		self.assertEqual(values["ill_lp_family"], "Tape")
		self.assertEqual(values["ill_lp_input_voltage"], "24VDC")
		self.assertEqual(values["ill_lp_watts_per_ft"], 2.74)
		self.assertEqual(values["ill_lp_max_run_ft"], 16.4)
		self.assertEqual(values["ill_lp_spec"], "NON-COW-SW-67-27K-150")
		self.assertEqual(
			values["ill_lp_summary"],
			"24VDC · 2.74 W/ft · Max run 16.4 ft (32.8 ft double feed) · Length 72.00 ft · Load 197.3 W",
		)
		self.assertIsNone(values["ill_lp_note"])
		self.assertEqual(set(values), set(lpm.LP_FIELDS))

	def test_cob_by_the_reel(self):
		spec = {**COWLITZ, "watts_per_foot": 6.67, "max_run_ft": 12, "max_run_double_ft": 24}
		values = lpm.compute_row(tape_row(1, "16.4ft Reel", 196.8), spec)
		self.assertEqual(values["ill_lp_watts"], 109.4)

	def test_feet_at_factor_one_uses_feet_and_notes_it(self):
		spec = {**COWLITZ, "watts_per_foot": 3.05}
		values = lpm.compute_row(tape_row(10, "Feet", 1.0), spec)
		self.assertEqual(values["ill_lp_watts"], 30.5)
		self.assertIn("should convert at 12", values["ill_lp_note"])

	def test_same_single_and_double_run_shows_once(self):
		values = lpm.compute_row(tape_row(12), {**COWLITZ, "max_run_double_ft": 16.4})
		self.assertIn("Max run 16.4 ft ·", values["ill_lp_summary"])
		self.assertNotIn("double feed", values["ill_lp_summary"])

	def test_spec_without_watts_per_foot(self):
		values = lpm.compute_row(tape_row(120), {**COWLITZ, "watts_per_foot": None})
		self.assertIsNone(values["ill_lp_watts"])
		self.assertEqual(values["ill_lp_length_ft"], 10.0)
		self.assertEqual(values["ill_lp_note"], "Spec has no W/ft")

	def test_unconvertible_uom(self):
		values = lpm.compute_row(tape_row(1, "Ea", 1, "Ea"), COWLITZ)
		self.assertIsNone(values["ill_lp_watts"])
		self.assertIn("Can't convert Ea to feet", values["ill_lp_note"])
		self.assertTrue(values["ill_lp_summary"].startswith("24VDC · 2.74 W/ft"))


class ComputeSheet(unittest.TestCase):
	def test_sheets_by_the_each(self):
		values = lpm.compute_row({"qty": 9, "uom": "Ea", "conversion_factor": 1, "stock_uom": "Ea"}, SHEET)
		self.assertEqual(values["ill_lp_area_sqft"], 18.0)
		self.assertEqual(values["ill_lp_watts"], 90.0)
		self.assertEqual(values["ill_lp_watts_per_sheet"], 10.0)
		self.assertEqual(values["ill_lp_family"], "Sheet")
		self.assertEqual(
			values["ill_lp_summary"],
			"24VDC · 5 W/sq ft · 10 W/sheet · Max 16 sq ft per 100 W · Area 18.00 sq ft · Load 90.0 W",
		)

	def test_sheet_size_uom(self):
		row = {"qty": 2, "uom": "1ft x 1ft Sheet", "conversion_factor": 0.5, "stock_uom": "Ea"}
		values = lpm.compute_row(row, SHEET)
		self.assertEqual(values["ill_lp_area_sqft"], 2.0)
		self.assertEqual(values["ill_lp_watts"], 10.0)

	def test_watts_per_sheet_without_watts_per_sqft(self):
		spec = {**SHEET, "watts_per_sqft": None, "total_sheet_watts": 20.0}
		values = lpm.compute_row({"qty": 3, "uom": "Ea", "conversion_factor": 1, "stock_uom": "Ea"}, spec)
		self.assertEqual(values["ill_lp_watts"], 60.0)

	def test_area_from_width_and_height(self):
		spec = {**SHEET, "sheet_area_sqft": None}
		values = lpm.compute_row({"qty": 1, "uom": "Ea", "conversion_factor": 1, "stock_uom": "Ea"}, spec)
		self.assertEqual(values["ill_lp_watts"], 10.0)

	def test_sheet_size_missing(self):
		spec = {**SHEET, "sheet_area_sqft": None, "sheet_width_ft": None}
		values = lpm.compute_row({"qty": 1, "uom": "Ea", "conversion_factor": 1, "stock_uom": "Ea"}, spec)
		self.assertIsNone(values["ill_lp_watts"])
		self.assertEqual(values["ill_lp_note"], "Sheet size missing on spec")


class NoSpecAndTotals(unittest.TestCase):
	def test_tape_item_without_spec_gets_only_a_note(self):
		values = lpm.compute_row(tape_row(12), None, tape_like=True)
		self.assertEqual(values["ill_lp_note"], lpm.NO_SPEC_NOTE)
		self.assertEqual([k for k, v in values.items() if v is not None], ["ill_lp_note"])

	def test_other_items_get_nothing(self):
		self.assertTrue(all(v is None for v in lpm.compute_row(tape_row(1), None).values()))

	def test_total_skips_alternatives(self):
		rows = [{"ill_lp_watts": 197.3}, {"ill_lp_watts": 90}, {"ill_lp_watts": 50, "is_alternative": 1}, {}]
		self.assertEqual(lpm.document_total_watts(rows), 287.3)


# ── Adapter (frappe boundary doubled) ─────────────────────────────────

ITEMS = [
	Record(name="NON-COW-SW-67-27K-150", variant_of="NON-COW-SW", item_group="LED Neon", stock_uom="Inch"),
	Record(name="COB-VARIANT", variant_of="COB-TEMPLATE", item_group="COB Tape", stock_uom="Inch"),
	Record(name="COB-NOSPEC", variant_of=None, item_group="COB Tape", stock_uom="Inch"),
	Record(name="COB-TEMPLATE", variant_of=None, item_group="COB Tape", stock_uom="Inch"),
	Record(name="LED-SNF-SW-O-27K-10W-3M-WH", variant_of=None, item_group="LED Sheet", stock_uom="Ea"),
	Record(name="DRIVER", variant_of=None, item_group="Power Supplies", stock_uom="Ea"),
]
TAPE_SPECS = [
	Record(
		name="NON-COW-SW-67-27K-150",
		input_voltage="24VDC",
		watts_per_foot=2.74,
		voltage_drop_max_run_length_ft=16.4,
		max_run_single_feed_ft=16.4,
		max_run_double_feed_ft=32.8,
	),
	Record(
		name="COB-TEMPLATE",
		input_voltage="24VDC",
		watts_per_foot=4.27,
		voltage_drop_max_run_length_ft=None,
		max_run_single_feed_ft=16.4,
	),
]
SHEET_SPECS = [
	Record(
		name="LED-SNF-SW-O-27K-10W-3M-WH",
		item="LED-SNF-SW-O-27K-10W-3M-WH",
		**{k: v for k, v in SHEET.items() if k not in ("family", "spec_doctype", "spec_name")},
	),
]


def catalog(frappe):
	def get_all(doctype, filters=None, **kwargs):
		source = {"Item": ITEMS, "ilL-Spec-LED Tape": TAPE_SPECS, "ilL-Spec-LED-Sheet": SHEET_SPECS}[doctype]
		rows = list(source)
		for field, value in (filters or {}).items():
			if isinstance(value, list) and value and value[0] == "in":
				rows = [row for row in rows if row.get(field) in set(value[1])]
		return rows

	frappe.get_all = MagicMock(side_effect=get_all)
	frappe.log_error = MagicMock()
	frappe.get_traceback = MagicMock(return_value="traceback")
	return frappe.get_all


def service():
	return load_service(ROOT + ".api.line_power")


def row(item_code, qty=12, uom="Inch", cf=1, stock_uom="Inch", **values):
	return Row(
		{
			"item_code": item_code,
			"qty": qty,
			"uom": uom,
			"conversion_factor": cf,
			"stock_uom": stock_uom,
			**values,
		}
	)


class ResolveSpecs(unittest.TestCase):
	def test_own_spec_sheet_and_none(self):
		with service() as (module, frappe):
			get_all = catalog(frappe)
			resolved = module.resolve_specs([i.name for i in ITEMS] * 10)
			self.assertEqual(get_all.call_count, 3)  # Items, tape specs, sheet specs: no N+1.
		cow = resolved["NON-COW-SW-67-27K-150"]["spec"]
		self.assertEqual(
			(cow["family"], cow["spec_name"], cow["max_run_ft"]), ("Tape", "NON-COW-SW-67-27K-150", 16.4)
		)
		self.assertEqual(resolved["LED-SNF-SW-O-27K-10W-3M-WH"]["spec"]["family"], "Sheet")
		self.assertIsNone(resolved["COB-NOSPEC"]["spec"])
		self.assertTrue(resolved["COB-NOSPEC"]["tape_like"])
		self.assertFalse(resolved["DRIVER"]["tape_like"])

	def test_a_variant_never_borrows_its_templates_spec(self):
		# LED-HD-SW covers 0.8 to 14.4 W/ft across its variants; its own spec has none.
		with service() as (module, frappe):
			catalog(frappe)
			resolved = module.resolve_specs(["COB-VARIANT"])
		self.assertIsNone(resolved["COB-VARIANT"]["spec"])
		self.assertTrue(resolved["COB-VARIANT"]["tape_like"])

	def test_single_feed_max_when_the_voltage_drop_limit_is_unset(self):
		with service() as (module, frappe):
			catalog(frappe)
			resolved = module.resolve_specs(["COB-TEMPLATE"])
		self.assertEqual(resolved["COB-TEMPLATE"]["spec"]["max_run_ft"], 16.4)

	def test_nothing_to_resolve_makes_no_queries(self):
		with service() as (module, frappe):
			get_all = catalog(frappe)
			self.assertEqual(module.resolve_specs([None, ""]), {})
			get_all.assert_not_called()


class StampRows(unittest.TestCase):
	def stamp(self, rows):
		with service() as (module, frappe):
			catalog(frappe)
			module.stamp_rows(rows)
		return rows

	def test_catalog_rows_are_stamped(self):
		rows = self.stamp(
			[row("NON-COW-SW-67-27K-150", 864), row("LED-SNF-SW-O-27K-10W-3M-WH", 9, "Ea", 1, "Ea")]
		)
		self.assertEqual(rows[0]["ill_lp_watts"], 197.3)
		self.assertEqual(rows[1]["ill_lp_watts"], 90.0)

	def test_missing_stock_uom_comes_from_the_item(self):
		rows = self.stamp([row("NON-COW-SW-67-27K-150", 2, "16.4ft Reel", 196.8, stock_uom=None)])
		self.assertEqual(rows[0]["ill_lp_length_ft"], 32.8)

	def test_configured_and_supply_rows_are_left_alone(self):
		rows = self.stamp(
			[
				row("NON-COW-SW-67-27K-150", ill_configured_tape_neon="ILL-CTN-1", ill_total_watts=40),
				row("NON-COW-SW-67-27K-150", ill_configured_group="GRP-1"),
				row("NON-COW-SW-67-27K-150", ill_is_power_supply_line=1),
			]
		)
		for each in rows:
			self.assertIsNone(each.get("ill_lp_watts"))
		self.assertEqual(rows[0]["ill_total_watts"], 40)

	def test_stale_values_clear_when_the_item_changes(self):
		rows = self.stamp([row("DRIVER", 1, "Ea", 1, "Ea", ill_lp_watts=197.3, ill_lp_summary="old")])
		self.assertIsNone(rows[0]["ill_lp_watts"])
		self.assertIsNone(rows[0]["ill_lp_summary"])

	def test_tape_without_spec_is_noted(self):
		rows = self.stamp([row("COB-NOSPEC")])
		self.assertEqual(rows[0]["ill_lp_note"], "No LED spec on file")
		self.assertIsNone(rows[0].get("ill_lp_summary"))


class Hook(unittest.TestCase):
	def test_failure_is_logged_and_never_raised(self):
		with service() as (module, frappe):
			catalog(frappe)
			frappe.get_all.side_effect = RuntimeError("db down")
			doc = Record(doctype="Quotation", name="Q-1", docstatus=0, items=[row("NON-COW-SW-67-27K-150")])
			module.stamp_line_power(doc)
			frappe.log_error.assert_called_once()

	def test_cancelled_and_migrating_documents_are_skipped(self):
		with service() as (module, frappe):
			get_all = catalog(frappe)
			module.stamp_line_power(Record(docstatus=2, items=[row("NON-COW-SW-67-27K-150")]))
			frappe.flags["in_migrate"] = True
			module.stamp_line_power(Record(docstatus=0, items=[row("NON-COW-SW-67-27K-150")]))
			get_all.assert_not_called()

	def test_submitted_order_update_is_stamped(self):
		with service() as (module, frappe):
			catalog(frappe)
			doc = Record(
				doctype="Sales Order", name="SO-1", docstatus=1, items=[row("NON-COW-SW-67-27K-150", 864)]
			)
			module.stamp_line_power(doc)
		self.assertEqual(doc["items"][0]["ill_lp_watts"], 197.3)


class Preview(unittest.TestCase):
	def test_returns_values_by_key_and_total(self):
		with service() as (module, frappe):
			catalog(frappe)
			rows = [
				{
					"key": "r1",
					"item_code": "NON-COW-SW-67-27K-150",
					"qty": 864,
					"uom": "Inch",
					"conversion_factor": 1,
					"stock_uom": "Inch",
				},
				{
					"key": "r2",
					"item_code": "LED-SNF-SW-O-27K-10W-3M-WH",
					"qty": 9,
					"uom": "Ea",
					"conversion_factor": 1,
					"stock_uom": "Ea",
				},
				{
					"key": "r3",
					"item_code": "LED-SNF-SW-O-27K-10W-3M-WH",
					"qty": 9,
					"uom": "Ea",
					"conversion_factor": 1,
					"stock_uom": "Ea",
					"is_alternative": 1,
				},
			]
			result = module.preview(json.dumps(rows))
		self.assertEqual(result["rows"]["r1"]["ill_lp_watts"], 197.3)
		self.assertEqual(result["total_watts"], 287.3)

	def test_requires_read_on_a_transaction(self):
		with service() as (module, frappe):
			catalog(frappe)
			frappe.has_permission = MagicMock(return_value=False)
			with self.assertRaises(PermissionError):
				module.preview([])

	def test_caps_the_row_count(self):
		with service() as (module, frappe):
			catalog(frappe)
			with self.assertRaises(ValueError):
				module.preview([{"key": str(i), "item_code": "DRIVER"} for i in range(501)])


class MissingSpecs(unittest.TestCase):
	def test_lists_items_with_no_spec_for_system_managers(self):
		with service() as (module, frappe):
			catalog(frappe)
			frappe.get_roles = MagicMock(return_value=["System Manager"])
			missing = module.missing_specs()
		self.assertEqual([item.name for item in missing], ["COB-VARIANT", "COB-NOSPEC"])

	def test_others_are_refused(self):
		with service() as (module, frappe):
			catalog(frappe)
			with self.assertRaises(PermissionError):
				module.missing_specs()


def row_fields():
	"""The custom fields the patch adds, as Frappe's meta sees them."""
	custom_field = type("module", (), {"create_custom_fields": MagicMock()})
	extras = {"frappe.custom.doctype.custom_field.custom_field": custom_field}
	with load_service("illumenate_lighting.patches.add_line_power_fields", extras) as (patch, _frappe):
		return patch._row_fields("ill_schedule_line_id")


class Meta:
	def __init__(self, fields):
		standard = [{"fieldname": name, "fieldtype": "Data"} for name in ("item_code", "uom", "stock_uom")]
		standard += [{"fieldname": name, "fieldtype": "Float"} for name in ("qty", "conversion_factor")]
		standard += [
			{"fieldname": name, "fieldtype": "Check"}
			for name in ("is_alternative", "ill_is_power_supply_line")
		]
		self.fields = {field["fieldname"]: Record(field) for field in [*standard, *fields]}

	def has_field(self, fieldname):
		return fieldname in self.fields

	def get_field(self, fieldname):
		return self.fields.get(fieldname)


def backfill_catalog(frappe, rows):
	"""``rows``: ``{child doctype: [row]}``; ``frappe.db.set_value`` records each write."""
	base = catalog(frappe).side_effect

	def get_all(doctype, filters=None, pluck=None, **kwargs):
		if doctype in ("Quotation Item", "Sales Order Item"):
			return [Record(each) for each in rows.get(doctype, [])]
		found = base(doctype, filters, **kwargs)
		return [each.get(pluck) for each in found] if pluck else found

	frappe.get_all = MagicMock(side_effect=get_all)
	frappe.get_meta = MagicMock(return_value=Meta(row_fields()))
	frappe.db.set_value = MagicMock()
	return frappe.db.set_value


def child(name, parent, item_code, qty, uom="Inch", stock_uom="Inch", **values):
	return {
		"name": name,
		"parent": parent,
		"item_code": item_code,
		"qty": qty,
		"uom": uom,
		"conversion_factor": 1,
		"stock_uom": stock_uom,
		**values,
	}


class Backfill(unittest.TestCase):
	def test_tape_sheet_and_no_spec_rows_are_written_without_nulls(self):
		# 2026-11-18: every write failed on NOT NULL ill_lp_watts_per_ft / ill_lp_watts_per_sqft.
		rows = {
			"Quotation Item": [
				child("qi-tape", "Q-1", "NON-COW-SW-67-27K-150", 864),
				child("qi-sheet", "Q-1", "LED-SNF-SW-O-27K-10W-3M-WH", 9, "Ea", "Ea"),
				child("qi-nospec", "Q-2", "COB-NOSPEC", 12),
				child("qi-supply", "Q-2", "NON-COW-SW-67-27K-150", 12, ill_is_power_supply_line=1),
			],
		}
		numeric = {field["fieldname"] for field in row_fields() if field["fieldtype"] == "Float"}
		with service() as (module, frappe):
			set_value = backfill_catalog(frappe, rows)
			counts = module.backfill()
			frappe.log_error.assert_not_called()
		self.assertEqual(
			counts,
			{"Quotation Item": {"stamped": 3, "failed": 0}, "Sales Order Item": {"stamped": 0, "failed": 0}},
		)
		written = {call.args[1]: call.args[2] for call in set_value.call_args_list}
		self.assertEqual(set(written), {"qi-tape", "qi-sheet", "qi-nospec"})
		self.assertTrue(all(call.kwargs["update_modified"] is False for call in set_value.call_args_list))
		for name, values in written.items():
			for field in numeric:
				self.assertIsNotNone(values[field], f"{name} {field}")
		self.assertEqual(written["qi-tape"]["ill_lp_watts"], 197.3)
		self.assertEqual(written["qi-tape"]["ill_lp_watts_per_sqft"], 0)
		self.assertEqual(written["qi-sheet"]["ill_lp_watts"], 90.0)
		self.assertEqual(written["qi-sheet"]["ill_lp_watts_per_ft"], 0)
		self.assertEqual(written["qi-nospec"]["ill_lp_watts"], 0)
		self.assertEqual(written["qi-nospec"]["ill_lp_note"], lpm.NO_SPEC_NOTE)
		self.assertIsNone(written["qi-nospec"]["ill_lp_summary"])  # Text fields still clear.

	def test_failures_are_counted_and_logged_once(self):
		rows = {
			"Quotation Item": [
				child("qi-tape", "Q-1", "NON-COW-SW-67-27K-150", 864),
				child("qi-sheet-1", "Q-1", "LED-SNF-SW-O-27K-10W-3M-WH", 9, "Ea", "Ea"),
				child("qi-sheet-2", "Q-2", "LED-SNF-SW-O-27K-10W-3M-WH", 9, "Ea", "Ea"),
			],
			"Sales Order Item": [child("soi-sheet", "SO-1", "LED-SNF-SW-O-27K-10W-3M-WH", 9, "Ea", "Ea")],
		}

		def fail_sheets(doctype, name, values, **kwargs):
			if "sheet" in name:
				raise RuntimeError("(1048, \"Column 'ill_lp_watts_per_ft' cannot be null\")")

		with service() as (module, frappe):
			backfill_catalog(frappe, rows).side_effect = fail_sheets
			counts = module.backfill()
			frappe.log_error.assert_called_once()
			message = frappe.log_error.call_args.kwargs["message"]
		self.assertEqual(
			counts,
			{"Quotation Item": {"stamped": 1, "failed": 2}, "Sales Order Item": {"stamped": 0, "failed": 1}},
		)
		self.assertIn(
			"Documents with failed rows (3):\nQuotation Q-1\nQuotation Q-2\nSales Order SO-1", message
		)

	def test_summary_names_at_most_fifty_documents(self):
		rows = {
			"Quotation Item": [child(f"qi-{i}", f"Q-{i}", "NON-COW-SW-67-27K-150", 12) for i in range(60)]
		}
		with service() as (module, frappe):
			backfill_catalog(frappe, rows).side_effect = RuntimeError("db down")
			counts = module.backfill()
			frappe.log_error.assert_called_once()
			message = frappe.log_error.call_args.kwargs["message"]
		self.assertEqual(counts["Quotation Item"], {"stamped": 0, "failed": 60})
		self.assertIn("Q-49\n", message)
		self.assertNotIn("Q-50\n", message)
		self.assertIn("... and 10 more", message)


class BackfillPatch(unittest.TestCase):
	def test_prints_counts_and_failures(self):
		counts = {
			"Quotation Item": {"stamped": 0, "failed": 584},
			"Sales Order Item": {"stamped": 1, "failed": 0},
		}
		line_power = types.SimpleNamespace(backfill=MagicMock(return_value=counts))
		api = types.SimpleNamespace(line_power=line_power)
		extras = {"illumenate_lighting.illumenate_lighting.api": api}
		with load_service("illumenate_lighting.patches.backfill_line_power", extras) as (patch, frappe):
			frappe.log_error = MagicMock()
			with redirect_stdout(io.StringIO()) as out:
				patch.execute()
			frappe.log_error.assert_not_called()
		self.assertIn("'failed': 584", out.getvalue())
		self.assertIn("584 rows failed", out.getvalue())


# ── Wiring ────────────────────────────────────────────────────────────


def doc_events():
	tree = ast.parse((REPO / "illumenate_lighting" / "hooks.py").read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "doc_events" for t in node.targets):
			return ast.literal_eval(node.value)
	raise AssertionError("doc_events not found")


def as_list(value):
	return value if isinstance(value, list) else [value]


class Wiring(unittest.TestCase):
	def test_stamp_runs_after_schedule_sync(self):
		events = doc_events()
		sync = ROOT + ".api.schedule_sync.on_transaction_validate"
		self.assertEqual(as_list(events["Quotation"]["validate"])[-1], HOOK)
		validate = as_list(events["Sales Order"]["validate"])
		self.assertEqual(validate[-1], HOOK)
		self.assertGreater(validate.index(HOOK), validate.index(sync))
		self.assertIn(HOOK, as_list(events["Sales Order"]["before_update_after_submit"]))
		self.assertIn(
			ROOT + ".portal.order_review.validate_order",
			as_list(events["Sales Order"]["before_update_after_submit"]),
		)

	def test_desk_script_is_registered_for_both_forms(self):
		source = (REPO / "illumenate_lighting" / "hooks.py").read_text(encoding="utf-8")
		tree = ast.parse(source)
		for node in tree.body:
			if isinstance(node, ast.Assign) and any(
				getattr(t, "id", None) == "doctype_js" for t in node.targets
			):
				doctype_js = ast.literal_eval(node.value)
				break
		for doctype in ("Quotation", "Sales Order"):
			self.assertIn("public/js/line_power.js", as_list(doctype_js[doctype]))

	def test_lineage_and_sync_ignore_the_new_fields(self):
		for path in ("portal/commercial_lineage.py", "api/schedule_sync.py", "api/build_links.py"):
			source = (REPO / "illumenate_lighting" / "illumenate_lighting" / path).read_text(encoding="utf-8")
			self.assertNotIn("ill_lp_", source, path)

	def test_patches_run_on_migrate_and_fresh_install(self):
		patches = (REPO / "illumenate_lighting" / "patches.txt").read_text().split("[post_model_sync]", 1)[1]
		lines = patches.splitlines()
		self.assertLess(
			lines.index("illumenate_lighting.patches.add_line_power_fields"),
			lines.index("illumenate_lighting.patches.backfill_line_power"),
		)
		# Re-run once rows can be written (the first run hit NOT NULL on every row).
		self.assertGreater(
			lines.index("illumenate_lighting.patches.backfill_line_power #2026-11-19 rerun after None fix"),
			lines.index("illumenate_lighting.patches.backfill_line_power"),
		)
		install = (REPO / "illumenate_lighting" / "illumenate_lighting" / "install.py").read_text()
		self.assertIn("illumenate_lighting.patches.add_line_power_fields import", install)


class FieldsPatch(unittest.TestCase):
	def test_fields_on_both_rows_and_panels_on_both_parents(self):
		recorder = MagicMock()
		custom_field = type("module", (), {"create_custom_fields": recorder})
		extras = {"frappe.custom.doctype.custom_field.custom_field": custom_field}
		with load_service("illumenate_lighting.patches.add_line_power_fields", extras) as (patch, frappe):
			frappe.clear_cache = MagicMock()
			patch.execute()
		call = recorder.call_args
		fields = call.args[0]
		self.assertEqual(set(fields), {"Quotation Item", "Sales Order Item", "Quotation", "Sales Order"})
		for child in ("Quotation Item", "Sales Order Item"):
			rows = fields[child]
			names = [f["fieldname"] for f in rows]
			self.assertEqual(rows[0]["insert_after"], "ill_schedule_line_id")
			for name in lpm.LP_FIELDS:
				self.assertIn(name, names)
			for field in rows:
				self.assertTrue(field["print_hide"])
				if field["fieldtype"] not in ("Section Break", "Column Break"):
					self.assertTrue(field["read_only"], field["fieldname"])
					self.assertTrue(field["allow_on_submit"], field["fieldname"])
			# Each field follows the one before it.
			for before, after in itertools.pairwise(rows):
				self.assertEqual(after["insert_after"], before["fieldname"])
		for parent in ("Quotation", "Sales Order"):
			self.assertEqual(fields[parent][0]["fieldtype"], "HTML")
			self.assertEqual(fields[parent][0]["insert_after"], "items")
		self.assertTrue(call.kwargs["update"])


if __name__ == "__main__":
	unittest.main()
