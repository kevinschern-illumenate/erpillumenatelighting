"""Quotations keep their Fixture Schedule links through cancel, amend and new schedule versions."""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from test_desk_configurator_save import desk
from test_offers import IssuedOfferGuards
from test_schedule_sync import Doc, quotation, quote_row, schedule, schedule_line, service
from test_services import ROOT, Record, load_service

LINE_ROWS = [
	Record(name="OLD-1", parent="SCH-1", line_key="K1"),
	Record(name="OLD-2", parent="SCH-1", line_key="K-GONE"),
	Record(name="FOREIGN", parent="SCH-9", line_key="K1"),
]


def versioned(frappe):
	"""SCH-1 is the first version; SCH-2 its next one; SCH-9 is unrelated."""
	frappe.db.get_value.side_effect = lambda doctype, name, field, *a, **k: (
		"SCH-1" if (field == "version_parent" and name == "SCH-2") else None
	)
	frappe.get_all.side_effect = lambda doctype, **kwargs: [
		row for row in LINE_ROWS if row.name in kwargs["filters"]["name"][1]
	]


def second_version(lines):
	sched = schedule(lines)
	sched.update(name="SCH-2", version_parent="SCH-1")
	return sched


class RowsFollowScheduleVersions(unittest.TestCase):
	def test_old_line_names_map_by_line_key_within_the_version_family_only(self):
		with service() as (sync, frappe):
			versioned(frappe)
			sched = second_version([schedule_line("NEW-1", line_key="K1")])
			mapping = sync.stale_line_map(sched, ["OLD-1", "OLD-2", "FOREIGN", "NEW-1", None])
		self.assertEqual(mapping, {"OLD-1": "NEW-1"})

	def test_moving_a_quote_to_the_next_version_relinks_its_rows_without_rewriting_scope(self):
		sched = second_version([schedule_line("NEW-1", line_key="K1")])
		row = quote_row("R1", "OLD-1")
		doc = quotation([row], [], ill_fixture_schedule="SCH-2")
		doc.get_doc_before_save = lambda: Doc(
			{"ill_fixture_schedule": "SCH-1", "items": [quote_row("R1", "OLD-1")]}
		)
		with service() as (sync, frappe):
			versioned(frappe)
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = sched
			with patch.object(sync, "schedule_is_open", return_value=True):
				sync.on_transaction_validate(doc)
		self.assertEqual(row.ill_schedule_line_id, "NEW-1")
		sched.save.assert_not_called()  # Nothing was added or removed: same line, new name.
		self.assertEqual([line.name for line in sched.lines], ["NEW-1"])

	def test_an_amended_quote_relinks_rows_but_leaves_the_schedule_alone(self):
		sched = second_version([schedule_line("NEW-1", line_key="K1")])
		row = quote_row("R1", "OLD-1")
		doc = quotation([row], None, ill_fixture_schedule="SCH-2", amended_from="QTN-0")
		with service() as (sync, frappe):
			versioned(frappe)
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = sched
			with patch.object(sync, "schedule_is_open", return_value=True):
				sync.on_transaction_validate(doc)
		self.assertEqual(row.ill_schedule_line_id, "NEW-1")
		sched.save.assert_not_called()


def quoted_schedule(status="QUOTED"):
	return Record(
		name="SCH-1",
		status=status,
		is_locked=0,
		ill_project=None,
		schedule_name="Main",
		customer="C1",
		modified="now",
		set_lifecycle_status=MagicMock(),
		add_comment=MagicMock(),
	)


class CancelReopensTheSchedule(unittest.TestCase):
	def run_cancel(self, still_quoted):
		with desk() as (module, frappe, *_):
			sched = quoted_schedule()

			def exists(doctype, filters=None):
				if doctype == "ilL-Project-Fixture-Schedule":
					return True
				return still_quoted if doctype == "Quotation" else False

			frappe.db.exists.side_effect = exists
			frappe.get_doc.return_value = sched
			module.on_quotation_cancel(Record(name="QTN-1", ill_fixture_schedule="SCH-1"))
			quotation_filters = next(
				c.args[1] for c in frappe.db.exists.call_args_list if c.args[0] == "Quotation"
			)
		self.assertEqual(quotation_filters["name"], ["!=", "QTN-1"])
		return sched

	def test_the_only_quote_cancelled_puts_the_schedule_back_to_ready(self):
		sched = self.run_cancel(still_quoted=False)
		sched.set_lifecycle_status.assert_called_once_with("READY", note=None)

	def test_another_submitted_quote_keeps_it_quoted(self):
		sched = self.run_cancel(still_quoted=True)
		sched.set_lifecycle_status.assert_not_called()
		self.assertIn("left unchanged", sched.add_comment.call_args.args[1])

	def test_new_version_button_reopens_in_place_when_nothing_quotes_it(self):
		for status, expected in (("QUOTED", "READY"), ("ISSUE", "DRAFT")):
			with self.subTest(status=status), desk() as (module, frappe, *_):
				sched = quoted_schedule(status)
				sched["create_new_version"] = MagicMock()
				frappe.db.exists.return_value = False
				with (
					patch.object(module, "_require_internal_user"),
					patch.object(module, "_load_schedule", return_value=(sched, None)),
				):
					result = module.create_schedule_version("SCH-1")
				sched.set_lifecycle_status.assert_called_once_with(expected, note=None)
				sched.create_new_version.assert_not_called()
				self.assertTrue(result["reopened"])
				self.assertEqual(result["name"], "SCH-1")


