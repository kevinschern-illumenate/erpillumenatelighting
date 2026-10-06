# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for the ERPNext -> QuickBooks push (qbo_push.py / qbo_client.py).

Run inside a bench:
    bench --site <site> run-tests --app illumenate_lighting \
        --module illumenate_lighting.illumenate_lighting.api.test_qbo_push

QuickBooks is replaced by FakeQBO, and ERPNext documents by in-memory dicts,
so the tests don't need a seeded Company / Customer / Sales Invoice. The
outbox state machine runs against the real ilL-QBO-Push-Log doctype.
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from illumenate_lighting.illumenate_lighting.api import qbo_client, qbo_push
from illumenate_lighting.illumenate_lighting.api.qbo_client import QBOError

MOD = "illumenate_lighting.illumenate_lighting.api.qbo_push"
TEST_PREFIX = "TEST-QBOPUSH-"


class FakeQBO:
	"""Tiny in-memory QuickBooks: enough of query/read/create/operation for the handlers."""

	def __init__(self):
		self.store = {}  # entity -> {id: record}
		self.calls = []
		self.next_id = 100
		self.fail_next = None

	def _add(self, entity, record):
		self.next_id += 1
		record = dict(record, Id=str(self.next_id), SyncToken="0")
		self.store.setdefault(entity, {})[record["Id"]] = record
		return record

	def query(self, statement):
		self.calls.append(("query", statement))
		entity = statement.split(" from ")[1].split()[0]
		rows = list(self.store.get(entity, {}).values())
		if " where " in statement:
			field, value = statement.split(" where ")[1].split(" = ", 1)
			value = value.split(" and ")[0].strip().strip("'").replace("\\'", "'")
			field = field.strip()
			rows = [
				r
				for r in rows
				if str((r.get(field) or {}).get("value") if isinstance(r.get(field), dict) else r.get(field))
				== value
			]
		return {entity: rows} if rows else {}

	def query_one(self, entity, statement):
		rows = self.query(statement).get(entity) or []
		return rows[0] if rows else None

	def read(self, entity, qbo_id):
		self.calls.append(("read", entity, qbo_id))
		record = self.store.get(entity, {}).get(str(qbo_id))
		if not record:
			raise QBOError("Object Not Found", status=400, code="610")
		return record

	def create(self, entity, body, requestid):
		self.calls.append(("create", entity, requestid, json.loads(json.dumps(body))))
		if self.fail_next:
			error, self.fail_next = self.fail_next, None
			raise error
		total = round(
			sum(
				-line["Amount"] if line.get("DetailType") == "DiscountLineDetail" else line.get("Amount", 0)
				for line in body.get("Line", [])
			),
			2,
		)
		if entity == "Payment":
			total = body.get("TotalAmt", 0)
		return self._add(entity, dict(body, TotalAmt=total, Balance=total))

	def update(self, entity, body, requestid):
		self.calls.append(("update", entity, requestid, body))
		self.store[entity][body["Id"]].update(body)
		return self.store[entity][body["Id"]]

	def operation(self, entity, body, operation, requestid, include=None):
		self.calls.append(("operation", entity, operation, include, body))
		record = self.store[entity][str(body["Id"])]
		if operation == "delete":
			del self.store[entity][str(body["Id"])]
			return {"Id": body["Id"], "status": "Deleted"}
		record.update(TotalAmt=0, Balance=0, PrivateNote="Voided")
		return record

	def created(self, entity):
		return [c for c in self.calls if c[0] == "create" and c[1] == entity]


SETTINGS = frappe._dict(
	push_enabled=1,
	qbo_default_item="ERPNext Sales",
	qbo_tax_item="Sales Tax",
	qbo_tax_code="NON",
	item_group_map=[frappe._dict(item_group="Drivers", qbo_item_name="Drivers Income")],
)


def _row(**kw):
	return frappe._dict(kw)


