# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api.mounting_accessory import (
	methods_without_accessory,
	needs_accessory,
)


class TestilLAttributeMountingMethod(FrappeTestCase):
	def _method(self, label, no_accessory):
		if not frappe.db.exists("ilL-Attribute-Mounting Method", label):
			frappe.get_doc(
				{"doctype": "ilL-Attribute-Mounting Method", "label": label, "code": label[:6].upper()}
			).insert(ignore_permissions=True)
		frappe.db.set_value("ilL-Attribute-Mounting Method", label, "no_accessory_required", no_accessory)
		return label

	def test_flagged_method_needs_no_accessory(self):
		drywall = self._method("_Test Drywall", 1)
		clips = self._method("_Test Clips", 0)
		self.assertFalse(needs_accessory(drywall))
		self.assertTrue(needs_accessory(clips))
		self.assertEqual(methods_without_accessory([drywall, clips]), {drywall})

	def test_empty_lookup(self):
		self.assertEqual(methods_without_accessory([]), set())
		self.assertTrue(needs_accessory(None))
