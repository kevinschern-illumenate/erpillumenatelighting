"""Power supplies are configured from their ilL-Driver-Template and scheduled as the resolved Item."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

SERVER_RESULT = {
	"success": True,
	"template_code": "DRV-A",
	"template_name": "Slim Driver",
	"selections": {"wattage": "96", "voltage_output": "24V DC"},
	"part_number": "ILL-SLM-96-24",
	"variant": {
		"spec_name": "DRV-96-24",
		"variant_name": "row1",
		"item": "DRV-96-24",
		"variant_code": "",
		"item_name": "96W 24V driver",
	},
}


class Line(Record):
	def __setattr__(self, key, value):
		self[key] = value

	def set(self, key, value):
		self[key] = value


DRIVER_STEPS = [
	{"name": "wattage", "label": "Wattage"},
	{"name": "voltage_output", "label": "Output Voltage"},
	{"name": "input_protocol", "label": "Dimming Input"},
	{"name": "output_protocol", "label": "Output Protocol"},
]


def driver_module(extras=None):
	"""portal.driver_configuration with its portal boundaries stubbed."""
	return load_service(
		ROOT + ".portal.driver_configuration",
		{
			ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=MagicMock()),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				RECEIPT="Receipt",
				object_value=MagicMock(),
				resolve_line=MagicMock(),
				schedule_context=MagicMock(),
			),
			ROOT + ".api.driver_controller_configurator": types.SimpleNamespace(DRIVER_STEPS=DRIVER_STEPS),
			**(extras or {}),
		},
	)


class DriverSave(unittest.TestCase):
	def deps(self, line, schedule, validate):
		return {
			ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=MagicMock()),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				RECEIPT="Receipt",
				object_value=lambda v, label: json.loads(v) if isinstance(v, str) else (v or {}),
				resolve_line=lambda *a: line,
				schedule_context=MagicMock(return_value=schedule),
			),
			ROOT + ".portal.line_fields": types.SimpleNamespace(
				LINE_PRODUCT_FIELDS=(
					"configured_fixture",
					"kit_template",
					"driver_template",
					"accessory_item",
				)
			),
			ROOT + ".portal.rollout": types.SimpleNamespace(require_family=MagicMock()),
			ROOT + ".api.driver_controller_configurator": types.SimpleNamespace(
				DRIVER_STEPS=[{"name": "wattage"}, {"name": "voltage_output"}, {"name": "input_protocol"}],
				_validate_configuration=validate,
			),
			ROOT + ".api.portal": types.SimpleNamespace(orderable_item_problem=MagicMock(return_value=None)),
			ROOT + ".portal.product_finder.sessions": types.SimpleNamespace(decoded=json.loads),
			ROOT + ".portal.product_finder.verification": types.SimpleNamespace(),
		}

	def test_save_revalidates_on_the_template_and_writes_the_server_item(self):
		line = Line(line_key="L", qty=1, line_id="", configured_fixture="OLD", kit_template="KIT")
		schedule = Record(
			name="S", modified="old", status="DRAFT", is_locked=0, lines=[line], save=MagicMock()
		)
		validate = MagicMock(return_value=SERVER_RESULT)
		with load_service(ROOT + ".portal.driver_configuration", self.deps(line, schedule, validate)) as (
			service,
			frappe,
		):
			frappe.db.get_value.side_effect = lambda doctype, *a, **k: (
				"Power Supplies" if doctype == "Item" else None
			)
			args = dict(
				schedule_name="S",
				template="DRV-A",
				selections={"wattage": "96", "voltage_output": "24V DC", "item_code": "FORGED", "price": 0},
				idempotency_key="retry-key",
				expected_modified="old",
				line_key="L",
				metadata={"qty": 3, "line_id": "PS1", "location": "Closet"},
			)
			result = service.save(**args)
			self.assertTrue(result["success"])
			self.assertEqual(result["item_code"], "DRV-96-24")
			kind, slug, selections, template = validate.call_args.args
			self.assertEqual((kind, slug, template), ("Driver", None, "DRV-A"))
			self.assertEqual(json.loads(selections), {"wattage": "96", "voltage_output": "24V DC"})
			self.assertIsNone(line.configured_fixture)
			self.assertIsNone(line.kit_template)
			self.assertEqual(line.manufacturer_type, "ACCESSORY")
			self.assertEqual(line.configuration_status, "Configured")
			self.assertEqual(line.driver_template, "DRV-A")
			self.assertEqual(line.accessory_item, "DRV-96-24")
			self.assertEqual(line.accessory_item_name, "Slim Driver · ILL-SLM-96-24 · 96W 24V driver")
			self.assertEqual(line.accessory_product_type, "Power Supplies")
			stored = json.loads(line.variant_selections)
			self.assertEqual(stored["product_category"], "Driver")
			self.assertEqual(stored["variant_name"], "row1")
			self.assertEqual(stored["selections"], SERVER_RESULT["selections"])
			self.assertEqual((line.qty, line.line_id, line.location), (3, "PS1", "Closet"))
			schedule.save.assert_called_once()

			receipt = frappe.get_doc.call_args.args[0]
			frappe.db.get_value.side_effect = None
			frappe.db.get_value.return_value = Record(
				request_hash=receipt["request_hash"], response_json=receipt["response_json"]
			)
			self.assertTrue(service.save(**args)["already_existed"])
			validate.assert_called_once()
			with self.assertRaisesRegex(ValueError, "different content"):
				service.save(**{**args, "template": "DRV-B"})

	def test_save_refuses_changed_schedules_invalid_configurations_and_missing_fixture_types(self):
		line = Line(line_key="L", qty=1, line_id="")
		schedule = Record(
			name="S", modified="old", status="DRAFT", is_locked=0, lines=[line], save=MagicMock()
		)
		validate = MagicMock(
			return_value={"success": False, "error": "No driver matches that combination of options"}
		)
		with load_service(ROOT + ".portal.driver_configuration", self.deps(line, schedule, validate)) as (
			service,
			frappe,
		):
			frappe.db.get_value.return_value = None
			args = dict(
				schedule_name="S",
				template="DRV-A",
				selections={"wattage": "96"},
				idempotency_key="retry-key",
				expected_modified="old",
				line_key="L",
				metadata={"line_id": "PS1"},
			)
			with self.assertRaisesRegex(ValueError, "No driver matches"):
				service.save(**args)
			validate.return_value = SERVER_RESULT
			with self.assertRaisesRegex(ValueError, "fixture type"):
				service.save(**{**args, "metadata": {}})
			with self.assertRaisesRegex(ValueError, "changed"):
				service.save(**{**args, "expected_modified": "newer"})
			schedule.save.assert_not_called()


class DriverLineHelpers(unittest.TestCase):
	def test_selection_labels_and_line_description(self):
		with driver_module() as (helpers, _frappe):
			self.assertEqual(
				helpers.selection_labels({"wattage": 96.0, "voltage_output": "24V DC", "input_protocol": ""}),
				{"Wattage": "96 W", "Output Voltage": "24V DC"},
			)
			self.assertEqual(helpers.line_description("Slim Driver", "P-1", "P-1"), "Slim Driver · P-1")

	def test_only_configured_driver_lines_carry_a_configuration(self):
		with driver_module() as (helpers, _frappe):
			self.check_configuration(helpers.driver_configuration)

	def check_configuration(self, driver_configuration):
		stored = json.dumps({"product_category": "Driver", "part_number": "P"})
		self.assertEqual(
			driver_configuration(Record(driver_template="T", accessory_item="I", variant_selections=stored))[
				"part_number"
			],
			"P",
		)
		self.assertIsNone(driver_configuration(Record(driver_template="T", variant_selections=stored)))
		self.assertIsNone(driver_configuration(Record(accessory_item="I", variant_selections=stored)))
		self.assertIsNone(
			driver_configuration(Record(driver_template="T", accessory_item="I", variant_selections="{bad"))
		)

	def test_driver_lines_reopen_in_the_power_supply_configurator(self):
		with (
			driver_module() as (helpers, _),
			load_service(
				ROOT + ".portal.configuration_reopen",
				{
					ROOT + ".portal.configuration": types.SimpleNamespace(
						FAMILIES={}, resolve_line=MagicMock(), schedule_context=MagicMock()
					),
					ROOT + ".portal.driver_configuration": helpers,
				},
			) as (service, _frappe),
		):
			configured = Record(
				driver_template="DRV-A",
				accessory_item="I",
				variant_selections=json.dumps(
					{"product_category": "Driver", "selections": {"wattage": "96"}}
				),
			)
			self.assertEqual(
				service.for_line(configured),
				{"family": "Driver", "template": "DRV-A", "selections": {"wattage": "96"}},
			)
			self.assertEqual(
				service.for_line(Record(driver_template="DRV-A")),
				{"family": "Driver", "template": "DRV-A", "selections": {}},
			)


class DriverTemplates(unittest.TestCase):
	def test_inactive_templates_cannot_be_configured_by_name(self):
		deps = {
			ROOT + ".doctype.ill_controller_template.ill_controller_template": types.SimpleNamespace(
				CONTROLLER_VARIANT_AXES={}
			),
			ROOT + ".doctype.ill_driver_template.ill_driver_template": types.SimpleNamespace(
				DRIVER_VARIANT_AXES={}, _normalise_axis_value=str
			),
		}
		with load_service(ROOT + ".api.driver_controller_configurator", deps) as (service, frappe):
			frappe.db.get_value.return_value = 0
			result = service.get_driver_configurator_init(template="DRV-OLD")
			self.assertEqual(result["success"], False)
			frappe.get_doc.assert_not_called()
			self.assertFalse(
				service.validate_driver_configuration(selections="{}", template="DRV-OLD")["success"]
			)


class DriverValidation(unittest.TestCase):
	def test_power_supply_resolves_to_its_spec_id_and_the_spec_item(self):
		deps = {
			ROOT + ".doctype.ill_controller_template.ill_controller_template": types.SimpleNamespace(
				CONTROLLER_VARIANT_AXES={}
			),
			ROOT + ".doctype.ill_driver_template.ill_driver_template": types.SimpleNamespace(
				DRIVER_VARIANT_AXES={}, _normalise_axis_value=str
			),
		}
		with load_service(ROOT + ".api.driver_controller_configurator", deps) as (service, frappe):
			template = Record(name="DRV-A", template_name="Slim Driver")
			variant = Record(name="row1", driver_spec="DRV-96-24", item=None, variant_code="")
			service._resolve_template = MagicMock(return_value=(template, None))
			service._active_steps = MagicMock(return_value=[{"name": "wattage", "label": "Wattage"}])
			service._matching_variants = MagicMock(return_value=[variant])
			service._calculate_pricing = MagicMock(return_value={})
			service._build_part_number = MagicMock(return_value="ILL-SLM-96")
			service._spec_summary = MagicMock(return_value=[])
			service._stock = MagicMock(return_value=None)
			frappe.db.get_value.side_effect = lambda doctype, name, field, *a, **k: {
				("ilL-Spec-Driver", "item"): "DRV-96-24",
				("Item", "item_name"): "96W driver",
			}.get((doctype, field))
			result = service._validate_configuration("Driver", None, '{"wattage": "96"}', "DRV-A")
			self.assertEqual(result["part_number"], "DRV-96-24")
			self.assertEqual(result["variant"]["item"], "DRV-96-24", "a blank fetched Item falls back to the spec's")
			self.assertEqual(result["variant"]["item_name"], "96W driver")
			service._stock.assert_called_once_with("DRV-96-24")
			service._build_part_number.assert_not_called()


class DriverPackets(unittest.TestCase):
	def test_configured_power_supply_gets_its_filled_submittal_and_falls_back_to_literature(self):
		stored = json.dumps(
			{"product_category": "Driver", "part_number": "ILL-SLM-96-24", "variant_name": "row1"}
		)
		line = Record(
			name="ROW",
			line_id="PS1",
			driver_template="DRV-A",
			accessory_item="DRV-96-24",
			manufacturer_type="ACCESSORY",
			variant_selections=stored,
		)
		renderer = MagicMock(
			return_value={"success": True, "file_url": "/private/files/drv.pdf", "provenance": {}}
		)
		pdf = types.SimpleNamespace(generate_filled_driver_line_submittal=renderer)
		with (
			driver_module() as (helpers, _),
			load_service(
				ROOT + ".portal.packets",
				{ROOT + ".portal.driver_configuration": helpers, ROOT + ".api.spec_submittal": pdf},
			) as (service, _frappe),
		):
			entry, warnings = {}, []
			self.assertTrue(service._driver_submittal(line, entry, warnings))
			renderer.assert_called_once_with("DRV-A", warnings=[], schedule_line="ROW")
			self.assertEqual(entry["source_kind"], "filled_submittal")
			self.assertEqual(entry["build"], {"doctype": "ilL-Driver-Template", "name": "DRV-A"})
			self.assertEqual(service._part_number(line), "ILL-SLM-96-24")

			renderer.return_value = {"success": False, "message": "No field mappings"}
			entry, warnings = {}, []
			self.assertFalse(service._driver_submittal(line, entry, warnings))
			self.assertEqual(entry, {})
			self.assertIn("No field mappings", warnings[-1])
			self.assertFalse(service._driver_submittal(Record(line, driver_template=None), {}, []))


if __name__ == "__main__":
	unittest.main()