def _invoice(**overrides):
	si = frappe._dict(
		doctype="Sales Invoice",
		name="ACC-SINV-2026-00042",
		docstatus=1,
		is_return=0,
		company="Test Co",
		currency="USD",
		customer="CUST-1",
		posting_date="2026-10-06",
		due_date="2026-11-05",
		contact_email="buyer@example.com",
		customer_address=None,
		shipping_address_name=None,
		po_no="PO-77",
		custom_qbo_id=None,
		disable_rounded_total=0,
		grand_total=118.36,
		rounded_total=118.0,
		items=[
			_row(
				item_code="LF-1",
				item_name="Linear 1",
				item_group="Fixtures",
				qty=2,
				net_rate=50,
				net_amount=100,
			),
			_row(
				item_code="DRV-1", item_name="Driver", item_group="Drivers", qty=3, net_rate=0.3, net_amount=1
			),
		],
		taxes=[
			_row(description="WA Sales Tax", account_head="Tax - TC", tax_amount_after_discount_amount=17.36)
		],
	)
	si.update(overrides)
	return si


class QBOPushCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.flags.in_qbo_inbound_sync = False
		self.qbo = FakeQBO()
		self.qbo._add("Item", {"Name": "ERPNext Sales"})
		self.qbo._add("Item", {"Name": "Sales Tax"})
		self.qbo._add("Item", {"Name": "Drivers Income"})
		self.written = {}
		self.patches = [
			patch(f"{MOD}._settings", return_value=SETTINGS),
			patch(f"{MOD}._write_back", side_effect=self._record_write_back),
			patch(f"{MOD}._qbo_address", return_value=None),
			patch.object(
				frappe, "get_cached_value", side_effect=self._cached_value_factory(frappe.get_cached_value)
			),
			patch(f"{MOD}.QBOClient", return_value=self.qbo),
		]
		for p in self.patches:
			p.start()
		frappe.cache().delete_keys("ill_qbo_ref::")

	def tearDown(self):
		for p in reversed(self.patches):
			p.stop()
		frappe.db.delete("ilL-QBO-Push-Log", {"reference_name": ["like", f"{TEST_PREFIX}%"]})

	def _record_write_back(self, doctype, name, qbo_id, synced_from):
		self.written[(doctype, name)] = (str(qbo_id), synced_from)

	@staticmethod
	def _cached_value_factory(original):
		def cached_value(doctype, name, *args, **kwargs):
			if doctype == "Company":
				return "USD"
			if doctype == "Item Group":
				return {"Fixtures": "All Item Groups", "Drivers": "All Item Groups"}.get(name)
			return original(doctype, name, *args, **kwargs)

		return cached_value

	def _customer(self, qbo_id=None):
		return frappe._dict(
			name="CUST-1",
			customer_name="Acme: Lighting",
			customer_type="Company",
			email_id="ap@acme.test",
			mobile_no="555-0100",
			customer_primary_address=None,
			custom_qbo_id=qbo_id,
		)


