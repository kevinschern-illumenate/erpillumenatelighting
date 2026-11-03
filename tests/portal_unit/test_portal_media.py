"""Hardening plan 4.3–4.7: purpose/captions, thumbnails, gallery, dealer logo and staff HEIC."""

import hashlib
import importlib.util
import io
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


def has_module(name):
	try:
		return importlib.util.find_spec(name) is not None
	except ValueError:
		return False


class Doc(dict):
	"""A document double whose attribute writes are visible through ``get``."""

	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value

	def save(self, **kwargs):
		self.setdefault("_saved", 0)
		self["_saved"] += 1
		return self

	def insert(self, **kwargs):
		return self


def flags(**overrides):
	values = {
		"upload_purpose_enabled": True,
		"thumbnails_enabled": True,
		"gallery_enabled": True,
		"dealer_logo_enabled": True,
		"staff_heic_enabled": True,
		"heic_uploads_enabled": True,
		**overrides,
	}
	return types.SimpleNamespace(**{key: (lambda value=value: value) for key, value in values.items()})


def media(**overrides):
	return load_service(ROOT + ".portal.media", {ROOT + ".portal.site_flags": flags(**overrides)})


class PurposeAndCaption(unittest.TestCase):
	def test_purpose_is_one_of_the_listed_values(self):
		with media() as (module, _frappe):
			self.assertEqual(module.clean_purpose(" site PHOTO "), "Site photo")
			self.assertEqual(module.clean_purpose(""), "")
			self.assertEqual(module.clean_purpose(None), "")
			with self.assertRaisesRegex(ValueError, "listed purposes"):
				module.clean_purpose("<script>")

	def test_caption_drops_control_characters_and_is_bounded(self):
		with media() as (module, _frappe):
			self.assertEqual(module.clean_caption("  Lobby\x00 cove\nnorth  "), "Lobby cove\nnorth")
			self.assertEqual(module.clean_caption("x" * 280), "x" * 280)
			with self.assertRaisesRegex(ValueError, "280"):
				module.clean_caption("x" * 281)

	def test_annotations_only_include_supplied_values_and_respect_the_kill_switch(self):
		with media() as (module, _frappe):
			self.assertEqual(module.annotations(), {})
			self.assertEqual(module.annotations("PO", None), {"purpose": "PO"})
			self.assertEqual(module.annotations(None, " Note "), {"caption": "Note"})
		with media(upload_purpose_enabled=False) as (module, _frappe):
			self.assertEqual(module.annotations("not even valid", "x" * 999), {})


