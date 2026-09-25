"""Commercial retries, ownership and immutable evidence at explicit Frappe boundaries."""

import hashlib
import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint


class Doc(Record):
	__setattr__ = dict.__setitem__


def dependencies():
	return {
		ROOT + ".portal.access": types.SimpleNamespace(
			get_actor=MagicMock(return_value=Record(is_company_dealer_for=lambda customer: customer == "A"))
		),
		ROOT + ".portal.accounts": types.SimpleNamespace(require_owned=MagicMock(), selections=MagicMock()),
	}


class OrderIntake(unittest.TestCase):
	def body(self):
		return {
			"acknowledge_scope": True,
			"customer_address": "BILL",
			"shipping_address_name": "SHIP",
			"contact_person": "BUYER",
			"requested_date": "2026-10-25",
			"expected_modified": "rev1",
			"file_ids": ["FILE1"],
			"scope_hash": "scope",
		}

	def test_foreign_buyer_and_foreign_contact_are_rejected(self):
		deps = dependencies()
		with load_service(ROOT + ".portal.order_intake", deps) as (service, _frappe):
			with self.assertRaises(PermissionError):
				service._buyer("B")
			deps[ROOT + ".portal.accounts"].require_owned.side_effect = PermissionError("foreign contact")
			with self.assertRaisesRegex(PermissionError, "foreign contact"):
				service.validate_context("A", service.normalize(self.body()))

	def test_unknown_fields_and_missing_scope_ack_are_rejected(self):
		with load_service(ROOT + ".portal.order_intake", dependencies()) as (service, _frappe):
			for body in ({**self.body(), "rate": 0}, {**self.body(), "acknowledge_scope": "false"}):
				with self.assertRaises(ValueError):
					service.normalize(body)

	def test_retry_returns_existing_order_before_stale_revision_check(self):
		with load_service(ROOT + ".portal.order_intake", dependencies()) as (service, frappe):
			body = self.body()
			frappe.db.get_value.return_value = Record(
				name="OI1", sales_order="SO1", intake_hash=fingerprint(service.normalize(body))
			)
			with patch.object(service, "_schedule", return_value=(Doc(modified="new"), "A")):
				self.assertTrue(service.submit("S1", body, "retry-key")["already_existed"])
				with self.assertRaisesRegex(ValueError, "different intake"):
					service.submit("S1", {**body, "po_no": "changed"}, "retry-key")

	def test_file_failure_rolls_back_order_creation_and_restores_context(self):
		with load_service(ROOT + ".portal.order_intake", dependencies()) as (service, frappe):
			with load_service(ROOT + ".api.build_artifacts") as (atomic, atomic_frappe):
				frappe.flags = Doc(ill_order_intake_context={"prior": True})
				schedule = Doc(
					name="S1",
					modified="rev1",
					lines=[],
					get_linked_sales_order=lambda: None,
					create_sales_order_result=MagicMock(return_value={"sales_order": "SO1"}),
				)
				body = {**self.body(), "scope_hash": fingerprint(service.scope(schedule))}
				frappe.db.get_value.return_value = None
				with (
					patch.object(service, "_schedule", return_value=(schedule, "A")),
					patch.object(service, "validate_context"),
					patch.object(service, "_files", side_effect=ValueError("upload failed")),
				):
					with self.assertRaisesRegex(ValueError, "upload failed"):
						atomic.atomic_build(service.submit.__wrapped__)("S1", body, "retry-key")
					atomic_frappe.db.rollback.assert_called_once_with(save_point="build_submit")
					self.assertEqual(frappe.flags.ill_order_intake_context, {"prior": True})
					schedule.create_sales_order_result.assert_called_once_with(include_other=False)


