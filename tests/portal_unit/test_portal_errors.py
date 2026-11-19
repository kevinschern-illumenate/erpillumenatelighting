"""Structured portal errors and broad-except narrowing — plan items 1.6 / 2.4."""

import pathlib
import types
import unittest
from typing import ClassVar
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

APP = pathlib.Path(__file__).resolve().parents[2] / "illumenate_lighting"
SCHEDULE = "ilL-Project-Fixture-Schedule"
LOADED = "2026-11-18 09:00:00.000001"
SAVED = "2026-11-18 09:00:00.000052"
STALE = "This schedule changed since you opened it. Reload to see the latest version."
RAW = "Error: Document has been modified after you have opened it. Please refresh to get the latest document."


class PortalErrors(unittest.TestCase):
	def load(self):
		return load_service(ROOT + ".portal.errors")

	def test_portal_error_is_a_validation_error_with_payload(self):
		with self.load() as (errors, frappe):
			with self.assertRaises(frappe.ValidationError) as caught:
				errors.portal_error("RUN_TOO_LONG", "Reduce this run to 16 ft", field="length", hint="Add a feed")
			self.assertEqual(
				caught.exception.portal_payload,
				{"code": "RUN_TOO_LONG", "message": "Reduce this run to 16 ft", "field": "length", "hint": "Add a feed"},
			)

	def raising_site(self, frappe):
		frappe.local.response = {}
		frappe.local.message_log = []
		frappe.msgprint = lambda text, **kwargs: frappe.local.message_log.append({"message": text, **kwargs})

	def test_portal_error_reaches_the_response_and_the_legacy_message_log(self):
		with self.load() as (errors, frappe):
			self.raising_site(frappe)
			frappe.local.message_log.append({"message": "earlier"})
			with self.assertRaises(errors.PortalError):
				errors.portal_error("RUN_TOO_LONG", "Reduce this run to 16 ft.", field="length", hint="Or add a feed.")
			self.assertEqual(frappe.local.response["portal_error"]["field"], "length")
			self.assertEqual(frappe.local.response["portal_error"]["code"], "RUN_TOO_LONG")
			self.assertEqual(
				frappe.local.message_log[-1], {"message": "Reduce this run to 16 ft. Or add a feed.", "indicator": "red"}
			)

	def test_a_caught_portal_error_becomes_a_quiet_legacy_reply(self):
		with self.load() as (errors, frappe):
			self.raising_site(frappe)
			frappe.local.message_log.append({"message": "earlier"})
			try:
				errors.portal_error("NO_FEED", "Pick a feed", field="feed")
			except errors.PortalError as exc:
				result = errors.failure(exc, "FALLBACK", title="t")
			self.assertEqual(result, {"success": False, "error": "Pick a feed", "error_code": "NO_FEED", "field": "feed"})
			self.assertNotIn("portal_error", frappe.local.response)
			self.assertEqual(frappe.local.message_log, [{"message": "earlier"}])

	def test_portal_error_without_a_request_still_raises(self):
		with self.load() as (errors, frappe):
			frappe.msgprint = MagicMock(side_effect=RuntimeError("no request"))
			with self.assertRaises(errors.PortalError) as caught:
				errors.portal_error("X", "Fix it")
			self.assertIsNone(caught.exception.msgprinted)

	def test_failure_keeps_portal_payload(self):
		with self.load() as (errors, frappe):
			frappe.log_error = MagicMock()
			result = errors.failure(errors.PortalError("X", "Fix it", field="f"), "FALLBACK", title="t")
			self.assertEqual(result, {"success": False, "error": "Fix it", "error_code": "X", "field": "f"})
			frappe.log_error.assert_not_called()

	def test_expected_errors_keep_message_and_are_not_logged(self):
		with self.load() as (errors, frappe):
			frappe.log_error = MagicMock()
			for exc in (ValueError("Bad length"), frappe.ValidationError("Bad length"), PermissionError("Bad length")):
				result = errors.failure(exc, "schedule_save_failed", title="t")
				self.assertEqual(
					result, {"success": False, "error": "Bad length", "error_code": "schedule_save_failed"}
				)
			frappe.log_error.assert_not_called()

	def test_service_endpoint_turns_raised_errors_into_replies(self):
		"""Account endpoints raised plain ValueErrors, which Frappe answered with a bare HTTP 500."""
		with self.load() as (errors, frappe):
			self.raising_site(frappe)
			frappe.session = Record(user="dealer@example.com")
			frappe.get_traceback = MagicMock(return_value="Traceback")
			frappe.log_error = MagicMock(return_value=Record(name="ERR-0002"))

			@errors.service_endpoint("account_request_failed", "Portal account service")
			def save_record(problem):
				frappe.local.message_log.append({"message": "queued popup"})
				raise problem

			refused = save_record(ValueError("This record changed. Reload before requesting a change."))
			self.assertEqual(
				refused,
				{
					"success": False,
					"error": "This record changed. Reload before requesting a change.",
					"error_code": "account_request_failed",
				},
			)
			self.assertEqual(frappe.local.message_log, [])
			frappe.log_error.assert_not_called()

			crashed = save_record(RuntimeError("Unknown column request_key"))
			self.assertEqual(crashed["error_code"], errors.UNEXPECTED)
			self.assertIn("ERR-0002", crashed["error"])
			message = frappe.log_error.call_args.kwargs["message"]
			self.assertIn("method: save_record", message)
			self.assertIn("user: dealer@example.com", message)
			self.assertEqual(save_record.__name__, "save_record")

	def test_unexpected_errors_are_logged_with_context_and_hidden(self):
		with self.load() as (errors, frappe):
			frappe.get_traceback = MagicMock(return_value="Traceback (most recent call last): ...")
			frappe.log_error = MagicMock(return_value=Record(name="ERR-0001"))
			result = errors.failure(
				RuntimeError("column x missing in tabSchedule"),
				"schedule_save_failed",
				title="Kit save failed",
				context={"schedule": "SCH-1", "line_idx": 2},
			)
			self.assertEqual(result["error_code"], errors.UNEXPECTED)
			self.assertNotIn("tabSchedule", result["error"])
			self.assertIn("ERR-0001", result["error"])
			kwargs = frappe.log_error.call_args.kwargs
			self.assertEqual(kwargs["title"], "Kit save failed")
			for fragment in ("schedule: SCH-1", "line_idx: 2", "RuntimeError", "Traceback"):
				self.assertIn(fragment, kwargs["message"])

	def test_rollback_only_for_write_requests_when_asked(self):
		with self.load() as (errors, frappe):
			frappe.log_error = MagicMock()
			frappe.local.request = Record(method="POST")
			errors.failure(ValueError("x"), "c", title="t")
			frappe.db.rollback.assert_not_called()
			errors.failure(ValueError("x"), "c", title="t", rollback=True)
			frappe.db.rollback.assert_called_once_with()
			frappe.local.request = Record(method="GET")
			errors.failure(ValueError("x"), "c", title="t", rollback=True)
			frappe.db.rollback.assert_called_once_with()

	def test_unexpected_logs_survive_rollback(self):
		with self.load() as (errors, frappe):
			frappe.get_traceback = MagicMock(return_value="")
			frappe.log_error = MagicMock()
			errors.failure(RuntimeError("boom"), "c", title="t", rollback=True)
			self.assertTrue(frappe.log_error.call_args.kwargs["defer_insert"])

	def test_logging_failures_never_mask_the_response(self):
		with self.load() as (errors, frappe):
			frappe.get_traceback = MagicMock(side_effect=RuntimeError)
			frappe.log_error = MagicMock(side_effect=RuntimeError("db gone"))
			result = errors.failure(RuntimeError("boom"), "C", title="t")
			self.assertEqual(result["error_code"], errors.UNEXPECTED)
			self.assertTrue(result["error"].endswith("."))


