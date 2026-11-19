"""Supplier part numbers and descriptions on Purchase Orders and RFQs, kept on the Item."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

SERVICE = ROOT + ".api.supplier_parts"
DESC = "custom_supplier_description"
LINE = "ill_supplier_description"
REPO = Path(__file__).resolve().parents[2]


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


class Document(Row):
	def __init__(self, doctype, items, **values):
		super().__init__(doctype=doctype, docstatus=0, items=[Row(i) for i in items], **values)
		self["flags"] = Record()


def setup(frappe, items, has_description=True):
	frappe.get_meta.return_value.has_field.return_value = has_description
	frappe.db.exists.return_value = True
	frappe.get_doc.side_effect = lambda doctype, name: items[name]


def item_supplier_rows(items):
	"""frappe.get_all over the Items' Supplier Items rows, as the database would answer it."""

	def get_all(doctype, filters=None, fields=None, order_by=None):
		codes, supplier = filters["parent"][1], filters["supplier"]
		return [
			Record(parent=code, **row)
			for code in codes
			if code in items
			for row in items[code].supplier_items
			if row.get("supplier") == supplier
		]

	return get_all


class ReadParts(unittest.TestCase):
	def test_first_row_for_the_supplier_wins_and_missing_items_are_blank(self):
		with load_service(SERVICE) as (sp, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.get_all.return_value = [
				Record(parent="A", supplier_part_no="V-1", **{DESC: "Profile"}),
				Record(parent="A", supplier_part_no="V-OLD", **{DESC: "Old"}),
			]
			result = sp.get_supplier_part_info("ACME", json.dumps(["A", "B", "A", ""]))
			self.assertTrue(result["has_description"])
			self.assertEqual(result["items"]["A"]["supplier_part_no"], "V-1")
			self.assertEqual(result["items"]["A"]["supplier_description"], "Profile")
			self.assertFalse(result["items"]["B"]["found"])
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual((filters["parent"], filters["supplier"]), (["in", ["A", "B"]], "ACME"))

	def test_rfq_reads_need_rfq_permission_and_other_doctypes_are_refused(self):
		with load_service(SERVICE) as (sp, frappe):
			frappe.get_meta.return_value.has_field.return_value = False
			frappe.get_all.return_value = []
			sp.get_supplier_part_info("ACME", ["A"], doctype="Request for Quotation")
			self.assertEqual(frappe.has_permission.call_args.args, ("Request for Quotation", "read"))
			self.assertNotIn(DESC, frappe.get_all.call_args.kwargs["fields"])
			with self.assertRaises(ValueError):
				sp.get_supplier_part_info("ACME", ["A"], doctype="Sales Order")

	def test_supplier_is_required(self):
		with load_service(SERVICE) as (sp, _):
			with self.assertRaises(ValueError):
				sp.get_supplier_part_info("", ["A"])


class DialogSave(unittest.TestCase):
	def test_updates_existing_row_adds_missing_and_skips_unchanged(self):
		items = {
			"A": Item(
				"A",
				[
					{"supplier": "OTHER", "supplier_part_no": "X"},
					{"supplier": "ACME", "supplier_part_no": "OLD"},
				],
			),
			"B": Item("B"),
			"C": Item("C", [{"supplier": "ACME", "supplier_part_no": "C-1", DESC: "Same"}]),
		}
		rows = [
			{"item_code": "A", "supplier_part_no": " NEW ", "supplier_description": "Profile\nAnodized"},
			{"item_code": "B", "supplier_part_no": "B-9", "supplier_description": ""},
			{"item_code": "C", "supplier_part_no": "C-1", "supplier_description": "Same"},
		]
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			result = sp.update_supplier_part_info("ACME", json.dumps(rows))
		self.assertEqual(result, {"updated": ["A", "B"], "unchanged": ["C"], "lines": []})
		self.assertEqual(items["A"].supplier_items[0].supplier_part_no, "X")  # other supplier untouched
		self.assertEqual(items["A"].supplier_items[1].supplier_part_no, "NEW")
		self.assertEqual(items["A"].supplier_items[1][DESC], "Profile\nAnodized")
		self.assertEqual(
			items["B"].supplier_items, [{"supplier": "ACME", "supplier_part_no": "B-9", DESC: ""}]
		)
		items["C"].save.assert_not_called()
		self.assertFalse(items["A"].flags.ignore_permissions)  # Item permissions apply

	def test_blank_dialog_value_clears_the_item(self):
		items = {"A": Item("A", [{"supplier": "ACME", "supplier_part_no": "P", DESC: "D"}])}
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			sp.update_supplier_part_info(
				"ACME", [{"item_code": "A", "supplier_part_no": "", "supplier_description": ""}]
			)
		self.assertEqual(
			(items["A"].supplier_items[0].supplier_part_no, items["A"].supplier_items[0][DESC]), ("", "")
		)

	def test_needs_item_write_permission_on_every_item_before_any_save(self):
		items = {"A": Item("A"), "B": Item("B")}
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			frappe.has_permission.side_effect = lambda doctype, ptype="read", doc=None, throw=False: (
				(_ for _ in ()).throw(PermissionError) if doc == "B" else True
			)
			with self.assertRaises(PermissionError):
				sp.update_supplier_part_info(
					"ACME",
					[
						{"item_code": "A", "supplier_part_no": "1"},
						{"item_code": "B", "supplier_part_no": "2"},
					],
				)
			self.assertIn(("Item", "write"), [c.args for c in frappe.has_permission.call_args_list])
		items["A"].save.assert_not_called()

	def test_rfq_saves_need_rfq_write_permission_and_leave_lines_alone(self):
		items = {"A": Item("A")}
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			result = sp.update_supplier_part_info(
				"ACME",
				[{"item_code": "A", "supplier_part_no": "1"}],
				doctype="Request for Quotation",
				name="RFQ-1",
			)
			self.assertEqual(frappe.has_permission.call_args_list[0].args, ("Request for Quotation", "write"))
			frappe.db.set_value.assert_not_called()
		self.assertEqual(result["lines"], [])

	def test_submitted_po_lines_are_corrected_and_noted(self):
		order = Record(
			name="PO-1",
			docstatus=1,
			supplier="ACME",
			items=[
				Record(name="L1", item_code="A", supplier_part_no="OLD"),
				Record(name="L2", item_code="A", supplier_part_no="NEW", **{LINE: "D"}),
			],
			check_permission=MagicMock(),
			add_comment=MagicMock(),
		)
		items = {"A": Item("A", [{"supplier": "ACME", "supplier_part_no": "OLD"}])}
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			frappe.get_doc.side_effect = lambda doctype, name: (
				order if doctype == "Purchase Order" else items[name]
			)
			result = sp.update_supplier_part_info(
				"ACME",
				[{"item_code": "A", "supplier_part_no": "NEW", "supplier_description": "D"}],
				name="PO-1",
			)
			frappe.db.set_value.assert_called_once_with(
				"Purchase Order Item", "L1", {"supplier_part_no": "NEW", LINE: "D"}, update_modified=False
			)
		self.assertEqual(result["lines"], ["L1"])
		self.assertIn("A: OLD → NEW", order.add_comment.call_args.args[1])


class DocumentSupplier(unittest.TestCase):
	def test_po_supplier_and_single_supplier_rfq(self):
		with load_service(SERVICE) as (sp, _):
			self.assertEqual(sp.document_supplier(Document("Purchase Order", [], supplier="ACME")), "ACME")
			one = Document("Request for Quotation", [], suppliers=[Row(supplier="ACME")])
			two = Document("Request for Quotation", [], suppliers=[Row(supplier="ACME"), Row(supplier="B")])
			self.assertEqual(sp.document_supplier(one), "ACME")
			self.assertIsNone(sp.document_supplier(two))


class LineFill(unittest.TestCase):
	def test_blank_line_values_come_from_the_item(self):
		items = {"A": Item("A", [{"supplier": "ACME", "supplier_part_no": "P-1", DESC: "Profile"}])}
		doc = Document(
			"Purchase Order",
			[
				{"item_code": "A"},
				{"item_code": "A", "supplier_part_no": "KEEP", LINE: "Mine"},
				{"item_code": "Z"},
			],
			supplier="ACME",
		)
		with load_service(SERVICE) as (sp, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.get_all.side_effect = item_supplier_rows(items)
			sp.fill_line_supplier_parts(doc)
		self.assertEqual((doc["items"][0].supplier_part_no, doc["items"][0][LINE]), ("P-1", "Profile"))
		self.assertEqual((doc["items"][1].supplier_part_no, doc["items"][1][LINE]), ("KEEP", "Mine"))
		self.assertIsNone(doc["items"][2].get("supplier_part_no"))

	def test_rfq_with_several_suppliers_and_submitted_docs_are_left_alone(self):
		with load_service(SERVICE) as (sp, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			sp.fill_line_supplier_parts(
				Document(
					"Request for Quotation",
					[{"item_code": "A"}],
					suppliers=[Row(supplier="A"), Row(supplier="B")],
				)
			)
			submitted = Document("Purchase Order", [{"item_code": "A"}], supplier="ACME")
			submitted["docstatus"] = 1
			sp.fill_line_supplier_parts(submitted)
			frappe.get_all.assert_not_called()


class LineWriteBack(unittest.TestCase):
	def test_changed_line_values_are_saved_to_the_item(self):
		items = {
			"A": Item("A", [{"supplier": "ACME", "supplier_part_no": "OLD", DESC: "Keep"}]),
			"B": Item("B"),
			"C": Item("C", [{"supplier": "ACME", "supplier_part_no": "C-1", DESC: "Same"}]),
		}
		doc = Document(
			"Request for Quotation",
			[
				{"item_code": "A", "supplier_part_no": "NEW", LINE: ""},
				{"item_code": "B", "supplier_part_no": "", LINE: "New description"},
				{"item_code": "C", "supplier_part_no": "C-1", LINE: "Same"},
			],
			suppliers=[Row(supplier="ACME")],
		)
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			frappe.get_all.side_effect = item_supplier_rows(items)
			sp.save_line_supplier_parts(doc)
		# A blank line description never clears the Item's.
		self.assertEqual(
			(items["A"].supplier_items[0].supplier_part_no, items["A"].supplier_items[0][DESC]),
			("NEW", "Keep"),
		)
		self.assertEqual(
			items["B"].supplier_items, [{"supplier": "ACME", "supplier_part_no": "", DESC: "New description"}]
		)
		items["C"].save.assert_not_called()

	def test_items_the_user_cannot_edit_are_skipped_with_a_message(self):
		items = {"A": Item("A"), "B": Item("B")}
		doc = Document(
			"Purchase Order",
			[{"item_code": "A", "supplier_part_no": "1"}, {"item_code": "B", "supplier_part_no": "2"}],
			supplier="ACME",
		)
		with load_service(SERVICE) as (sp, frappe):
			setup(frappe, items)
			frappe.get_all.side_effect = item_supplier_rows(items)
			frappe.has_permission.side_effect = lambda doctype, ptype="read", doc=None, throw=False: (
				doc != "B"
			)
			sp.save_line_supplier_parts(doc)
			messages = " ".join(str(c.args[0]) for c in frappe.msgprint.call_args_list)
		items["A"].save.assert_called_once()
		items["B"].save.assert_not_called()
		self.assertIn("B", messages.split("Item:")[-1])

	def test_nothing_to_do_without_one_supplier(self):
		doc = Document(
			"Request for Quotation",
			[{"item_code": "A", "supplier_part_no": "1"}],
			suppliers=[Row(supplier="A"), Row(supplier="B")],
		)
		with load_service(SERVICE) as (sp, frappe):
			sp.save_line_supplier_parts(doc)
			frappe.get_doc.assert_not_called()


class Wiring(unittest.TestCase):
	def test_hooks_script_and_patch(self):
		hooks = (REPO / "illumenate_lighting" / "hooks.py").read_text(encoding="utf-8")
		for doctype in ("Purchase Order", "Request for Quotation"):
			self.assertIn(f'"{doctype}": "public/js/supplier_parts.js"', hooks)
		self.assertEqual(hooks.count("supplier_parts.fill_line_supplier_parts"), 2)
		self.assertEqual(hooks.count("supplier_parts.save_line_supplier_parts"), 2)
		self.assertTrue((REPO / "illumenate_lighting" / "public" / "js" / "supplier_parts.js").exists())
		patches = (REPO / "illumenate_lighting" / "patches.txt").read_text().split("[post_model_sync]", 1)[1]
		self.assertIn("illumenate_lighting.patches.add_supplier_part_line_fields", patches.splitlines())
		install = (REPO / "illumenate_lighting" / "illumenate_lighting" / "install.py").read_text()
		self.assertIn("illumenate_lighting.patches.add_supplier_part_line_fields import", install)

	def test_patch_shows_the_part_number_and_adds_the_description(self):
		created = MagicMock()
		setter = MagicMock()
		extras = {
			"frappe.custom.doctype.custom_field.custom_field": type(
				"m", (), {"create_custom_fields": created}
			),
			"frappe.custom.doctype.property_setter.property_setter": type(
				"m", (), {"make_property_setter": setter}
			),
		}
		with load_service("illumenate_lighting.patches.add_supplier_part_line_fields", extras) as (
			patch,
			frappe,
		):
			frappe.db.exists.return_value = True
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.clear_cache = MagicMock()
			patch.execute()
		fields = created.call_args.args[0]
		self.assertEqual(set(fields), {"Purchase Order Item", "Request for Quotation Item"})
		for (field,) in fields.values():
			self.assertEqual((field["fieldname"], field["insert_after"]), (LINE, "supplier_part_no"))
		self.assertIn("read_only_depends_on", fields["Request for Quotation Item"][0])
		set_props = {(c.args[0], c.args[2], c.args[3]) for c in setter.call_args_list}
		for doctype in fields:
			self.assertIn((doctype, "hidden", "0"), set_props)
			self.assertIn((doctype, "read_only", "0"), set_props)


if __name__ == "__main__":
	unittest.main()
