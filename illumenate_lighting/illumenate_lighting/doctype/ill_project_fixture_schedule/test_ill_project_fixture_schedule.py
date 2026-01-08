# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestilLProjectFixtureSchedule(FrappeTestCase):
	def setUp(self):
		"""Set up test data"""
		# Create test customer
		self.customer_name = "_Test Customer for Schedule"
		if not frappe.db.exists("Customer", self.customer_name):
			customer = frappe.new_doc("Customer")
			customer.customer_name = self.customer_name
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		# Create test item for configured fixture
		self.item_code = "_Test Configured Fixture Item"
		if not frappe.db.exists("Item", self.item_code):
			item = frappe.new_doc("Item")
			item.item_code = self.item_code
			item.item_name = self.item_code
			item.item_group = "Products"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)

		# Create test fixture template
		self.template_code = "_Test Template"
		if not frappe.db.exists("ilL-Fixture-Template", self.template_code):
			template = frappe.new_doc("ilL-Fixture-Template")
			template.template_code = self.template_code
			template.template_name = "Test Template"
			template.is_active = 1
			template.insert(ignore_permissions=True)

		# Create test configured fixture
		self.config_hash = "_test_config_hash_12345678"
		if not frappe.db.exists("ilL-Configured-Fixture", self.config_hash):
			config_fixture = frappe.new_doc("ilL-Configured-Fixture")
			config_fixture.config_hash = self.config_hash
			config_fixture.fixture_template = self.template_code
			config_fixture.engine_version = "1.0.0"
			config_fixture.requested_overall_length_mm = 1000
			config_fixture.manufacturable_overall_length_mm = 995
			config_fixture.runs_count = 1
			config_fixture.total_watts = 15.5
			config_fixture.finish = "Silver"
			config_fixture.lens_appearance = "Clear"
			config_fixture.configured_item = self.item_code
			config_fixture.insert(ignore_permissions=True)

	def tearDown(self):
		"""Clean up test data"""
		# Delete test schedules
		test_schedules = frappe.get_all(
			"ilL-Project-Fixture-Schedule",
			filters={"schedule_name": ["like", "_Test%"]},
			pluck="name"
		)
		for schedule in test_schedules:
			frappe.delete_doc("ilL-Project-Fixture-Schedule", schedule, force=True)

		# Delete test sales orders
		test_orders = frappe.get_all(
			"Sales Order",
			filters={"customer": self.customer_name},
			pluck="name"
		)
		for order in test_orders:
			frappe.delete_doc("Sales Order", order, force=True)

	def test_create_sales_order_basic(self):
		"""Test basic Sales Order creation from fixture schedule"""
		# Create a schedule with ILLUMENATE lines
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Basic"
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 2,
			"location": "Office A",
			"notes": "Install above desk",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()

		# Verify Sales Order was created
		self.assertIsNotNone(so_name)
		so = frappe.get_doc("Sales Order", so_name)

		# Verify customer
		self.assertEqual(so.customer, self.customer_name)

		# Verify SO items
		self.assertEqual(len(so.items), 1)
		so_item = so.items[0]

		# Verify item code
		self.assertEqual(so_item.item_code, self.item_code)

		# Verify qty
		self.assertEqual(so_item.qty, 2)

		# Verify custom fields
		self.assertEqual(so_item.ill_configured_fixture, self.config_hash)
		self.assertEqual(so_item.ill_template_code, self.template_code)
		self.assertEqual(so_item.ill_requested_length_mm, 1000)
		self.assertEqual(so_item.ill_mfg_length_mm, 995)
		self.assertEqual(so_item.ill_runs_count, 1)
		self.assertEqual(so_item.ill_total_watts, 15.5)
		self.assertEqual(so_item.ill_finish, "Silver")
		self.assertEqual(so_item.ill_lens, "Clear")
		self.assertEqual(so_item.ill_engine_version, "1.0.0")

		# Verify schedule status was updated
		schedule.reload()
		self.assertEqual(schedule.status, "ORDERED")

	def test_create_sales_order_filters_illumenate_only(self):
		"""Test that only ILLUMENATE lines are included in the Sales Order"""
		# Create a schedule with mixed lines
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Mixed"
		schedule.customer = self.customer_name
		schedule.status = "READY"

		# ILLUMENATE line
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})

		# OTHER line (should be excluded)
		schedule.append("lines", {
			"line_id": "L2",
			"qty": 3,
			"manufacturer_type": "OTHER",
			"manufacturer_name": "Other Mfr",
			"model_number": "XYZ-123",
		})

		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()

		# Verify only ILLUMENATE line is included
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual(len(so.items), 1)
		self.assertEqual(so.items[0].ill_configured_fixture, self.config_hash)

	def test_create_sales_order_no_customer_throws(self):
		"""Test that missing customer throws an error"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule No Customer"
		schedule.customer = None
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.insert(ignore_permissions=True)

		# Attempt to create Sales Order - should throw
		with self.assertRaises(frappe.exceptions.ValidationError):
			schedule.create_sales_order()

	def test_create_sales_order_no_illumenate_lines_throws(self):
		"""Test that schedule with no ILLUMENATE lines throws an error"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule No ILL Lines"
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"manufacturer_type": "OTHER",
			"manufacturer_name": "Other Mfr",
		})
		schedule.insert(ignore_permissions=True)

		# Attempt to create Sales Order - should throw
		with self.assertRaises(frappe.exceptions.ValidationError):
			schedule.create_sales_order()

	def test_create_sales_order_multiple_lines(self):
		"""Test Sales Order creation with multiple ILLUMENATE lines"""
		# Create another configured fixture
		config_hash_2 = "_test_config_hash_22222222"
		if not frappe.db.exists("ilL-Configured-Fixture", config_hash_2):
			config_fixture = frappe.new_doc("ilL-Configured-Fixture")
			config_fixture.config_hash = config_hash_2
			config_fixture.fixture_template = self.template_code
			config_fixture.engine_version = "1.0.0"
			config_fixture.requested_overall_length_mm = 2000
			config_fixture.manufacturable_overall_length_mm = 1995
			config_fixture.runs_count = 2
			config_fixture.total_watts = 31.0
			config_fixture.finish = "Black"
			config_fixture.lens_appearance = "Frosted"
			config_fixture.configured_item = self.item_code
			config_fixture.insert(ignore_permissions=True)

		# Create schedule with multiple ILLUMENATE lines
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Multi"
		schedule.customer = self.customer_name
		schedule.status = "READY"

		schedule.append("lines", {
			"line_id": "L1",
			"qty": 2,
			"location": "Room A",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.append("lines", {
			"line_id": "L2",
			"qty": 4,
			"location": "Room B",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": config_hash_2,
		})

		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()

		# Verify SO has both items
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual(len(so.items), 2)

		# Verify first item
		self.assertEqual(so.items[0].qty, 2)
		self.assertEqual(so.items[0].ill_configured_fixture, self.config_hash)
		self.assertEqual(so.items[0].ill_mfg_length_mm, 995)

		# Verify second item
		self.assertEqual(so.items[1].qty, 4)
		self.assertEqual(so.items[1].ill_configured_fixture, config_hash_2)
		self.assertEqual(so.items[1].ill_mfg_length_mm, 1995)

		# Clean up
		frappe.delete_doc("ilL-Configured-Fixture", config_hash_2, force=True)

	def test_create_sales_order_description_includes_details(self):
		"""Test that SO item description includes location and notes"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Description"
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"location": "Reception Desk",
			"notes": "Under cabinet mount",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()
		so = frappe.get_doc("Sales Order", so_name)

		# Verify description contains location and notes
		description = so.items[0].description
		self.assertIn("Reception Desk", description)
		self.assertIn("Under cabinet mount", description)
		self.assertIn(self.template_code, description)
