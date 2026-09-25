import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.portal.pdf_mapping import check_mappings, set_value


class LineDocuments(unittest.TestCase):
	def dependencies(self):
		return {
			ROOT + ".portal.configuration": types.SimpleNamespace(
				resolve_line=MagicMock(), schedule_context=MagicMock()
			)
		}

	def test_duplicate_gets_independent_associations_without_reassigning_source(self):
		with load_service(ROOT + ".portal.line_documents", self.dependencies()) as (module, frappe):
			frappe.get_all.return_value = [
				Record(
					name="SOURCE",
					file="F",
					file_name="a.pdf",
					sha256="hash",
					title="Specification",
					is_primary=1,
				)
			]
			doc = MagicMock()
			frappe.get_doc.return_value = doc
			module.clone("OLD", Record(line_key="L1"), "NEW", Record(line_key="L2"))
			data = frappe.get_doc.call_args.args[0]
			self.assertEqual(data["schedule"], "NEW")
			self.assertEqual(data["line_key"], "L2")
			self.assertEqual(data["copied_from"], "SOURCE")
			self.assertEqual(data["file"], "F")
			frappe.db.set_value.assert_not_called()

	def test_failed_replacement_does_not_retire_previous_specification(self):
		files = types.SimpleNamespace(finalize_files=MagicMock(side_effect=ValueError("corrupt")))
		with load_service(
			ROOT + ".portal.line_documents", {**self.dependencies(), ROOT + ".portal.files": files}
		) as (module, frappe):
			schedule = Record(name="S", doctype="ilL-Project-Fixture-Schedule", modified="now")
			with (
				patch.object(module, "schedule_context", return_value=schedule),
				patch.object(module, "resolve_line", return_value=Record(manufacturer_type="OTHER")),
			):
				with self.assertRaisesRegex(ValueError, "corrupt"):
					module.attach("S", "L", ["F"], "F", "now")
			frappe.db.set_value.assert_not_called()

	def test_required_mappings_fail_before_prefix_hides_missing_value(self):
		mapping = {
			"pdf_field_name": "Length",
			"source_doctype": "Build",
			"source_field": "length",
			"required_value": 1,
		}
		with self.assertRaisesRegex(ValueError, "Required engineering"):
			set_value({}, mapping, None, "Length: ")
		values = {}
		set_value(values, mapping, 0, "0 mm")
		self.assertEqual(values["Length"], "0 mm")
		with self.assertRaisesRegex(ValueError, "exactly once"):
			set_value(values, mapping, 1, "1 mm")
		self.assertTrue(check_mappings([mapping, mapping], {"Length": {}}))
		self.assertTrue(check_mappings([mapping], {"Other": {}}))
