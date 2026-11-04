"""Phase 0 Z1 and Z4: n8n config from site config, and the staging Webflow ID reset."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

SYNC_URL = "https://n8n.invalid/webhook/test-sync"
SPEC_URL = "https://n8n.invalid/webhook/test-spec"


class N8nConfig(unittest.TestCase):
	def test_webhook_urls_come_from_site_config_with_no_default(self):
		with load_service(ROOT + ".api.n8n_config") as (module, frappe):
			for getter in (module.sync_webhook_url, module.spec_webhook_url):
				with self.subTest(getter=getter.__name__), self.assertRaises(ValueError):
					getter()
			frappe.conf.update(n8n_sync_webhook_url=SYNC_URL, n8n_spec_webhook_url=f"  {SPEC_URL} ")
			self.assertEqual(module.sync_webhook_url(), SYNC_URL)
			self.assertEqual(module.spec_webhook_url(), SPEC_URL)

	def test_webhook_url_must_be_https(self):
		with load_service(ROOT + ".api.n8n_config") as (module, frappe):
			frappe.conf["n8n_sync_webhook_url"] = "http://n8n.invalid/webhook/x"
			with self.assertRaises(ValueError):
				module.sync_webhook_url()

	def test_secret_header_name_and_legacy_fallback(self):
		with load_service(ROOT + ".api.n8n_config") as (module, frappe):
			with self.assertRaises(ValueError):
				module.auth_headers()
			# Sites configured before Z1 keep working through the legacy key and header.
			frappe.conf["ERP-Sync-Secret-2026"] = "legacy"
			self.assertEqual(module.auth_headers(), {"ERP-Sync-Secret-2026": "legacy"})
			frappe.conf.update(n8n_sync_secret="new", n8n_sync_secret_header="STAGING-Sync-Secret")
			self.assertEqual(module.auth_headers(), {"STAGING-Sync-Secret": "new"})

	def test_environment_defaults_to_production_and_rejects_unknown(self):
		with load_service(ROOT + ".api.n8n_config") as (module, frappe):
			self.assertEqual(module.webflow_environment(), "production")
			self.assertFalse(module.is_staging())
			frappe.conf["webflow_environment"] = "Staging"
			self.assertTrue(module.is_staging())
			frappe.conf["webflow_environment"] = "stage"
			with self.assertRaises(ValueError):
				module.webflow_environment()


class StagingWebflowReset(unittest.TestCase):
	def run_reset(self, staging=True, dry_run=True):
		config = types.ModuleType(ROOT + ".api.n8n_config")
		config.is_staging = lambda: staging
		config.ENVIRONMENT_KEY = "webflow_environment"
		with load_service(ROOT + ".api.staging_webflow_reset", {config.__name__: config}) as (module, frappe):
			frappe.only_for = MagicMock()
			frappe.parse_json = lambda value: value == "true"
			frappe.logger = MagicMock()
			frappe.db.set_value = MagicMock()
			frappe.db.commit = MagicMock()
			tables = {
				"ilL-Product-Publication": [
					Record(name="PUB-1", product="P1", brand="illumenate", remote_item_id="a" * 24),
					Record(name="PUB-2", product="P2", brand="illumenate"),
				],
				"ilL-Child-Webflow-Sync-State": [
					Record(name="ROW-1", parent="P1", brand="illumenate", webflow_item_id="a" * 24)
				],
				"ilL-Webflow-Product": [Record(name="P1", webflow_item_id="a" * 24)],
				"ilL-Publish-Job": [
					Record(name="JOB-1", product="P1", brand="illumenate", operation="STAGE")
				],
			}
			frappe.get_all = lambda doctype, **kwargs: tables[doctype]
			report = module.clear_production_webflow_ids(dry_run=dry_run)
			return report, frappe

	def test_refuses_outside_staging(self):
		with self.assertRaises(ValueError):
			self.run_reset(staging=False)

	def test_dry_run_reports_without_writing(self):
		report, frappe = self.run_reset()
		self.assertTrue(report["dry_run"])
		self.assertEqual(
			report["counts"],
			{"publications": 1, "sync_targets": 1, "products": 1, "open_jobs_superseded": 1},
		)
		frappe.only_for.assert_called_once_with("System Manager")
		frappe.db.set_value.assert_not_called()
		frappe.db.commit.assert_not_called()

	def test_apply_clears_ids_and_supersedes_open_jobs(self):
		report, frappe = self.run_reset(dry_run=False)
		self.assertFalse(report["dry_run"])
		writes = {(call.args[0], call.args[1]): call.args[2] for call in frappe.db.set_value.call_args_list}
		self.assertIsNone(writes[("ilL-Product-Publication", "PUB-1")]["remote_item_id"])
		self.assertIsNone(writes[("ilL-Product-Publication", "PUB-1")]["published_on"])
		self.assertNotIn(("ilL-Product-Publication", "PUB-2"), writes)
		self.assertIsNone(writes[("ilL-Child-Webflow-Sync-State", "ROW-1")]["webflow_item_id"])
		self.assertIsNone(writes[("ilL-Webflow-Product", "P1")]["webflow_item_id"])
		self.assertEqual(writes[("ilL-Publish-Job", "JOB-1")]["state"], "SUPERSEDED")
		frappe.db.commit.assert_called_once()

	def test_string_dry_run_from_http_is_parsed(self):
		report, frappe = self.run_reset(dry_run="true")
		self.assertTrue(report["dry_run"])
		frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
