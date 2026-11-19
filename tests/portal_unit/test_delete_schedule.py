"""Health item 7: a schedule with configuration history refuses deletion with a dealer message."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class DeleteSchedule(unittest.TestCase):
	def call(self, delete_error=None):
		deps = {
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				has_permission=lambda *a: True
			),
		}
		with load_service(ROOT + ".api.portal", deps) as (api, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="S", status="DRAFT")
			frappe.local.request = Record(method="POST")
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="Traceback")
			frappe.utils.strip_html = lambda value: value
			frappe.local.message_log = [{"message": "earlier"}]
			error = delete_error(frappe) if delete_error else None

			def delete_doc(doctype, name):
				if error:
					# frappe.throw queues its text for the page's error dialog before raising.
					frappe.local.message_log.append({"message": str(error), "raise_exception": 1})
					raise error

			frappe.delete_doc = MagicMock(side_effect=delete_doc)
			return api.delete_schedule("S"), frappe

	def test_linked_receipts_return_a_friendly_message_without_an_error_log(self):
		result, frappe = self.call(
			lambda frappe: frappe.LinkExistsError(
				"Cannot delete or cancel because ilL-Project-Fixture-Schedule S is linked with "
				"ilL-Configuration-Receipt CR-0001"
			)
		)
		self.assertFalse(result["success"])
		self.assertEqual(
			result["error"],
			"This schedule has configuration history and can't be deleted. "
			"Archive its project or ask ilLumenate to remove it.",
		)
		self.assertNotIn("ilL-Configuration-Receipt", str(result))
		frappe.log_error.assert_not_called()
		frappe.db.rollback.assert_called_once_with()
		self.assertEqual(frappe.local.message_log, [{"message": "earlier"}])

	def test_a_draft_without_links_is_still_deleted(self):
		result, frappe = self.call()
		self.assertEqual(result, {"success": True})
		frappe.delete_doc.assert_called_once_with("ilL-Project-Fixture-Schedule", "S")

	def test_other_failures_are_still_logged(self):
		result, frappe = self.call(lambda frappe: RuntimeError("deadlock"))
		self.assertEqual(result["error_code"], "internal_error")
		frappe.log_error.assert_called_once()


if __name__ == "__main__":
	unittest.main()
