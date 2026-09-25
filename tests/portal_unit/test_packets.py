import hashlib
import io
import unittest

from PIL import Image
from pypdf import PdfReader, PdfWriter

from illumenate_lighting.illumenate_lighting.portal.packet_manifest import assemble_manifest


def pdf_bytes(pages=1, password=None):
	writer = PdfWriter()
	for _ in range(pages):
		writer.add_blank_page(width=612, height=792)
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


if __name__ == "__main__":
	unittest.main()
