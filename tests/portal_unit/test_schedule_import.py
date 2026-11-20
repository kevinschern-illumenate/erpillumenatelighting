"""Plan 3.4: importing schedule lines from a CSV/XLSX sheet (dry run, then an all-or-nothing commit)."""

import base64
import csv
import io
import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Line(Record):
	__setattr__ = dict.__setitem__


class Schedule(Record):
	__setattr__ = dict.__setitem__

	def append(self, field, values):
		row = Line(values)
		self.setdefault(field, []).append(row)
		return row


class NotAPartNumber(ValueError):
	pass


def positive_int(value, default=1, minimum=1):
	try:
		return max(int(value), minimum)
	except (TypeError, ValueError):
		return default


def sheet(rows, delimiter=","):
	output = io.StringIO()
	csv.writer(output, delimiter=delimiter).writerows(rows)
	return base64.b64encode(output.getvalue().encode("utf-8-sig")).decode()


TEMPLATE = ["Type", "Qty", "Location", "Description", "Part Number", "Notes", "Length (in)"]


class ScheduleImport(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.decode_enabled = True
		self.schedule = Schedule(name="S1", status="DRAFT", is_locked=0, modified="rev-1", lines=[])
		self.schedule.save = MagicMock()
		self.contexts = []
		self.decoded = []

		def schedule_context(name, write=False, lock=False):
			self.contexts.append((name, write, lock))
			return self.schedule

		def editable(schedule):
			if schedule.get("is_locked"):
				raise ValueError("This schedule version is locked. Create a new version to make changes.")

		def require_fresh(schedule, expected_modified=None):
			if expected_modified and str(expected_modified) != str(schedule.modified):
				raise ValueError("This schedule changed since you opened it.")

		def decode(part_number):
			self.decoded.append(part_number)
			if not part_number.upper().startswith("ILL-"):
				raise NotAPartNumber(part_number + " is not a fixture part number")
			if part_number.upper().startswith("ILL-SH01"):
				return {
					"status": "partial",
					"template": "FT-SH01",
					"template_name": "Shallow <01>",
					"unmatched": [{"answer": "ZZ", "reason": "no longer offered on this product"}],
				}
			if part_number.upper().startswith("ILL-AMB"):
				return {"status": "ambiguous", "template": None, "candidates": [{"value": "A"}, {"value": "B"}]}
			return {"status": "unknown", "template": None}

		def orderable(code, is_sales_staff=False):
			return None if code in ("CLIP-1", "PS-96") else "This Item is not active"

		items = {
			"CLIP-1": Record(item_name="Mounting clip", item_group="Accessories"),
			"PS-96": Record(item_name="96W driver", item_group="Power Supplies"),
		}
		self.portal_api = types.SimpleNamespace(
			orderable_item_problem=orderable,
			is_power_supply_group=lambda name: (name or "").lower().startswith(("power suppl", "driver")),
			is_extrusion_kit_group=lambda name: (name or "").lower().startswith("extrusion kit"),
		)
		self.items = items
		self.extras = {
			ROOT + ".api.build_artifacts": types.SimpleNamespace(atomic_build=lambda function: function),
			ROOT + ".api.configuration_contract": types.SimpleNamespace(TAPE_NEON_CATEGORIES=("LED Tape",)),
			ROOT + ".api.portal": self.portal_api,
			ROOT + ".portal.site_flags": types.SimpleNamespace(
				schedule_import_enabled=lambda: self.enabled,
				part_number_decode_enabled=lambda: self.decode_enabled,
			),
			ROOT + ".portal.bulk_lines": types.SimpleNamespace(_editable=editable),
			ROOT + ".portal.configuration": types.SimpleNamespace(schedule_context=schedule_context),
			ROOT + ".portal.schedule_lines": types.SimpleNamespace(require_fresh=require_fresh),
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda role: False),
			ROOT + ".portal.part_number": types.SimpleNamespace(decode=decode, NotAPartNumber=NotAPartNumber),
			ROOT + ".utils": types.SimpleNamespace(parse_positive_int=positive_int),
			ROOT + ".system_design.dealer_data": types.SimpleNamespace(apply=lambda line, data: None),
			ROOT + ".portal.files": types.SimpleNamespace(finalize_spec=MagicMock()),
		}

	@contextmanager
	def module(self):
		with load_service(ROOT + ".portal.line_add", self.extras) as (line_add, frappe):
			frappe.db.get_value.side_effect = lambda doctype, name, fields, as_dict=False: self.items.get(name)
			extras = {**self.extras, ROOT + ".portal.line_add": line_add}
			with load_service(ROOT + ".portal.schedule_import", extras) as (module, frappe):
				frappe.db.get_value.side_effect = lambda doctype, name, fields, as_dict=False: self.items.get(name)
				self.frappe = frappe
				yield module

	def rows(self):
		return [
			TEMPLATE,
			["L1", "4", "Lobby", "Cove", "ILL-SH01-S-D-30-O3-F-C-WH-48-J", "Paint first", "48"],
			["L2", "2", "Hall", "Downlight", "", "", ""],
			["", "1", "", "", "", "", ""],
			["", "", "", "", "", "", ""],
			["L4", "two", "Bath", "", "", "", ""],
		]

	def preview(self, rows, mapping=None, filename="lines.csv"):
		with self.module() as module:
			return module.preview_schedule_import("S1", filename, sheet(rows), mapping)

	def commit(self, rows, **kwargs):
		with self.module() as module:
			kwargs.setdefault("expected_modified", "rev-1")
			return module.commit_schedule_import("S1", "lines.csv", sheet(rows), **kwargs)

	def test_the_template_maps_itself_and_the_dry_run_saves_nothing(self):
		result = self.preview(self.rows())
		self.assertEqual(result["columns"], TEMPLATE)
		self.assertEqual(
			result["mapping"],
			{"line_id": 0, "qty": 1, "location": 2, "description": 3, "part_number": 4, "notes": 5, "length_in": 6},
		)
		self.assertEqual(self.contexts, [("S1", True, False)])
		statuses = [(row["row"], row["status"], row["line_id"]) for row in result["rows"]]
		self.assertEqual(
			statuses,
			# Sheet row numbers: the blank row 5 still counts, so L4 is row 6 as the dealer sees it.
			[(2, "needs_configuration", "L1"), (3, "needs_configuration", "L2"), (4, "needs_configuration", ""), (6, "error", "L4")],
		)
		first = result["rows"][0]
		self.assertEqual(first["summary"], "Shallow <01>")
		self.assertIn("Not recognised: ZZ", first["messages"])
		self.assertEqual(result["rows"][3]["messages"], ["Quantity must be a whole number of at least 1"])
		self.assertEqual(result["counts"], {"ok": 0, "needs_configuration": 3, "error": 1})
		self.assertEqual(self.schedule.lines, [])
		self.schedule.save.assert_not_called()

	def test_the_downloaded_template_explains_itself_and_its_examples_are_skipped(self):
		with self.module() as module:
			header, examples = module.TEMPLATE_COLUMNS, module.TEMPLATE_ROWS
			self.assertEqual(len(header), len(module.FIELDS))
			self.assertEqual(module.suggest_mapping(header), {field: i for i, field in enumerate(module.FIELD_NAMES)})
			self.assertTrue(all(row[0].startswith("#") and len(row) == len(header) for row in examples))
			kinds = {row[module.FIELD_NAMES.index("manufacturer_type")] for row in examples}
			self.assertEqual(kinds - {""}, {"ILLUMENATE", "OTHER", "ACCESSORY"})
			with self.assertRaises(ValueError):
				module.preview_schedule_import("S1", "template.csv", sheet([header, *examples]))
		dealer = ["D1", "3", "Lobby", "Wall wash", "", "", "96", "ILLUMENATE"] + [""] * (len(header) - 8)
		result = self.preview([header, *examples, dealer])
		self.assertEqual([(row["line_id"], row["status"]) for row in result["rows"]], [("D1", "needs_configuration")])

	def test_errors_block_the_commit_until_they_are_skipped(self):
		refused = self.commit(self.rows())
		self.assertFalse(refused["success"])
		self.assertEqual(refused["counts"]["error"], 1)
		self.schedule.save.assert_not_called()
		self.assertEqual(self.schedule.lines, [])

		result = self.commit(self.rows(), skip_errors="1")
		self.assertEqual((result["success"], result["count"], result["skipped"]), (True, 3, 1))
		self.assertEqual(self.contexts[-1], ("S1", True, True))
		self.schedule.save.assert_called_once_with(ignore_permissions=True)
		l1, l2, blank = self.schedule.lines
		self.assertEqual(
			(l1.line_id, l1.qty, l1.location, l1.manufacturer_type, l1.product_type, l1.fixture_template),
			("L1", 4, "Lobby", "ILLUMENATE", "Linear Fixture", "FT-SH01"),
		)
		self.assertEqual(l1.configuration_status, "Pending")
		self.assertEqual(l1.notes, "Paint first\nPart number: ILL-SH01-S-D-30-O3-F-C-WH-48-J\nLength: 48 in")
		self.assertEqual((l2.fixture_template, l2.product_type, l2.notes), (None, None, "Description: Downlight"))
		self.assertEqual((blank.line_id, blank.qty, blank.location), (None, 1, None))

	def test_the_commit_is_refused_when_the_schedule_changed(self):
		with self.assertRaises(ValueError):
			self.commit(self.rows()[:3], expected_modified="rev-0")
		self.schedule.save.assert_not_called()

	def test_an_export_reads_back_with_other_and_accessory_lines(self):
		header = [
			"Project", "Schedule", "Line ID", "Manufacturer Type", "Qty", "Location", "Description", "CCT",
			"Requested Length (in)", "Notes", "Manufacturer Name", "Fixture Model", "Finish",
			"Accessory Item Code", "Accessory Item Name", "Part Number", "Unit Price",
		]
		rows = [
			header,
			["P", "S", "A1", "ILLUMENATE", "3", "Lobby", "SH01 30K", "3000K", "47.5", "", "", "", "", "", "", "ILL-SH01-X", "10.00"],
			["P", "S", "B1", "OTHER", "1", "Bath", "Acme", "", "", "keep", "Acme", "D-100", "Black", "", "", "", "5.00"],
			["P", "S", "C1", "ACCESSORY", "6", "", "Mounting clip", "", "", "", "", "", "", "CLIP-1", "Mounting clip", "", "1.00"],
			["P", "S", "C2", "ACCESSORY", "1", "", "", "", "", "", "", "", "", "PS-96", "", "", "1.00"],
			["P", "S", "X1", "ACCESSORY", "1", "", "", "", "", "", "", "", "", "GONE", "", "", "1.00"],
			["P", "S", "Z1", "BOGUS", "1", "", "", "", "", "", "", "", "", "", "", "", ""],
			["P", "S", "Z2", "OTHER", "1", "", "", "", "", "", "", "", "", "", "", "", ""],
			["SCHEDULE TOTAL", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "17.00"],
		]
		preview = self.preview(rows)
		mapping = preview["mapping"]
		self.assertEqual(
			(mapping["line_id"], mapping["manufacturer_type"], mapping["length_in"], mapping["part_number"], mapping["other_finish"]),
			(2, 3, 8, 15, 12),
		)
		self.assertNotIn("Unit Price", [preview["columns"][index] for index in mapping.values()])
		self.assertEqual(
			[(row["line_id"], row["status"]) for row in preview["rows"]],
			[("A1", "needs_configuration"), ("B1", "ok"), ("C1", "ok"), ("C2", "ok"), ("X1", "error"), ("Z1", "error"), ("Z2", "error")],
		)
		messages = {row["line_id"]: row["messages"] for row in preview["rows"]}
		self.assertEqual(messages["X1"], ["This Item is not active"])
		self.assertEqual(messages["Z1"], ["Manufacturer Type must be ILLUMENATE, OTHER or ACCESSORY"])
		self.assertEqual(messages["Z2"], ["Enter the manufacturer name"])

		result = self.commit(rows, skip_errors="true")
		self.assertEqual((result["count"], result["skipped"]), (4, 3))
		a1, b1, c1, c2 = self.schedule.lines
		self.assertEqual((a1.fixture_template, a1.notes), ("FT-SH01", "Part number: ILL-SH01-X\nLength: 47.5 in"))
		self.assertEqual(
			(b1.manufacturer_type, b1.manufacturer_name, b1.fixture_model_number, b1.other_finish, b1.notes),
			("OTHER", "Acme", "D-100", "Black", "keep"),
		)
		self.assertEqual(
			(c1.accessory_item, c1.accessory_item_name, c1.accessory_product_type, c1.configuration_status, c1.qty),
			("CLIP-1", "Mounting clip", "Accessories", "Configured", 6),
		)
		self.assertEqual((c2.accessory_item, c2.get("accessory_product_type"), c2.get("driver_template")), ("PS-96", None, None))

	def test_types_are_inferred_and_the_mapping_can_be_chosen(self):
		rows = [["Mark", "Count", "Maker", "Item"], ["A", "1", "Acme", ""], ["B", "2", "", "CLIP-1"], ["C", "3", "", ""]]
		guessed = self.preview(rows)
		self.assertEqual(guessed["mapping"], {"line_id": 0, "qty": 1})
		chosen = self.preview(rows, json.dumps({"line_id": 0, "qty": "1", "manufacturer_name": 2, "accessory_item": 3, "notes": None}))
		self.assertEqual(chosen["mapping"], {"line_id": 0, "qty": 1, "manufacturer_name": 2, "accessory_item": 3})
		self.assertEqual([row["manufacturer_type"] for row in chosen["rows"]], ["OTHER", "ACCESSORY", "ILLUMENATE"])
		for mapping in ({"line_id": 9}, {"secret": 0}, ["line_id"], "{"):
			with self.assertRaises(ValueError):
				self.preview(rows, json.dumps(mapping) if not isinstance(mapping, str) else mapping)
		with self.assertRaises(ValueError):
			self.preview(rows, {"notes": None})

	def test_part_numbers_that_do_not_decode_are_kept_in_the_notes(self):
		rows = [TEMPLATE, ["A", "1", "", "Strip", "LS-48", "", ""], ["B", "1", "", "", "ILL-AMB-1", "", ""], ["C", "1", "", "", "ILL-QQ-1", "", "-3"]]
		result = self.preview(rows)
		a, b, c = result["rows"]
		self.assertEqual(a["messages"], ["Part number not recognised. Choose the product when configuring."])
		self.assertEqual(b["messages"], ["This part number fits several products. Choose one when configuring."])
		self.assertEqual((c["status"], c["messages"]), ("error", ["Length (in) must be a number of inches"]))
		self.commit(rows[:3])
		self.assertEqual(self.schedule.lines[0].notes, "Description: Strip\nPart number: LS-48")
		self.assertIsNone(self.schedule.lines[1].fixture_template)

	def test_the_decode_kill_switch_skips_decoding(self):
		self.decode_enabled = False
		result = self.preview(self.rows()[:2])
		self.assertEqual(self.decoded, [])
		self.assertNotIn("summary", result["rows"][0])

	def test_files_are_checked_before_they_are_read(self):
		with self.module() as module:
			good = sheet(self.rows())
			for filename, content, message in (
				("lines.pdf", good, "Upload a .csv or .xlsx file"),
				("lines.csv", "", "The file is empty"),
				("lines.csv", "not base64!", "The file could not be read"),
				("lines.csv", "A" * (module.MAX_BYTES * 2), "larger than 1 MB"),
				("lines.xlsx", good, "not an Excel .xlsx file"),
				("lines.csv", sheet([TEMPLATE]), "no lines under its header"),
				("lines.csv", sheet([TEMPLATE, ["", "", "", "", "", "", ""], ["x"]]), None),
			):
				if message is None:
					continue
				with self.assertRaisesRegex(ValueError, message):
					module.preview_schedule_import("S1", filename, content)
			too_many = [TEMPLATE] + [["L", "1"]] * (module.MAX_ROWS + 1)
			with self.assertRaisesRegex(ValueError, "at most 500"):
				module.preview_schedule_import("S1", "lines.csv", sheet(too_many))
			exactly = [TEMPLATE] + [["L", "1"]] * module.MAX_ROWS
			self.assertEqual(len(module.preview_schedule_import("S1", "lines.csv", sheet(exactly))["rows"]), 500)
			# No recognisable header: the preview offers the columns to map instead of failing.
			unmapped = module.preview_schedule_import("S1", "lines.csv", sheet([["Foo"], ["1"]]))
			self.assertEqual((unmapped["columns"], unmapped["mapping"], unmapped["rows"]), (["Foo"], {}, []))
			self.assertIn("Choose which column holds each field", unmapped["warnings"][0])
			with self.assertRaisesRegex(ValueError, "Map at least one column"):
				module.commit_schedule_import("S1", "lines.csv", sheet([["Foo"], ["1"]]))

	def test_semicolon_sheets_and_excel_workbooks_are_read(self):
		result = self.preview([TEMPLATE, ["A", "2", "Lobby", "", "", "", ""]], filename="x.CSV")
		self.assertEqual(result["rows"][0]["qty"], 2)
		with self.module() as module:
			semi = module.preview_schedule_import("S1", "x.csv", sheet([TEMPLATE, ["A", "5", "Lobby, East", "", "", "", ""]], ";"))
			self.assertEqual((semi["rows"][0]["qty"], semi["rows"][0]["location"]), (5, "Lobby, East"))

		book = MagicMock()
		book.worksheets = [MagicMock()]
		book.worksheets[0].iter_rows.return_value = iter([("Type", "Qty", None), (None, None, None), ("A", 3.0, "Lobby")])
		openpyxl = types.SimpleNamespace(load_workbook=MagicMock(return_value=book))
		self.extras["openpyxl"] = openpyxl
		data = base64.b64encode(b"PK\x03\x04rest").decode()
		with self.module() as module:
			result = module.preview_schedule_import("S1", "x.xlsx", data)
		self.assertEqual(result["columns"], ["Type", "Qty", ""])
		self.assertEqual((result["rows"][0]["row"], result["rows"][0]["qty"]), (3, 3))
		self.assertTrue(openpyxl.load_workbook.call_args.kwargs["read_only"])
		book.close.assert_called_once()

	def test_guests_and_the_kill_switch_are_refused(self):
		self.enabled = False
		with self.assertRaisesRegex(ValueError, "turned off"):
			self.preview(self.rows())
		self.enabled = True
		with self.module() as module:
			self.frappe.session.user = "Guest"
			with self.assertRaises(PermissionError):
				module.commit_schedule_import("S1", "lines.csv", sheet(self.rows()))
		self.schedule.is_locked = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.commit(self.rows())

	def test_an_architects_schedule_with_a_title_block_reads_as_written(self):
		# Seen live: "QTY." and "MFR" were not recognised, so every quantity became 1 and a Lutron
		# downlight was added as an ilLumenate line; a title row above the header failed the file.
		rows = [
			["Smith Residence - Lighting Fixture Schedule"],
			["Issued for permit"],
			["TYPE", "QTY.", "MFR", "CATALOG #", "DESCRIPTION", "LAMP", "VOLTS", "LOCATION"],
			["A", "12", "Lutron", "HWQS", "Downlight", "LED 12W", "120", "Kitchen"],
			["B", "3", "ilLumenate", "", "Linear cove", "LED", "24", "Living"],
			["#1", "2 ea", "Acme", "", "Sconce", "", "", "Hall"],
		]
		result = self.preview(rows)
		self.assertEqual(
			result["mapping"],
			{
				"line_id": 0, "qty": 1, "manufacturer_name": 2, "part_number": 3, "description": 4,
				"lamp_info": 5, "input_voltage": 6, "location": 7,
			},
		)
		self.assertEqual(
			[(row["row"], row["line_id"], row["qty"], row["manufacturer_type"], row["status"]) for row in result["rows"]],
			[
				(4, "A", 12, "OTHER", "ok"),
				(5, "B", 3, "ILLUMENATE", "needs_configuration"),
				# "#1" is a fixture designation, not a comment.
				(6, "#1", 2, "OTHER", "ok"),
			],
		)
		self.assertIn("Row 3 is used as the header row; the rows above it were skipped.", result["warnings"])
		self.commit(rows)
		lutron, cove, sconce = self.schedule.lines
		# The catalog number is the other maker's model, and the description is kept.
		self.assertEqual(
			(lutron.manufacturer_name, lutron.fixture_model_number, lutron.lamp_info, lutron.input_voltage, lutron.notes),
			("Lutron", "HWQS", "LED 12W", "120", "Description: Downlight"),
		)
		self.assertEqual((cove.manufacturer_type, cove.notes), ("ILLUMENATE", "Description: Linear cove"))
		self.assertEqual((sconce.line_id, sconce.qty), ("#1", 2))

	def test_lengths_quantities_and_types_are_read_the_way_people_type_them(self):
		header = ["Type", "Qty", "Length", "Manufacturer Type", "Manufacturer"]
		rows = [
			header,
			["L1", "4", "10'", "ilLumenate", ""],
			["L2", "1,200", '48"', "Illumenate Lighting", ""],
			["L3", "2", "4' 6\"", "ILL", ""],
			["L4", "1", "120 in", "", "ilLumenate"],
			["B1", "6 pcs", "", "Other mfr", "Acme"],
			["P1", "2", "", "Accessory", ""],
			["X1", "1", "about ten feet", "", ""],
		]
		result = self.preview(rows)
		got = [(row["line_id"], row["qty"], row["manufacturer_type"], row["status"], row.get("length_in")) for row in result["rows"]]
		self.assertEqual(
			got,
			[
				("L1", 4, "ILLUMENATE", "needs_configuration", 120.0),
				("L2", 1200, "ILLUMENATE", "needs_configuration", 48.0),
				("L3", 2, "ILLUMENATE", "needs_configuration", 54.0),
				("L4", 1, "ILLUMENATE", "needs_configuration", 120.0),
				("B1", 6, "OTHER", "ok", None),
				("P1", 2, "ACCESSORY", "error", None),
				("X1", 1, "ILLUMENATE", "error", None),
			],
		)
		self.commit(rows, skip_errors=1)
		self.assertEqual(self.schedule.lines[0].notes, "Length: 120 in (entered as 10')")
		self.assertEqual(self.schedule.lines[3].notes, "Length: 120 in (entered as 120 in)")

	def test_missing_columns_are_called_out_in_the_preview(self):
		result = self.preview([["Type", "Location"], ["A", "Lobby"]])
		warnings = " ".join(result["warnings"])
		self.assertIn("every line gets Qty 1", warnings)
		self.assertIn("every line is treated as an ilLumenate line", warnings)
		self.assertNotIn("without a fixture type", warnings)
		header, examples = None, None
		with self.module() as module:
			header, examples = module.TEMPLATE_COLUMNS, module.TEMPLATE_ROWS
		full = self.preview([header, *examples, ["D1", "3"] + [""] * (len(header) - 2)])
		self.assertEqual(full["warnings"], [f"{len(examples)} row(s) starting with # were skipped as notes."])

	def test_a_part_number_kept_by_the_import_reads_back_from_the_notes(self):
		with self.module() as module:
			self.assertEqual(
				module.imported_part_number("Paint first\nPart number: ILL-SH01-SW-67\nLength: 48 in"), "ILL-SH01-SW-67"
			)
			self.assertIsNone(module.imported_part_number("Part number unknown, ask the architect"))
			self.assertIsNone(module.imported_part_number(None))

	def test_the_template_example_part_number_has_the_real_layout(self):
		with self.module() as module:
			tokens = module.EXAMPLE_PART_NUMBER.split("-")
			self.assertEqual(tokens[0], "ILL")
			self.assertGreaterEqual(len(tokens), 11)
			column = module.FIELD_NAMES.index("part_number")
			self.assertIn(module.EXAMPLE_PART_NUMBER, [row[column] for row in module.TEMPLATE_ROWS])
			self.assertIn(module.EXAMPLE_PART_NUMBER, [row[column] for row in module.EXAMPLES])

	def test_the_excel_template_guides_the_dealer_and_imports_once_filled_in(self):
		import openpyxl

		with self.module() as module:
			data = module.template_workbook()
			self.frappe.local.response = types.SimpleNamespace()
			module.download_import_template()
			self.assertEqual(self.frappe.local.response.type, "download")
			self.assertTrue(self.frappe.local.response.filename.endswith(".xlsx"))
			self.frappe.session.user = "Guest"
			with self.assertRaises(PermissionError):
				module.download_import_template()
			self.assertEqual(module.download_import_template.whitelist_options, {"methods": ["GET"]})
			columns = module.TEMPLATE_COLUMNS
		book = openpyxl.load_workbook(io.BytesIO(data))
		self.assertEqual(book.sheetnames, ["Lines", "How to use", "Examples"])
		self.assertEqual(book.active.title, "Lines")
		lines = book["Lines"]
		self.assertTrue(lines["A1"].value.startswith("#"))
		self.assertEqual([cell.value for cell in lines[2]], columns)
		self.assertTrue(all(cell.comment for cell in lines[2]), "every column name carries a tip")
		self.assertIn('"ILLUMENATE,OTHER,ACCESSORY"', [v.formula1 for v in lines.data_validations.dataValidation])
		how = " ".join(str(cell.value) for row in book["How to use"].iter_rows() for cell in row if cell.value)
		for words in ("Needs configuration", "Manufacturer Name", "Accessory Item Code", "Part Number"):
			self.assertIn(words, how)
		self.assertEqual(book["Examples"].max_row, 2 + len(module.EXAMPLES))

		# A dealer fills in two lines and uploads the file as is.
		lines.append(["A1", 4, "Lobby", "Cove", "", "", "10'", "ILLUMENATE"])
		lines.append(["B1", 2, "Hall", "Sconce", "", "", "", "", "Acme", "SC-1"])
		output = io.BytesIO()
		book.save(output)
		self.extras.pop("openpyxl", None)
		with self.module() as module:
			result = module.preview_schedule_import("S1", "filled.xlsx", base64.b64encode(output.getvalue()).decode())
		self.assertEqual(result["warnings"], [], "the template's own tip row is not reported")
		self.assertEqual(
			[(row["row"], row["line_id"], row["qty"], row["status"]) for row in result["rows"]],
			[(3, "A1", 4, "needs_configuration"), (4, "B1", 2, "ok")],
		)

	def test_the_endpoints_are_post_only(self):
		with self.module() as module:
			for endpoint in (module.preview_schedule_import, module.commit_schedule_import):
				self.assertEqual(endpoint.whitelist_options, {"methods": ["POST"]})
			self.assertEqual(module.TEMPLATE_COLUMNS[: len(TEMPLATE)], TEMPLATE)


if __name__ == "__main__":
	unittest.main()
