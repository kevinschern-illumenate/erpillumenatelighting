"""Bulk media manifest (plan 5.7): parsing, SSRF-safe sources, D1 no-overwrite and Import wiring."""

import hashlib
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from test_catalog_builder import API, catalog_service
from test_services import ROOT, Record, load_service

MM = ROOT + ".api.media_manifest"
PRODUCT = "ilL-Webflow-Product"
GALLERY = "ilL-Child-Webflow-Gallery-Image"
KIT = "ilL-Extrusion-Kit-Template"
HERE = os.path.dirname(os.path.abspath(__file__))


def fake_validate(filename, content):
	if content == b"bad":
		raise ValueError("Image validation failed: cannot identify image file")
	mime = "application/pdf" if filename.endswith(".pdf") else "image/jpeg"
	return {"filename": filename, "size": len(content), "mime_type": mime, "sha256": "x", "pages": None}


def zip_bytes(entries):
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
		for name, content in entries.items():
			archive.writestr(name, content)
	return buffer.getvalue()


class World:
	def __init__(self):
		self.products = [
			Record(
				name="SL01",
				product_slug="sl01",
				featured_image=None,
				dimensions_image="/files/dims.png",
				series_family_image=None,
				kit_template="KIT-1",
			),
			Record(name="NOTPL", product_slug="no-template", featured_image=None),
		]
		self.templates = {(KIT, "KIT-1"): Record(name="KIT-1", hero_image=None, hero_image_alt=None)}
		self.gallery = [Record(parent="SL01", image="/files/old.jpg", display_order=3)]
		self.files = {
			"F-PUBLIC": Record(
				name="F-PUBLIC", file_url="/files/side.jpg", file_name="side.jpg", is_private=0, content=b"side"
			),
			"F-PRIVATE": Record(
				name="F-PRIVATE",
				file_url="/private/files/raw.jpg",
				file_name="raw.jpg",
				is_private=1,
				content=b"raw",
			),
			"F-OLD": Record(
				name="F-OLD", file_url="/files/old.jpg", file_name="old.jpg", is_private=0, content=b"old"
			),
		}
		self.public_hashes = {}
		self.writable = True
		self.saved = []
		self.created_files = []
		self.docs = {}


@contextmanager
def manifest_module(world=None):
	world = world or World()
	with load_service(MM) as (mm, frappe):
		_wire(mm, frappe, world)
		with (
			patch.object(mm, "validate_content", side_effect=fake_validate),
			patch.object(mm, "stored_bytes", side_effect=lambda doc: doc.content),
		):
			yield mm, frappe, world


def _wire(mm, frappe, world):
	def names(filters, key):
		value = filters.get(key)
		return set(value[1]) if value else None

	def get_all(doctype, filters=None, fields=None, pluck=None, **kwargs):
		filters = filters or {}
		if doctype == PRODUCT:
			slugs, wanted = names(filters, "product_slug"), names(filters, "name")
			return [
				p
				for p in world.products
				if (slugs is not None and p.product_slug in slugs) or (wanted is not None and p.name in wanted)
			]
		if doctype == GALLERY:
			return [g for g in world.gallery if g.parent in set(filters["parent"][1])]
		if doctype == "File":
			url = world.public_hashes.get(filters.get("content_hash"))
			return [url] if url else []
		wanted = names(filters, "name") or set()
		return [row for (dt, name), row in world.templates.items() if dt == doctype and name in wanted]

	def get_doc(doctype, name=None):
		if isinstance(doctype, dict):
			data = doctype
			doc = MagicMock()
			doc.file_url = "/files/" + data["file_name"]
			doc.get_full_path.return_value = os.path.join(HERE, "never-written", data["file_name"])
			doc.insert.side_effect = lambda **kw: world.created_files.append(data)
			return doc
		if doctype == "File":
			return world.files[name]
		key = (doctype, name)
		if key not in world.docs:
			doc = MagicMock()
			doc.doctype, doc.name, doc.values, doc.rows = doctype, name, {}, []
			doc.set.side_effect = lambda field, value, doc=doc: doc.values.__setitem__(field, value)
			doc.append.side_effect = lambda field, row, doc=doc: doc.rows.append((field, row))
			doc.save.side_effect = lambda doc=doc: world.saved.append((doc.doctype, doc.name))
			world.docs[key] = doc
		return world.docs[key]

	def file_lookup(doctype, filters, field):
		if doctype == "File" and isinstance(filters, dict):
			for doc in world.files.values():
				if doc.file_url == filters.get("file_url"):
					return doc.name
		return None

	frappe.get_all.side_effect = get_all
	frappe.get_doc.side_effect = get_doc
	frappe.get_meta.return_value.has_field.return_value = True
	frappe.db.exists.side_effect = lambda doctype, name: doctype == "File" and name in world.files
	frappe.db.get_value.side_effect = file_lookup
	frappe.has_permission.side_effect = lambda doctype, ptype, doc=None: ptype == "read" or world.writable


