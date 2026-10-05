"""Catalog contracts: current DocTypes, reference ordering, and CSV round trips."""

import ast
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.fixture_builder.__main__ import generate_all, validate_config
from tools.fixture_builder.catalog import (
	CONFIGURATION_TABLES,
	WEBFLOW_TEMPLATES,
	csv_data,
	generate_catalog,
	identity,
	links,
	prepare_catalog,
	with_defaults,
)
from tools.fixture_builder.catalog_examples import example_catalog
from tools.fixture_builder.catalog_schema import PRODUCTS, ROOT, SNAPSHOT, build_schema
from tools.fixture_builder.config_schema import load_config


class CatalogTests(unittest.TestCase):
	def test_cli_uses_shared_catalog_implementation(self):
		from illumenate_lighting.illumenate_lighting.catalog_authoring.catalog import (
			prepare_catalog as shared,
		)

		self.assertIs(prepare_catalog, shared)

	@classmethod
	def setUpClass(cls):
		cls.schema = build_schema()

	def test_browser_metadata_tracks_live_doctypes(self):
		self.assertEqual(json.loads(SNAPSHOT.read_text(encoding="utf-8")), self.schema)
		for product in PRODUCTS.values():
			self.assertIn(product["template"], self.schema["doctypes"])
			self.assertIn(product["spec"], self.schema["doctypes"])

	def test_supported_templates_track_runtime_publication_contract(self):
		path = ROOT / "illumenate_lighting/illumenate_lighting/api/product_readiness.py"
		module = ast.parse(path.read_text(encoding="utf-8"))
		assignment = next(
			node
			for node in module.body
			if isinstance(node, ast.Assign)
			and any(isinstance(target, ast.Name) and target.id == "TEMPLATES" for target in node.targets)
		)
		for product, (field, doctype, choices) in ast.literal_eval(assignment.value).items():
			self.assertEqual(WEBFLOW_TEMPLATES[product], (field, doctype))
			self.assertEqual(CONFIGURATION_TABLES[doctype], choices)

	def test_empty_active_template_and_missing_product_template_are_rejected(self):
		config = example_catalog("led-sheet")
		config["records"]["ilL-LED-Sheet-Template"][0]["allowed_specs"] = []
		self.assertTrue(any("active compatible specification" in issue for issue in validate_config(config)))
		config = example_catalog("driver")
		del config["records"]["ilL-Webflow-Product"][0]["driver_template"]
		self.assertTrue(any("matching product template" in issue for issue in validate_config(config)))

	def test_every_product_example_round_trips_and_generates_ordered_imports(self):
		browser_examples = json.loads((ROOT / "tools/yaml_builder_ui/src/catalog-examples.json").read_text())
		for product in PRODUCTS:
			with self.subTest(product=product), tempfile.TemporaryDirectory() as output:
				config = load_config(ROOT / f"tools/fixture_builder/templates/catalog_{product}.yaml")
				self.assertEqual(config, example_catalog(product))
				self.assertEqual(config, browser_examples[product])
				self.assertEqual(validate_config(config), [])
				files = generate_all(config, output)
				manifest = json.loads((Path(output) / "manifest.json").read_text())
				self.assertEqual(list(files), [row["file"] for row in manifest["imports"]])
				known = {(row["doctype"], row["name"]) for row in manifest["external_links"]}
				_, batches, _ = prepare_catalog(config, self.schema)
				for entry, (doctype, records) in zip(manifest["imports"], batches, strict=True):
					with open(files[entry["file"]], encoding="utf-8-sig", newline="") as handle:
						header, *rows = list(csv.reader(handle))
					self.assertEqual(len(header), len(set(header)))
					self.assertTrue(all(len(row) == len(header) for row in rows))
					self.assertEqual(entry["records"], len(records))
					for record in records:
						for target, name, field in links(doctype, record, self.schema):
							self.assertIn(
								(target, name), known, f"{doctype}.{field} imported before dependency"
							)
						known.add((doctype, identity(doctype, record, self.schema)))

	def test_child_protocol_tables_with_same_doctype_do_not_mix(self):
		record = with_defaults(
			"ilL-Spec-Controller",
			{
				"item": "CTRL",
				"input_protocols": [{"protocol": "DMX"}, {"protocol": "DALI"}],
				"output_protocols": [{"protocol": "PWM"}],
				"notes": "line one\nline two",
			},
			self.schema,
		)
		headers, rows = csv_data("ilL-Spec-Controller", [record], self.schema)
		input_col = headers.index("Protocol (Input Protocols)")
		output_col = headers.index("Protocol (Output Protocols)")
		self.assertEqual([row[input_col] for row in rows], ["DMX", "DALI"])
		self.assertEqual([row[output_col] for row in rows], ["PWM", ""])
		self.assertEqual(rows[1][headers.index("Controller Item")], "")

	def test_item_supplier_rows_export_part_number_and_description(self):
		record = {
			"item_code": "CH-CA01",
			"supplier_items": [
				{
					"supplier": "Linea Lighting Co., Limited",
					"supplier_part_no": "00123",
					"custom_supplier_description": "Channel, 2 m",
				},
				{"supplier": "Backup Supplier", "supplier_part_no": "B-9"},
			],
		}
		headers, rows = csv_data("Item", [record], self.schema)
		columns = [
			headers.index(name)
			for name in (
				"Supplier (Supplier Items)",
				"Supplier Part Number (Supplier Items)",
				"supplier_items.custom_supplier_description",
			)
		]
		self.assertEqual(
			[[row[i] for i in columns] for row in rows],
			[["Linea Lighting Co., Limited", "00123", "Channel, 2 m"], ["Backup Supplier", "B-9", ""]],
		)

	def test_unresolved_links_fail_before_any_files_are_written(self):
		config = example_catalog("led-sheet")
		config["records"]["ilL-LED-Sheet-Template"][0]["leader_cable_item"] = "TYPO"
		with tempfile.TemporaryDirectory() as output:
			with self.assertRaisesRegex(ValueError, "unresolved Item / TYPO"):
				generate_catalog(config, output)
			self.assertEqual(list(Path(output).iterdir()), [])

	def test_ambiguous_variants_are_rejected_even_when_hidden_axes_differ(self):
		config = example_catalog("driver")
		template = config["records"]["ilL-Driver-Template"][0]
		variant = {**template["variants"][0], "input_protocol": "DALI", "is_default": 0}
		template["variants"].append(variant)
		with self.assertRaisesRegex(ValueError, "ambiguous variants"):
			prepare_catalog(config)

	def test_engineering_contract_is_enforced(self):
		for doctype, product, field, value in (
			("ilL-Spec-Driver", "driver", "usable_load_factor", 1.1),
			("ilL-Spec-LED Tape", "tape", "input_protocol", ""),
			("ilL-Spec-LED-Sheet", "led-sheet", "sheet_width_ft", 0),
			("ilL-Spec-Controller", "controller", "channels", 1.5),
		):
			with self.subTest(doctype=doctype):
				config = example_catalog(product)
				config["records"][doctype][0][field] = value
				self.assertTrue(any(field in error for error in validate_config(config)))

	def test_unknown_fields_invalid_enums_and_nonfinite_values_are_rejected(self):
		for key, value in (
			("typo", 1),
			("max_wattage", math.inf),
			("output_type", "Wrong"),
			("outputs_count", "two"),
		):
			with self.subTest(key=key):
				config = example_catalog("driver")
				config["records"]["ilL-Spec-Driver"][0][key] = value
				with self.assertRaisesRegex(ValueError, key):
					prepare_catalog(config)

	def test_circular_reverse_links_explain_recovery(self):
		config = example_catalog("driver")
		config["records"]["ilL-Driver-Template"][0]["webflow_product"] = "example-driver"
		with self.assertRaisesRegex(ValueError, "Circular import links"):
			prepare_catalog(config)

	def test_same_doctype_dependencies_split_into_ordered_batches(self):
		config = example_catalog("driver")
		config["records"]["Item Group"] = [
			{"item_group_name": "Products", "parent_item_group": "Example Parent"},
			{"item_group_name": "Example Parent", "is_group": 1},
		]
		_, batches, _ = prepare_catalog(config)
		groups = [rows for doctype, rows in batches if doctype == "Item Group"]
		self.assertEqual(len(groups), 2)
		self.assertEqual(groups[0][0]["item_group_name"], "Example Parent")

	def test_duplicate_names_and_missing_prompt_names_are_rejected(self):
		config = example_catalog("driver")
		config["records"]["Item"].append(dict(config["records"]["Item"][0]))
		with self.assertRaisesRegex(ValueError, "duplicate record"):
			prepare_catalog(config)
		config = example_catalog("driver")
		config["records"]["ilL-Attribute-LED Package"] = [{"code": "SW", "spectrum_type": "Static White"}]
		self.assertTrue(validate_config(config))

	def test_dynamic_links_are_checked(self):
		config = example_catalog("led-sheet")
		config["records"]["ilL-LED-Sheet-Template"][0]["allowed_options"][0]["attribute_link"] = "TYPO"
		with self.assertRaisesRegex(ValueError, "unresolved ilL-Attribute-CCT / TYPO"):
			prepare_catalog(config)

	def test_catalog_loader_rejects_unknown_version_and_nonmapping(self):
		with tempfile.TemporaryDirectory() as output:
			path = Path(output) / "invalid.yaml"
			for value in ([1, 2], {"schema_version": 999}):
				path.write_text(yaml.safe_dump(value), encoding="utf-8")
				with self.assertRaises(ValueError):
					load_config(path)


if __name__ == "__main__":
	unittest.main()