class TestBuilders(QBOPushCase):
	def test_lines_sum_to_rounded_total_with_tax_and_rounding(self):
		si = _invoice()
		body = qbo_push.build_sales_body(si, self.qbo, SETTINGS, "7", qbo_push.document_total(si))
		self.assertAlmostEqual(
			sum(
				line["Amount"] if line["DetailType"] != "DiscountLineDetail" else -line["Amount"]
				for line in body["Line"]
			),
			118.0,
			places=2,
		)
		discount = [line for line in body["Line"] if line["DetailType"] == "DiscountLineDetail"]
		self.assertEqual(discount[0]["Amount"], 0.36)
		self.assertEqual(body["DocNumber"], "ACC-SINV-2026-00042")
		self.assertIn("ERPNext Sales Invoice ACC-SINV-2026-00042", body["PrivateNote"])
		self.assertEqual(body["CustomerMemo"]["value"], "PO PO-77")

	def test_qty_rate_mismatch_falls_back_to_qty_one(self):
		si = _invoice()
		body = qbo_push.build_sales_body(si, self.qbo, SETTINGS, "7", qbo_push.document_total(si))
		exact, rounded = body["Line"][0], body["Line"][1]
		self.assertEqual(
			(exact["SalesItemLineDetail"]["Qty"], exact["SalesItemLineDetail"]["UnitPrice"]), (2, 50)
		)
		self.assertEqual(rounded["SalesItemLineDetail"]["Qty"], 1)
		self.assertEqual(rounded["SalesItemLineDetail"]["UnitPrice"], 1)
		self.assertTrue(rounded["Description"].startswith("3 x DRV-1"))
		for line in body["Line"]:
			if line["DetailType"] == "SalesItemLineDetail":
				self.assertEqual(line["SalesItemLineDetail"]["TaxCodeRef"], {"value": "NON"})

	def test_item_group_mapping_and_tax_item(self):
		si = _invoice()
		body = qbo_push.build_sales_body(si, self.qbo, SETTINGS, "7", qbo_push.document_total(si))
		ids = {name: rec["Id"] for rec in self.qbo.store["Item"].values() for name in [rec["Name"]]}
		self.assertEqual(body["Line"][0]["SalesItemLineDetail"]["ItemRef"]["value"], ids["ERPNext Sales"])
		self.assertEqual(body["Line"][1]["SalesItemLineDetail"]["ItemRef"]["value"], ids["Drivers Income"])
		self.assertEqual(body["Line"][2]["SalesItemLineDetail"]["ItemRef"]["value"], ids["Sales Tax"])
		self.assertEqual(body["Line"][2]["Description"], "WA Sales Tax")

	def test_credit_note_amounts_are_positive(self):
		si = _invoice(
			is_return=1,
			grand_total=-50,
			rounded_total=-50,
			items=[_row(item_code="LF-1", item_name="Linear 1", qty=-1, net_rate=50, net_amount=-50)],
			taxes=[],
		)
		body = qbo_push.build_sales_body(si, self.qbo, SETTINGS, "7", qbo_push.document_total(si))
		self.assertEqual(body["Line"][0]["Amount"], 50)
		self.assertEqual(body["Line"][0]["SalesItemLineDetail"]["Qty"], 1)
		self.assertNotIn("DueDate", body)

	def test_missing_qbo_item_is_a_permanent_error(self):
		with self.assertRaises(qbo_push.PushError):
			qbo_push.qbo_ref_id(self.qbo, "Item", "Nope")

	def test_doc_number_keeps_the_sequence_end(self):
		self.assertEqual(qbo_push.doc_number("ILL-SINV-LONGPREFIX-2026-00042"), "LONGPREFIX-2026-00042")


class TestCustomer(QBOPushCase):
	def test_creates_customer_with_sanitized_display_name(self):
		with patch(f"{MOD}._customer_row", return_value=self._customer()):
			qbo_id = qbo_push.ensure_customer(self.qbo, "CUST-1")
		created = self.qbo.created("Customer")[0][3]
		self.assertEqual(created["DisplayName"], "Acme- Lighting")
		self.assertEqual(created["PrimaryEmailAddr"], {"Address": "ap@acme.test"})
		self.assertEqual(self.written[("Customer", "CUST-1")], (qbo_id, qbo_push.SYNCED_FROM_ERPNEXT))

	def test_links_existing_customer_by_display_name(self):
		existing = self.qbo._add("Customer", {"DisplayName": "Acme- Lighting"})
		with patch(f"{MOD}._customer_row", return_value=self._customer()):
			qbo_id = qbo_push.ensure_customer(self.qbo, "CUST-1")
		self.assertEqual(qbo_id, existing["Id"])
		self.assertEqual(self.qbo.created("Customer"), [])
		self.assertEqual(self.written[("Customer", "CUST-1")][1], qbo_push.LINKED)

	def test_duplicate_name_falls_back_to_suffixed_name(self):
		self.qbo.fail_next = QBOError("Duplicate Name Exists Error", status=400, code="6240")
		with patch(f"{MOD}._customer_row", return_value=self._customer()):
			qbo_push.ensure_customer(self.qbo, "CUST-1")
		names = [c[3]["DisplayName"] for c in self.qbo.created("Customer")]
		self.assertEqual(names, ["Acme- Lighting", "Acme- Lighting (CUST-1)"])

	def test_linked_customer_is_not_looked_up(self):
		with patch(f"{MOD}._customer_row", return_value=self._customer(qbo_id="55")):
			self.assertEqual(qbo_push.ensure_customer(self.qbo, "CUST-1"), "55")
		self.assertEqual(self.qbo.calls, [])


