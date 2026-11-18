"""Phase 7: who may press Sync to Webflow, upload a spec PDF, and what the sync users need."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class SyncAccess(unittest.TestCase):
	def load(self, catalog=True, links=None):
		import test_webflow_sync

		deps = test_webflow_sync._dependencies()
		self.staff = deps[ROOT + ".portal.staff"]
		self.staff.allowed.return_value = catalog
		self.template_link = deps[ROOT + ".template_link"]
		context = load_service(ROOT + ".api.webflow_export_v2", deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_cached_value = MagicMock(return_value="System User")
		frappe.has_permission = MagicMock(return_value=True)
		frappe.db.get_value = MagicMock(return_value=Record(links or {}))
		frappe.db.exists = MagicMock(return_value=True)
		return module, frappe

	def test_the_buttons_need_the_publisher_role_before_anything_happens(self):
		module, frappe = self.load(catalog=False)
		for button in (module.trigger_sync_v2, module.trigger_publish_v2, module.request_spec_sheet):
			with (
				self.subTest(button=button.__name__),
				self.assertRaisesRegex(PermissionError, "Catalog Publisher"),
			):
				button("kit-ra02")
		frappe.get_doc.assert_not_called()
		module.request.assert_not_called()

	def test_a_linked_template_needs_write_too(self):
		module, _frappe = self.load(links={"kit_template": "KIT-RA02"})
		self.template_link.require_template_access.side_effect = PermissionError("no write on KIT-RA02")
		with self.assertRaisesRegex(PermissionError, "KIT-RA02"):
			module.trigger_sync_v2("kit-ra02")
		self.template_link.require_template_access.assert_called_once_with(
			"ilL-Extrusion-Kit-Template", "KIT-RA02"
		)

	def test_uploading_a_spec_pdf_needs_the_integration_role(self):
		module, _frappe = self.load()
		self.staff.require.side_effect = PermissionError("integration")
		with self.assertRaises(PermissionError):
			module.upload_spec_pdf()
		self.staff.require.assert_called_once_with("integration")


class SyncUsers(unittest.TestCase):
	def test_what_each_user_is_missing(self):
		with load_service(ROOT + ".webflow_promotion") as (module, _frappe):
			_roles, perms = module.expected_access("n8n")
			everything = {perm: True for perm in perms}
			self.assertEqual(
				module.access_problems("System User", 1, ["ilL Integration"], everything, "n8n"), []
			)
			problems = module.access_problems(
				"Website User", 0, [], {**everything, ("File", "create"): False}, "n8n"
			)
			self.assertEqual(
				problems,
				[
					"user is disabled",
					"user type is Website User, needs System User",
					"missing role ilL Integration",
					"cannot create File",
				],
			)
			self.assertEqual(
				module.access_problems(
					"System User",
					1,
					["System Manager"],
					{("ilL-Webflow-Product", "read"): True},
					"webflow_auto_push",
				),
				[],
			)


if __name__ == "__main__":
	unittest.main()
