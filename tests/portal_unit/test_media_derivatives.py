"""Hardening plan 5.8: WebP derivatives for staff product images, tested with Pillow doubles."""

import hashlib
import io
import json
import os
import tempfile
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service
from test_webflow_sync import _dependencies

HERE = os.path.dirname(os.path.abspath(__file__))
GPS = 0x8825


class FakeExif(dict):
	def tobytes(self):
		return json.dumps(sorted(self)).encode()


class FakeImage:
	def __init__(self, size, mode="RGB", fmt="JPEG", exif=None, info=None, saves=None):
		self.size, self.mode, self.format = size, mode, fmt
		self.exif = FakeExif(exif or {})
		self.info = info or {}
		self.saves = saves if saves is not None else []

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False

	def getexif(self):
		return self.exif

	def convert(self, mode):
		return FakeImage(self.size, mode, self.format, saves=self.saves)

	def resize(self, size, resample):
		return FakeImage(size, self.mode, self.format, saves=self.saves)

	def save(self, buffer, fmt, **options):
		self.saves.append((fmt, self.size, self.mode, options))
		buffer.write(f"{fmt}:{self.size[0]}x{self.size[1]}".encode())


def pillow(image, rotate=False):
	opened = MagicMock(return_value=image)
	Image = types.SimpleNamespace(open=opened, LANCZOS="lanczos")

	def transpose(source):
		if not rotate:
			return FakeImage(source.size, source.mode, source.format, info=source.info, saves=source.saves)
		return FakeImage(source.size[::-1], source.mode, source.format, info=source.info, saves=source.saves)

	return Image, types.SimpleNamespace(exif_transpose=transpose)


def file_doc(**values):
	base = {
		"name": "F-1",
		"file_name": "hero.jpg",
		"file_url": "/files/hero.jpg",
		"attached_to_doctype": "ilL-Webflow-Product",
		"attached_to_name": "demo",
		"attached_to_field": "featured_image",
		"content_hash": "abc",
		"is_private": 0,
	}
	base.update(values)
	return Record(base)


@contextmanager
def derivatives(enabled=True):
	with load_service(ROOT + ".api.media_derivatives") as (module, frappe):
		flags = types.SimpleNamespace(media_derivatives_enabled=MagicMock(return_value=enabled))
		frappe.enqueue = MagicMock()
		frappe.log_error = MagicMock()
		frappe.get_traceback = MagicMock(return_value="trace")
		frappe.delete_doc = MagicMock()
		with patch.object(module, "site_flags", flags):
			yield module, frappe


