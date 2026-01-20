# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Webflow Integration API
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWebflowIntegration(FrappeTestCase):
	"""Test cases for the webflow integration API"""

	def setUp(self):
		"""Set up test data"""
		# Create a test item
		if not frappe.db.exists("Item", "TEST-ITEM-001"):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": "TEST-ITEM-001",
				"item_name": "Test Product",
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_sales_item": 1,
				"is_stock_item": 1,
				"disabled": 0,
			})
			item.insert(ignore_permissions=True)

	def tearDown(self):
		"""Clean up test data"""
		# Delete test items if they exist
		if frappe.db.exists("Item", "TEST-ITEM-001"):
			frappe.delete_doc("Item", "TEST-ITEM-001", force=1, ignore_permissions=True)

	def test_get_product_detail_with_item_code(self):
		"""Test get_product_detail with item_code parameter"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_product_detail
		
		result = get_product_detail(item_code="TEST-ITEM-001")
		
		self.assertTrue(result["success"])
		self.assertIsNotNone(result["product"])
		self.assertEqual(result["product"]["item_code"], "TEST-ITEM-001")
		self.assertEqual(result["product"]["item_name"], "Test Product")

	def test_get_product_detail_with_sku(self):
		"""Test get_product_detail with sku parameter"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_product_detail
		
		result = get_product_detail(sku="TEST-ITEM-001")
		
		self.assertTrue(result["success"])
		self.assertIsNotNone(result["product"])
		self.assertEqual(result["product"]["item_code"], "TEST-ITEM-001")

	def test_get_product_detail_no_params(self):
		"""Test get_product_detail with no parameters returns error"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_product_detail
		
		result = get_product_detail()
		
		self.assertFalse(result["success"])
		self.assertIn("required", result["error"].lower())

	def test_get_product_detail_not_found(self):
		"""Test get_product_detail with non-existent item"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_product_detail
		
		result = get_product_detail(item_code="NON-EXISTENT-ITEM")
		
		self.assertFalse(result["success"])
		self.assertIn("not found", result["error"].lower())

	def test_get_product_detail_disabled_item(self):
		"""Test get_product_detail with disabled item"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_product_detail
		
		# Create and disable a test item
		if not frappe.db.exists("Item", "TEST-DISABLED-ITEM"):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": "TEST-DISABLED-ITEM",
				"item_name": "Test Disabled Product",
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_sales_item": 1,
				"disabled": 1,
			})
			item.insert(ignore_permissions=True)
		
		result = get_product_detail(item_code="TEST-DISABLED-ITEM")
		
		self.assertFalse(result["success"])
		self.assertIn("disabled", result["error"].lower())
		
		# Clean up
		if frappe.db.exists("Item", "TEST-DISABLED-ITEM"):
			frappe.delete_doc("Item", "TEST-DISABLED-ITEM", force=1, ignore_permissions=True)

	def test_get_related_products(self):
		"""Test get_related_products"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_related_products
		
		# Create another test item in the same group
		if not frappe.db.exists("Item", "TEST-ITEM-002"):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": "TEST-ITEM-002",
				"item_name": "Test Product 2",
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_sales_item": 1,
				"disabled": 0,
			})
			item.insert(ignore_permissions=True)
		
		result = get_related_products(item_code="TEST-ITEM-001", limit=10)
		
		self.assertTrue(result["success"])
		self.assertIsInstance(result["products"], list)
		
		# Clean up
		if frappe.db.exists("Item", "TEST-ITEM-002"):
			frappe.delete_doc("Item", "TEST-ITEM-002", force=1, ignore_permissions=True)

	def test_get_active_products_for_webflow(self):
		"""Test get_active_products_for_webflow"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_active_products_for_webflow
		
		result = get_active_products_for_webflow()
		
		self.assertTrue(result["success"])
		self.assertIsInstance(result["products"], list)
		self.assertIsInstance(result["count"], int)

	def test_get_active_products_for_webflow_with_filters(self):
		"""Test get_active_products_for_webflow with filters"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_active_products_for_webflow
		
		result = get_active_products_for_webflow(item_group="Products")
		
		self.assertTrue(result["success"])
		self.assertIsInstance(result["products"], list)

	def test_get_products_by_codes(self):
		"""Test get_products_by_codes"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_products_by_codes
		
		result = get_products_by_codes(item_codes=["TEST-ITEM-001"])
		
		self.assertTrue(result["success"])
		self.assertIsInstance(result["products"], list)
		self.assertEqual(result["count"], 1)
		
		if result["products"]:
			self.assertEqual(result["products"][0]["item_code"], "TEST-ITEM-001")

	def test_get_products_by_codes_with_json_string(self):
		"""Test get_products_by_codes with JSON string input"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_products_by_codes
		
		result = get_products_by_codes(item_codes='["TEST-ITEM-001"]')
		
		self.assertTrue(result["success"])
		self.assertIsInstance(result["products"], list)

	def test_get_products_by_codes_invalid_input(self):
		"""Test get_products_by_codes with invalid input"""
		from illumenate_lighting.illumenate_lighting.api.webflow_integration import get_products_by_codes
		
		result = get_products_by_codes(item_codes="invalid")
		
		self.assertFalse(result["success"])
		self.assertIn("error", result)
