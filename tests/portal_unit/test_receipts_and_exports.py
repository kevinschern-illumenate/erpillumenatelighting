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


class StaffRaisedQuoteRequests(unittest.TestCase):
	def dependencies(self, capabilities):
		access = types.ModuleType(ROOT + ".portal.access")
		access.can_edit_schedule = MagicMock(return_value=True)
		access.can_read_schedule = MagicMock(return_value=True)
		staff = types.ModuleType(ROOT + ".portal.staff")

		def require(capability):
			if capability not in capabilities:
				raise PermissionError("staff only")

		staff.require = MagicMock(side_effect=require)
		return {access.__name__: access, staff.__name__: staff}

	def test_only_sales_staff_can_raise_a_request_for_a_dealer(self):
		with load_service(ROOT + ".portal.quotes", self.dependencies(set())) as (module, _frappe):
			module.request_quote = MagicMock()
			with self.assertRaises(PermissionError):
				module.request_quote_for_dealer("S1", notes="Phone call")
			module.request_quote.assert_not_called()

	def test_staff_request_uses_the_dealer_flow_and_records_who_raised_it(self):
		with load_service(ROOT + ".portal.quotes", self.dependencies({"sales"})) as (module, frappe):
			frappe.session.user = "jay@example.com"
			request = MagicMock()
			frappe.get_doc.return_value = request
			module.request_quote = MagicMock(
				return_value={"success": True, "request_name": "QR9", "state": "REQUESTED", "already_existed": False}
			)
			receipt = module.request_quote_for_dealer("S1", notes="Phone call", requested_date="2026-12-01")
			module.request_quote.assert_called_once_with(
				"S1", idempotency_key=None, notes="Phone call", contact=None, requested_date="2026-12-01"
			)
			self.assertEqual(receipt["request_name"], "QR9")
			frappe.get_doc.assert_called_once_with("ilL-Quote-Request", "QR9")
			request.add_comment.assert_called_once()
			self.assertIn("jay@example.com", request.add_comment.call_args.args[1])

	def test_a_repeated_staff_request_adds_no_second_note(self):
		with load_service(ROOT + ".portal.quotes", self.dependencies({"sales"})) as (module, frappe):
			module.request_quote = MagicMock(return_value={"request_name": "QR9", "already_existed": True})
			module.request_quote_for_dealer("S1")
			frappe.get_doc.assert_not_called()


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


class SchedulePartNumbers(unittest.TestCase):
	def test_linear_fixture_shows_display_part_number_not_hash_name(self):
		file_manager = types.ModuleType("frappe.utils.file_manager")
		file_manager.save_file = MagicMock()
		with load_service(ROOT + ".api.exports", {file_manager.__name__: file_manager}) as (module, frappe):
			line = Record(
				idx=1,
				line_id="A",
				qty=2,
				manufacturer_type="ILLUMENATE",
				configured_fixture="ILL-CF-" + "a" * 64,
			)
			frappe.get_doc.return_value = Record(
				schedule_name="Schedule", status="DRAFT", ill_project=None, customer=None, lines=[line]
			)
			frappe.get_all.return_value = [
				Record(name=line.configured_fixture, display_part_number="ILL-SL-SW-I-30-HO-FR-SM-WH-48")
			]
			module._get_fixture_export_details = MagicMock(return_value={})
			data = module._get_schedule_data("S1")
			self.assertIn("display_part_number", frappe.get_all.call_args.kwargs["fields"])
			html = module._generate_pdf_content(data)
			self.assertIn("<strong>ILL-SL-SW-I-30-HO-FR-SM-WH-48</strong>", html)
			self.assertNotIn("ILL-CF-", html)


class SchedulePdfExports(unittest.TestCase):
	"""The portal PDF exports print with the schedule print formats (owner, 2026-11-23)."""

	def export(self, priced, print_error=None):
		file_manager = types.ModuleType("frappe.utils.file_manager")
		file_manager.save_file = MagicMock()
		pdf_module = types.SimpleNamespace(get_pdf=MagicMock(return_value=b"%PDF-old"))
		with load_service(
			ROOT + ".api.exports", {file_manager.__name__: file_manager, "frappe.utils.pdf": pdf_module}
		) as (module, frappe):
			schedule = Record(name="S1", schedule_name="Main")
			frappe.get_doc.return_value = schedule
			frappe.get_roles.return_value = ["Dealer"]
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="traceback")
			frappe.get_print = MagicMock(side_effect=print_error, return_value=b"%PDF-print")
			module._check_schedule_access = lambda name: (True, None)
			module._create_export_job = MagicMock(return_value="JOB")
			module._update_export_job_status = MagicMock()
			module._get_schedule_data = MagicMock(return_value={})
			module._generate_pdf_content = MagicMock(return_value="<html>old</html>")
			saved = []
			module._save_file_ignore_permissions = lambda name, content, *a, **kw: (
				saved.append((name, content)) or Record(file_url=f"/private/files/{name}")
			)
			result = module.generate_schedule_pdf("S1", priced=priced)
			return result, frappe, saved

	def test_unpriced_pdf_uses_the_fixture_schedule_format(self):
		result, frappe, saved = self.export(False)
		self.assertTrue(result["success"], result)
		kwargs = frappe.get_print.call_args.kwargs
		self.assertEqual(kwargs["print_format"], "ilL Fixture Schedule")
		self.assertTrue(kwargs["as_pdf"])
		self.assertEqual(saved[0][1], b"%PDF-print")
		self.assertIn("_no_price_", saved[0][0])
		# Print permission is bypassed only for the call; access was checked before it.
		self.assertFalse(frappe.flags.ignore_print_permissions)

	def test_priced_pdf_uses_the_msrp_format(self):
		result, frappe, saved = self.export(True)
		self.assertTrue(result["success"], result)
		self.assertEqual(frappe.get_print.call_args.kwargs["print_format"], "ilL Fixture Schedule - MSRP")
		self.assertIn("_priced_", saved[0][0])

	def test_a_failing_print_format_falls_back_to_the_older_layout(self):
		result, frappe, saved = self.export(False, print_error=RuntimeError("bad template"))
		self.assertTrue(result["success"], result)
		self.assertEqual(saved[0][1], b"%PDF-old")
		frappe.log_error.assert_called_once()
