"""Commercial schema installation must also cover existing and freshly installed sites."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import load_service

PATCH = "illumenate_lighting.patches.b2b_commercial_lineage"
ROW_TYPES = ("Quotation Item", "Sales Order Item", "Delivery Note Item", "Sales Invoice Item")


class CommercialSchema(unittest.TestCase):
	def install(self, existing):
		def create_fields(definitions, update=True):
			for doctype, fields in definitions.items():
				for field in fields:
					key = (doctype, field["fieldname"])
					if key not in existing:
						existing[key] = types.SimpleNamespace(**field, save=MagicMock())
					elif update:
						vars(existing[key]).update(field)

		custom_fields = types.SimpleNamespace(create_custom_fields=create_fields)
		with load_service(PATCH, {"frappe.custom.doctype.custom_field.custom_field": custom_fields}) as (
			module,
			frappe,
		):
			frappe.db.exists.return_value = True
			frappe.get_meta = lambda dt: types.SimpleNamespace(
				has_field=lambda name: (dt, name) in existing,
				get_field=lambda name: existing.get((dt, name)),
			)
			frappe.get_doc.side_effect = lambda dt, filters: existing[(filters["dt"], filters["fieldname"])]
			module.execute()
			module.execute()
			frappe.db.sql.assert_not_called()
		return existing

	def test_fresh_install_creates_fields_used_by_portal_queries_and_configurators(self):
		fields = self.install({})
		for doctype in ROW_TYPES:
			for field in (
				"ill_configured_fixture",
				"ill_configured_tape_neon",
				"ill_configured_led_sheet",
				"ill_configured_group",
				"ill_bom",
				"ill_configured_product",
				"ill_configuration_json",
				"ill_fixture_schedule",
				"ill_schedule_line_id",
				"additional_notes",
			):
				self.assertIn((doctype, field), fields)
			self.assertIn("LED Sheet", fields[(doctype, "ill_product_type")].options.split("\n"))
		for doctype in ("Quotation", "Sales Order"):
			self.assertIn((doctype, "ill_fixture_schedule"), fields)
		for doctype in ROW_TYPES[:2]:
			self.assertIn((doctype, "ill_is_power_supply_line"), fields)

	def test_repeat_setup_preserves_existing_settings_and_additional_product_choices(self):
		product = types.SimpleNamespace(
			fieldtype="Select", options="\nLinear Fixture\nLED Tape\nLED Neon\nSite Product", save=MagicMock()
		)
		notes = types.SimpleNamespace(fieldtype="Text Editor", label="Site Notes", read_only=0)
		section = types.SimpleNamespace(fieldtype="Data", label="Site Room", read_only=0)
		fields = self.install(
			{
				("Sales Order Item", "ill_product_type"): product,
				("Sales Order Item", "additional_notes"): notes,
				("Sales Order Item", "ill_section_label"): section,
			}
		)
		self.assertEqual(product.options.split("\n")[-2:], ["Site Product", "LED Sheet"])
		product.save.assert_called_once_with(ignore_permissions=True)
		self.assertIs(fields[("Sales Order Item", "additional_notes")], notes)
		self.assertEqual(notes.fieldtype, "Text Editor")
		self.assertEqual(section.label, "Site Room")
		self.assertEqual(section.read_only, 0)

	def test_existing_sites_receive_a_new_post_sync_patch(self):
		patches = Path("illumenate_lighting/patches.txt").read_text().split("[post_model_sync]", 1)[1]
		self.assertIn("illumenate_lighting.patches.b2b_commercial_schema", patches.splitlines())
