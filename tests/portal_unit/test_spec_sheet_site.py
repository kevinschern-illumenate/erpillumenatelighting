"""Spec sheet site glue: the post-migrate Chromium install and the User initials field."""

import os
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

SITE = ROOT + ".api.spec_sheets.site"
INITIALS_PATCH = "illumenate_lighting.patches.spec_sheet_document_initials"


class ChromiumAfterMigrate(unittest.TestCase):
	def migrate(self, *, redis_up=True, installed=False, in_test=False, enqueue_error=None):
		connection = MagicMock()
		connection.ping.return_value = True
		if not redis_up:
			connection.ping.side_effect = ConnectionError("redis down")
		jobs = types.SimpleNamespace(get_redis_conn=MagicMock(return_value=connection))
		with (
			tempfile.TemporaryDirectory() as bench,
			patch.dict(os.environ, {}, clear=False),
			load_service(SITE, {"frappe.utils.background_jobs": jobs}) as (module, frappe),
		):
			os.environ.pop("ILL_SPEC_SHEET_CHROMIUM", None)
			frappe.in_test = in_test
			frappe.utils.get_bench_path = lambda: bench
			if installed:
				frappe.conf["spec_sheet_chromium_path"] = "/opt/chrome/headless_shell"
			frappe.enqueue = MagicMock(side_effect=enqueue_error)
			frappe.log_error = MagicMock()
			module.after_migrate()
			return frappe

	def test_queues_one_deduplicated_install_on_the_long_queue(self):
		frappe = self.migrate()
		frappe.enqueue.assert_called_once()
		self.assertEqual(frappe.enqueue.call_args.args[0], SITE + ".install_chromium")
		kwargs = frappe.enqueue.call_args.kwargs
		self.assertEqual(kwargs["queue"], "long")
		self.assertTrue(kwargs["deduplicate"])
		self.assertEqual(kwargs["job_id"], "ill_spec_sheet_install_chromium")
		self.assertNotIn("now", kwargs)

	def test_unreachable_redis_never_runs_the_download_inside_the_migration(self):
		# Frappe runs an enqueued job synchronously during migrate when Redis is down.
		frappe = self.migrate(redis_up=False)
		frappe.enqueue.assert_not_called()
		frappe.log_error.assert_not_called()

	def test_installed_or_configured_chromium_is_left_alone(self):
		self.migrate(installed=True).enqueue.assert_not_called()

	def test_test_runs_skip_the_install(self):
		self.migrate(in_test=True).enqueue.assert_not_called()

	def test_queue_failures_are_logged_not_raised(self):
		frappe = self.migrate(enqueue_error=RuntimeError("queue full"))
		frappe.log_error.assert_called_once()


class SiteBrand(unittest.TestCase):
	def file(self, content):
		handle = tempfile.NamedTemporaryFile(delete=False)
		handle.write(content)
		handle.close()
		self.addCleanup(os.unlink, handle.name)
		return handle.name

	def test_site_record_overrides_and_file_logos_resolve_through_frappe_files(self):
		record = Record(
			document_branding_json='{"notice": "Subject to change."}',
			default_document_initials="IL",
			document_logos=[Record(spec_line="TW", logo="/files/tw.svg", is_placeholder=0)],
		)
		with load_service(SITE) as (module, frappe):
			frappe.db.get_value.side_effect = lambda doctype, filters, field: {
				"ilL-Webflow-Brand": "ilLumenate",
				"File": "FILE-0001",
			}[doctype]
			document = MagicMock()
			document.as_dict.return_value = record
			document.get_full_path.return_value = self.file(b"<svg/>")
			frappe.get_doc.return_value = document
			brand = module.site_brand()
			self.assertEqual(brand["notice"], "Subject to change.")
			self.assertEqual(brand["default_document_initials"], "IL")
			self.assertEqual(brand["logos"]["TW"]["file"], "/files/tw.svg")
			self.assertEqual(brand["file_assets"].get("/files/tw.svg"), (b"<svg/>", "image/svg+xml"))

	def test_missing_file_record_is_an_error(self):
		with load_service(SITE) as (module, frappe):
			frappe.db.get_value.return_value = None
			with self.assertRaisesRegex(ValueError, "No File record"):
				module.file_assets().get("/private/files/missing.png")