def row(**values):
	base = {"product_slug": "sl01", "role": "gallery", "file_url_or_zip_path": "/files/side.jpg"}
	base.update(values)
	return base


class ManifestParsing(unittest.TestCase):
	def test_csv_json_and_rows_normalise_to_the_same_rows(self):
		with manifest_module() as (mm, _, __):
			csv_text = "\ufeffProduct_Slug,role,file_url_or_zip_path,alt_text\nsl01,gallery,/files/a.jpg,Side\n,,,\n"
			expected = [
				{"product_slug": "sl01", "role": "gallery", "file_url_or_zip_path": "/files/a.jpg", "alt_text": "Side"}
			]
			self.assertEqual(mm.parse_manifest(csv_text), expected)
			self.assertEqual(mm.parse_manifest(json.dumps(expected)), expected)
			self.assertEqual(mm.parse_manifest([{**expected[0], "display_order": 2}])[0]["display_order"], "2")
			for empty in (None, "", "  ", []):
				self.assertEqual(mm.parse_manifest(empty), [])

	def test_unreadable_manifests_are_refused(self):
		with manifest_module() as (mm, _, __):
			for value, message in (
				("[broken", "not valid JSON"),
				("role,alt_text\ngallery,x\n", "needs the columns"),
				([{"product_slug": "a", "colour": "red"}], "Unknown media manifest column: colour"),
				({"product_slug": "a"}, "CSV text or a list"),
				([{"product_slug": {"nested": 1}}], "must be text"),
				([row()] * (mm.MAX_MEDIA_ROWS + 1), "limit 200"),
				("product_slug,role,file_url_or_zip_path\na,b,c,d\n", "more cells"),
			):
				with self.subTest(message=message), self.assertRaisesRegex(mm.ManifestError, message):
					mm.parse_manifest(value)

	def test_hash_covers_rows_and_zip_content(self):
		with manifest_module() as (mm, _, __):
			base = mm.manifest_hash([row()], None)
			self.assertEqual(base, mm.manifest_hash([row()], None))
			self.assertNotEqual(base, mm.manifest_hash([row(alt_text="x")], None))
			self.assertNotEqual(base, mm.manifest_hash([row()], {"file": "Z", "content_hash": "1"}))


