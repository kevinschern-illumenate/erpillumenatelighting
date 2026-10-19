"""Spec submittal readiness: missing attachments, and a dry run that grades every field mapping."""

import io
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

READINESS = ROOT + ".api.submittal_readiness"
PDF_FIELDS = ("fixture_type", "lumens", "finish", "price", "notes")


def fillable_pdf(names=PDF_FIELDS):
	from reportlab.pdfgen import canvas as pdf_canvas

	buffer = io.BytesIO()
	canvas = pdf_canvas.Canvas(buffer)
	for index, name in enumerate(names):
		canvas.acroForm.textfield(name=name, x=50, y=750 - index * 40, width=300, height=24)
	canvas.showPage()
	canvas.save()
	return buffer.getvalue()


class Flags(dict):
	"""frappe.flags: attribute writes are keys."""

	__getattr__ = dict.get
	__setattr__ = dict.__setitem__


def mapping(field, doctype, source, **extra):
	return {"pdf_field_name": field, "source_doctype": doctype, "source_field": source, **extra}


CF = "ilL-Configured-Fixture"
LINE = "ilL-Child-Fixture-Schedule-Line"
SCHEMA = {CF: {"lumens", "finish_code", "unit_price"}, LINE: {"line_id"}}


def has_field(doctype, field):
	return field in SCHEMA.get(doctype, ())


class Rules(unittest.TestCase):
	def evaluate(self, mappings, captured, **kwargs):
		with load_service(READINESS) as (module, _frappe):
			return module.evaluate(mappings, captured, has_field, **kwargs)

	def test_each_failure_names_the_mapping_to_fix(self):
		result = self.evaluate(
			[
				mapping("lumens", CF, "lumens"),
				mapping("lumen", CF, "lumens"),
				mapping("finish", CF, "finsh_code"),
				mapping("fixture_type", LINE, "line_id", required_value=1),
				mapping("notes", CF, "finish_code"),
				mapping("", CF, "lumens"),
			],
			{
				"pdf_fields": list(PDF_FIELDS),
				"field_values": {"lumens": "1200", "lumen": "1200", "notes": ""},
			},
		)
		rows = {row["pdf_field_name"]: row for row in result["mappings"]}
		self.assertEqual(rows["lumens"]["status"], "ok")
		self.assertEqual(rows["lumen"]["problems"], ["The PDF has no field named lumen"])
		self.assertEqual(rows["finish"]["problems"], [f"{CF} has no field finsh_code"])
		self.assertEqual(rows["fixture_type"]["problems"], ["Required value is blank for this sample"])
		self.assertEqual(rows["notes"]["status"], "blank")
		self.assertIn("Enter the PDF field name", rows[""]["problems"])
		self.assertEqual(result["failures"], 4)
		self.assertEqual(result["blanks"], 1)
		self.assertEqual(result["unmapped_pdf_fields"], ["price"])

	def test_duplicates_webflow_and_commercial_sources_are_notes(self):
		result = self.evaluate(
			[
				mapping("lumens", CF, "lumens"),
				mapping("lumens", CF, "lumens", webflow_field="project_name"),
				mapping("price", CF, "unit_price"),
			],
			{"pdf_fields": list(PDF_FIELDS), "field_values": {"lumens": "1200", "price": ""}},
			blocked=lambda doctype, field: "price" in field,
		)
		lumens, webflow, price = result["mappings"]
		self.assertIn("Mapped 2 times; the last mapping is used", lumens["notes"])
		self.assertIn("Uses the project_name parameter when one is supplied", webflow["notes"])
		self.assertEqual(price["status"], "ok")
		self.assertIn("Commercial value; left blank in packets and downloads", price["notes"])

	def test_without_a_run_only_the_schema_is_checked(self):
		result = self.evaluate([mapping("lumens", CF, "nope"), mapping("finish", CF, "finish_code")], {})
		self.assertEqual([row["status"] for row in result["mappings"]], ["fail", "ok"])
		self.assertEqual(result["unmapped_pdf_fields"], [])

	def test_template_needs_both_attachments_and_mappings(self):
		with load_service(READINESS) as (module, _frappe):
			ready = module.template_issues(
				{"spec_submittal_template": "/files/s.pdf", "spec_sheet": "/files/sheet.pdf"},
				3,
				{"/files/s.pdf", "/files/sheet.pdf"},
			)
			bare = module.template_issues({}, 0, set())
			sheet_only = module.template_issues({"spec_sheet": "/files/sheet.pdf"}, 2, {"/files/sheet.pdf"})
			lost = module.template_issues(
				{"spec_submittal_template": "/files/gone.pdf", "spec_sheet": "/files/sheet.pdf"},
				2,
				{"/files/sheet.pdf"},
			)
		self.assertEqual(ready, {"status": "ready", "missing": [], "notes": []})
		self.assertEqual(bare["missing"], ["spec_submittal_template", "spec_sheet", "field_mappings"])
		self.assertEqual(sheet_only["missing"], ["spec_submittal_template"])
		self.assertIn(
			"Submittals fill the spec sheet until a spec submittal template is attached", sheet_only["notes"]
		)
		self.assertEqual(lost["missing"], ["spec_submittal_template"])
		self.assertIn("/files/gone.pdf", lost["notes"][0])

	def test_report_counts_missing_attachments(self):
		with load_service(READINESS) as (module, _frappe):
			summary = module.summarize(
				[
					{
						"kind": "Fixture",
						"status": "incomplete",
						"missing": ["spec_submittal_template", "spec_sheet"],
					},
					{"kind": "Fixture", "status": "ready", "missing": []},
					{"kind": "Driver", "status": "incomplete", "missing": ["spec_sheet"]},
				]
			)
		self.assertEqual(summary["incomplete"], 2)
		self.assertEqual(summary["no_submittal_template"], 1)
		self.assertEqual(summary["no_spec_sheet"], 2)
		self.assertEqual(summary["by_kind"]["Fixture"], {"total": 2, "incomplete": 1})


