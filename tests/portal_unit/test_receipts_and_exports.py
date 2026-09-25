import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint


class QuoteReceipts(unittest.TestCase):
	def dependencies(self):
		access = types.ModuleType(ROOT + ".portal.access")
		access.can_edit_schedule = MagicMock(return_value=True)
		access.can_read_schedule = MagicMock(return_value=True)
		documents = types.ModuleType(ROOT + ".portal.line_documents")
		documents.active = MagicMock(return_value=[])
		return {access.__name__: access, documents.__name__: documents}

	def test_retry_returns_receipt_without_quoted_transition(self):
		with load_service(ROOT + ".portal.quotes", self.dependencies()) as (module, frappe):
			schedule = Record(
				name="S1",
				customer="A",
				ill_project="P1",
				status="READY",
				modified="new",
				lines=[Record(name="LINE1", qty=1)],
				reload=MagicMock(),
			)
			data = module._snapshot(schedule)
			data["notes"] = ""
			data.update(contact="", requested_date=None, files=[])
			frappe.get_doc.return_value = schedule
			frappe.db.get_value.return_value = Record(
				name="QR1", state="REQUESTED", request_hash=fingerprint(data)
			)
			receipt = module.request_quote("S1", idempotency_key="retry", expected_modified="old")
			self.assertEqual(receipt["request_name"], "QR1")
			self.assertEqual(schedule.status, "READY")
			self.assertTrue(receipt["already_existed"])
			frappe.db.set_value.assert_not_called()

	def test_retry_with_changed_content_conflicts(self):
		with load_service(ROOT + ".portal.quotes", self.dependencies()) as (module, frappe):
			frappe.get_doc.return_value = Record(name="S1", lines=[], reload=MagicMock())
			frappe.db.get_value.return_value = Record(name="QR1", request_hash="other")
			with self.assertRaisesRegex(ValueError, "different content"):
				module.request_quote("S1", idempotency_key="retry")


class ExportRevocation(unittest.TestCase):
	def dependencies(self, pricing=True):
		access = types.ModuleType(ROOT + ".portal.access")
		access.can_read_schedule = MagicMock(return_value=False)
		access.schedule_query_conditions = MagicMock(return_value="SCOPED_SCHEDULES")
		exports = types.ModuleType(ROOT + ".api.exports")
		exports._check_pricing_permission = MagicMock(return_value=pricing)
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		return {module.__name__: module for module in (access, exports, document)}

	def test_creator_loses_export_access_after_revocation(self):
		with load_service(ROOT + ".doctype.ill_export_job.ill_export_job", self.dependencies()) as (
			module,
			frappe,
		):
			doc = Record(
				owner=frappe.session.user,
				requested_by=frappe.session.user,
				schedule="S1",
				export_type="SPEC_SUBMITTAL",
			)
			self.assertFalse(module.has_permission(doc))

	def test_query_intersects_price_permission_with_schedule_scope(self):
		with load_service(ROOT + ".doctype.ill_export_job.ill_export_job", self.dependencies(False)) as (
			module,
			_frappe,
		):
			query = module.get_permission_query_conditions()
			self.assertIn("SCOPED_SCHEDULES", query)
			self.assertIn("NOT IN ('PDF_PRICED', 'CSV_PRICED')", query)
			self.assertNotIn(" OR ", query)