class TestSalesInvoicePush(QBOPushCase):
	def _push(self, si, customer_qbo_id="7"):
		log = frappe._dict(name="LOG-1", reference_name=si.name)
		with (
			patch.object(frappe, "get_doc", return_value=si),
			patch(f"{MOD}.ensure_customer", return_value=customer_qbo_id),
			patch(f"{MOD}.enqueue_push") as enqueue,
		):
			result = qbo_push._push_sales_invoice(log, self.qbo)
		return result, enqueue

	def test_creates_invoice_and_writes_back(self):
		result, _ = self._push(_invoice())
		self.assertEqual(result["qbo_entity"], "Invoice")
		create = self.qbo.created("Invoice")[0]
		self.assertEqual(create[2], qbo_push._requestid("Sales Invoice", "ACC-SINV-2026-00042", "create"))
		self.assertEqual(self.written[("Sales Invoice", "ACC-SINV-2026-00042")][0], result["qbo_id"])
		self.assertEqual(result["warnings"], [])

	def test_retry_links_invoice_created_by_an_earlier_attempt(self):
		self.qbo._add(
			"Invoice",
			{
				"DocNumber": "ACC-SINV-2026-00042",
				"PrivateNote": "ERPNext Sales Invoice ACC-SINV-2026-00042",
				"CustomerRef": {"value": "7"},
				"TotalAmt": 118,
			},
		)
		result, _ = self._push(_invoice())
		self.assertIn("Linked to existing", result["message"])
		self.assertEqual(self.qbo.created("Invoice"), [])

	def test_doc_number_clash_with_other_invoice_needs_a_person(self):
		self.qbo._add(
			"Invoice",
			{
				"DocNumber": "ACC-SINV-2026-00042",
				"PrivateNote": "",
				"CustomerRef": {"value": "99"},
				"TotalAmt": 5,
			},
		)
		with self.assertRaises(qbo_push.PushError):
			self._push(_invoice())

	def test_already_linked_is_skipped(self):
		with self.assertRaises(qbo_push.PushSkip):
			self._push(_invoice(custom_qbo_id="145"))

	def test_multicurrency_is_rejected(self):
		with self.assertRaises(qbo_push.PushError):
			self._push(_invoice(currency="CAD"))

	def test_qbo_total_mismatch_is_flagged(self):
		original = self.qbo.create

		def taxed_create(entity, body, requestid):
			record = original(entity, body, requestid)
			record["TotalAmt"] = 130.0
			return record

		self.qbo.create = taxed_create
		result, _ = self._push(_invoice())
		self.assertIn("differs from ERPNext", result["warnings"][0])

	def test_credit_note_queues_application(self):
		si = _invoice(
			is_return=1,
			return_against="ACC-SINV-2026-00001",
			update_outstanding_for_self=0,
			grand_total=-50,
			rounded_total=-50,
			items=[_row(item_code="LF-1", item_name="Linear 1", qty=-1, net_rate=50, net_amount=-50)],
			taxes=[],
		)
		result, enqueue = self._push(si)
		self.assertEqual(result["qbo_entity"], "CreditMemo")
		enqueue.assert_called_once_with("Sales Invoice", si.name, "Apply Credit")

	def test_credit_note_with_own_outstanding_is_not_applied(self):
		si = _invoice(
			is_return=1,
			return_against="ACC-SINV-2026-00001",
			update_outstanding_for_self=1,
			grand_total=-50,
			rounded_total=-50,
			items=[_row(item_code="LF-1", item_name="Linear 1", qty=-1, net_rate=50, net_amount=-50)],
			taxes=[],
		)
		_, enqueue = self._push(si)
		enqueue.assert_not_called()

	def test_apply_credit_creates_zero_payment_capped_at_balance(self):
		invoice = self.qbo._add("Invoice", {"TotalAmt": 100, "Balance": 30})
		si = _invoice(is_return=1, custom_qbo_id="900", return_against="ACC-SINV-2026-00001", grand_total=-50)
		with (
			patch.object(frappe, "get_doc", return_value=si),
			patch.object(frappe.db, "get_value", return_value=invoice["Id"]),
			patch(f"{MOD}.ensure_customer", return_value="7"),
		):
			result = qbo_push._apply_credit_note(frappe._dict(name="LOG-2", reference_name=si.name), self.qbo)
		body = self.qbo.created("Payment")[0][3]
		self.assertEqual(body["TotalAmt"], 0)
		self.assertEqual([line["Amount"] for line in body["Line"]], [30, 30])
		self.assertEqual(body["Line"][1]["LinkedTxn"][0], {"TxnId": "900", "TxnType": "CreditMemo"})
		self.assertEqual(result["qbo_entity"], "Payment")

	def test_void_invoice_uses_sync_token(self):
		invoice = self.qbo._add("Invoice", {"TotalAmt": 118, "Balance": 118})
		row = frappe._dict(name="SI-1", custom_qbo_id=invoice["Id"], is_return=0)
		with patch.object(frappe.db, "get_value", return_value=row):
			result = qbo_push._void_sales_invoice(frappe._dict(name="LOG-3", reference_name="SI-1"), self.qbo)
		op = next(c for c in self.qbo.calls if c[0] == "operation")
		self.assertEqual(op[2], "void")
		self.assertEqual(op[4], {"Id": invoice["Id"], "SyncToken": "0"})
		self.assertIn("Voided", result["message"])

	def test_void_already_voided_is_skipped(self):
		invoice = self.qbo._add("Invoice", {"TotalAmt": 0, "PrivateNote": "Voided"})
		row = frappe._dict(name="SI-1", custom_qbo_id=invoice["Id"], is_return=0)
		with patch.object(frappe.db, "get_value", return_value=row), self.assertRaises(qbo_push.PushSkip):
			qbo_push._void_sales_invoice(frappe._dict(name="LOG-3", reference_name="SI-1"), self.qbo)

	def test_void_never_synced_is_skipped(self):
		row = frappe._dict(name="SI-1", custom_qbo_id=None, is_return=0)
		with patch.object(frappe.db, "get_value", return_value=row), self.assertRaises(qbo_push.PushSkip):
			qbo_push._void_sales_invoice(frappe._dict(name="LOG-3", reference_name="SI-1"), self.qbo)

	def test_cancelled_credit_note_deletes_application_then_memo(self):
		memo = self.qbo._add("CreditMemo", {"TotalAmt": 50})
		application = self.qbo._add("Payment", {"TotalAmt": 0})
		row = frappe._dict(name="SI-RET", custom_qbo_id=memo["Id"], is_return=1)
		with patch.object(frappe.db, "get_value", side_effect=[row, application["Id"]]):
			qbo_push._void_sales_invoice(frappe._dict(name="LOG-4", reference_name="SI-RET"), self.qbo)
		ops = [(c[1], c[2]) for c in self.qbo.calls if c[0] == "operation"]
		self.assertEqual(ops, [("Payment", "delete"), ("CreditMemo", "delete")])


