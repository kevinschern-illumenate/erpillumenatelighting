"""Dealer → Customer resolution through Contacts (recovery plan §7.3)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

USER = "dealer@example.com"


def _resolve(contacts, links):
	"""Run _get_user_customer against Contact rows and (contact, customer) links."""
	document = types.ModuleType("frappe.model.document")
	document.Document = type("Document", (), {})
	extras = {"frappe.model": types.ModuleType("frappe.model"), "frappe.model.document": document}
	with load_service(ROOT + ".doctype.ill_project.ill_project", extras) as (module, frappe):
		frappe.get_meta = MagicMock(return_value=MagicMock(has_field=MagicMock(return_value=True)))

		def get_all(doctype, filters=None, or_filters=None, fields=None, **kwargs):
			if doctype == "Contact":
				return [Record(row) for row in contacts]
			parents = set(filters["parent"][1])
			return [Record(parent=parent, link_name=name) for parent, name in links if parent in parents]

		frappe.get_all = MagicMock(side_effect=get_all)
		return module._get_user_customer(USER)


def contact(name, user=None, contact_only=0):
	return {"name": name, "user": user, "ill_portal_contact_only": contact_only}


class CustomerResolution(unittest.TestCase):
	def test_user_linked_contact_wins_over_email_only_match(self):
		# Before §7.3 this resolved to None and the dealer lost their projects.
		contacts = [contact("C-USER", USER), contact("C-EMAIL")]
		links = [("C-USER", "Dealer Co"), ("C-EMAIL", "Old Co")]
		self.assertEqual(_resolve(contacts, links), "Dealer Co")

	def test_email_only_match_is_used_when_no_user_linked_contact_has_a_customer(self):
		self.assertEqual(_resolve([contact("C-EMAIL")], [("C-EMAIL", "Dealer Co")]), "Dealer Co")
		contacts = [contact("C-USER", USER), contact("C-EMAIL")]
		self.assertEqual(_resolve(contacts, [("C-EMAIL", "Dealer Co")]), "Dealer Co")

	def test_one_customer_across_several_contacts_resolves(self):
		contacts = [contact("C-1", USER), contact("C-2", USER)]
		links = [("C-1", "Dealer Co"), ("C-2", "Dealer Co")]
		self.assertEqual(_resolve(contacts, links), "Dealer Co")

	def test_genuine_ambiguity_resolves_to_none(self):
		contacts = [contact("C-1", USER), contact("C-2", USER)]
		self.assertIsNone(_resolve(contacts, [("C-1", "Dealer Co"), ("C-2", "Other Co")]))
		contacts = [contact("C-1"), contact("C-2")]
		self.assertIsNone(_resolve(contacts, [("C-1", "Dealer Co"), ("C-2", "Other Co")]))

	def test_contact_only_and_other_users_contacts_never_grant_membership(self):
		contacts = [contact("C-ONLY", contact_only=1), contact("C-OTHER", "someone@example.com")]
		links = [("C-ONLY", "Dealer Co"), ("C-OTHER", "Dealer Co")]
		self.assertIsNone(_resolve(contacts, links))

	def test_no_contacts_resolves_to_none(self):
		self.assertIsNone(_resolve([], []))


if __name__ == "__main__":
	unittest.main()