class LineDocumentAnnotations(unittest.TestCase):
	def dependencies(self, schedule, line):
		return {
			ROOT + ".portal.configuration": types.SimpleNamespace(
				resolve_line=MagicMock(return_value=line), schedule_context=MagicMock(return_value=schedule)
			),
			ROOT + ".portal.site_flags": flags(),
		}

	def test_attach_stores_purpose_and_caption_on_new_documents(self):
		schedule = Doc(name="S", doctype="ilL-Project-Fixture-Schedule", modified="now")
		line = Record(line_key="L1", manufacturer_type="OTHER")
		finalize = MagicMock(
			return_value=[{"name": "F1", "file_name": "a.jpg", "sha256": "h", "purpose": "Site photo", "caption": ""}]
		)
		deps = {**self.dependencies(schedule, line), ROOT + ".portal.files": types.SimpleNamespace(finalize_files=finalize)}
		with load_service(ROOT + ".portal.line_documents", deps) as (module, frappe):
			frappe.get_all.return_value = []
			inserted = []
			frappe.get_doc.side_effect = lambda values: inserted.append(values) or MagicMock()
			module.attach("S", "L1", '["F1"]', expected_modified="now", purpose=None, caption="North wall")
			self.assertEqual(inserted[0]["purpose"], "Site photo")
			self.assertEqual(inserted[0]["caption"], "North wall")
			inserted.clear()
			module.attach("S", "L1", '["F1"]', expected_modified="now", purpose="Existing fixture")
			self.assertEqual(inserted[0]["purpose"], "Existing fixture")

	def test_attach_rejects_an_unlisted_purpose_before_finalizing(self):
		finalize = MagicMock()
		deps = {
			**self.dependencies(Doc(name="S", modified="now"), Record()),
			ROOT + ".portal.files": types.SimpleNamespace(finalize_files=finalize),
		}
		with load_service(ROOT + ".portal.line_documents", deps) as (module, _frappe):
			with self.assertRaisesRegex(ValueError, "listed purposes"):
				module.attach("S", "L1", '["F1"]', expected_modified="now", purpose="Bogus")
		finalize.assert_not_called()

	def test_annotate_checks_the_concurrency_token_and_never_touches_the_file(self):
		schedule = Doc(name="S", modified="now")
		with load_service(ROOT + ".portal.line_documents", self.dependencies(schedule, Record())) as (module, frappe):
			frappe.get_doc.return_value = Doc(name="D", schedule="S", active=1, file="F")
			with self.assertRaisesRegex(ValueError, "Schedule changed"):
				module.annotate("D", "stale", purpose="PO")
			frappe.db.set_value.assert_not_called()
			result = module.annotate("D", "now", purpose="po", caption="Signed")
			frappe.db.set_value.assert_called_once_with(
				"ilL-Line-Document", "D", {"purpose": "PO", "caption": "Signed"}
			)
			self.assertEqual(result["purpose"], "PO")
			self.assertEqual(schedule["_saved"], 1)

	def test_annotate_refuses_removed_documents(self):
		schedule = Doc(name="S", modified="now")
		with load_service(ROOT + ".portal.line_documents", self.dependencies(schedule, Record())) as (module, frappe):
			frappe.get_doc.return_value = Doc(name="D", schedule="S", active=0)
			with self.assertRaisesRegex(ValueError, "removed"):
				module.annotate("D", "now", caption="x")

	def test_clone_copies_purpose_and_caption(self):
		with load_service(ROOT + ".portal.line_documents", self.dependencies(None, None)) as (module, frappe):
			frappe.get_all.return_value = [
				Record(name="SRC", file="F", file_name="a.jpg", sha256="h", title="a", is_primary=0, purpose="PO", caption="c")
			]
			module.clone("OLD", Record(line_key="L1"), "NEW", Record(line_key="L2"))
			data = frappe.get_doc.call_args.args[0]
			self.assertEqual((data["purpose"], data["caption"]), ("PO", "c"))

	def test_list_documents_adds_thumbnails_and_purposes(self):
		schedule = Doc(name="S", modified="now")
		line = Record(line_key="L1", manufacturer_type="OTHER")
		with load_service(ROOT + ".portal.line_documents", self.dependencies(schedule, line)) as (module, frappe):
			frappe.get_all.side_effect = [
				[Record(name="D", file="F", file_name="a.jpg")],
				[Record(file="F", thumbnail="T")],
				[Record(name="T", file_url="/private/files/a.thumb.webp")],
			]
			result = module.list_documents("S", "L1")
			self.assertEqual(result["documents"][0]["thumbnail_url"], "/private/files/a.thumb.webp")
			self.assertIn("Site photo", result["purposes"])


