"""Patch: the Tape/Neon template's custom_documents rows move to other_documents."""

import unittest
from unittest.mock import MagicMock

from test_services import load_service

PATCH = "illumenate_lighting.patches.move_tape_custom_documents_to_other_documents"


class TapeDocumentsPatch(unittest.TestCase):
	def run_patch(self, custom_field):
		with load_service(PATCH) as (module, frappe):
			frappe.db.get_value.return_value = custom_field
			frappe.delete_doc = MagicMock()
			frappe.clear_cache = MagicMock()
			module.execute()
			return frappe

	def test_rows_move_and_the_custom_field_is_deleted(self):
		frappe = self.run_patch("ilL-Tape-Neon-Template-custom_documents")
		sql, args = frappe.db.sql.call_args.args
		self.assertIn("set parentfield = 'other_documents'", sql)
		self.assertIn("parentfield = 'custom_documents'", sql)
		self.assertEqual(args, ("ilL-Tape-Neon-Template",))
		frappe.delete_doc.assert_called_once_with(
			"Custom Field", "ilL-Tape-Neon-Template-custom_documents", ignore_permissions=True, force=True
		)

	def test_a_site_without_the_custom_field_is_left_alone(self):
		frappe = self.run_patch(None)
		frappe.db.sql.assert_not_called()
		frappe.delete_doc.assert_not_called()


if __name__ == "__main__":
	unittest.main()