class ManifestSources(unittest.TestCase):
	def test_remote_and_traversal_sources_are_rejected_without_fetching(self):
		with manifest_module() as (mm, frappe, _):
			for value in (
				"http://example.com/a.jpg",
				"https://169.254.169.254/latest",
				"//evil.example/a.jpg",
				"ftp:a.jpg",
				"data:image/png;base64,AAAA",
				"file:///etc/passwd",
				"/files/../site_config.json",
				"/files/%2e%2e/site_config.json",
				"images/../../x.jpg",
				"/etc/passwd",
				"/api/method/frappe.ping",
				"/files/a.jpg?x=1",
				"C:\\images\\a.jpg",
				"",
			):
				with self.subTest(value=value), self.assertRaises(ValueError):
					mm.classify_source(value)
			frappe.get_doc.assert_not_called()
			self.assertEqual(mm.classify_source("/files/a.jpg"), ("url", "/files/a.jpg"))
			self.assertEqual(mm.classify_source("/private/files/a.jpg"), ("url", "/private/files/a.jpg"))
			self.assertEqual(mm.classify_source("a1b2c3d4e5"), ("file", "a1b2c3d4e5"))
			self.assertEqual(mm.classify_source("sl01/side view.jpg"), ("zip", "sl01/side view.jpg"))

	def test_site_paths_without_file_documents_stay_inside_the_files_folder(self):
		with manifest_module() as (mm, frappe, _), tempfile.TemporaryDirectory(dir=HERE) as site:
			for folder in ("public", "private"):
				os.makedirs(os.path.join(site, folder, "files"))
			with open(os.path.join(site, "public", "files", "loose.jpg"), "wb") as handle:
				handle.write(b"loose")
			with open(os.path.join(site, "secret.jpg"), "wb") as handle:
				handle.write(b"secret")
			os.symlink(os.path.join(site, "secret.jpg"), os.path.join(site, "public", "files", "link.jpg"))
			frappe.get_site_path = lambda *parts: os.path.join(site, *parts)
			self.assertEqual(mm._site_file("/files/loose.jpg"), ("loose.jpg", b"loose", False))
			for url in ("/files/link.jpg", "/files/missing.jpg", "/private/files/loose.jpg", "/files/a/b.jpg"):
				with self.subTest(url=url), self.assertRaises(ValueError):
					mm._site_file(url)

	def test_zip_entries_are_bounded_and_read_from_the_uploaded_file(self):
		world = World()
		world.files["ZIP"] = Record(
			name="ZIP", file_url="/private/files/media.zip", file_name="media.zip", is_private=1, file_size=10
		)
		archive = zip_bytes({"sl01/side.jpg": b"img", "bomb.jpg": b"\0" * 300_000, "dir/": b""})
		world.files["ZIP"].get_full_path = lambda: io.BytesIO(archive)
		world.files["ZIP"]["content_hash"] = "zip-hash"
		with manifest_module(world) as (mm, frappe, _):
			source = mm.ZipSource("/private/files/media.zip")
			self.assertEqual(source.identity(), {"file": "ZIP", "content_hash": "zip-hash"})
			self.assertEqual(source.read("sl01/side.jpg"), b"img")
			for path, message in (("missing.jpg", "not in the media ZIP"), ("bomb.jpg", "compressed too much"), ("dir/", "folder")):
				with self.subTest(path=path), self.assertRaisesRegex(ValueError, message):
					source.read(path)
			source.close()
			for reference, message in (("NOPE", "uploaded to ERPNext"), ("F-PUBLIC", r"\.zip file")):
				with self.subTest(reference=reference), self.assertRaisesRegex(mm.ManifestError, message):
					mm.ZipSource(reference).identity()
			frappe.has_permission.side_effect = lambda *a, **k: False
			with self.assertRaisesRegex(mm.ManifestError, "cannot read"):
				mm.ZipSource("ZIP").identity()