class ChangeRequests(unittest.TestCase):
	def deps(self):
		return {
			ROOT + ".portal.order_intake": types.SimpleNamespace(_buyer=MagicMock()),
			ROOT + ".portal.order_review": types.SimpleNamespace(
				_staff=MagicMock(), snapshot=lambda order: order.get("snapshot"), lock_orders=MagicMock()
			),
			ROOT + ".portal.orders": types.SimpleNamespace(load_accessible_sales_order=MagicMock()),
			ROOT + ".portal.files": types.SimpleNamespace(finalize_files=MagicMock()),
		}

	def test_stale_change_never_creates_a_request_or_attaches_files(self):
		deps = self.deps()
		with load_service(ROOT + ".portal.order_changes", deps) as (service, frappe):
			frappe.db.get_value.return_value = None
			with patch.object(service, "_order", return_value=Doc(customer="A", snapshot={"qty": 2})):
				with self.assertRaisesRegex(ValueError, "order changed"):
					service.submit("SO1", "Change", "Increase quantity", fingerprint({"qty": 1}), "retry-key")
			deps[ROOT + ".portal.files"].finalize_files.assert_not_called()
			frappe.get_doc.assert_not_called()

	def test_cancellation_completion_requires_actual_erp_cancellation(self):
		with load_service(ROOT + ".portal.order_changes", self.deps()) as (service, frappe):
			request = Doc(
				sales_order="SO1",
				state="UNDER_REVIEW",
				modified="r1",
				request_type="Cancellation",
				reload=MagicMock(),
			)
			frappe.get_doc.return_value = request
			with patch.object(service, "_order", return_value=Doc(docstatus=1, snapshot={"qty": 1})):
				with self.assertRaisesRegex(ValueError, "native ERP workflow"):
					service.decide("OC1", "COMPLETE", "Cancelled", "r1", fingerprint({"qty": 1}))
			self.assertEqual(request.state, "UNDER_REVIEW")

	def test_completed_change_requires_approved_amendment(self):
		deps = self.deps()
		deps[ROOT + ".portal.orders"].load_accessible_sales_order.return_value = Doc(
			customer="B", docstatus=1, amended_from="SO1"
		)
		with load_service(ROOT + ".portal.order_changes", deps) as (service, frappe):
			frappe.get_doc.return_value = Doc(
				sales_order="SO1",
				state="UNDER_REVIEW",
				modified="r1",
				request_type="Change",
				reload=MagicMock(),
			)
			with patch.object(
				service,
				"_order",
				return_value=Doc(name="SO1", customer="A", docstatus=2, snapshot={"qty": 1}),
			):
				with self.assertRaisesRegex(ValueError, "approved amendment"):
					service.decide("OC1", "COMPLETE", "Amended", "r1", fingerprint({"qty": 1}), "FOREIGN")


class AcknowledgmentEvidence(unittest.TestCase):
	def test_download_rejects_replaced_bytes_even_on_owned_file(self):
		deps = {ROOT + ".portal.order_intake": types.SimpleNamespace(can_access=lambda doc: True)}
		with load_service(ROOT + ".portal.order_acknowledgment", deps) as (service, frappe):
			intake = Doc(
				doctype="ilL-Order-Intake",
				name="OI1",
				state="APPROVED",
				acknowledgment_file="F1",
				acknowledgment_sha256=hashlib.sha256(b"approved").hexdigest(),
			)
			file = Doc(
				is_private=1,
				attached_to_doctype=intake.doctype,
				attached_to_name=intake.name,
				get_content=lambda: b"changed",
			)
			frappe.get_doc.side_effect = [intake, file]
			with self.assertRaisesRegex(ValueError, "checksum"):
				service.download("SO1")

	def test_create_uses_frozen_snapshot_and_does_not_regenerate(self):
		pdf = types.SimpleNamespace(get_pdf=MagicMock(return_value=b"pdf"))
		exports = types.SimpleNamespace(_save_file_ignore_permissions=MagicMock(return_value=Doc(name="F1")))
		with load_service(
			ROOT + ".portal.order_acknowledgment", {"frappe.utils.pdf": pdf, ROOT + ".api.exports": exports}
		) as (service, frappe):
			frappe.utils.sanitize_html = lambda value: value
			intake = Doc(
				name="OI1",
				sales_order="SO1",
				approved_on="2026-09-25",
				approved_by="staff",
				approved_snapshot=json.dumps(
					{"customer": "Old customer", "items": [], "grand_total": 90, "currency": "USD"}
				),
			)
			service.create(intake)
			self.assertIn("Old customer", pdf.get_pdf.call_args.args[0])
			service.create(intake)
			pdf.get_pdf.assert_called_once()
			frappe.get_doc.assert_not_called()