class DryRun(unittest.TestCase):
	"""A configured fixture goes through the real generator and PDF filler; nothing is saved."""

	def run_fixture(self, mappings):
		pdf_bytes = fillable_pdf()
		saved = MagicMock(return_value=Record(name=None, file_url=None))
		stubs = {
			ROOT + ".api.exports": types.SimpleNamespace(_save_file_ignore_permissions=saved),
			ROOT + ".api.configuration_contract": types.SimpleNamespace(fingerprint=lambda value: "hash"),
			ROOT + ".api.engineering_sources": types.SimpleNamespace(resolve=lambda *args: (False, None)),
		}
		configured = Record(name="CF-1", fixture_template="TPL", lumens=1200, finish_code="", unit_price=99)
		configured.save = MagicMock()
		line = Record(name="L1", line_id="A1")
		records = {
			(CF, "CF-1"): configured,
			("ilL-Fixture-Template", "TPL"): Record(
				doctype="ilL-Fixture-Template",
				name="TPL",
				spec_submittal_template="/files/sub.pdf",
				spec_sheet=None,
			),
			("ilL-Project-Fixture-Schedule", "SCH-1"): Record(name="SCH-1", lines=[line], ill_project=None),
		}
		with load_service(ROOT + ".api.spec_submittal", stubs) as (pdf, pdf_frappe):
			pdf_frappe.flags = Flags()
			pdf_frappe.get_doc.side_effect = lambda doctype, name: records[(doctype, name)]
			pdf_frappe.get_all.return_value = mappings
			pdf_frappe.db.get_value.return_value = None
			pdf_frappe.log_error = MagicMock()
			pdf._get_file_doc_by_url = lambda url, warnings=None: Record(
				name="F1", get_content=lambda: pdf_bytes
			)
			model = types.SimpleNamespace(default_fields=("name", "owner"))
			with load_service(READINESS, {ROOT + ".api.spec_submittal": pdf, "frappe.model": model}) as (
				module,
				frappe,
			):
				frappe.flags = pdf_frappe.flags
				frappe.get_doc.side_effect = pdf_frappe.get_doc.side_effect
				frappe.get_all.side_effect = lambda doctype, **kwargs: ["L1"] if doctype == LINE else mappings
				frappe.db.get_value.side_effect = lambda doctype, name, field: "SCH-1"
				frappe.get_meta = lambda doctype: Record(has_field=lambda field: has_field(doctype, field))
				result = module.run_dry_run("Fixture", "TPL", "CF-1")
				flag_after = frappe.flags.get("ill_submittal_dry_run")
		return result, saved, configured, flag_after

	def test_failing_and_blank_mappings_are_reported_from_the_real_fill(self):
		result, _saved, configured, flag_after = self.run_fixture(
			[
				mapping("fixture_type", LINE, "line_id"),
				mapping("lumens", CF, "lumens", suffix=" lm"),
				mapping("finish", CF, "finish_code", required_value=1),
				mapping("price", CF, "unit_price"),
				mapping("beam", CF, "lumens"),
				mapping("notes", CF, "not_a_field"),
			]
		)
		self.assertTrue(result["success"], result)
		self.assertEqual(result["pdf_template"], "/files/sub.pdf")
		rows = {row["pdf_field_name"]: row for row in result["mappings"]}
		self.assertEqual((rows["fixture_type"]["status"], rows["fixture_type"]["value"]), ("ok", "A1"))
		self.assertEqual(rows["lumens"]["value"], "1200 lm")
		self.assertEqual(rows["finish"]["problems"], ["Required value is blank for this sample"])
		# Commercial values never leave the dry run, as in packets.
		self.assertEqual(rows["price"]["value"], "")
		self.assertIn("Commercial value; left blank in packets and downloads", rows["price"]["notes"])
		self.assertEqual(rows["beam"]["problems"], ["The PDF has no field named beam"])
		self.assertEqual(rows["notes"]["problems"], [f"{CF} has no field not_a_field"])
		self.assertEqual(result["failures"], 3)
		self.assertTrue(any("beam" in warning for warning in result["warnings"]))
		configured.save.assert_not_called()
		self.assertIsNone(flag_after)

	def test_a_pdf_matching_no_mapping_fails_generation(self):
		result, saved, _configured, _flag = self.run_fixture([mapping("wrong", CF, "lumens")])
		self.assertFalse(result["success"])
		self.assertEqual(result["mappings"][0]["problems"], ["The PDF has no field named wrong"])
		self.assertEqual(result["unmapped_pdf_fields"], sorted(PDF_FIELDS))
		saved.assert_not_called()


class DryRunKeepsNothing(unittest.TestCase):
	def test_generated_file_is_not_saved_during_a_dry_run(self):
		file_manager = types.ModuleType("frappe.utils.file_manager")
		file_manager.save_file = MagicMock()
		with load_service(ROOT + ".api.exports", {file_manager.__name__: file_manager}) as (module, frappe):
			frappe._dict = Record
			frappe.flags = Flags(ill_submittal_dry_run={})
			result = module._save_file_ignore_permissions("x.pdf", b"%PDF", CF, "CF-1")
		self.assertIsNone(result.file_url)
		file_manager.save_file.assert_not_called()


if __name__ == "__main__":
	unittest.main()
