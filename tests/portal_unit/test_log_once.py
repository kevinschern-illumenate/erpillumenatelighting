"""Hardening plan 8: conditions that repeat on every tick or read log once a day, not every time.

``utils.log_error_once`` keeps one site cache key per condition and day; the Webflow spec
enrichment warnings (export v1 and v2) use ``spec-enrich-skip:<product>:<date>``. The retry tick's
missing-n8n log is covered in test_webflow_auto_push.
"""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service
from test_webflow_sync import _dependencies


class FakeCache:
	"""``frappe.cache`` double: call it for the cache, values kept in a dict."""

	def __init__(self):
		self.values = {}
		self.ttls = {}

	def __call__(self):
		return self

	def get_value(self, key):
		return self.values.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.values[key] = value
		self.ttls[key] = expires_in_sec


class LogErrorOnce(unittest.TestCase):
	def load(self):
		context = load_service(ROOT + ".utils")
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.log_error = MagicMock()
		frappe.cache = FakeCache()
		return module, frappe

	def test_one_log_per_key_per_day(self):
		module, frappe = self.load()
		self.assertTrue(module.log_error_once("k", "Title", "first"))
		self.assertFalse(module.log_error_once("k", "Title", "again"))
		self.assertTrue(module.log_error_once("other", "Title"))
		frappe.utils.nowdate = lambda: "2026-09-26"
		self.assertTrue(module.log_error_once("k", "Title", "next day"))
		self.assertEqual(
			[call.kwargs for call in frappe.log_error.call_args_list],
			[
				{"title": "Title", "message": "first"},
				{"title": "Title", "message": None},
				{"title": "Title", "message": "next day"},
			],
		)
		self.assertEqual(set(frappe.cache.values), {"k:2026-09-25", "other:2026-09-25", "k:2026-09-26"})
		self.assertGreater(frappe.cache.ttls["k:2026-09-25"], 24 * 3600)

	def test_without_a_cache_it_still_logs(self):
		module, frappe = self.load()
		frappe.cache = MagicMock(side_effect=RuntimeError("redis down"))
		self.assertTrue(module.log_error_once("k", "Title"))
		self.assertTrue(module.log_error_once("k", "Title"))
		self.assertEqual(frappe.log_error.call_count, 2)


class EnrichmentSkippedLogsOncePerProduct(unittest.TestCase):
	"""Two reads of the same products write one "Webflow Spec Enrichment Skipped" per product."""

	def load(self, path):
		deps = _dependencies()
		deps[ROOT + ".api.webflow_attributes"].ATTRIBUTE_FILTER_FIELD_SLUGS = {}
		deps[ROOT + ".api.webflow_attributes"].build_product_filter_field_data = MagicMock()
		context = load_service(path, deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.log_error = MagicMock()
		frappe.cache = FakeCache()
		frappe.get_all = MagicMock(return_value=[])
		return module, frappe

	def assert_once_per_product(self, path):
		module, frappe = self.load(path)
		doc = types.SimpleNamespace(certifications=[])
		for _read in range(2):
			for name in ("kit-a", "kit-b"):
				product = {"name": name, "product_type": "Extrusion Kit", "specifications": []}
				module._enrich_specifications_from_linked_doctypes(product, doc)
				# The read still carries the warning every time.
				self.assertEqual(len(product["_spec_warnings"]), 1)
		self.assertEqual(frappe.log_error.call_count, 2)
		self.assertEqual(
			{call.kwargs["title"] for call in frappe.log_error.call_args_list},
			{"Webflow Spec Enrichment Skipped"},
		)
		self.assertIn("kit-a", frappe.log_error.call_args_list[0].kwargs["message"])
		self.assertIn("kit-b", frappe.log_error.call_args_list[1].kwargs["message"])
		self.assertIn("spec-enrich-skip:kit-a:2026-09-25", frappe.cache.values)

		# A driver template with no active variants: the second read is quiet too.
		frappe.log_error.reset_mock()
		for _read in range(2):
			product = {"name": "drv-1", "driver_template": "DT-1", "specifications": []}
			self.assertEqual(module._enrich_variant_template_specs("Driver", product, set()), [])
			self.assertEqual(len(product["_spec_warnings"]), 1)
		frappe.log_error.assert_called_once()

	def test_export_v2(self):
		self.assert_once_per_product(ROOT + ".api.webflow_export_v2")

	def test_export_v1(self):
		self.assert_once_per_product(ROOT + ".api.webflow_export")


if __name__ == "__main__":
	unittest.main()
