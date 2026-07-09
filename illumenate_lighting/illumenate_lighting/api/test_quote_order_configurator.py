# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Integration tests for the quote/order configurator LED Sheet path.

Guards the regression where a configured LED Sheet was added to a
Quotation/Sales Order row without an ``Item Price`` and without an MSRP in the
artifact, so the row priced to zero.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from illumenate_lighting.illumenate_lighting.api import quote_order_configurator as qoc
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
	DEFAULT_SELLING_PRICE_LIST,
)


class TestQuoteOrderConfiguratorSheetPricing(FrappeTestCase):
	"""LED Sheet artifacts must carry a real price."""

	def setUp(self):
		self.sheet_msrp = 137.5
		self.sheet = frappe.get_doc({
			"doctype": "ilL-Configured-LED-Sheet",
			"part_number": "TEST-CLS-PRICING",
			"selected_finish": "White",
			"total_groups": 1,
			"total_system_watts": 20,
			"sheets_needed": 2,
			"msrp": self.sheet_msrp,
		}).insert(ignore_permissions=True)

		# Clean up any pre-existing Item/Item Price from a prior failed run so
		# the assertions below reflect this test's artifact generation.
		self.item_code = self.sheet.part_number
		frappe.db.delete("Item Price", {"item_code": self.item_code})
		if frappe.db.exists("Item", self.item_code):
			frappe.delete_doc("Item", self.item_code, force=True, ignore_permissions=True)

	def _ensure_artifact(self):
		# The BOM build needs real component items; it is exercised elsewhere.
		# Here we isolate the pricing behaviour of the artifact path.
		with patch(
			"illumenate_lighting.illumenate_lighting.api.led_sheet_bom.create_or_get_led_sheet_bom",
			return_value={"bom_name": "TEST-CLS-BOM", "messages": []},
		):
			return qoc._ensure_configured_artifacts(
				qoc.PRODUCT_TYPE_SHEET,
				configured_fixture=None,
				configured_tape_neon=None,
				configured_led_sheet=self.sheet.name,
			)

	def test_artifact_carries_sheet_msrp(self):
		artifact = self._ensure_artifact()

		self.assertEqual(artifact["item_code"], self.item_code)
		self.assertEqual(flt(artifact["msrp_unit"]), self.sheet_msrp)
		self.assertEqual(flt(artifact["total_msrp"]), self.sheet_msrp)
		# The fallback resolver used by _apply_pricing_to_row must find it.
		self.assertEqual(flt(qoc._artifact_msrp(artifact)), self.sheet_msrp)

	def test_item_price_created_at_msrp(self):
		self._ensure_artifact()

		self.assertTrue(
			frappe.db.exists(
				"Item Price",
				{
					"item_code": self.item_code,
					"price_list": DEFAULT_SELLING_PRICE_LIST,
					"selling": 1,
				},
			)
		)
		self.assertEqual(
			flt(qoc._get_selling_rate(self.item_code)), self.sheet_msrp
		)
