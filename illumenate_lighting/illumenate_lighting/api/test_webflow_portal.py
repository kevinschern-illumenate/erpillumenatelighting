# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Webflow Portal API

Tests the project/schedule/line cascading selection endpoints
and dealer-gated pricing endpoint.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock


class TestWebflowPortalGetProjects(FrappeTestCase):
	"""Test cases for get_projects endpoint"""

	def test_get_projects_guest_rejected(self):
		"""Test that guest users are rejected"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_projects

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = get_projects()

		self.assertFalse(result["success"])
		self.assertIn("Authentication required", result["error"])

	def test_get_projects_internal_user_gets_all(self):
		"""Test that internal users get all active projects"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_projects

		mock_projects = [
			MagicMock(
				name="PROJ-001",
				project_name="Project A",
				customer="CUST-001",
				status="ACTIVE",
				location="NYC",
			),
		]

		with patch.object(frappe, "session", MagicMock(user="admin@test.com")):
			with patch(
				"illumenate_lighting.illumenate_lighting.api.webflow_portal._get_user_customer_or_fail",
				return_value=None,
			):
				with patch.object(
					frappe,
					"get_all",
					return_value=mock_projects,
				):
					result = get_projects()

		self.assertTrue(result["success"])
		self.assertIn("projects", result)

	def test_get_projects_portal_user_filtered(self):
		"""Test that portal users get only their customer's projects"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_projects

		with patch.object(frappe, "session", MagicMock(user="portal@test.com")):
			with patch(
				"illumenate_lighting.illumenate_lighting.api.webflow_portal._get_user_customer_or_fail",
				return_value="CUST-001",
			):
				with patch.object(
					frappe,
					"get_all",
					return_value=[],
				) as mock_get_all:
					result = get_projects()

		self.assertTrue(result["success"])
		# Verify the customer filter was applied
		call_args = mock_get_all.call_args
		self.assertEqual(call_args[1]["filters"]["customer"], "CUST-001")


class TestWebflowPortalGetFixtureSchedules(FrappeTestCase):
	"""Test cases for get_fixture_schedules endpoint"""

	def test_get_fixture_schedules_guest_rejected(self):
		"""Test that guest users are rejected"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_fixture_schedules

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = get_fixture_schedules(project="PROJ-001")

		self.assertFalse(result["success"])

	def test_get_fixture_schedules_missing_project(self):
		"""Test error when project is not provided"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_fixture_schedules

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			result = get_fixture_schedules(project="")

		self.assertFalse(result["success"])
		self.assertIn("required", result["error"].lower())

	def test_get_fixture_schedules_ownership_check(self):
		"""Test that ownership is verified"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_fixture_schedules

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			with patch(
				"illumenate_lighting.illumenate_lighting.api.webflow_portal._verify_project_ownership",
				return_value={"success": False, "error": "Permission denied"},
			):
				result = get_fixture_schedules(project="PROJ-001")

		self.assertFalse(result["success"])
		self.assertIn("Permission denied", result["error"])


class TestWebflowPortalGetLineIds(FrappeTestCase):
	"""Test cases for get_line_ids endpoint"""

	def test_get_line_ids_guest_rejected(self):
		"""Test that guest users are rejected"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_line_ids

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = get_line_ids(project="PROJ-001", fixture_schedule="SCHED-001")

		self.assertFalse(result["success"])

	def test_get_line_ids_missing_params(self):
		"""Test error when required params are missing"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_line_ids

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			result = get_line_ids(project="", fixture_schedule="")

		self.assertFalse(result["success"])
		self.assertIn("required", result["error"].lower())


class TestWebflowPortalAddFixture(FrappeTestCase):
	"""Test cases for add_fixture_to_schedule endpoint"""

	def test_add_fixture_guest_rejected(self):
		"""Test that guest users are rejected"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			add_fixture_to_schedule,
		)

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = add_fixture_to_schedule(
				project="PROJ-001",
				fixture_schedule="SCHED-001",
				fixture_part_number="SH01-xxx",
			)

		self.assertFalse(result["success"])

	def test_add_fixture_missing_params(self):
		"""Test error when required params are missing"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			add_fixture_to_schedule,
		)

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			result = add_fixture_to_schedule(
				project="",
				fixture_schedule="",
				fixture_part_number="",
			)

		self.assertFalse(result["success"])
		self.assertIn("required", result["error"].lower())


class TestWebflowPortalGetPricing(FrappeTestCase):
	"""Test cases for get_pricing endpoint"""

	def test_get_pricing_guest_rejected(self):
		"""Test that guest users are rejected"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_pricing

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = get_pricing(item_code="ITEM-001")

		self.assertFalse(result["success"])

	def test_get_pricing_non_dealer_rejected(self):
		"""Test that non-dealer users cannot access pricing"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_pricing

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			with patch(
				"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_dealer_user",
				return_value=False,
			):
				with patch(
					"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_internal_user",
					return_value=False,
				):
					result = get_pricing(item_code="ITEM-001")

		self.assertFalse(result["success"])
		self.assertIn("authorized", result["error"].lower())

	def test_get_pricing_dealer_allowed(self):
		"""Test that dealer users can access pricing"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_pricing

		with patch.object(frappe, "session", MagicMock(user="dealer@test.com")):
			with patch(
				"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_dealer_user",
				return_value=True,
			):
				with patch(
					"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_internal_user",
					return_value=False,
				):
					with patch.object(
						frappe.db,
						"exists",
						return_value=True,
					):
						with patch.object(
							frappe.db,
							"get_single_value",
							return_value="Standard Selling",
						):
							with patch.object(
								frappe.db,
								"get_value",
								return_value={"price_list_rate": 100.0, "currency": "USD"},
							):
								result = get_pricing(item_code="ITEM-001")

		self.assertTrue(result["success"])
		self.assertEqual(result["price"], 100.0)
		self.assertEqual(result["currency"], "USD")

	def test_get_pricing_missing_item_code(self):
		"""Test error when item_code is not provided"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_pricing

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			result = get_pricing(item_code="")

		self.assertFalse(result["success"])
		self.assertIn("required", result["error"].lower())


