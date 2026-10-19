"""Order revision lines, deleting withdrawn drafts, and packing slip downloads."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jinja2.sandbox import SandboxedEnvironment
from test_services import ROOT, Record, load_service


def dependencies():
	access = types.ModuleType(ROOT + ".portal.access")
	access.get_actor = MagicMock(return_value=Record(user="sales@example.com", is_dealer=False))
	orders = types.ModuleType(ROOT + ".portal.orders")
	orders.load_accessible_sales_order = MagicMock(return_value=True)
	return {access.__name__: access, orders.__name__: orders}


PACKING_SLIP = Path(ROOT.replace(".", "/")) / "print_format/ill_delivery_note/ill_delivery_note.html"


class RevisionLines(unittest.TestCase):
	def test_lines_are_marked_against_the_original_request(self):
		with load_service(ROOT + ".portal.order_review", dependencies()) as (module, _frappe):
			original = {
				"items": [
					{"name": "a", "item_code": "X", "qty": 2, "rate": 10.0, "amount": 20},
					{"name": "b", "item_code": "Y", "qty": 1, "rate": 5, "amount": 5},
					{"name": "c", "item_code": "W", "qty": 1, "rate": 5, "amount": 5},
				]
			}
			current = {
				"items": [
					{"name": "a", "item_code": "X", "qty": 3.0, "rate": 10, "amount": 30},
					{"name": "c", "item_code": "W", "qty": 1.0, "rate": 5.0, "amount": 5.0},
					{"name": "d", "item_code": "Z", "qty": 1, "rate": 1, "amount": 1},
				]
			}
			lines = module.line_changes(original, current)
		self.assertEqual(
			[(line["item_code"], line["status"]) for line in lines],
			[("X", "changed"), ("W", "unchanged"), ("Z", "added"), ("Y", "removed")],
		)
		self.assertEqual(lines[0]["changed"], ["qty", "amount"])
		self.assertEqual(lines[0]["was"]["qty"], 2)


class DeleteWithdrawnDraft(unittest.TestCase):
	def trash(self, state, docstatus=0):
		with load_service(ROOT + ".portal.order_review", dependencies()) as (module, frappe):
			frappe.db.get_value.return_value = Record(name="INTAKE1", state=state)
			frappe.get_all.side_effect = lambda doctype, **kwargs: {
				"ilL-Quote-Offer": ["OFFER1"],
				"ilL-Order-Change": ["CHANGE1"],
			}.get(doctype, [])
			module.on_trash(Record(name="SO1", docstatus=docstatus))
			return frappe

	def test_withdrawn_request_releases_its_links_and_keeps_history(self):
		frappe = self.trash("WITHDRAWN")
		cleared = {call.args[:3] for call in frappe.db.set_value.call_args_list}
		self.assertEqual(
			cleared,
			{
				("ilL-Order-Intake", "INTAKE1", "sales_order"),
				("ilL-Quote-Offer", "OFFER1", "sales_order"),
				("ilL-Order-Change", "CHANGE1", "sales_order"),
				("ilL-Order-Change", "CHANGE1", "result_sales_order"),
			},
		)
		frappe.get_doc.return_value.add_comment.assert_called_once()

	def test_open_request_must_be_decided_before_delete(self):
		with self.assertRaisesRegex(ValueError, "still open"):
			self.trash("UNDER_REVIEW")

	def test_submitted_orders_are_left_to_erpnext(self):
		frappe = self.trash("APPROVED", docstatus=1)
		frappe.db.set_value.assert_not_called()


class PackingSlip(unittest.TestCase):
	def test_packing_slip_renders_without_shadowing_translation(self):
		source = PACKING_SLIP.read_text()
		self.assertNotRegex(source, r"set\s+_\s*=")

		class Doc:
			def __init__(self, **values):
				self.__dict__.update(values)

			def __getattr__(self, key):
				return None

			def get(self, key, default=None):
				return self.__dict__.get(key, default)

			def get_formatted(self, key):
				return str(self.get(key))

		items = [
			Doc(
				idx=1,
				item_code="A",
				item_name="Alpha",
				qty=2,
				uom="Nos",
				against_sales_order="SO1",
				ill_section_label="Lobby",
			),
			Doc(idx=2, item_code="B", item_name="Beta", qty=1, uom="Nos", against_sales_order="SO1"),
		]
		doc = Doc(
			name="DN1",
			items=items,
			customer_name="Buyer",
			posting_date="2026-10-01",
			vehicle_no="1Z",
			total_qty=3,
		)
		html = (
			SandboxedEnvironment()
			.from_string(source)
			.render(
				doc=doc,
				frappe=Doc(utils=Doc(format_date=str)),
				_=lambda text: text,
				ill_sanitize_html=lambda text: text,
			)
		)
		self.assertIn("Packing Slip", html)
		self.assertIn("1Z", html)
		self.assertIn("SO1", html)
		self.assertNotIn("Rate", html)


class OrderDocumentDownload(unittest.TestCase):
	def test_broken_site_format_falls_back_to_standard(self):
		access = types.ModuleType(ROOT + ".portal.access")
		access.get_actor = MagicMock(return_value=Record(is_guest=False, user="buyer@example.com"))
		with load_service(ROOT + ".portal.orders", {access.__name__: access}) as (module, frappe):
			frappe.PrintFormatError = type("PrintFormatError", (Exception,), {})
			frappe.clear_last_message = MagicMock()
			frappe.log_error = MagicMock()
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(doctype="Delivery Note", docstatus=1)
			calls = []

			def get_print(doctype, name, print_format=None, **kwargs):
				calls.append(print_format)
				if print_format != "Standard":
					raise frappe.PrintFormatError("line 14")
				return b"%PDF"

			frappe.get_print = get_print
			with patch.object(module, "_customer_document_accessible", return_value=True):
				filename, pdf = module.get_order_document_pdf("Delivery Note", "DN1")
		self.assertEqual(calls, ["ilL Delivery Note", "Standard"])
		self.assertEqual((filename, pdf), ("Packing-Slip-DN1.pdf", b"%PDF"))


if __name__ == "__main__":
	unittest.main()