class KitSpecLoaders(unittest.TestCase):
	def test_missing_spec_is_quiet_and_unexpected_errors_are_logged(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			frappe.get_traceback = MagicMock(return_value="")
			frappe.log_error = MagicMock()
			frappe.get_doc.side_effect = frappe.DoesNotExistError("gone")
			for loader in (service._get_profile_spec_data, service._get_lens_spec_data, service._get_accessory_spec_data):
				self.assertEqual(loader("SPEC-1"), {"spec_name": "SPEC-1", "error": "Could not load spec"})
			frappe.log_error.assert_not_called()
			frappe.get_doc.side_effect = RuntimeError("bad column")
			self.assertEqual(
				service._get_lens_spec_data("SPEC-2"), {"spec_name": "SPEC-2", "error": "Could not load spec"}
			)
			self.assertIn("spec: SPEC-2", frappe.log_error.call_args.kwargs["message"])


class StaleScheduleSaves(unittest.TestCase):
	"""Health item 6: a double-submitted line action is a stale reply, never a logged raw error."""

	def call(self, endpoint, save_error=None, modified=LOADED, **kwargs):
		deps = {
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda c: False),
			ROOT + ".portal.line_undo": types.SimpleNamespace(
				snapshot=lambda schedule, lines: [], remember=MagicMock(return_value=None)
			),
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				has_permission=lambda *a: True
			),
			ROOT + ".portal.line_edit": types.SimpleNamespace(apply_line_data=MagicMock()),
		}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			error = frappe.TimestampMismatchError(RAW) if save_error is None else save_error
			schedule = Record(
				name="S",
				status="DRAFT",
				is_locked=0,
				modified=modified,
				lines=[Record(line_key="A")],
				save=MagicMock(side_effect=error),
				duplicate_line=MagicMock(side_effect=error),
			)
			frappe.get_doc.return_value = schedule
			frappe.db.exists.return_value = True
			# The competing save is committed: who saved it and when is read after the rollback.
			frappe.db.get_value.side_effect = lambda doctype, name, *a, **kw: (
				Record(modified=SAVED, modified_by="pat@example.com") if doctype == SCHEDULE else "Pat Smith"
			)
			frappe.local.request = Record(method="POST")
			frappe.local.message_log = [{"message": "earlier"}, {"message": RAW, "raise_exception": 1}]
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="Traceback")
			frappe.utils.strip_html = lambda value: value
			result = getattr(api, endpoint)("S", line_key="A", expected_modified=LOADED, **kwargs)
			return result, frappe, schedule

	def test_timestamp_mismatch_is_a_stale_reply_with_conflict_details(self):
		for endpoint, extra in (
			("delete_schedule_line", {}),
			("duplicate_schedule_line", {}),
			("update_schedule_line", {"line_data": {"qty": 2}}),
		):
			with self.subTest(endpoint=endpoint):
				result, frappe, _ = self.call(endpoint, **extra)
				self.assertEqual(result["error_code"], "stale")
				self.assertFalse(result["success"])
				self.assertEqual(result["error"], STALE)
				self.assertNotIn("modified after", result["error"])
				self.assertEqual(result["conflict"]["modified"], SAVED)
				self.assertEqual(result["conflict"]["modified_by_name"], "Pat Smith")
				self.assertNotIn("pat@example.com", str(result))
				frappe.log_error.assert_not_called()
				frappe.db.rollback.assert_called()
				# The raw Frappe text queued for the page's error dialog is withdrawn too.
				self.assertEqual(frappe.local.message_log, [{"message": "earlier"}])

	def test_refused_expected_modified_is_stale_and_not_logged(self):
		result, frappe, schedule = self.call("delete_schedule_line", modified=SAVED)
		self.assertEqual(result["error_code"], "stale")
		self.assertEqual(result["error"], STALE)
		self.assertEqual(result["conflict"]["modified"], SAVED)
		schedule.save.assert_not_called()
		frappe.log_error.assert_not_called()

	def test_without_a_schedule_the_reply_is_stale_without_conflict(self):
		with load_service(ROOT + ".api.portal") as (api, frappe):
			frappe.log_error = MagicMock()
			result = api._safe_error(frappe.TimestampMismatchError(RAW), "prefix")
			self.assertEqual(result, {"success": False, "error": STALE, "error_code": "stale"})
			frappe.log_error.assert_not_called()

	def test_other_errors_are_still_logged(self):
		result, frappe, _ = self.call("delete_schedule_line", save_error=RuntimeError("deadlock"))
		self.assertEqual(result["error_code"], "internal_error")
		self.assertNotIn("conflict", result)
		frappe.log_error.assert_called_once()


class NarrowedSites(unittest.TestCase):
	"""The plan-listed swallow sites must route through portal.errors."""

	SITES: ClassVar[dict[str, tuple[str, int]]] = {
		"illumenate_lighting/api/tape_neon_configurator.py": ("failure(", 5),
		"illumenate_lighting/api/extrusion_kit_configurator.py": ("is_expected(e)", 4),
		"templates/pages/schedule.py": ("log_unexpected(e", 3),
	}

	def test_sites_use_the_boundary_helpers(self):
		for relative, (needle, count) in self.SITES.items():
			source = (APP / relative).read_text(encoding="utf-8")
			self.assertGreaterEqual(source.count(needle), count, relative)
			self.assertNotIn('return {"success": False, "error": str(e)}', source, relative)


if __name__ == "__main__":
	unittest.main()