class ManifestPlan(unittest.TestCase):
	def test_gallery_rows_add_images_and_never_duplicate(self):
		with manifest_module() as (mm, frappe, _):
			results = mm.plan(
				[
					row(alt_text="Side view"),
					row(file_url_or_zip_path="/files/old.jpg"),
					row(file_url_or_zip_path="F-PUBLIC", display_order="9"),
				]
			)
			self.assertEqual([r["status"] for r in results], ["ok", "ok", "ok"])
			self.assertEqual(results[0]["targets"], ["ilL-Webflow-Product SL01: gallery #4"])
			self.assertEqual(results[1]["warnings"], ["Already in the gallery of SL01"])
			self.assertEqual(results[1]["_actions"], [])
			self.assertEqual(results[2]["warnings"], ["Already in the gallery of SL01"])
			self.assertNotIn("_actions", mm.public_result(results[0]))
			frappe.db.commit.assert_not_called()
			frappe.get_doc.assert_any_call("File", "F-PUBLIC")

	def test_d1_existing_images_are_skipped_unless_the_row_says_replace(self):
		world = World()
		world.templates[(KIT, "KIT-1")]["hero_image"] = "/files/hero.jpg"
		with manifest_module(world) as (mm, _, __):
			results = mm.plan(
				[
					row(role="dimensions"),
					row(role="hero"),
					row(role="gallery", is_primary="1"),
					row(role="dimensions", replace="true", file_url_or_zip_path="F-OLD"),
					row(role="featured"),
					row(role="dimensions", file_url_or_zip_path="/files/dims.png"),
				]
			)
		statuses = [r["status"] for r in results]
		self.assertEqual(statuses, ["skipped", "skipped", "skipped", "ok", "ok", "error"])
		self.assertIn("replace=1", results[0]["message"])
		self.assertIn("KIT-1 already has a hero image (/files/hero.jpg)", results[1]["message"])
		# is_primary also targets the hero, so the whole row is kept back.
		self.assertEqual(results[2]["_actions"], [])
		self.assertEqual(results[3]["targets"], ["ilL-Webflow-Product SL01: dimensions image (replace)"])
		self.assertTrue(results[3]["_actions"][0]["replace"])
		self.assertIn("Row 4 already sets the dimensions image of SL01", results[5]["message"])

	def test_hero_rows_target_the_source_template_with_alt_text(self):
		with manifest_module() as (mm, _, __):
			results = mm.plan([row(role="hero", alt_text="Kit profile"), row(product_slug="no-template", role="hero")])
		self.assertEqual(results[0]["status"], "ok")
		action = results[0]["_actions"][0]
		self.assertEqual((action["doctype"], action["name"], action["field"]), (KIT, "KIT-1", "hero_image"))
		self.assertEqual((action["alt_field"], action["alt_text"]), ("hero_image_alt", "Kit profile"))
		self.assertEqual(results[1]["status"], "error")
		self.assertIn("no source template", results[1]["message"])

	def test_row_errors_are_reported_per_row(self):
		world = World()
		with manifest_module(world) as (mm, _, __):
			world.files["F-BAD"] = Record(name="F-BAD", file_url="/files/bad.jpg", file_name="bad.jpg", content=b"bad")
			world.files["F-PDF"] = Record(name="F-PDF", file_url="/files/a.pdf", file_name="a.pdf", content=b"%PDF")
			world.files["F-BIG"] = Record(name="F-BIG", file_url="/files/big.jpg", file_name="big.jpg", file_size=30 << 20)
			results = mm.plan(
				[
					row(product_slug="missing"),
					row(role="poster"),
					row(file_url_or_zip_path="https://example.com/a.jpg"),
					row(file_url_or_zip_path="F-BAD"),
					row(file_url_or_zip_path="F-PDF"),
					row(file_url_or_zip_path="F-BIG"),
					row(file_url_or_zip_path="pics/a.jpg"),
					row(display_order="first"),
					row(alt_text="x" * 141),
					row(is_primary="maybe"),
					row(product_slug=""),
				]
			)
		messages = [r["message"] for r in results]
		self.assertTrue(all(r["status"] == "error" for r in results), messages)
		for index, text in enumerate(
			(
				"No ilL-Webflow-Product",
				"role must be one of",
				"Remote URLs are not fetched",
				"Image validation failed",
				"Only JPEG and PNG",
				"20 MiB",
				"Upload a media ZIP",
				"whole number",
				"at most 140",
				"Expected a boolean",
				"product_slug is required",
			)
		):
			self.assertIn(text, messages[index])

	def test_write_permission_is_required_on_each_target(self):
		world = World()
		world.writable = False
		with manifest_module(world) as (mm, frappe, _):
			results = mm.plan([row(), row(role="hero")])
			self.assertEqual([r["status"] for r in results], ["error", "error"])
			self.assertIn("You cannot edit ilL-Webflow-Product SL01", results[0]["message"])
			self.assertIn(f"You cannot edit {KIT} KIT-1", results[1]["message"])
			frappe.has_permission.side_effect = lambda doctype, ptype, doc=None: doctype != "File"
			results = mm.plan([row()])
			self.assertIn("You cannot read the file", results[0]["message"])

	def test_private_and_zip_sources_become_public_copies(self):
		world = World()
		world.files["ZIP"] = Record(name="ZIP", file_url="/private/files/m.zip", file_name="m.zip", content_hash="z")
		world.files["ZIP"].get_full_path = lambda: io.BytesIO(zip_bytes({"sl01/new.jpg": b"new"}))
		with manifest_module(world) as (mm, _, __):
			zip_source = mm.ZipSource("ZIP")
			results = mm.plan(
				[row(file_url_or_zip_path="/private/files/raw.jpg"), row(role="featured", file_url_or_zip_path="sl01/new.jpg")],
				zip_source,
			)
		self.assertEqual([r["status"] for r in results], ["ok", "ok"])
		self.assertIn("public copy", results[0]["warnings"][0])
		self.assertEqual(results[0]["_actions"][0]["image"]["content"], b"raw")
		self.assertIsNone(results[0]["_actions"][0]["image"]["url"])
		self.assertEqual(results[1]["_actions"][0]["image"]["filename"], "new.jpg")

	def test_identical_public_content_counts_as_already_set(self):
		world = World()
		world.public_hashes[hashlib.md5(b"raw").hexdigest()] = "/files/old.jpg"
		with manifest_module(world) as (mm, _, __):
			results = mm.plan([row(file_url_or_zip_path="F-PRIVATE")])
		self.assertEqual(results[0]["_actions"], [])
		self.assertEqual(results[0]["warnings"][-1], "Already in the gallery of SL01")


