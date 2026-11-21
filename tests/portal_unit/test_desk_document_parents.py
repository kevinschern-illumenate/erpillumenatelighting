"""Desk "Configure & Add Fixture" on Purchase Order, RFQ, Material Request and Work Order."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_desk_configurator_save import desk, stub
from test_services import ROOT, Record

REPO = Path(__file__).resolve().parents[2]


class Row(Record):
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value

	def as_dict(self):
		return dict(self)


class Parent(Record):
	__setattr__ = dict.__setitem__

	def __init__(self, doctype, fields):
		super().__init__(doctype=doctype, items=[])
		self.meta = Record(has_field=lambda field: field in fields)

	def update(self, values):
		dict.update(self, values)

	def append(self, field, values):
		row = Row(values)
		self[field].append(row)
		return row


def set_child_value(row, field, value):
	row[field] = value


class DocumentParentGuards(unittest.TestCase):
	def test_document_parents_never_take_a_schedule(self):
		with desk() as (module, _frappe, builder, _sheets, _tape_neon):
			with patch.object(module, "_require_internal_user"), patch.object(module, "_require_parent_doctype"):
				for parent in ("Purchase Order", "Request for Quotation", "Material Request", "Work Order"):
					with self.subTest(parent=parent):
						result = module.build_configured_line(
							parent_doctype=parent,
							product_type="Linear Fixture",
							selections_json={},
							schedule="SCH-1",
						)
						self.assertFalse(result["success"])
						self.assertIn("fixture schedule", result["error"])
			builder._dispatch_save.assert_not_called()

	def test_work_order_refuses_catalog_parts_before_any_build(self):
		with desk() as (module, _frappe, builder, _sheets, _tape_neon):
			with patch.object(module, "_require_internal_user"), patch.object(module, "_require_parent_doctype"):
				for family in ("Driver", "Controller", "Extrusion Kit"):
					with self.subTest(family=family):
						result = module.build_configured_line(
							parent_doctype="Work Order", product_type=family, selections_json={}
						)
						self.assertFalse(result["success"])
						self.assertIn("Work Order", result["error"])
			builder._dispatch_save.assert_not_called()

	def test_only_selling_documents_use_schedules(self):
		with desk() as (module, _frappe, _builder, _sheets, _tape_neon):
			self.assertTrue(module.uses_schedule("Quotation"))
			self.assertTrue(module.uses_schedule("Sales Order"))
			for parent in ("Purchase Order", "Request for Quotation", "Material Request", "Work Order"):
				self.assertFalse(module.uses_schedule(parent))
				self.assertIn(parent, module.PARENT_DOCTYPES)
			self.assertNotIn("Driver", module._product_types_for("Work Order"))
			self.assertIn("Driver", module._product_types_for("Purchase Order"))

	def test_receipt_guard_accepts_the_same_parents(self):
		with desk() as (module, _frappe, _builder, _sheets, _tape_neon):
			source = (REPO / "illumenate_lighting/illumenate_lighting/portal/desk_build_receipt.py").read_text()
			for parent in module.PARENT_DOCTYPES:
				self.assertIn(f'"{parent}"', source)

	def test_purchasing_staff_without_a_sales_role_may_use_document_parents_only(self):
		with desk() as (module, frappe, _builder, _sheets, _tape_neon):
			staff = stub(ROOT + ".portal.staff", allowed=MagicMock(return_value=False))
			frappe.session = Record(user="buyer@illumenate.test")
			frappe.db.get_value.return_value = Record(enabled=1, user_type="System User")
			with patch.dict(sys.modules, {ROOT + ".portal.staff": staff}):
				module._require_internal_user("Purchase Order")
				module._require_internal_user("Work Order")
				for parent in ("Quotation", "Sales Order", None):
					with self.subTest(parent=parent), self.assertRaises(PermissionError):
						module._require_internal_user(parent)
				frappe.db.get_value.return_value = Record(enabled=1, user_type="Website User")
				with self.assertRaises(PermissionError):
					module._require_internal_user("Material Request")


class WorkOrderBuild(unittest.TestCase):
	def test_built_item_becomes_the_production_item_with_its_bom(self):
		with desk() as (module, frappe, _builder, _sheets, _tape_neon):
			frappe.db.get_value.return_value = Record(item_name="ILL-FIX", description="Fixture", stock_uom="Nos")
			frappe.db.exists.return_value = False
			frappe.get_meta.return_value = Record(
				has_field=lambda f: f in {"ill_configured_fixture", "ill_configurator_request", "ill_product_type"}
			)
			artifact = {"item_code": "ILL-FIX", "bom": "BOM-ILL-FIX-001", "configured_fixture": "CF-1", "product_type": "Linear Fixture"}
			result = module._work_order_result(artifact, "Linear Fixture", 4, '{"family":"Linear Fixture"}', [{"item": "PS"}], {})
			self.assertTrue(result["success"])
			self.assertTrue(result["work_order"])
			values = result["header_values"]
			self.assertEqual(values["production_item"], "ILL-FIX")
			self.assertEqual(values["bom_no"], "BOM-ILL-FIX-001")
			self.assertEqual(values["qty"], 4)
			self.assertEqual(values["ill_configured_fixture"], "CF-1")
			self.assertNotIn("ill_configured_tape_neon", values)  # not a Work Order field here
			self.assertEqual(len(result["notes"]), 1)  # included power supplies are ordered separately
			self.assertEqual(result["built"]["bom"], "BOM-ILL-FIX-001")

	def test_ship_in_pieces_build_cannot_be_one_work_order(self):
		with desk() as (module, _frappe, _builder, _sheets, _tape_neon):
			artifact = {
				"item_code": "ILL-FIX",
				"bom": None,
				"light_engines": [{"item_code": "ILL-FIX-LE1", "bom": "BOM-LE1", "qty": 2}],
			}
			result = module._work_order_result(artifact, "Linear Fixture", 1, "{}", [], {})
			self.assertFalse(result["success"])
			self.assertIn("Product Bundle", result["error"])
			self.assertIn("ILL-FIX-LE1", result["error"])


class DocumentRows(unittest.TestCase):
	def _row(self, module, frappe, parent, header, details, child_fields, **kwargs):
		parent_fields = {"supplier", "company", "schedule_date", "set_warehouse"}
		frappe.new_doc = lambda doctype: Parent(doctype, parent_fields)
		frappe.get_meta.return_value = Record(has_field=lambda f: f in child_fields)
		qoc = sys.modules[ROOT + ".api.quote_order_configurator"]
		qoc.tag_row_with_artifact = lambda row, artifact, *a, **kw: row.set("ill_bom", artifact.get("bom"))
		with (
			patch.object(module, "_set_child_value", set_child_value),
			patch.object(module, "_document_item_details", return_value=details),
		):
			return module._build_document_row_values(
				parent, None, header, kwargs.pop("artifact"), 2, section_label=None, fixture_type="L1", **kwargs
			)

	def test_purchase_order_row_falls_back_to_bom_cost_and_keeps_notes_in_the_description(self):
		with desk() as (module, frappe, _builder, _sheets, _tape_neon):
			bom = Record(total_cost=300.0, quantity=2.0)
			item = Record(item_name="ILL-FIX", stock_uom="Nos", description="Linear fixture 1200mm")
			frappe.db.get_value.side_effect = lambda doctype, *a, **kw: bom if doctype == "BOM" else item
			fields = {"item_code", "item_name", "description", "qty", "uom", "stock_uom", "conversion_factor",
				"stock_qty", "schedule_date", "warehouse", "rate", "amount", "bom", "ill_bom"}
			values = self._row(
				module, frappe, "Purchase Order",
				{"supplier": "ACME", "schedule_date": "2026-01-01", "set_warehouse": "Stores - IL"},
				{"expense_account": "Not a child field"},
				fields,
				artifact={"item_code": "ILL-FIX", "bom": "BOM-1", "configuration_snapshot": {}},
				additional_notes="Match finish to sample",
			)
			self.assertEqual(values["rate"], 150.0)
			self.assertEqual(values["amount"], 300.0)
			self.assertEqual(values["bom"], "BOM-1")
			self.assertEqual(values["ill_bom"], "BOM-1")
			self.assertEqual(values["warehouse"], "Stores - IL")
			# A past required-by date moves to today.
			self.assertEqual(values["schedule_date"], "2026-09-25")
			self.assertIn("Match finish to sample", values["description"])
			self.assertNotIn("expense_account", values)

	def test_material_request_row_has_no_price(self):
		with desk() as (module, frappe, _builder, _sheets, _tape_neon):
			frappe.db.get_value.return_value = Record(item_name="ILL-TAPE", stock_uom="Nos", description="Tape")
			fields = {"item_code", "qty", "uom", "schedule_date", "warehouse", "rate"}
			values = self._row(
				module, frappe, "Material Request", {"schedule_date": "2026-12-01"}, {}, fields,
				artifact={"item_code": "ILL-TAPE", "bom": "BOM-T", "configuration_snapshot": {}},
				additional_notes=None,
			)
			self.assertEqual(values["schedule_date"], "2026-12-01")
			self.assertNotIn("rate", values)
			self.assertEqual(values["qty"], 2)


class DialogWiring(unittest.TestCase):
	def test_every_document_parent_loads_the_button_script(self):
		hooks = (REPO / "illumenate_lighting/hooks.py").read_text()
		script = (REPO / "illumenate_lighting/public/js/configured_build_docs.js").read_text()
		state = (REPO / "illumenate_lighting/public/js/desk/dialog/state.js").read_text()
		self.assertIn("public/js/configured_build_docs.js", hooks)
		for parent in ("Purchase Order", "Request for Quotation", "Material Request", "Work Order"):
			self.assertIn(f"'{parent}'", script)
			self.assertIn(f'"{parent}"', hooks)
			self.assertIn(f"'{parent}'", state)

	def test_desk_dialog_follows_the_dark_theme(self):
		css = (REPO / "illumenate_lighting/public/css/configurator/desk_configurator.css").read_text()
		self.assertIn('[data-theme="dark"] .ill-desk-configurator-dialog', css)
		for shared in ("shared_configurator.css", "fixture_steps.css", "tape_neon_steps.css"):
			text = (REPO / "illumenate_lighting/public/css/configurator" / shared).read_text()
			# Bootstrap greys and blues go through tokens the desk theme re-points.
			for raw in ("#f8f9fa;", "#dee2e6;", "#0d6efd;", "#495057;"):
				self.assertNotIn(": " + raw, text, f"{shared} hardcodes {raw}")


if __name__ == "__main__":
	unittest.main()
