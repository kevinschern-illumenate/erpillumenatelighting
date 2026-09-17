# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Persona access-matrix tests for the Frappe dealer portal (Phase 0/1).

Two Customers, one persona per row of the target authorization model, and
assertions that document decisions, list predicates and the portal APIs all
agree. These reproduce P0.1-P0.6 and finding 6.4 of
docs/DEALER_PORTAL_ASSESSMENT_AND_IMPLEMENTATION_PLAN.md.

Run with::

	bench --site <site> run-tests --app illumenate_lighting \
		--module illumenate_lighting.illumenate_lighting.api.test_portal_access_matrix
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import document_requests, portal
from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
	get_permission_query_conditions as project_query_conditions,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
	has_permission as project_has_permission,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
	get_permission_query_conditions as schedule_query_conditions,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
	has_permission as schedule_has_permission,
)
from illumenate_lighting.illumenate_lighting.portal import access

PREFIX = "_Test Access"

CUSTOMER_A = f"{PREFIX} Co A"
CUSTOMER_B = f"{PREFIX} Co B"

DEALER_A = "_test_access_dealer_a@example.com"
MEMBER_A = "_test_access_member_a@example.com"
DEALER_B = "_test_access_dealer_b@example.com"
MEMBER_B = "_test_access_member_b@example.com"
VIEW_COLLAB = "_test_access_view_collab@example.com"
EDIT_COLLAB = "_test_access_edit_collab@example.com"
OUTSIDER = "_test_access_outsider@example.com"

ALL_USERS = (DEALER_A, MEMBER_A, DEALER_B, MEMBER_B, VIEW_COLLAB, EDIT_COLLAB, OUTSIDER)
PERSONAS = (*ALL_USERS, "Guest")

REQUEST_TYPE = f"{PREFIX} Request Type"
TEMPLATE_CODE = "_TestAccessTemplate"
ITEM_CODE = f"{PREFIX} Item"
CONFIG_HASH = "_test_access_config"


