"""Generate Spec job: status, n8n answer and registration (plan Phase 3)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service


class Job(unittest.TestCase):
	def setUp(self):
		context = load_service(ROOT + ".spec_sheet_job")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.cache = {}
		cache = self.frappe.cache.return_value
		cache.get_value.side_effect = self.cache.get
		cache.set_value.side_effect = lambda key, value, **kw: self.cache.update({key: dict(value)})
		self.frappe._ = lambda text: text
		self.frappe.log_error = MagicMock()
		self.frappe.db.commit = MagicMock()
		self.frappe.db.set_value = MagicMock()

	def status(self):
		return self.cache["spec_sheet_job:j1"]

	def test_a_successful_run_registers_the_file(self):
		self.module.call_n8n = MagicMock(return_value={"success": True, "file_url": "/files/a.pdf"})
		self.frappe.db.get_value.return_value = "/files/a.pdf"
		self.module.run("j1", "ilL-Extrusion-Kit-Template", "KIT-RA01", "illumenate")
		self.assertEqual(self.status()["status"], "Done")
		self.assertEqual(self.status()["file_url"], "/files/a.pdf")
		self.frappe.db.set_value.assert_not_called()

	def test_the_template_is_pointed_at_the_file_when_n8n_did_not(self):
		self.frappe.db.get_value.return_value = "/files/old.pdf"
		self.frappe.db.exists.return_value = True
		self.module.register_spec_sheet("ilL-Extrusion-Kit-Template", "KIT-RA01", "/files/a.pdf")
		self.frappe.db.set_value.assert_called_once_with(
			"ilL-Extrusion-Kit-Template", "KIT-RA01", "spec_sheet", "/files/a.pdf"
		)

	def test_a_failed_run_is_reported_and_changes_nothing(self):
		self.module.call_n8n = MagicMock(return_value={"success": False, "error": "Vercel timed out"})
		self.module.run("j1", "ilL-Extrusion-Kit-Template", "KIT-RA01", "illumenate")
		self.assertEqual(self.status()["status"], "Failed")
		self.assertEqual(self.status()["message"], "Vercel timed out")
		self.frappe.db.set_value.assert_not_called()


class Records(unittest.TestCase):
	def test_product_only_keys_are_ignored(self):
		with load_service(ROOT + ".spec_sheet_data") as (module, frappe):
			frappe.as_json = __import__("json").dumps
			real = {"name": "kit-ra01", "gallery_images": [1], "beam_angle": 110, "sublabel": "A"}
			built = {"name": "template:KIT", "gallery_images": [], "beam_angle": 110, "sublabel": "B"}
			self.assertEqual(module.compare_records(real, built), ["sublabel"])


if __name__ == "__main__":
	unittest.main()