class TestPaymentPush(QBOPushCase):
	def _pe(self, **overrides):
		pe = frappe._dict(
			doctype="Payment Entry",
			name="ACC-PAY-2026-00009",
			docstatus=1,
			payment_type="Receive",
			party_type="Customer",
			party="CUST-1",
			company="Test Co",
			paid_from_account_currency="USD",
			paid_to_account_currency="USD",
			received_amount=150,
			posting_date="2026-10-06",
			reference_no="CHK 1001",
			custom_qbo_id=None,
			custom_synced_from=None,
			deductions=[],
			references=[_row(reference_doctype="Sales Invoice", reference_name="SI-1", allocated_amount=118)],
		)
		pe.update(overrides)
		return pe

	def _push(self, pe, invoice_qbo_id="145", open_log=False):
		with (
			patch.object(frappe, "get_doc", return_value=pe),
			patch.object(frappe.db, "get_value", return_value=invoice_qbo_id),
			patch(f"{MOD}._has_open_log", return_value=open_log),
			patch(f"{MOD}.ensure_customer", return_value="7"),
		):
			return qbo_push._push_payment_entry(frappe._dict(name="LOG-5", reference_name=pe.name), self.qbo)

	def test_creates_payment_linked_to_invoice(self):
		result = self._push(self._pe())
		body = self.qbo.created("Payment")[0][3]
		self.assertEqual(body["TotalAmt"], 150)
		self.assertEqual(
			body["Line"], [{"Amount": 118, "LinkedTxn": [{"TxnId": "145", "TxnType": "Invoice"}]}]
		)
		self.assertEqual(body["PrivateNote"], "ERPNext Payment Entry ACC-PAY-2026-00009")
		self.assertEqual(body["PaymentRefNum"], "CHK 1001")
		self.assertIn("customer credit", result["warnings"][0])
		self.assertEqual(
			self.written[("Payment Entry", "ACC-PAY-2026-00009")][1], qbo_push.SYNCED_FROM_ERPNEXT
		)

	def test_waits_for_invoice_still_being_pushed(self):
		with self.assertRaises(qbo_push.PushWait):
			self._push(self._pe(), invoice_qbo_id=None, open_log=True)

	def test_invoice_not_in_qbo_needs_a_person(self):
		with self.assertRaises(qbo_push.PushError):
			self._push(self._pe(), invoice_qbo_id=None, open_log=False)

	def test_payment_from_qbo_is_never_pushed_back(self):
		with self.assertRaises(qbo_push.PushSkip):
			self._push(self._pe(custom_synced_from="QuickBooks Online", custom_qbo_id="300"))

	def test_deductions_are_rejected(self):
		with self.assertRaises(qbo_push.PushError):
			self._push(self._pe(deductions=[_row(amount=5)]))

	def test_retry_links_payment_from_earlier_attempt(self):
		existing = self.qbo._add(
			"Payment",
			{
				"CustomerRef": {"value": "7"},
				"TxnDate": "2026-10-06",
				"PrivateNote": "ERPNext Payment Entry ACC-PAY-2026-00009",
			},
		)
		result = self._push(self._pe())
		self.assertEqual(result["qbo_id"], existing["Id"])
		self.assertEqual(self.qbo.created("Payment"), [])

	def test_void_payment_uses_update_include_void(self):
		payment = self.qbo._add("Payment", {"TotalAmt": 150})
		row = frappe._dict(name="PE-1", custom_qbo_id=payment["Id"], custom_synced_from="ERPNext")
		with patch.object(frappe.db, "get_value", return_value=row):
			qbo_push._void_payment_entry(frappe._dict(name="LOG-6", reference_name="PE-1"), self.qbo)
		op = next(c for c in self.qbo.calls if c[0] == "operation")
		self.assertEqual((op[2], op[3]), ("update", "void"))
		self.assertTrue(op[4]["sparse"])


