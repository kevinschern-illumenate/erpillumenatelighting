"""Plan 3.14: the schedule page's dealer pricing toggle is saved per user."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


def parse_bool(value, *, default=False):
	if value in (None, ""):
		return default
	if str(value).lower() in ("1", "true"):
		return True
	if str(value).lower() in ("0", "false"):
		return False
	raise ValueError("Expected a boolean (true/false or 1/0)")


class DealerPricingPreference(unittest.TestCase):
	def setUp(self):
		self.dealer = True
		self.priced = True
		self.extras = {
			ROOT + ".api.exports": types.SimpleNamespace(_check_pricing_permission=lambda user=None: self.priced),
			ROOT + ".doctype.ill_project.ill_project": types.SimpleNamespace(_is_dealer_user=lambda user: self.dealer),
			ROOT + ".api.configuration_contract": types.SimpleNamespace(parse_bool=parse_bool),
		}

	def service(self):
		return load_service(ROOT + ".portal.user_preferences", self.extras)

	def test_unset_preference_is_off_and_a_saved_choice_wins(self):
		with self.service() as (module, frappe):
			frappe.db.get_value.return_value = None
			self.assertFalse(module.show_dealer_pricing("dealer@example.com"))
			frappe.db.get_value.assert_called_with(
				"ilL-Portal-User-Settings", {"user": "dealer@example.com"}, "show_dealer_pricing"
			)
			frappe.db.get_value.return_value = 0
			self.assertFalse(module.show_dealer_pricing("dealer@example.com"))
			frappe.db.get_value.return_value = 1
			self.assertTrue(module.show_dealer_pricing())

	def test_saving_updates_the_existing_settings_row(self):
		with self.service() as (module, frappe):
			frappe.db.get_value.return_value = "SET-1"
			self.assertEqual(module.set_show_dealer_pricing("0"), {"success": True, "show_dealer_pricing": False})
			frappe.db.set_value.assert_called_once_with("ilL-Portal-User-Settings", "SET-1", "show_dealer_pricing", 0)
			self.assertEqual(module.set_show_dealer_pricing.whitelist_options, {"methods": ["POST"]})

	def test_saving_creates_the_settings_row_when_missing(self):
		with self.service() as (module, frappe):
			frappe.db.get_value.return_value = None
			settings = Record()
			settings.set = lambda field, value: settings.__setitem__(field, value)
			settings.insert = MagicMock()
			frappe.new_doc = MagicMock(return_value=settings)
			module.set_show_dealer_pricing("true")
			frappe.new_doc.assert_called_once_with("ilL-Portal-User-Settings")
			self.assertEqual(settings["show_dealer_pricing"], 1)
			settings.insert.assert_called_once_with(ignore_permissions=True)

	def test_only_pricing_dealers_can_save_and_values_are_validated(self):
		for dealer, priced in ((False, True), (True, False)):
			self.dealer, self.priced = dealer, priced
			with self.subTest(dealer=dealer, priced=priced), self.service() as (module, frappe):
				with self.assertRaises(PermissionError):
					module.set_show_dealer_pricing(1)
				frappe.db.set_value.assert_not_called()
		self.dealer = self.priced = True
		with self.service() as (module, frappe):
			with self.assertRaisesRegex(ValueError, "Choose whether"):
				module.set_show_dealer_pricing("maybe")
			frappe.session = Record(user="Guest")
			self.assertFalse(module.can_toggle_dealer_pricing())


if __name__ == "__main__":
	unittest.main()
