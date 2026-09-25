import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	build_identity,
	cable_stock_quantity,
	fingerprint,
	finite_number,
	length_mm,
	parse_bool,
)
from illumenate_lighting.illumenate_lighting.api.power_planner import plan_power
from illumenate_lighting.illumenate_lighting.api.product_projection import project_product, safe_document_url


class ConfigurationContracts(unittest.TestCase):
	def test_boolean_wire_values(self):
		for value in (False, 0, "0", "false", "False", "off", "no"):
			with self.subTest(value=value):
				self.assertFalse(parse_bool(value, default=True))
		for value in (True, 1, "1", "true", "on", "yes"):
			with self.subTest(value=value):
				self.assertTrue(parse_bool(value))
		self.assertTrue(parse_bool(None, default=True))
		for value in ("maybe", 2, [], {}, float("nan")):
			with self.subTest(value=value), self.assertRaises(ValueError):
				parse_bool(value)

	def test_finite_dimensions(self):
		for value in (True, float("inf"), float("nan"), "NaN", -1):
			with self.subTest(value=value), self.assertRaises(ValueError):
				finite_number(value, minimum=0)
		self.assertEqual(length_mm(72, "in"), length_mm(6, "ft"))
		self.assertEqual(length_mm(72, "in"), length_mm(1828.8))

	def test_cable_uom(self):
		self.assertEqual(cable_stock_quantity(72, "in", "Foot"), 6)
		self.assertAlmostEqual(cable_stock_quantity(72, "in", "Meter"), 1.8288)
		with self.assertRaises(ValueError):
			cable_stock_quantity(72, "in", "Nos")
		self.assertEqual(cable_stock_quantity(72, "in", "Nos", assembly_length_mm=1828.8), 1)

	def test_resolved_build_identity(self):
		self.assertEqual(fingerprint({"a": 1, "b": 2}), fingerprint({"b": 2, "a": 1}))
		base = build_identity({"include_power": False}, [], "r1", engine_version="2")
		self.assertNotEqual(base, build_identity({"include_power": True}, [], "r1", engine_version="2"))
		self.assertNotEqual(
			base, build_identity({"include_power": False}, [{"item": "supply"}], "r1", engine_version="2")
		)
		self.assertNotEqual(base, build_identity({"include_power": False}, [], "r2", engine_version="2"))


class ProductContracts(unittest.TestCase):
	def product(self, family="Fixture Template"):
		return {
			"name": "P1",
			"product_slug": "p1",
			"product_name": "Product",
			"is_active": 1,
			"is_configurable": 1,
			"product_type": family,
			"fixture_template": "F1",
			"tape_neon_template": "T1",
			"led_sheet_template": "S1",
		}

	def test_family_handoff_and_retirement(self):
		for family, category, template in (
			("Fixture Template", "Linear Fixture", "F1"),
			("LED Tape", "LED Tape", "T1"),
			("LED Neon", "LED Neon", "T1"),
			("LED Sheet", "LED Sheet", "S1"),
		):
			with self.subTest(family=family):
				product = self.product(family)
				projection = project_product(product)
				params = parse_qs(urlsplit(projection["configure_url"]).query)
				self.assertEqual(params["category"], [category])
				self.assertEqual(params["template"], [template])
				product["is_active"] = 0
				self.assertEqual(project_product(product)["capability"], "unavailable")

	def test_schema_document_option_projection(self):
		product = self.product()
		product["documents"] = [
			{"document_title": "Datasheet", "document_file": "/files/data.pdf", "document_type": "Datasheet"}
		]
		product["configurator_options"] = [
			{
				"option_step": 1,
				"option_label": "CCT",
				"allowed_values_json": '[{"code":"30","label":"3000K"}]',
			}
		]
		projection = project_product(product)
		self.assertEqual(projection["documents"][0]["title"], "Datasheet")
		self.assertEqual(projection["configurator_options"][0]["allowed_values"][0]["code"], "30")
		for kind, fields in (
			("document", product["documents"][0]),
			("configurator_option", product["configurator_options"][0]),
		):
			path = Path(
				f"illumenate_lighting/illumenate_lighting/doctype/ill_child_webflow_{kind}/ill_child_webflow_{kind}.json"
			)
			schema = json.loads(path.read_text())
			self.assertTrue(set(fields) <= {row["fieldname"] for row in schema["fields"]})

	def test_invalid_options_and_price_scope(self):
		product = self.product()
		product["configurator_options"] = [{"allowed_values_json": "broken"}]
		self.assertEqual(project_product(product)["capability"], "inquiry")
		self.assertNotIn("pricing", project_product(product, price=20))
		self.assertNotIn("pricing", project_product(self.product("LED Sheet"), price=20, commercial=True))
		self.assertEqual(project_product(self.product(), price=20, commercial=True)["pricing"]["amount"], 20)

	def test_private_or_unsafe_document_never_projected(self):
		for url in (
			"javascript:alert(1)",
			"//evil.test/a.pdf",
			"/private/files/a.pdf",
			"https://user:pass@example.com/a.pdf",
		):
			with self.subTest(url=url):
				self.assertIsNone(safe_document_url(url))


class PowerPlanning(unittest.TestCase):
	def candidate(self, item, total, per_output, outputs=1, factor=1, cost=1):
		return {
			"item_code": item,
			"max_wattage": total,
			"max_wattage_per_output": per_output,
			"outputs_count": outputs,
			"usable_load_factor": factor,
			"cost": cost,
		}

	def circuits(self, *loads):
		return [{"run_key": str(i), "watts": load} for i, load in enumerate(loads)]

	def test_unequal_runs_are_not_averaged(self):
		with self.assertRaises(ValueError):
			plan_power(self.circuits(20, 100), [self.candidate("60W", 120, 60, 2)])

	def test_total_capacity_and_derating(self):
		plan = plan_power(self.circuits(60, 60), [self.candidate("100W", 100, 100, 2)])
		self.assertEqual(plan["drivers"], [{"driver_item": "100W", "qty": 2}])
		with self.assertRaises(ValueError):
			plan_power(self.circuits(90), [self.candidate("100W", 100, 100, factor=0.8)])

	def test_prefer_one_feasible_supply_before_cost(self):
		plan = plan_power(
			self.circuits(20, 100),
			[self.candidate("single", 100, 100, cost=1), self.candidate("dual", 150, 100, 2, cost=100)],
		)
		self.assertEqual(plan["drivers"], [{"driver_item": "dual", "qty": 1}])
		self.assertEqual(sorted(a["watts"] for a in plan["allocations"]), [20, 100])

	def test_excluded_and_determinism(self):
		self.assertEqual(plan_power(self.circuits(100), [], include_power=False)["drivers"], [])
		choices = [self.candidate("B", 100, 100), self.candidate("A", 100, 100)]
		self.assertEqual(plan_power(self.circuits(60), choices), plan_power(self.circuits(60), choices[::-1]))
		self.assertEqual(plan_power(self.circuits(60), choices)["drivers"][0]["driver_item"], "A")


if __name__ == "__main__":
	unittest.main()
