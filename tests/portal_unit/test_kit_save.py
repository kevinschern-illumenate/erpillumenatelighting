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
}
SERVER_RESULT = {
	"success": True,
	"is_valid": True,
	"part_number": "KIT-1-BK-FR",
	"build_description": "Server build",
	"kit_composition": {"profile": {"item": "PROFILE-BK", "qty": 1}, "mounting": {"item": "CLIP", "qty": 6}},
	"spec_data": {},
	"resolved_items": {"profile_item": "PROFILE-BK"},
	"selections": {**SELECTIONS, "endcap_style": "Flat", "endcap_color": "Black"},
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
			"selections": {**SELECTIONS, "unexpected": "dropped", "endcap_color": "Red"},
		}
		result, validate, line, schedule = self.run_save(configuration_result=json.dumps(forged))
		self.assertTrue(result["success"])
		validate.assert_called_once_with(SELECTIONS)
		stored = json.loads(line.variant_selections)
		self.assertEqual(line.ill_item_code, "KIT-1-BK-FR")
		self.assertEqual(stored["kit_composition"], SERVER_RESULT["kit_composition"])
		self.assertEqual(stored["pricing"], {"total_price_msrp": 70.0})
		self.assertNotIn("unexpected", stored["selections"])
		# Endcaps are never the caller's choice; the stored ones are the server's.
		self.assertEqual(stored["selections"]["endcap_color"], "Black")
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
	def test_part_number_uses_profile_family_lens_mounting_and_finish_codes(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			codes = {
				("ilL-Attribute-Lens Appearance", "White"): "WH",
				("ilL-Attribute-Mounting Method", "Mounting Clip"): "MC",
				("ilL-Attribute-Finish", "Anodized Silver"): "SV",
			}
			frappe.db.get_value.side_effect = lambda doctype, name, field: codes[(doctype, name)]
			template = Record(default_profile_family="SH01", series="Different series", template_code="KIT-OTHER")
			selections = dict(kit_template="KIT-OTHER", lens_appearance="White", mounting_method="Mounting Clip", finish="Anodized Silver", endcap_style="Solid", endcap_color="Grey")
			self.assertEqual(service._build_kit_part_number(selections, template), "KIT-SH01-WH-MC-SV")

	def test_missing_part_number_codes_do_not_produce_placeholder_part_numbers(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			frappe.db.get_value.return_value = None
			with self.assertRaisesRegex(ValueError, "profile family"):
				service._build_kit_part_number(SELECTIONS, Record(name="KIT-1", default_profile_family=None))
			with self.assertRaisesRegex(ValueError, "code"):
				service._build_kit_part_number(SELECTIONS, Record(default_profile_family="SH01"))

	def test_validation_and_schedule_writer_keep_components_and_pricing_with_the_new_code(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			template = Record(
				name="KIT-1", template_code="KIT-1", template_name="Slim Kit", is_active=1,
				default_profile_family="SH01", profile_stock_length_mm=2000, lens_stock_length_mm=2000,
				solid_endcap_qty=2, feed_through_endcap_qty=2, mounting_accessory_qty=6,
				get_allowed_values=lambda kind: [],
			)
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = template
			codes = {"Anodized Silver": "SV", "White": "WH", "Mounting Clip": "MC"}
			frappe.db.get_value.side_effect = lambda dt, name, field: 10 if dt == "Item Price" else codes.get(name)
			profile = Record(profile_item="PROFILE-SV", profile_spec="PROFILE-SPEC")
			lens = Record(lens_item="LENS-WH", lens_spec="LENS-SPEC")
			solid = Record(endcap_item="SOLID-SV", endcap_spec="SOLID-SPEC", endcap_style="Solid")
			feed = Record(endcap_item="FEED-SV", endcap_spec="FEED-SPEC")
			mounting = Record(accessory_item="MOUNT-MC", accessory_spec="MOUNT-SPEC")
			selections = dict(kit_template="KIT-1", finish="Anodized Silver", lens_appearance="White", mounting_method="Mounting Clip")
			with patch.multiple(
				service,
				_resolve_kit_profile=MagicMock(return_value=profile),
				_resolve_kit_lens=MagicMock(return_value=lens),
				_resolve_kit_endcaps=MagicMock(return_value={"solid": solid, "feed_through": feed, "color": "Silver"}),
				_resolve_kit_mounting=MagicMock(return_value=mounting),
				_collect_spec_data=MagicMock(return_value={}),
				get_kit_component_stock=MagicMock(return_value={"success": False}),
			):
				result = service.validate_kit_configuration(selections)
				self.assertTrue(result["is_valid"])
				line = types.SimpleNamespace()
				service._write_kit_line(None, line, result)
				stored = json.loads(line.variant_selections)
				self.assertEqual(line.ill_item_code, "KIT-SH01-WH-MC-SV")
				self.assertEqual(stored["part_number"], line.ill_item_code)
				self.assertEqual(stored["kit_composition"], result["kit_composition"])
				self.assertEqual(stored["pricing"], {"total_price_msrp": 120.0})
				self.assertEqual(stored["selections"]["endcap_color"], "Silver")
				# A setup error is a validation response the UI can display, not an exception.
				template["default_profile_family"] = None
				invalid = service.validate_kit_configuration(selections)
				self.assertFalse(invalid["is_valid"])
				self.assertIn("profile family", invalid["error"])
			frappe.db.exists.assert_called_with("ilL-Extrusion-Kit-Template", "KIT-1")

	def test_inactive_templates_cannot_be_validated(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="KIT-1", is_active=0)
			result = service.validate_kit_configuration(SELECTIONS)
		self.assertEqual(result["is_valid"], False)
		self.assertEqual(result["error"], "Kit template is not active")

	def run_endcaps(self, color, maps):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			frappe.db.get_value.return_value = color
			frappe.get_all.side_effect = lambda doctype, filters, **kw: [
				Record(m) for m in maps if m["endcap_type"] == filters["endcap_type"] and m["endcap_color"] == filters["endcap_color"]
			]
			with patch.object(service, "enabled_rows", side_effect=lambda rows, field: rows):
				result = service._resolve_kit_endcaps("KIT-1", "Black Anodized")
			finish_lookup = frappe.db.get_value.call_args
		return result, finish_lookup

	def test_endcaps_follow_the_finish_color(self):
		maps = [
			{"endcap_type": "Solid", "endcap_color": "Black", "endcap_style": "Flat", "endcap_item": "EC-S-BK"},
			{"endcap_type": "Feed-Through", "endcap_color": "Black", "endcap_style": "Flat FT", "endcap_item": "EC-F-BK"},
			{"endcap_type": "Solid", "endcap_color": "White", "endcap_style": "Flat", "endcap_item": "EC-S-WH"},
		]
		result, finish_lookup = self.run_endcaps("Black", maps)
		self.assertEqual(finish_lookup.args[0], "ilL-Rel-Finish Endcap Color")
		self.assertEqual(finish_lookup.args[1], {"finish": "Black Anodized", "is_active": 1})
		self.assertEqual(result["color"], "Black")
		self.assertEqual(result["solid"].endcap_item, "EC-S-BK")
		self.assertEqual(result["feed_through"].endcap_item, "EC-F-BK")
		self.assertNotIn("error", result)

	def test_missing_finish_color_or_endcap_type_is_an_error(self):
		result, _ = self.run_endcaps(None, [])
		self.assertIn("No endcap color is mapped to finish 'Black Anodized'", result["error"])
		solid_only = [{"endcap_type": "Solid", "endcap_color": "Black", "endcap_style": "Flat", "endcap_item": "EC-S-BK"}]
		result, _ = self.run_endcaps("Black", solid_only)
		self.assertIn("No feed-through endcap mapping", result["error"])


if __name__ == "__main__":
	unittest.main()
