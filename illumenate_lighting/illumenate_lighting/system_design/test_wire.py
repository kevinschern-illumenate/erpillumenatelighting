# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for field wire specs and the CSV import (WP-1.4)."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import wire_import

HEADER = ",".join(wire_import.COLUMNS)


def row(code, mode="Per Foot", spool=""):
	values = {
		"item_code": code,
		"item_name": code,
		"wire_name": "18/2 CL3R test",
		"category": "class2-power",
		"applications": "class2-dc",
		"conductors": "2x18 Cu stranded power",
		"listing": "CL3R",
		"rated_v": "300",
		"temp_rating_c": "75",
		"riser": "1",
		"riser_label": "18/2 CL3R",
		"sales_uom_mode": mode,
		"spool_length_ft": spool,
		"source_reference": "Installed-site test datasheet",
	}
	return ",".join(values.get(column, "") for column in wire_import.COLUMNS)


class TestFieldWire(IntegrationTestCase):
	def test_masters_are_idempotent(self):
		wire_import.ensure_wire_masters()
		wire_import.ensure_wire_masters()
		self.assertTrue(frappe.db.exists("Item Group", "Field Wire"))
		self.assertTrue(frappe.db.exists("UOM", "Foot"))
		self.assertEqual(frappe.db.get_value("UOM", "Spool", "must_be_whole_number"), 1)

	def test_import_creates_sellable_items_and_specs(self):
		foot, spool = ("ZZTEST-WIRE-" + frappe.generate_hash(length=6).upper() for _ in range(2))
		text = "\n".join((HEADER, row(foot), row(spool, "Per Spool", "500")))
		report = wire_import.import_wire_csv(text, dry_run=False)
		self.assertTrue(report["written"], report)
		self.assertEqual(frappe.db.get_value("Item", foot, ["stock_uom", "is_sales_item"]), ("Foot", 1))
		self.assertEqual(frappe.db.get_value("Item", spool, "stock_uom"), "Spool")
		spec = frappe.get_doc("ilL-Spec-Wire", spool)
		self.assertEqual(
			(spec.category, spec.spool_length_ft, len(spec.conductors)), ("Class 2 Power", 500, 1)
		)
		again = wire_import.import_wire_csv(text, dry_run=True)
		self.assertEqual({r["spec_action"] for r in again["rows"]}, {"update"})

	def test_per_spool_needs_a_length(self):
		code = "ZZTEST-WIRE-" + frappe.generate_hash(length=6).upper()
		wire_import.import_wire_csv("\n".join((HEADER, row(code))), dry_run=False)
		spec = frappe.get_doc("ilL-Spec-Wire", code)
		spec.sales_uom_mode = "Per Spool"
		spec.spool_length_ft = 0
		with self.assertRaisesRegex(frappe.ValidationError, "Spool length"):
			spec.save(ignore_permissions=True)