class Thumbnails(unittest.TestCase):
	def test_failure_never_blocks_the_upload(self):
		with media() as (module, frappe):
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="tb")
			with patch.object(module, "make_thumbnail", side_effect=OSError("decoder")):
				self.assertIsNone(module.store_thumbnail(Record(name="U", mime_type="image/jpeg"), "a.jpg", b"x"))
			frappe.log_error.assert_called_once()

	def test_pdfs_and_disabled_sites_get_no_thumbnail(self):
		with media() as (module, frappe):
			with patch.object(module, "make_thumbnail") as make:
				self.assertIsNone(module.store_thumbnail(Record(mime_type="application/pdf"), "a.pdf", b"%PDF"))
			make.assert_not_called()
		with media(thumbnails_enabled=False) as (module, frappe):
			with patch.object(module, "make_thumbnail") as make:
				self.assertIsNone(module.store_thumbnail(Record(mime_type="image/png"), "a.png", b"x"))
				self.assertEqual(module.thumbnail_urls(["F"]), {})
			make.assert_not_called()
			frappe.get_all.assert_not_called()

	def test_thumbnail_is_a_private_file_owned_by_the_upload_artifact(self):
		with media() as (module, frappe):
			created = []

			def get_doc(values):
				created.append(values)
				return Doc(name="T", is_private=1, file_url="/private/files/a.thumb.webp")

			frappe.get_doc.side_effect = get_doc
			with patch.object(module, "make_thumbnail", return_value=b"webp"):
				self.assertEqual(module.store_thumbnail(Record(name="U", mime_type="image/jpeg"), "site/a.jpg", b"x"), "T")
			self.assertEqual(created[0]["file_name"], "a.thumb.webp")
			self.assertEqual(created[0]["is_private"], 1)
			self.assertEqual(created[0]["owner"], "Administrator")
			self.assertEqual((created[0]["attached_to_doctype"], created[0]["attached_to_name"]), ("ilL-Portal-Upload", "U"))

	def test_a_public_storage_result_is_not_linked(self):
		with media() as (module, frappe):
			frappe.get_doc.return_value = Doc(name="T", is_private=0, file_url="/files/a.webp")
			with patch.object(module, "make_thumbnail", return_value=b"webp"):
				self.assertIsNone(module.store_thumbnail(Record(name="U", mime_type="image/png"), "a.png", b"x"))

	def test_upload_records_purpose_caption_and_thumbnail(self):
		created = []

		def get_doc(values):
			created.append(values)
			doc = Doc({k: v for k, v in values.items() if k != "doctype"}, name=values["doctype"])
			if values["doctype"] == "File":
				doc.update(is_private=1, file_url="/private/files/a.jpg")
			return doc

		metadata = {"filename": "a.jpg", "size": 1, "sha256": "0" * 64, "mime_type": "image/jpeg", "pages": None}
		with load_service(ROOT + ".portal.files", {ROOT + ".portal.site_flags": flags()}) as (module, frappe):
			frappe.request = Record(files={"file": Record(filename="a.jpg", stream=io.BytesIO(b"x"))})
			frappe.get_doc = MagicMock(side_effect=get_doc)
			with (
				patch.object(module, "validate_content", return_value=metadata),
				patch.object(module, "normalize_upload", side_effect=lambda name, body: (name, body)),
				patch(ROOT + ".portal.media.store_thumbnail", return_value="THUMB") as thumb,
			):
				module.upload(purpose="site photo", caption="Lobby")
			artifact = created[0]
			self.assertEqual((artifact["purpose"], artifact["caption"]), ("Site photo", "Lobby"))
			thumb.assert_called_once()
			self.assertEqual(thumb.call_args.args[1:], ("a.jpg", b"x"))

	def test_thumbnail_urls_map_originals_to_their_thumbnail(self):
		with media() as (module, frappe):
			frappe.get_all.side_effect = [
				[Record(file="F1", thumbnail="T1"), Record(file="F2", thumbnail="T2")],
				[Record(name="T1", file_url="/private/files/1.webp")],
			]
			self.assertEqual(module.thumbnail_urls(["F1", "F2", None]), {"F1": "/private/files/1.webp"})

	def test_backfill_skips_changed_bytes_and_is_rerunnable(self):
		with media() as (module, frappe):
			good = Doc(name="U1", file="F1", sha256=hashlib.sha256(b"ok").hexdigest(), mime_type="image/png")
			changed = Doc(name="U2", file="F2", sha256="stale", mime_type="image/png")
			files = {"F1": MagicMock(file_name="a.png", get_content=lambda: b"ok"), "F2": MagicMock(get_content=lambda: b"new")}
			frappe.get_all.return_value = [Record(name="U1"), Record(name="U2")]
			frappe.get_doc.side_effect = lambda doctype, name: {"U1": good, "U2": changed}.get(name) or files[name]
			with patch.object(module, "store_thumbnail", return_value="T1") as store:
				self.assertEqual(module.backfill_thumbnails(limit=10), 1)
			store.assert_called_once_with(good, "a.png", b"ok")
			frappe.db.set_value.assert_called_once_with("ilL-Portal-Upload", "U1", "thumbnail", "T1", update_modified=False)
			self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["thumbnail"], ["is", "not set"])

	@unittest.skipUnless(has_module("PIL"), "Pillow is not installed")
	def test_thumbnail_is_upright_small_webp_without_metadata(self):
		from PIL import Image

		source = Image.new("RGB", (2000, 1000), "red")
		exif = Image.Exif()
		exif[0x0112] = 6  # rotate 90° clockwise on display
		exif[0x8825] = {2: (1, 2, 3)}  # GPS
		buffer = io.BytesIO()
		source.save(buffer, format="JPEG", exif=exif)
		with media() as (module, _frappe):
			data = module.make_thumbnail(buffer.getvalue())
			self.assertIsNone(module.make_thumbnail(b"%PDF-1.7"))
		with Image.open(io.BytesIO(data)) as thumb:
			self.assertEqual(thumb.format, "WEBP")
			self.assertEqual(thumb.size, (240, 480))
			self.assertFalse(thumb.getexif())


