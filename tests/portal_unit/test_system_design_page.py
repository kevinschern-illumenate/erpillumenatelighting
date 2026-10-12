"""The System Designer portal page: who gets the app, who is redirected, and what the mount receives."""

import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

PAGE = "illumenate_lighting.templates.pages.system_design"


def page(user="dealer@example.com", exists=True, can_read=True, enabled=True, schedule="SCH-0001"):
	access = types.SimpleNamespace(can_read_schedule=MagicMock(return_value=can_read))
	settings = types.SimpleNamespace(is_enabled_for=MagicMock(return_value=enabled))
	context = load_service(
		PAGE,
		{ROOT + ".portal.access": access, ROOT + ".system_design.settings": settings},
	)

	class Page:
		def __enter__(self):
			module, frappe = context.__enter__()
			frappe.session.user = user
			frappe.form_dict = Record(schedule=schedule)
			frappe.request = SimpleNamespace(
				path="/portal/schedules/SCH-0001/design", query_string=b"tab=power"
			)
			frappe.local.flags = Record()
			frappe.Redirect = type("Redirect", (Exception,), {})
			frappe.sessions = SimpleNamespace(get_csrf_token=MagicMock(return_value="test-csrf"))
			frappe.db.exists.return_value = exists
			frappe.get_doc.return_value = Record(name=schedule)
			self.access, self.settings = access, settings
			return module, frappe

		def __exit__(self, *exc):
			return context.__exit__(*exc)

	return Page()


class SystemDesignPage(unittest.TestCase):
	def test_guest_goes_to_login_with_return_path(self):
		with page(user="Guest") as (module, frappe):
			with self.assertRaises(frappe.Redirect):
				module.get_context({})
			self.assertEqual(
				frappe.local.flags.redirect_location,
				"/login?redirect-to=%2Fportal%2Fschedules%2FSCH-0001%2Fdesign%3Ftab%3Dpower",
			)
			frappe.sessions.get_csrf_token.assert_not_called()

	def test_missing_and_unreadable_schedules_are_not_found(self):
		for kwargs in ({"exists": False}, {"can_read": False}):
			with self.subTest(**kwargs), page(**kwargs) as (module, frappe):
				with self.assertRaises(LookupError):
					module.get_context({})
				frappe.sessions.get_csrf_token.assert_not_called()

	def test_users_without_the_designer_return_to_the_schedule(self):
		with page(enabled=False) as (module, frappe):
			with self.assertRaises(frappe.Redirect):
				module.get_context({})
			self.assertEqual(frappe.local.flags.redirect_location, "/portal/schedules/SCH-0001")
		with page(enabled=False, schedule=None) as (module, frappe):
			with self.assertRaises(frappe.Redirect):
				module.get_context({})
			self.assertEqual(frappe.local.flags.redirect_location, "/portal/projects")

	def test_authorized_user_gets_mount_options(self):
		with page() as (module, _frappe):
			with tempfile.TemporaryDirectory() as directory:
				bundle = Path(directory) / "designer.js"
				bundle.write_text("// bundle", encoding="utf-8")
				with patch.object(module, "BUNDLE", bundle):
					context = module.get_context({})
				self.assertEqual(context["asset_version"], int(bundle.stat().st_mtime))
			self.assertEqual(module.no_cache, 1)
			self.assertEqual(context["title"], "ilLumenate System Designer")
			self.assertEqual(context["assets"], "/assets/illumenate_lighting/system_designer/designer")
			self.assertEqual(
				context["mount_options"],
				{
					"schedule": "SCH-0001",
					"csrfToken": "test-csrf",
					"apiBase": "/api/method/illumenate_lighting.illumenate_lighting.system_design.api",
				},
			)

	def test_page_without_a_schedule_skips_the_schedule_check(self):
		with page(schedule=None) as (module, frappe):
			context = module.get_context({})
			self.assertIsNone(context["mount_options"]["schedule"])
			frappe.db.exists.assert_not_called()

	def test_bundle_path_points_at_the_committed_build(self):
		with page() as (module, _frappe):
			self.assertEqual(
				module.BUNDLE,
				Path(__file__).resolve().parents[2]
				/ "illumenate_lighting/public/system_designer/designer.js",
			)


if __name__ == "__main__":
	unittest.main()
