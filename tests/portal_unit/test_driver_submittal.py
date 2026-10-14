"""Driver Template documents work for both configured and fixture-selected supply lines."""

import io
import json
import types
import unittest
from unittest.mock import MagicMock

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, TextStringObject
from test_driver_configuration import driver_module
from test_packets import pdf_bytes
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.portal.packet_manifest import assemble_manifest


def form_pdf(fields):
	"""A real fillable master, so field values and per-document flattening are exercised."""
	writer = PdfWriter()
	page = writer.add_blank_page(width=612, height=792)
	font = writer._add_object(
		DictionaryObject(
			{
				NameObject("/Type"): NameObject("/Font"),
				NameObject("/Subtype"): NameObject("/Type1"),
				NameObject("/BaseFont"): NameObject("/Helvetica"),
			}
		)
	)
	resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/Helv"): font})})
	widgets = ArrayObject()
	for index, field in enumerate(fields):
		widget = DictionaryObject(
			{
				NameObject("/Type"): NameObject("/Annot"),
				NameObject("/Subtype"): NameObject("/Widget"),
				NameObject("/FT"): NameObject("/Tx"),
				NameObject("/T"): TextStringObject(field),
				NameObject("/V"): TextStringObject(""),
				NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
				NameObject("/Rect"): ArrayObject(
					[FloatObject(n) for n in (20, 740 - index * 30, 590, 765 - index * 30)]
				),
			}
		)
		widgets.append(writer._add_object(widget))
	page[NameObject("/Annots")] = widgets
	page[NameObject("/Resources")] = resources
	writer._root_object[NameObject("/AcroForm")] = writer._add_object(
		DictionaryObject(
			{
				NameObject("/Fields"): widgets,
				NameObject("/DR"): resources,
				NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
			}
		)
	)
	stream = io.BytesIO()
	writer.write(stream)
	return stream.getvalue()


