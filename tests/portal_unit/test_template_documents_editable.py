"""Templates' Other Documents are where document files are added (owner, 2026-11-25).

A Customize Form setting made the File column of ilL-Child-Webflow-Document read-only, to stop
files being added on the Webflow Product, which takes its documents from the template. The
template shares that child table, so its Other Documents was locked too. The patch removes the
setting; the Webflow Product form keeps its File column read-only in its own script.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import load_service

APP = Path(__file__).resolve().parents[2] / "illumenate_lighting"
PATCH = "illumenate_lighting.patches.unlock_template_document_files"


class UnlockTemplateDocumentFiles(unittest.TestCase):
	def test_removes_only_the_read_only_setting_on_the_file_column(self):
		with load_service(PATCH) as (patch, frappe):
			frappe.get_all = MagicMock(return_value=["ilL-Child-Webflow-Document-document_file-read_only"])
			frappe.delete_doc = MagicMock()
			frappe.clear_cache = MagicMock()
			patch.execute()
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(
				filters,
				{
					"doc_type": "ilL-Child-Webflow-Document",
					"field_name": "document_file",
					"property": "read_only",
				},
			)
			frappe.delete_doc.assert_called_once_with(
				"Property Setter",
				"ilL-Child-Webflow-Document-document_file-read_only",
				ignore_permissions=True,
				force=True,
			)
			frappe.clear_cache.assert_any_call(doctype="ilL-Child-Webflow-Document")

	def test_nothing_to_remove_is_fine(self):
		with load_service(PATCH) as (patch, frappe):
			frappe.get_all = MagicMock(return_value=[])
			frappe.delete_doc = MagicMock()
			frappe.clear_cache = MagicMock()
			patch.execute()
			frappe.delete_doc.assert_not_called()

	def test_patch_is_listed(self):
		patches = (APP / "patches.txt").read_text().split()
		self.assertIn(PATCH, patches)

	def test_the_file_column_is_editable_in_the_doctype(self):
		doctype = json.loads(
			(
				APP / "illumenate_lighting/doctype/ill_child_webflow_document/ill_child_webflow_document.json"
			).read_text()
		)
		field = next(f for f in doctype["fields"] if f["fieldname"] == "document_file")
		self.assertFalse(field.get("read_only"))

	def test_the_webflow_product_form_keeps_its_file_column_read_only(self):
		script = (APP / "illumenate_lighting/doctype/ill_webflow_product/ill_webflow_product.js").read_text()
		self.assertIn("update_docfield_property('document_file', 'read_only', 1)", script)


if __name__ == "__main__":
	unittest.main()