class ManifestApply(unittest.TestCase):
	def test_templates_save_before_products_and_files_are_attached(self):
		world = World()
		with manifest_module(world) as (mm, _frappe, _):
			results = mm.plan(
				[
					row(alt_text="Side"),
					row(role="hero", alt_text="Hero", file_url_or_zip_path="/private/files/raw.jpg"),
					row(role="featured", file_url_or_zip_path="F-OLD"),
					row(file_url_or_zip_path="/files/old.jpg"),
				]
			)
			created = []
			mm.apply(results, created)
		self.assertEqual([r["status"] for r in results], ["attached", "attached", "attached", "unchanged"])
		self.assertEqual(world.saved, [(KIT, "KIT-1"), (PRODUCT, "SL01")])
		template = world.docs[(KIT, "KIT-1")]
		self.assertEqual(template.values, {"hero_image": "/files/raw.jpg", "hero_image_alt": "Hero"})
		product = world.docs[(PRODUCT, "SL01")]
		self.assertEqual(product.values, {"featured_image": "/files/old.jpg"})
		self.assertEqual(
			product.rows, [("gallery_images", {"image": "/files/side.jpg", "alt_text": "Side", "display_order": 4})]
		)
		self.assertEqual(len(world.created_files), 1)
		new_file = world.created_files[0]
		self.assertEqual(
			(new_file["is_private"], new_file["attached_to_doctype"], new_file["attached_to_field"]),
			(0, KIT, "hero_image"),
		)
		self.assertEqual(created, [os.path.join(HERE, "never-written", "raw.jpg")])

	def test_rows_that_were_skipped_or_failed_are_never_applied(self):
		world = World()
		with manifest_module(world) as (mm, _, __):
			results = mm.plan([row(role="dimensions"), row(product_slug="missing")])
			mm.apply(results, [])
		self.assertEqual([r["status"] for r in results], ["skipped", "error"])
		self.assertEqual(world.saved, [])

	def test_remove_new_files_ignores_missing_paths(self):
		with manifest_module() as (mm, _, __), tempfile.TemporaryDirectory(dir=HERE) as folder:
			path = os.path.join(folder, "new.jpg")
			with open(path, "wb") as handle:
				handle.write(b"x")
			mm.remove_new_files([path, os.path.join(folder, "missing.jpg")])
			self.assertFalse(os.path.exists(path))