class TestWebflowPortalGetScheduleKitStock(FrappeTestCase):
	"""Test cases for get_schedule_kit_stock endpoint"""

	def test_guest_rejected(self):
		"""Test that guest users are rejected"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_schedule_kit_stock

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = get_schedule_kit_stock(schedule_name="SCHED-001")

		self.assertFalse(result["success"])
		self.assertIn("Authentication", result["error"])

	def test_missing_schedule_name(self):
		"""Test error when schedule_name is empty"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_schedule_kit_stock

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			result = get_schedule_kit_stock(schedule_name="")

		self.assertFalse(result["success"])
		self.assertIn("required", result["error"].lower())

	def test_nonexistent_schedule(self):
		"""Test error when schedule does not exist"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import get_schedule_kit_stock

		with patch.object(frappe, "session", MagicMock(user="user@test.com")):
			with patch.object(frappe.db, "exists", return_value=False):
				result = get_schedule_kit_stock(schedule_name="NONEXISTENT")

		self.assertFalse(result["success"])
		self.assertIn("not found", result["error"].lower())


class TestResolveKitStockForLine(FrappeTestCase):
	"""Test cases for _resolve_kit_stock_for_line helper"""

	def test_unconfigured_line_returns_none(self):
		"""Unconfigured kit line (no variant_selections) returns None"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			_resolve_kit_stock_for_line,
		)

		line = MagicMock()
		line.variant_selections = None
		result = _resolve_kit_stock_for_line(line, "user@test.com")
		self.assertIsNone(result)

	def test_invalid_json_returns_none(self):
		"""Line with invalid JSON in variant_selections returns None"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			_resolve_kit_stock_for_line,
		)

		line = MagicMock()
		line.variant_selections = "NOT VALID JSON{{"
		result = _resolve_kit_stock_for_line(line, "user@test.com")
		self.assertIsNone(result)

	def test_missing_kit_template_returns_none(self):
		"""Line with no kit_template in selections returns None"""
		import json
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			_resolve_kit_stock_for_line,
		)

		line = MagicMock()
		line.variant_selections = json.dumps({"selections": {}})
		line.kit_template = None
		result = _resolve_kit_stock_for_line(line, "user@test.com")
		self.assertIsNone(result)


class TestApplyStockVisibility(FrappeTestCase):
	"""Test cases for _apply_stock_visibility helper"""

	def test_dealer_sees_full_quantities(self):
		"""Dealer users see full stock quantities"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			_apply_stock_visibility,
		)

		stock_result = {
			"success": True,
			"components": [
				{
					"component": "Profile",
					"item_code": "ITEM-001",
					"qty_per_kit": 1,
					"stock_qty": 10.0,
					"kits_fulfillable": 10,
					"in_stock": True,
					"lead_time_class": "in-stock",
				}
			],
			"total_kits_fulfillable": 10,
			"limiting_component": None,
		}

		with patch(
			"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_dealer_user",
			return_value=True,
		):
			with patch(
				"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_internal_user",
				return_value=False,
			):
				result = _apply_stock_visibility(stock_result, "dealer@test.com")

		# Dealer sees full data including stock_qty
		self.assertIn("stock_qty", result["components"][0])
		self.assertEqual(result["components"][0]["stock_qty"], 10.0)

	def test_non_privileged_sees_only_boolean(self):
		"""Non-dealer non-internal users see only boolean in_stock per component"""
		from illumenate_lighting.illumenate_lighting.api.webflow_portal import (
			_apply_stock_visibility,
		)

		stock_result = {
			"success": True,
			"components": [
				{
					"component": "Profile",
					"item_code": "ITEM-001",
					"qty_per_kit": 1,
					"stock_qty": 10.0,
					"kits_fulfillable": 10,
					"in_stock": True,
					"lead_time_class": "in-stock",
				}
			],
			"total_kits_fulfillable": 10,
			"limiting_component": None,
		}

		with patch(
			"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_dealer_user",
			return_value=False,
		):
			with patch(
				"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_internal_user",
				return_value=False,
			):
				result = _apply_stock_visibility(stock_result, "portal@test.com")

		# Non-privileged user should NOT see stock_qty or qty_per_kit or kits_fulfillable
		self.assertNotIn("stock_qty", result["components"][0])
		self.assertNotIn("qty_per_kit", result["components"][0])
		self.assertNotIn("kits_fulfillable", result["components"][0])
		# Should see in_stock boolean and lead_time_class
		self.assertIn("in_stock", result["components"][0])
		self.assertIn("lead_time_class", result["components"][0])
		self.assertTrue(result["components"][0]["in_stock"])