class PrivateFileGuard(unittest.TestCase):
	def test_thumbnail_of_a_cloned_line_document_follows_the_original(self):
		frappe_file = types.ModuleType("frappe.core.doctype.file.file")
		frappe_file.File = object
		frappe_file.has_permission = MagicMock(return_value=False)
		file_access = MagicMock(return_value=True)
		deps = {
			"frappe.core": types.ModuleType("frappe.core"),
			"frappe.core.doctype": types.ModuleType("frappe.core.doctype"),
			"frappe.core.doctype.file": types.ModuleType("frappe.core.doctype.file"),
			"frappe.core.doctype.file.file": frappe_file,
			ROOT + ".portal.files": types.SimpleNamespace(has_permission=MagicMock(return_value=False)),
			ROOT + ".portal.line_documents": types.SimpleNamespace(file_access=file_access),
		}
		with load_service(ROOT + ".portal.private_file", deps) as (module, frappe):
			frappe.get_doc.return_value = Record(name="U", file="ORIG", thumbnail="THUMB")
			thumb = Record(name="THUMB", attached_to_doctype="ilL-Portal-Upload", attached_to_name="U")
			self.assertTrue(module._portal_file_decision(thumb, "read", "viewer@example.com"))
			file_access.assert_called_with("ORIG", "viewer@example.com")
			original = Record(name="ORIG", attached_to_doctype="ilL-Portal-Upload", attached_to_name="U")
			module._portal_file_decision(original, "read", "viewer@example.com")
			file_access.assert_called_with("ORIG", "viewer@example.com")
			file_access.return_value = False
			self.assertFalse(module._portal_file_decision(thumb, "read", "stranger@example.com"))


def gallery_dependencies(readable=True, editable=True, request_write=True):
	access = types.SimpleNamespace(
		can_read_project=MagicMock(return_value=readable),
		can_read_schedule=MagicMock(side_effect=lambda doc, user=None: doc.name != "HIDDEN"),
		can_edit_schedule=MagicMock(return_value=editable),
	)
	configuration = types.SimpleNamespace(
		schedule_context=MagicMock(side_effect=lambda name, **kw: SCHEDULES[name]),
		resolve_line=MagicMock(side_effect=lambda schedule, key: schedule.lines[0]),
	)
	files = types.SimpleNamespace(_context_access=MagicMock(return_value=request_write))
	return {
		ROOT + ".portal.site_flags": flags(),
		ROOT + ".portal.access": access,
		ROOT + ".portal.configuration": configuration,
		ROOT + ".portal.files": files,
	}


SCHEDULES = {
	"S1": Doc(
		name="S1",
		schedule_name="Lobby",
		modified="m1",
		ill_project="P",
		is_locked=0,
		lines=[Record(name="row1", line_key="L1", line_id="A1")],
	),
	"HIDDEN": Doc(name="HIDDEN", modified="m2", ill_project="P", lines=[]),
}


