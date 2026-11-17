"""A product save keeps the sync's own fields as the database holds them (2026-11-12)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Row(Record):
	def set(self, key, value):
		self[key] = value


class SyncIdentity(unittest.TestCase):
	def product(self, flags=None):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		model = types.ModuleType("frappe.model")
		model.document = document
		context = load_service(
			ROOT + ".doctype.ill_webflow_product.ill_webflow_product",
			{"frappe.model": model, "frappe.model.document": document},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.db.get_value = MagicMock(
			return_value=Record(
				webflow_item_id="a" * 24, sync_status="Synced", last_synced_at="t", sync_error_message=None
			)
		)
		frappe.get_all = MagicMock(
			return_value=[
				Record(
					brand="illumenate",
					webflow_item_id="a" * 24,
					sync_status="Synced",
					last_synced_at="t",
					sync_error_message=None,
				)
			]
		)
		doc = module.ilLWebflowProduct()
		doc.doctype, doc.name = "ilL-Webflow-Product", "kit-ra03"
		doc.flags = Record(flags or {})
		doc.webflow_item_id, doc.sync_status = "", "Pending"
		doc.sync_targets = [
			Row(brand="illumenate", webflow_item_id="", sync_status="Pending"),
			Row(brand="lighting_206", webflow_item_id=""),
		]
		doc.get = lambda key, default=None: getattr(doc, key, default)
		doc.set = lambda key, value: setattr(doc, key, value)
		return doc

	def test_a_stale_form_cannot_blank_the_item_id(self):
		doc = self.product()
		doc.keep_sync_identity()
		self.assertEqual((doc.webflow_item_id, doc.sync_status), ("a" * 24, "Synced"))
		self.assertEqual(doc.sync_targets[0]["webflow_item_id"], "a" * 24)
		self.assertEqual(doc.sync_targets[1]["webflow_item_id"], "")  # a new brand row is left as it is

	def test_the_sync_itself_may_write_them(self):
		doc = self.product({"sync_identity_write": True})
		doc.keep_sync_identity()
		self.assertEqual(doc.webflow_item_id, "")


if __name__ == "__main__":
	unittest.main()
