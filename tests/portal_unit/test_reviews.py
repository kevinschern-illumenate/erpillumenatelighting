import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint


class OrderApproval(unittest.TestCase):
	def dependencies(self):
		access = types.ModuleType(ROOT + ".portal.access")
		access.get_actor = MagicMock(
			return_value=Record(
				user="buyer@example.com",
				is_dealer=True,
				is_company_dealer_for=lambda customer: customer == "A",
			)
		)
		orders = types.ModuleType(ROOT + ".portal.orders")
		orders.load_accessible_sales_order = MagicMock(return_value=True)
		accounts = types.ModuleType(ROOT + ".portal.accounts")
		accounts.require_owned = MagicMock()
		return {access.__name__: access, orders.__name__: orders, accounts.__name__: accounts}

	def order(self):
		return Record(
			name="SO1",
			ill_fixture_schedule="S1",
			customer="A",
			company="MFG",
			items=[],
			customer_address="BILL",
			shipping_address_name="SHIP",
			contact_person="CONTACT",
			ill_confirmed_delivery_date="2026-10-25",
			ill_delivery_confirmed_by="sales@example.com",
		)

	def test_native_submit_checks_acknowledgment_without_drawing_gate(self):
		with load_service(ROOT + ".portal.order_review", self.dependencies()) as (module, _frappe):
			order = self.order()
			# dict.items shadows Frappe's child-table attribute in this boundary double.
			order = types.SimpleNamespace(**order)
			order.get = lambda field: getattr(order, field, None)
			request = Record(
				state="UNDER_REVIEW",
				acknowledged_by="buyer@example.com",
				intake_json="{}",
				acknowledged_hash=fingerprint(module.snapshot(order)),
				request_snapshot=json.dumps(module.snapshot(order)),
			)
			with patch.object(module, "_staff"), patch.object(module, "_load", return_value=(order, request)):
				module.before_submit(order)
				order.customer = "Changed customer"
				with self.assertRaisesRegex(ValueError, "acknowledge"):
					module.before_submit(order)

	def test_role_without_erp_submit_permission_cannot_approve(self):
		with load_service(ROOT + ".portal.order_review", self.dependencies()) as (module, frappe):
			frappe.get_roles.return_value = [module.APPROVER_ROLE]
			frappe.db.get_value.return_value = "System User"
			frappe.has_permission.return_value = False
			with self.assertRaisesRegex(PermissionError, "ERP Sales Order"):
				module._staff(self.order(), approve=True)

	def test_native_guard_requires_intake_confirmed_date_and_current_company_records(self):
		deps = self.dependencies()
		with load_service(ROOT + ".portal.order_review", deps) as (module, _frappe):
			order = types.SimpleNamespace(**self.order())
			order.get = lambda key: getattr(order, key, None)
			request = Record(state="UNDER_REVIEW", intake_json=None)
			with patch.object(module, "_staff"), patch.object(module, "_load", return_value=(order, request)):
				with self.assertRaisesRegex(ValueError, "intake"):
					module.before_submit(order)
				request["intake_json"] = "{}"
				order.ill_delivery_confirmed_by = None
				with self.assertRaisesRegex(ValueError, "confirm"):
					module.before_submit(order)
				order.ill_delivery_confirmed_by = "staff"
				deps[ROOT + ".portal.accounts"].require_owned.side_effect = PermissionError(
					"Archived address"
				)
				with self.assertRaisesRegex(PermissionError, "Archived"):
					module.before_submit(order)

	def test_dealer_cannot_approve_with_erp_permission_alone(self):
		with load_service(ROOT + ".portal.order_review", self.dependencies()) as (module, _frappe):
			with self.assertRaises(PermissionError):
				module._staff(self.order(), approve=True)

	def test_incomplete_bom_cannot_pass_native_guard(self):
		with load_service(ROOT + ".portal.order_review", self.dependencies()) as (module, frappe):
			order = types.SimpleNamespace(**self.order())
			order.get = lambda field: getattr(order, field, None)
			order.items = [Record(idx=1, ill_configured_tape_neon="BUILD", item_code="ITEM", ill_bom="BOM")]
			request = Record(
				state="SUBMITTED",
				acknowledged_by="buyer@example.com",
				intake_json="{}",
				acknowledged_hash=fingerprint(module.snapshot(order)),
				request_snapshot=json.dumps(module.snapshot(order)),
			)
			frappe.db.exists.return_value = False
			with patch.object(module, "_staff"), patch.object(module, "_load", return_value=(order, request)):
				with self.assertRaisesRegex(ValueError, "BOM"):
					module.before_submit(order)

	def test_cancelled_accepted_quotation_blocks_order_approval(self):
		with load_service(ROOT + ".portal.order_review", self.dependencies()) as (module, frappe):
			order = types.SimpleNamespace(**self.order(), ill_quote_offer="OFFER1")
			order.get = lambda field: getattr(order, field, None)
			request = Record(
				state="SUBMITTED",
				acknowledged_by="buyer@example.com",
				intake_json="{}",
				acknowledged_hash=fingerprint(module.snapshot(order)),
				request_snapshot=json.dumps(module.snapshot(order)),
			)
			frappe.get_doc.return_value = Record(
				state="ACCEPTED", sales_order="SO1", customer="A", quotation="Q1"
			)
			frappe.db.get_value.return_value = 2
			with (
				patch.object(module, "_staff"),
				patch.object(module, "_load", return_value=(order, request)),
				self.assertRaisesRegex(ValueError, "cancelled"),
			):
				module.before_submit(order)


