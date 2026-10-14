"""DESK-9: dealer-scoped project parties instead of portal-created Customers."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

PARTY = "ilL-Project-Party"


class Doc(Record):
	"""A saved-document stand-in: attribute writes land in the dict."""

	def __setattr__(self, key, value):
		self[key] = value


class Store:
	"""Just enough of frappe.db / get_all / new_doc over in-memory rows."""

	def __init__(self, frappe, parties=(), customers=(), users=None, projects=()):
		self.parties = {row["name"]: Doc(row) for row in parties}
		self.customers = {row["name"]: Doc(row) for row in customers}
		self.users = users or {}
		self.projects = {row["name"]: Doc(row) for row in projects}
		self.set_values = []
		frappe.db.get_value = self.get_value
		frappe.db.exists = self.exists
		frappe.db.set_value = self.set_value
		frappe.db.escape = lambda value: "'" + str(value).replace("'", "''") + "'"
		frappe.db.get_single_value = MagicMock(return_value=None)
		frappe.get_all = self.get_all
		frappe.new_doc = self.new_doc
		frappe.get_doc = self.get_doc

	def table(self, doctype):
		return {PARTY: self.parties, "Customer": self.customers, "ilL-Project": self.projects}[doctype]

	@staticmethod
	def matches(row, filters):
		for key, wanted in (filters or {}).items():
			value = row.get(key)
			if isinstance(wanted, list):
				operator, operand = wanted
				if operator == "in" and value not in operand:
					return False
				if operator == "!=" and value == operand:
					return False
			elif isinstance(wanted, str) and isinstance(value, str):
				if value.lower() != wanted.lower():  # MariaDB's default collation ignores case
					return False
			elif value != wanted and not (wanted == 0 and not value):
				return False
		return True

	def get_value(self, doctype, name, field=None, as_dict=False):
		if doctype == "User":
			return self.users.get(name)
		rows = self.table(doctype)
		if isinstance(name, dict):
			row = next((row for row in rows.values() if self.matches(row, name)), None)
		else:
			row = rows.get(name)
		if row is None:
			return None
		if isinstance(field, list):
			picked = Doc({key: row.get(key) for key in field})
			return picked if as_dict else tuple(picked.values())
		return row.get(field)

	def exists(self, doctype, name):
		rows = self.table(doctype)
		if isinstance(name, dict):
			return any(self.matches(row, name) for row in rows.values())
		return name in rows

	def set_value(self, doctype, name, field, value=None, update_modified=True):
		values = field if isinstance(field, dict) else {field: value}
		self.table(doctype)[name].update(values)
		self.set_values.append((doctype, name, values))

	def get_all(self, doctype, filters=None, fields=None, order_by=None, **kwargs):
		rows = [row for row in self.table(doctype).values() if self.matches(row, filters)]
		if order_by == "party_name asc":
			rows.sort(key=lambda row: row.party_name)
		return [Doc(row) for row in rows]

	def new_doc(self, doctype):
		store = self
		doc = Doc(doctype=doctype)

		def insert(ignore_permissions=False):
			table = store.table(doctype)
			doc["name"] = doc.get("customer_name") if doctype == "Customer" else f"PTY-{len(table) + 1}"
			doc["ignore_permissions"] = ignore_permissions
			table[doc.name] = doc
			return doc

		doc["insert"] = insert
		doc["db_set"] = lambda field, value: doc.update({field: value})
		return doc

	def get_doc(self, doctype, name=None):
		if isinstance(doctype, dict):
			doc = self.new_doc(doctype["doctype"])
			doc.update({key: value for key, value in doctype.items() if key != "doctype"})
			return doc
		doc = self.table(doctype)[name]
		doc["db_set"] = lambda field, value: doc.update({field: value})
		return doc


def actor(user="dana@acme.test", customer="ACME", dealer=True, internal=False):
	return types.SimpleNamespace(
		user=user, customer=customer, is_dealer=dealer, is_internal=internal, is_guest=False
	)


class ProjectParties(unittest.TestCase):
	def service(self, who=None, staff=False, sales=True, **store):
		self.actor = who or actor()
		access = types.SimpleNamespace(get_actor=MagicMock(return_value=self.actor))
		owner = types.SimpleNamespace(can_set_owner_company=MagicMock(return_value=staff))
		self.require = MagicMock(side_effect=None if sales else PermissionError("staff only"))
		staff_module = types.SimpleNamespace(require=self.require)
		context = load_service(
			ROOT + ".portal.project_parties",
			{
				ROOT + ".portal.access": access,
				ROOT + ".portal.project_owner": owner,
				ROOT + ".portal.staff": staff_module,
			},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.store = Store(frappe, **store)
		return module, frappe

	# -- create_party -----------------------------------------------------

	def test_dealer_creates_for_own_company_whatever_company_they_send(self):
		module, _frappe = self.service()
		result = module.create(
			{"party_name": "  Acme   GC ", "role": "General Contractor", "owner_customer": "RIVAL", "email": "gc@x"}
		)
		party = self.store.parties[result["party"]]
		self.assertEqual((party.owner_customer, party.party_name, party.role), ("ACME", "Acme GC", "General Contractor"))
		self.assertEqual(party.email, "gc@x")
		self.assertFalse(result["existing"])

	def test_same_name_and_role_returns_the_existing_party_not_an_error(self):
		module, _frappe = self.service(
			parties=[{"name": "PTY-1", "party_name": "Acme GC", "role": "General Contractor", "owner_customer": "ACME"}]
		)
		result = module.create({"party_name": "acme gc", "role": "General Contractor"})
		self.assertEqual(result, {"party": "PTY-1", "label": "Acme GC", "role": "General Contractor", "existing": True})
		self.assertEqual(len(self.store.parties), 1)

	def test_two_dealers_may_each_have_the_same_name_and_one_dealer_one_name_per_role(self):
		module, _frappe = self.service(
			parties=[{"name": "PTY-1", "party_name": "Acme GC", "role": "General Contractor", "owner_customer": "RIVAL"}]
		)
		mine = module.create({"party_name": "Acme GC", "role": "General Contractor"})
		self.assertFalse(mine["existing"], "another dealer's party is neither reused nor revealed")
		architect = module.create({"party_name": "Acme GC", "role": "Architect"})
		self.assertNotEqual(architect["party"], mine["party"])

	def test_only_dealers_and_staff_create_parties(self):
		module, _frappe = self.service(who=actor(dealer=False))
		with self.assertRaises(PermissionError):
			module.create({"party_name": "X", "role": "Architect"})
		module, _frappe = self.service(who=actor(customer=None))
		with self.assertRaises(PermissionError):
			module.create({"party_name": "X", "role": "Architect"})

	def test_staff_create_for_the_company_they_name(self):
		module, _frappe = self.service(who=actor(customer=None, dealer=False), staff=True, customers=[{"name": "ACME"}])
		with self.assertRaisesRegex(ValueError, "dealer company first"):
			module.create({"party_name": "X", "role": "Architect"})
		with self.assertRaisesRegex(ValueError, "does not exist"):
			module.create({"party_name": "X", "role": "Architect", "owner_customer": "GHOST"})
		result = module.create({"party_name": "X", "role": "Architect", "owner_customer": "ACME"})
		self.assertEqual(self.store.parties[result["party"]].owner_customer, "ACME")

	def test_name_and_role_are_required(self):
		module, _frappe = self.service()
		with self.assertRaisesRegex(ValueError, "Name is required"):
			module.create({"party_name": "   ", "role": "Architect"})
		with self.assertRaisesRegex(ValueError, "Choose a role"):
			module.create({"party_name": "X", "role": "Customer"})

	# -- permissions ------------------------------------------------------

	def test_website_users_see_only_their_company_and_only_dealers_change_it(self):
		module, _frappe = self.service(users={"dana@acme.test": "Website User", "sam@ill.test": "System User"})
		mine, theirs = Record(owner_customer="ACME"), Record(owner_customer="RIVAL")
		self.assertTrue(module.has_permission(mine, "read", "dana@acme.test"))
		self.assertTrue(module.has_permission(mine, "write", "dana@acme.test"))
		self.assertFalse(module.has_permission(mine, "delete", "dana@acme.test"))
		self.assertFalse(module.has_permission(theirs, "read", "dana@acme.test"))
		self.assertEqual(module.query_conditions("dana@acme.test"), "`tabilL-Project-Party`.owner_customer = 'ACME'")
		self.assertIs(module.has_permission(theirs, "write", "sam@ill.test"), True)
		self.assertEqual(module.query_conditions("sam@ill.test"), "")
		self.assertIs(module.has_permission(mine, "read", "Guest"), False)
		self.assertEqual(module.query_conditions("Guest"), "1=0")

	def test_non_dealer_members_read_only_and_users_without_a_company_see_nothing(self):
		module, _frappe = self.service(who=actor(dealer=False), users={"dana@acme.test": "Website User"})
		self.assertTrue(module.has_permission(Record(owner_customer="ACME"), "read", "dana@acme.test"))
		self.assertFalse(module.has_permission(Record(owner_customer="ACME"), "write", "dana@acme.test"))
		module, _frappe = self.service(who=actor(customer=None), users={"dana@acme.test": "Website User"})
		self.assertEqual(module.query_conditions("dana@acme.test"), "1=0")
		self.assertFalse(module.has_permission(Record(owner_customer=None), "read", "dana@acme.test"))

	# -- project validation and pickers -----------------------------------

	def project(self, previous=None, **values):
		doc = Record(owner_customer="ACME", **values)
		doc.is_new = lambda: previous is None
		doc.get_doc_before_save = lambda: previous
		return doc

	def test_project_fields_need_a_party_of_the_owner_company_in_that_role(self):
		module, _frappe = self.service(
			parties=[
				{"name": "PTY-1", "party_name": "Studio", "role": "Architect", "owner_customer": "ACME"},
				{"name": "PTY-2", "party_name": "Rival GC", "role": "General Contractor", "owner_customer": "RIVAL"},
			]
		)
		module.validate_project(self.project(architect="PTY-1"))
		with self.assertRaisesRegex(ValueError, "is not a Lighting Designer"):
			module.validate_project(self.project(lighting_designer="PTY-1"))
		with self.assertRaisesRegex(PermissionError, "another company"):
			module.validate_project(self.project(general_contractor="PTY-2"))
		with self.assertRaisesRegex(ValueError, "not a known project party"):
			module.validate_project(self.project(end_client_party="CUST-OLD"))
		# Unchanged values are not re-checked, so a transferred project still saves.
		module.validate_project(self.project(previous=Record(general_contractor="PTY-2"), general_contractor="PTY-2"))

	def test_pickers_list_the_company_parties_by_field_and_keep_current_choices(self):
		parties = [
			{"name": "PTY-1", "party_name": "Studio", "role": "Architect", "owner_customer": "ACME", "disabled": 0},
			{"name": "PTY-2", "party_name": "Hotel", "role": "End Client", "owner_customer": "ACME", "disabled": 0},
			{"name": "PTY-3", "party_name": "Old", "role": "Architect", "owner_customer": "ACME", "disabled": 1},
			{"name": "PTY-4", "party_name": "Rival", "role": "Architect", "owner_customer": "RIVAL", "disabled": 0},
		]
		module, _frappe = self.service(parties=parties)
		choices = module.picker_options()
		self.assertEqual(choices["architect"], [{"value": "PTY-1", "label": "Studio"}])
		self.assertEqual(choices["end_client_party"], [{"value": "PTY-2", "label": "Hotel"}])
		kept = module.picker_options(Record(owner_customer="ACME", architect="PTY-3"))
		self.assertIn({"value": "PTY-3", "label": "Old"}, kept["architect"], "a disabled current choice stays")
		# A collaborator from another company sees only what the project already names.
		outsider = module.picker_options(Record(owner_customer="RIVAL", architect="PTY-4"))
		self.assertEqual(outsider["architect"], [{"value": "PTY-4", "label": "Rival"}])
		self.assertEqual(outsider["end_client_party"], [])

	def test_new_portal_projects_bill_the_owner_company_unless_the_end_client_is_promoted(self):
		module, _frappe = self.service(
			parties=[
				{"name": "PTY-1", "party_name": "Hotel", "role": "End Client", "owner_customer": "ACME"},
				{"name": "PTY-2", "party_name": "Big Co", "role": "End Client", "owner_customer": "ACME", "customer": "BIG"},
			]
		)
		self.assertEqual(module.project_customer({}, "ACME"), "ACME")
		self.assertEqual(module.project_customer({"end_client_party": "PTY-1"}, "ACME"), "ACME")
		self.assertEqual(module.project_customer({"end_client_party": "PTY-2"}, "ACME"), "BIG")

	def test_labels_name_parties_and_legacy_customers(self):
		module, _frappe = self.service(
			parties=[{"name": "PTY-1", "party_name": "Hotel", "role": "End Client", "owner_customer": "ACME"}],
			customers=[{"name": "CUST-9", "customer_name": "Nine Inc"}],
		)
		project = Record(end_client_party="PTY-1", architect="PTY-1", customer="ACME")
		self.assertEqual(module.project_labels(project), {"end_client_party": "Hotel", "architect": "Hotel"})
		self.assertEqual(module.end_client_label(project), "Hotel")
		self.assertEqual(module.end_client_label(Record(customer="CUST-9")), "Nine Inc")

	# -- promotion --------------------------------------------------------

	def test_promotion_is_staff_only(self):
		module, _frappe = self.service(sales=False)
		with self.assertRaises(PermissionError):
			module.promote_to_customer("PTY-1")
		self.assertEqual(module.promote_to_customer.whitelist_options, {"methods": ["POST"]})

	def test_promotion_creates_a_customer_and_repoints_projects_that_bill_the_dealer(self):
		module, _frappe = self.service(
			parties=[{"name": "PTY-1", "party_name": "Hotel", "role": "End Client", "owner_customer": "ACME"}],
			customers=[{"name": "ACME", "customer_name": "Acme"}],
			projects=[
				{"name": "P-1", "end_client_party": "PTY-1", "customer": "ACME", "owner_customer": "ACME"},
				{"name": "P-2", "end_client_party": "PTY-1", "customer": "OTHER", "owner_customer": "ACME"},
			],
		)
		result = module.promote_to_customer("PTY-1")
		self.assertEqual(result, {"customer": "Hotel", "created": True, "projects": ["P-1"]})
		self.assertEqual(self.store.parties["PTY-1"].customer, "Hotel")
		self.assertEqual(self.store.customers["Hotel"].customer_group, "All Customer Groups")
		self.assertEqual(self.store.projects["P-2"].customer, "OTHER", "a project with its own Customer is left")

	def test_promotion_never_silently_links_a_same_named_customer(self):
		module, _frappe = self.service(
			parties=[{"name": "PTY-1", "party_name": "Acme GC", "role": "General Contractor", "owner_customer": "ACME"}],
			customers=[{"name": "Acme GC", "customer_name": "Acme GC"}],
		)
		with self.assertRaisesRegex(ValueError, "already exists"):
			module.promote_to_customer("PTY-1")
		result = module.promote_to_customer("PTY-1", customer="Acme GC")
		self.assertEqual((result["customer"], result["created"]), ("Acme GC", False))
		with self.assertRaisesRegex(ValueError, "does not exist"):
			module.promote_to_customer("PTY-1", customer="Ghost")


CUSTOMERS = [
	{"name": "ACME", "customer_name": "Acme", "owner": "Administrator"},
	{"name": "Studio X", "customer_name": "Studio X", "owner": "dana@acme.test"},
	{"name": "Hotel", "customer_name": "Hotel", "owner": "dana@acme.test"},
	{"name": "Big GC", "customer_name": "Big GC", "owner": "sam@ill.test"},
	{"name": "Real Client", "customer_name": "Real Client", "owner": "sam@ill.test"},
]
USERS = {"dana@acme.test": "Website User", "sam@ill.test": "System User", "lee@rival.test": "Website User"}


class Migration(unittest.TestCase):
	def run_patch(self, projects, customers, users, companies=None, parties=()):
		project_module = types.SimpleNamespace(
			_get_user_customer=MagicMock(side_effect=lambda user: (companies or {}).get(user))
		)
		pp_context = load_service(ROOT + ".portal.project_parties")
		project_parties, _ = pp_context.__enter__()
		self.addCleanup(pp_context.__exit__, None, None, None)
		context = load_service(
			"illumenate_lighting.patches.migrate_project_parties",
			{
				ROOT + ".portal.project_parties": project_parties,
				ROOT + ".doctype.ill_project.ill_project": project_module,
			},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		project_parties.frappe = frappe
		store = Store(frappe, parties=parties, customers=customers, users=users, projects=projects)
		return module, store

	def projects(self):
		return [
			{
				"name": "P-1", "owner": "dana@acme.test", "owner_customer": "ACME", "customer": "Hotel",
				"architect": "Studio X", "general_contractor": "Big GC",
			},
			{
				"name": "P-2", "owner": "dana@acme.test", "owner_customer": "ACME", "customer": "Real Client",
				"architect": "Studio X",
			},
			{"name": "P-3", "owner": "lee@rival.test", "owner_customer": None, "customer": "ACME", "architect": "Studio X"},
		]

	def test_customers_become_parties_of_the_owner_company_and_customers_stay(self):
		module, store = self.run_patch(
			self.projects(), CUSTOMERS, USERS, companies={"dana@acme.test": "ACME", "lee@rival.test": "RIVAL"}
		)
		stats = module.migrate()
		parties = {(p.owner_customer, p.role, p.party_name): p for p in store.parties.values()}
		studio = parties[("ACME", "Architect", "Studio X")]
		self.assertEqual((studio.source_customer, studio.customer), ("Studio X", None))
		big_gc = parties[("ACME", "General Contractor", "Big GC")]
		self.assertEqual(big_gc.customer, "Big GC", "a staff-created Customer is already a real one")
		hotel = parties[("ACME", "End Client", "Hotel")]
		p1, p2 = store.projects["P-1"], store.projects["P-2"]
		self.assertEqual((p1.architect, p1.general_contractor, p1.end_client_party), (studio.name, big_gc.name, hotel.name))
		self.assertEqual(p1.customer, "Hotel", "billing Customer is untouched")
		self.assertEqual(p2.architect, studio.name, "one party per company, role and name")
		self.assertIsNone(p2.get("end_client_party"), "a staff-created end client stays a Customer only")
		# No owner company: the Customer creator's company decides.
		self.assertEqual(store.parties[store.projects["P-3"].architect].owner_customer, "ACME")
		self.assertEqual(len(store.customers), len(CUSTOMERS), "no Customer is deleted or created")
		self.assertEqual((stats["parties"], stats["projects"], stats["skipped"]), (3, 3, []))

	def test_running_twice_changes_nothing(self):
		module, store = self.run_patch(self.projects(), CUSTOMERS, USERS, companies={"dana@acme.test": "ACME"})
		module.migrate()
		before = {name: dict(project) for name, project in store.projects.items()}
		count = len(store.parties)
		stats = module.migrate()
		self.assertEqual((stats["parties"], stats["projects"]), (0, 0))
		self.assertEqual(len(store.parties), count)
		self.assertEqual({name: dict(project) for name, project in store.projects.items()}, before)

	def test_unresolvable_values_are_reported_not_guessed(self):
		projects = [
			{"name": "P-9", "owner": "sam@ill.test", "owner_customer": None, "customer": "ACME", "architect": "Big GC"},
			{"name": "P-8", "owner": "dana@acme.test", "owner_customer": "ACME", "customer": "ACME", "architect": "Gone"},
		]
		module, store = self.run_patch(projects, CUSTOMERS, USERS)
		stats = module.migrate()
		self.assertEqual(len(stats["skipped"]), 2)
		self.assertEqual(store.projects["P-9"].architect, "Big GC")
		self.assertEqual(store.parties, {})


if __name__ == "__main__":
	unittest.main()
