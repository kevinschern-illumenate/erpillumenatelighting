"""Desk "Configure & Add Fixture" segment decoding and schedule-line overwrite."""

import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import segment_list

SEGMENTS = [{"ip_rating": "IP67", "fixture_length_value": 150, "end_type": "Endcap"}]


class Doc(Record):
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value

	def append(self, field, values):
		row = Doc(name="child-new", **values)
		self[field].append(row)
		return row


def stub(name, **attrs):
	module = types.ModuleType(name)
	module.__dict__.update(attrs)
	return module


@contextmanager
def desk():
	policy = stub(ROOT + ".portal.access", can_edit_schedule=MagicMock(), can_read_schedule=MagicMock())
	with (
		load_service(ROOT + ".api.build_artifacts") as (atomic, _),
		load_service(
			ROOT + ".portal.configuration",
			{ROOT + ".portal.access": policy, ROOT + ".api.build_artifacts": atomic},
		) as (portal, _),
	):
		sheets = stub(
			ROOT + ".api.led_sheet_configurator",
			remove_sheet_accessories_for_line=MagicMock(),
			resync_led_sheet_line_accessories=MagicMock(),
		)
		tape_neon = stub(ROOT + ".api.tape_neon_configurator", _write_tape_neon_line=MagicMock())
		builder = stub(
			ROOT + ".api.configured_product_builder",
			_coerce_dict=lambda value: json.loads(value) if isinstance(value, str) else value,
			_dispatch_save=MagicMock(),
			_ensure_fixture_artifacts=MagicMock(),
			_ensure_tape_neon_artifacts=MagicMock(),
			_error_text_from_messages=MagicMock(),
			_fixture_payload_from_portal_selections=MagicMock(),
			_tape_neon_payload_from_portal_selections=MagicMock(return_value={}),
		)
		extras = {
			ROOT + ".api.led_sheet_configurator": sheets,
			ROOT + ".api.tape_neon_configurator": tape_neon,
			ROOT + ".api.build_artifacts": stub(ROOT + ".api.build_artifacts", atomic_build=lambda f: f),
			ROOT + ".api.configured_product_builder": builder,
			ROOT + ".api.manufacturing_generator": stub(
				ROOT + ".api.manufacturing_generator", ensure_configured_item_price=MagicMock()
			),
			ROOT + ".api.quote_order_configurator": stub(
				ROOT + ".api.quote_order_configurator",
				PRODUCT_TYPE_FIXTURE="Linear Fixture",
				PRODUCT_TYPE_TAPE="LED Tape",
				PRODUCT_TYPE_NEON="LED Neon",
				PRODUCT_TYPE_SHEET="LED Sheet",
				_apply_artifact_to_row=MagicMock(),
				_ensure_configured_artifacts=MagicMock(),
				_normalize_product_type=lambda value: value,
				_serialize_json=MagicMock(),
				_set_child_value=MagicMock(),
			),
			ROOT + ".api.webflow_schedule": stub(
				ROOT + ".api.webflow_schedule", _get_next_fixture_type_id=MagicMock()
			),
			ROOT + ".doctype.ill_project.ill_project": stub(
				ROOT + ".doctype.ill_project.ill_project", has_permission=MagicMock()
			),
			ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": stub(
				ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule",
				EDITABLE_STATUSES=("DRAFT", "READY"),
				has_permission=MagicMock(),
			),
			ROOT + ".portal.desk_build_receipt": stub(
				ROOT + ".portal.desk_build_receipt", idempotent=lambda f: f
			),
			ROOT + ".portal.site_flags": stub(ROOT + ".portal.site_flags", conf_flag=MagicMock()),
			ROOT + ".portal.configuration": portal,
		}
		with load_service(ROOT + ".api.desk_configurator", extras) as (module, frappe):
			yield module, frappe, builder, sheets, tape_neon


class DeskSegments(unittest.TestCase):
	def test_segment_list_unwraps_one_extra_encoding_and_rejects_other_shapes(self):
		encoded = json.dumps(SEGMENTS)
		for value in (SEGMENTS, encoded, json.dumps(encoded)):
			with self.subTest(value=value):
				self.assertEqual(segment_list(value), SEGMENTS)
		for empty in (None, "", "  "):
			self.assertIsNone(segment_list(empty))
		for invalid in ("[", json.dumps("text"), json.dumps({"ip_rating": "IP67"}), json.dumps(["IP67"])):
			with self.subTest(invalid=invalid), self.assertRaises(ValueError):
				segment_list(invalid)

	def test_build_hands_the_engine_payload_a_decoded_segment_list(self):
		with desk() as (module, _frappe, builder, _sheets, _tape_neon):
			builder._dispatch_save.return_value = {"is_valid": False, "error": "stop after dispatch"}
			call = dict(
				parent_doctype="Sales Order",
				product_type="LED Neon",
				selections_json={"cct": "3000K"},
				fixture_type="L2",
			)
			with (
				patch.object(module, "_require_internal_user"),
				patch.object(module, "_require_parent_doctype"),
			):
				# The desk dialog used to JSON-encode an already encoded string.
				for sent in (json.dumps(SEGMENTS), json.dumps(json.dumps(SEGMENTS)), SEGMENTS):
					builder._tape_neon_payload_from_portal_selections.reset_mock()
					result = module.build_configured_line(**call, segments_json=sent)
					self.assertEqual(result["error"], "stop after dispatch")
					self.assertEqual(
						builder._tape_neon_payload_from_portal_selections.call_args.args[2], SEGMENTS
					)
				builder._tape_neon_payload_from_portal_selections.reset_mock()
				result = module.build_configured_line(**call, segments_json=json.dumps("not a list"))
				self.assertFalse(result["success"])
				builder._tape_neon_payload_from_portal_selections.assert_not_called()


class DeskScheduleLine(unittest.TestCase):
	def test_overwriting_a_sheet_line_with_neon_drops_sheet_links_accessories_and_notes(self):
		with desk() as (module, _frappe, _builder, sheets, tape_neon):
			line = Doc(
				name="L1",
				manufacturer_type="ILLUMENATE",
				product_type="LED Sheet",
				configured_led_sheet="CLS-1",
				led_sheet_template="SHEET",
				trim_info="stale",
				notes="Configured LED Sheet CLS-1 | 2x2 panels",
			)
			schedule = Doc(name="S1", lines=[line])
			seen = {}
			sheets.remove_sheet_accessories_for_line.side_effect = lambda _s, row: seen.update(
				sheet=row.configured_led_sheet
			)
			module._write_schedule_line(
				schedule,
				0,
				"LED Neon",
				{"configured_tape_neon": "CTN-1", "item_code": "NEON-ITEM", "bom": "BOM-NEON"},
				{"computed": {}},
				fixture_type="L2",
				location="Exterior Stairs",
				qty=1,
				notes=None,
				tape_neon_template="NEON",
				msrp_unit=10,
			)
			self.assertEqual(seen, {"sheet": "CLS-1"})  # Accessories resolved before the link is cleared.
			self.assertIsNone(line.configured_led_sheet)
			self.assertIsNone(line.led_sheet_template)
			self.assertIsNone(line.trim_info)
			self.assertEqual(line.notes, "")
			self.assertEqual((line.ill_item_code, line.ill_bom), ("NEON-ITEM", "BOM-NEON"))
			self.assertEqual((line.line_id, line.location, line.qty), ("L2", "Exterior Stairs", 1))
			tape_neon._write_tape_neon_line.assert_called_once()
			sheets.resync_led_sheet_line_accessories.assert_not_called()


if __name__ == "__main__":
	unittest.main()
