import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from test_configuration_save import Doc
from test_services import ROOT, Record, load_service


@contextmanager
def service():
	files = types.ModuleType(ROOT + ".portal.files")
	files._context_access = MagicMock(return_value=True)
	files.finalize_files = MagicMock(return_value=[])
	files.list_files = MagicMock(return_value=[])
	with (
		load_service(ROOT + ".api.build_artifacts") as (atomic, _),
		load_service(
			ROOT + ".portal.conversations", {files.__name__: files, ROOT + ".api.build_artifacts": atomic}
		) as (module, frappe),
	):
		atomic.frappe = frappe
		doc = Doc(doctype="Issue", name="ISSUE1", status="Open", raised_by="buyer@example.com", flags=Doc())
		doc.save = MagicMock()
		stored = {}

		def get_doc(value, name=None):
			if isinstance(value, str):
				return doc
			message = Doc(**value, flags=Doc(), name="MESSAGE1")
			message.insert = lambda **kwargs: stored.setdefault(message.request_key, message)
			return message

		frappe.get_doc.side_effect = get_doc
		frappe.db.get_value.side_effect = lambda dt, filters, *a, **k: stored.get(filters.get("request_key"))
		with (
			patch.object(module, "is_staff", return_value=False) as staff,
			patch.object(module, "_notify") as notify,
		):
			yield module, frappe, files, doc, stored, staff, notify


def args(**extra):
	return {
		"parent_type": "Issue",
		"parent_name": "ISSUE1",
		"body": "Please check this",
		"idempotency_key": "retry-1234",
		**extra,
	}


class Conversations(unittest.TestCase):
	def test_commercial_reply_returns_information_request_to_staff_without_approval(self):
		with service() as (module, _frappe, _files, doc, _stored, _staff, _notify):
			doc.doctype, doc.state = "ilL-Order-Intake", "INFORMATION_NEEDED"
			module._transition(doc, False, "REPLY", "Customer")
			self.assertEqual((doc.state, doc.ill_next_action_by), ("UNDER_REVIEW", "Staff"))
			with self.assertRaisesRegex(ValueError, "commercial review"):
				module._transition(doc, True, "RESOLVE", "Customer")
			doc.state = "APPROVED"
			with self.assertRaisesRegex(ValueError, "closed"):
				module._transition(doc, False, "REPLY", "Customer")

	def test_customer_cannot_create_internal_note_or_resolve(self):
		with service() as (module, _frappe, files, _doc, stored, _staff, _notify):
			for extra in ({"visibility": "Internal"}, {"action": "RESOLVE"}):
				with self.assertRaises(PermissionError):
					module.reply(**args(**extra))
			self.assertEqual(stored, {})
			files.finalize_files.assert_not_called()

	def test_retry_has_one_message_and_one_attachment_finalize(self):
		with service() as (module, _frappe, files, _doc, stored, _staff, _notify):
			module.reply(**args(file_ids=["FILE1"]))
			self.assertTrue(module.reply(**args(file_ids=["FILE1"]))["already_existed"])
			self.assertEqual(len(stored), 1)
			files.finalize_files.assert_called_once_with(
				["FILE1"], module.MESSAGE, "MESSAGE1", allow_unbound=True
			)
			with self.assertRaisesRegex(ValueError, "different content"):
				module.reply(**args(body="Changed message"))

	def test_retry_rechecks_parent_access_before_receipt(self):
		with service() as (module, _frappe, files, _doc, _stored, _staff, _notify):
			module.reply(**args())
			files._context_access.return_value = False
			with self.assertRaises(PermissionError):
				module.reply(**args())

	def test_internal_note_hidden_from_list_and_direct_access(self):
		with service() as (module, frappe, files, _doc, _stored, staff, _notify):
			frappe.get_all.return_value = []
			module.list_messages("Issue", "ISSUE1")
			self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["visibility"], "Customer")
			message = Record(reference_type="Issue", reference_name="ISSUE1", visibility="Internal")
			self.assertFalse(module.has_permission(message))
			staff.return_value = True
			self.assertTrue(module.has_permission(message))
			files._context_access.return_value = False
			self.assertFalse(module.has_permission(message))

	def test_closed_conversation_requires_staff_reopen_and_reason(self):
		with service() as (module, _frappe, _files, doc, _stored, staff, _notify):
			doc.status = "Resolved"
			with self.assertRaisesRegex(ValueError, "closed"):
				module.reply(**args())
			staff.return_value = True
			module.reply(**args(action="REOPEN"))
			self.assertEqual(doc.status, "Open")

	def test_failed_attachment_rolls_back_reply(self):
		with service() as (module, frappe, files, _doc, _stored, _staff, notify):
			files.finalize_files.side_effect = PermissionError("Revoked upload")
			with self.assertRaises(PermissionError):
				module.reply(**args(file_ids=["FILE1"]))
			frappe.db.rollback.assert_called_once()
			notify.assert_not_called()
