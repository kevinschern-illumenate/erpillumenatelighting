"""Linear lens sources follow the resolved Item and the checked-in DocType schema."""

import json
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_linear_builds import BuildDoc
from test_services import ROOT, Record, load_service


class LinearEngineeringSources(unittest.TestCase):
	def setUp(self):
		self.schemas = {}
		root = Path(__file__).resolve().parents[2] / "illumenate_lighting/illumenate_lighting/doctype"
		for path in root.glob("*/*.json"):
			schema = json.loads(path.read_text(encoding="utf-8-sig"))
			self.schemas[schema["name"]] = {field["fieldname"] for field in schema["fields"]}
		self.records = {
			("ilL-Spec-Lens", "LENS-A"): Record(
				item="LENS-A", lens_appearance="Diffused", stock_length_mm=2000, family="A"
			),
			("ilL-Spec-Lens", "LENS-B"): Record(
				item="LENS-B", lens_appearance="Diffused", stock_length_mm=3000, family="B"
			),
			("ilL-Rel-Tape Offering", "OFFERING"): Record(tape_spec="TAPE"),
			("ilL-Spec-LED Tape", "TAPE"): Record(item="TAPE", watts_per_foot=4),
			("ilL-Spec-Profile", "PROFILE"): Record(item="PROFILE", width_mm=20),
			("ilL-Spec-Driver", "DRIVER"): Record(item="DRIVER", max_wattage=96),
		}

	def get_value(self, doctype, name, fields, *, as_dict=False):
		requested = [fields] if isinstance(fields, str) else fields
		self.assertFalse(set(requested) - (self.schemas[doctype] | {"name"}), (doctype, requested))
		if doctype == "ilL-Configured-Fixture":
			return None  # Save a new build.
		record = self.records.get((doctype, name))
		if record is None:
			return None
		if as_dict:
			return Record({field: record.get(field) for field in requested})
		return record.get(fields)

	def test_preview_and_save_capture_the_resolved_lens_and_valid_source_fields(self):
		material = types.SimpleNamespace(build_fixture_bom_items=lambda doc: [])
		for in_memory in (True, False):
			for lens, appearance in (
				("LENS-A", "Diffused"),
				("LENS-B", "Diffused"),
				("LENS-A", None),
				(None, "Diffused"),
			):
				with (
					self.subTest(in_memory=in_memory, lens=lens, appearance=appearance),
					load_service(ROOT + ".api.engineering_sources") as (sources, _),
					load_service(
						ROOT + ".api.linear_build",
						{
							ROOT + ".api.engineering_sources": sources,
							ROOT + ".api.manufacturing_generator": material,
						},
					) as (engine, frappe),
					patch.object(sources, "frappe", frappe),
					patch.object(engine, "cable_manifest", return_value=[]),
				):
					frappe.db.get_value.side_effect = self.get_value
					frappe.get_all.return_value = []
					doc = BuildDoc(
						fixture_template="FIXTURE",
						tape_offering="OFFERING",
						profile_item="PROFILE",
						lens_item=lens,
						lens_appearance=appearance,
						drivers=[Record(driver_item="DRIVER")],
						flags=BuildDoc(),
						insert=MagicMock(),
					)
					result = engine.finish(doc, {}, {}, {}, True, None, in_memory=in_memory)
					captured = engine.snapshot(doc)["engineering_sources"]
					self.assertEqual(captured["ilL-Spec-Lens"]["name"], lens)
					self.assertEqual(
						captured["ilL-Spec-Lens"].get("stock_length_mm"),
						self.records.get(("ilL-Spec-Lens", lens), {}).get("stock_length_mm"),
					)
					self.assertEqual(captured["ilL-Spec-LED Tape"]["watts_per_foot"], 4)
					self.assertEqual(captured["ilL-Spec-Profile"]["width_mm"], 20)
					self.assertEqual(captured["ilL-Spec-Driver"]["max_wattage"], 96)
					if in_memory:
						self.assertIs(result, doc)
						doc.insert.assert_not_called()
						frappe.db.sql.assert_not_called()
					else:
						self.assertEqual(result, doc.name)
						doc.insert.assert_called_once_with(ignore_permissions=True)

	def test_legacy_submittal_uses_resolved_lens_not_shared_appearance(self):
		with (
			load_service(ROOT + ".api.engineering_sources") as (sources, _),
			load_service(ROOT + ".api.spec_submittal", {ROOT + ".api.engineering_sources": sources}) as (
				service,
				frappe,
			),
		):
			frappe.db.get_value.side_effect = self.get_value
			for lens, expected in (("LENS-A", 2000), ("LENS-B", 3000), (None, None)):
				with self.subTest(lens=lens):
					doc = Record(lens_item=lens, lens_appearance="Diffused")
					self.assertEqual(
						service._get_source_value(
							"ilL-Spec-Lens",
							"stock_length_mm",
							configured_fixture=doc,
						),
						expected,
					)

	def test_sealed_submittal_keeps_lens_data_when_master_changes(self):
		with (
			load_service(ROOT + ".api.engineering_sources") as (sources, frappe),
			load_service(ROOT + ".api.spec_submittal", {ROOT + ".api.engineering_sources": sources}) as (
				service,
				submittal_frappe,
			),
		):
			frappe.db.get_value.side_effect = self.get_value
			doc = Record(
				build_snapshot_json=json.dumps(
					{
						"engine_version": "linear-2",
						"engineering_sources": sources.capture(lens="LENS-A"),
					}
				)
			)
			self.records[("ilL-Spec-Lens", "LENS-A")]["stock_length_mm"] = 9000
			self.assertEqual(
				service._get_source_value(
					"ilL-Spec-Lens",
					"stock_length_mm",
					configured_fixture=doc,
				),
				2000,
			)
			submittal_frappe.db.get_value.assert_not_called()
