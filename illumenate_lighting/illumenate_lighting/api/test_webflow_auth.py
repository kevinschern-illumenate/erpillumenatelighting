# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Webflow Authentication API
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock


class TestWebflowAuth(FrappeTestCase):
	"""Test cases for the Webflow authentication API"""

	def test_get_user_context_as_guest(self):
		"""Test get_user_context rejects guest users"""
		from illumenate_lighting.illumenate_lighting.api.webflow_auth import get_user_context

		with patch.object(frappe, "session", MagicMock(user="Guest")):
			result = get_user_context()

		self.assertFalse(result["success"])
		self.assertIn("Authentication required", result["error"])

	def test_get_user_context_authenticated(self):
		"""Test get_user_context returns context for authenticated user"""
		from illumenate_lighting.illumenate_lighting.api.webflow_auth import get_user_context

		# Use Administrator for testing since it always exists
		with patch.object(frappe, "session", MagicMock(user="Administrator")):
			with patch(
				"illumenate_lighting.illumenate_lighting.api.webflow_auth._get_or_generate_api_credentials",
				return_value=("test-api-key", "test-api-secret"),
			):
				result = get_user_context()

		self.assertTrue(result["success"])
		self.assertEqual(result["user"], "Administrator")
		self.assertIn("is_dealer", result)
		self.assertIn("is_internal", result)
		self.assertIn("customer", result)
		self.assertIn("api_key", result)
		self.assertIn("api_secret", result)

	def test_get_user_context_has_full_name(self):
		"""Test get_user_context includes full_name"""
		from illumenate_lighting.illumenate_lighting.api.webflow_auth import get_user_context

		with patch.object(frappe, "session", MagicMock(user="Administrator")):
			with patch(
				"illumenate_lighting.illumenate_lighting.api.webflow_auth._get_or_generate_api_credentials",
				return_value=("key", "secret"),
			):
				result = get_user_context()

		self.assertTrue(result["success"])
		self.assertIn("full_name", result)

	def test_get_user_context_dealer_user(self):
		"""Test get_user_context correctly identifies dealer role"""
		from illumenate_lighting.illumenate_lighting.api.webflow_auth import get_user_context

		with patch.object(frappe, "session", MagicMock(user="dealer@test.com")):
			with patch(
				"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_dealer_user",
				return_value=True,
			):
				with patch(
					"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._is_internal_user",
					return_value=False,
				):
					with patch(
						"illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project._get_user_customer",
						return_value="TEST-CUST-001",
					):
						with patch.object(
							frappe.db, "get_value", return_value="Test Customer"
						):
							with patch(
								"illumenate_lighting.illumenate_lighting.api.webflow_auth._get_or_generate_api_credentials",
								return_value=("key", "secret"),
							):
								with patch.object(
									frappe.utils, "get_fullname", return_value="Dealer User"
								):
									result = get_user_context()

		self.assertTrue(result["success"])
		self.assertTrue(result["is_dealer"])
		self.assertFalse(result["is_internal"])
		self.assertEqual(result["customer"], "TEST-CUST-001")
		self.assertEqual(result["customer_name"], "Test Customer")