class TestOutbox(QBOPushCase):
	def _log(self, suffix="A", action="Create", doctype="Sales Invoice", **values):
		fields = {
			"doctype": "ilL-QBO-Push-Log",
			"reference_doctype": doctype,
			"reference_name": f"{TEST_PREFIX}{suffix}",
			"action": action,
			"status": "Queued",
			"attempts": 0,
			"next_attempt_at": now_datetime(),
		}
		fields.update(values)
		log = frappe.get_doc(fields)
		log.insert(ignore_permissions=True)
		return log.name

	def _status(self, name):
		return frappe.db.get_value(
			"ilL-QBO-Push-Log",
			name,
			["status", "attempts", "next_attempt_at", "last_error", "qbo_id"],
			as_dict=True,
		)

	def _run(self, name, handler):
		with patch.dict(qbo_push.HANDLERS, {("Sales Invoice", "Create"): handler}):
			return qbo_push.process_log(name)

	def test_success_marks_synced(self):
		name = self._log()
		self.assertEqual(self._run(name, lambda log, client: {"qbo_id": "145", "message": "ok"}), "Synced")
		row = self._status(name)
		self.assertEqual((row.status, row.qbo_id, row.attempts), ("Synced", "145", 1))
		self.assertIsNone(row.next_attempt_at)

	def test_transient_error_schedules_retry(self):
		name = self._log()

		def boom(log, client):
			raise QBOError("throttled", status=429, transient=True)

		self._run(name, boom)
		row = self._status(name)
		self.assertEqual(row.status, "Failed")
		self.assertIsNotNone(row.next_attempt_at)
		self.assertIn("throttled", row.last_error)

	def test_permanent_error_stops_retrying(self):
		name = self._log()

		def bad(log, client):
			raise qbo_push.PushError("fix the data")

		with patch.object(frappe, "log_error"):
			self._run(name, bad)
		row = self._status(name)
		self.assertEqual(row.status, "Failed")
		self.assertIsNone(row.next_attempt_at)

	def test_wait_keeps_log_queued(self):
		name = self._log()

		def wait(log, client):
			raise qbo_push.PushWait("invoice first")

		self._run(name, wait)
		self.assertEqual(self._status(name).status, "Queued")

	def test_retries_stop_after_max_attempts(self):
		name = self._log(attempts=qbo_push.MAX_ATTEMPTS - 1)

		def boom(log, client):
			raise QBOError("down", status=503, transient=True)

		with patch.object(frappe, "log_error") as log_error:
			self._run(name, boom)
		row = self._status(name)
		self.assertIsNone(row.next_attempt_at)
		log_error.assert_called_once()

	def test_later_log_waits_for_earlier_one_on_same_document(self):
		first = self._log(suffix="ORDER", action="Create", status="Failed")
		second = self._log(suffix="ORDER", action="Void")
		frappe.db.set_value(
			"ilL-QBO-Push-Log",
			second,
			"creation",
			add_to_date(frappe.db.get_value("ilL-QBO-Push-Log", first, "creation"), seconds=1),
		)
		handler = MagicMock()
		with patch.dict(qbo_push.HANDLERS, {("Sales Invoice", "Void"): handler}):
			self.assertEqual(qbo_push.process_log(second), "Queued")
		handler.assert_not_called()
		self.assertIn(first, self._status(second).last_error)

	def test_done_log_is_not_run_again(self):
		name = self._log(status="Synced")
		handler = MagicMock()
		self._run(name, handler)
		handler.assert_not_called()

	def test_enqueue_reuses_open_log(self):
		with patch.object(frappe, "enqueue"):
			first = qbo_push.enqueue_push("Sales Invoice", f"{TEST_PREFIX}DUP", "Create")
			second = qbo_push.enqueue_push("Sales Invoice", f"{TEST_PREFIX}DUP", "Create")
		self.assertEqual(first, second)


