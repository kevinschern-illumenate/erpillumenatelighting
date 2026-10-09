"""Field wire specs and the Desk CSV import (System Designer WP-1.4, D7)."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

WIRE = ROOT + ".system_design.wire"
IMPORT = ROOT + ".system_design.wire_import"
TEMPLATE = Path(__file__).resolve().parents[2] / "tools/seed_imports/field_wire_TEMPLATE.csv"
HEADER = (
	"item_code,item_name,wire_name,category,applications,conductors,listing,rated_v,temp_rating_c,"
	"plenum,riser,wet,direct_burial,sunlight_resistant,shielded,impedance_ohm,resistance_ohm_per_kft,"
	"ampacity_a,ampacity_basis,od_in,riser_label,sales_uom_mode,spool_length_ft,is_verified,"
	"source_reference,is_active"
)
ROW = (
	'WIRE-18-2-CL3R,18/2 CL3R,18/2 CL3R,class2-power,"class2-dc, lv-fixture-whip",'
	"2x18 Cu stranded power (red/black),CL3R,300,75,0,1,0,0,0,0,,6.39,,,0.2,18/2 CL3R,"
	"Per Foot,,1,Manufacturer datasheet rev C,1"
)


def csv_text(*rows):
	return "\n".join((HEADER, *rows)) + "\n"


class WireRules(unittest.TestCase):
	def setUp(self):
		self.context = load_service(WIRE)
		self.wire, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def spec(self, **values):
		base = {
			"category": "Class 2 Power",
			"applications": "class2-dc",
			"temp_rating_c": "75",
			"sales_uom_mode": "Per Foot",
			"rated_v": 300,
			"source_reference": "Manufacturer datasheet",
		}
		return self.wire.spec_problems({**base, **values})

	def test_conductor_groups_parse(self):
		rows, problems = self.wire.parse_conductors(
			"2x18 Cu stranded power (red/black); 1 \u00d7 #18 cu solid ground; 4x24 Cu solid data pair"
		)
		self.assertEqual(problems, [])
		self.assertEqual(
			rows,
			[
				{
					"count": 2,
					"awg": "18",
					"material": "Cu",
					"stranding": "Stranded",
					"role": "Power",
					"colors": "red, black",
				},
				{"count": 1, "awg": "18", "material": "Cu", "stranding": "Solid", "role": "Ground"},
				{"count": 4, "awg": "24", "material": "Cu", "stranding": "Solid", "role": "Data Pair"},
			],
		)
		self.assertEqual(self.wire.parse_conductors("1x4/0 Al stranded power")[0][0]["awg"], "4/0")

	def test_bad_conductor_groups_are_reported(self):
		rows, problems = self.wire.parse_conductors("two 18 gauge; 2x17 Cu solid power")
		self.assertEqual(rows, [])
		self.assertEqual(len(problems), 2)
		self.assertIn("AWG 17", problems[1])

	def test_conductor_rules(self):
		self.assertEqual(self.wire.conductor_problems([]), ["Add at least one conductor group"])
		problems = self.wire.conductor_problems(
			[{"count": 3, "role": "Data Pair"}, {"count": 2, "role": "Power", "colors": "red"}]
		)
		self.assertIn("even", problems[0])
		self.assertIn("one color per conductor", problems[1])
		self.assertEqual(self.wire.conductor_problems([{"count": 2, "role": "Data Pair"}]), [])

	def test_per_spool_requires_spool_length(self):
		self.assertIn(
			"Spool length (ft) is required when the wire is sold per spool",
			self.spec(sales_uom_mode="Per Spool"),
		)
		self.assertIn(
			"Spool length (ft) is required when the wire is sold per spool",
			self.spec(sales_uom_mode="Per Spool", spool_length_ft=0),
		)
		self.assertEqual(self.spec(sales_uom_mode="Per Spool", spool_length_ft=500), [])
		self.assertEqual(self.spec(), [])

	def test_applications_and_category(self):
		self.assertEqual(
			self.wire.split_applications("class2-dc, DMX;class2-dc nope"), (["class2-dc", "dmx"], ["nope"])
		)
		self.assertIn("Unknown run types: nope", self.spec(applications="dmx,nope"))
		self.assertIn("List at least one run type in Applications", self.spec(applications=" "))
		self.assertEqual(self.wire.category_label("building-wire"), "Building Wire")
		self.assertEqual(self.wire.category_label("Flex Cord"), "Flex Cord")
		self.assertIsNone(self.wire.category_label("rope"))

	def test_example_data_is_refused(self):
		problems = self.spec(source_reference="Synthetic example for the riser implementation plan")
		self.assertTrue(any("EXAMPLE" in p for p in problems))

	def test_item_must_be_sellable_and_match_the_sales_unit(self):
		item = {"name": "W1", "is_sales_item": 1, "disabled": 0, "has_variants": 0, "stock_uom": "Foot"}
		self.assertEqual(self.wire.item_problems(item, "Per Foot"), [])
		self.assertEqual(self.wire.item_problems(None, "Per Foot"), ["Item does not exist"])
		self.assertIn(
			"must be a sales item", self.wire.item_problems({**item, "is_sales_item": 0}, "Per Foot")[0]
		)
		self.assertIn("template", self.wire.item_problems({**item, "has_variants": 1}, "Per Foot")[0])
		self.assertIn("disabled", self.wire.item_problems({**item, "disabled": 1}, "Per Foot")[0])
		self.assertIn("must be Foot", self.wire.item_problems({**item, "stock_uom": "Nos"}, "Per Foot")[0])
		self.assertIn("cannot be Foot", self.wire.item_problems(item, "Per Spool")[0])
		self.assertEqual(self.wire.item_problems({**item, "stock_uom": "Spool"}, "Per Spool"), [])


class WireSpecController(unittest.TestCase):
	def load(self):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		model = types.ModuleType("frappe.model")
		model.document = document
		return load_service(
			ROOT + ".doctype.ill_spec_wire.ill_spec_wire",
			{"frappe.model": model, "frappe.model.document": document},
		)

	def doc(self, module, **values):
		base = {
			"item": "W1",
			"category": "class2-power",
			"applications": "class2-dc,  dmx",
			"temp_rating_c": "75",
			"sales_uom_mode": "Per Foot",
			"spool_length_ft": 250,
			"rated_v": 300,
			"source_reference": "Datasheet",
		}
		doc = module.ilLSpecWire()
		doc.__dict__.update({**base, **values})
		doc.conductors = [Record(count=2, role="Power", as_dict=None)]
		for row in doc.conductors:
			row["as_dict"] = lambda row=row: dict(row)
		doc.as_dict = lambda: dict(doc.__dict__)
		return doc

	def test_validate_normalizes_and_accepts_a_sellable_item(self):
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = Record(
				name="W1", is_sales_item=1, disabled=0, has_variants=0, stock_uom="Foot"
			)
			doc = self.doc(module)
			doc.validate()
			self.assertEqual((doc.category, doc.applications), ("Class 2 Power", "class2-dc,dmx"))
			self.assertIsNone(doc.spool_length_ft)

	def test_validate_refuses_an_item_that_is_not_sold(self):
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = Record(
				name="W1", is_sales_item=0, disabled=0, has_variants=0, stock_uom="Foot"
			)
			with self.assertRaisesRegex(ValueError, "must be a sales item"):
				self.doc(module).validate()

	def test_validate_requires_spool_length_per_spool(self):
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = Record(
				name="W1", is_sales_item=1, disabled=0, has_variants=0, stock_uom="Spool"
			)
			with self.assertRaisesRegex(ValueError, "Spool length"):
				self.doc(module, sales_uom_mode="Per Spool", spool_length_ft=None).validate()


class WireCsvImport(unittest.TestCase):
	def load(self, allowed=True):
		def require_capability(name):
			if not allowed:
				raise PermissionError(name)

		access = types.SimpleNamespace(require_capability=MagicMock(side_effect=require_capability))
		return load_service(IMPORT, {ROOT + ".system_design.access": access})

	def test_parser_reads_a_reviewed_row(self):
		with self.load() as (module, _frappe):
			(row,) = module.parse_csv("﻿" + csv_text(ROW, ",,,,"))
			self.assertEqual(row["problems"], [])
			self.assertEqual(row["row"], 2)
			spec = row["spec"]
			self.assertEqual(spec["category"], "Class 2 Power")
			self.assertEqual(spec["applications"], "class2-dc,lv-fixture-whip")
			self.assertEqual(
				(spec["rated_v"], spec["resistance_ohm_per_kft"], spec["ampacity_a"]), (300.0, 6.39, None)
			)
			self.assertEqual(
				(spec["riser"], spec["plenum"], spec["is_verified"], spec["is_active"]), (1, 0, 1, 1)
			)
			self.assertEqual(spec["conductors"][0]["colors"], "red, black")
			self.assertIsNone(spec["spool_length_ft"])

	def test_parser_reports_row_problems(self):
		bad = ROW.replace("300,75", "lots,80").replace(",1,0,0,0,0,", ",maybe,0,0,0,0,")
		with self.load() as (module, _frappe):
			first, second = module.parse_csv(csv_text(bad, ROW))
			self.assertIn("rated_v must be a number", first["problems"])
			self.assertIn("riser must be yes/no or 1/0", first["problems"])
			self.assertIn("Temperature rating must be 60, 75, 90 or 105", first["problems"])
			self.assertTrue(any("repeated" in p for p in second["problems"]))

	def test_parser_refuses_unusable_files(self):
		with self.load() as (module, _frappe):
			for text in ("", "item_code,wire_name\nA,B\n", csv_text()):
				with self.subTest(text=text[:20]), self.assertRaises(module.DesignError) as caught:
					module.parse_csv(text)
				self.assertEqual(caught.exception.code, "INVALID")

	def test_template_has_every_column_and_no_values(self):
		with self.load() as (module, _frappe):
			with open(TEMPLATE, encoding="utf-8") as handle:
				header, *rest = handle.read().splitlines()
			self.assertEqual(tuple(header.split(",")), module.COLUMNS)
			self.assertTrue(all(not line.replace(",", "").strip() for line in rest))

	def test_dry_run_writes_nothing(self):
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = None
			frappe.db.exists.return_value = False
			report = module.import_wire_csv(csv_text(ROW))
			self.assertEqual(report["rows"][0]["item_action"], "create")
			self.assertEqual(report["rows"][0]["spec_action"], "create")
			self.assertEqual((report["dry_run"], report["written"], report["invalid"]), (True, False, 0))
			frappe.get_doc.assert_not_called()

	def test_invalid_rows_block_the_whole_import(self):
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = Record(
				name="WIRE-18-2-CL3R", is_sales_item=1, disabled=0, has_variants=1, stock_uom="Foot"
			)
			frappe.db.exists.return_value = False
			report = module.import_wire_csv(csv_text(ROW), dry_run=False)
			self.assertFalse(report["written"])
			self.assertIn("template", report["rows"][0]["problems"][0])
			frappe.get_doc.assert_not_called()

	def test_import_creates_a_sellable_item_and_spec(self):
		spool = ROW.replace("WIRE-18-2-CL3R", "WIRE-SPOOL").replace("Per Foot,", "Per Spool,500")
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = None
			frappe.db.exists.return_value = False
			docs = []
			frappe.get_doc.side_effect = lambda values: docs.append(values) or MagicMock()
			report = module.import_wire_csv(csv_text(ROW, spool), dry_run=False)
			self.assertTrue(report["written"])
			items = [d for d in docs if d["doctype"] == "Item"]
			self.assertEqual(
				[(i["item_code"], i["stock_uom"], i["is_sales_item"], i["item_group"]) for i in items],
				[("WIRE-18-2-CL3R", "Foot", 1, "Field Wire"), ("WIRE-SPOOL", "Spool", 1, "Field Wire")],
			)
			specs = [d for d in docs if d["doctype"] == "ilL-Spec-Wire"]
			self.assertEqual([s["item"] for s in specs], ["WIRE-18-2-CL3R", "WIRE-SPOOL"])
			self.assertEqual(specs[1]["spool_length_ft"], 500.0)
			self.assertNotIn("conductors", specs[0])
			frappe.db.savepoint.assert_called_once_with("field_wire_import")

	def test_failed_write_rolls_back(self):
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = None
			frappe.db.exists.return_value = False
			frappe.get_doc.side_effect = RuntimeError("duplicate")
			with self.assertRaises(RuntimeError):
				module.import_wire_csv(csv_text(ROW), dry_run=False)
			frappe.db.rollback.assert_called_once_with(save_point="field_wire_import")

	def test_endpoint_needs_catalog_staff(self):
		with self.load(allowed=False) as (module, frappe):
			result = module.import_field_wire(csv_text(ROW))
			self.assertEqual(result["code"], "FORBIDDEN")
			frappe.db.get_value.assert_not_called()
		with self.load() as (module, frappe):
			frappe.db.get_value.return_value = None
			frappe.db.exists.return_value = False
			result = module.import_field_wire(csv_text(ROW), dry_run="0")
			self.assertTrue(result["success"])
			self.assertTrue(result["data"]["written"])


if __name__ == "__main__":
	unittest.main()