class Gallery(unittest.TestCase):
	def run_gallery(self, deps, **kwargs):
		with load_service(ROOT + ".portal.media", deps) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.side_effect = lambda doctype, name: SCHEDULES.get(name, Record(name=name))

			def get_all(doctype, **kw):
				if doctype == "ilL-Project-Fixture-Schedule":
					return ["S1", "HIDDEN"]
				if doctype == "ilL-Line-Document":
					self.line_filters = kw["filters"]
					return [
						Record(name="D1", schedule="S1", line_key="L1", file="F1", file_name="site.JPG", title="site", purpose="Site photo", caption="<b>x</b>"),
						Record(name="D2", schedule="S1", line_key="L1", file="F2", file_name="spec.pdf", title="spec"),
					]
				if doctype == "ilL-Portal-Upload":
					return [Record(file="F1", thumbnail="T1")]
				if doctype == "File":
					names = kw["filters"]["name"][1]
					return [Record(name=n, file_url=f"/private/files/{n}") for n in names]
				if doctype == "ilL-Document-Request":
					return [Record(name="R1", request_type="Drawing", status="Submitted")]
				return []

			frappe.get_all.side_effect = get_all
			return module.gallery(**kwargs)

	def test_project_gallery_lists_only_readable_images_with_rights(self):
		result = self.run_gallery(gallery_dependencies(), project="P")
		self.assertEqual(self.line_filters["schedule"], ["in", ["S1"]])
		self.assertEqual([item["name"] for item in result["items"]], ["D1"])
		item = result["items"][0]
		self.assertEqual(item["thumbnail_url"], "/private/files/T1")
		self.assertEqual(item["image_url"], "/private/files/F1")
		self.assertEqual(item["line_id"], "A1")
		self.assertEqual(item["caption"], "<b>x</b>")  # escaped by the client, never rendered as HTML
		self.assertTrue(item["can_edit"])
		self.assertEqual(result["requests"][0]["name"], "R1")

	def test_viewers_get_no_edit_rights_or_request_targets(self):
		result = self.run_gallery(gallery_dependencies(editable=False), project="P")
		self.assertFalse(result["items"][0]["can_edit"])
		self.assertEqual(result["requests"], [])

	def test_unreadable_project_is_refused(self):
		with self.assertRaises(PermissionError):
			self.run_gallery(gallery_dependencies(readable=False), project="P")

	def test_line_gallery_filters_by_line(self):
		self.run_gallery(gallery_dependencies(), schedule_name="S1", line_key="L1")
		self.assertEqual(self.line_filters["line_key"], "L1")
		self.assertEqual(self.line_filters["schedule"], ["in", ["S1"]])

	def test_kill_switch_returns_an_empty_disabled_gallery(self):
		deps = {**gallery_dependencies(), ROOT + ".portal.site_flags": flags(gallery_enabled=False)}
		with load_service(ROOT + ".portal.media", deps) as (module, frappe):
			self.assertFalse(module.gallery(project="P")["enabled"])
			frappe.get_all.assert_not_called()


class AttachToRequest(unittest.TestCase):
	def attach(self, deps=None, request=None, existing=(), content=b"photo", source=None):
		source = source or Doc(name="D1", schedule="S1", file="F1", file_name="site.jpg", active=1, sha256=hashlib.sha256(b"photo").hexdigest(), purpose="Site photo", caption="c")
		request = request or Doc(name="R1", status="Submitted", project="P")
		created = []
		with load_service(ROOT + ".portal.media", deps or gallery_dependencies()) as (module, frappe):
			frappe.db.exists.return_value = True

			def get_doc(*args):
				if isinstance(args[0], dict):
					created.append(args[0])
					return Doc(args[0], name=f"NEW{len(created)}", is_private=1, file_url="/private/files/site.jpg")
				return {"ilL-Line-Document": source, "ilL-Document-Request": request, "File": MagicMock(get_content=lambda: content)}[args[0]]

			frappe.get_doc.side_effect = get_doc
			frappe.get_all.return_value = [Record(sha256=s) for s in existing]
			result = module.attach_to_request("D1", "R1")
		return result, created

	def test_copies_the_photo_as_a_new_private_upload_of_the_request(self):
		result, created = self.attach()
		artifact, file = created
		self.assertEqual((artifact["parent_type"], artifact["parent_name"], artifact["state"]), ("ilL-Document-Request", "R1", "FINALIZED"))
		self.assertEqual(artifact["purpose"], "Site photo")
		self.assertEqual((file["is_private"], file["owner"], file["attached_to_doctype"]), (1, "Administrator", "ilL-Portal-Upload"))
		self.assertFalse(result["already_attached"])

	def test_duplicate_is_reported_not_stored_twice(self):
		result, created = self.attach(existing=[hashlib.sha256(b"photo").hexdigest()])
		self.assertTrue(result["already_attached"])
		self.assertEqual(created, [])

	def test_request_rules_are_enforced(self):
		with self.assertRaises(PermissionError):
			self.attach(deps=gallery_dependencies(request_write=False))
		with self.assertRaises(PermissionError):
			self.attach(request=Doc(name="R1", status="Submitted", project="OTHER"))
		with self.assertRaisesRegex(ValueError, "no longer accepts"):
			self.attach(request=Doc(name="R1", status="Completed", project="P"))
		with self.assertRaisesRegex(ValueError, "at most 10"):
			self.attach(existing=[str(n) for n in range(10)])
		with self.assertRaisesRegex(ValueError, "bytes changed"):
			self.attach(content=b"tampered")
		with self.assertRaisesRegex(ValueError, "Only active photos"):
			self.attach(source=Doc(name="D1", schedule="S1", file="F1", file_name="spec.pdf", active=1, sha256="h"))


