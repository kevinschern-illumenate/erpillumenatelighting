"""Inbound shipments: totals, cost defaults, PO write-back, bill amounts, Landed Cost Voucher drafts."""

import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

PURCHASING = ROOT + ".api.purchasing"
BOARD = ROOT + ".api.purchasing_board"


def cost(
	cost_type, est=0, actual=None, account="Freight In - ilL", allocation="By value", included=1, pi=None
):
	return {
		"cost_type": cost_type,
		"estimated_amount": est,
		"actual_amount": actual,
		"expense_account": account,
		"allocation": allocation,
		"include_in_landed_cost": included,
		"purchase_invoice": pi,
	}


class Totals(unittest.TestCase):
	def test_totals_variance_and_landed_pct(self):
		with load_service(PURCHASING) as (p, _):
			pos = [{"po_value": 6000}, {"po_value": 4000}]
			costs = [cost("Freight", 800, 900), cost("Duty", 300), cost("Brokerage", 100, 150)]
			t = p.shipment_totals(pos, costs)
			self.assertEqual(t["goods_value"], 10000)
			self.assertEqual(t["estimated_cost_total"], 1200)
			self.assertEqual(t["actual_cost_total"], 1050)
			self.assertEqual(t["variance"], 150)  # billed lines only: 1050 vs 900 estimated
			self.assertEqual(t["landed_cost_pct"], 13.5)  # 900 + 300 (estimate) + 150 over 10,000
			self.assertEqual(p.shipment_totals([], [])["landed_cost_pct"], 0)
			self.assertEqual(p.po_shares(pos), [60.0, 40.0])
			self.assertEqual(
				p.po_shares([{"po_value": 1, "share_pct": 70}, {"po_value": 9, "share_pct": 30}]), [70, 30]
			)

	def test_new_cost_lines_get_their_type_defaults(self):
		with load_service(PURCHASING) as (p, _):
			settings = {
				"cost_defaults": {
					"Freight": {
						"include_in_landed_cost": 1,
						"allocation": "By qty",
						"expense_account": "Freight In - ilL",
					}
				}
			}
			freight = p.fill_cost_defaults({"cost_type": "Freight"}, settings)
			self.assertEqual(
				(freight["allocation"], freight["include_in_landed_cost"], freight["expense_account"]),
				("By qty", 1, "Freight In - ilL"),
			)
			storage = p.fill_cost_defaults({"cost_type": "Storage / demurrage"}, settings)
			self.assertEqual((storage["allocation"], storage["include_in_landed_cost"]), ("By value", 0))
			duty = p.fill_cost_defaults({"cost_type": "Duty"}, {})
			self.assertEqual((duty["allocation"], duty["include_in_landed_cost"]), ("By value", 1))
			# a line the team already set keeps its choices
			kept = p.fill_cost_defaults(
				{"cost_type": "Freight", "allocation": "Manual", "include_in_landed_cost": 0}, settings
			)
			self.assertEqual(
				(kept["allocation"], kept["include_in_landed_cost"], kept["expense_account"]),
				("Manual", 0, "Freight In - ilL"),
			)

	def test_estimates_from_settings_and_hts_rates(self):
		with load_service(PURCHASING) as (p, _):
			settings = {
				"cost_defaults": {
					"Freight": {
						"include_in_landed_cost": 1,
						"allocation": "By qty",
						"estimate_pct_of_value": 8,
					},
					"Brokerage": {
						"include_in_landed_cost": 1,
						"allocation": "By value",
						"estimate_flat_amount": 125,
					},
				}
			}
			hts = [
				{"value": 5000, "duty_pct": 3, "tariff_pct": 25},
				{"value": 5000, "duty_pct": 0, "tariff_pct": 0},
			]
			lines = {line["cost_type"]: line for line in p.estimate_costs(10000, settings, hts, "Ocean FCL")}
			self.assertEqual(lines["Freight"]["estimated_amount"], 800)
			self.assertEqual(lines["Duty"]["estimated_amount"], 150)
			self.assertEqual(lines["Tariff (additional)"]["estimated_amount"], 1250)
			self.assertEqual(lines["Brokerage"]["estimated_amount"], 125)
			self.assertIn("MPF / HMF", lines)  # code fallback rate
			self.assertNotIn("Storage / demurrage", lines)
			self.assertEqual(lines["Freight"]["allocation"], "By qty")

	def test_bill_amounts(self):
		with load_service(PURCHASING) as (p, _):
			one = [cost("Freight", 800, pi="PI-1")]
			self.assertEqual(p.fill_actuals(one, "PI-1", 912.5, []), 1)
			self.assertEqual(one[0]["actual_amount"], 912.5)
			split = [
				cost("Duty", 300, account="Duties - ilL", pi="PI-2"),
				cost("Brokerage", 100, account="Brokerage - ilL", pi="PI-2"),
			]
			items = [
				{"expense_account": "Duties - ilL", "base_net_amount": 310},
				{"expense_account": "Brokerage - ilL", "base_net_amount": 125},
			]
			self.assertEqual(p.fill_actuals(split, "PI-2", 435, items), 2)
			self.assertEqual([c["actual_amount"] for c in split], [310, 125])
			kept = [cost("Freight", 800, actual=777, pi="PI-1")]
			self.assertEqual(p.fill_actuals(kept, "PI-1", 912.5, []), 0)
			self.assertEqual(kept[0]["actual_amount"], 777)


