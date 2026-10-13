import hashlib
import io
import types
import unittest
from unittest.mock import MagicMock

from PIL import Image
from pypdf import PdfReader, PdfWriter
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.portal.packet_manifest import assemble_manifest


def pdf_bytes(pages=1, password=None, text=None):
	writer = PdfWriter()
	for _ in range(pages):
		page = writer.add_blank_page(width=612, height=792)
		if text:
			# A minimal text stream so the overlay is detectable on the merged page.
			from pypdf.generic import ContentStream, DictionaryObject, NameObject

			font = DictionaryObject(
				{
					NameObject("/Type"): NameObject("/Font"),
					NameObject("/Subtype"): NameObject("/Type1"),
					NameObject("/BaseFont"): NameObject("/Helvetica"),
				}
			)
			page[NameObject("/Resources")] = DictionaryObject(
				{NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
			)
			stream = ContentStream(None, writer)
			stream.set_data(f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode())
			page[NameObject("/Contents")] = writer._add_object(stream)
	if password:
		writer.encrypt(password)
	stream = io.BytesIO()
	writer.write(stream)
	return stream.getvalue()


def line(key, **values):
	return {
		"line_key": key,
		"line_id": "F1",
		"manufacturer_type": "OTHER",
		"qty": 1,
		"spec_document_url": "/private/files/source.pdf",
		**values,
	}


class PacketManifest(unittest.TestCase):
	def test_changed_approved_source_cannot_enter_packet(self):
		manifest, parts, errors = assemble_manifest(
			[line("one", expected_sha256="previous")], lambda _: (pdf_bytes(), "source.pdf")
		)
		self.assertFalse(parts)
		self.assertEqual(manifest[0]["status"], "failed")
		self.assertIn("after document approval", errors[0])

	def test_reference_document_does_not_replace_required_filled_spec(self):
		manifest, parts, errors = assemble_manifest(
			[
				line("configured", manufacturer_type="ILLUMENATE"),
				line("reference", manufacturer_type="ILLUMENATE", filled_required=False),
			],
			lambda _: (pdf_bytes(), "reference.pdf"),
		)
		self.assertEqual(len(parts), 1)
		self.assertEqual(manifest[0]["status"], "failed")
		self.assertTrue(errors)

	def test_repeated_designations_have_independent_page_ranges(self):
		content = pdf_bytes(2)
		manifest, parts, errors = assemble_manifest(
			[line("first"), line("second")], lambda _: (content, "source.pdf"), cover_pages=1
		)
		self.assertEqual(errors, [])
		self.assertEqual(len(parts), 2)
		self.assertEqual([(e["page_start"], e["page_end"]) for e in manifest], [(2, 3), (4, 5)])
		self.assertEqual(manifest[0]["sha256"], hashlib.sha256(content).hexdigest())

	def test_cover_does_not_hide_missing_required_source(self):
		manifest, parts, errors = assemble_manifest(
			[line("first", spec_document_url=None)],
			lambda _: self.fail("No source should be loaded"),
			cover_pages=2,
		)
		self.assertEqual(parts, [])
		self.assertEqual(manifest[0]["status"], "failed")
		self.assertEqual(len(errors), 2)

	def test_static_fallback_is_not_filled_success(self):
		_manifest, parts, errors = assemble_manifest(
			[line("first", manufacturer_type="ILLUMENATE")],
			lambda _: self.fail("Static fallback must not be loaded"),
		)
		self.assertFalse(parts)
		self.assertIn("filled submittal", errors[0])

	def test_failed_render_reports_its_reason_and_row(self):
		_manifest, _parts, errors = assemble_manifest(
			[
				line(
					"first",
					line_id=None,
					idx=3,
					manufacturer_type="ILLUMENATE",
					render_error="Failed to fill PDF form fields; PDF filling blocked: none of the 2 mapped field(s) exist",
				)
			],
			lambda _: self.fail("A failed render must not load a source"),
		)
		self.assertTrue(
			errors[0].startswith("Line Row 3 (first): The filled submittal could not be generated")
		)
		self.assertIn("none of the 2 mapped field(s) exist", errors[0])

	def test_corrupt_and_encrypted_documents_block_completion(self):
		for content in (b"%PDF-invalid", pdf_bytes(password="secret")):
			with self.subTest(encrypted=len(content) > 100):
				manifest, _, errors = assemble_manifest([line("one")], lambda _: (content, "source.pdf"))
				self.assertEqual(manifest[0]["status"], "failed")
				self.assertTrue(errors)

	def test_raster_source_converts_and_keeps_original_checksum(self):
		stream = io.BytesIO()
		Image.new("RGBA", (100, 150), (255, 0, 0, 128)).save(stream, "PNG")
		content = stream.getvalue()
		manifest, parts, errors = assemble_manifest([line("one")], lambda _: (content, "drawing.png"))
		self.assertFalse(errors)
		self.assertEqual(len(PdfReader(io.BytesIO(parts[0])).pages), 1)
		self.assertEqual(manifest[0]["sha256"], hashlib.sha256(content).hexdigest())
		self.assertNotEqual(manifest[0]["sha256"], manifest[0]["pdf_sha256"])

	def test_optional_accessory_exclusion_is_visible(self):
		manifest, _, errors = assemble_manifest(
			[
				line("one"),
				line("accessory", required=False, spec_document_url=None, manufacturer_type="ACCESSORY"),
			],
			lambda _: (pdf_bytes(), "source.pdf"),
		)
		self.assertFalse(errors)
		self.assertEqual(manifest[1]["status"], "excluded")

	def test_duplicate_stable_identity_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "unique stable key"):
			assemble_manifest([line("one"), line("one")], lambda _: (pdf_bytes(), "source.pdf"))


