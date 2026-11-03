"""Generate Spec job: status, n8n answer and registration (plan Phase 3)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


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
		self.frappe.db.rollback = MagicMock()
		# The stable link, file cleanup and product push are tested on their own.
		import sys
		import types

		route = types.ModuleType(ROOT + ".spec_sheet_route")
		route.public_url = lambda name: f"https://site/spec-sheets/{name.lower()}.pdf"
		route.prune = MagicMock(return_value=[])
		listing = types.ModuleType(ROOT + ".template_listing")
		listing.push_to_product = MagicMock()
		self.route, self.listing = route, listing
		for module in (route, listing):
			sys.modules[module.__name__] = module
			self.addCleanup(sys.modules.pop, module.__name__, None)
		package = sys.modules.get(ROOT)
		if package is not None:
			for attr, module in (("spec_sheet_route", route), ("template_listing", listing)):
				old = getattr(package, attr, None)
				setattr(package, attr, module)
				self.addCleanup(setattr, package, attr, old)

	def status(self):
		return self.cache["spec_sheet_job:j1"]

	def test_a_successful_run_registers_the_file(self):
		self.module.call_n8n = MagicMock(return_value={"success": True, "file_url": "/files/a.pdf"})
		self.frappe.db.get_value.return_value = "/files/a.pdf"
		self.module.run("j1", "ilL-Extrusion-Kit-Template", "KIT-RA01", "illumenate")
		self.assertEqual(self.status()["status"], "Done")
		self.assertEqual(self.status()["file_url"], "/files/a.pdf")
		# Only the stable link is written; the file was already attached by n8n.
		self.frappe.db.set_value.assert_called_once_with(
			"ilL-Extrusion-Kit-Template",
			"KIT-RA01",
			"spec_sheet_public_url",
			"https://site/spec-sheets/kit-ra01.pdf",
		)
		self.route.prune.assert_called_once_with("ilL-Extrusion-Kit-Template", "KIT-RA01")
		self.listing.push_to_product.assert_called_once()

	def test_the_template_is_pointed_at_the_file_when_n8n_did_not(self):
		self.frappe.db.get_value.return_value = "/files/old.pdf"
		self.frappe.db.exists.return_value = True
		self.module.register_spec_sheet("ilL-Extrusion-Kit-Template", "KIT-RA01", "/files/a.pdf")
		self.frappe.db.set_value.assert_any_call(
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


class Route(unittest.TestCase):
	def setUp(self):
		context = load_service(ROOT + ".spec_sheet_route")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)

	def test_spec_sheet_paths(self):
		key = self.module.key_from_path
		self.assertEqual(key("/spec-sheets/kit-ra01.pdf"), "kit-ra01")
		self.assertEqual(key("spec-sheets/KIT-RA01"), "KIT-RA01")
		self.assertEqual(key("/Spec-Sheets/kit-ra01.PDF"), "kit-ra01")
		for path in ("/spec-sheets/", "/spec-sheets/a/b.pdf", "/files/kit-ra01.pdf", "/portal"):
			self.assertIsNone(key(path), path)

	def test_one_match_in_any_case_or_none(self):
		rows = {"ilL-Extrusion-Kit-Template": [("KIT-RA01",)]}
		self.frappe.db.sql.side_effect = lambda query, values: next(
			(found for doctype, found in rows.items() if doctype in query), []
		)
		self.assertEqual(self.module.find_template("kit-ra01"), ("ilL-Extrusion-Kit-Template", "KIT-RA01"))
		rows["ilL-Driver-Template"] = [("kit-ra01",)]
		self.frappe.log_error = MagicMock()
		self.assertIsNone(self.module.find_template("kit-ra01"))
		self.frappe.log_error.assert_called_once()

	def test_pruning_keeps_the_newest_two_and_the_current_file(self):
		files = [Record(file_url=f"/files/{n}.pdf") for n in ("new", "mid", "old", "older")]
		kept_current = self.module.files_to_prune(files, "/files/older.pdf")
		self.assertEqual([row.file_url for row in kept_current], ["/files/old.pdf"])
		self.assertEqual(self.module.files_to_prune(files[:2], "/files/new.pdf"), [])
