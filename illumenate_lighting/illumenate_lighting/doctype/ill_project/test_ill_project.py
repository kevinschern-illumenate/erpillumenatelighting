# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestilLProject(FrappeTestCase):
	"""Test cases for ilL-Project DocType"""

	def setUp(self):
		"""Set up test data"""
		# Create test customer
		self.test_customer = self._ensure_customer("Test Customer for Project")

		# Create test users
		self.user1 = self._ensure_user("test_project_user1@example.com", "Test User 1")
		self.user2 = self._ensure_user("test_project_user2@example.com", "Test User 2")
		self.user3 = self._ensure_user("test_project_user3@example.com", "Test User 3")

		# Link user1 and user2 to test customer via Contact
		self._link_user_to_customer(self.user1, self.test_customer)
		self._link_user_to_customer(self.user2, self.test_customer)
		# user3 is NOT linked to any customer

	def _ensure_customer(self, customer_name):
		"""Create a customer if it doesn't exist"""
		if not frappe.db.exists("Customer", customer_name):
			customer = frappe.new_doc("Customer")
			customer.customer_name = customer_name
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)
			return customer.name
		return customer_name

	def _ensure_user(self, email, full_name):
		"""Create a user if it doesn't exist"""
		if not frappe.db.exists("User", email):
			user = frappe.new_doc("User")
			user.email = email
			user.first_name = full_name
			user.send_welcome_email = 0
			user.insert(ignore_permissions=True)
		return email

	def _link_user_to_customer(self, user, customer):
		"""Link a user to a customer via Contact"""
		# Check if contact already exists
		existing_contact = frappe.db.get_value("Contact", {"user": user}, "name")
		if existing_contact:
			contact = frappe.get_doc("Contact", existing_contact)
		else:
			contact = frappe.new_doc("Contact")
			contact.first_name = user.split("@")[0]
			contact.user = user

		# Add customer link if not already present
		has_customer_link = False
		for link in contact.links or []:
			if link.link_doctype == "Customer" and link.link_name == customer:
				has_customer_link = True
				break

		if not has_customer_link:
			contact.append("links", {
				"link_doctype": "Customer",
				"link_name": customer,
			})

		contact.save(ignore_permissions=True)

	def test_create_project(self):
		"""Test creating a basic project"""
		project = frappe.new_doc("ilL-Project")
		project.project_name = "Test Project 1"
		project.customer = self.test_customer
		project.insert()

		self.assertIsNotNone(project.name)
		self.assertEqual(project.project_name, "Test Project 1")
		self.assertEqual(project.customer, self.test_customer)
		self.assertFalse(project.is_private)
		self.assertTrue(project.is_active)

	def test_create_private_project_with_collaborators(self):
		"""Test creating a private project with collaborators"""
		project = frappe.new_doc("ilL-Project")
		project.project_name = "Private Project"
		project.customer = self.test_customer
		project.is_private = 1
		project.append("collaborators", {
			"user": self.user2,
			"access_level": "VIEW",
			"is_active": 1,
		})
		project.insert()

		self.assertTrue(project.is_private)
		self.assertEqual(len(project.collaborators), 1)
		self.assertEqual(project.collaborators[0].user, self.user2)
		self.assertIsNotNone(project.collaborators[0].added_on)

	def test_permission_query_company_visible(self):
		"""Test that company-visible projects are accessible to all users from same customer"""
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			get_permission_query_conditions,
		)

		# Create a non-private project
		project = frappe.new_doc("ilL-Project")
		project.project_name = "Company Visible Project"
		project.customer = self.test_customer
		project.is_private = 0
		project.insert()

		# Get conditions for user1 (linked to customer)
		conditions = get_permission_query_conditions(self.user1)

		# Conditions should allow access to company-visible projects
		self.assertIn("is_private = 0", conditions)

	def test_permission_query_private_owner(self):
		"""Test that private projects are visible to owner"""
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			has_permission,
		)

		# Create a private project as Administrator
		project = frappe.new_doc("ilL-Project")
		project.project_name = "Private Owner Project"
		project.customer = self.test_customer
		project.is_private = 1
		project.insert()

		# Owner should have permission
		self.assertTrue(has_permission(project, "read", project.owner))

	def test_permission_query_private_collaborator(self):
		"""Test that private projects are visible to collaborators"""
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			has_permission,
		)

		# Create a private project with user2 as collaborator
		project = frappe.new_doc("ilL-Project")
		project.project_name = "Private Collaborator Project"
		project.customer = self.test_customer
		project.is_private = 1
		project.append("collaborators", {
			"user": self.user2,
			"access_level": "VIEW",
			"is_active": 1,
		})
		project.insert()

		# User2 (collaborator) should have permission
		self.assertTrue(has_permission(project, "read", self.user2))

		# User3 (not a collaborator) should NOT have permission
		self.assertFalse(has_permission(project, "read", self.user3))

	def test_collaborator_edit_access(self):
		"""Test that collaborator with EDIT access can write"""
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			has_permission,
		)

		project = frappe.new_doc("ilL-Project")
		project.project_name = "Edit Access Project"
		project.customer = self.test_customer
		project.is_private = 1
		project.append("collaborators", {
			"user": self.user2,
			"access_level": "EDIT",
			"is_active": 1,
		})
		project.insert()

		# User2 with EDIT access should have write permission
		self.assertTrue(has_permission(project, "write", self.user2))

	def test_collaborator_view_only_access(self):
		"""Test that collaborator with VIEW access cannot write"""
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
			has_permission,
		)

		project = frappe.new_doc("ilL-Project")
		project.project_name = "View Only Access Project"
		project.customer = self.test_customer
		project.is_private = 1
		project.append("collaborators", {
			"user": self.user2,
			"access_level": "VIEW",
			"is_active": 1,
		})
		project.insert()

		# User2 with VIEW access should have read but not write permission
		self.assertTrue(has_permission(project, "read", self.user2))
		self.assertFalse(has_permission(project, "write", self.user2))

	def tearDown(self):
		"""Clean up test data"""
		# Delete test projects
		test_projects = frappe.get_all(
			"ilL-Project",
			filters={"customer": self.test_customer},
			pluck="name",
		)
		for project_name in test_projects:
			frappe.delete_doc("ilL-Project", project_name, force=True)
