"""FLOW-7: Dealers see their company's support tickets; other members see only their own."""

import re
import sqlite3
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

# user -> (company, is_dealer)
PEOPLE = {
	"dana@acme.test": ("ACME", True),
	"pat@acme.test": ("ACME", False),
	"sam@acme.test": ("ACME", False),
	"olga@other.test": ("OTHER", True),
	"designer@studio.test": (None, False),
}
CONTACT_LINKS = [("C-DANA", "dana@acme.test", "ACME"), ("C-PAT", "pat@acme.test", "ACME"), ("C-SAM", "sam@acme.test", "ACME"), ("C-OLGA", "olga@other.test", "OTHER")]
ORDERS = {"SO-ACME": "ACME", "SO-OTHER": "OTHER"}
PROJECTS = {"P-ACME": "ACME", "P-OTHER": "OTHER"}
TICKETS = [
	# name, raised_by, order, project
	("ISS-DANA", "dana@acme.test", None, None),
	("ISS-PAT", "pat@acme.test", None, None),
	("ISS-SAM-ORDER", "sam@acme.test", "SO-ACME", None),
	("ISS-DESIGNER-PROJECT", "designer@studio.test", None, "P-ACME"),
	("ISS-DESIGNER-ORDER", "designer@studio.test", "SO-ACME", None),
	("ISS-OLGA", "olga@other.test", None, None),
	("ISS-OLGA-ORDER", "olga@other.test", "SO-OTHER", None),
	("ISS-PAT-FOREIGN-ORDER", "pat@acme.test", "SO-OTHER", None),
	("ISS-DESIGNER-OTHER", "designer@studio.test", None, "P-OTHER"),
]


def database():
	db = sqlite3.connect(":memory:")
	db.row_factory = sqlite3.Row
	db.execute("create table `tabIssue` (name, subject, status, creation, ill_next_action_by, raised_by, ill_portal_order, ill_project)")
	db.execute("create table `tabSales Order` (name, customer)")
	db.execute("create table `tabilL-Project` (name, owner_customer)")
	for index, (name, raised_by, order, project) in enumerate(TICKETS):
		db.execute(
			"insert into `tabIssue` values (?, ?, 'Open', ?, 'Staff', ?, ?, ?)",
			(name, "About " + name, f"2026-10-{index + 1:02d}", raised_by, order, project),
		)
	db.executemany("insert into `tabSales Order` values (?, ?)", ORDERS.items())
	db.executemany("insert into `tabilL-Project` values (?, ?)", PROJECTS.items())
	return db


def run_sql(db, query, params=None, as_dict=False):
	"""Run a MariaDB-style ``%(name)s`` query on sqlite, expanding tuple parameters."""
	values = []

	def bind(match):
		value = (params or {})[match.group(1)]
		if isinstance(value, tuple):
			values.extend(value)
			return "(" + ", ".join("?" for _ in value) + ")"
		values.append(value)
		return "?"

	rows = db.execute(re.sub(r"%\((\w+)\)s", bind, query), values).fetchall()
	return [Record(dict(row)) for row in rows] if as_dict else [tuple(row) for row in rows]