class Enqueue(unittest.TestCase):
	def test_product_and_template_images_enqueue_after_commit_with_a_key(self):
		cases = (
			{},
			{"attached_to_field": "image"},
			{"attached_to_doctype": "ilL-Fixture-Template", "attached_to_field": "hero_image"},
			{"attached_to_doctype": "ilL-LED-Sheet-Template", "attached_to_field": "image", "file_url": "/private/files/a.PNG"},
		)
		for values in cases:
			with self.subTest(**values), derivatives() as (module, frappe):
				doc = file_doc(**values)
				module.on_file_insert(doc, "after_insert")
				kwargs = frappe.enqueue.call_args.kwargs
				self.assertEqual(frappe.enqueue.call_args.args[0], module.__name__ + ".process_file")
				self.assertTrue(kwargs["enqueue_after_commit"])
				self.assertTrue(kwargs["deduplicate"])
				self.assertEqual(kwargs["queue"], "long")
				self.assertEqual(kwargs["job_id"], module.idempotency_key(doc))
				self.assertEqual(kwargs["key"], kwargs["job_id"])
				self.assertEqual(kwargs["file_name"], "F-1")

	def test_other_files_are_ignored(self):
		cases = (
			{"attached_to_doctype": "Customer"},
			{"attached_to_field": "spec_sheet"},
			{"attached_to_field": None},
			{"attached_to_name": "new-ill-webflow-product-1"},
			{"file_url": "/files/sheet.pdf"},
			{"file_url": "/files/photo.webp"},
			{"file_url": "https://example.com/hero.jpg"},
		)
		for values in cases:
			with self.subTest(**values), derivatives() as (module, frappe):
				module.on_file_insert(file_doc(**values))
				frappe.enqueue.assert_not_called()

	def test_the_site_flag_turns_processing_off(self):
		with derivatives(enabled=False) as (module, frappe):
			module.on_file_insert(file_doc())
			frappe.enqueue.assert_not_called()

	def test_an_enqueue_failure_never_blocks_the_upload(self):
		with derivatives() as (module, frappe):
			frappe.enqueue.side_effect = RuntimeError("redis down")
			module.on_file_insert(file_doc())
			frappe.log_error.assert_called_once()

	def test_key_follows_content_and_visibility(self):
		with derivatives() as (module, _):
			key = module.idempotency_key
			self.assertEqual(key(file_doc()), key(file_doc(name="F-2", attached_to_name="other")))
			self.assertNotEqual(key(file_doc()), key(file_doc(is_private=1)))
			self.assertNotEqual(key(file_doc()), key(file_doc(content_hash="def")))
			self.assertIn("/files/hero.jpg", key(file_doc(content_hash=None)))
			self.assertTrue(key(file_doc()).endswith(":webp-v1"))

	def test_watched_templates_match_the_product_projection(self):
		with derivatives() as (module, _):
			templates = {doctype for _, doctype in module.HERO_LINKS}
			self.assertEqual(set(module.WATCHED_FIELDS), {"ilL-Webflow-Product", *templates})
			self.assertEqual(len(templates), 6)


class Transform(unittest.TestCase):
	def run_transform(self, image, rotate=False, widths=None):
		with derivatives() as (module, _):
			Image, ImageOps = pillow(image, rotate)
			options = {} if widths is None else {"widths": widths}
			return module.make_derivatives(b"bytes", Image, ImageOps, **options)

	def test_three_widths_as_webp_without_exif(self):
		image = FakeImage((3000, 2000))
		result = self.run_transform(image)
		self.assertEqual((result["width"], result["height"]), (3000, 2000))
		self.assertEqual([(d["width"], d["height"]) for d in result["derivatives"]], [(480, 320), (1200, 800), (2400, 1600)])
		for fmt, _, _, options in image.saves:
			self.assertEqual(fmt, "WEBP")
			self.assertNotIn("exif", options)
		self.assertIsNone(result["stripped"])

	def test_never_upscales(self):
		result = self.run_transform(FakeImage((1000, 500)))
		self.assertEqual([d["width"] for d in result["derivatives"]], [480])
		self.assertEqual(self.run_transform(FakeImage((300, 300)))["derivatives"], [])
		exact = FakeImage((1200, 600))
		result = self.run_transform(exact)
		self.assertEqual([d["width"] for d in result["derivatives"]], [480, 1200])
		self.assertEqual(result["derivatives"][1]["content"], b"WEBP:1200x600")

	def test_dimensions_follow_the_exif_orientation(self):
		result = self.run_transform(FakeImage((2000, 3000)), rotate=True)
		self.assertEqual((result["width"], result["height"]), (3000, 2000))

	def test_gps_is_removed_from_the_original_and_other_exif_kept(self):
		image = FakeImage((800, 600), exif={GPS: {"lat": 1}, 0x0112: 1}, info={"icc_profile": b"icc"})
		result = self.run_transform(image)
		fmt, size, _, options = image.saves[-1]
		self.assertEqual((fmt, size), ("JPEG", (800, 600)))
		self.assertEqual(json.loads(options["exif"]), [0x0112])
		self.assertEqual(options["quality"], "keep")
		self.assertEqual(options["icc_profile"], b"icc")
		self.assertEqual(result["stripped"], b"JPEG:800x600")

	def test_png_gps_is_removed_without_jpeg_options(self):
		image = FakeImage((800, 600), fmt="PNG", exif={GPS: {}})
		self.run_transform(image)
		fmt, _, _, options = image.saves[-1]
		self.assertEqual(fmt, "PNG")
		self.assertNotIn("quality", options)

	def test_unusual_modes_are_converted(self):
		cmyk = FakeImage((600, 600), mode="CMYK")
		self.run_transform(cmyk)
		self.assertEqual(cmyk.saves[0][2], "RGB")
		palette = FakeImage((600, 600), mode="P", info={"transparency": 0})
		self.run_transform(palette)
		self.assertEqual(palette.saves[0][2], "RGBA")

	def test_names_follow_the_convention(self):
		with derivatives() as (module, _):
			self.assertEqual(module.derivative_name("hero.shot.JPG", 480), "hero.shot.ill-w480.webp")


