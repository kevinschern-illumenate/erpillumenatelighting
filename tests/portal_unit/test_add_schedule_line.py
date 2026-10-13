"""Generic line entry cannot elevate a dealer's input to a configured product."""

import types
import unittest
from unittest.mock import MagicMock

from test_product_finder_content import FakeDocument
from test_services import ROOT, Record, load_service


class AddLine(unittest.TestCase):
	def run_add(self, staff=False, item=None, **changes):
		deps = {
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda c: staff),
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				has_permission=lambda *a: True
			),
		}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			line = FakeDocument(idx=1)
			schedule = Record(
				name="S", status="DRAFT", is_locked=0, lines=[line], append=lambda *a: line, save=MagicMock()
			)
			frappe.get_doc.return_value = schedule
			frappe.db.exists.return_value = True
			frappe.db.get_value.return_value = item
			result = api.add_schedule_line(
				"S", {"line_id": "L", "qty": 1, "configuration_status": "Configured", **changes}
			)
			return result, line, schedule

	def test_dealer_is_pending_and_staff_retains_explicit_status(self):
		for staff, status in [(False, "Pending"), (True, "Configured")]:
			result, line, _ = self.run_add(staff)
			self.assertTrue(result["success"], result)
			self.assertEqual(line.configuration_status, status)

	def test_accessory_must_be_an_active_sales_sku(self):
		for item in (
			None,
			Record(disabled=1, is_sales_item=1),
			Record(disabled=0, is_sales_item=0),
			Record(disabled=0, is_sales_item=1, has_variants=1),
		):
			result, _, schedule = self.run_add(item=item, accessory_item="SKU", manufacturer_type="ACCESSORY")
			self.assertFalse(result["success"])
			schedule.save.assert_not_called()
		result, _, _ = self.run_add(
			item=Record(disabled=0, is_sales_item=1, has_variants=0),
			accessory_item="SKU",
			manufacturer_type="ACCESSORY",
		)
		self.assertTrue(result["success"], result)

	def test_extrusion_kit_line_keeps_its_template_for_the_kit_configurator(self):
		for product_type in ("Extrusion Kits", "Extrusion Kit"):
			result, line, schedule = self.run_add(
				staff=True, item=1, product_type=product_type, kit_template="KIT-A"
			)
			self.assertTrue(result["success"], result)
			self.assertEqual(line.product_type, "Extrusion Kit")
			self.assertEqual(line.kit_template, "KIT-A")
			self.assertEqual(line.configuration_status, "Pending")
			schedule.save.assert_called_once()

	def test_extrusion_kit_line_needs_an_active_template(self):
		for changes in ({"kit_template": "GONE"}, {"product_type": "Extrusion Kits"}):
			result, _, schedule = self.run_add(item=None, **changes)
			self.assertFalse(result["success"])
			schedule.save.assert_not_called()
