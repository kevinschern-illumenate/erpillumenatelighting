import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


def dependencies(*capabilities):
	conversation = types.ModuleType(ROOT + ".portal.conversations")
	conversation._pagination = lambda page, size: (int(page), int(size))
	staff = types.ModuleType(ROOT + ".portal.staff")
	staff.allowed = MagicMock(side_effect=lambda capability, _user=None: capability in capabilities)
	return {conversation.__name__: conversation, staff.__name__: staff}


class SalesInbox(unittest.TestCase):
	def test_open_unfiled_mail_to_sales_and_mine_reads_desk_assignment(self):
		with load_service(ROOT + ".portal.queues", dependencies("inbox")) as (module, frappe):
			frappe.session.user = "ryan@example.com"
			_label, doctype, filters, _fields = module.query("inbox", "mine", "lead time")
			self.assertEqual(doctype, "Communication")
			self.assertEqual(filters["recipients"], ["like", "%sales@illumenate.lighting%"])
			self.assertEqual(filters["sent_or_received"], "Received")
			self.assertEqual(filters["status"], "Open")
			self.assertEqual(filters["reference_doctype"], ["is", "not set"])
			self.assertEqual(filters["_assign"], ["like", '%"ryan@example.com"%'])
			self.assertEqual(filters["subject"], ["like", "%lead time%"])
			self.assertNotIn("name", filters)

	def test_assignment_list_cannot_answer_unassigned_or_overdue(self):
		with load_service(ROOT + ".portal.queues", dependencies("inbox")) as (module, _frappe):
			for view in ("unassigned", "overdue"):
				with self.assertRaises(ValueError):
					module.query("inbox", view)

	def test_inbox_needs_a_customer_facing_role(self):
		with load_service(ROOT + ".portal.queues", dependencies("operations")) as (module, _frappe):
			with self.assertRaises(PermissionError):
				module.query("inbox")

	def test_every_customer_facing_team_shares_the_inbox(self):
		with load_service(ROOT + ".portal.staff") as (module, _frappe):
			inbox = module.CAPABILITIES["inbox"]
			for team in ("sales", "support", "catalog"):
				self.assertTrue(module.CAPABILITIES[team] <= inbox, team)


class NewCustomers(unittest.TestCase):
	def test_won_deal_customers_without_terms_wait_on_accounts(self):
		with load_service(ROOT + ".portal.queues", dependencies("accounts")) as (module, frappe):
			frappe.get_meta = MagicMock()
			frappe.get_meta.return_value.has_field.return_value = True
			_label, doctype, filters, _fields = module.query("new_customers", search="Acme")
			self.assertEqual(doctype, "Customer")
			self.assertEqual(filters["crm_deal"], ["is", "set"])
			self.assertEqual(filters["payment_terms"], ["is", "not set"])
			self.assertEqual(filters["customer_name"], ["like", "%Acme%"])
			frappe.get_meta.assert_called_with("Customer")

	def test_queue_hidden_until_crm_sync_adds_the_deal_link(self):
		with load_service(ROOT + ".portal.queues", dependencies("accounts")) as (module, frappe):
			frappe.get_meta = MagicMock()
			frappe.get_meta.return_value.has_field.return_value = False
			frappe.get_list = MagicMock(return_value=[Record(total=0)])
			keys = [row["key"] for row in module.summary()["queues"]]
			self.assertIn("accounts", keys)
			self.assertNotIn("new_customers", keys)
			with self.assertRaises(PermissionError):
				module.query("new_customers")


if __name__ == "__main__":
	unittest.main()
