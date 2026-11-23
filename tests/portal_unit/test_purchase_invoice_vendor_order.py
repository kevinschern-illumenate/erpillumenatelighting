"""Purchase Invoice Vendor Order / Ack #, carried from the Purchase Order(s)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

PURCHASING = ROOT + ".api.purchasing"


def invoice(*orders, **values):
	doc = Record(items=[Record(purchase_order=o) for o in orders], **values)
	doc.meta = MagicMock()
	doc.meta.has_field.return_value = True
	doc.set = lambda key, value: doc.__setitem__(key, value)
	return doc


class VendorOrderNumbers(unittest.TestCase):
	def test_values_follow_line_order_and_skip_blanks_and_repeats(self):
		with load_service(PURCHASING) as (p, frappe):
			frappe.get_all.return_value = [
				["PO-2", "ACK-2"],
				["PO-1", " ACK-1 "],
				["PO-3", None],
				["PO-4", "ACK-2"],
			]
			value = p.vendor_order_numbers(["PO-1", None, "PO-2", "PO-1", "PO-3", "PO-4"])
			self.assertEqual(value, "ACK-1, ACK-2")
			self.assertEqual(
				frappe.get_all.call_args.kwargs["filters"], {"name": ["in", ["PO-1", "PO-2", "PO-3", "PO-4"]]}
			)

	def test_no_orders_makes_no_query(self):
		with load_service(PURCHASING) as (p, frappe):
			self.assertEqual(p.vendor_order_numbers([None, ""]), "")
			frappe.get_all.assert_not_called()


class FillInvoice(unittest.TestCase):
	def test_blank_invoice_takes_the_purchase_order_value(self):
		with load_service(PURCHASING) as (p, frappe):
			frappe.get_all.return_value = [["PO-1", "PI-EG976261106"]]
			doc = invoice("PO-1", "PO-1")
			p.fill_invoice_vendor_order(doc)
			self.assertEqual(doc.ill_vendor_order_no, "PI-EG976261106")

	def test_a_value_already_on_the_invoice_is_kept(self):
		with load_service(PURCHASING) as (p, frappe):
			doc = invoice("PO-1", ill_vendor_order_no="TYPED")
			p.fill_invoice_vendor_order(doc)
			self.assertEqual(doc.ill_vendor_order_no, "TYPED")
			frappe.get_all.assert_not_called()

	def test_invoice_without_purchase_orders_stays_blank(self):
		with load_service(PURCHASING) as (p, _frappe):
			doc = invoice(None)
			p.fill_invoice_vendor_order(doc)
			self.assertIsNone(doc.ill_vendor_order_no)


class PushFromPurchaseOrder(unittest.TestCase):
	def test_ack_entered_later_reaches_blank_invoices(self):
		with load_service(PURCHASING) as (p, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.get_all.side_effect = [
				["PINV-1"],  # invoices on this PO with no value yet
				["PO-1", "PO-1"],  # PINV-1's lines
				[["PO-1", "ACK-9"]],  # the PO values
			]
			p.push_vendor_order_to_invoices(Record(name="PO-1", ill_vendor_order_no="ACK-9"))
			filters = frappe.get_all.call_args_list[0].kwargs["filters"]
			self.assertIn(["Purchase Invoice Item", "purchase_order", "=", "PO-1"], filters)
			self.assertIn(["ill_vendor_order_no", "is", "not set"], filters)
			frappe.db.set_value.assert_called_once_with(
				"Purchase Invoice", "PINV-1", "ill_vendor_order_no", "ACK-9", update_modified=False
			)

	def test_blank_purchase_order_value_changes_nothing(self):
		with load_service(PURCHASING) as (p, frappe):
			p.push_vendor_order_to_invoices(Record(name="PO-1", ill_vendor_order_no=""))
			frappe.get_all.assert_not_called()
			frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
