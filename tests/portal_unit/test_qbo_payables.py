import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


def utils():
	module = types.ModuleType("frappe.utils")
	module.flt = lambda value, precision=None: (
		round(float(value or 0), precision) if precision is not None else float(value or 0)
	)
	module.cint = lambda value: int(value or 0)
	module.getdate = lambda value: str(value)[:10]
	module.nowdate = lambda: "2026-10-13"
	module.now_datetime = lambda: "2026-10-13 12:00:00"
	module.add_to_date = lambda value, minutes=0: f"{value} {minutes:+d}m"
	return {module.__name__: module}


def invoice(name, party="Acme", outstanding=100.0, company="ilL", doctype="Sales Invoice"):
	field = "customer" if doctype == "Sales Invoice" else "supplier"
	account = "debit_to" if doctype == "Sales Invoice" else "credit_to"
	return Record(
		name=name,
		company=company,
		grand_total=outstanding,
		outstanding_amount=outstanding,
		**{field: party, f"{field}_name": party, account: "Party - ilL"},
	)


class Allocations(unittest.TestCase):
	def test_allocations_define_the_invoices_and_repeats_are_summed(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, _frappe):
			event = module._normalize_payload(
				{
					"qbo_payment_id": "9",
					"event_type": "Create",
					"amount": 300,
					"qbo_invoice_ids": ["10", "11"],
					"allocations": [
						{"qbo_invoice_id": "10", "amount": 100},
						{"qbo_invoice_id": "11", "amount": 150},
						{"qbo_invoice_id": "10", "amount": 50},
					],
				}
			)
			self.assertEqual(event["allocations"], [("10", 150.0), ("11", 150.0)])
			self.assertEqual(event["qbo_invoice_ids"], ["10", "11"])

	def test_listed_invoice_without_an_amount_is_refused(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, _frappe):
			with self.assertRaises(module.QBOSyncError) as refused:
				module._normalize_payload(
					{
						"qbo_payment_id": "9",
						"event_type": "Create",
						"qbo_invoice_ids": ["10", "11"],
						"allocations": [{"qbo_invoice_id": "10", "amount": 100}],
					}
				)
			self.assertEqual(refused.exception.code, "invalid_allocation")

	def test_bill_payment_reads_bill_and_vendor_keys(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, _frappe):
			event = module._normalize_payload(
				{
					"qbo_payment_id": "77",
					"event_type": "Create",
					"amount": 40,
					"vendor_qbo_id": "5",
					"allocations": [{"qbo_bill_id": "300", "amount": 40}],
				},
				module.PAY,
			)
			self.assertEqual(event["allocations"], [("300", 40.0)])
			self.assertEqual(event["customer_qbo_id"], "5")

	def test_legacy_single_invoice_takes_the_whole_payment(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, _frappe):
			event = module._normalize_payload(
				{"qbo_payment_id": "9", "event_type": "Create", "amount": 80, "qbo_invoice_id": "10"}
			)
			self.assertEqual(module._resolve_allocations(event), [("10", 80.0)])


