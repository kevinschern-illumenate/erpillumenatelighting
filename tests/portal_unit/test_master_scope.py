"""Dealer row scoping for Customer, Contact and Address (SEC-3).

The predicates run against an in-memory SQLite copy of the tables they touch, so
these tests check which rows a persona actually gets back, not SQL text.
"""

import sqlite3
import types
import unittest

from test_services import ROOT, Record, load_service

ACCESS = "illumenate_lighting.illumenate_lighting.portal.access"

SCHEMA = """
CREATE TABLE `tabUser` (name TEXT, user_type TEXT);
CREATE TABLE `tabCustomer` (name TEXT, owner TEXT);
CREATE TABLE `tabContact` (name TEXT, owner TEXT, user TEXT);
CREATE TABLE `tabAddress` (name TEXT, owner TEXT);
CREATE TABLE `tabDynamic Link` (parent TEXT, parenttype TEXT, link_doctype TEXT, link_name TEXT);
CREATE TABLE `tabilL-Project` (
	name TEXT, owner TEXT, customer TEXT, owner_customer TEXT, architect TEXT,
	lighting_designer TEXT, general_contractor TEXT, project_manager TEXT
);
INSERT INTO `tabUser` VALUES
	('dealer@a.test', 'Website User'), ('member@a.test', 'Website User'),
	('designer@x.test', 'Website User'), ('sales@ill.test', 'System User');
INSERT INTO `tabCustomer` VALUES
	('Dealer A', 'Administrator'), ('Dealer B', 'Administrator'),
	('A End Client', 'dealer@a.test'), ('B End Client', 'dealer-b@b.test'),
	('Shared GC', 'dealer-b@b.test'), ('B Private Architect', 'dealer-b@b.test');
INSERT INTO `tabContact` VALUES
	('A Buyer', 'Administrator', 'dealer@a.test'), ('B Buyer', 'Administrator', 'dealer-b@b.test'),
	('GC Contact', 'dealer-b@b.test', NULL), ('A PM', 'dealer-b@b.test', NULL),
	('A Scratch', 'dealer@a.test', NULL);
INSERT INTO `tabAddress` VALUES
	('A Warehouse', 'Administrator'), ('B Warehouse', 'Administrator'), ('A Draft', 'dealer@a.test');
INSERT INTO `tabDynamic Link` VALUES
	('A Buyer', 'Contact', 'Customer', 'Dealer A'), ('B Buyer', 'Contact', 'Customer', 'Dealer B'),
	('GC Contact', 'Contact', 'Customer', 'Shared GC'),
	('A Warehouse', 'Address', 'Customer', 'Dealer A'), ('B Warehouse', 'Address', 'Customer', 'Dealer B'),
	-- A Contact row in the link table must not leak an Address of the same name.
	('B Warehouse', 'Contact', 'Customer', 'Dealer A');
-- Team columns link ilL-Project-Party (DESK-9). These hold the pre-migration Customer
-- names on purpose: a project naming a party must not expose a same-named Customer.
INSERT INTO `tabilL-Project` VALUES
	('P-A', 'dealer@a.test', 'A End Client', 'Dealer A', NULL, NULL, 'Shared GC', 'A PM'),
	('P-B', 'dealer-b@b.test', 'B End Client', 'Dealer B', 'B Private Architect', NULL, 'Shared GC', 'B Buyer');
"""

# Stand-ins for access._project_visibility_sql: which projects each persona may read.
READABLE_PROJECTS = {
	"dealer@a.test": "p.owner_customer = 'Dealer A'",
	"member@a.test": "p.owner_customer = 'Dealer A'",
	"designer@x.test": "p.name = 'P-B'",
}
CUSTOMERS = {"dealer@a.test": "Dealer A", "member@a.test": "Dealer A", "designer@x.test": None}


def _access_module():
	module = types.ModuleType(ACCESS)
	module.PROJECT_TABLE = "`tabilL-Project`"
	module.get_actor = lambda user: types.SimpleNamespace(
		user=user, is_guest=user not in CUSTOMERS, customer=CUSTOMERS.get(user)
	)
	module._project_visibility_sql = lambda actor, table: READABLE_PROJECTS.get(actor.user, "1=0")
	return module