@contextmanager
def builder(world=None, **access):
	world = world or World()
	with (
		load_service(MM) as (mm, _),
		catalog_service(API, **access) as (service, frappe),
		patch.object(service, "media_manifest", mm),
		patch.object(mm, "frappe", frappe),
		patch.object(mm, "validate_content", side_effect=fake_validate),
		patch.object(mm, "stored_bytes", side_effect=lambda doc: doc.content),
	):
		staff_get_value = frappe.db.get_value.side_effect
		_wire(mm, frappe, world)
		file_lookup = frappe.db.get_value.side_effect
		frappe.db.get_value.side_effect = lambda doctype, filters, field: (
			staff_get_value(doctype, filters, field) if doctype == "User" else file_lookup(doctype, filters, field)
		)
		events, logs, passing = [], [], []
		frappe.local.site = "test.local"
		frappe.local.message_log = []
		frappe.utils.now_datetime = lambda: datetime(2026, 11, 3, 12)
		frappe.utils.strip_html_tags = lambda text: re.sub(r"<[^>]*>", "", text)
		frappe.get_traceback = lambda: "private traceback"
		frappe.db.sql.return_value = [[1]]
		frappe.db.commit.side_effect = lambda: events.append("commit")
		frappe.db.rollback.side_effect = lambda **kw: events.append("rollback")
		media_get_all = frappe.get_all.side_effect

		def get_all(doctype, **kwargs):
			if doctype == service.AUDIT:
				return passing
			return media_get_all(doctype, **kwargs)

		frappe.get_all.side_effect = get_all
		media_get_doc = frappe.get_doc.side_effect

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict) and doctype.get("doctype") == service.AUDIT:
				audit = MagicMock()
				audit.insert.side_effect = lambda **kw: (logs.append(doctype), events.append("log"))
				audit.name = f"CAT-IMP-{len(logs) + 1}"
				return audit
			return media_get_doc(doctype, name)

		frappe.get_doc.side_effect = get_doc
		yield service, frappe, world, events, logs, passing


