"""Desk "Configure & Add Fixture" for Extrusion Kits, power supplies and controllers."""

import json
import unittest
from unittest.mock import MagicMock, patch

from test_desk_configurator_save import Doc, desk, stub
from test_services import ROOT, Record

KIT_RESULT = {
	"is_valid": True,
	"part_number": "KIT-SH01-FR-MC-WH",
	"build_description": "Slim Kit, White",
	"kit_template": {"name": "KIT", "template_name": "Slim Kit"},
	"kit_composition": {
		"profile": {"item": "PROFILE", "qty": 1, "length_mm": 2000},
		"lens": {"item": "LENS", "qty": 1},
		"mounting": {"item": "CLIP", "qty": 6},
	},
	"selections": {"kit_template": "KIT", "finish": "White"},
}


def kit_create_rows(so, _line, config, qty_multiplier=1):
	for key in ("profile", "lens", "solid_endcap", "feed_through_endcap", "mounting"):
		comp = config["kit_composition"].get(key)
		if comp:
			row = so.append("items", {})
			row.item_code, row.qty = comp["item"], comp["qty"] * qty_multiplier
			row.description = f"{config['kit_template']['template_name']} {config['part_number']} - {key}"
	return {"items_added": 1}


def families(kit_write=None, driver_write=None):
	kit = stub(
		ROOT + ".api.extrusion_kit_configurator",
		KIT_SELECTION_KEYS=("kit_template", "finish", "lens_appearance", "mounting_method"),
		validate_kit_configuration=MagicMock(return_value=KIT_RESULT),
		create_kit_so_lines=kit_create_rows,
		_write_kit_line=kit_write or MagicMock(),
	)
	steps = [{"name": "wattage"}, {"name": "voltage_output"}]
	drivers = stub(
		ROOT + ".api.driver_controller_configurator",
		_KINDS={"Driver": {"steps": steps}, "Controller": {"steps": [{"name": "channels"}]}},
		_validate_configuration=MagicMock(
			return_value={
				"success": True,
				"template_code": "DRV-A",
				"template_name": "Slim Driver",
				"product_slug": "",
				"part_number": "PS-96-24",
				"selections": {"wattage": "96", "voltage_output": "24"},
				"variant": {"item": "PS-96-24-ITEM", "item_name": "96 W driver", "variant_code": "96-24"},
				"pricing": {"total_msrp": 120},
			}
		),
	)
	return {
		ROOT + ".api.extrusion_kit_configurator": kit,
		ROOT + ".api.driver_controller_configurator": drivers,
		ROOT + ".api.portal": stub(ROOT + ".api.portal", orderable_item_problem=MagicMock(return_value=None)),
		ROOT + ".portal.driver_configuration": stub(
			ROOT + ".portal.driver_configuration",
			line_description=lambda *parts: " · ".join(p for p in parts if p),
			write_line=driver_write or MagicMock(),
		),
		ROOT + ".portal.line_fields": stub(ROOT + ".portal.line_fields", LINE_PRODUCT_FIELDS=("accessory_item", "kit_template")),
		ROOT + ".api.power_supply_lines": stub(ROOT + ".api.power_supply_lines", clear_power_lines=MagicMock()),
	}


def row_values(_parent, _name, _header, artifact, qty, **fields):
	return {"item_code": artifact["item_code"], "qty": qty, "description": artifact["description"], **fields}