class WriteBack(unittest.TestCase):
	def test_status_never_moves_backwards(self):
		with load_service(PURCHASING) as (p, _):
			self.assertEqual(p.forward_status("Sent", "Shipped"), "Shipped")
			self.assertEqual(p.forward_status(None, "Shipped"), "Shipped")
			self.assertIsNone(p.forward_status("Delivered", "Shipped"))
			self.assertIsNone(p.forward_status("Shipped", "Shipped"))
			self.assertIsNone(p.forward_status("Issue", "Delivered"))
			self.assertEqual(p.shipment_vendor_status("At port / customs"), "Shipped")
			self.assertEqual(p.shipment_vendor_status("Costs final"), "Delivered")
			self.assertIsNone(p.shipment_vendor_status("Planned"))

	def shipment(self, status, eta="2026-12-01", before=None):
		doc = MagicMock()
		doc.name = "ILL-SHP-2026-0001"
		doc.status = status
		doc.eta = eta
		values = {
			"eta": eta,
			"purchase_orders": [Record(purchase_order="PO-1"), Record(purchase_order="PO-2")],
		}
		doc.get.side_effect = lambda key, default=None: values.get(key, default)
		doc.get_doc_before_save.return_value = before
		return doc

	def test_write_back_moves_pos_forward_and_carries_eta(self):
		with load_service(PURCHASING) as (p, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.get_all.return_value = [
				Record(name="PO-1", ill_vendor_status="Confirmed", ill_eta="2026-11-20", per_received=0),
				Record(name="PO-2", ill_vendor_status="Delivered", ill_eta="2026-12-01", per_received=100),
			]
			before = Record(status="Booked", eta="2026-11-20")
			p.shipment_write_back(self.shipment("In transit", before=before))
			updates = {c.args[1]: c.args[2] for c in frappe.db.set_value.call_args_list}
			self.assertEqual(updates, {"PO-1": {"ill_vendor_status": "Shipped", "ill_eta": "2026-12-01"}})
			frappe.db.set_value.reset_mock()
			p.shipment_write_back(
				self.shipment("In transit", before=Record(status="In transit", eta="2026-12-01"))
			)
			frappe.db.set_value.assert_not_called()  # nothing changed

	def test_write_back_failure_is_logged_not_raised(self):
		with load_service(PURCHASING) as (p, frappe):
			frappe.get_meta.side_effect = RuntimeError("db down")
			frappe.log_error = MagicMock()
			p.shipment_write_back(self.shipment("Delivered"))
			self.assertIn("Purchasing hook failed", frappe.log_error.call_args.kwargs["title"])

	def test_email_from_po_marks_it_sent_once(self):
		with load_service(PURCHASING) as (p, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			frappe.utils.nowdate = lambda: "2026-11-18"
			frappe.db.get_value.return_value = Record(name="PO-1", docstatus=1, ill_vendor_status="Not sent")
			comm = Record(reference_doctype="Purchase Order", reference_name="PO-1", sent_or_received="Sent")
			p.on_communication(comm)
			frappe.db.set_value.assert_called_once_with(
				"Purchase Order",
				"PO-1",
				{"ill_vendor_status": "Sent", "ill_sent_on": "2026-11-18"},
				update_modified=False,
			)
			frappe.db.set_value.reset_mock()
			frappe.db.get_value.return_value = Record(name="PO-1", docstatus=1, ill_vendor_status="Confirmed")
			p.on_communication(comm)
			p.on_communication(
				Record(reference_doctype="Purchase Order", reference_name="PO-1", sent_or_received="Received")
			)
			frappe.db.set_value.assert_not_called()


class LandedCostVoucher(unittest.TestCase):
	RECEIPTS = ({"name": "PR-1", "docstatus": 1}, {"name": "PR-2", "docstatus": 1})

	def test_refuses_estimates_unless_allowed(self):
		with load_service(BOARD) as (pb, _):
			costs = [cost("Freight", 800, 900), cost("Duty", 300)]
			with self.assertRaisesRegex(ValueError, "No actual amount yet for: Duty"):
				pb.lcv_plan(costs, self.RECEIPTS)
			plan = pb.lcv_plan(costs, self.RECEIPTS, allow_estimate=True)
			self.assertEqual([t["amount"] for t in plan["taxes"]], [900, 300])

	def test_refuses_unsubmitted_receipts_and_missing_accounts(self):
		with load_service(BOARD) as (pb, _):
			costs = [cost("Freight", 800, 900)]
			with self.assertRaisesRegex(ValueError, "PR-2"):
				pb.lcv_plan(costs, [{"name": "PR-1", "docstatus": 1}, {"name": "PR-2", "docstatus": 0}])
			with self.assertRaisesRegex(ValueError, "no purchase receipts"):
				pb.lcv_plan(costs, [])
			with self.assertRaisesRegex(ValueError, "expense account"):
				pb.lcv_plan([cost("Freight", 800, 900, account=None)], self.RECEIPTS)
			with self.assertRaisesRegex(ValueError, "In Landed Cost"):
				pb.lcv_plan([cost("Storage / demurrage", 50, 50, included=0)], self.RECEIPTS)

	def test_one_taxes_row_per_included_cost_type(self):
		with load_service(BOARD) as (pb, _):
			costs = [
				cost("Freight", 500, 600, allocation="By qty"),
				cost("Freight", 100, 120, allocation="By qty"),
				cost("Drayage / delivery", 50, 60, allocation="By qty"),
				cost("Storage / demurrage", 40, 45, included=0, allocation="By qty"),
			]
			plan = pb.lcv_plan(costs, self.RECEIPTS)
			self.assertEqual(plan["basis"], "Qty")
			self.assertEqual(
				[(t["description"], t["amount"]) for t in plan["taxes"]],
				[("Freight", 720), ("Drayage / delivery", 60)],
			)
			self.assertTrue(all(t["expense_account"] for t in plan["taxes"]))

	def test_mixed_allocation_bases_are_refused(self):
		with load_service(BOARD) as (pb, _):
			costs = [
				cost("Freight", 500, 600, allocation="By qty"),
				cost("Duty", 300, 310, allocation="By value"),
			]
			with self.assertRaisesRegex(ValueError, "split them into two vouchers"):
				pb.lcv_plan(costs, self.RECEIPTS)
			manual = [
				cost("Freight", 500, 600, allocation="Manual"),
				cost("Duty", 300, 310, allocation="Manual"),
			]
			self.assertEqual(pb.lcv_plan(manual, self.RECEIPTS)["basis"], "Distribute Manually")

	def test_draft_voucher_is_inserted_never_submitted(self):
		with load_service(BOARD) as (pb, frappe):
			frappe.get_roles.return_value = ["Purchase Manager"]
			ship = MagicMock()
			ship.get.side_effect = lambda key, default=None: {
				"receipts": [Record(purchase_receipt="PR-1")],
				"costs": [Record(cost("Freight", 500, 600))],
			}.get(key, default)
			lcv = MagicMock(doctype="Landed Cost Voucher")
			lcv.name = "LCV-1"
			frappe.get_doc.side_effect = lambda *a: ship if a[0] == "ilL-Inbound-Shipment" else lcv
			frappe.get_list = MagicMock(
				return_value=[Record(name="PR-1", docstatus=1, supplier="Acme", company="C")]
			)
			frappe.get_meta.return_value.get_table_fields.return_value = []
			with patch.object(pb, "purchasing") as purchasing:
				purchasing.SHIPMENT = "ilL-Inbound-Shipment"
				purchasing.read_settings.return_value = {"company": "C"}
				result = pb.make_landed_cost_voucher("SHP-1")
			self.assertEqual(result["name"], "LCV-1")
			lcv.get_items_from_purchase_receipts.assert_called_once()
			lcv.insert.assert_called_once()
			lcv.submit.assert_not_called()
			ship.append.assert_called_with(
				"landed_cost_vouchers", {"landed_cost_voucher": "LCV-1", "lcv_docstatus": 0}
			)


if __name__ == "__main__":
	unittest.main()
