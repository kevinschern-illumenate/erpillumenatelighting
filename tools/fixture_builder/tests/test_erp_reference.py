"""ERPNext export reference: parsing, the checked-in snapshot, and link resolution."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.fixture_builder.catalog import generate_catalog, prepare_catalog
from tools.fixture_builder.catalog_examples import example_catalog
from tools.fixture_builder.catalog_schema import build_schema
from tools.fixture_builder.erp_reference import (
	REFERENCE,
	build_reference,
	load_reference,
	parse_export,
	unconfirmed_links,
)

TAPE_EXPORT = "\n".join(
	[
		'"Data Import Template"',
		'"Table:","ilL-Spec-LED Tape"',
		'"Notes:"',
		'"DocType:","ilL-Spec-LED Tape","","","","","","~","ilL-Child-Tape-Dimming-Protocol","supported_dimming_protocols","",""',
		'"Column Labels:","ID","Tape Item","Input Voltage","W/ft","Operating Temperature","Created By","","ID","Protocol","Created On","Created By"',
		'"Column Name:","name","item","input_voltage","watts_per_foot","operating_temp","owner","~","name","protocol","creation","owner"',
		'"Start entering data below this line"',
		'"","""TAPE-A""","TAPE-A","24VDC",3.0,"\'-4°F to 140°F","someone@example.com","","""c1""","PWM","2026-01-01","someone@example.com"',
		'"","","","","","","","","""c2""","0-10V","2026-01-01","someone@example.com"',
		'"","""TAPE-B""","TAPE-B","24VDC",4.4,"","someone@example.com","","","","",""',
	]
)


class ErpReferenceTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.schema = build_schema()

	def test_export_rows_become_typed_records_with_child_tables(self):
		doctype, records = parse_export(TAPE_EXPORT, self.schema)
		self.assertEqual(doctype, "ilL-Spec-LED Tape")
		self.assertEqual(
			records[0],
			{
				"name": "TAPE-A",
				"item": "TAPE-A",
				"input_voltage": "24VDC",
				"watts_per_foot": 3.0,
				"operating_temp": "-4°F to 140°F",
				"supported_dimming_protocols": [{"protocol": "PWM"}, {"protocol": "0-10V"}],
			},
		)
		self.assertEqual(
			records[1], {"name": "TAPE-B", "item": "TAPE-B", "input_voltage": "24VDC", "watts_per_foot": 4.4}
		)

	def test_zip_exports_list_linked_records_as_existing(self):
		with tempfile.TemporaryDirectory() as folder:
			archive = Path(folder) / "exports.zip"
			with zipfile.ZipFile(archive, "w") as handle:
				handle.writestr("ilL-Spec-LED Tape (5).csv", TAPE_EXPORT)
				handle.writestr("notes.csv", "not,an,export\n")
			reference, skipped = build_reference([archive], self.schema, exported_on="2026-10-01")
		self.assertEqual(reference["doctypes"]["ilL-Spec-LED Tape"]["source"], "export")
		self.assertEqual(
			reference["doctypes"]["Item"], {"source": "links", "records": {"TAPE-A": {}, "TAPE-B": {}}}
		)
		self.assertEqual(
			set(reference["doctypes"]["ilL-Attribute-Dimming Protocol"]["records"]), {"PWM", "0-10V"}
		)
		self.assertEqual(skipped, ["notes.csv: not an ERPNext Data Import Template export"])

	def test_checked_in_snapshot_matches_current_doctypes_without_prices(self):
		data = json.loads(REFERENCE.read_text(encoding="utf-8"))
		self.assertGreater(len(data["doctypes"]["ilL-Spec-LED Tape"]["records"]), 0)

		def check(doctype, record, path):
			fields = {field["fieldname"]: field for field in self.schema["doctypes"][doctype]["fields"]}
			for key, value in record.items():
				self.assertIn(key, fields, path)
				self.assertNotEqual(fields[key]["fieldtype"], "Currency", f"{path}.{key}")
				if isinstance(value, list):
					for i, child in enumerate(value):
						check(fields[key]["options"], child, f"{path}.{key}[{i}]")

		for doctype, entry in data["doctypes"].items():
			self.assertIn(doctype, self.schema["doctypes"])
			for name, record in entry["records"].items():
				check(doctype, record, f"{doctype}/{name}")

	def test_reference_links_resolve_and_existing_records_are_not_reimported(self):
		config = example_catalog("tape")
		tape = config["records"]["ilL-Spec-LED Tape"][0]["item"]
		del config["external_links"]["ilL-Attribute-Dimming Protocol"]
		reference = {"ilL-Attribute-Dimming Protocol": {"PWM"}}
		with self.assertRaisesRegex(ValueError, "unresolved ilL-Attribute-Dimming Protocol / PWM"):
			prepare_catalog(config, self.schema)
		_, _, external = prepare_catalog(config, self.schema, reference)
		self.assertIn(("ilL-Attribute-Dimming Protocol", "PWM"), external)
		with tempfile.TemporaryDirectory() as output:
			generate_catalog(config, output, reference)
			manifest = json.loads((Path(output) / "manifest.json").read_text())
		sources = {(row["doctype"], row["name"]): row["source"] for row in manifest["external_links"]}
		self.assertEqual(sources["ilL-Attribute-Dimming Protocol", "PWM"], "ERPNext export")
		self.assertEqual(sources["UOM", "Meter"], "declared")
		with self.assertRaisesRegex(ValueError, f"{tape} already exists in ERPNext"):
			prepare_catalog(config, self.schema, {**reference, "ilL-Spec-LED Tape": {tape}})

	def test_declared_links_missing_from_full_exports_are_reported(self):
		with tempfile.TemporaryDirectory() as folder:
			path = Path(folder) / "reference.json"
			path.write_text(
				json.dumps(
					{
						"schema_version": 1,
						"exported_on": "2026-10-01",
						"doctypes": {
							"ilL-Attribute-CCT": {"source": "export", "records": {"3000K": {}}},
							"Item": {"source": "links", "records": {}},
						},
					}
				)
			)
			config = {
				"external_links": {"ilL-Attribute-CCT": ["3000K", "3000"], "Item": ["NEW"], "UOM": ["Nos"]}
			}
			self.assertEqual(unconfirmed_links(config, path), [("ilL-Attribute-CCT", "3000")])
			self.assertEqual(load_reference(path)["ilL-Attribute-CCT"], {"3000K"})


if __name__ == "__main__":
	unittest.main()