class DriverSubmittal(unittest.TestCase):
	def setUp(self):
		self.variant = Record(
			name="row100",
			parent="DRV",
			driver_spec="SPEC-100",
			item=None,
			wattage=100,
			voltage_output="24V",
			is_active=1,
			is_default=0,
		)
		self.template = Record(
			doctype="ilL-Driver-Template",
			name="DRV",
			spec_submittal_template="/files/master.pdf",
			spec_sheet="/files/driver-sheet.pdf",
			variants=[Record(name="row60", driver_spec="SPEC-60", is_active=1, is_default=1), self.variant],
		)
		self.line = Record(
			name="PS-ROW",
			line_key="PS-KEY",
			line_id="L1",
			idx=2,
			qty=4,
			location="Lobby",
			notes=None,
			manufacturer_type="ACCESSORY",
			accessory_item="ITEM-100",
			power_supply_for_line="FIXTURE-KEY",
			parent="S",
			parenttype="ilL-Project-Fixture-Schedule",
		)
		self.schedule = Record(name="S", lines=[self.line], ill_project="P")
		self.project = Record(project_name="Project Alpha", location="Building A")
		self.mappings = [
			{
				"pdf_field_name": "watts",
				"source_doctype": "ilL-Spec-Driver",
				"source_field": "max_wattage",
				"suffix": " W",
			},
			{"pdf_field_name": "project", "source_doctype": "ilL-Project", "source_field": "project_name"},
			{
				"pdf_field_name": "fixture",
				"source_doctype": "ilL-Child-Fixture-Schedule-Line",
				"source_field": "line_id",
			},
			{
				"pdf_field_name": "location",
				"source_doctype": "ilL-Child-Fixture-Schedule-Line",
				"source_field": "location",
			},
			{
				"pdf_field_name": "part",
				"source_doctype": "ilL-Driver-Template",
				"source_field": "name",
				"webflow_field": "part_number",
			},
		]
		self.master = form_pdf([row["pdf_field_name"] for row in self.mappings])
		self.saved_content = {}
		self.saved = MagicMock(side_effect=self.save_file)
		self.records = {
			("ilL-Driver-Template", "DRV"): self.template,
			("ilL-Spec-Driver", "SPEC-100"): Record(name="SPEC-100", item="ITEM-100", max_wattage=100),
			("ilL-Spec-Driver", "SPEC-60"): Record(name="SPEC-60", item="ITEM-60", max_wattage=60),
			("ilL-Child-Fixture-Schedule-Line", "PS-ROW"): self.line,
			("ilL-Project-Fixture-Schedule", "S"): self.schedule,
			("ilL-Project", "P"): self.project,
		}
		self.candidates = [self.variant]

	def save_file(self, filename, content, doctype, name, **kwargs):
		url = f"/private/files/{filename}"
		self.saved_content[url] = content
		return Record(name="GENERATED", file_url=url)

	def get_all(self, doctype, **kwargs):
		if doctype == "ilL-Spec-Driver":
			return ["SPEC-100"] if kwargs["filters"]["item"] == "ITEM-100" else []
		if doctype == "ilL-Child-Driver-Template-Variant":
			filters = kwargs["filters"]
			return [
				row
				for row in self.candidates
				if row.driver_spec in filters["driver_spec"][1]
				and (not filters.get("parent") or row.parent == filters["parent"])
			]
		if doctype == "ilL-Driver-Submittal-Mapping":
			return self.mappings
		return []

	def get_value(self, doctype, name, field, **kwargs):
		if doctype == "ilL-Item-Literature":
			return None
		if doctype == "ilL-Configured-Fixture":
			return "LINEAR-PART"
		record = self.records.get((doctype, name))
		return record.get(field) if record else None

	def modules(self):
		return {
			ROOT + ".api.exports": types.SimpleNamespace(_save_file_ignore_permissions=self.saved),
			ROOT + ".portal.access": types.SimpleNamespace(can_read_schedule=MagicMock(return_value=True)),
		}

	def configure(self, pdf, frappe):
		frappe.get_doc.side_effect = lambda doctype, name: self.records[(doctype, name)]
		frappe.get_all.side_effect = self.get_all
		frappe.db.get_value.side_effect = self.get_value
		frappe.log_error = MagicMock()
		pdf._get_linked_webflow_product = MagicMock(return_value=None)
		pdf._get_file_doc_by_url = MagicMock(
			return_value=Record(name="MASTER", get_content=lambda: self.master)
		)

	def gather(self, *lines):
		with (
			driver_module() as (helpers, _),
			load_service(
				ROOT + ".api.spec_submittal",
				{**self.modules(), ROOT + ".portal.driver_configuration": helpers},
			) as (pdf, frappe),
		):
			self.configure(pdf, frappe)
			pdf.generate_filled_submittal = MagicMock(
				return_value={"success": True, "file_url": "/files/fixture.pdf"}
			)
			with load_service(
				ROOT + ".portal.packets",
				{
					ROOT + ".api.spec_submittal": pdf,
					ROOT + ".portal.driver_configuration": helpers,
					ROOT + ".portal.build_documents": types.SimpleNamespace(generate_group=MagicMock()),
					ROOT + ".portal.line_documents": types.SimpleNamespace(active=lambda *args: []),
				},
			) as (packets, packet_frappe):
				packet_frappe.db.get_value.side_effect = self.get_value
				warnings = []
				entries = packets.gather(Record(name="S", lines=list(lines or [self.line])), warnings)
				return entries, warnings

	def test_included_and_standalone_supplies_fill_the_exact_variant_with_schedule_values(self):
		for standalone in (False, True):
			with self.subTest(standalone=standalone):
				if standalone:
					self.line.update(
						driver_template="DRV",
						variant_selections=json.dumps(
							{
								"product_category": "Driver",
								"variant_name": "row100",
								"part_number": "SPEC-100",
							}
						),
					)
				entries, warnings = self.gather()
				self.assertEqual(entries[0]["source_kind"], "filled_submittal", warnings)
				self.assertEqual(entries[0]["build"], {"doctype": "ilL-Driver-Template", "name": "DRV"})
				reader = PdfReader(io.BytesIO(self.saved_content[entries[0]["spec_document_url"]]))
				text = reader.pages[0].extract_text()
				for value in ("100 W", "Project Alpha", "L1", "Lobby", "SPEC-100"):
					self.assertIn(value, text)
				self.assertNotIn("60 W", text)
				self.assertFalse(reader.get_fields(), "Generated driver form fields must be flattened")
				self.assertEqual(entries[0]["provenance"]["build"]["item"], "ITEM-100")

	def test_fixture_and_its_included_supply_both_reach_the_packet_manifest(self):
		fixture = Record(
			self.line,
			name="FIXTURE-ROW",
			line_key="FIXTURE-KEY",
			idx=1,
			manufacturer_type="ILLUMENATE",
			configured_fixture="CF",
			accessory_item=None,
		)
		entries, warnings = self.gather(fixture, self.line)
		manifest, parts, errors = assemble_manifest(
			entries, lambda url: (self.saved_content.get(url) or pdf_bytes(), "product.pdf")
		)
		self.assertEqual(errors, [], warnings)
		self.assertEqual([entry["status"] for entry in manifest], ["included", "included"])
		self.assertEqual(len(parts), 2)
		self.assertEqual([entry["quantity"] for entry in manifest], [4, 4])

	def test_normal_full_and_partial_packet_requests_all_include_driver_documents(self):
		self.schedule.update(doctype="ilL-Project-Fixture-Schedule", modified="revision")
		self.records[("ilL-Export-Job", "JOB")] = Record(name="JOB")
		self.template["set"] = self.template.__setitem__
		stubs = self.modules()
		exports = stubs[ROOT + ".api.exports"]
		exports._check_schedule_access = lambda name: (True, None)
		exports._update_export_job_status = MagicMock()
		exports._get_schedule_data = MagicMock(return_value={})
		exports._generate_pdf_content = MagicMock(return_value="<html>Schedule</html>")
		stubs.update(
			{
				ROOT + ".portal.quotes": types.SimpleNamespace(_snapshot=lambda schedule: {}),
				ROOT + ".portal.packet_jobs": types.SimpleNamespace(
					InterruptedPacket=type("InterruptedPacket", (Exception,), {}),
					checkpoint=MagicMock(),
					lock_running=MagicMock(),
				),
				ROOT + ".portal.build_documents": types.SimpleNamespace(generate_group=MagicMock()),
				ROOT + ".portal.line_documents": types.SimpleNamespace(active=lambda *args: []),
				"frappe.utils.pdf": types.SimpleNamespace(get_pdf=lambda html: pdf_bytes()),
			}
		)

		def source_file(url, *args):
			content = self.saved_content.get(url)
			if content is None:
				content = self.master if url == "/files/master.pdf" else pdf_bytes(text="DRIVER-SHEET")
			return Record(
				name="SOURCE",
				file_name="source.pdf",
				is_private=0,
				get_content=lambda: content,
				is_downloadable=lambda: True,
			)

		with (
			driver_module() as (helpers, _),
			load_service(
				ROOT + ".api.spec_submittal", {**stubs, ROOT + ".portal.driver_configuration": helpers}
			) as (pdf, frappe),
		):
			self.configure(pdf, frappe)
			pdf._get_file_doc_by_url = source_file
			frappe.get_traceback = MagicMock(return_value="traceback")
			with load_service(
				ROOT + ".portal.packets",
				{
					**stubs,
					ROOT + ".api.spec_submittal": pdf,
					ROOT + ".portal.driver_configuration": helpers,
				},
			) as (packets, _):
				# Both services share one Frappe request and its packet-job flag in production.
				packets.frappe = frappe
				for standalone in (False, True):
					if standalone:
						self.line.update(
							driver_template="DRV",
							variant_selections=json.dumps(
								{
									"product_category": "Driver",
									"variant_name": "row100",
									"part_number": "SPEC-100",
								}
							),
						)
					for export_type in ("SPEC_SUBMITTAL", "SPEC_SUBMITTAL_FULL"):
						for allow_partial in (False, True):
							with self.subTest(
								standalone=standalone, export_type=export_type, allow_partial=allow_partial
							):
								result = packets.generate(
									"S",
									export_type,
									include_cover=False,
									job_name="JOB",
									allow_partial=allow_partial,
								)
								self.assertTrue(result["success"], result)
								self.assertEqual(result["status"], "COMPLETE")
								self.assertTrue(
									all(entry["status"] == "included" for entry in result["manifest"])
								)
								self.assertEqual(
									len(result["manifest"]), 2 if export_type.endswith("FULL") else 1
								)
								reader = PdfReader(io.BytesIO(self.saved_content[result["file_url"]]))
								text = "\n".join(page.extract_text() for page in reader.pages)
								self.assertIn("100 W", text)
								if export_type.endswith("FULL"):
									self.assertIn("DRIVER-SHEET", text)

	def test_both_supply_paths_use_the_template_spec_sheet_when_no_mappings_exist(self):
		self.mappings = []
		self.template["spec_submittal_template"] = None
		for standalone in (False, True):
			with self.subTest(standalone=standalone):
				if standalone:
					self.line.update(
						driver_template="DRV",
						variant_selections=json.dumps(
							{
								"product_category": "Driver",
								"variant_name": "row100",
								"part_number": "SPEC-100",
							}
						),
					)
				entries, warnings = self.gather()
				self.assertEqual(entries[0]["spec_document_url"], "/files/driver-sheet.pdf")
				self.assertEqual(entries[0]["source_kind"], "template_spec_sheet")
				self.assertIn("No field mappings", warnings[-1])
				self.assertEqual(entries[0]["warnings"], [warnings[-1]])
				_manifest, parts, errors = assemble_manifest(entries, lambda url: (pdf_bytes(), "sheet.pdf"))
				self.assertFalse(errors)
				self.assertEqual(len(parts), 1)
		self.saved.assert_not_called()

	def test_wrong_pdf_field_mapping_uses_template_sheet_and_keeps_the_reason(self):
		self.mappings = [
			{"pdf_field_name": "missing", "source_doctype": "ilL-Spec-Driver", "source_field": "max_wattage"}
		]
		entries, warnings = self.gather()
		self.assertEqual(entries[0]["source_kind"], "template_spec_sheet")
		self.assertIn("none of the 1 mapped field(s) exist", warnings[-1])
		self.saved.assert_not_called()

	def test_missing_and_wrong_saved_variants_never_fall_back_to_the_default_supply(self):
		for variant in ("deleted-row", "row60"):
			with self.subTest(variant=variant):
				self.line.update(
					driver_template="DRV",
					variant_selections=json.dumps(
						{
							"product_category": "Driver",
							"variant_name": variant,
						}
					),
				)
				entries, warnings = self.gather()
				self.assertEqual(entries[0]["source_kind"], "template_spec_sheet", warnings)
		self.saved.assert_not_called()

	def test_ambiguous_item_associations_report_a_failure_instead_of_choosing_a_supply(self):
		self.candidates.append(Record(self.variant, name="another-row", parent="OTHER-DRV"))
		entries, warnings = self.gather()
		self.assertIn("matches multiple template variants", warnings[0])
		_manifest, _parts, errors = assemble_manifest(entries, lambda url: (pdf_bytes(), "sheet.pdf"))
		self.assertIn("Required source document is missing", errors[0])
		self.saved.assert_not_called()

	def test_ordinary_accessory_still_uses_approved_item_literature(self):
		self.line["accessory_item"] = "BRACKET"
		get_value = self.get_value
		self.get_value = lambda doctype, name, field, **kwargs: (
			Record(document="BRACKET-FILE", no_document_required=0, sha256=None)
			if doctype == "ilL-Item-Literature"
			else "/files/bracket.pdf"
			if doctype == "File"
			else get_value(doctype, name, field, **kwargs)
		)
		entries, _warnings = self.gather()
		self.assertEqual(entries[0]["source_kind"], "approved_item_literature")
		self.assertEqual(entries[0]["spec_document_url"], "/files/bracket.pdf")
		self.saved.assert_not_called()

	def test_schedule_access_is_checked_before_driver_documents_are_resolved(self):
		stubs = self.modules()
		stubs[ROOT + ".portal.access"].can_read_schedule.return_value = False
		with load_service(ROOT + ".api.spec_submittal", stubs) as (pdf, frappe):
			self.configure(pdf, frappe)
			with self.assertRaisesRegex(PermissionError, "Schedule access denied"):
				pdf.generate_filled_driver_line_submittal("DRV", schedule_line=self.line.name)
			frappe.get_all.assert_not_called()
		self.saved.assert_not_called()


if __name__ == "__main__":
	unittest.main()