class CompanySupport(unittest.TestCase):
	def setUp(self):
		def actor(user=None):
			company, dealer = PEOPLE.get(user, (None, False))
			return types.SimpleNamespace(user=user, is_internal=False, is_dealer=dealer, customer=company)

		self.accessible_order = MagicMock(
			side_effect=lambda order, user: ORDERS.get(order) == PEOPLE[user][0] and PEOPLE[user][1]
		)
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(get_actor=actor),
			ROOT + ".portal.conversations": types.SimpleNamespace(
				_pagination=lambda page, size: (int(page), int(size)), is_staff=lambda doc, user=None: False
			),
			ROOT + ".doctype.ill_project.ill_project": types.SimpleNamespace(
				_get_user_customer=lambda user: PEOPLE.get(user, (None, False))[0]
			),
			ROOT + ".portal.orders": types.SimpleNamespace(load_accessible_sales_order=self.accessible_order),
		}
		context = load_service(ROOT + ".portal.support", deps)
		self.support, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.db = database()
		frappe.db.sql.side_effect = lambda query, params=None, as_dict=False: run_sql(self.db, query, params, as_dict)
		frappe.db.get_value.side_effect = self.get_value
		frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda field: True)

		def get_all(doctype, filters=None, fields=None, pluck=None, as_list=False, **kwargs):
			if doctype == "Dynamic Link":
				return [contact for contact, _user, company in CONTACT_LINKS if company == filters["link_name"]]
			if doctype == "Contact":
				names = set(filters["name"][1])
				return [Record(user=user, email_id=user) for contact, user, _company in CONTACT_LINKS if contact in names]
			if doctype == "User":
				return [(user, user.split("@")[0].title()) for user in filters["name"][1]]
			raise AssertionError(doctype)

		frappe.get_all = get_all
		self.frappe = frappe

	def get_value(self, doctype, name, field=None, *args, **kwargs):
		if doctype == "User":
			return 1
		if doctype == "Sales Order":
			return ORDERS.get(name)
		if doctype == "ilL-Project":
			return PROJECTS.get(name)
		raise AssertionError(doctype)

	def visible(self, user):
		self.frappe.session = Record(user=user)
		page = self.support.list_tickets(page=1, page_size=50)
		names = {row.name for row in page["tickets"]}
		self.assertEqual(page["total"], len(names))
		readable = {name for name, *_rest in TICKETS if self.support.can_read(self.ticket(name), user)}
		self.assertEqual(names, readable, "the list and the detail page must agree")
		return names, page

	def ticket(self, name):
		_name, raised_by, order, project = next(row for row in TICKETS if row[0] == name)
		return Record(doctype="Issue", name=name, raised_by=raised_by, ill_portal_order=order, ill_project=project)

	def test_dealer_sees_colleagues_tickets_and_tickets_about_company_orders(self):
		names, page = self.visible("dana@acme.test")
		self.assertEqual(
			names,
			{"ISS-DANA", "ISS-PAT", "ISS-SAM-ORDER", "ISS-DESIGNER-PROJECT", "ISS-DESIGNER-ORDER"},
		)
		self.assertTrue(page["company"])
		raisers = {row.name: (row.raised_by_me, row.raised_by_name) for row in page["tickets"]}
		self.assertEqual(raisers["ISS-DANA"], (True, None))
		self.assertEqual(raisers["ISS-PAT"], (False, "Pat"))

	def test_non_dealer_member_sees_only_their_own(self):
		names, page = self.visible("pat@acme.test")
		self.assertEqual(names, {"ISS-PAT"})
		self.assertFalse(page["company"])
		self.assertFalse(self.support.can_read(self.ticket("ISS-DANA"), "pat@acme.test"))

	def test_other_companies_tickets_are_never_visible(self):
		names, _page = self.visible("dana@acme.test")
		self.assertFalse(names & {"ISS-OLGA", "ISS-OLGA-ORDER", "ISS-PAT-FOREIGN-ORDER", "ISS-DESIGNER-OTHER"})
		olga, _page = self.visible("olga@other.test")
		# A ticket about OTHER's order belongs to OTHER, whoever raised it.
		self.assertEqual(olga, {"ISS-OLGA", "ISS-OLGA-ORDER", "ISS-DESIGNER-OTHER", "ISS-PAT-FOREIGN-ORDER"})
		self.assertFalse(olga & {"ISS-DANA", "ISS-PAT", "ISS-SAM-ORDER", "ISS-DESIGNER-PROJECT"})

	def test_waiting_on_customer_counts_use_the_same_scope(self):
		conditions, params = self.support._conditions("dana@acme.test")
		where = " AND ".join([*conditions, "ill_next_action_by = 'Staff'"])
		rows = run_sql(self.db, f"select name from `tabIssue` where {where}", params)
		self.assertEqual(len(rows), 5)


if __name__ == "__main__":
	unittest.main()