class DealerLogo(unittest.TestCase):
	def store(self, artifact, mime="image/png", content=b"logo"):
		file = Doc(name="F1", attached_to_doctype="ilL-Portal-Upload", attached_to_name="U1", is_private=1, get_content=lambda: content)
		artifact = Doc({"name": "U1", "requested_by": "buyer@example.com", "file": "F1", "state": "STAGING", "sha256": hashlib.sha256(b"logo").hexdigest(), "mime_type": mime, **artifact})
		created = []
		with media() as (module, frappe):

			def get_doc(*args):
				if isinstance(args[0], dict):
					created.append(args[0])
					return Doc(args[0], file_url="/files/dealer-logo.png")
				return {"File": file, "ilL-Portal-Upload": artifact}[args[0]]

			frappe.get_doc.side_effect = get_doc
			with patch.object(module, "normalize_logo", return_value=(b"png", 400, 100)):
				result = module.store_dealer_logo("F1", "CUST")
			return result, created, artifact, frappe

	def test_logo_is_reencoded_published_and_linked(self):
		result, created, artifact, frappe = self.store({})
		logo = created[0]
		self.assertEqual(logo["content"], b"png")
		self.assertEqual(logo["is_private"], 0)
		self.assertEqual((logo["attached_to_doctype"], logo["attached_to_name"], logo["attached_to_field"]), ("Customer", "CUST", "dealer_logo"))
		frappe.db.set_value.assert_called_once_with("Customer", "CUST", "dealer_logo", "/files/dealer-logo.png")
		self.assertEqual((artifact.parent_type, artifact.state, artifact.purpose), ("Customer", "FINALIZED", "Logo"))
		self.assertEqual(result, {"dealer_logo": "/files/dealer-logo.png", "width": 400, "height": 100})

	def test_only_the_callers_own_unbound_image_upload_is_accepted(self):
		for change in ({"requested_by": "other@example.com"}, {"parent_type": "Issue", "parent_name": "I1"}, {"state": "FINALIZED"}):
			with self.subTest(change=change), self.assertRaises(PermissionError):
				self.store(change)
		with self.assertRaisesRegex(ValueError, "PNG or JPEG"):
			self.store({}, mime="application/pdf")
		with self.assertRaisesRegex(ValueError, "changed"):
			self.store({}, content=b"swapped")

	def test_endpoint_requires_a_company_dealer_and_supports_removal(self):
		company = MagicMock(return_value="CUST")
		available = MagicMock(return_value=True)
		deps = {
			ROOT + ".portal.media": types.SimpleNamespace(dealer_logo_available=available, store_dealer_logo=MagicMock(return_value={"dealer_logo": "/files/x.png"})),
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=MagicMock()),
			ROOT + ".portal.access": types.SimpleNamespace(get_actor=MagicMock()),
		}
		with load_service(ROOT + ".portal.accounts", deps) as (module, frappe):
			with patch.object(module, "company", company):
				self.assertEqual(module.set_dealer_logo(remove="1"), {"success": True, "dealer_logo": None})
				frappe.db.set_value.assert_called_once_with("Customer", "CUST", "dealer_logo", None)
				self.assertEqual(module.set_dealer_logo(file_id="F1")["dealer_logo"], "/files/x.png")
				with self.assertRaisesRegex(ValueError, "Choose"):
					module.set_dealer_logo()
				available.return_value = False
				with self.assertRaises(PermissionError):
					module.set_dealer_logo(file_id="F1")

	@unittest.skipUnless(has_module("PIL"), "Pillow is not installed")
	def test_normalize_logo_fits_the_title_block_box(self):
		from PIL import Image

		buffer = io.BytesIO()
		Image.new("RGBA", (3000, 1000), (0, 0, 0, 0)).save(buffer, format="PNG")
		with media() as (module, _frappe):
			data, width, height = module.normalize_logo(buffer.getvalue())
			with self.assertRaisesRegex(ValueError, "Logo could not be read|PNG or JPEG"):
				module.normalize_logo(b"%PDF-1.7")
		self.assertEqual((width, height), (1200, 400))
		with Image.open(io.BytesIO(data)) as image:
			self.assertEqual((image.format, image.mode), ("PNG", "RGBA"))