class TestDocEvents(QBOPushCase):
	def _si(self, **kw):
		doc = _invoice(name=f"{TEST_PREFIX}EV", **kw)
		doc.doctype = "Sales Invoice"
		return doc

	def test_submit_queues_when_enabled(self):
		with patch(f"{MOD}.enqueue_push") as enqueue:
			qbo_push.on_sales_invoice_submit(self._si())
		enqueue.assert_called_once_with("Sales Invoice", f"{TEST_PREFIX}EV", "Create")

	def test_disabled_push_queues_nothing(self):
		with (
			patch(f"{MOD}._settings", return_value=frappe._dict(SETTINGS, push_enabled=0)),
			patch(f"{MOD}.enqueue_push") as enqueue,
		):
			qbo_push.on_sales_invoice_submit(self._si())
		enqueue.assert_not_called()

	def test_documents_before_start_date_are_ignored(self):
		with (
			patch(f"{MOD}._settings", return_value=frappe._dict(SETTINGS, push_start_date="2026-10-07")),
			patch(f"{MOD}.enqueue_push") as enqueue,
		):
			qbo_push.on_sales_invoice_submit(self._si())
		enqueue.assert_not_called()

	def test_queue_failure_never_blocks_submit(self):
		with (
			patch(f"{MOD}.enqueue_push", side_effect=RuntimeError("redis down")),
			patch.object(frappe, "log_error"),
		):
			qbo_push.on_sales_invoice_submit(self._si())

	def test_payment_from_inbound_sync_is_not_pushed(self):
		pe = frappe._dict(doctype="Payment Entry", name="PE-1", payment_type="Receive", party_type="Customer")
		frappe.flags.in_qbo_inbound_sync = True
		try:
			with patch(f"{MOD}.enqueue_push") as enqueue:
				qbo_push.on_payment_entry_submit(pe)
				qbo_push.on_payment_entry_cancel(pe)
		finally:
			frappe.flags.in_qbo_inbound_sync = False
		enqueue.assert_not_called()

	def test_payment_from_qbo_is_not_pushed(self):
		pe = frappe._dict(
			doctype="Payment Entry",
			name="PE-1",
			payment_type="Receive",
			party_type="Customer",
			custom_synced_from="QuickBooks Online",
			posting_date="2026-10-06",
		)
		with patch(f"{MOD}.enqueue_push") as enqueue:
			qbo_push.on_payment_entry_submit(pe)
		enqueue.assert_not_called()

	def test_cancel_of_never_synced_invoice_queues_nothing(self):
		with patch(f"{MOD}.enqueue_push") as enqueue, patch(f"{MOD}._has_log", return_value=False):
			qbo_push.on_sales_invoice_cancel(self._si())
		enqueue.assert_not_called()

	def test_cancel_of_synced_invoice_queues_void(self):
		with patch(f"{MOD}.enqueue_push") as enqueue:
			qbo_push.on_sales_invoice_cancel(self._si(custom_qbo_id="145"))
		enqueue.assert_called_once_with("Sales Invoice", f"{TEST_PREFIX}EV", "Void")


