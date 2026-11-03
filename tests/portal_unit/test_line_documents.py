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

	def test_missing_required_value_warns_without_a_stray_prefix(self):
		mapping = {
			"pdf_field_name": "Length",
			"source_doctype": "Build",
			"source_field": "length",
			"required_value": 1,
		}
		values, warnings = {}, []
		# A missing required value warns and leaves the field blank instead of stopping the packet.
		set_value(values, mapping, None, "Length: ", warnings)
		self.assertEqual(values, {"Length": ""})
		self.assertIn("Required value is missing: Build.length", warnings.pop())
		values.clear()
		set_value(values, mapping, 0, "0 mm", warnings)
		self.assertEqual(values["Length"], "0 mm")
		# Authoring mistakes warn instead of blocking the submittal; preflight still reports them.
		set_value(values, mapping, 1, "1 mm", warnings)
		set_value(values, {**mapping, "pdf_field_name": None}, 2, "2 mm", warnings)
		self.assertEqual(values, {"Length": "1 mm"})
		self.assertIn("mapped more than once", warnings[0])
		self.assertIn("no PDF field name", warnings[1])
		self.assertTrue(check_mappings([mapping, mapping], {"Length": {}}))
		self.assertTrue(check_mappings([mapping], {"Other": {}}))


class DuplicateDetection(unittest.TestCase):
	"""Plan 4.8: the same bytes are reported, not stored twice on one line."""

	A, B = "a" * 64, "b" * 64

	def load(self, flag=True):
		configuration = types.SimpleNamespace(resolve_line=MagicMock(), schedule_context=MagicMock())
		flags = types.SimpleNamespace(upload_duplicate_check_enabled=MagicMock(return_value=flag))
		return load_service(
			ROOT + ".portal.line_documents",
			{ROOT + ".portal.configuration": configuration, ROOT + ".portal.site_flags": flags},
		)

	def schedule(self):
		return Record(
			name="S",
			doctype="ilL-Project-Fixture-Schedule",
			modified="now",
			lines=[
				Record(name="row1", line_key="L1", line_id="A1", idx=1),
				Record(name="row2", line_key="L2", line_id=None, idx=12),
			],
			save=MagicMock(),
		)

	def test_find_duplicates_labels_lines_and_filters_digests(self):
		with self.load() as (module, frappe):
			frappe.get_all.return_value = [
				Record(sha256=self.A, line_key="L2", file_name="photo.jpg"),
				Record(sha256=self.B, line_key="L1", file_name="spec.pdf"),
			]
			with (
				patch.object(module, "schedule_context", return_value=self.schedule()),
				patch.object(module, "resolve_line", return_value=Record(line_key="L1", name="row1")),
			):
				result = module.find_duplicates("S", "L1", f'["{self.A.upper()}", "nope", "{self.B}", "{self.A}"]')
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(filters["sha256"], ["in", [self.A, self.B]])
			self.assertEqual(filters["schedule"], "S")
			self.assertEqual(
				[(d["line_label"], d["same_line"]) for d in result["duplicates"]], [("12", False), ("A1", True)]
			)

	def test_find_duplicates_checks_access_first_and_honours_the_kill_switch(self):
		with self.load(flag=False) as (module, frappe):
			with patch.object(module, "schedule_context", side_effect=PermissionError("no")):
				with self.assertRaises(PermissionError):
					module.find_duplicates("S", None, f'["{self.A}"]')
			with patch.object(module, "schedule_context", return_value=self.schedule()):
				self.assertEqual(module.find_duplicates("S", None, f'["{self.A}"]')["duplicates"], [])
			frappe.get_all.assert_not_called()

	def test_bad_hash_payload_is_a_validation_error(self):
		with self.load() as (module, frappe):
			with patch.object(module, "schedule_context", return_value=self.schedule()):
				with self.assertRaisesRegex(ValueError, "JSON list"):
					module.find_duplicates("S", None, "{not json")
				many = [f"{i:064x}" for i in range(20)]
				self.assertEqual(len(module._digests(many)), module.MAX_DIGESTS)

	def attach(self, flag=True, primary=None):
		files = types.SimpleNamespace(
			finalize_files=MagicMock(
				return_value=[
					{"name": "F-new", "file_name": "copy.jpg", "file_url": "/private/files/copy.jpg", "sha256": self.A},
					{"name": "F-other", "file_name": "other.pdf", "file_url": "/private/files/other.pdf", "sha256": self.B},
				]
			)
		)
		media = types.SimpleNamespace(annotations=MagicMock(return_value={}))
		existing = [Record(name="D1", file="F-old", file_name="photo.jpg", sha256=self.A, is_primary=0)]
		with self.load(flag) as (module, frappe):
			with (
				patch.dict("sys.modules", {ROOT + ".portal.files": files, ROOT + ".portal.media": media}),
				patch.object(module, "schedule_context", return_value=self.schedule()),
				patch.object(
					module,
					"resolve_line",
					return_value=Record(line_key="L1", name="row1", manufacturer_type="OTHER"),
				),
				patch.object(module, "active", return_value=existing),
			):
				result = module.attach("S", "L1", '["F-new", "F-other"]', primary, "now")
			inserted = [call.args[0]["file"] for call in frappe.get_doc.call_args_list]
		return result, inserted

	def test_attach_skips_bytes_already_on_the_line_and_reports_them(self):
		result, inserted = self.attach()
		self.assertEqual(inserted, ["F-other"])
		self.assertEqual(
			result["duplicates"],
			[{"file_name": "copy.jpg", "existing_file_name": "photo.jpg", "line_label": "A1"}],
		)
		self.assertIn("documents", result)

	def test_attach_keeps_a_duplicate_chosen_as_primary_and_stores_all_when_switched_off(self):
		self.assertEqual(self.attach(primary="F-new")[1], ["F-new", "F-other"])
		result, inserted = self.attach(flag=False)
		self.assertEqual(inserted, ["F-new", "F-other"])
		self.assertEqual(result["duplicates"], [])