class PickerSurvivesABadLine(unittest.TestCase):
	def test_one_unreadable_line_does_not_stop_the_schedule_loading(self):
		reopen = types.ModuleType(ROOT + ".portal.configuration_reopen")

		def for_line(line):
			if line.name == "BROKEN":
				raise LookupError("ilL-Configured-Fixture CF-GONE not found")
			return {"family": "Linear Fixture"}

		reopen.for_line = for_line
		with desk() as (module, frappe, *_), patch.dict(sys.modules, {reopen.__name__: reopen}):
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			lines = [
				Record(name="BROKEN", line_id="A1", qty=1, configured_fixture="CF-GONE"),
				Record(name="OK", line_id="A2", qty=1, line_key="K2"),
			]
			sched = Record(lines=lines, **{k: v for k, v in quoted_schedule("DRAFT").items()})
			with (
				patch.object(module, "_require_internal_user"),
				patch.object(module, "_load_schedule", return_value=(sched, None)),
				patch.object(module, "_next_fixture_type", return_value="A3"),
			):
				data = module.get_schedule_picker_data("SCH-1")
		self.assertTrue(data["success"])
		self.assertEqual(
			[line["initial_request"] for line in data["lines"]], [None, {"family": "Linear Fixture"}]
		)
		frappe.log_error.assert_called_once()


class PortalRequestQuotes(unittest.TestCase):
	def offers(self):
		return load_service(ROOT + ".portal.offers", IssuedOfferGuards().dependencies())

	def test_cancelling_the_issued_quote_reopens_its_request(self):
		with self.offers() as (module, frappe):
			offer = Record(
				name="OFFER1", quote_request="QR1", flags=Record(), is_new=lambda: False, save=MagicMock()
			)
			request = Record(
				state="ISSUED", latest_issued_offer="OFFER1", save=MagicMock(), add_comment=MagicMock()
			)
			frappe.db.get_value.return_value = "OFFER1"
			frappe.get_doc.side_effect = [offer, request]
			module.on_cancel(Record(name="QTN-1"))
		self.assertEqual((offer.state, request.state), ("CANCELLED", "UNDER_REVIEW"))
		request.save.assert_called_once_with(ignore_permissions=True)

	def test_a_later_schedule_version_can_be_offered_but_not_an_unrelated_one(self):
		with self.offers() as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.db.get_value.side_effect = lambda doctype, name, field: (
				"SCH-1" if name == "SCH-2" else None
			)
			request = Record(schedule="SCH-1")
			for linked, expected in (("SCH-1", "SCH-1"), ("SCH-2", "SCH-2"), ("SCH-9", None), (None, None)):
				with self.subTest(linked=linked):
					offered = module.offer_schedule(Record(ill_fixture_schedule=linked), request)
					self.assertEqual(offered, expected)

	def test_a_request_on_a_superseded_version_is_quoted_on_the_open_one(self):
		with self.offers() as (module, frappe):
			frappe.db.get_value.side_effect = lambda doctype, name, field: {
				("SCH-1", "is_locked"): 1,
				("SCH-2", "is_locked"): 0,
			}.get((name, field))
			frappe.get_all.return_value = ["SCH-3"]
			self.assertEqual(module.open_revision("SCH-1"), "SCH-3")
			self.assertEqual(
				frappe.get_all.call_args.kwargs["filters"], {"version_parent": "SCH-1", "is_locked": 0}
			)
			self.assertEqual(module.open_revision("SCH-2"), "SCH-2")


if __name__ == "__main__":
	unittest.main()
