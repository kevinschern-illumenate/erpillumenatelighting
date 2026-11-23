"""Kevin's Desk: the Done button's server side (kevins_desk/done.py)."""

import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from test_services import load_service

PKG = "illumenate_lighting.kevins_desk"
OWNER = "kevins@example.com"
NOW = datetime(2026, 11, 23, 9, 0)
OWN = {"sales@example.com", "kevins@example.com"}


@contextmanager
def done_module():
	utils = types.ModuleType("frappe.utils")
	utils.now_datetime = lambda: NOW
	utils.add_days = lambda d, n: d + timedelta(days=n)
	with load_service(PKG + ".done", {"frappe.utils": utils}) as (done, frappe):
		frappe.log_error = MagicMock()
		yield done, frappe


class Parse(unittest.TestCase):
	def test_todo_and_gmail_ids(self):
		with done_module() as (done, _):
			self.assertEqual(done.parse("ToDo:6gq1qes7f4"), ("todo", "6gq1qes7f4"))
			self.assertEqual(
				done.parse("gmail:Sales@Example.com:18a2b3c4d5e6f708"),
				("gmail", "sales@example.com", "18a2b3c4d5e6f708"),
			)

	def test_anything_else_is_not_found(self):
		with done_module() as (done, _):
			for bad in (
				None,
				42,
				"",
				"ToDo:",
				"ToDo:../x",
				"Sales Order:SO-1",
				"gmail:t1",
				"gmail:sales@example.com:",
				"gmail:sales@example.com:t 1",
				"gmail:nobody:t1",
			):
				with self.subTest(bad=bad), self.assertRaises(LookupError):
					done.parse(bad)


class CloseTodo(unittest.TestCase):
	def todo(self, **kw):
		return types.SimpleNamespace(
			**dict({"allocated_to": OWNER, "status": "Open"}, **kw), save=MagicMock()
		)

	def test_closes_the_owners_open_todo(self):
		doc = self.todo()
		with done_module() as (done, frappe):
			frappe.get_doc = MagicMock(return_value=doc)
			done.close_todo("T-1", OWNER)
		frappe.get_doc.assert_called_once_with("ToDo", "T-1")
		self.assertEqual(doc.status, "Closed")
		doc.save.assert_called_once_with()  # a normal save: ERPNext's own permission check applies

	def test_someone_elses_todo_is_not_found(self):
		doc = self.todo(allocated_to="ryanb@example.com")
		with done_module() as (done, frappe):
			frappe.get_doc = MagicMock(return_value=doc)
			with self.assertRaises(LookupError):
				done.close_todo("T-1", OWNER)
		doc.save.assert_not_called()

	def test_already_closed_or_cancelled_is_left_alone(self):
		for status in ("Closed", "Cancelled"):
			doc = self.todo(status=status)
			with self.subTest(status=status), done_module() as (done, frappe):
				frappe.get_doc = MagicMock(return_value=doc)
				done.close_todo("T-1", OWNER)
			doc.save.assert_not_called()
			self.assertEqual(doc.status, status)


class HideThread(unittest.TestCase):
	def test_a_new_thread_is_recorded_and_old_records_pruned(self):
		with done_module() as (done, frappe):
			frappe.db.get_value.return_value = None
			done.hide_thread("sales@example.com", "t1", "m9", "  RFQ " + "x" * 200, OWN)
		frappe.db.delete.assert_called_once_with(
			"ilL-Desk-Done", {"modified": ["<", NOW - timedelta(days=done.KEEP_DAYS)]}
		)
		record = frappe.get_doc.call_args.args[0]
		self.assertEqual(
			{k: record[k] for k in ("doctype", "mailbox", "thread_id", "message_id")},
			{
				"doctype": "ilL-Desk-Done",
				"mailbox": "sales@example.com",
				"thread_id": "t1",
				"message_id": "m9",
			},
		)
		self.assertEqual(len(record["title"]), 140)
		self.assertTrue(record["title"].startswith("RFQ x"))
		frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	def test_a_thread_done_before_moves_to_its_new_last_message(self):
		with done_module() as (done, frappe):
			frappe.db.get_value.return_value = "abc123"
			done.hide_thread("sales@example.com", "t1", "m10", None, OWN)
		frappe.db.set_value.assert_called_once_with(
			"ilL-Desk-Done", "abc123", {"message_id": "m10", "title": "(no subject)"}
		)
		frappe.get_doc.assert_not_called()

	def test_other_mailboxes_and_bad_message_ids_are_refused(self):
		for mailbox, message_id in (
			("someone@else.com", "m1"),
			("sales@example.com", None),
			("sales@example.com", ""),
			("sales@example.com", "m 1"),
			("sales@example.com", ["m1"]),
		):
			with self.subTest(mailbox=mailbox, message_id=message_id), done_module() as (done, frappe):
				with self.assertRaises(LookupError):
					done.hide_thread(mailbox, "t1", message_id, "x", OWN)
				frappe.db.delete.assert_not_called()
				frappe.get_doc.assert_not_called()


class Marks(unittest.TestCase):
	def test_marks_key_by_mailbox_and_thread(self):
		with done_module() as (done, frappe):
			frappe.get_all = MagicMock(
				return_value=[{"mailbox": "sales@example.com", "thread_id": "t1", "message_id": "m9"}]
			)
			self.assertEqual(done.marks(), {("sales@example.com", "t1"): "m9"})

	def test_an_unreadable_table_hides_nothing_and_is_logged(self):
		with done_module() as (done, frappe):
			frappe.get_all = MagicMock(side_effect=RuntimeError("no such table"))
			self.assertEqual(done.marks(), {})
		frappe.log_error.assert_called_once()


if __name__ == "__main__":
	unittest.main()
