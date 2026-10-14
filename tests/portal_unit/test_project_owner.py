"""REL-5: sales staff name the dealer company that owns a project they create."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service


class ProjectOwner(unittest.TestCase):
	def service(self, allowed=False):
		self.allowed = MagicMock(return_value=allowed)
		context = load_service(
			ROOT + ".portal.project_owner",
			{ROOT + ".portal.staff": types.SimpleNamespace(allowed=self.allowed)},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module, frappe

	def test_sales_capability_or_administrator_may_set_the_owner_company(self):
		module, frappe = self.service(allowed=True)
		frappe.session.user = "sam@illumenate.test"
		self.assertTrue(module.can_set_owner_company())
		self.allowed.assert_called_with("sales", "sam@illumenate.test")
		module, _frappe = self.service(allowed=False)
		self.assertFalse(module.can_set_owner_company("dana@acme.test"))
		self.assertTrue(module.can_set_owner_company("Administrator"))

	def test_owner_company_must_exist_and_have_a_dealer(self):
		module, frappe = self.service()
		with self.assertRaisesRegex(ValueError, "Choose the dealer company"):
			module.validate_owner_company("  ")
		frappe.db.exists.return_value = False
		with self.assertRaisesRegex(ValueError, "does not exist"):
			module.validate_owner_company("Ghost Co")
		frappe.db.exists.return_value = True
		frappe.db.sql.return_value = []
		with self.assertRaisesRegex(ValueError, "no dealer contact"):
			module.validate_owner_company("GC Builders")
		frappe.db.sql.return_value = [(1,)]
		self.assertEqual(module.validate_owner_company(" Acme Lighting "), "Acme Lighting")
		sql, params = frappe.db.sql.call_args.args
		self.assertIn("role.role = 'Dealer'", sql)
		self.assertIn("user.enabled = 1", sql)
		self.assertEqual(params, {"customer": "Acme Lighting"})


if __name__ == "__main__":
	unittest.main()
