# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for opening a schedule in the designer (WP-2.3)."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import api
from illumenate_lighting.illumenate_lighting.system_design.test_designs import designer_customer


class TestOpenDesign(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		project = frappe.get_doc(
			{
				"doctype": "ilL-Project",
				"project_name": "ZZ Designer Open Test",
				"customer": designer_customer(),
			}
		)
		project.insert(ignore_permissions=True)
		schedule = frappe.get_doc(
			{
				"doctype": "ilL-Project-Fixture-Schedule",
				"schedule_name": "ZZ Designer Open Schedule",
				"ill_project": project.name,
				"lines": [
					{
						"line_id": "TP1",
						"qty": 2,
						"location": "Hall",
						"manufacturer_type": "OTHER",
						"manufacturer_name": "Other Co",
						"watts_each": 12,
						"input_voltage_v": 120,
						"voltage_class": "Line Voltage",
					},
					{"line_id": "TP2", "qty": 1, "location": "Hall", "manufacturer_type": "OTHER"},
				],
			}
		)
		schedule.insert(ignore_permissions=True)
		self.schedule = schedule

	def test_open_design_lists_lines_and_readiness(self):
		response = api.open_design(schedule=self.schedule.name)
		self.assertTrue(response["success"], response)
		data = response["data"]
		self.assertEqual([line["kind"] for line in data["lines"]], ["third-party", "third-party"])
		keys = [line["key"] for line in data["lines"]]
		self.assertEqual(data["readiness"]["ready"], keys[:1])
		self.assertEqual(data["readiness"]["needs_data"][0]["key"], keys[1])
		self.assertEqual(len(data["catalog_hash"]), 64)
		self.assertFalse(data["review_requirement"]["required"])
		self.assertTrue(data["permissions"]["can_edit"])
		self.assertIsNone(data["design"])
		self.assertIsNone(data["newer_version"])
		self.assertNotIn("<", data["settings"]["terms_text"])
		self.assertIn("licensed electrician", data["settings"]["terms_text"])
		self.assertEqual(api.open_design(schedule="NOPE-404")["code"], "NOT_FOUND")

	def test_eligible_supplies(self):
		self.schedule.append(
			"lines",
			{
				"line_id": "TP3",
				"qty": 1,
				"location": "Hall",
				"manufacturer_type": "OTHER",
				"watts_each": 10,
				"input_voltage_v": 24,
				"voltage_class": "Low Voltage",
			},
		)
		self.schedule.save(ignore_permissions=True)
		keys = [line["key"] for line in api.open_design(schedule=self.schedule.name)["data"]["lines"]]
		line_voltage = api.eligible_supplies(schedule=self.schedule.name, run_keys=f'["{keys[0]}:1:1"]')
		self.assertEqual(line_voltage["code"], "INVALID")
		self.assertIn("line voltage", line_voltage["error"])
		found = api.eligible_supplies(
			schedule=self.schedule.name, run_keys=[f"{keys[2]}:1:1"], location_rating="Dry"
		)
		self.assertTrue(found["success"], found)
		for row in found["data"]:
			self.assertEqual(set(row), {"catalog_id", "item_code", "rank", "location_rating"})
		bad = api.eligible_supplies(
			schedule=self.schedule.name, run_keys=[f"{keys[2]}:1:1"], location_rating="Sky"
		)
		self.assertEqual(bad["code"], "INVALID")
		self.assertEqual(api.eligible_supplies(schedule="NOPE-404", run_keys=["a:1:1"])["code"], "NOT_FOUND")

	def test_find_schedules_and_review_requirement(self):
		found = api.find_schedules(query="ZZ Designer Open")
		self.assertTrue(found["success"], found)
		self.assertIn(self.schedule.name, [row["name"] for row in found["data"]])
		self.assertEqual(api.find_schedules(query="Z")["code"], "INVALID")
		requirement = api.review_requirement(schedule=self.schedule.name)
		self.assertEqual(requirement["data"]["required"], False)
