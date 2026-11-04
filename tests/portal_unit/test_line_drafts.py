"""Plan 3.1: durable configurator drafts keyed by user + schedule + line + product type."""

import json
import types
import unittest

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.line_drafts"


class LineDrafts(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.schedule = Record(name="SCH-1", lines=[Record(name="row1", line_key="k-1")])
		self.calls = []

		def schedule_context(name, write=False, lock=False):
			self.calls.append((name, write))
			if name != "SCH-1":
				raise PermissionError("Schedule is unavailable")
			return self.schedule

		def resolve_line(schedule, line_key=None, line_idx=None):
			matches = [line for line in schedule.lines if line.line_key == line_key or line.name == line_key]
			if len(matches) != 1:
				raise ValueError("The selected line changed or is unavailable; reload the schedule")
			return matches[0]

		self.extras = {
			ROOT + ".portal.configuration": types.SimpleNamespace(
				schedule_context=schedule_context, resolve_line=resolve_line
			),
			ROOT + ".portal.site_flags": types.SimpleNamespace(durable_drafts_enabled=lambda: self.enabled),
		}

	def draft(self, **request):
		return json.dumps({"request": {"family": "Linear Fixture", "template": "T1", **request}, "metadata": {"qty": "2"}})

	def test_first_save_inserts_a_scoped_session_row(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.get_all.return_value = []
			result = module.save_draft("SCH-1", "Linear Fixture", self.draft(), line_key="k-1")
			self.assertEqual(result, {"success": True, "saved_on": "2026-09-25 12:00:00"})
			self.assertEqual(self.calls, [("SCH-1", True)], "drafts require write access to the schedule")
			doc = frappe.get_doc.call_args.args[0]
			self.assertEqual(
				{key: doc[key] for key in ("doctype", "user", "schedule", "line_key", "product_type", "source", "status")},
				{
					"doctype": "ilL-Configurator-Session",
					"user": "buyer@example.com",
					"schedule": "SCH-1",
					"line_key": "k-1",
					"product_type": "Linear Fixture",
					"source": "Portal",
					"status": "Active",
				},
			)
			self.assertEqual(json.loads(doc["draft_json"])["request"]["template"], "T1")
			frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	def test_later_saves_update_the_same_row_and_retire_duplicates(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.get_all.return_value = [Record(name="D1"), Record(name="D0")]
			module.save_draft("SCH-1", "LED Tape", self.draft(template="T2"))
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(filters["line_key"], "", "a new-line draft has an empty line key")
			self.assertEqual(filters["user"], "buyer@example.com")
			first, second = frappe.db.set_value.call_args_list
			self.assertEqual(first.args[0:2], ("ilL-Configurator-Session", "D1"))
			self.assertEqual(json.loads(first.args[2]["draft_json"])["request"]["template"], "T2")
			self.assertEqual(first.args[2]["last_seen"], "2026-09-25 12:00:00")
			self.assertEqual(second.args, ("ilL-Configurator-Session", "D0", "status", "Used"))
			frappe.get_doc.assert_not_called()

	def test_a_line_key_must_exist_on_the_schedule(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			with self.assertRaises(ValueError):
				module.save_draft("SCH-1", "Linear Fixture", self.draft(), line_key="gone")
			frappe.get_doc.assert_not_called()

	def test_permission_and_input_are_checked_before_anything_is_stored(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.get_all.return_value = []
			with self.assertRaises(PermissionError):
				module.save_draft("SCH-OTHER", "Linear Fixture", self.draft())
			for product_type, draft in (
				("Mixed", self.draft()),
				("Linear Fixture", "not json"),
				("Linear Fixture", json.dumps({"metadata": {}})),
				("Linear Fixture", json.dumps({"request": {}, "metadata": "x"})),
				("Linear Fixture", json.dumps({"request": {"blob": "x" * (64 * 1024)}})),
			):
				with self.subTest(product_type=product_type, draft=draft[:30]), self.assertRaises(ValueError):
					module.save_draft("SCH-1", product_type, draft)
			frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				module.save_draft("SCH-1", "Linear Fixture", self.draft())
			frappe.get_doc.assert_not_called()
			frappe.db.set_value.assert_not_called()

	def test_only_the_request_and_line_details_are_kept(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.get_all.return_value = []
			payload = {"request": {"template": "T1"}, "metadata": {"qty": "1"}, "user": "someone@else", "price": 1}
			module.save_draft("SCH-1", "Linear Fixture", payload)
			stored = json.loads(frappe.get_doc.call_args.args[0]["draft_json"])
			self.assertEqual(stored, {"request": {"template": "T1"}, "metadata": {"qty": "1"}})

	def test_get_returns_the_latest_draft_or_none(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.get_all.return_value = []
			self.assertEqual(module.get_draft("SCH-1", "Linear Fixture", "k-1"), {"success": True, "draft": None})
			frappe.get_all.return_value = [
				Record(name="D1", draft_json='{"request": {"template": "T1"}, "metadata": {}}', last_seen="2026-11-03 10:00:00", modified="x")
			]
			result = module.get_draft("SCH-1", "Linear Fixture", "k-1")
			self.assertEqual(result["draft"]["request"], {"template": "T1"})
			self.assertEqual(result["saved_on"], "2026-11-03 10:00:00")
			self.assertEqual(frappe.get_all.call_args.kwargs["order_by"], "modified desc")
			with self.assertRaises(PermissionError):
				module.get_draft("SCH-OTHER", "Linear Fixture")

	def test_discard_retires_every_matching_draft(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			frappe.get_all.return_value = [Record(name="D1"), Record(name="D2")]
			self.assertEqual(module.discard_draft("SCH-1", "Linear Fixture", "k-1"), {"success": True})
			self.assertEqual(
				[call.args for call in frappe.db.set_value.call_args_list],
				[("ilL-Configurator-Session", "D1", "status", "Used"), ("ilL-Configurator-Session", "D2", "status", "Used")],
			)

	def test_the_kill_switch_stops_saving_and_restoring(self):
		self.enabled = False
		with load_service(MODULE, self.extras) as (module, frappe):
			self.assertEqual(module.save_draft("SCH-1", "Linear Fixture", self.draft()), {"success": False, "disabled": True})
			self.assertEqual(module.get_draft("SCH-1", "Linear Fixture")["draft"], None)
			frappe.get_all.assert_not_called()
			frappe.get_doc.assert_not_called()

	def test_finder_session_lookups_ignore_schedule_drafts(self):
		from pathlib import Path

		repo = Path(__file__).resolve().parents[2] / "illumenate_lighting/illumenate_lighting"
		for path in ("api/configurator_session.py", "portal/product_finder/presentation.py"):
			source = (repo / path).read_text(encoding="utf8")
			self.assertIn('"schedule": ["is", "not set"]', source, path)


class DraftSessionSchema(unittest.TestCase):
	def test_the_draft_fields_are_additive(self):
		from pathlib import Path

		path = (
			Path(__file__).resolve().parents[2]
			/ "illumenate_lighting/illumenate_lighting/doctype/ill_configurator_session/ill_configurator_session.json"
		)
		doctype = json.loads(path.read_text(encoding="utf8"))
		fields = {field["fieldname"]: field for field in doctype["fields"]}
		self.assertEqual(fields["schedule"]["options"], "ilL-Project-Fixture-Schedule")
		self.assertEqual(fields["line_key"]["fieldtype"], "Data")
		self.assertEqual(fields["draft_json"]["fieldtype"], "JSON")
		self.assertTrue(all(fields[name].get("read_only") for name in ("schedule", "line_key", "draft_json")))
		for name in ("user", "session_token", "product_type", "quiz_answers", "status", "source", "last_seen"):
			self.assertIn(name, fields, "existing finder fields are kept")
		self.assertEqual(doctype["field_order"], [field["fieldname"] for field in doctype["fields"]])


class DraftFlag(unittest.TestCase):
	def test_durable_drafts_default_on(self):
		with load_service(ROOT + ".portal.site_flags") as (module, frappe):
			self.assertTrue(module.durable_drafts_enabled())
			frappe.conf["ill_portal_durable_drafts"] = "false"
			self.assertFalse(module.durable_drafts_enabled())


if __name__ == "__main__":
	unittest.main()
