"""Plan 3.7: recently used products for the schedule's Add Line picker."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.recent_products"
CONFIGURE = "illumenate_lighting.templates.pages.configure"


class RecentProducts(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.readable = {"SCH-1", "SCH-2"}
		self.families = {"Linear Fixture", "LED Tape", "LED Sheet", "Driver"}
		self.configurator_calls = []
		self.schedules = [
			Record(name="SCH-2", owner="buyer@example.com"),
			Record(name="SCH-1", owner="buyer@example.com"),
			Record(name="SCH-X", owner="someone@else.com"),
		]
		self.lines = [
			Record(parent="SCH-1", idx=1, fixture_template="FT-OLD"),
			Record(parent="SCH-1", idx=2, fixture_template="FT-1"),
			Record(parent="SCH-2", idx=1, tape_neon_template="TN-1"),
			Record(parent="SCH-2", idx=2, fixture_template="FT-1"),
			Record(parent="SCH-2", idx=3, led_sheet_template="LS-1", driver_template="DRV-1"),
			Record(parent="SCH-X", idx=1, fixture_template="FT-SECRET"),
		]
		# What the Add Line pickers offer right now (template_filters)
		self.offered = {
			"ilL-Fixture-Template": {"FT-1": Record(name="FT-1", template_code="ILL-FT1", template_name="Fixture One")},
			"ilL-Tape-Neon-Template": {
				"TN-1": Record(name="TN-1", template_code="TN1", template_name="Tape One", product_category="LED Tape")
			},
			"ilL-LED-Sheet-Template": {"LS-1": Record(name="LS-1", template_code="LS1", template_name="Sheet One")},
			"ilL-Driver-Template": {"DRV-1": Record(name="DRV-1", template_code="", template_name="")},
		}
		self.image_calls = []

		def attach_images(doctype, rows):
			self.image_calls.append((doctype, [row.name for row in rows]))
			for row in rows:
				row["image"] = "/files/" + row.name + ".jpg"
				row["image_alt"] = row.name + " hero"
			return rows

		self.extras = {
			ROOT + ".portal.site_flags": types.SimpleNamespace(recent_products_enabled=lambda: self.enabled),
			ROOT + ".portal.access": types.SimpleNamespace(
				can_read_schedule=lambda schedule, user=None: schedule.name in self.readable
			),
			ROOT + ".portal.configurator_access": types.SimpleNamespace(
				require_configurator=lambda schedule=None, user=None: self.configurator_calls.append(schedule)
			),
			ROOT + ".portal.rollout": types.SimpleNamespace(available=lambda family, **kw: family in self.families),
			ROOT + ".portal_listing": types.SimpleNamespace(
				template_filters=lambda staff=None, **filters: {**filters, "product_status": ["in", ["Active"]]}
			),
			CONFIGURE: types.SimpleNamespace(attach_images=attach_images),
		}

	def wire(self, frappe):
		frappe.get_list = MagicMock(return_value=self.schedules)

		def get_all(doctype, filters=None, fields=None, **kwargs):
			if doctype == "ilL-Child-Fixture-Schedule-Line":
				parents = filters["parent"][1]
				self.assertEqual(filters["parenttype"], "ilL-Project-Fixture-Schedule")
				self.assertEqual(filters["manufacturer_type"], "ILLUMENATE")
				return [Record(line) for line in self.lines if line.parent in parents]
			self.assertEqual(filters["product_status"], ["in", ["Active"]], "only templates the picker offers")
			names = filters["name"][1]
			return [Record(row) for name, row in self.offered.get(doctype, {}).items() if name in names]

		frappe.get_all = MagicMock(side_effect=get_all)

	def run_recent(self, *args, **kwargs):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			return module, frappe, module.recent_products(*args, **kwargs)

	def test_newest_schedule_and_last_lines_first_without_repeats(self):
		_module, _frappe, result = self.run_recent()
		self.assertTrue(result["success"])
		self.assertEqual(
			[(p["family"], p["name"]) for p in result["products"]],
			[("led_sheet", "LS-1"), ("driver", "DRV-1"), ("fixture", "FT-1"), ("tape_neon", "TN-1")],
		)
		self.assertEqual(self.configurator_calls, [None])

	def test_cards_carry_the_main_image_and_picker_details(self):
		_module, _frappe, result = self.run_recent()
		tape = next(p for p in result["products"] if p["name"] == "TN-1")
		self.assertEqual(tape["image"], "/files/TN-1.jpg", "D1 main image from attach_images (5.4)")
		self.assertEqual(tape["image_alt"], "TN-1 hero")
		self.assertEqual(tape["category"], "LED Tape")
		self.assertEqual(tape["doctype"], "ilL-Tape-Neon-Template")
		driver = next(p for p in result["products"] if p["name"] == "DRV-1")
		self.assertEqual((driver["template_code"], driver["template_name"]), ("DRV-1", "DRV-1"))

	def test_unreadable_schedules_and_unoffered_templates_are_left_out(self):
		_module, _frappe, result = self.run_recent()
		names = [p["name"] for p in result["products"]]
		self.assertNotIn("FT-SECRET", names, "lines of schedules the user cannot read")
		self.assertNotIn("FT-OLD", names, "templates the picker no longer offers")

	def test_families_outside_the_rollout_are_left_out(self):
		self.families.discard("LED Tape")
		self.families.discard("Driver")
		_module, _frappe, result = self.run_recent()
		self.assertEqual([p["name"] for p in result["products"]], ["LS-1", "FT-1"])

	def test_the_current_schedule_comes_first_and_grants_configurator_access(self):
		_module, _frappe, result = self.run_recent("SCH-1", limit="2")
		self.assertEqual([p["name"] for p in result["products"]], ["FT-1", "LS-1"])
		self.assertEqual(self.configurator_calls, ["SCH-1"])

	def test_limit_is_clamped(self):
		module, _frappe, _result = self.run_recent()
		self.assertEqual(module._limit("abc"), module.DEFAULT_LIMIT)
		self.assertEqual(module._limit("0"), 1)
		self.assertEqual(module._limit(1000), module.MAX_LIMIT)

	def test_no_schedules_means_no_template_queries(self):
		self.schedules = []
		_module, frappe, result = self.run_recent()
		self.assertEqual(result["products"], [])
		frappe.get_all.assert_not_called()

	def test_kill_switch_and_guest_are_refused(self):
		self.enabled = False
		with self.assertRaises(PermissionError):
			self.run_recent()
		self.enabled = True
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				module.recent_products()
		self.assertEqual(self.configurator_calls, [])

	def test_is_a_get_endpoint(self):
		module, _frappe, _result = self.run_recent()
		self.assertEqual(module.recent_products.whitelist_options, {})


if __name__ == "__main__":
	unittest.main()