class DeskCatalogLines(unittest.TestCase):
	def build(self, module, frappe, modules, **call):
		frappe._dict = Record
		with (
			patch.dict("sys.modules", modules),
			patch.object(module, "_require_internal_user"),
			patch.object(module, "_require_parent_doctype"),
			patch.object(module, "_build_row_values", side_effect=row_values),
			patch.object(module, "_next_fixture_type", return_value="K2"),
		):
			return module.build_configured_line(parent_doctype="Quotation", **call)

	def test_kit_without_schedule_adds_every_component_scaled_by_quantity(self):
		with desk() as (module, frappe, *_):
			modules = families()
			result = self.build(
				module,
				frappe,
				modules,
				product_type="Extrusion Kit",
				selections_json=json.dumps({"kit_template": "KIT", "finish": "White", "endcap_color": "Red"}),
				qty=3,
				fixture_type="K1",
				location="Lobby",
			)
			self.assertTrue(result["success"], result)
			kit = modules[ROOT + ".api.extrusion_kit_configurator"]
			self.assertEqual(kit.validate_kit_configuration.call_args.args[0], {"kit_template": "KIT", "finish": "White"})
			rows = [result["row_values"], *result["accessory_rows"]]
			self.assertEqual([(r["item_code"], r["qty"]) for r in rows], [("PROFILE", 3), ("LENS", 3), ("CLIP", 18)])
			self.assertTrue(all(r["fixture_type"] == "K1" and r["section_label"] == "Lobby" for r in rows))
			self.assertIn("Slim Kit KIT-SH01-FR-MC-WH", rows[0]["description"])
			request = json.loads(rows[0]["ill_configurator_request"])
			self.assertEqual((request["family"], request["template"]), ("Extrusion Kit", "KIT"))
			self.assertIsNone(result["schedule"])
			kit._write_kit_line.assert_not_called()

	def test_power_supply_on_a_schedule_writes_the_portal_accessory_line(self):
		with desk() as (module, frappe, *_):
			schedule = Doc(name="S1", status="DRAFT", is_locked=0, lines=[], save=MagicMock())
			written = {}
			modules = families(driver_write=lambda line, result: written.update(line=line, template=result["template_code"]))
			with patch.object(module, "_load_schedule", return_value=(schedule, None)):
				result = self.build(
					module,
					frappe,
					modules,
					product_type="Driver",
					selections_json={"wattage": "96", "voltage_output": "24", "extra": "ignored"},
					template="DRV-A",
					qty=2,
					fixture_type="PS1",
					schedule="S1",
				)
			self.assertTrue(result["success"], result)
			validate = modules[ROOT + ".api.driver_controller_configurator"]._validate_configuration
			self.assertEqual(validate.call_args.args[0], "Driver")
			self.assertEqual(json.loads(validate.call_args.args[2]), {"wattage": "96", "voltage_output": "24"})
			self.assertEqual(validate.call_args.args[3], "DRV-A")
			line = written["line"]
			self.assertEqual((line.line_id, line.qty, written["template"]), ("PS1", 2, "DRV-A"))
			schedule.save.assert_called_once()
			self.assertEqual(result["row_values"]["item_code"], "PS-96-24-ITEM")
			self.assertEqual(result["row_values"]["qty"], 2)
			self.assertEqual(result["row_values"]["description"], "Slim Driver · PS-96-24 · 96 W driver")
			self.assertEqual(result["accessory_rows"], [])

	def test_controller_needs_a_product_and_power_supply_needs_a_template(self):
		with desk() as (module, frappe, *_):
			for product_type in ("Controller", "Power Supply"):
				with self.subTest(product_type=product_type):
					result = self.build(module, frappe, families(), product_type=product_type, selections_json={}, qty=1)
					self.assertFalse(result["success"])

	def test_controller_schedules_the_variant_item_as_a_configured_accessory(self):
		with desk() as (module, frappe, *_):
			schedule = Doc(name="S1", status="READY", is_locked=0, lines=[], save=MagicMock())
			with patch.object(module, "_load_schedule", return_value=(schedule, None)):
				result = self.build(
					module,
					frappe,
					families(),
					product_type="Controller",
					selections_json={"channels": "4"},
					product_slug="ctrl-4",
					qty=1,
					schedule="S1",
				)
			self.assertTrue(result["success"], result)
			line = schedule.lines[0]
			self.assertEqual((line.manufacturer_type, line.accessory_item, line.line_id), ("ACCESSORY", "PS-96-24-ITEM", "K2"))
			self.assertEqual(json.loads(line.variant_selections)["product_slug"], "ctrl-4")


if __name__ == "__main__":
	unittest.main()
