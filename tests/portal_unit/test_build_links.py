"""A configured order row's build links follow the Item the row orders."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_schedule_sync import Doc, Row, quote_row, schedule_line
from test_schedule_sync import service as sync_service
from test_services import ROOT, Record, load_service

BUILDER = types.SimpleNamespace(
	_fixture_configuration_snapshot=lambda doc: {"configured_fixture": doc.name, "bom": doc.bom},
	_tape_neon_configuration_snapshot=lambda doc: {"configured_tape_neon": doc.name},
	_serialize_json=json.dumps,
)
# The quoted 195.5" build and the 120" default the row still pointed at (Kevin's order).
NEW = Record(
	doctype="ilL-Configured-Fixture",
	name="ILL-CF-new",
	configured_item="RA04-195.5",
	bom="BOM-RA04-195.5-001",
	fixture_template="ILL-RA04-FS",
	requested_overall_length_mm=4966,
	manufacturable_overall_length_mm=4895,
	runs_count=1,
	total_watts=32,
	finish="Black",
	lens_appearance="White Lens",
	engine_version="linear-2",
)
ITEM_BUILDS = {"RA04-195.5": "ILL-CF-new", "RA04-120.0": "ILL-CF-old"}


def service():
	return load_service(ROOT + ".api.build_links", {ROOT + ".api.configured_product_builder": BUILDER})


def builds(frappe):
	frappe.db.exists.return_value = False
	frappe.db.get_value.side_effect = lambda doctype, name, field, *a, **k: (
		ITEM_BUILDS.get(name) if field == "custom_ill_configured_fixture" else None
	)
	frappe.get_doc.side_effect = lambda doctype, name: {"ILL-CF-new": NEW}[name]


def order_row(item_code, **values):
	return Row(
		{
			"idx": 1,
			"item_code": item_code,
			"bom_no": "BOM-RA04-195.5-001",
			"ill_configured_fixture": "ILL-CF-old",
			"ill_configured_product": "ILL-CF-old",
			"ill_configured_item": "RA04-120.0",
			"ill_bom": "BOM-RA04-120.0-001",
			"ill_requested_length_mm": 3048,
			"ill_configurator_request": '{"segments": [{"requested_length_mm": 3048}]}',
			**values,
		}
	)


def order(rows, doctype="Sales Order", docstatus=0):
	return Doc({"doctype": doctype, "docstatus": docstatus, "items": rows})


class RowsFollowTheirItem(unittest.TestCase):
	def test_a_row_ordering_another_builds_item_takes_that_builds_links(self):
		row = order_row("RA04-195.5")
		with service() as (links, frappe):
			builds(frappe)
			moved = links.follow_items(order([row], docstatus=1))  # Submit validates first.
		self.assertEqual(moved, ["1"])
		self.assertEqual(row.ill_configured_fixture, "ILL-CF-new")
		self.assertEqual(row.ill_configured_product, "ILL-CF-new")
		self.assertEqual(row.ill_configured_item, "RA04-195.5")
		self.assertEqual(row.ill_bom, "BOM-RA04-195.5-001")
		self.assertEqual(row.bom_no, "BOM-RA04-195.5-001")
		self.assertEqual(row.ill_requested_length_mm, 4966)
		self.assertEqual(json.loads(row.ill_configuration_json)["configured_fixture"], "ILL-CF-new")
		# The old build's inputs go, so reopening the row starts from the new build.
		self.assertIsNone(row.ill_configurator_request)
		self.assertEqual(row.item_code, "RA04-195.5")  # Price, description and Item stay as quoted.

	def test_rows_already_on_their_items_build_are_left_alone(self):
		row = order_row("RA04-120.0")
		with service() as (links, frappe):
			builds(frappe)
			self.assertEqual(links.follow_items(order([row], "Quotation")), [])
			frappe.get_doc.assert_not_called()
			frappe.msgprint.assert_not_called()
		self.assertEqual(row.ill_configured_fixture, "ILL-CF-old")

	def test_items_naming_no_build_supplies_groups_and_cancelled_documents_are_untouched(self):
		legacy = order_row("LEGACY-ITEM")
		supply = order_row("RA04-195.5", ill_is_power_supply_line=1)
		group = order_row("RA04-195.5", ill_configured_group="GRP-1")
		with service() as (links, frappe):
			builds(frappe)
			self.assertEqual(links.follow_items(order([legacy, supply, group])), [])
			links.follow_items(order([order_row("RA04-195.5")], docstatus=2))
			frappe.get_doc.assert_not_called()
		for row in (legacy, supply, group):
			self.assertEqual(row.ill_configured_fixture, "ILL-CF-old")

	def test_a_legacy_build_id_item_code_names_its_own_build(self):
		with service() as (links, frappe):
			frappe.db.exists.side_effect = lambda doctype, name: (
				doctype == "ilL-Configured-Fixture" and name == "ILL-CF-abc"
			)
			self.assertEqual(links.item_build("ILL-CF-abc"), ("ilL-Configured-Fixture", "ILL-CF-abc"))


class ScheduleLineFollowsTheRow(unittest.TestCase):
	def test_the_rows_new_fixture_build_reaches_its_one_row_line(self):
		line = schedule_line(
			"L1",
			manufacturer_type="ILLUMENATE",
			configured_fixture="ILL-CF-old",
			ill_item_code="RA04-120.0",
			ill_configurator_request="{}",
		)
		before = quote_row("R1", "L1", item_code="RA04-195.5", ill_configured_fixture="ILL-CF-old")
		row = quote_row(
			"R1",
			"L1",
			item_code="RA04-195.5",
			ill_configured_fixture="ILL-CF-new",
			ill_bom="BOM-RA04-195.5-001",
			ill_template_code="ILL-RA04-FS",
			ill_mfg_length_mm=4895,
		)
		with sync_service() as (sync, _):
			changes = sync.line_updates(line, row, before)
		self.assertEqual(changes["configured_fixture"], "ILL-CF-new")
		self.assertEqual(changes["ill_item_code"], "RA04-195.5")
		self.assertEqual(changes["ill_bom"], "BOM-RA04-195.5-001")
		self.assertEqual(changes["manufacturable_length_mm"], 4895)
		self.assertIsNone(changes["ill_configurator_request"])


class PinnedBuildError(unittest.TestCase):
	def test_the_mismatch_names_the_row_and_both_builds(self):
		row = order_row("RA04-195.5", ill_bom=None)
		old = Record(
			doctype="ilL-Configured-Fixture",
			name="ILL-CF-old",
			build_schema_version=2,
			configured_item="RA04-120.0",
			bom="BOM-RA04-120.0-001",
		)
		extras = {
			ROOT + ".api.build_artifacts": types.SimpleNamespace(
				assert_bom=MagicMock(), atomic_build=lambda function: function
			),
			ROOT + ".api.configuration_contract": types.SimpleNamespace(finite_number=float),
			ROOT + ".api.linear_build": types.SimpleNamespace(snapshot=lambda doc: {"components": []}),
		}
		with load_service(ROOT + ".api.manufacturing_order", extras) as (orders, frappe):
			frappe.get_doc.return_value = old
			with self.assertRaises(ValueError) as raised:
				orders.pinned_build(row)
		message = str(raised.exception)
		for text in ("Row 1", "RA04-195.5", "ILL-CF-old", "RA04-120.0"):
			self.assertIn(text, message)


if __name__ == "__main__":
	unittest.main()
