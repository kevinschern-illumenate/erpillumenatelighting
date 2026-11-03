"""Site-config values arrive typed differently depending on how Frappe Cloud stores them."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service


class SiteFlags(unittest.TestCase):
	def test_boolean_flag_accepts_every_stored_form(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			self.assertFalse(flags.conf_flag("ill_portal_fixture_groups"))
			for value, expected in (
				(True, True),
				(1, True),
				("true", True),
				("1", True),
				(False, False),
				(0, False),
				("false", False),
				("0", False),
				("", False),
			):
				with self.subTest(value=value):
					frappe.conf["ill_portal_fixture_groups"] = value
					self.assertIs(flags.conf_flag("ill_portal_fixture_groups"), expected)
			frappe.log_error.assert_not_called()

	def test_unreadable_flag_uses_default_and_is_logged_once(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			frappe.conf["ill_portal_fixture_groups"] = "enabled"
			self.assertFalse(flags.conf_flag("ill_portal_fixture_groups"))
			self.assertTrue(flags.conf_flag("ill_portal_fixture_groups", default=True))
			frappe.log_error.assert_called_once()

	def test_fixture_groups_are_on_unless_a_site_turns_them_off(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			self.assertTrue(flags.fixture_groups_enabled())
			for value in (False, 0, "false", "0"):
				with self.subTest(value=value):
					frappe.conf["ill_portal_fixture_groups"] = value
					self.assertFalse(flags.fixture_groups_enabled())

	def test_upload_switches_are_on_unless_a_site_turns_them_off(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			self.assertTrue(flags.heic_uploads_enabled())
			on = {"upload_widget": True, "upload_purpose": True, "gallery": True}
			self.assertEqual(flags.portal_client_flags(), on)
			frappe.conf["ill_portal_heic_uploads"] = "false"
			frappe.conf["ill_portal_upload_widget"] = 0
			self.assertFalse(flags.heic_uploads_enabled())
			self.assertEqual(flags.portal_client_flags(), {**on, "upload_widget": False})

	def test_media_switches_are_on_unless_a_site_turns_them_off(self):
		switches = {
			"upload_purpose_enabled": "ill_portal_upload_purpose",
			"thumbnails_enabled": "ill_portal_thumbnails",
			"gallery_enabled": "ill_portal_gallery",
			"dealer_logo_enabled": "ill_portal_dealer_logo",
			"staff_heic_enabled": "ill_desk_heic_conversion",
			"upload_duplicate_check_enabled": "ill_portal_upload_duplicate_check",
		}
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			for function, key in switches.items():
				with self.subTest(key=key):
					self.assertTrue(getattr(flags, function)())
					frappe.conf[key] = "false"
					self.assertFalse(getattr(flags, function)())
			client = flags.portal_client_flags()
			self.assertFalse(client["upload_purpose"])
			self.assertFalse(client["gallery"])

	def test_portal_layout_publishes_client_flags_as_json(self):
		from pathlib import Path

		root = Path(__file__).resolve().parents[2]
		base = (root / "illumenate_lighting/templates/portal_base.html").read_text(encoding="utf-8")
		self.assertIn('id="ill-portal-flags">{{ ill_portal_client_flags() | tojson }}</script>', base)
		hooks = (root / "illumenate_lighting/hooks.py").read_text(encoding="utf-8")
		self.assertIn("portal.jinja_methods.ill_portal_client_flags", hooks)

	def test_list_accepts_json_and_json_strings(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			frappe.log_error = MagicMock()
			self.assertIsNone(flags.conf_list("ill_portal_pilot_users"))
			frappe.conf["ill_portal_pilot_users"] = ["a@example.com"]
			self.assertEqual(flags.conf_list("ill_portal_pilot_users"), ["a@example.com"])
			frappe.conf["ill_portal_pilot_users"] = '["b@example.com"]'
			self.assertEqual(flags.conf_list("ill_portal_pilot_users"), ["b@example.com"])
			frappe.conf["ill_portal_pilot_users"] = "[]"
			self.assertEqual(flags.conf_list("ill_portal_pilot_users"), [])
			for invalid in ("a@example.com", '{"a": 1}', [1, 2]):
				with self.subTest(value=invalid):
					frappe.conf["ill_portal_pilot_users"] = invalid
					self.assertIsNone(flags.conf_list("ill_portal_pilot_users"))
			self.assertEqual(frappe.log_error.call_count, 3)


if __name__ == "__main__":
	unittest.main()