class CatalogBuilderMedia(unittest.TestCase):
	def test_dealers_cannot_check_or_import_media(self):
		for access in ({"roles": ["Dealer"]}, {"user": "Guest"}, {"roles": []}):
			with self.subTest(access=access), builder(**access) as (service, _frappe, world, events, _, __):
				for call in (lambda: service.check(media=[row()]), lambda: service.import_catalog(None, "h", [row()])):
					with self.assertRaises(PermissionError):
						call()
				self.assertEqual(events, [])
				self.assertEqual(world.saved, [])

	def test_media_only_check_reports_rows_and_writes_nothing(self):
		with builder() as (service, _frappe, world, events, logs, _):
			response = service.check(media=json.dumps([row(), row(role="dimensions")]))
		self.assertEqual((response["status"], response["stage"]), ("Passed", "media"))
		self.assertEqual([r["status"] for r in response["media"]], ["ok", "skipped"])
		self.assertEqual(response["summary"]["media_rows"], 2)
		self.assertEqual(response["summary"]["media_skipped"], 1)
		self.assertEqual(response["summary"]["errors"], 0)
		self.assertEqual(world.saved, [])
		self.assertEqual(events, ["rollback", "log", "commit"])
		self.assertEqual(json.loads(logs[0]["results_json"])["media"][0]["status"], "ok")
		self.assertIn("media", json.loads(logs[0]["catalog_json"]))
		self.assertNotIn("_actions", json.dumps(response["media"]))

	def test_error_rows_fail_the_check(self):
		with builder() as (service, _, _world, _events, __, ___):
			response = service.check(media=[row(file_url_or_zip_path="http://example.com/x.jpg")])
		self.assertEqual(response["status"], "Failed")
		self.assertEqual(response["summary"]["media_errors"], 1)
		self.assertEqual(response["summary"]["errors"], 1)
		self.assertFalse(response["ok"])

	def test_import_needs_a_passing_check_of_the_same_manifest(self):
		with builder() as (service, _frappe, world, events, _, passing):
			checked = service.check(media=[row()])
			passing.append("CHECK-1")
			changed = service.import_catalog(None, checked["catalog_hash"], [row(alt_text="new")])
			self.assertEqual((changed["status"], changed["stage"]), ("Refused", "gate"))
			self.assertEqual(world.saved, [])
			imported = service.import_catalog(None, checked["catalog_hash"], [row()])
		self.assertEqual(imported["status"], "Imported")
		self.assertEqual(imported["media"][0]["status"], "attached")
		self.assertEqual(imported["summary"]["media_attached"], 1)
		self.assertEqual(world.saved, [(PRODUCT, "SL01")])
		self.assertEqual(events[-3:], ["commit", "log", "commit"])

	def test_failed_attach_rolls_back_and_removes_new_files(self):
		world = World()
		with builder(world) as (service, _frappe, _, events, __, passing), tempfile.TemporaryDirectory(dir=HERE) as folder:
			path = os.path.join(folder, "copy.jpg")
			with open(path, "wb") as handle:
				handle.write(b"x")
			passing.append("CHECK-1")
			media = [row(role="featured", file_url_or_zip_path="F-PRIVATE")]
			checked = service.check(media=media)
			before = len(events)

			def failing_apply(results, created):
				created.append(path)
				raise ValueError("Featured Image is not allowed")

			with patch.object(service.media_manifest, "apply", side_effect=failing_apply):
				response = service.import_catalog(None, checked["catalog_hash"], media)
			self.assertEqual(response["status"], "Rolled Back")
			self.assertIn("Featured Image is not allowed", response["errors"][0])
			self.assertFalse(os.path.exists(path))
			self.assertEqual(events[before:], ["rollback", "log", "commit"])

	def test_bad_manifest_is_refused_before_the_lock(self):
		with builder() as (service, frappe, _, __, logs, ___):
			response = service.check(media="colour\nred\n")
			self.assertEqual((response["status"], response["stage"]), ("Refused", "shape"))
			self.assertEqual(response["media"], [])
			frappe.db.sql.assert_not_called()
			self.assertEqual(len(logs), 1)

	def test_media_runs_after_catalog_records_in_the_same_transaction(self):
		catalog = {"schema_version": 2, "product_type": "extrusion-kit", "series_name": "S", "records": {"Brand": [{}]}}
		for status, expected in (("checked", "Passed"), ("error", "Failed")):
			record = {"batch": 1, "doctype": "Brand", "catalog_name": "B", "name": "B", "status": status, "message": "", "warnings": []}
			with (
				self.subTest(status=status),
				builder() as (service, _, __, events, ___, ____),
				patch.object(service, "_existence_map", return_value={}),
				patch.object(service, "prepare_catalog", return_value=({}, [("Brand", [{}])], [])),
				patch.object(service, "_insert_batches", return_value=[record]),
				patch.object(service.media_manifest, "plan", wraps=service.media_manifest.plan) as plan,
			):
				response = service.check(catalog, [row()])
				self.assertEqual(response["status"], expected)
				self.assertEqual(response["results"][0]["status"], status)
				self.assertEqual(plan.call_count, 1 if status == "checked" else 0)
				self.assertEqual(len(response["media"]), 1 if status == "checked" else 0)
				self.assertNotEqual(response["catalog_hash"], service.catalog_hash(catalog))
				self.assertEqual(events[0], "rollback")

	def test_catalog_runs_without_media_keep_their_response_shape(self):
		with builder() as (service, _, __, ___, ____, _____):
			response = service.check({"records": []})
		self.assertNotIn("media", response)
		self.assertNotIn("media_rows", response["summary"])


if __name__ == "__main__":
	unittest.main()