class Worker(unittest.TestCase):
	@contextmanager
	def worker(self, record=None, pil=True, image=None):
		with derivatives() as (module, frappe):
			record = record or Record(name="R-1", status="Queued")
			record.save = MagicMock()
			source = file_doc()
			created = []

			def get_doc(doctype, name=None):
				if isinstance(doctype, dict):
					doc = Record(doctype, name=f"NEW-{len(created) + 1}")
					doc.file_url = "/files/" + (doctype.get("file_name") or "x")
					doc.insert = MagicMock(return_value=doc)
					doc.save = MagicMock()
					if doctype["doctype"] == "File":
						created.append(doc)
					return doc
				return record if doctype == module.DOCTYPE else source

			frappe.get_doc.side_effect = get_doc
			frappe.db.exists.return_value = True
			frappe.db.get_value.return_value = "R-1"
			frappe.get_all.return_value = ["F-1", "F-9"]
			pair = pillow(image or FakeImage((1600, 900), exif={GPS: {}})) if pil else (None, None)
			with (
				patch.object(module, "_pillow", return_value=pair),
				patch.object(module, "stored_bytes", return_value=b"original"),
				patch.object(module, "validate_content") as validate,
				patch.object(module, "_replace_original") as replace,
			):
				yield module, frappe, record, created, validate, replace

	def test_success_records_dimensions_and_creates_unattached_files(self):
		with self.worker() as (module, _, record, created, validate, replace):
			self.assertEqual(module.process_file("F-1", "key"), "Done")
			validate.assert_called_once_with("hero.jpg", b"original")
			replace.assert_called_once()
			self.assertEqual(replace.call_args.args[1], b"JPEG:1600x900")
			self.assertEqual([doc.file_name for doc in created], ["hero.ill-w480.webp", "hero.ill-w1200.webp"])
			for doc in created:
				self.assertNotIn("attached_to_doctype", doc)
				self.assertEqual(doc.is_private, 0)
			self.assertEqual((record.status, record.width, record.height, record.gps_removed), ("Done", 1600, 900, 1))
			saved = json.loads(record.derivatives)
			self.assertEqual([(d["width"], d["file"]) for d in saved], [(480, "NEW-1"), (1200, "NEW-2")])
			self.assertIsNone(record.error)

	def test_without_gps_the_original_is_untouched(self):
		with self.worker(image=FakeImage((900, 900))) as (module, _, record, _created, _validate, replace):
			module.process_file("F-1", "key")
			replace.assert_not_called()
			self.assertEqual(record.gps_removed, 0)

	def test_done_records_are_not_redone(self):
		with self.worker(record=Record(name="R-1", status="Done")) as (module, _, _, created, validate, _):
			self.assertEqual(module.process_file("F-1", "key"), "Done")
			validate.assert_not_called()
			self.assertEqual(created, [])

	def test_missing_pillow_is_recorded_as_skipped(self):
		with self.worker(pil=False) as (module, _, record, created, validate, _):
			self.assertEqual(module.process_file("F-1", "key"), "Skipped")
			self.assertIn("Pillow", record.error)
			validate.assert_not_called()
			self.assertEqual(created, [])

	def test_invalid_images_are_recorded_as_errors(self):
		with self.worker() as (module, frappe, record, created, validate, _):
			validate.side_effect = ValueError("Image must be PNG/JPEG with at most 40 million pixels")
			self.assertEqual(module.process_file("F-1", "key"), "Error")
			self.assertIn("40 million", record.error)
			frappe.log_error.assert_called_once()
			self.assertEqual(created, [])

	def test_a_failed_file_insert_removes_the_files_already_created(self):
		with self.worker() as (module, frappe, _record, _created, _validate, _replace):
			original = frappe.get_doc.side_effect

			def get_doc(doctype, name=None):
				doc = original(doctype, name)
				if isinstance(doctype, dict) and doctype.get("file_name", "").endswith("w1200.webp"):
					doc.insert.side_effect = RuntimeError("disk full")
				return doc

			frappe.get_doc.side_effect = get_doc
			self.assertEqual(module.process_file("F-1", "key"), "Error")
			frappe.delete_doc.assert_called_once_with("File", "NEW-1", ignore_permissions=True, force=True)

	def test_a_new_record_is_created_once_per_key(self):
		with self.worker() as (module, frappe, _record, _created, _validate, _replace):
			frappe.db.get_value.return_value = None
			module.process_file("F-1", "key")
			inserted = [c.args[0] for c in frappe.get_doc.call_args_list if isinstance(c.args[0], dict)]
			record = next(doc for doc in inserted if doc["doctype"] == module.DOCTYPE)
			self.assertEqual(
				(record["idempotency_key"], record["source_url"], record["recipe"]), ("key", "/files/hero.jpg", "webp-v1")
			)

	def test_a_deleted_file_is_ignored(self):
		with self.worker() as (module, frappe, _record, created, _validate, _replace):
			frappe.db.exists.return_value = False
			self.assertEqual(module.process_file("F-1", "key"), "Missing")
			self.assertEqual(created, [])

	def test_the_original_is_replaced_atomically_and_every_row_updated(self):
		with derivatives() as (module, frappe), tempfile.TemporaryDirectory(dir=HERE) as folder:
			path = os.path.join(folder, "hero.jpg")
			with open(path, "wb") as handle:
				handle.write(b"with gps")
			frappe.get_all.return_value = ["F-1", "F-9"]
			source = file_doc()
			source.get_full_path = lambda: path
			module._replace_original(source, b"clean")
			with open(path, "rb") as handle:
				self.assertEqual(handle.read(), b"clean")
			self.assertEqual(os.listdir(folder), ["hero.jpg"])
			self.assertEqual(frappe.get_all.call_args.kwargs["filters"], {"file_url": "/files/hero.jpg"})
			values = {"content_hash": hashlib.md5(b"clean").hexdigest(), "file_size": 5}
			self.assertEqual(
				[c.args for c in frappe.db.set_value.call_args_list],
				[("File", "F-1", values), ("File", "F-9", values)],
			)


