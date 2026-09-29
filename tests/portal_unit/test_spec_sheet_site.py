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
			document.get_content.return_value = b"<svg/>"
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
