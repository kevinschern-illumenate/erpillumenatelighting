"""Pinned builds accept artifact links through Frappe's real save bookkeeping and reject content edits."""

import copy
import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

DOCTYPE = ROOT + ".doctype."


class Row(Record):
	def as_dict(self):
		return dict(self)


class FakeDocument(dict):
	"""Document double: key access through ``get`` and attributes, with a stored version."""

	def __init__(self, fields, values, old=None):
		super().__init__(values)
		object.__setattr__(self, "meta", Record(fields=fields))
		object.__setattr__(self, "flags", Record())
		object.__setattr__(self, "_old", old)

	def __getattr__(self, key):
		return self.get(key)

	def is_new(self):
		return self._old is None

	def get_doc_before_save(self):
		return self._old


def field(fieldname, fieldtype="Data", fetch_from=None):
	return Record(fieldname=fieldname, fieldtype=fieldtype, fetch_from=fetch_from)


def saving(controller, fields, values, **changes):
	"""Return the in-flight doc as Frappe presents it to ``validate`` after ``set_user_and_timestamp``."""
	old = FakeDocument(fields, copy.deepcopy(values))
	current = copy.deepcopy(values)
	current.update(changes)
	for table in (f.fieldname for f in fields if f.fieldtype == "Table"):
		current[table] = [
			Row({**row, "modified": "2026-09-29 12:00:00.000001", "modified_by": "saver@example.com"})
			for row in current.get(table) or []
		]
	return controller(fields, current, old)


def stored_rows(*rows):
	return [
		Row({**row, "name": f"row{index}", "modified": "2026-09-01 08:00:00", "modified_by": "a@example.com"})
		for index, row in enumerate(rows, start=1)
	]


def stub(name, **attributes):
	module = types.ModuleType(name)
	for key, value in attributes.items():
		setattr(module, key, value)
	return module


def document_module():
	return stub("frappe.model.document", Document=FakeDocument)


class ImmutabilityHelper(unittest.TestCase):
	def test_bookkeeping_and_fetched_fields_are_not_build_content(self):
		with load_service(ROOT + ".api.build_immutability") as (module, _frappe):
			fields = [
				field("section", "Section Break"),
				field("spec_sheet_link", fetch_from="fixture_template.spec_sheet"),
				field("segments", "Table"),
			]
			old = FakeDocument(fields, {"spec_sheet_link": "/a.pdf", "segments": stored_rows({"length": 10})})
			new = FakeDocument(
				fields,
				{
					"spec_sheet_link": "/b.pdf",
					"segments": [Row({**old["segments"][0], "modified": "later", "__unsaved": 1})],
				},
			)
			self.assertEqual(module.changed_fields(new, old, set()), [])

	def test_changed_fields_are_named(self):
		with load_service(ROOT + ".api.build_immutability") as (module, _frappe):
			fields = [field("cct"), field("segments", "Table")]
			old = FakeDocument(fields, {"cct": "3000K", "segments": stored_rows({"length": 10})})
			new = FakeDocument(
				fields, {"cct": "3000K", "segments": [Row({**old["segments"][0], "length": 11})]}
			)
			with self.assertRaisesRegex(ValueError, r"immutable \(changed: segments\)"):
				module.assert_unchanged(new, old, set(), "immutable")


