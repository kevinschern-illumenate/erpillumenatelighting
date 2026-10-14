"""REL-9: the Customer list is the user's own company, its users' Customers and readable projects'.

DESK-9: a project's architect, designer and contractor are project parties, so they add nothing.
"""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class AllowedCustomers(unittest.TestCase):
	def service(self, staff=False, user_customer="ACME"):
		owner = types.SimpleNamespace(can_set_owner_company=MagicMock(return_value=staff))
		project = types.SimpleNamespace(_get_user_customer=MagicMock(return_value=user_customer))
		context = load_service(
			ROOT + ".portal.allowed_customers",
			{
				ROOT + ".portal.project_owner": owner,
				ROOT + ".doctype.ill_project.ill_project": project,
			},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_list = MagicMock(return_value=[])
		frappe.db.sql_list = MagicMock(return_value=[])
		return module, frappe

	def test_sales_staff_see_every_customer(self):
		module, frappe = self.service(staff=True)
		frappe.get_all.return_value = [
			Record(name="C-1", customer_name=None),
			Record(name="C-2", customer_name="Bee"),
		]
		result = module.allowed_customers("sam@illumenate.test")
		self.assertEqual(
			result["allowed_customers"], [{"value": "C-1", "label": "C-1"}, {"value": "C-2", "label": "Bee"}]
		)
		self.assertIsNone(result["user_customer"])

	def test_no_company_means_no_choices(self):
		module, _frappe = self.service(user_customer=None)
		self.assertEqual(module.allowed_customers("x@y.test")["allowed_customers"], [])

	def test_own_company_its_users_customers_and_readable_projects_in_one_lookup(self):
		module, frappe = self.service()
		frappe.db.sql_list.return_value = ["dana@acme.test"]
		frappe.get_list.return_value = [Record(customer="HOTEL")]
		labels = {"ACME": "Acme", "MINE": "Mine Co", "HOTEL": "Hotel", "ARCH": "Arch", "GC": "GC Ltd"}

		def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
			if pluck:
				self.assertEqual(filters, {"owner": ["in", ["dana@acme.test"]]})
				return ["MINE"]
			return [Record(name=name, customer_name=labels[name]) for name in filters["name"][1]]

		frappe.get_all.side_effect = get_all
		result = module.allowed_customers("dana@acme.test")
		self.assertEqual(
			[option["value"] for option in result["allowed_customers"]],
			["ACME", "HOTEL", "MINE"],
		)
		self.assertEqual(frappe.get_list.call_args.kwargs["user"], "dana@acme.test")
		self.assertEqual(frappe.get_list.call_args.kwargs["fields"], ["customer"], "team fields are parties")
		self.assertEqual(frappe.db.get_value.call_count, 0, "no per-customer lookups")
		sql = frappe.db.sql_list.call_args.args[0]
		self.assertNotIn("IN (", sql, "no transitive shared-contact clause")


if __name__ == "__main__":
	unittest.main()
