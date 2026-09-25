# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Unit tests for the portal status vocabulary and schedule-level stock demand.

Pure-function tests (no fixtures needed) covering:
- ERP facts -> customer-facing order status mapping
- schedule status transitions per persona
- qty-scaled, shared-demand stock allocation
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import pricing_utils
from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule import (
	ill_project_fixture_schedule as schedule_module,
)
from illumenate_lighting.illumenate_lighting.portal import status


class TestOrderPortalStatus(FrappeTestCase):
	def test_draft_is_order_request(self):
		self.assertEqual(status.derive_order_portal_status(0, "Draft"), "order_request")

	def test_cancelled(self):
		self.assertEqual(status.derive_order_portal_status(2, "Cancelled"), "cancelled")
		self.assertEqual(status.derive_order_portal_status(1, "Cancelled"), "cancelled")

	def test_submitted_without_work_orders_is_approved_not_in_production(self):
		self.assertEqual(
			status.derive_order_portal_status(1, "To Deliver and Bill"), "approved"
		)

	def test_production_derived_from_work_order_quantities(self):
		wos = [{"status": "In Process", "qty": 10, "produced_qty": 4}]
		self.assertEqual(
			status.derive_order_portal_status(1, "To Deliver and Bill", work_orders=wos),
			"in_production",
		)
		wos = [{"status": "Completed", "qty": 10, "produced_qty": 10}]
		self.assertEqual(
			status.derive_order_portal_status(1, "To Deliver and Bill", work_orders=wos),
			"production_complete",
		)

	def test_delivery_is_not_production_completion(self):
		# Partial delivery: shipped state wins, but a 'To Bill' order is not
		# labelled "Ready to Ship" anymore.
		self.assertEqual(
			status.derive_order_portal_status(1, "To Bill", per_delivered=50), "partially_shipped"
		)
		self.assertEqual(
			status.derive_order_portal_status(1, "To Bill", per_delivered=100), "shipped"
		)
		self.assertEqual(
			status.derive_order_portal_status(1, "Completed", per_delivered=100, per_billed=100),
			"completed",
		)

	def test_every_key_has_metadata(self):
		for key in status.ORDER_PORTAL_STATUSES:
			self.assertTrue(status.order_status_label(key))
			self.assertTrue(status.order_status_class(key))

	def test_schedule_statuses_have_vocabulary(self):
		for s in schedule_module.SCHEDULE_STATUSES:
			self.assertIn(s, status.SCHEDULE_STATUS_META, s)


class TestScheduleTransitions(FrappeTestCase):
	def _transitions(self, current, internal=False, dealer=False):
		with patch.object(schedule_module, "_is_internal_user", return_value=internal), patch.object(
			schedule_module, "_is_dealer_user", return_value=dealer
		):
			return schedule_module.allowed_portal_transitions(current, "someone@example.com")

	def test_collaborator_transitions(self):
		self.assertEqual(self._transitions("DRAFT"), ["READY"])
		self.assertEqual(self._transitions("READY"), ["DRAFT"])
		self.assertEqual(self._transitions("QUOTED"), ["DRAFT", "READY"])
		self.assertEqual(self._transitions("ISSUE"), [])

	def test_dealer_cannot_issue_offer_or_recover_issue(self):
		self.assertEqual(self._transitions("READY", dealer=True), ["DRAFT"])
		self.assertEqual(self._transitions("ISSUE", dealer=True), [])

	def test_internal_can_recover_issue(self):
		self.assertEqual(self._transitions("ISSUE", internal=True), ["DRAFT", "READY"])

	def test_system_states_are_not_portal_settable(self):
		for state in ("ORDER_REQUESTED", "ORDERED", "CLOSED"):
			self.assertEqual(self._transitions(state, internal=True), [])
			self.assertNotIn(state, schedule_module.PORTAL_SETTABLE_STATUSES)


class TestScheduleStockDemand(FrappeTestCase):
	def _run(self, specs, stock, privileged=True):
		with patch.object(pricing_utils, "_bulk_stock_query", return_value=dict(stock)), patch.object(
			pricing_utils, "_is_privileged_user", return_value=privileged
		), patch.object(pricing_utils, "_eligible_warehouses", return_value=["ilL-Stores - T"]):
			return pricing_utils.batch_stock_for_schedule_lines(specs)

	def test_line_quantity_scales_demand(self):
		specs = [{"key": 1, "qty": 10, "components": [("Profile", "PROF", 1, "Nos")]}]
		result = self._run(specs, {"PROF": 1})
		self.assertFalse(result["lines"][1]["all_in_stock"])
		self.assertEqual(result["lines"][1]["items"][0]["qty_required"], 10)
		self.assertEqual(result["shortages"][0]["shortage"], 9)

	def test_shared_component_is_allocated_in_line_order(self):
		specs = [
			{"key": 1, "qty": 1, "components": [("Profile", "PROF", 1, "Nos")]},
			{"key": 2, "qty": 1, "components": [("Profile", "PROF", 1, "Nos")]},
		]
		result = self._run(specs, {"PROF": 1})
		self.assertTrue(result["lines"][1]["all_in_stock"])
		self.assertFalse(result["lines"][2]["all_in_stock"])
		self.assertEqual(len(result["shortages"]), 1)

	def test_missing_configuration_is_unknown_not_false_certainty(self):
		result = self._run([{"key": 1, "qty": 1, "components": []}], {})
		self.assertEqual(result["lines"][1]["availability"], "unknown")

	def test_unprivileged_users_only_see_booleans(self):
		specs = [{"key": 1, "qty": 2, "components": [("Profile", "PROF", 1, "Nos")]}]
		result = self._run(specs, {"PROF": 5}, privileged=False)
		entry = result["lines"][1]["items"][0]
		self.assertTrue(entry["is_sufficient"])
		self.assertNotIn("qty_available", entry)
		self.assertNotIn("shortage", result["shortages"][0] if result["shortages"] else {})

	def test_stock_api_requires_login_and_caps_input(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				pricing_utils.get_bom_stock_for_items_api("[]")
		finally:
			frappe.set_user("Administrator")

		too_many = [{"item_code": f"X{i}", "qty": 1} for i in range(pricing_utils.MAX_STOCK_API_ITEMS + 1)]
		result = pricing_utils.get_bom_stock_for_items_api(frappe.as_json(too_many))
		self.assertIn("error", result)
