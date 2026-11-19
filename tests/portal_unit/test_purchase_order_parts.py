"""Purchase Order "Supplier Parts": part numbers and descriptions saved back onto Items."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

SERVICE = ROOT + ".api.purchase_order"
DESC = "custom_supplier_description"


class Row(Record):
	def __setattr__(self, key, value):
		self[key] = value


class Item(Record):
	def __init__(self, code, rows=()):
		super().__init__(name=code, supplier_items=[Row(r) for r in rows])
		self["flags"] = Record()
		self["save"] = MagicMock()

	def append(self, field, values):
		self[field].append(Row(values))


def setup(frappe, items, has_description=True):
	frappe.get_meta.return_value.has_field.return_value = has_description
	frappe.db.exists.return_value = True
	frappe.get_doc.side_effect = lambda doctype, name: items[name]


class ReadParts(unittest.TestCase):
	def test_first_row_for_the_supplier_wins_and_missing_items_are_blank(self):
		with load_service(SERVICE) as (po, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.get_all.return_value = [
				Record(parent="A", supplier_part_no="V-1", **{DESC: "Profile"}),
				Record(parent="A", supplier_part_no="V-OLD", **{DESC: "Old"}),
			]
			result = po.get_supplier_part_info("ACME", json.dumps(["A", "B", "A", ""]))
			self.assertTrue(result["has_description"])
			self.assertEqual(result["items"]["A"]["supplier_part_no"], "V-1")
			self.assertEqual(result["items"]["A"]["supplier_description"], "Profile")
			self.assertEqual(
				result["items"]["B"], {"supplier_part_no": "", "supplier_description": "", "found": False}
			)
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(filters["parent"], ["in", ["A", "B"]])
			self.assertEqual(filters["supplier"], "ACME")
			self.assertIn(DESC, frappe.get_all.call_args.kwargs["fields"])

	def test_without_the_custom_field_description_is_not_queried(self):
		with load_service(SERVICE) as (po, frappe):
			frappe.get_meta.return_value.has_field.return_value = False
			frappe.get_all.return_value = []
			result = po.get_supplier_part_info("ACME", ["A"])
			self.assertFalse(result["has_description"])
			self.assertNotIn(DESC, frappe.get_all.call_args.kwargs["fields"])

	def test_supplier_is_required(self):
		with load_service(SERVICE) as (po, _):
			with self.assertRaises(ValueError):
				po.get_supplier_part_info("", ["A"])


class SaveParts(unittest.TestCase):
	def test_updates_existing_row_adds_missing_and_skips_unchanged(self):
		items = {
			"A": Item(
				"A",
				[
					{"supplier": "OTHER", "supplier_part_no": "X"},
					{"supplier": "ACME", "supplier_part_no": "OLD", DESC: ""},
				],
			),
			"B": Item("B"),
			"C": Item("C", [{"supplier": "ACME", "supplier_part_no": "C-1", DESC: "Same"}]),
		}
		with load_service(SERVICE) as (po, frappe):
			setup(frappe, items)
			result = po.update_supplier_part_info(
				"ACME",
				json.dumps(
					[
						{
							"item_code": "A",
							"supplier_part_no": " NEW ",
							"supplier_description": "Profile\nAnodized",
						},
						{"item_code": "B", "supplier_part_no": "B-9", "supplier_description": ""},
						{"item_code": "C", "supplier_part_no": "C-1", "supplier_description": "Same"},
					]
				),
			)
		self.assertEqual(result, {"updated": ["A", "B"], "unchanged": ["C"], "lines": []})
		self.assertEqual(items["A"].supplier_items[0].supplier_part_no, "X")  # other supplier untouched
		self.assertEqual(items["A"].supplier_items[1].supplier_part_no, "NEW")
		self.assertEqual(items["A"].supplier_items[1][DESC], "Profile\nAnodized")
		self.assertEqual(
			items["B"].supplier_items, [{"supplier": "ACME", "supplier_part_no": "B-9", DESC: ""}]
		)
		items["A"].save.assert_called_once()
		items["C"].save.assert_not_called()
		self.assertFalse(items["A"].flags.ignore_permissions)  # Item permissions apply

	def test_blank_values_add_no_row(self):
		items = {"A": Item("A")}
		with load_service(SERVICE) as (po, frappe):
			setup(frappe, items)
			result = po.update_supplier_part_info("ACME", [{"item_code": "A"}])
		self.assertEqual(result["unchanged"], ["A"])
		self.assertEqual(items["A"].supplier_items, [])

	def test_description_ignored_without_the_custom_field(self):
		items = {"A": Item("A", [{"supplier": "ACME", "supplier_part_no": "P"}])}
		with load_service(SERVICE) as (po, frappe):
			setup(frappe, items, has_description=False)
			result = po.update_supplier_part_info(
				"ACME", [{"item_code": "A", "supplier_part_no": "P", "supplier_description": "x"}]
			)
		self.assertEqual(result["unchanged"], ["A"])
		self.assertNotIn(DESC, items["A"].supplier_items[0])

	def test_needs_item_write_permission_on_every_item_before_any_save(self):
		items = {"A": Item("A"), "B": Item("B")}
		with load_service(SERVICE) as (po, frappe):
			setup(frappe, items)

			def check(doctype, ptype="read", doc=None, throw=False):
				if doctype == "Item" and doc == "B":
					raise PermissionError
				return True

			frappe.has_permission.side_effect = check
			with self.assertRaises(PermissionError):
				po.update_supplier_part_info(
					"ACME",
					[
						{"item_code": "A", "supplier_part_no": "A-1"},
						{"item_code": "B", "supplier_part_no": "B-1"},
					],
				)
			calls = [c.args for c in frappe.has_permission.call_args_list]
			self.assertIn(("Item", "write"), calls)
		items["A"].save.assert_not_called()

	def test_needs_purchase_order_write_permission(self):
		with load_service(SERVICE) as (po, frappe):
			frappe.has_permission.side_effect = PermissionError
			with self.assertRaises(PermissionError):
				po.update_supplier_part_info("ACME", [])
			self.assertEqual(frappe.has_permission.call_args.args, ("Purchase Order", "write"))

	def test_submitted_po_lines_are_corrected_and_noted(self):
		order = Record(
			name="PO-1",
			docstatus=1,
			supplier="ACME",
			items=[
				Record(name="L1", item_code="A", supplier_part_no="OLD"),
				Record(name="L2", item_code="A", supplier_part_no="NEW"),
			],
			check_permission=MagicMock(),
			add_comment=MagicMock(),
		)
		items = {"A": Item("A", [{"supplier": "ACME", "supplier_part_no": "OLD"}])}
		with load_service(SERVICE) as (po, frappe):
			setup(frappe, items)
			frappe.get_doc.side_effect = lambda doctype, name: (
				order if doctype == "Purchase Order" else items[name]
			)
			result = po.update_supplier_part_info(
				"ACME", [{"item_code": "A", "supplier_part_no": "NEW"}], "PO-1"
			)
			frappe.db.set_value.assert_called_once_with(
				"Purchase Order Item", "L1", "supplier_part_no", "NEW", update_modified=False
			)
		self.assertEqual(result["lines"], ["L1"])
		self.assertIn("A: OLD → NEW", order.add_comment.call_args.args[1])

	def test_draft_po_lines_are_left_to_the_form(self):
		order = Record(
			name="PO-2",
			docstatus=0,
			supplier="ACME",
			items=[Record(name="L1", item_code="A")],
			check_permission=MagicMock(),
		)
		items = {"A": Item("A")}
		with load_service(SERVICE) as (po, frappe):
			setup(frappe, items)
			frappe.get_doc.side_effect = lambda doctype, name: (
				order if doctype == "Purchase Order" else items[name]
			)
			result = po.update_supplier_part_info(
				"ACME", [{"item_code": "A", "supplier_part_no": "NEW"}], "PO-2"
			)
			frappe.db.set_value.assert_not_called()
		self.assertEqual(result["lines"], [])


class FormScript(unittest.TestCase):
	def test_purchase_order_script_is_registered(self):
		hooks = Path("illumenate_lighting/hooks.py").read_text(encoding="utf-8")
		self.assertIn('"Purchase Order": "public/js/purchase_order.js"', hooks)
		self.assertTrue(Path("illumenate_lighting/public/js/purchase_order.js").exists())


if __name__ == "__main__":
	unittest.main()
