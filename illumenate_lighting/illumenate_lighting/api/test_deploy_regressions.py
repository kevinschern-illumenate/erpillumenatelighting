"""Installed-site regressions for the September 29, 2026 Phase 2 deployment fixes.

Run on a migrated test site with bench run-tests --module
illumenate_lighting.illumenate_lighting.api.test_deploy_regressions.
These use Frappe's real permission engine and database, which the portal_unit
stubs cannot: Frappe v16 treats a None has_permission hook result as a denial.
"""

import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from illumenate_lighting import portal_workspace
from illumenate_lighting.illumenate_lighting.portal import order_review

PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"


def _system_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(*roles)
	return email


class TestDeployRegressions(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_non_administrators_can_upload_edit_and_delete_attachments(self):
		for email, roles in (
			("ill-regression-manager@example.com", ["System Manager"]),
			("ill-regression-sales@example.com", ["Sales User"]),
		):
			with self.subTest(user=email):
				frappe.set_user(_system_user(email, roles))
				todo = frappe.get_doc({"doctype": "ToDo", "description": "Attachment regression"}).insert()
				attachment = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": "regression-note.txt",
						"content": b"attachment regression",
						"attached_to_doctype": "ToDo",
						"attached_to_name": todo.name,
						"is_private": 1,
					}
				).insert()
				for ptype in ("read", "write", "delete"):
					self.assertTrue(frappe.has_permission("File", ptype, attachment), ptype)
				self.assertTrue(attachment.is_downloadable())
				attachment.delete()
				frappe.set_user("Administrator")

	def test_system_manager_uploads_webflow_product_featured_image(self):
		# The scenario the removed permission diagnostic reproduced (recovery plan §6.1).
		slug = "ill-regression-" + frappe.generate_hash(length=10)
		frappe.get_doc(
			{
				"doctype": "ilL-Webflow-Product",
				"name": slug,
				"product_slug": slug,
				"product_name": "Regression Product",
				"product_type": "LED Tape",
			}
		).db_insert()
		try:
			frappe.set_user(_system_user("ill-regression-manager@example.com", ["System Manager"]))
			image = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "regression-featured.png",
					"content": base64.b64decode(PNG_1X1),
					"attached_to_doctype": "ilL-Webflow-Product",
					"attached_to_name": slug,
					"attached_to_field": "featured_image",
					"is_private": 0,
				}
			).insert()
			for ptype in ("read", "write", "delete"):
				self.assertTrue(frappe.has_permission("File", ptype, image), ptype)
			image.delete()
		finally:
			frappe.set_user("Administrator")
			frappe.db.delete("ilL-Webflow-Product", {"name": slug})

	def test_other_users_private_attachment_stays_denied(self):
		frappe.set_user(_system_user("ill-regression-owner@example.com", ["System Manager"]))
		todo = frappe.get_doc({"doctype": "ToDo", "description": "Private owner"}).insert()
		attachment = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "private-owner.txt",
				"content": b"not for other users",
				"attached_to_doctype": "ToDo",
				"attached_to_name": todo.name,
				"is_private": 1,
			}
		).insert()
		outsider = _system_user("ill-regression-outsider@example.com", ["Sales User"])
		self.assertFalse(frappe.has_permission("File", "read", attachment, user=outsider))

	def test_schedule_linked_order_without_intake_keeps_native_submit(self):
		frappe.set_user(_system_user("ill-regression-sales@example.com", ["Sales User"]))
		order = frappe.new_doc("Sales Order")
		order.name = "SO-ILL-NATIVE-REGRESSION"
		order.ill_fixture_schedule = "SCHEDULE-FROM-QUOTATION"
		order.ill_confirmed_delivery_date = "2020-01-01"
		order.delivery_date = "2026-12-01"
		self.assertFalse(order_review._portal_governed(order))
		order_review.validate_order(order)
		order_review.before_submit(order)
		order_review.on_submit(order)
		self.assertEqual(order.ill_delivery_confirmed_by, frappe.session.user)
		self.assertEqual(str(order.delivery_date), "2026-12-01")

	def test_portal_intake_and_its_amendments_stay_governed(self):
		intake = frappe.get_doc(
			{"doctype": order_review.DOCTYPE, "name": "OI-ILL-REGRESSION", "sales_order": "SO-ILL-PORTAL"}
		)
		intake.db_insert()
		portal = frappe._dict(name="SO-ILL-PORTAL", ill_fixture_schedule="S")
		amendment = frappe._dict(
			name="SO-ILL-PORTAL-1", ill_fixture_schedule="S", amended_from="SO-ILL-PORTAL"
		)
		self.assertTrue(order_review._portal_governed(portal))
		self.assertTrue(order_review._portal_governed(amendment))
		self.assertFalse(order_review._portal_governed(frappe._dict(name="SO-ILL-PORTAL")))

	def test_workspace_hook_failure_is_logged_and_rolled_back(self):
		with (
			tempfile.TemporaryDirectory() as temporary,
			patch.object(portal_workspace, "_directory", return_value=Path(temporary)),
		):
			pending = Path(temporary) / "pending.json"
			pending.write_text(json.dumps({"backup": "missing.json"}), encoding="utf-8")
			before = frappe.db.count("Error Log")
			portal_workspace.after_migrate()
			self.assertTrue(pending.exists())
			self.assertEqual(frappe.db.count("Error Log"), before + 1)
