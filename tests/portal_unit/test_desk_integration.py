"""Desk shows what is waiting on staff and where portal records came from (DESK-4, DESK-5, DESK-6)."""

import re
import sqlite3
import unittest

from test_services import ROOT, load_service

SCHEMA = """
CREATE TABLE `tabUser` (name TEXT PRIMARY KEY, user_type TEXT);
CREATE TABLE `tabilL-Portal-Message` (
	name TEXT PRIMARY KEY, reference_type TEXT, reference_name TEXT, actor TEXT, visibility TEXT, creation TEXT
);
INSERT INTO `tabUser` VALUES ('sales@illumenate.test', 'System User'), ('buyer@acme.test', 'Website User');
"""


class UnreadCustomerMessages(unittest.TestCase):
	def count(self, messages):
		db = sqlite3.connect(":memory:")
		db.executescript(SCHEMA)
		db.executemany(
			"INSERT INTO `tabilL-Portal-Message` VALUES (?, 'ilL-Quote-Request', 'QR-1', ?, ?, ?)",
			[(f"M{i}", *row) for i, row in enumerate(messages)],
		)
		with load_service(ROOT + ".portal.conversations") as (module, frappe):
			frappe.db.sql = lambda query, values: db.execute(
				re.sub(r"%\((\w+)\)s", r":\1", query), values
			).fetchall()
			return module.new_from_customer("ilL-Quote-Request", "QR-1")

	def test_counts_customer_messages_after_the_last_staff_message(self):
		messages = [
			("buyer@acme.test", "Customer", "2026-10-10 09:00"),
			("sales@illumenate.test", "Customer", "2026-10-11 09:00"),
			("buyer@acme.test", "Customer", "2026-10-12 09:00"),
			("buyer@acme.test", "Customer", "2026-10-13 09:00"),
		]
		self.assertEqual(self.count(messages), 2)

	def test_a_staff_note_counts_as_staff_having_looked(self):
		messages = [
			("buyer@acme.test", "Customer", "2026-10-10 09:00"),
			("sales@illumenate.test", "Internal", "2026-10-11 09:00"),
		]
		self.assertEqual(self.count(messages), 0)

	def test_no_staff_reply_yet_counts_everything_from_the_customer(self):
		self.assertEqual(self.count([("buyer@acme.test", "Customer", "2026-10-10 09:00")]), 1)


class QueueColumns(unittest.TestCase):
	def test_quote_and_order_queues_show_who_and_what(self):
		with load_service(ROOT + ".portal.queues") as (module, _frappe):
			for queue in ("quotes", "orders"):
				with self.subTest(queue=queue):
					fields = module.QUEUES[queue][4]
					for field in ("customer", "schedule", "requested_by"):
						self.assertIn(field, fields)
			self.assertIn("project", module.QUEUES["quotes"][4])


if __name__ == "__main__":
	unittest.main()