class PayloadMap(unittest.TestCase):
	def test_one_query_for_finished_records(self):
		with derivatives() as (module, frappe):
			frappe.get_all.return_value = [
				Record(source_url="/files/a.jpg", width=3000, height=2000, derivatives=json.dumps([{"width": 480, "height": 320, "url": "/files/a.ill-w480.webp", "file": "F"}])),
				Record(source_url="/files/a.jpg", width=1, height=1, derivatives="[]"),
				Record(source_url="/files/b.jpg", width=10, height=10, derivatives="not json"),
			]
			found = module.derivative_map(["/files/a.jpg", None, "/files/b.jpg", "/files/a.jpg"])
			self.assertEqual(frappe.get_all.call_count, 1)
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(filters, {"source_url": ["in", ["/files/a.jpg", "/files/b.jpg"]], "status": "Done"})
			self.assertEqual(found["/files/a.jpg"]["derivatives"], [{"width": 480, "height": 320, "url": "/files/a.ill-w480.webp"}])
			self.assertEqual(found["/files/b.jpg"]["derivatives"], [])
			self.assertEqual(module.derivative_map([]), {})
			self.assertEqual(frappe.get_all.call_count, 1)


class WebflowPayload(unittest.TestCase):
	def test_payload_key_is_flag_gated_and_off_by_default(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			self.assertFalse(flags.webflow_image_derivatives_enabled())
			self.assertTrue(flags.media_derivatives_enabled())
			frappe.conf["ill_webflow_image_derivatives"] = "true"
			frappe.conf["ill_media_derivatives"] = 0
			self.assertTrue(flags.webflow_image_derivatives_enabled())
			self.assertFalse(flags.media_derivatives_enabled())
		path = os.path.join(HERE, "..", "..", *ROOT.split("."), "api", "webflow_export_v2.py")
		with open(path, encoding="utf-8") as handle:
			source = handle.read()
		self.assertEqual(source.count("_add_image_derivatives("), 2)
		self.assertIn(
			"    if webflow_image_derivatives_enabled():\n        _add_image_derivatives(products, listings, brand_code)",
			source,
		)

	def test_derivatives_are_keyed_by_absolute_source_url(self):
		with load_service(ROOT + ".api.webflow_export_v2", _dependencies()) as (module, _):
			found = {
				"/files/hero.jpg": {"derivatives": [{"width": 480, "height": 320, "url": "/files/hero.ill-w480.webp"}]},
				"/files/g.png": {"derivatives": []},
			}
			products = [{"name": "demo", "featured_image": "/files/hero.jpg", "hero_image": "/files/hero.jpg"}]
			listing = types.SimpleNamespace(gallery_images=[Record(image="/files/g.png"), Record(image="/files/none.jpg")])
			with (
				patch.object(module.media_derivatives, "derivative_map", return_value=found) as lookup,
				patch.object(module, "_make_absolute_url", side_effect=lambda url, brand=None: f"https://{brand}{url}"),
			):
				module._add_image_derivatives(products, {"demo": listing}, "erp")
			self.assertEqual(sorted(lookup.call_args.args[0]), ["/files/g.png", "/files/hero.jpg", "/files/none.jpg"])
			self.assertEqual(
				products[0]["image_derivatives"],
				{
					"https://erp/files/hero.jpg": [{"width": 480, "height": 320, "url": "https://erp/files/hero.ill-w480.webp"}],
					"https://erp/files/g.png": [],
				},
			)


class Schema(unittest.TestCase):
	def test_metadata_doctype_is_additive_and_read_only(self):
		path = os.path.join(HERE, "..", "..", *ROOT.split("."), "doctype", "ill_image_derivative", "ill_image_derivative.json")
		with open(path, encoding="utf-8") as handle:
			meta = json.load(handle)
		self.assertEqual(meta["name"], "ilL-Image-Derivative")
		fields = {field["fieldname"]: field for field in meta["fields"]}
		self.assertEqual([field["fieldname"] for field in meta["fields"]], meta["field_order"])
		for field in fields.values():
			if field["fieldtype"] not in ("Section Break", "Column Break"):
				self.assertEqual(field.get("read_only"), 1, field["fieldname"])
		self.assertEqual(fields["idempotency_key"].get("unique"), 1)
		self.assertEqual(fields["source_url"].get("search_index"), 1)
		self.assertEqual(
			{name: fields[name].get("default") for name in ("status", "width", "height", "derivatives", "recipe")},
			{"status": "Queued", "width": "0", "height": "0", "derivatives": "[]", "recipe": "webp-v1"},
		)
		self.assertTrue(all(not p.get("create") and not p.get("write") for p in meta["permissions"]))

	def test_hook_is_registered_on_file_after_insert(self):
		path = os.path.join(HERE, "..", "..", "illumenate_lighting", "hooks.py")
		with open(path, encoding="utf-8") as handle:
			self.assertIn(
				'"File": {"after_insert": "illumenate_lighting.illumenate_lighting.api.media_derivatives.on_file_insert"}',
				handle.read(),
			)


if __name__ == "__main__":
	unittest.main()