class Upsert(unittest.TestCase):
	def run_upsert(self, module, frappe, payload, invoices, kind=None):
		kind = kind or module.RECEIVE
		frappe.db.exists.return_value = False
		module._match_invoice = MagicMock(side_effect=lambda qbo_id, _kind: invoices[qbo_id])
		module._get_submitted_payment_entry = MagicMock(return_value=None)
		module._update_log = MagicMock()
		module._create_payment_entry = MagicMock(return_value=Record(name="PE-1"))
		event = module._normalize_payload(payload, kind)
		return module._handle_upsert(event, Record(name="LOG-1"), kind)

	def test_one_payment_settles_two_invoices(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			invoices = {"10": invoice("SINV-1", outstanding=100), "11": invoice("SINV-2", outstanding=60)}
			result = self.run_upsert(
				module,
				frappe,
				{
					"qbo_payment_id": "9",
					"event_type": "Create",
					"amount": 160,
					"allocations": [
						{"qbo_invoice_id": "10", "amount": 100},
						{"qbo_invoice_id": "11", "amount": 60},
					],
				},
				invoices,
			)
			self.assertEqual(result["action"], "created")
			applied, _event, kind = module._create_payment_entry.call_args.args
			self.assertEqual(
				[(inv.name, amount) for inv, amount in applied], [("SINV-1", 100.0), ("SINV-2", 60.0)]
			)
			self.assertIs(kind, module.RECEIVE)
			matched = module._update_log.call_args_list[0].kwargs
			self.assertEqual(matched["allocations"], "SINV-1: 100.00\nSINV-2: 60.00")
			self.assertFalse(module._update_log.call_args_list[-1].kwargs.get("warnings"))

	def test_allocations_above_the_payment_are_refused(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			with self.assertRaises(module.QBOSyncError) as refused:
				self.run_upsert(
					module,
					frappe,
					{
						"qbo_payment_id": "9",
						"event_type": "Create",
						"amount": 100,
						"allocations": [
							{"qbo_invoice_id": "10", "amount": 80},
							{"qbo_invoice_id": "11", "amount": 40},
						],
					},
					{"10": invoice("SINV-1"), "11": invoice("SINV-2")},
				)
			self.assertEqual(refused.exception.code, "allocation_exceeds_payment")
			module._create_payment_entry.assert_not_called()

	def test_invoices_of_two_customers_are_refused(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			with self.assertRaises(module.QBOSyncError) as refused:
				self.run_upsert(
					module,
					frappe,
					{
						"qbo_payment_id": "9",
						"event_type": "Create",
						"amount": 100,
						"allocations": [
							{"qbo_invoice_id": "10", "amount": 50},
							{"qbo_invoice_id": "11", "amount": 50},
						],
					},
					{"10": invoice("SINV-1"), "11": invoice("SINV-2", party="Other")},
				)
			self.assertEqual(refused.exception.code, "mixed_parties")

	def test_unapplied_remainder_is_a_warning(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			self.run_upsert(
				module,
				frappe,
				{
					"qbo_payment_id": "9",
					"event_type": "Create",
					"amount": 120,
					"allocations": [{"qbo_invoice_id": "10", "amount": 100}],
				},
				{"10": invoice("SINV-1")},
			)
			self.assertIn("stays unallocated", module._update_log.call_args_list[-1].kwargs["warnings"][0])

	def test_bill_payment_matches_purchase_invoices_by_pay_entries_only(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			bill = invoice("PINV-1", party="Supplier A", outstanding=40, doctype="Purchase Invoice")
			self.run_upsert(
				module,
				frappe,
				{"qbo_payment_id": "77", "event_type": "Create", "amount": 40, "qbo_bill_id": "300"},
				{"300": bill},
				module.PAY,
			)
			module._get_submitted_payment_entry.assert_called_with("77", module.PAY)
			self.assertEqual(frappe.db.exists.call_args.args[1]["payment_type"], "Pay")
			self.assertEqual(module._update_log.call_args_list[0].kwargs["purchase_invoice"], "PINV-1")


class Matching(unittest.TestCase):
	def test_in_sync_compares_every_allocation(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			frappe.db.get_value.return_value = Record(paid_amount=160, posting_date="2026-09-15")
			frappe.get_all.return_value = [
				Record(reference_name="SINV-2", allocated_amount=60),
				Record(reference_name="SINV-1", allocated_amount=100),
			]
			event = {"amount": 160, "txn_date": "2026-09-15"}
			same = [(invoice("SINV-1"), 100.0), (invoice("SINV-2"), 60.0)]
			moved = [(invoice("SINV-1"), 110.0), (invoice("SINV-2"), 50.0)]
			self.assertTrue(module._is_in_sync("PE-1", event, same))
			self.assertFalse(module._is_in_sync("PE-1", event, moved))

	def test_existing_entry_lookup_is_scoped_to_payment_type(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			module._get_submitted_payment_entry("77", module.PAY)
			self.assertEqual(frappe.db.get_value.call_args.args[1]["payment_type"], "Pay")


class BillPaymentEntry(unittest.TestCase):
	def entry(self, module, frappe, settings):
		module._get_settings = MagicMock(return_value=settings)
		frappe.db.exists.return_value = True
		frappe.db.get_value.return_value = "USD"
		pe = Record(flags=Record(), references=[])
		pe.append = lambda table, row: pe[table].append(row)
		pe.insert = MagicMock()
		pe.submit = MagicMock()
		frappe.new_doc = MagicMock(return_value=pe)
		bill = invoice("PINV-1", party="Supplier A", outstanding=40, doctype="Purchase Invoice")
		event = {"qbo_payment_id": "77", "event_type": "Create", "amount": 40, "txn_date": "2026-10-01"}
		return module._create_payment_entry([(bill, 40.0)], event, module.PAY)

	def test_pays_the_supplier_from_the_configured_bank(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			pe = self.entry(module, frappe, {"paid_from_account": "Bank - ilL"})
			self.assertEqual(pe.payment_type, "Pay")
			self.assertEqual((pe.party_type, pe.party), ("Supplier", "Supplier A"))
			self.assertEqual((pe.paid_from, pe.paid_to), ("Bank - ilL", "Party - ilL"))
			self.assertEqual(pe.references[0]["reference_doctype"], "Purchase Invoice")
			pe.submit.assert_called_once()

	def test_refuses_without_a_paid_from_account(self):
		with load_service(ROOT + ".api.qbo_sync", utils()) as (module, frappe):
			with self.assertRaises(module.QBOSyncError) as refused:
				self.entry(module, frappe, {"paid_to_account": "Trust - ilL"})
			self.assertEqual(refused.exception.code, "paid_from_account_missing")


def qbo_sync_stub(settings):
	stub = types.ModuleType(ROOT + ".api.qbo_sync")

	class QBOSyncError(Exception):
		def __init__(self, code, message):
			super().__init__(message)
			self.code = code
			self.message = message

	stub.SIGNATURE_HEADER = "X-QBO-Signature"
	stub.QBOSyncError = QBOSyncError
	stub._commit = MagicMock()
	stub._get_settings = MagicMock(return_value=settings)
	stub._get_webhook_secret = MagicMock(return_value="secret")
	stub._record_auth_failure = MagicMock()
	stub._verify_signature = MagicMock(return_value=True)
	return {stub.__name__: stub, **utils()}


ON = {"bill_webhook_url": "https://n8n.example/webhook/bills", "bills_from_date": "2026-11-01"}


def purchase_invoice(**values):
	base = dict(
		name="PINV-1",
		company="ilL",
		supplier="SUP-1",
		supplier_name="Supplier A",
		posting_date="2026-11-03",
		due_date="2026-12-03",
		currency="USD",
		is_return=0,
		grand_total=118.0,
		rounded_total=118.0,
		items=[
			Record(item_code="TAPE", item_name="Tape", qty=2, net_amount=60),
			Record(item_code="LENS", item_name="Lens", qty=1, net_amount=40),
		],
	)
	return Record(**{**base, **values})


class BillPush(unittest.TestCase):
	def test_payload_lines_and_adjustment_add_up_to_the_total(self):
		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.db.get_value.return_value = "V-9"
			payload = module.bill_payload(purchase_invoice())
			self.assertEqual([line["amount"] for line in payload["lines"]], [60.0, 40.0])
			self.assertEqual(payload["adjustment"], 18.0)
			self.assertEqual(payload["total"], 118.0)
			self.assertEqual(payload["vendor_qbo_id"], "V-9")

	def test_nothing_is_queued_before_the_cutover_for_returns_or_when_off(self):
		cases = [
			(ON, purchase_invoice(posting_date="2026-10-31")),
			(ON, purchase_invoice(is_return=1)),
			({"bill_webhook_url": "https://n8n.example/x"}, purchase_invoice()),
		]
		for settings, doc in cases:
			with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(settings)) as (module, frappe):
				frappe.enqueue = MagicMock()
				module.on_submit(doc)
				frappe.enqueue.assert_not_called()
		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.enqueue = MagicMock()
			module.on_cancel(purchase_invoice())
			self.assertEqual(frappe.enqueue.call_args.kwargs["bill_event"], "Cancel")
			self.assertTrue(frappe.enqueue.call_args.kwargs["enqueue_after_commit"])

	def test_send_signs_the_exact_body(self):
		import hashlib
		import hmac

		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.get_doc.return_value = purchase_invoice()
			frappe.db.get_value.return_value = None
			requests = types.ModuleType("requests")
			requests.post = MagicMock()
			with patch.dict("sys.modules", {"requests": requests}):
				self.assertTrue(module.send("PINV-1"))
			kwargs = requests.post.call_args.kwargs
			expected = hmac.new(b"secret", kwargs["data"], hashlib.sha256).hexdigest()
			self.assertEqual(kwargs["headers"]["X-QBO-Signature"], expected)
			self.assertEqual(json.loads(kwargs["data"])["purchase_invoice"], "PINV-1")

	def test_failed_send_is_logged_for_the_hourly_retry(self):
		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.get_doc.return_value = purchase_invoice()
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="trace")
			requests = types.ModuleType("requests")
			requests.post = MagicMock(side_effect=OSError("n8n down"))
			with patch.dict("sys.modules", {"requests": requests}):
				self.assertFalse(module.send("PINV-1"))
			frappe.log_error.assert_called_once()

	def test_retry_picks_unlinked_invoices_from_the_cutover(self):
		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.get_all.return_value = []
			module.send_pending()
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(filters["custom_qbo_id"], ["is", "not set"])
			self.assertEqual(filters["posting_date"], [">=", "2026-11-01"])
			self.assertEqual(filters["is_return"], 0)


class BillLink(unittest.TestCase):
	def test_writes_bill_id_and_the_invoice_supplier_vendor_id(self):
		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.db.exists.return_value = True
			values = {("Purchase Invoice", "supplier"): "SUP-1"}
			frappe.db.get_value.side_effect = lambda doctype, _name, field: values.get((doctype, field))
			result = module.link_bill(
				{"purchase_invoice": "PINV-1", "qbo_bill_id": "300", "vendor_qbo_id": "9"}
			)
			self.assertEqual(result["supplier"], "SUP-1")
			written = [call.args[:4] for call in frappe.db.set_value.call_args_list]
			self.assertEqual(
				written,
				[
					("Purchase Invoice", "PINV-1", "custom_qbo_id", "300"),
					("Supplier", "SUP-1", "custom_qbo_id", "9"),
				],
			)

	def test_a_different_existing_id_is_a_conflict(self):
		with load_service(ROOT + ".api.qbo_bills", qbo_sync_stub(ON)) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.db.get_value.return_value = "299"
			with self.assertRaises(Exception) as refused:
				module.link_bill({"purchase_invoice": "PINV-1", "qbo_bill_id": "300"})
			self.assertEqual(refused.exception.code, "qbo_id_conflict")
			frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