class IncompleteWatermark(unittest.TestCase):
	def test_banner_marks_only_the_opening_pages(self):
		with load_service(ROOT + ".portal.packets", {}) as (module, _frappe):
			marked = module._incomplete_watermark(pdf_bytes(5), lambda _html: pdf_bytes(1, text="BANNER"))
		pages = PdfReader(io.BytesIO(marked)).pages
		self.assertEqual(len(pages), 5)
		self.assertEqual(["BANNER" in page.extract_text() for page in pages], [True, True, False, False, False])


class PacketGather(unittest.TestCase):
	kit_renderer = MagicMock(return_value={"success": True, "file_url": "/private/files/kit.pdf"})

	def gather(self, *rows, get_value=None):
		def unfillable(name, warnings=None, schedule_line=None):
			warnings.append(
				"PDF filling blocked: none of the 2 mapped field(s) exist in the PDF template /files/t.pdf."
			)
			return {"success": False, "message": "Failed to fill PDF form fields", "warnings": warnings}

		stubs = {
			ROOT + ".api.spec_submittal": types.ModuleType("spec_submittal"),
			ROOT + ".portal.build_documents": types.ModuleType("build_documents"),
			ROOT + ".portal.line_documents": types.ModuleType("line_documents"),
		}
		stubs[ROOT + ".api.spec_submittal"].__dict__.update(
			generate_filled_submittal=unfillable,
			generate_filled_neon_submittal=MagicMock(),
			generate_filled_sheet_submittal=MagicMock(),
			generate_filled_kit_submittal=self.kit_renderer,
		)
		stubs[ROOT + ".portal.build_documents"].generate_group = MagicMock()
		stubs[ROOT + ".portal.line_documents"].active = lambda schedule, line: []
		with load_service(ROOT + ".portal.packets", stubs) as (module, _frappe):
			if get_value:
				_frappe.db.get_value.side_effect = get_value
			warnings = []
			return module.gather(Record(name="S1", lines=list(rows)), warnings), warnings

	@staticmethod
	def templates(spec_sheets):
		"""Fixture CF1 belongs to template T1; spec_sheets maps template -> spec sheet URL."""

		def get_value(doctype, name, field, **_kwargs):
			if (doctype, field) == ("ilL-Configured-Fixture", "fixture_template"):
				return "T1"
			if field == "spec_sheet":
				return spec_sheets.get(name)
			return None

		return get_value

	def test_template_without_a_usable_submittal_falls_back_to_its_spec_sheet(self):
		row = dict(idx=1, line_id=None, qty=1, location=None, notes=None, manufacturer_type="ILLUMENATE")
		lines, warnings = self.gather(
			Record(row, name="R1", line_key="K1", configured_fixture="CF1"),
			get_value=self.templates({"T1": "/files/t1-spec-sheet.pdf"}),
		)
		self.assertEqual(lines[0]["spec_document_url"], "/files/t1-spec-sheet.pdf")
		self.assertEqual(lines[0]["source_kind"], "template_spec_sheet")
		self.assertNotIn("render_error", lines[0])
		self.assertIn("Line Row 1: used the T1 spec sheet", lines[0]["warnings"][0])
		self.assertIn("none of the 2 mapped field(s) exist", lines[0]["warnings"][0])
		self.assertIn(lines[0]["warnings"][0], warnings)
		manifest, parts, errors = assemble_manifest(lines, lambda _: (pdf_bytes(), "sheet.pdf"))
		self.assertEqual(errors, [])
		self.assertEqual(len(parts), 1)
		self.assertEqual(manifest[0]["status"], "included")
		self.assertEqual(manifest[0]["warnings"], lines[0]["warnings"])

	def test_template_without_any_document_warns_and_leaves_the_line_out(self):
		row = dict(idx=1, line_id=None, qty=1, location=None, notes=None, manufacturer_type="ILLUMENATE")
		lines, warnings = self.gather(
			Record(row, name="R1", line_key="K1", configured_fixture="CF1"),
			Record(row, name="R2", line_key="K2", idx=2, manufacturer_type="OTHER", spec_sheet="/files/o.pdf"),
			get_value=self.templates({}),
		)
		self.assertFalse(lines[0]["required"])
		self.assertIn("T1 has no spec submittal or spec sheet", lines[0]["warnings"][0])
		self.assertIn(lines[0]["warnings"][0], warnings)
		manifest, parts, errors = assemble_manifest(lines, lambda _: (pdf_bytes(), "other.pdf"))
		self.assertEqual(errors, [])
		self.assertEqual(len(parts), 1)
		self.assertEqual(manifest[0]["status"], "excluded")
		self.assertEqual(manifest[0]["reason"], "No spec submittal or spec sheet available")

	def test_unconfigured_line_still_reports_why(self):
		row = dict(idx=2, line_id=None, qty=1, location=None, notes=None, manufacturer_type="ILLUMENATE")
		lines, _warnings = self.gather(Record(row, name="R2", line_key="K2"))
		self.assertIn("no configured build", lines[0]["render_error"])
		_manifest, _parts, errors = assemble_manifest(lines, lambda _: self.fail("No source should load"))
		self.assertIn(
			"Line Row 2 (K2): The filled submittal could not be generated: The line has no", errors[0]
		)

	def test_unconfigured_kit_falls_back_to_its_spec_sheet(self):
		row = dict(idx=1, line_id="K", qty=4, location=None, notes=None, manufacturer_type="ILLUMENATE")
		self.kit_renderer = MagicMock(
			return_value={"success": False, "message": "Configure this extrusion kit before exporting"}
		)
		lines, _warnings = self.gather(
			Record(row, name="R1", line_key="K1", kit_template="KIT-A"),
			get_value=self.templates({"KIT-A": "/files/kit-a.pdf"}),
		)
		self.assertEqual(lines[0]["spec_document_url"], "/files/kit-a.pdf")
		self.assertEqual(lines[0]["provenance"]["template_type"], "ilL-Extrusion-Kit-Template")
		self.assertIn("Line K: used the KIT-A spec sheet", lines[0]["warnings"][0])

	def test_filled_submittal_carries_its_mapping_warnings(self):
		row = dict(idx=1, line_id="K", qty=4, location=None, notes=None, manufacturer_type="ILLUMENATE")

		def renderer(name, warnings=None, schedule_line=None):
			warnings += ["[DEBUG] noise", "2 PDF field(s) have no mapping and will be left blank: ['A', 'B']"]
			return {"success": True, "file_url": "/private/files/kit.pdf"}

		self.kit_renderer = renderer
		lines, _warnings = self.gather(Record(row, name="R1", line_key="K1", kit_template="KIT-A"))
		self.assertEqual(lines[0]["source_kind"], "filled_submittal")
		self.assertEqual(
			lines[0]["warnings"], ["Line K: 2 PDF field(s) have no mapping and will be left blank: ['A', 'B']"]
		)

	def test_linear_line_carries_display_part_number_not_hash_name(self):
		row = dict(idx=1, line_id="A", qty=1, location=None, notes=None, manufacturer_type="ILLUMENATE")
		calls = []

		def get_value(doctype, name, field, **_kwargs):
			calls.append((doctype, name, field))
			return "ILL-SL-SW-I-30-HO-FR-SM-WH-48"

		lines, _warnings = self.gather(
			Record(row, name="R1", line_key="K1", configured_fixture="ILL-CF-" + "a" * 64),
			Record(row, name="R2", line_key="K2", manufacturer_type="OTHER", fixture_model_number="ACM-200"),
			get_value=get_value,
		)
		self.assertEqual([entry["part_number"] for entry in lines], ["ILL-SL-SW-I-30-HO-FR-SM-WH-48", "ACM-200"])
		self.assertEqual(calls[0], ("ilL-Configured-Fixture", "ILL-CF-" + "a" * 64, "display_part_number"))
		manifest, _parts, _errors = assemble_manifest(lines, lambda _: (pdf_bytes(), "source.pdf"))
		self.assertEqual(manifest[0]["part_number"], "ILL-SL-SW-I-30-HO-FR-SM-WH-48")

	def test_configured_kit_line_fills_its_template_submittal_with_the_kit_part_number(self):
		row = dict(idx=1, line_id="K", qty=4, location=None, notes=None, manufacturer_type="ILLUMENATE")
		self.kit_renderer = MagicMock(return_value={"success": True, "file_url": "/private/files/kit.pdf"})
		lines, _warnings = self.gather(
			Record(
				row,
				name="R1",
				line_key="K1",
				product_type="Extrusion Kit",
				kit_template="KIT-A",
				ill_item_code="ILL-KIT-A-WH",
			)
		)
		self.kit_renderer.assert_called_once()
		self.assertEqual(self.kit_renderer.call_args.args, ("KIT-A",))
		self.assertEqual(self.kit_renderer.call_args.kwargs["schedule_line"], "R1")
		self.assertEqual(lines[0]["part_number"], "ILL-KIT-A-WH")
		self.assertEqual(lines[0]["build"], {"doctype": "ilL-Extrusion-Kit-Template", "name": "KIT-A"})
		self.assertEqual(lines[0]["spec_document_url"], "/private/files/kit.pdf")
		self.assertTrue(lines[0]["has_submittal"])


if __name__ == "__main__":
	unittest.main()
