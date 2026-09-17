# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Authorisation, atomicity and visibility tests for schedule → Sales Order.

These cover the paths that only ever break for real dealers: System Managers
bypass the ERPNext role check, so a missing Dealer permission or a leaked
partial BOM never shows up when the suite runs as Administrator.
"""

import frappe
from frappe.permissions import update_permission_property
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api import portal, webflow_portal, webflow_schedule
from illumenate_lighting.illumenate_lighting.dealer_permissions import (
	DEALER_ROLE,
	apply_dealer_permissions,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
	can_convert_schedule_to_order,
)

DEALER_USER = "_test_dealer_conv@example.com"
UNLINKED_DEALER_USER = "_test_dealer_nolink@example.com"
COLLABORATOR_USER = "_test_collab_conv@example.com"

DEALER_CUSTOMER = "_Test Dealer Conv Customer"
TEMPLATE_CODE = "_TestConvTemplate"
PROFILE_ITEM = "_Test Conv Profile Item"
NO_BOM_ITEM = "_Test Conv No BOM Item"
CONFIG_OK = "_test_conv_config_ok"
CONFIG_NO_BOM = "_test_conv_config_no_bom"


class TestDealerOrderConversion(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._ensure_role()
		apply_dealer_permissions()
		self._ensure_masters()
		self._ensure_users()
		self._ensure_project()

	def tearDown(self):
		frappe.set_user("Administrator")
		for so in frappe.get_all(
			"Sales Order", filters={"customer": DEALER_CUSTOMER}, pluck="name"
		):
			frappe.delete_doc("Sales Order", so, force=True, ignore_permissions=True)
		for schedule in frappe.get_all(
			"ilL-Project-Fixture-Schedule",
			filters={"schedule_name": ["like", "_Test Conv%"]},
			pluck="name",
		):
			frappe.delete_doc(
				"ilL-Project-Fixture-Schedule", schedule, force=True, ignore_permissions=True
			)

	# ------------------------------------------------------------------
	# fixtures
	# ------------------------------------------------------------------

	def _ensure_role(self):
		if not frappe.db.exists("Role", DEALER_ROLE):
			role = frappe.new_doc("Role")
			role.role_name = DEALER_ROLE
			role.desk_access = 1
			role.insert(ignore_permissions=True)

	def _ensure_masters(self):
		if not frappe.db.exists("Customer", DEALER_CUSTOMER):
			customer = frappe.new_doc("Customer")
			customer.customer_name = DEALER_CUSTOMER
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		if not frappe.db.exists("Item", PROFILE_ITEM):
			item = frappe.new_doc("Item")
			item.item_code = PROFILE_ITEM
			item.item_name = PROFILE_ITEM
			item.item_group = "Products"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)

		if not frappe.db.exists("Item", NO_BOM_ITEM):
			item = frappe.new_doc("Item")
			item.item_code = NO_BOM_ITEM
			item.item_name = NO_BOM_ITEM
			item.item_group = "Products"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)

		if not frappe.db.exists("ilL-Fixture-Template", TEMPLATE_CODE):
			template = frappe.new_doc("ilL-Fixture-Template")
			template.template_code = TEMPLATE_CODE
			template.template_name = "Test Conv Template"
			template.is_active = 1
			template.insert(ignore_permissions=True)

		# Buildable fixture: has a profile component so a BOM can be generated.
		if not frappe.db.exists("ilL-Configured-Fixture", CONFIG_OK):
			fixture = frappe.new_doc("ilL-Configured-Fixture")
			fixture.config_hash = CONFIG_OK
			fixture.fixture_template = TEMPLATE_CODE
			fixture.engine_version = "1.0.0"
			fixture.requested_overall_length_mm = 1000
			fixture.manufacturable_overall_length_mm = 995
			fixture.runs_count = 1
			fixture.total_watts = 15.5
			fixture.profile_item = PROFILE_ITEM
			fixture.insert(ignore_permissions=True)

		# Unbuildable fixture: the Item exists but there are no component
		# mappings, so BOM generation fails and the conversion must abort.
		if not frappe.db.exists("ilL-Configured-Fixture", CONFIG_NO_BOM):
			fixture = frappe.new_doc("ilL-Configured-Fixture")
			fixture.config_hash = CONFIG_NO_BOM
			fixture.fixture_template = TEMPLATE_CODE
			fixture.engine_version = "1.0.0"
			fixture.requested_overall_length_mm = 1000
			fixture.manufacturable_overall_length_mm = 995
			fixture.runs_count = 1
			fixture.total_watts = 15.5
			fixture.configured_item = NO_BOM_ITEM
			fixture.insert(ignore_permissions=True)

	def _ensure_user(self, email, roles):
		if not frappe.db.exists("User", email):
			user = frappe.new_doc("User")
			user.email = email
			user.first_name = email.split("@")[0]
			user.send_welcome_email = 0
			user.user_type = "System User"
			user.insert(ignore_permissions=True)
		else:
			user = frappe.get_doc("User", email)

		existing = {r.role for r in user.roles}
		missing = [r for r in roles if r not in existing]
		if missing:
			for role in missing:
				user.append("roles", {"role": role})
			user.save(ignore_permissions=True)
		return user

	def _link_contact(self, email, customer):
		contact_name = frappe.db.get_value("Contact", {"user": email}, "name")
		if contact_name:
			return contact_name

		contact = frappe.new_doc("Contact")
		contact.first_name = email.split("@")[0]
		contact.user = email
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": customer})
		contact.insert(ignore_permissions=True)
		return contact.name

	def _ensure_users(self):
		self._ensure_user(DEALER_USER, [DEALER_ROLE])
		self._link_contact(DEALER_USER, DEALER_CUSTOMER)

		# Dealer role, but no Contact → Customer link at all.
		self._ensure_user(UNLINKED_DEALER_USER, [DEALER_ROLE])

		# Portal collaborator: no Dealer role.
		self._ensure_user(COLLABORATOR_USER, [])

	def _ensure_project(self):
		name = frappe.db.get_value("ilL-Project", {"project_name": "_Test Conv Project"})
		if name:
			self.project = frappe.get_doc("ilL-Project", name)
		else:
			self.project = frappe.new_doc("ilL-Project")
			self.project.project_name = "_Test Conv Project"
			self.project.customer = DEALER_CUSTOMER
			self.project.owner_customer = DEALER_CUSTOMER
			self.project.insert(ignore_permissions=True)

		if not any(c.user == COLLABORATOR_USER for c in self.project.collaborators or []):
			self.project.append(
				"collaborators",
				{"user": COLLABORATOR_USER, "access_level": "EDIT", "is_active": 1},
			)
			self.project.save(ignore_permissions=True)

	def _make_schedule(self, suffix, config_hash=CONFIG_OK, status="READY"):
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = f"_Test Conv {suffix}"
		schedule.ill_project = self.project.name
		schedule.customer = DEALER_CUSTOMER
		schedule.status = status
		schedule.append(
			"lines",
			{
				"line_id": "L1",
				"qty": 2,
				"manufacturer_type": "ILLUMENATE",
				"configured_fixture": config_hash,
			},
		)
		schedule.insert(ignore_permissions=True)
		return schedule

	# ------------------------------------------------------------------
	# dealer permissions
	# ------------------------------------------------------------------

	def test_dealer_with_create_permission_can_convert(self):
		schedule = self._make_schedule("Dealer Allowed")

		frappe.set_user(DEALER_USER)
		result = portal.create_schedule_sales_order(schedule.name)

		self.assertTrue(result.get("success"), result.get("error"))
		self.assertTrue(frappe.db.exists("Sales Order", result["sales_order"]))

		frappe.set_user("Administrator")
		schedule.reload()
		# A draft Sales Order is only an order request until our team submits it.
		self.assertEqual(schedule.status, "ORDER_REQUESTED")
		self.assertEqual(schedule.sales_order, result["sales_order"])

	def test_submitting_the_order_marks_the_schedule_ordered(self):
		from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
			on_sales_order_cancel,
			on_sales_order_submit,
			on_sales_order_trash,
		)

		schedule = self._make_schedule("Lifecycle")
		frappe.set_user(DEALER_USER)
		result = portal.create_schedule_sales_order(schedule.name)
		frappe.set_user("Administrator")
		self.assertTrue(result.get("success"), result.get("error"))
		so = frappe.get_doc("Sales Order", result["sales_order"])

		on_sales_order_submit(so)
		schedule.reload()
		self.assertEqual(schedule.status, "ORDERED")

		on_sales_order_cancel(so)
		schedule.reload()
		self.assertEqual(schedule.status, "ISSUE")
		self.assertIn("sales@illumenate.lighting", schedule.status_note or "")

		# Deleting an un-submitted request is also an exception state.
		schedule.set_lifecycle_status("ORDER_REQUESTED", sales_order=so.name)
		on_sales_order_trash(so)
		schedule.reload()
		self.assertEqual(schedule.status, "ISSUE")

	def test_dealer_without_create_permission_is_blocked_and_rolls_back(self):
		"""No Sales Order create permission → no order and no orphan Item/BOM.

		``append_quote_lines`` writes Items, Item Prices and BOMs *before*
		``so.insert()``, so this is also the "failure after Item/BOM creation but
		before Sales Order insertion" case.
		"""
		schedule = self._make_schedule("Dealer Denied")
		bom_before = frappe.db.get_value("ilL-Configured-Fixture", CONFIG_OK, "bom")
		update_permission_property(
			"Sales Order", DEALER_ROLE, 0, "create", 0, validate=False
		)

		try:
			frappe.set_user(DEALER_USER)
			with self.assertRaises(frappe.PermissionError):
				schedule.create_sales_order_result()
		finally:
			frappe.set_user("Administrator")
			update_permission_property(
				"Sales Order", DEALER_ROLE, 0, "create", 1, validate=False
			)

		self.assertIsNone(
			frappe.db.get_value("Sales Order", {"ill_fixture_schedule": schedule.name}, "name")
		)
		schedule.reload()
		self.assertEqual(schedule.status, "READY")
		# The savepoint rollback must have undone the manufacturing writes.
		self.assertEqual(
			frappe.db.get_value("ilL-Configured-Fixture", CONFIG_OK, "bom"), bom_before
		)

	def test_dealer_without_customer_link_is_denied(self):
		schedule = self._make_schedule("Dealer No Link")

		frappe.set_user(UNLINKED_DEALER_USER)
		allowed, reason = can_convert_schedule_to_order(schedule, UNLINKED_DEALER_USER)

		self.assertFalse(allowed)
		self.assertIn("permission", reason.lower())

		result = portal.create_schedule_sales_order(schedule.name)
		self.assertFalse(result.get("success"))

	def test_edit_collaborator_cannot_convert_ready_schedule(self):
		"""EDIT access is enough to change a schedule, not to place an order."""
		schedule = self._make_schedule("Collab Ready")

		allowed, reason = can_convert_schedule_to_order(schedule, COLLABORATOR_USER)
		self.assertFalse(allowed)
		self.assertIn("dealer", reason.lower())

		frappe.set_user(COLLABORATOR_USER)
		result = portal.create_schedule_sales_order(schedule.name)
		self.assertFalse(result.get("success"))

		frappe.set_user("Administrator")
		self.assertIsNone(
			frappe.db.get_value("Sales Order", {"ill_fixture_schedule": schedule.name}, "name")
		)

	def test_edit_collaborator_cannot_convert_quoted_schedule(self):
		"""Only Dealers and internal users place orders, even once quoted."""
		schedule = self._make_schedule("Collab Quoted", status="QUOTED")

		allowed, _reason = can_convert_schedule_to_order(schedule, COLLABORATOR_USER)
		self.assertFalse(allowed)

		allowed, _reason = can_convert_schedule_to_order(schedule, DEALER_USER)
		self.assertTrue(allowed)

	def test_guest_cannot_convert(self):
		schedule = self._make_schedule("Guest")

		allowed, _reason = can_convert_schedule_to_order(schedule, "Guest")
		self.assertFalse(allowed)

	# ------------------------------------------------------------------
	# idempotency / atomicity
	# ------------------------------------------------------------------

	def test_duplicate_conversion_returns_the_same_order(self):
		schedule = self._make_schedule("Duplicate")

		first = schedule.create_sales_order_result()
		self.assertFalse(first.get("already_existed"))

		schedule.reload()
		second = schedule.create_sales_order_result()

		self.assertTrue(second.get("already_existed"))
		self.assertEqual(first["sales_order"], second["sales_order"])

		orders = frappe.get_all(
			"Sales Order", filters={"ill_fixture_schedule": schedule.name}, pluck="name"
		)
		self.assertEqual(len(orders), 1)

	def test_duplicate_conversion_through_portal_endpoint(self):
		schedule = self._make_schedule("Duplicate Portal")

		frappe.set_user(DEALER_USER)
		first = portal.create_schedule_sales_order(schedule.name)
		second = portal.create_schedule_sales_order(schedule.name)
		frappe.set_user("Administrator")

		self.assertTrue(first.get("success"), first.get("error"))
		self.assertTrue(second.get("success"), second.get("error"))
		self.assertTrue(second.get("already_existed"))
		self.assertEqual(first["sales_order"], second["sales_order"])

	def test_bom_failure_aborts_the_whole_conversion(self):
		"""A manufactured fixture with no BOM must not become an order line."""
		schedule = self._make_schedule("No BOM", config_hash=CONFIG_NO_BOM)

		with self.assertRaises(frappe.ValidationError) as ctx:
			schedule.create_sales_order_result()

		self.assertIn("BOM", str(ctx.exception))
		self.assertIsNone(
			frappe.db.get_value("Sales Order", {"ill_fixture_schedule": schedule.name}, "name")
		)
		schedule.reload()
		self.assertEqual(schedule.status, "READY")
		# BOM links written before the failure are rolled back.
		self.assertFalse(frappe.db.get_value("ilL-Configured-Fixture", CONFIG_NO_BOM, "bom"))

	# ------------------------------------------------------------------
	# draft order visibility
	# ------------------------------------------------------------------

	def test_draft_order_is_visible_to_the_dealer_as_an_order_request(self):
		schedule = self._make_schedule("Draft Visible")

		frappe.set_user(DEALER_USER)
		created = portal.create_schedule_sales_order(schedule.name)
		self.assertTrue(created.get("success"), created.get("error"))

		details = portal.get_order_details(created["sales_order"])
		frappe.set_user("Administrator")

		self.assertTrue(details.get("success"), details.get("error"))
		self.assertEqual(details["order"]["docstatus"], 0)
		self.assertTrue(details["order"]["is_request"])

		schedule.reload()
		self.assertEqual(schedule.status, "ORDER_REQUESTED")

	def test_order_of_another_customer_is_not_visible(self):
		schedule = self._make_schedule("Foreign Order")
		result = schedule.create_sales_order_result()

		frappe.set_user(UNLINKED_DEALER_USER)
		details = portal.get_order_details(result["sales_order"])
		frappe.set_user("Administrator")

		self.assertFalse(details.get("success"))

	# ------------------------------------------------------------------
	# customer / contact endpoints
	# ------------------------------------------------------------------

	def test_create_customer_requires_dealer_or_internal_role(self):
		frappe.set_user(COLLABORATOR_USER)
		result = portal.create_customer({"customer_name": "_Test Conv Rogue Customer"})
		frappe.set_user("Administrator")

		self.assertFalse(result.get("success"))
		self.assertFalse(frappe.db.exists("Customer", "_Test Conv Rogue Customer"))

	def test_dealer_can_create_customer_without_choosing_customer_group(self):
		frappe.set_user(DEALER_USER)
		result = portal.create_customer(
			{
				"customer_name": "_Test Conv Dealer Customer",
				"customer_group": "_Nonexistent Group",
			}
		)
		frappe.set_user("Administrator")

		self.assertTrue(result.get("success"), result.get("error"))
		created = frappe.get_doc("Customer", result["customer_name"])
		self.assertNotEqual(created.customer_group, "_Nonexistent Group")

		frappe.delete_doc("Customer", created.name, force=True, ignore_permissions=True)

	def test_create_contact_requires_dealer_or_internal_role(self):
		frappe.set_user(COLLABORATOR_USER)
		result = portal.create_contact({"first_name": "_TestConvRogue"})
		frappe.set_user("Administrator")

		self.assertFalse(result.get("success"))

	def test_dealer_contact_is_linked_to_the_dealer_customer(self):
		frappe.set_user(DEALER_USER)
		result = portal.create_contact(
			{"first_name": "_TestConvDealerContact", "email_id": "_testconvcontact@example.com"}
		)
		frappe.set_user("Administrator")

		self.assertTrue(result.get("success"), result.get("error"))
		contact = frappe.get_doc("Contact", result["contact_name"])
		self.assertIn(DEALER_CUSTOMER, [link.link_name for link in contact.links])

		frappe.delete_doc("Contact", contact.name, force=True, ignore_permissions=True)

	# ------------------------------------------------------------------
	# configured-record scoping
	# ------------------------------------------------------------------

	def test_configured_fixture_details_are_schedule_scoped(self):
		self._make_schedule("Scoped")

		frappe.set_user(COLLABORATOR_USER)
		allowed = portal.get_configured_fixture_details(CONFIG_OK)
		frappe.set_user(UNLINKED_DEALER_USER)
		denied = portal.get_configured_fixture_details(CONFIG_OK)
		frappe.set_user("Administrator")

		self.assertTrue(allowed.get("success"), allowed.get("error"))
		self.assertFalse(denied.get("success"))

	# ------------------------------------------------------------------
	# webflow endpoints
	# ------------------------------------------------------------------

	def test_webflow_get_projects_hides_private_projects(self):
		private = frappe.new_doc("ilL-Project")
		private.project_name = "_Test Conv Private Project"
		private.customer = DEALER_CUSTOMER
		private.owner_customer = DEALER_CUSTOMER
		private.is_private = 1
		private.insert(ignore_permissions=True)

		try:
			frappe.set_user(COLLABORATOR_USER)
			result = webflow_portal.get_projects()
			frappe.set_user("Administrator")

			self.assertTrue(result.get("success"), result.get("error"))
			self.assertNotIn(private.name, [p["name"] for p in result["projects"]])
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("ilL-Project", private.name, force=True, ignore_permissions=True)

	def test_webflow_update_line_quantity_writes_qty(self):
		schedule = self._make_schedule("Qty Update")
		line_name = schedule.lines[0].name

		result = webflow_schedule.update_line_quantity(line_name, 7)

		self.assertTrue(result.get("success"), result.get("error"))
		self.assertEqual(result["old_quantity"], 2)
		self.assertEqual(
			frappe.db.get_value("ilL-Child-Fixture-Schedule-Line", line_name, "qty"), 7
		)

	# ------------------------------------------------------------------
	# installer / migration
	# ------------------------------------------------------------------

	def test_apply_dealer_permissions_is_idempotent(self):
		apply_dealer_permissions()
		self.assertEqual(apply_dealer_permissions(), [])

	def test_dealer_permissions_are_least_privilege(self):
		apply_dealer_permissions()

		self.assertEqual(self._perm("Sales Order", "create"), 1)
		self.assertEqual(self._perm("Sales Order", "read"), 1)
		self.assertEqual(self._perm("Sales Order", "write"), 0)
		self.assertEqual(self._perm("Sales Order", "submit"), 0)
		self.assertEqual(self._perm("Sales Order", "delete"), 0)

		# The portal creates Customers/Contacts through role-gated whitelisted
		# endpoints, so the role itself must stay read-only on those masters.
		self.assertEqual(self._perm("Customer", "write"), 0)
		self.assertEqual(self._perm("Customer", "create"), 0)
		self.assertEqual(self._perm("Contact", "write"), 0)

	def test_dealer_cannot_see_another_customers_sales_order(self):
		other_customer = "_Test Conv Other Customer"
		if not frappe.db.exists("Customer", other_customer):
			customer = frappe.new_doc("Customer")
			customer.customer_name = other_customer
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		from illumenate_lighting.illumenate_lighting.dealer_permissions import (
			sales_order_has_permission,
		)

		mine = frappe._dict({"customer": DEALER_CUSTOMER, "owner": "Administrator"})
		theirs = frappe._dict({"customer": other_customer, "owner": "Administrator"})

		self.assertTrue(sales_order_has_permission(mine, "read", DEALER_USER))
		self.assertFalse(sales_order_has_permission(theirs, "read", DEALER_USER))
		# Internal users are never restricted.
		self.assertTrue(sales_order_has_permission(theirs, "read", "Administrator"))

	@staticmethod
	def _perm(doctype, ptype):
		table = (
			"Custom DocPerm"
			if frappe.db.exists("Custom DocPerm", {"parent": doctype})
			else "DocPerm"
		)
		return int(
			frappe.db.get_value(
				table,
				{"parent": doctype, "role": DEALER_ROLE, "permlevel": 0},
				ptype,
			)
			or 0
		)
