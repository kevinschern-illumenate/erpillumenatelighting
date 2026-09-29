"""Installed-site regressions: pinned builds accept their Item and BOM through Frappe's real save.

Run on a migrated test site with bench run-tests --module
illumenate_lighting.illumenate_lighting.api.test_build_saves.
Frappe restamps modified/modified_by on every child row before validate runs,
which the portal_unit doubles can only imitate. A guard that compared child
rows verbatim rejected every Item/BOM attachment for Tape, Neon and Sheet builds.
"""

import json

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint


def _pinned(values, build, engine_flag):
	build = {
		**build,
		"components": [{"item_code": "REGRESSION-PART", "qty": 1}],
		"nonce": frappe.generate_hash(),
	}
	doc = frappe.get_doc(
		{**values, "build_snapshot_json": json.dumps(build), "config_hash": fingerprint(build)}
	)
	# Only Frappe's save bookkeeping is under test here, not engineering master data.
	doc.flags.ignore_links = True
	doc.flags[engine_flag] = True
	return doc.insert(ignore_permissions=True)


def _resave(doc, **values):
	doc = frappe.get_doc(doc.doctype, doc.name)
	doc.flags.ignore_links = True
	doc.update(values)
	return doc.save(ignore_permissions=True)


class TestBuildSaves(IntegrationTestCase):
	def test_tape_neon_build_accepts_item_and_bom_but_not_content_changes(self):
		doc = _pinned(
			{
				"doctype": "ilL-Configured-Tape-Neon",
				"naming_series": "ILL-CTN-.#####",
				"product_category": "LED Tape",
				"tape_neon_template": "REGRESSION-TEMPLATE",
				"build_schema_version": 2,
				"requested_length_mm": 1000,
				"segments": [{"segment_index": 1, "requested_length_mm": 1000, "end_type": "Endcap"}],
			},
			{"engine_version": "tape-neon-2"},
			"tape_engine_write",
		)
		_resave(doc, configured_item="REGRESSION-ITEM")
		saved = _resave(doc, bom="REGRESSION-BOM")
		self.assertEqual((saved.configured_item, saved.bom), ("REGRESSION-ITEM", "REGRESSION-BOM"))
		with self.assertRaisesRegex(frappe.ValidationError, "immutable"):
			_resave(doc, requested_length_mm=2000)

	def test_led_sheet_build_accepts_item_and_bom_but_not_content_changes(self):
		doc = _pinned(
			{
				"doctype": "ilL-Configured-LED-Sheet",
				"naming_series": "ILL-CLS-.#####",
				"engine_version": "led-sheet-2",
				"bundle_mode": "Bundle",
				"status": "Configured",
				"coverage_width_ft": 3,
				"groups": [{"group_number": 1, "sheet_count": 4, "group_watts": 80}],
			},
			{"engine_version": "led-sheet-2"},
			"sheet_engine_write",
		)
		saved = _resave(doc, configured_item="ILL-SHEET-" + doc.config_hash, bom="REGRESSION-BOM")
		self.assertEqual(saved.bom, "REGRESSION-BOM")
		with self.assertRaisesRegex(frappe.ValidationError, "immutable"):
			_resave(doc, coverage_width_ft=9)