class TestClient(FrappeTestCase):
	def _client(self):
		return qbo_client.QBOClient(proxy_url="https://n8n.example/webhook/x", secret="s3cret")

	def test_request_is_signed_and_unwrapped(self):
		response = MagicMock(status_code=200, text="")
		response.json.return_value = {"ok": True, "status": 200, "body": {"Invoice": {"Id": "5"}}}
		with patch("requests.post", return_value=response) as post:
			result = self._client().create("Invoice", {"Line": []}, "rid-1")
		self.assertEqual(result, {"Id": "5"})
		raw = post.call_args.kwargs["data"]
		expected = hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
		self.assertEqual(post.call_args.kwargs["headers"]["X-QBO-Signature"], expected)
		sent = json.loads(raw)
		self.assertEqual(
			(sent["method"], sent["path"], sent["params"]), ("POST", "/invoice", {"requestid": "rid-1"})
		)

	def test_fault_is_parsed(self):
		response = MagicMock(status_code=200, text="")
		response.json.return_value = {
			"ok": False,
			"status": 400,
			"body": {
				"Fault": {
					"Error": [{"Message": "Duplicate Name Exists Error", "Detail": "x", "code": "6240"}]
				}
			},
		}
		with patch("requests.post", return_value=response), self.assertRaises(QBOError) as ctx:
			self._client().query("select * from Customer")
		self.assertEqual(ctx.exception.code, "6240")
		self.assertFalse(ctx.exception.transient)

	def test_auth_failure_is_retryable_with_clear_message(self):
		response = MagicMock(status_code=200, text="")
		response.json.return_value = {"ok": False, "status": 401, "body": {}}
		with patch("requests.post", return_value=response), self.assertRaises(QBOError) as ctx:
			self._client().query("select * from CompanyInfo")
		self.assertTrue(ctx.exception.transient)
		self.assertIn("reconnect", ctx.exception.message)

	def test_bad_proxy_signature_is_not_retried(self):
		response = MagicMock(status_code=200, text="")
		response.json.return_value = {"ok": False, "status": 401, "error": "bad signature"}
		with patch("requests.post", return_value=response), self.assertRaises(QBOError) as ctx:
			self._client().query("select * from CompanyInfo")
		self.assertFalse(ctx.exception.transient)

	def test_n8n_down_is_retryable(self):
		response = MagicMock(status_code=502, text="Bad Gateway")
		response.json.side_effect = ValueError
		with patch("requests.post", return_value=response), self.assertRaises(QBOError) as ctx:
			self._client().query("select * from CompanyInfo")
		self.assertTrue(ctx.exception.transient)

	def test_query_values_are_escaped(self):
		self.assertEqual(qbo_client.escape_query_value("O'Brien \\ Co"), "O\\'Brien \\\\ Co")
