"""Plan 3.8: the configurator estimate panel's lead time and tape/neon price estimate."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.estimate"
PRICING = ROOT + ".api.tape_neon_pricing"


class Estimate(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.visible = {("ilL-Driver-Template", "DRV-1"), ("ilL-LED-Sheet-Template", "LS-1")}
		self.configurator_calls = []
		self.classes = {
			"LT-STD": Record(name="LT-STD", code="STD", label="Standard", days_min=10, days_max=15),
			"LT-REV": Record(name="LT-REV", code="", label="", days_min=20, days_max=5),
			"LT-BAD": Record(name="LT-BAD", code="BAD", label="Odd", days_min="x", days_max=-3),
		}
		self.templates = {
			("ilL-Driver-Template", "DRV-1"): "LT-STD",
			("ilL-LED-Sheet-Template", "LS-1"): None,
		}
		self.offerings = {
			"OFF-1": Record(is_active=1, lead_time_class_override="LT-STD"),
			"OFF-OFF": Record(is_active=0, lead_time_class_override="LT-STD"),
			"OFF-NONE": Record(is_active=1, lead_time_class_override=None),
		}
		self.priced = []

		def require_visible(doctype, name, staff=None):
			if (doctype, name) not in self.visible:
				raise LookupError(f"{doctype} {name} not found")

		def price_result(result, template=None):
			self.priced.append((result, template))
			if self.price_error:
				raise self.price_error
			result["computed"]["total_price_msrp"] = 123.45
			return result

		self.price_error = None
		self.extras = {
			ROOT + ".portal.site_flags": types.SimpleNamespace(live_estimate_enabled=lambda: self.enabled),
			ROOT + ".portal.configurator_access": types.SimpleNamespace(
				require_configurator=lambda schedule=None, user=None: self.configurator_calls.append(schedule)
			),
			ROOT + ".portal_listing": types.SimpleNamespace(require_template_visible=require_visible),
			PRICING: types.SimpleNamespace(price_result=price_result),
		}

	def wire(self, frappe):
		def get_value(doctype, name, fields=None, as_dict=False):
			if doctype == "ilL-Attribute-Lead Time Class":
				return self.classes.get(name)
			if doctype == "ilL-Rel-Tape Offering":
				return self.offerings.get(name)
			self.assertEqual(fields, "lead_time_class")
			return self.templates.get((doctype, name))

		frappe.db.get_value = MagicMock(side_effect=get_value)

	def call(self, function, *args, **kwargs):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			return module, frappe, getattr(module, function)(*args, **kwargs)

	def test_template_lead_time_class(self):
		module, _frappe, result = self.call("lead_time", "driver", "DRV-1", schedule_name=" SCH-1 ")
		self.assertEqual(
			result,
			{"success": True, "lead_time": {"code": "STD", "label": "Standard", "days_min": 10, "days_max": 15}},
		)
		self.assertEqual(self.configurator_calls, ["SCH-1"])
		self.assertEqual(module.lead_time.whitelist_options, {"methods": ["GET"]})

	def test_template_without_a_class_has_no_lead_time(self):
		_module, _frappe, result = self.call("lead_time", "led_sheet", "LS-1")
		self.assertEqual(result, {"success": True, "lead_time": None})
		self.assertEqual(self.configurator_calls, [None])

	def test_templates_the_user_is_not_offered_are_refused(self):
		with self.assertRaises(LookupError):
			self.call("lead_time", "controller", "CTL-HIDDEN")

	def test_tape_families_use_the_active_offering_override(self):
		for family in ("fixture", "tape_neon"):
			_module, _frappe, result = self.call("lead_time", family, tape_offering="OFF-1")
			self.assertEqual(result["lead_time"]["code"], "STD")
		for offering in ("OFF-OFF", "OFF-NONE", "OFF-MISSING", ""):
			_module, _frappe, result = self.call("lead_time", "tape_neon", tape_offering=offering)
			self.assertIsNone(result["lead_time"], offering)

	def test_kit_has_no_class_and_unknown_families_are_refused(self):
		_module, _frappe, result = self.call("lead_time", "kit", "KIT-1")
		self.assertEqual(result, {"success": True, "lead_time": None})
		with self.assertRaises(ValueError):
			self.call("lead_time", "ilL-Driver-Template", "DRV-1")

	def test_class_values_are_normalised(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.assertEqual(
				module.lead_time_class("LT-REV"),
				{"code": "LT-REV", "label": "LT-REV", "days_min": 5, "days_max": 20},
			)
			self.assertEqual(
				module.lead_time_class("LT-BAD"), {"code": "BAD", "label": "Odd", "days_min": None, "days_max": None}
			)
			self.assertIsNone(module.lead_time_class("LT-MISSING"))
			self.assertIsNone(module.lead_time_class(None))

	def test_kill_switch_and_guests(self):
		self.enabled = False
		with self.assertRaises(PermissionError):
			self.call("lead_time", "driver", "DRV-1")
		self.enabled = True
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.session.user = "Guest"
			with self.assertRaises(PermissionError):
				module.lead_time("driver", "DRV-1")
		self.assertEqual(self.configurator_calls, [])

	def valid_result(self):
		return {
			"is_valid": True,
			"computed": {"total_watts": 12},
			"resolved_items": {"tape_offering": "OFF-1"},
		}

	def test_tape_estimate_prices_a_copy_like_the_save_path(self):
		result = self.valid_result()
		_module, _frappe, out = self.call("attach_tape_neon_estimate", result, "TN-1", "1")
		self.assertIs(out, result)
		self.assertEqual(
			out["estimate"],
			{
				"total_price_msrp": 123.45,
				"lead_time": {"code": "STD", "label": "Standard", "days_min": 10, "days_max": 15},
			},
		)
		self.assertNotIn("total_price_msrp", out["computed"], "the validation output is not changed")
		priced, template = self.priced[0]
		self.assertIsNot(priced, result)
		self.assertEqual(template, "TN-1")

	def test_missing_prices_do_not_invalidate_the_configuration(self):
		self.price_error = ValueError("A current Standard Selling price in stock UOM is required for TAPE")
		_module, _frappe, out = self.call("attach_tape_neon_estimate", self.valid_result(), None, True)
		self.assertTrue(out["is_valid"])
		self.assertIsNone(out["estimate"]["total_price_msrp"])
		self.assertEqual(out["estimate"]["lead_time"]["code"], "STD")

	def test_estimate_only_when_asked_valid_and_enabled(self):
		for include in (None, "", "0", "false", "maybe", False):
			_module, _frappe, out = self.call("attach_tape_neon_estimate", self.valid_result(), None, include)
			self.assertNotIn("estimate", out, include)
		invalid = {**self.valid_result(), "is_valid": False}
		_module, _frappe, out = self.call("attach_tape_neon_estimate", invalid, None, "1")
		self.assertNotIn("estimate", out)
		self.enabled = False
		_module, _frappe, out = self.call("attach_tape_neon_estimate", self.valid_result(), None, "true")
		self.assertNotIn("estimate", out)
		self.assertEqual(self.priced, [])


if __name__ == "__main__":
	unittest.main()