class StaffHeic(unittest.TestCase):
	def file(self, **values):
		doc = Doc({"file_name": "hero.HEIC", "content": b"heic", "attached_to_doctype": "ilL-Fixture-Template", "attached_to_field": "hero_image", **values})
		doc["get_content"] = lambda: doc["content"]
		return doc

	def test_template_hero_heic_becomes_jpeg_before_storage(self):
		with media() as (module, _frappe):
			with patch.object(module, "normalize_upload", return_value=("hero.jpg", b"jpeg")) as normalize:
				doc = self.file()
				module.convert_staff_heic(doc)
			normalize.assert_called_once_with("hero.HEIC", b"heic")
			self.assertEqual((doc.file_name, doc.content, doc.decode), ("hero.jpg", b"jpeg", False))

	def test_gallery_rows_and_webflow_images_are_covered(self):
		with media() as (module, _frappe):
			for doctype, field in (("ilL-Webflow-Product", "featured_image"), ("ilL-Webflow-Product", "image"), ("ilL-Tape-Neon-Template", "image")):
				with self.subTest(field=field), patch.object(module, "normalize_upload", return_value=("a.jpg", b"j")) as normalize:
					module.convert_staff_heic(self.file(attached_to_doctype=doctype, attached_to_field=field))
					normalize.assert_called_once()

	def test_everything_else_is_untouched(self):
		cases = (
			{"attached_to_doctype": "Issue"},
			{"attached_to_field": "spec_sheet"},
			{"attached_to_field": None},
			{"file_name": "hero.jpg"},
			{"content": b""},
			{"is_folder": 1},
		)
		with media() as (module, _frappe):
			for change in cases:
				with self.subTest(change=change), patch.object(module, "normalize_upload") as normalize:
					module.convert_staff_heic(self.file(**change))
					normalize.assert_not_called()
		with media(staff_heic_enabled=False) as (module, _frappe):
			with patch.object(module, "normalize_upload") as normalize:
				module.convert_staff_heic(self.file())
			normalize.assert_not_called()

	def test_undecodable_heic_is_refused_with_the_helper_message(self):
		with media() as (module, _frappe):
			with patch.object(module, "normalize_upload", side_effect=ValueError("Image content does not match its filename")):
				with self.assertRaisesRegex(ValueError, "does not match"):
					module.convert_staff_heic(self.file())

	def test_portal_file_converts_before_frappe_writes_the_bytes(self):
		from pathlib import Path

		source = (Path(__file__).resolve().parents[2] / "illumenate_lighting/illumenate_lighting/portal/private_file.py").read_text()
		body = source[source.index("def before_insert") :]
		self.assertLess(body.index("convert_staff_heic(self)"), body.index("super().before_insert()"))


if __name__ == "__main__":
	unittest.main()