class TestPortalAccessMatrix(FrappeTestCase):
	# ------------------------------------------------------------------
	# fixtures
	# ------------------------------------------------------------------

	def setUp(self):
		frappe.set_user("Administrator")
		self._ensure_roles()
		self._ensure_customers()
		self._ensure_users()
		self._ensure_request_type()
		self._ensure_configured_fixture()
		self._make_projects_and_schedules()
		# Handoffs live in the cache with a long TTL; start every test clean.
		for user in ALL_USERS:
			access.clear_configured_record_handoff(
				"ilL-Configured-Fixture", self.fixture_name, user
			)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all(
			"ilL-Document-Request",
			filters={"requester_user": ["in", list(ALL_USERS)]},
			pluck="name",
		):
			frappe.delete_doc("ilL-Document-Request", name, force=True, ignore_permissions=True)
		for name in frappe.get_all(
			"ilL-Project-Fixture-Schedule",
			filters={"schedule_name": ["like", f"{PREFIX}%"]},
			pluck="name",
		):
			frappe.delete_doc(
				"ilL-Project-Fixture-Schedule", name, force=True, ignore_permissions=True
			)
		for name in frappe.get_all(
			"ilL-Project", filters={"project_name": ["like", f"{PREFIX}%"]}, pluck="name"
		):
			frappe.delete_doc("ilL-Project", name, force=True, ignore_permissions=True)

	def _ensure_roles(self):
		for role_name in ("Dealer", "Customer"):
			if not frappe.db.exists("Role", role_name):
				role = frappe.new_doc("Role")
				role.role_name = role_name
				role.desk_access = 0
				role.insert(ignore_permissions=True)

	def _ensure_customers(self):
		for name in (CUSTOMER_A, CUSTOMER_B):
			if not frappe.db.exists("Customer", name):
				customer = frappe.new_doc("Customer")
				customer.customer_name = name
				customer.customer_type = "Company"
				customer.insert(ignore_permissions=True)

	def _ensure_user(self, email, roles):
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.new_doc("User")
			user.email = email
			user.first_name = email.split("@")[0]
			user.send_welcome_email = 0
			user.insert(ignore_permissions=True)

		existing = {r.role for r in user.roles}
		missing = [r for r in roles if r not in existing]
		if missing:
			for role in missing:
				user.append("roles", {"role": role})
			user.save(ignore_permissions=True)

	def _link_contact(self, email, customer):
		if frappe.db.get_value("Contact", {"user": email}, "name"):
			return
		contact = frappe.new_doc("Contact")
		contact.first_name = email.split("@")[0]
		contact.user = email
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": customer})
		contact.insert(ignore_permissions=True)

	def _ensure_users(self):
		# "Customer" gives portal users role-level access to the project
		# doctype so that only the policy hook decides the outcome.
		self._ensure_user(DEALER_A, ["Dealer", "Customer"])
		self._ensure_user(DEALER_B, ["Dealer", "Customer"])
		for email in (MEMBER_A, MEMBER_B, VIEW_COLLAB, EDIT_COLLAB, OUTSIDER):
			self._ensure_user(email, ["Customer"])

		self._link_contact(DEALER_A, CUSTOMER_A)
		self._link_contact(MEMBER_A, CUSTOMER_A)
		self._link_contact(DEALER_B, CUSTOMER_B)
		self._link_contact(MEMBER_B, CUSTOMER_B)

	def _ensure_request_type(self):
		if not frappe.db.exists("ilL-Request-Type", REQUEST_TYPE):
			rt = frappe.new_doc("ilL-Request-Type")
			rt.type_name = REQUEST_TYPE
			rt.category = "Drawing"
			rt.is_active = 1
			rt.portal_label = REQUEST_TYPE
			rt.insert(ignore_permissions=True)

	def _ensure_configured_fixture(self):
		if not frappe.db.exists("Item", ITEM_CODE):
			item = frappe.new_doc("Item")
			item.item_code = ITEM_CODE
			item.item_name = ITEM_CODE
			item.item_group = "Products"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)

		if not frappe.db.exists("ilL-Fixture-Template", TEMPLATE_CODE):
			template = frappe.new_doc("ilL-Fixture-Template")
			template.template_code = TEMPLATE_CODE
			template.template_name = "Test Access Template"
			template.is_active = 1
			template.insert(ignore_permissions=True)

		# Owned by Administrator and not on any schedule: a guessed id. The
		# document name is a generated part number, so resolve it by hash.
		if not frappe.db.exists("ilL-Configured-Fixture", {"config_hash": CONFIG_HASH}):
			fixture = frappe.new_doc("ilL-Configured-Fixture")
			fixture.config_hash = CONFIG_HASH
			fixture.fixture_template = TEMPLATE_CODE
			fixture.engine_version = "1.0.0"
			fixture.requested_overall_length_mm = 1234
			fixture.manufacturable_overall_length_mm = 1230
			fixture.runs_count = 1
			fixture.total_watts = 10
			fixture.configured_item = ITEM_CODE
			fixture.insert(ignore_permissions=True)
		self.fixture_name = frappe.db.get_value(
			"ilL-Configured-Fixture", {"config_hash": CONFIG_HASH}, "name"
		)

	def _insert_as(self, doc, owner):
		"""Insert ``doc`` so that Frappe records ``owner`` as its owner."""
		frappe.set_user(owner)
		try:
			doc.insert(ignore_permissions=True)
		finally:
			frappe.set_user("Administrator")
		return doc

	def _make_project(self, suffix, owner, customer, is_private=0, collaborators=None):
		project = frappe.new_doc("ilL-Project")
		project.project_name = f"{PREFIX} {suffix}"
		project.customer = customer
		project.owner_customer = customer
		project.is_private = is_private
		for user, level in collaborators or []:
			project.append(
				"collaborators", {"user": user, "access_level": level, "is_active": 1}
			)
		return self._insert_as(project, owner)

	def _make_schedule(self, suffix, project, owner, inherits=1, is_private=0):
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = f"{PREFIX} {suffix}"
		schedule.ill_project = project.name
		schedule.customer = project.customer
		schedule.inherits_project_privacy = inherits
		schedule.is_private = is_private
		return self._insert_as(schedule, owner)

	def _make_projects_and_schedules(self):
		self.public_a = self._make_project("Public A", DEALER_A, CUSTOMER_A)
		self.private_a = self._make_project(
			"Private A",
			DEALER_A,
			CUSTOMER_A,
			is_private=1,
			collaborators=[(VIEW_COLLAB, "VIEW"), (EDIT_COLLAB, "EDIT")],
		)
		self.member_project_a = self._make_project("Member Project A", MEMBER_A, CUSTOMER_A)
		self.public_b = self._make_project("Public B", DEALER_B, CUSTOMER_B)
		self.projects = [self.public_a, self.private_a, self.member_project_a, self.public_b]

		self.sched_public_a = self._make_schedule("Sched Public A", self.public_a, DEALER_A)
		self.sched_private_a = self._make_schedule("Sched Private A", self.private_a, DEALER_A)
		self.sched_optout_a = self._make_schedule(
			"Sched Optout Private A", self.public_a, DEALER_A, inherits=0, is_private=1
		)
		self.sched_b = self._make_schedule("Sched B", self.public_b, DEALER_B)
		self.schedules = [
			self.sched_public_a,
			self.sched_private_a,
			self.sched_optout_a,
			self.sched_b,
		]

	def _listed(self, doctype, conditions, names):
		if conditions == "":
			return set(names)
		return set(
			frappe.db.sql(
				f"SELECT name FROM `tab{doctype}` WHERE name IN %(names)s AND {conditions}",
				{"names": tuple(names)},
				pluck=True,
			)
		)

	# ------------------------------------------------------------------
	# P0.1 - company membership grants read only
	# ------------------------------------------------------------------

	def test_same_company_member_is_read_only(self):
		self.assertTrue(project_has_permission(self.public_a, "read", MEMBER_A))
		self.assertFalse(project_has_permission(self.public_a, "write", MEMBER_A))
		self.assertFalse(project_has_permission(self.public_a, "delete", MEMBER_A))
		self.assertFalse(project_has_permission(self.private_a, "read", MEMBER_A))

		self.assertTrue(schedule_has_permission(self.sched_public_a, "read", MEMBER_A))
		self.assertFalse(schedule_has_permission(self.sched_public_a, "write", MEMBER_A))

	def test_same_company_member_cannot_mutate_via_api(self):
		frappe.set_user(MEMBER_A)

		result = portal.update_project(self.public_a.name, {"description": "changed"})
		self.assertFalse(result["success"])

		result = portal.archive_project(self.public_a.name)
		self.assertFalse(result["success"])

		result = portal.create_schedule(
			{"ill_project": self.public_a.name, "schedule_name": f"{PREFIX} Rogue"}
		)
		self.assertFalse(result["success"])
		self.assertFalse(
			frappe.db.exists("ilL-Project-Fixture-Schedule", {"schedule_name": f"{PREFIX} Rogue"})
		)

		result = portal.rename_schedule(self.sched_public_a.name, f"{PREFIX} Renamed")
		self.assertFalse(result["success"])

	def test_company_dealer_can_mutate_company_projects(self):
		self.assertTrue(project_has_permission(self.public_a, "write", DEALER_A))
		self.assertTrue(project_has_permission(self.private_a, "write", DEALER_A))
		self.assertTrue(project_has_permission(self.member_project_a, "write", DEALER_A))
		self.assertTrue(schedule_has_permission(self.sched_optout_a, "write", DEALER_A))

		self.assertFalse(project_has_permission(self.public_a, "read", DEALER_B))
		self.assertFalse(schedule_has_permission(self.sched_public_a, "read", DEALER_B))

	def test_collaborator_levels(self):
		self.assertTrue(project_has_permission(self.private_a, "read", VIEW_COLLAB))
		self.assertFalse(project_has_permission(self.private_a, "write", VIEW_COLLAB))

		self.assertTrue(project_has_permission(self.private_a, "write", EDIT_COLLAB))
		self.assertFalse(project_has_permission(self.private_a, "delete", EDIT_COLLAB))

		self.assertTrue(schedule_has_permission(self.sched_private_a, "read", VIEW_COLLAB))
		self.assertFalse(schedule_has_permission(self.sched_private_a, "write", VIEW_COLLAB))
		self.assertTrue(schedule_has_permission(self.sched_private_a, "write", EDIT_COLLAB))

		self.assertFalse(project_has_permission(self.private_a, "read", OUTSIDER))
		self.assertFalse(project_has_permission(self.public_a, "read", "Guest"))

	# ------------------------------------------------------------------
	# P0.2 - list visibility equals direct access
	# ------------------------------------------------------------------

	def test_project_list_matches_direct_access(self):
		names = [p.name for p in self.projects]
		for user in PERSONAS:
			listed = self._listed("ilL-Project", project_query_conditions(user), names)
			direct = {p.name for p in self.projects if project_has_permission(p, "read", user)}
			self.assertEqual(listed, direct, f"project parity failed for {user}")

	def test_schedule_list_matches_direct_access(self):
		names = [s.name for s in self.schedules]
		for user in PERSONAS:
			listed = self._listed(
				"ilL-Project-Fixture-Schedule", schedule_query_conditions(user), names
			)
			direct = {
				s.name for s in self.schedules if schedule_has_permission(s, "read", user)
			}
			self.assertEqual(listed, direct, f"schedule parity failed for {user}")

	def test_collaborator_discovers_inherited_schedule(self):
		listed = self._listed(
			"ilL-Project-Fixture-Schedule",
			schedule_query_conditions(VIEW_COLLAB),
			[s.name for s in self.schedules],
		)
		self.assertIn(self.sched_private_a.name, listed)
		self.assertNotIn(self.sched_b.name, listed)

	def test_optout_private_schedule_hidden_from_company_member(self):
		self.assertTrue(project_has_permission(self.public_a, "read", MEMBER_A))
		self.assertFalse(schedule_has_permission(self.sched_optout_a, "read", MEMBER_A))
		listed = self._listed(
			"ilL-Project-Fixture-Schedule",
			schedule_query_conditions(MEMBER_A),
			[s.name for s in self.schedules],
		)
		self.assertNotIn(self.sched_optout_a.name, listed)

	# ------------------------------------------------------------------
	# P0.3 / P0.4 - document requests are scoped and validated
	# ------------------------------------------------------------------

	def _create_request(self, user, project=None, description="Need a drawing"):
		frappe.set_user(user)
		return document_requests.create_portal_document_request(
			request_type=REQUEST_TYPE, description=description, project=project
		)

	def test_request_list_and_counts_are_scoped(self):
		req_a = self._create_request(MEMBER_A, project=self.public_a.name)
		req_b = self._create_request(MEMBER_B, project=self.public_b.name)

		frappe.set_user(MEMBER_B)
		listed = document_requests.list_requests()
		names = {r["name"] for r in listed["requests"]}
		self.assertIn(req_b.name, names)
		self.assertNotIn(req_a.name, names)
		self.assertEqual(listed["total"], len(names))

		counts = document_requests.get_request_counts()
		self.assertEqual(counts["all"], len(names))

		frappe.set_user(DEALER_A)
		names = {r["name"] for r in document_requests.list_requests()["requests"]}
		self.assertIn(req_a.name, names)
		self.assertNotIn(req_b.name, names)

		frappe.set_user(MEMBER_B)
		detail = document_requests.get_request_detail(req_a.name)
		self.assertFalse(detail["success"])
		self.assertEqual(detail["error"], "Request not found")

	def test_request_creation_requires_project_access(self):
		frappe.set_user(MEMBER_B)
		result = document_requests.create_request(
			{
				"request_type": REQUEST_TYPE,
				"description": "Peek",
				"project": self.private_a.name,
			}
		)
		self.assertFalse(result["success"])
		self.assertFalse(
			frappe.db.exists(
				"ilL-Document-Request", {"requester_user": MEMBER_B, "project": self.private_a.name}
			)
		)

		result = portal.create_drawing_request(
			{"drawing_type": "shop_drawing", "project": self.private_a.name, "description": "Peek"}
		)
		self.assertFalse(result["success"])

	def test_drawing_request_never_creates_request_type(self):
		frappe.set_user(MEMBER_A)
		result = portal.create_drawing_request(
			{"drawing_type": "_test_access_bogus", "description": "x"}
		)
		self.assertFalse(result["success"])
		self.assertFalse(frappe.db.exists("ilL-Request-Type", "Test Access Bogus"))

	def test_request_creation_rejects_guest(self):
		frappe.set_user("Guest")
		result = document_requests.create_request(
			{"request_type": REQUEST_TYPE, "description": "x"}
		)
		self.assertFalse(result["success"])
		self.assertFalse(document_requests.list_requests()["success"])

	# ------------------------------------------------------------------
	# P0.5 - configured records need provenance before attachment
	# ------------------------------------------------------------------

	def test_guessed_configured_fixture_cannot_be_attached(self):
		frappe.set_user(DEALER_A)
		result = portal.save_configured_fixture_to_schedule(
			self.sched_public_a.name, self.fixture_name, 1230
		)
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "Configured fixture not found")

		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", self.sched_public_a.name)
		self.assertFalse(
			any(line.configured_fixture == self.fixture_name for line in schedule.lines)
		)

	def test_validated_configured_fixture_can_be_attached(self):
		frappe.set_user(DEALER_A)
		access.register_configured_record_handoff("ilL-Configured-Fixture", self.fixture_name)

		self.assertTrue(
			access.can_read_configured_record("ilL-Configured-Fixture", self.fixture_name)
		)
		result = portal.save_configured_fixture_to_schedule(
			self.sched_public_a.name, self.fixture_name, 1230
		)
		self.assertTrue(result["success"], result.get("error"))

		# Now that it sits on a readable schedule, company members can read it
		# without their own handoff, but strangers still cannot.
		frappe.set_user(MEMBER_A)
		self.assertTrue(
			access.can_read_configured_record("ilL-Configured-Fixture", self.fixture_name)
		)
		frappe.set_user(MEMBER_B)
		self.assertFalse(
			access.can_read_configured_record("ilL-Configured-Fixture", self.fixture_name)
		)

	# ------------------------------------------------------------------
	# P0.6 - one collaborator-management rule
	# ------------------------------------------------------------------

	def test_collaborator_management_policy(self):
		self.assertTrue(access.can_manage_project_collaborators(self.member_project_a, MEMBER_A))
		self.assertTrue(access.can_manage_project_collaborators(self.member_project_a, DEALER_A))
		self.assertFalse(access.can_manage_project_collaborators(self.private_a, EDIT_COLLAB))
		self.assertFalse(access.can_manage_project_collaborators(self.public_a, MEMBER_A))
		self.assertFalse(access.can_manage_project_collaborators(self.public_a, DEALER_B))

	def test_company_dealer_manages_collaborators_via_api(self):
		frappe.set_user(DEALER_A)
		result = portal.update_project_collaborators(
			self.member_project_a.name, [{"user": OUTSIDER, "access_level": "VIEW"}]
		)
		self.assertTrue(result["success"], result.get("error"))
		project = frappe.get_doc("ilL-Project", self.member_project_a.name)
		self.assertTrue(project_has_permission(project, "read", OUTSIDER))

	def test_edit_collaborator_cannot_manage_collaborators_or_privacy(self):
		frappe.set_user(EDIT_COLLAB)
		result = portal.update_project_collaborators(self.private_a.name, [])
		self.assertFalse(result["success"])
		project = frappe.get_doc("ilL-Project", self.private_a.name)
		self.assertEqual(len(project.collaborators), 2)

		result = portal.toggle_project_privacy(self.private_a.name, 0)
		self.assertFalse(result["success"])
		self.assertTrue(frappe.db.get_value("ilL-Project", self.private_a.name, "is_private"))

	def test_other_company_dealer_cannot_invite(self):
		frappe.set_user(DEALER_B)
		result = portal.invite_project_collaborator(
			self.public_a.name, "_test_access_invitee@example.com", send_invite=0
		)
		self.assertFalse(result["success"])
		self.assertFalse(frappe.db.exists("User", "_test_access_invitee@example.com"))

	# ------------------------------------------------------------------
	# 6.4 - customer selection is rejected, never silently swapped
	# ------------------------------------------------------------------

	def test_create_project_rejects_foreign_customer(self):
		frappe.set_user(MEMBER_A)
		result = portal.create_project(
			{"project_name": f"{PREFIX} Foreign", "customer": CUSTOMER_B}
		)
		self.assertFalse(result["success"])
		self.assertFalse(frappe.db.exists("ilL-Project", {"project_name": f"{PREFIX} Foreign"}))