class MasterScope(unittest.TestCase):
	def setUp(self):
		self.db = sqlite3.connect(":memory:")
		self.db.executescript(SCHEMA)
		self.addCleanup(self.db.close)
		self.loaded = load_service(ROOT + ".portal.master_scope", {ACCESS: _access_module()})
		self.module, frappe = self.loaded.__enter__()
		self.addCleanup(self.loaded.__exit__, None, None, None)
		frappe.db.escape = lambda value: "'" + str(value).replace("'", "''") + "'"
		frappe.db.get_value = lambda doctype, name, field: (
			self.db.execute("SELECT user_type FROM `tabUser` WHERE name = ?", (name,)).fetchone() or [None]
		)[0]
		frappe.db.sql = lambda query, values=(): self.db.execute(query.replace("%s", "?"), values).fetchall()

	def visible(self, doctype, user):
		condition = getattr(self.module, doctype.lower() + "_query_conditions")(user)
		query = f"SELECT name FROM `tab{doctype}`" + (f" WHERE {condition}" if condition else "")
		return {row[0] for row in self.db.execute(query)}

	def test_dealer_sees_own_company_project_customers_and_own_records(self):
		user = "dealer@a.test"
		self.assertEqual(self.visible("Customer", user), {"Dealer A", "A End Client"})
		self.assertEqual(self.visible("Contact", user), {"A Buyer", "A PM", "A Scratch"})
		self.assertEqual(self.visible("Address", user), {"A Warehouse", "A Draft"})

	def test_non_dealer_company_member_is_scoped_to_readable_projects(self):
		user = "member@a.test"
		self.assertEqual(self.visible("Customer", user), {"Dealer A", "A End Client"})
		self.assertEqual(self.visible("Contact", user), {"A Buyer", "A PM"})
		self.assertEqual(self.visible("Address", user), {"A Warehouse"})

	def test_external_collaborator_sees_only_the_invited_project_customer(self):
		user = "designer@x.test"
		self.assertEqual(self.visible("Customer", user), {"B End Client"})
		self.assertEqual(self.visible("Contact", user), {"B Buyer"})
		self.assertEqual(self.visible("Address", user), set())

	def test_team_parties_no_longer_expose_customers(self):
		# DESK-9: the architect and contractor are dealer-scoped parties, so a project
		# naming them reveals neither the other dealer's Customers nor their contacts.
		for user in ("dealer@a.test", "member@a.test", "designer@x.test"):
			with self.subTest(user=user):
				self.assertFalse({"Shared GC", "B Private Architect"} & self.visible("Customer", user))
				self.assertNotIn("GC Contact", self.visible("Contact", user))

	def test_staff_are_unrestricted_and_guests_see_nothing(self):
		for doctype in ("Customer", "Contact", "Address"):
			total = {row[0] for row in self.db.execute(f"SELECT name FROM `tab{doctype}`")}
			self.assertEqual(self.visible(doctype, "sales@ill.test"), total)
			self.assertEqual(self.visible(doctype, "Administrator"), total)
			self.assertEqual(self.visible(doctype, "Guest"), set())
			self.assertEqual(self.visible(doctype, "disabled@a.test"), set())

	def test_document_permission_matches_the_list(self):
		for doctype in ("Customer", "Contact", "Address"):
			check = getattr(self.module, doctype.lower() + "_has_permission")
			names = [row[0] for row in self.db.execute(f"SELECT name FROM `tab{doctype}`")]
			for user in ("dealer@a.test", "member@a.test", "designer@x.test", "sales@ill.test", "Guest"):
				visible = self.visible(doctype, user)
				for name in names:
					with self.subTest(doctype=doctype, user=user, name=name):
						self.assertEqual(check(Record(name=name), "read", user), name in visible)
			self.assertIs(check(Record(name=None), "read", "dealer@a.test"), False)

	def test_hostile_names_are_escaped(self):
		CUSTOMERS["o'brien@a.test"] = "Dealer A"
		self.addCleanup(CUSTOMERS.pop, "o'brien@a.test")
		self.db.execute("INSERT INTO `tabUser` VALUES ('o''brien@a.test', 'Website User')")
		self.assertIn("Dealer A", self.visible("Customer", "o'brien@a.test"))


if __name__ == "__main__":
	unittest.main()
