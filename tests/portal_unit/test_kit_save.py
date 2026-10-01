"""Extrusion Kit saves keep only the caller's selections; priced and ordered data is server-derived."""

import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

SELECTIONS = {
	"kit_template": "KIT-1",
	"finish": "Black",
	"lens_appearance": "Frosted",
	"mounting_method": "Clip",
	"endcap_style": "Flat",
	"endcap_color": "Black",
}
SERVER_RESULT = {
	"success": True,
	"is_valid": True,
	"part_number": "KIT-1-BK-FR",
	"build_description": "Server build",
	"kit_composition": {"profile": {"item": "PROFILE-BK", "qty": 1}, "mounting": {"item": "CLIP", "qty": 6}},
	"spec_data": {},
	"resolved_items": {"profile_item": "PROFILE-BK"},
	"selections": SELECTIONS,
	"kit_template": {"name": "KIT-1"},
}


class KitSave(unittest.TestCase):
	def run_save(self, schedule=None, validation=SERVER_RESULT, **kwargs):
		permission = MagicMock(return_value=True)
		deps = {
			ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				has_permission=permission
			),
		}
		schedule = schedule or Record(status="DRAFT", is_locked=0, lines=[])
		schedule["save"] = MagicMock()
		appended = Record(idx=len(schedule.lines) + 1)
		schedule["append"] = lambda field, values: schedule.lines.append(appended) or appended
		with load_service(ROOT + ".api.extrusion_kit_configurator", deps) as (service, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = schedule
			frappe.db.get_value.return_value = 10.0  # every component priced at $10
			with patch.object(service, "validate_kit_configuration", return_value=validation) as validate:
				result = service.save_kit_to_schedule("SCH-1", **kwargs)
		return result, validate, appended, schedule

	def test_forged_composition_and_pricing_are_replaced_by_the_server_result(self):
		forged = {
			"is_valid": True,
			"part_number": "FREE-KIT",
			"kit_composition": {"profile": {"item": "SOMETHING-ELSE", "qty": 0}},
			"pricing": {"total_price_msrp": 0},
			"selections": {**SELECTIONS, "unexpected": "dropped"},
		}
		result, validate, line, schedule = self.run_save(configuration_result=json.dumps(forged))
		self.assertTrue(result["success"])
		validate.assert_called_once_with(SELECTIONS)
		stored = json.loads(line.variant_selections)
		self.assertEqual(line.ill_item_code, "KIT-1-BK-FR")
		self.assertEqual(stored["kit_composition"], SERVER_RESULT["kit_composition"])
		self.assertEqual(stored["pricing"], {"total_price_msrp": 70.0})
		self.assertNotIn("unexpected", stored["selections"])
		schedule.save.assert_called_once()

	def test_explicit_selections_take_precedence(self):
		result, validate, _line, _schedule = self.run_save(
			selections=json.dumps(SELECTIONS), configuration_result=json.dumps({"selections": {"kit_template": "X"}})
		)
		self.assertTrue(result["success"])
		validate.assert_called_once_with(SELECTIONS)

	def test_invalid_or_missing_selections_save_nothing(self):
		invalid = {"success": False, "is_valid": False, "error": "Kit template is not active"}
		result, _validate, _line, schedule = self.run_save(validation=invalid, selections=SELECTIONS)
		self.assertEqual(result, {"success": False, "error": "Kit template is not active"})
		schedule.save.assert_not_called()
		result, validate, _line, schedule = self.run_save(configuration_result=json.dumps({"is_valid": True}))
		self.assertEqual(result["error"], "Kit selections are required")
		validate.assert_not_called()
		schedule.save.assert_not_called()

	def test_locked_schedule_versions_are_not_changed(self):
		locked = Record(status="DRAFT", is_locked=1, lines=[])
		result, validate, _line, schedule = self.run_save(schedule=locked, selections=SELECTIONS)
		self.assertFalse(result["success"])
		self.assertIn("locked", result["error"])
		validate.assert_not_called()
		schedule.save.assert_not_called()


class KitValidation(unittest.TestCase):
	def test_inactive_templates_cannot_be_validated(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="KIT-1", is_active=0)
			result = service.validate_kit_configuration(SELECTIONS)
		self.assertEqual(result["is_valid"], False)
		self.assertEqual(result["error"], "Kit template is not active")


if __name__ == "__main__":
	unittest.main()
