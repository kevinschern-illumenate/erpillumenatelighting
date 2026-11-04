"""Hardening plan 7.3: a dealer session never receives an Internal portal message, on any page."""

import re
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_conversations import service
from test_services import ROOT, Record, load_service

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting"

ROWS = [
	Record(name="M1", actor="buyer@example.com", creation="2026-11-01 09:00", body="Customer question", visibility="Customer", action="REPLY"),
	Record(name="M2", actor="staff@example.com", creation="2026-11-01 10:00", body="Margin is thin", visibility="Internal", action="REPLY"),
	Record(name="M3", actor="staff@example.com", creation="2026-11-01 11:00", body="Answer sent", visibility="Customer", action="REPLY"),
]
# Every Python module that reads ilL-Portal-Message. A new reader must be added here only after
# it is shown to filter visibility for dealers (or be staff/write-only).
REVIEWED_READERS = {
	"illumenate_lighting/hooks.py",
	"illumenate_lighting/illumenate_lighting/portal/conversations.py",
	"illumenate_lighting/illumenate_lighting/portal/files.py",
	# Reads only a message's parent record to build a link; every entry passes outbox.reference_access.
	"illumenate_lighting/illumenate_lighting/portal/notification_center.py",
	"illumenate_lighting/illumenate_lighting/portal/outbox.py",
	"illumenate_lighting/illumenate_lighting/portal/product_finder/verification.py",
	"illumenate_lighting/illumenate_lighting/portal/schedule_commercial.py",
}


def table(doctype, filters=None, **kwargs):
	rows = [row for row in ROWS if all(row.get(key) == value for key, value in (filters or {}).items() if key in row)]
	if kwargs.get("order_by", "").startswith("creation desc"):
		rows = sorted(rows, key=lambda row: row.creation, reverse=True)
	return [Record(row) for row in rows][: kwargs.get("limit_page_length") or None]


class DealerNeverSeesInternal(unittest.TestCase):
	def test_no_conversation_parent_returns_internal_rows_to_a_dealer(self):
		with service() as (module, frappe, _files, doc, _stored, staff, _notify):
			frappe.get_all.side_effect = lambda doctype, **kw: table(doctype, **kw) if doctype == module.MESSAGE else []
			frappe.db.count.side_effect = lambda doctype, filters: len(table(doctype, filters))
			for parent_type in module.PARENTS:
				with self.subTest(parent=parent_type):
					doc.doctype = parent_type
					doc.state = "UNDER_REVIEW"
					result = module.list_messages(parent_type, "P-1")
					self.assertEqual([row.visibility for row in result["messages"]], ["Customer", "Customer"])
					self.assertNotIn("Margin is thin", repr(result))
					self.assertEqual(result["total"], 2)
			staff.return_value = True
			self.assertIn("Internal", [row.visibility for row in module.list_messages("Issue", "P-1")["messages"]])

	def test_direct_reads_and_attachments_refuse_internal_rows(self):
		with service() as (module, _frappe, _files, _doc, _stored, _staff, _notify):
			for parent_type in module.PARENTS:
				with self.subTest(parent=parent_type):
					internal = Record(reference_type=parent_type, reference_name="P-1", visibility="Internal")
					self.assertFalse(module.has_permission(internal))
					self.assertTrue(module.has_permission(Record(internal, visibility="Customer")))

	def test_schedule_page_preview_uses_the_last_customer_message(self):
		with load_service(ROOT + ".portal.schedule_commercial") as (module, frappe):
			frappe.get_all.side_effect = table
			frappe.utils.strip_html = lambda value: value
			self.assertEqual(module._last_message("QR-1"), "Answer sent")
			ROWS.append(Record(name="M4", actor="staff@example.com", creation="2026-11-01 12:00", body="Internal only", visibility="Internal"))
			try:
				self.assertEqual(module._last_message("QR-1"), "Answer sent")
			finally:
				ROWS.pop()

	def test_notifications_never_point_a_dealer_at_an_internal_note(self):
		conversations = types.SimpleNamespace(has_permission=MagicMock(return_value=True), is_staff=MagicMock(return_value=True))
		with load_service(ROOT + ".portal.outbox", {ROOT + ".portal.conversations": conversations}) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(doctype="ilL-Portal-Message", visibility="Internal", reference_type="Issue", reference_name="I-1", actor="staff@example.com")
			event = Record(reference_type="ilL-Portal-Message", reference_name="M2")
			self.assertFalse(module.reference_access(event, "buyer@example.com"))

	def test_every_message_reader_is_reviewed(self):
		root = APP.parent
		readers = set()
		for source in APP.rglob("*.py"):
			relative = source.relative_to(root).as_posix()
			if source.name.startswith("test_") or "/doctype/ill_portal_message/" in relative or "/patches/" in relative:
				continue
			if re.search(r"ilL-Portal-Message", source.read_text(encoding="utf-8", errors="ignore")):
				readers.add(relative)
		self.assertEqual(readers, REVIEWED_READERS)


class DeskComposer(unittest.TestCase):
	def test_staff_composer_defaults_to_internal_with_a_separate_dealer_button(self):
		source = (APP / "public/js/portal_conversation.js").read_text(encoding="utf-8")
		self.assertIn("visibility.value = 'Internal';", source)
		self.assertIn("__('Send to dealer')", source)
		self.assertIn("__('The dealer will see this message.')", source)
		self.assertIn("if (!staffView) audience = 'Customer';", source)


if __name__ == "__main__":
	unittest.main()