class Row(Record):
	def __getattr__(self, name):
		return self.get(name)


class SpecAssetValidation(unittest.TestCase):
	FPO_SVG = b'<svg><path fill="#EC008C" d="M0 0h1v1z"/></svg>'

	def validate(self, rows, before=None, files=None):
		files = files or {}
		doc = Row(spec_assets=rows)
		doc.get_doc_before_save = lambda: Row(spec_assets=before) if before is not None else None
		with tempfile.TemporaryDirectory() as folder, load_service(SITE) as (module, frappe):
			paths = {}
			for url, content in files.items():
				path = os.path.join(folder, url.rsplit("/", 1)[-1])
				with open(path, "wb") as handle:
					handle.write(content)
				paths[url] = path
			frappe.db.get_value.side_effect = lambda doctype, filters, field: (
				filters["file_url"] if filters["file_url"] in paths else None
			)
			frappe.get_doc.side_effect = lambda doctype, name: types.SimpleNamespace(
				get_full_path=lambda: paths[name]
			)
			module.stamp_spec_assets(doc)
			return frappe

	def test_new_rows_get_a_hash_and_fpo_svgs_become_placeholders(self):
		photo = Row(name="new-1", idx=1, file="/files/hero.png", sha256=None, is_placeholder=0)
		drawing = Row(name="new-2", idx=2, file="/files/side.svg", sha256=None, is_placeholder=0)
		self.validate(
			[photo, drawing], files={"/files/hero.png": b"\x89PNG", "/files/side.svg": self.FPO_SVG}
		)
		self.assertEqual(len(photo.sha256), 64)
		self.assertFalse(photo.is_placeholder)
		self.assertTrue(drawing.is_placeholder)
		self.assertIn("FPO", drawing.placeholder_note)

	def test_unchanged_rows_are_not_reread_and_replaced_files_are(self):
		kept = Row(name="row-1", idx=1, file="/files/a.svg", sha256="a" * 64)
		replaced = Row(name="row-2", idx=2, file="/files/new.svg", sha256="b" * 64)
		before = [Row(name="row-1", file="/files/a.svg"), Row(name="row-2", file="/files/old.svg")]
		self.validate([kept, replaced], before=before, files={"/files/new.svg": b"<svg/>"})
		self.assertEqual(kept.sha256, "a" * 64)
		self.assertNotEqual(replaced.sha256, "b" * 64)

	def test_links_and_unsupported_files_are_refused(self):
		for file, message in (
			("https://cdn.example.com/hero.png", "upload the file"),
			("/files/hero.tif", "Unsupported asset type"),
			("/files/missing.png", "No File record"),
			("/files/script.svg", "contains <script>"),
		):
			with self.subTest(file=file), self.assertRaisesRegex(ValueError, message):
				self.validate(
					[Row(name="r", idx=1, file=file, sha256=None, is_placeholder=0)],
					files={"/files/script.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'},
				)


class BrandValidation(unittest.TestCase):
	def validate(self, **values):
		doc = Row({"brand_code": "illumenate", "document_logos": [], **values})
		doc.as_dict = lambda: dict(doc)
		with load_service(SITE) as (module, _frappe):
			module.validate_document_branding(doc)

	def test_valid_branding_passes(self):
		self.validate(
			document_branding_json='{"notice": "Subject to change."}',
			document_logos=[Row(spec_line="TW", logo="/files/tw.svg")],
		)

	def test_bad_json_keys_and_linked_logos_are_refused(self):
		for values, message in (
			({"document_branding_json": "{not json"}, "Document Branding"),
			({"document_branding_json": '{"logos": {}}'}, "Unknown document branding keys"),
			({"document_logos": [Row(spec_line="TW", logo="https://example.com/tw.svg")]}, "uploaded file"),
			({"document_logos": [Row(spec_line="TW", logo="/files/tw.ai")]}, "Unsupported asset type"),
		):
			with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
				self.validate(**values)


class LegacyImages(unittest.TestCase):
	MODULE = ROOT + ".api.spec_sheets.legacy_images"

	def test_values_are_classified_by_where_the_file_lives(self):
		with load_service(self.MODULE) as (module, _frappe):
			classify = module.classify
			self.assertEqual(classify("/files/a.png"), ("file", "/files/a.png"))
			self.assertEqual(classify("/private/files/a.png?fid=1"), ("file", "/private/files/a.png"))
			self.assertEqual(classify("https://erp.test/files/a.png", "erp.test"), ("file", "/files/a.png"))
			self.assertEqual(classify("https://cdn.test/a.png", "erp.test")[0], "external")
			self.assertEqual(classify("/Users/design/Links/SH01 Hero.tif")[0], "local")
			self.assertEqual(classify("  ")[0], "blank")

	def test_plan_moves_files_once_and_reports_everything_else(self):
		values = {
			"custom_image_hero": "https://erp.test/files/hero.png",
			"custom_image_dimensions_1": "/files/cross.svg",
			"custom_image_dimensions_2": "/files/side.svg",
			"custom_dimensions_2_title": " Side View ",
			"custom_image_dimensions_3": "/Users/design/Links/clip.ai",
			"custom_image_acc_dims_1": "/files/clip.tif",
			"custom_image_acc_dims_2": "/files/gone.svg",
			"custom_image_ul_rated_icon": "/files/ul.svg",
		}
		with load_service(self.MODULE) as (module, _frappe):
			rows, issues = module.plan_product(
				values, {"/files/cross.svg"}, "erp.test", file_exists=lambda url: url != "/files/gone.svg"
			)
		self.assertEqual(
			[(row["asset_role"], row["file"], row["title"], row["display_order"]) for row in rows],
			[("Hero", "/files/hero.png", "", 1), ("Dimension Drawing", "/files/side.svg", "Side View", 2)],
		)
		problems = {issue["column"]: issue["problem"] for issue in issues}
		self.assertIn("Local path", problems["custom_image_dimensions_3"])
		self.assertIn("Convert", problems["custom_image_acc_dims_1"])
		self.assertIn("No File record", problems["custom_image_acc_dims_2"])
		self.assertIn("Shared artwork", problems["custom_image_ul_rated_icon"])
		self.assertNotIn("custom_image_dimensions_1", problems)

	def test_sites_without_the_customize_form_columns_do_nothing(self):
		with load_service(self.MODULE) as (module, frappe):
			frappe.get_meta = lambda doctype: types.SimpleNamespace(has_field=lambda name: False)
			self.assertEqual(module.run(dry_run=False), {"products": 0, "moved": 0, "issues": []})
			frappe.get_all.assert_not_called()


class DocumentInitialsField(unittest.TestCase):
	def test_user_field_is_created_idempotently_after_last_name(self):
		created = []
		custom_fields = types.SimpleNamespace(
			create_custom_fields=lambda definitions, update=True: created.append((definitions, update))
		)
		with load_service(
			INITIALS_PATCH, {"frappe.custom.doctype.custom_field.custom_field": custom_fields}
		) as (
			module,
			_frappe,
		):
			module.execute()
		((definitions, update),) = created
		self.assertTrue(update)
		(field,) = definitions["User"]
		self.assertEqual(field["fieldname"], "ill_document_initials")
		self.assertEqual(field["insert_after"], "last_name")
		self.assertEqual(field["fieldtype"], "Data")


if __name__ == "__main__":
	unittest.main()