class DrawingRelease(unittest.TestCase):
	def dependencies(self):
		requests = types.ModuleType(ROOT + ".doctype.ill_document_request.ill_document_request")
		requests.has_permission = MagicMock(return_value=True)
		return {requests.__name__: requests}

	def test_only_named_reviewer_can_decide(self):
		with load_service(ROOT + ".portal.drawing_review", self.dependencies()) as (module, frappe):
			frappe.get_doc.return_value = Record(technical_reviewer="someone-else@example.com")
			with self.assertRaises(PermissionError):
				module.decide("REQ", "token", "APPROVED")
			frappe.db.sql.assert_not_called()

	def test_published_drawing_cannot_be_approved_for_a_later_build(self):
		import hashlib

		deps = self.dependencies()
		impact = types.SimpleNamespace(request_build_hash=MagicMock(return_value="current"))
		deps[ROOT + ".portal.drawing_impact"] = impact
		with load_service(ROOT + ".portal.drawing_review", deps) as (module, frappe):
			revision = Record(
				name="REV1",
				file="/private/files/a.pdf",
				is_published_to_portal=1,
				published_on="2026-09-25",
				idx=1,
				published_build_hash="old",
				published_file_sha256=hashlib.sha256(b"drawing").hexdigest(),
			)
			request = Record(doctype="ilL-Document-Request", name="REQ", deliverables=[revision])
			frappe.get_doc.return_value = Record(
				attached_to_doctype=request.doctype,
				attached_to_name=request.name,
				get_content=lambda: b"drawing",
			)
			with self.assertRaisesRegex(ValueError, "predates"):
				module._current(request)
			revision["published_build_hash"] = "current"
			self.assertEqual(module._current(request)[2], "current")
			revision["published_file_sha256"] = "changed"
			with self.assertRaisesRegex(ValueError, "bytes changed"):
				module._current(request)

	def test_changed_build_invalidates_production_release(self):
		with load_service(ROOT + ".portal.drawing_review", self.dependencies()) as (module, frappe):
			frappe.get_all.return_value = ["REQ"]
			frappe.get_doc.return_value = Record(technical_reviewer="reviewer@example.com")
			old_token = fingerprint(
				{"request": "REQ", "revision": "REV1", "file": "checksum", "build": "original"}
			)
			frappe.db.exists.side_effect = lambda _doctype, filters: filters["revision_token"] == old_token
			with patch.object(module, "_current", return_value=(Record(name="REV1"), "checksum", "changed")):
				with self.assertRaisesRegex(ValueError, "on hold"):
					module.before_work_order_submit(Record(sales_order="SO1"))
			with patch.object(module, "_current", return_value=(Record(name="REV1"), "checksum", "original")):
				module.before_work_order_submit(Record(sales_order="SO1"))


class SellingPrices(unittest.TestCase):
	def test_length_is_converted_once_to_stock_units(self):
		with load_service(ROOT + ".api.tape_neon_pricing") as (module, frappe):
			frappe.db.get_value.return_value = "Foot"
			self.assertEqual(module.stock_quantity("WIRE", 24), 2)
			frappe.get_all.return_value = [Record(price_list_rate=3, uom="Foot")]
			self.assertEqual(module.selling_amount("WIRE", 2), 6)

	def test_missing_price_is_not_free_but_explicit_zero_is_valid(self):
		with load_service(ROOT + ".api.tape_neon_pricing") as (module, frappe):
			frappe.db.get_value.return_value = "Nos"
			frappe.get_all.return_value = []
			with self.assertRaisesRegex(ValueError, "selling price|Selling price"):
				module.selling_amount("DRIVER", 1)
			frappe.get_all.return_value = [Record(price_list_rate=0, uom="Nos")]
			self.assertEqual(module.selling_amount("DRIVER", 2), 0)

	def test_expired_or_wrong_uom_price_is_rejected(self):
		with load_service(ROOT + ".api.tape_neon_pricing") as (module, frappe):
			frappe.db.get_value.return_value = "Foot"
			for row in (
				Record(price_list_rate=3, uom="Inch"),
				Record(price_list_rate=3, valid_upto="2026-09-24"),
			):
				frappe.get_all.return_value = [row]
				with self.assertRaises(ValueError):
					module.selling_amount("WIRE", 1)