class ControllerImmutability(unittest.TestCase):
	def assert_artifact_links_save(self, controller, fields, values, mutable_change, content_change, message):
		saving(controller, fields, values, **mutable_change).validate()
		with self.assertRaisesRegex(ValueError, message):
			saving(controller, fields, values, **content_change).validate()

	def test_tape_neon_accepts_item_and_bom_after_child_rows_are_restamped(self):
		extras = {
			"frappe.model.document": document_module(),
			ROOT + ".api.tape_neon_build": stub(ROOT + ".api.tape_neon_build", snapshot=MagicMock()),
		}
		with load_service(DOCTYPE + "ill_configured_tape_neon.ill_configured_tape_neon", extras) as (
			module,
			_frappe,
		):
			fields = [
				field("build_schema_version", "Int"),
				field("config_hash"),
				field("configured_item", "Link"),
				field("segments", "Table"),
				field("pricing_snapshot", "Table"),
			]
			values = {
				"build_schema_version": 2,
				"config_hash": "HASH",
				"segments": stored_rows({"segment_index": 1, "requested_length_mm": 1000}),
				"pricing_snapshot": stored_rows({"msrp_unit": 12.5}),
			}
			self.assert_artifact_links_save(
				module.ilLConfiguredTapeNeon,
				fields,
				values,
				{"configured_item": "TAPE-ITEM"},
				{"config_hash": "OTHER"},
				"This build is immutable",
			)

	def test_led_sheet_accepts_item_and_bom_after_group_rows_are_restamped(self):
		bundle = stub(
			ROOT + ".api.led_sheet_bundle",
			snapshot=MagicMock(),
			item_belongs=lambda code, doc: code == "SHEET-ITEM",
		)
		extras = {"frappe.model.document": document_module(), ROOT + ".api.led_sheet_bundle": bundle}
		with load_service(DOCTYPE + "ill_configured_led_sheet.ill_configured_led_sheet", extras) as (
			module,
			_frappe,
		):
			fields = [
				field("engine_version"),
				field("selected_cct", "Link"),
				field("configured_item", "Link"),
				field("bom", "Link"),
				field("groups", "Table"),
			]
			values = {
				"engine_version": "led-sheet-2",
				"selected_cct": "3000K",
				"groups": stored_rows({"sheet_count": 4, "compatible_driver": "DRV"}),
			}
			self.assert_artifact_links_save(
				module.ilLConfiguredLEDSheet,
				fields,
				values,
				{"configured_item": "SHEET-ITEM", "bom": "BOM-1"},
				{"configured_item": "SHEET-ITEM", "selected_cct": "4000K"},
				"This Sheet build is immutable",
			)

	def test_group_accepts_item_and_bom_after_member_rows_are_restamped(self):
		build = {
			"request": {"family": "LED Tape", "template": "T1"},
			"members": [{"member_key": "m1", "length": 1}],
			"power_plan": {
				"allocations": [
					{"run_key": "m1:r1", "supply": 1, "output": 1, "item_code": "DRV", "watts": 10.0}
				]
			},
		}
		extras = {
			"frappe.model.document": document_module(),
			ROOT + ".api.fixture_group_bom": stub(
				ROOT + ".api.fixture_group_bom", snapshot=lambda doc: copy.deepcopy(build)
			),
			ROOT + ".api.group_contract": stub(
				ROOT + ".api.group_contract", TEMPLATE_TYPES={"LED Tape": "ilL-Tape-Neon-Template"}
			),
		}
		with load_service(DOCTYPE + "ill_configured_group.ill_configured_group", extras) as (module, _frappe):
			fields = [
				field("family"),
				field("template_type"),
				field("template"),
				field("description", "Small Text"),
				field("configured_item", "Link"),
				field("members", "Table"),
				field("allocations", "Table"),
			]
			values = {
				"description": "Two runs",
				"family": "LED Tape",
				"template_type": "ilL-Tape-Neon-Template",
				"template": "T1",
				"members": stored_rows(
					{"member_key": "m1", "snapshot_json": json.dumps(build["members"][0])}
				),
				"allocations": stored_rows(
					{
						"member_key": "m1",
						"run_key": "m1:r1",
						"supply_number": 1,
						"output_number": 1,
						"item_code": "DRV",
						"watts": 10.0,
					}
				),
			}

			def controller(fields, values, old):
				doc = module.ilLConfiguredGroup(fields, values, old)
				doc.flags.group_engine_write = True
				return doc

			self.assert_artifact_links_save(
				controller,
				fields,
				values,
				{"configured_item": "GROUP-ITEM"},
				{"configured_item": "GROUP-ITEM", "description": "Three runs"},
				"Group engineering builds are immutable",
			)

	def test_linear_fixture_keeps_accepting_item_links(self):
		extras = {
			"frappe.model.document": document_module(),
			ROOT + ".api.linear_build": stub(ROOT + ".api.linear_build", snapshot=MagicMock()),
		}
		with load_service(DOCTYPE + "ill_configured_fixture.ill_configured_fixture", extras) as (
			module,
			_frappe,
		):
			fields = [
				field("build_schema_version", "Int"),
				field("finish", "Link"),
				field("spec_sheet_link", fetch_from="fixture_template.spec_sheet"),
				field("configured_item", "Link"),
				field("segments", "Table"),
			]
			values = {
				"build_schema_version": 2,
				"finish": "BLK",
				"spec_sheet_link": "/files/a.pdf",
				"segments": stored_rows({"segment_index": 1}),
			}
			self.assert_artifact_links_save(
				module.ilLConfiguredFixture,
				fields,
				values,
				{"configured_item": "FIXTURE-ITEM", "spec_sheet_link": "/files/b.pdf"},
				{"finish": "WHT"},
				"This fixture build is immutable",
			)


if __name__ == "__main__":
	unittest.main()
