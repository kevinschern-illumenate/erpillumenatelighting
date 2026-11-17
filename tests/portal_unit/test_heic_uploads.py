"""Hardening plan 4.2 / D2: HEIC photos become orientation-corrected, metadata-free JPEGs."""

import importlib.util
import io
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.portal import file_validation
from illumenate_lighting.illumenate_lighting.portal.file_validation import (
	is_heif,
	normalize_upload,
	validate_content,
)


def ftyp(brand, compatible=b"mif1heic"):
	box = b"ftyp" + brand + b"\0\0\0\0" + compatible
	return (len(box) + 4).to_bytes(4, "big") + box + b"\0" * 32


def has_module(name):
	try:
		return importlib.util.find_spec(name) is not None
	except ValueError:
		return False


class HeifSniffing(unittest.TestCase):
	def test_phone_brands_are_heif(self):
		for brand in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
			with self.subTest(brand=brand):
				self.assertTrue(is_heif(ftyp(brand)))

	def test_avif_video_and_garbage_are_not_heif(self):
		for content in (ftyp(b"avif"), ftyp(b"isom"), ftyp(b"qt  "), b"\xff\xd8\xff" + b"\0" * 20, b"", b"ftyp"):
			with self.subTest(content=content[:12]):
				self.assertFalse(is_heif(content))


class NormalizeUpload(unittest.TestCase):
	def test_other_formats_pass_through_untouched(self):
		content = b"%PDF-1.7 not even parsed here"
		self.assertEqual(normalize_upload("a.pdf", content), ("a.pdf", content))
		self.assertEqual(normalize_upload("a.JPG", b"x"), ("a.JPG", b"x"))

	def test_renamed_non_heif_is_rejected_before_decoding(self):
		for content in (b"\xff\xd8\xff\xe0 jpeg bytes", ftyp(b"avif"), b"%PDF-1.7"):
			with self.subTest(content=content[:8]), self.assertRaisesRegex(ValueError, "does not match"):
				normalize_upload("IMG_0001.HEIC", content)

	def test_size_cap_applies_to_uploaded_bytes(self):
		for content in (b"", ftyp(b"heic") + b"x" * file_validation.MAX_FILE_BYTES):
			with self.subTest(size=len(content)), self.assertRaisesRegex(ValueError, "20 MiB"):
				normalize_upload("photo.heic", content)

	def test_missing_decoder_rejects_with_a_clear_message(self):
		with patch.dict(sys.modules, {"pillow_heif": None}):
			with self.assertRaisesRegex(ValueError, "export the photo as JPEG"):
				normalize_upload("photo.heif", ftyp(b"heic"))

	def test_heif_mode_never_reaches_validate_content_unconverted(self):
		with self.assertRaisesRegex(ValueError, "Only PDF, JPEG and PNG"):
			validate_content("photo.heic", ftyp(b"heic"))


@unittest.skipUnless(has_module("pillow_heif") and has_module("PIL"), "needs pillow-heif (installed by the contracts job)")
class HeifConversion(unittest.TestCase):
	def heic(self, size=(40, 20), orientation=6):
		import pillow_heif
		from PIL import Image

		pillow_heif.register_heif_opener()
		image = Image.new("RGB", size, (200, 30, 30))
		image.putpixel((0, 0), (0, 0, 255))
		exif = Image.Exif()
		exif[0x0112] = orientation
		exif[0x010F] = "PhoneMaker"
		exif[0x8825] = {1: "N", 2: (45.0, 30.0, 0.0), 3: "W", 4: (73.0, 35.0, 0.0)}
		stream = io.BytesIO()
		image.save(stream, format="HEIF", exif=exif.tobytes(), quality=90)
		return stream.getvalue()

	def test_converted_jpeg_is_upright_and_metadata_free(self):
		from PIL import Image

		content = self.heic()
		self.assertTrue(is_heif(content))
		filename, converted = normalize_upload("../IMG_0001.HEIC", content)
		self.assertEqual(filename, "IMG_0001.jpg")
		with Image.open(io.BytesIO(converted)) as result:
			self.assertEqual(result.format, "JPEG")
			self.assertEqual(result.size, (20, 40))
			self.assertEqual(dict(result.getexif()), {})
			self.assertNotIn("exif", result.info)
			self.assertNotIn("xmp", result.info)
		self.assertNotIn(b"PhoneMaker", converted)
		metadata = validate_content(filename, converted)
		self.assertEqual(metadata["mime_type"], "image/jpeg")

	def test_pixel_cap_applies_to_heif(self):
		with patch.object(file_validation, "MAX_IMAGE_PIXELS", 100):
			with self.assertRaisesRegex(ValueError, "40 million pixels"):
				normalize_upload("big.heic", self.heic(size=(20, 20)))


class UploadStream(unittest.TestCase):
	def upload(self, enabled, filename="IMG.heic", content=b"raw-heic"):
		normalize = MagicMock(return_value=("IMG.jpg", b"jpeg-bytes"))
		validate = MagicMock(
			side_effect=lambda name, body: {
				"filename": name,
				"size": len(body),
				"sha256": "0" * 64,
				"mime_type": "image/jpeg",
				"pages": None,
			}
		)
		created = []

		def get_doc(values):
			doc = MagicMock(**{k: v for k, v in values.items() if k != "doctype"})
			doc.name = values["doctype"]
			doc.insert.return_value = doc
			if values["doctype"] == "File":
				doc.is_private, doc.file_url = 1, "/private/files/IMG.jpg"
			created.append(values)
			return doc

		site_flags = types.SimpleNamespace(
			heic_uploads_enabled=lambda: enabled,
			upload_purpose_enabled=lambda: True,
			thumbnails_enabled=lambda: False,
			gallery_enabled=lambda: True,
			dealer_logo_enabled=lambda: True,
			staff_heic_enabled=lambda: True,
		)
		with load_service(ROOT + ".portal.files", {ROOT + ".portal.site_flags": site_flags}) as (module, frappe):
			frappe.request = Record(
				files={"file": Record(filename=filename, stream=io.BytesIO(content))}
			)
			frappe.get_doc = MagicMock(side_effect=get_doc)
			with patch.object(module, "normalize_upload", normalize), patch.object(module, "validate_content", validate):
				result = module.upload()
		return result, created, normalize, validate

	def test_enabled_upload_stores_the_converted_jpeg(self):
		result, created, normalize, validate = self.upload(True)
		normalize.assert_called_once_with("IMG.heic", b"raw-heic")
		validate.assert_called_once_with("IMG.jpg", b"jpeg-bytes")
		file = next(values for values in created if values["doctype"] == "File")
		self.assertEqual((file["file_name"], file["content"]), ("IMG.jpg", b"jpeg-bytes"))
		self.assertEqual(result["filename"], "IMG.jpg")
		self.assertTrue(result["success"])

	def test_kill_switch_keeps_the_original_pdf_jpeg_png_contract(self):
		_result, created, normalize, validate = self.upload(False)
		normalize.assert_not_called()
		validate.assert_called_once_with("IMG.heic", b"raw-heic")
		file = next(values for values in created if values["doctype"] == "File")
		self.assertEqual(file["content"], b"raw-heic")


if __name__ == "__main__":
	unittest.main()
