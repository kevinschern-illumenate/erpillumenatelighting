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
		route.public_url = lambda name, brand: f"https://site/spec-sheets/{brand}_{name.lower()}.pdf"
		route.template_brand = lambda doctype, name: "illumenate-lighting"
		route.detach_older = MagicMock(return_value=[])
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

	def test_a_successful_run_pushes_to_who_pressed_the_button(self):
		import sys
		import types

		notify = types.ModuleType(ROOT + ".webflow_notify")
		notify.spec_sheet_generated = MagicMock()
		sys.modules[notify.__name__] = notify
		self.addCleanup(sys.modules.pop, notify.__name__, None)
		package = sys.modules.get(ROOT)
		if package is not None:
			old = getattr(package, "webflow_notify", None)
			package.webflow_notify = notify
			self.addCleanup(setattr, package, "webflow_notify", old)
		self.cache["spec_sheet_job:j1"] = {"user": "owner@example.com"}
		self.module.call_n8n = MagicMock(return_value={"success": True, "file_url": "/files/a.pdf"})
		self.frappe.db.get_value.return_value = "/files/a.pdf"
		self.module.run("j1", "ilL-Extrusion-Kit-Template", "KIT-RA02", "illumenate")
		notify.spec_sheet_generated.assert_called_once_with(
			"owner@example.com", "ilL-Extrusion-Kit-Template", "KIT-RA02"
		)
		self.module.run("j1", "ilL-Extrusion-Kit-Template", "KIT-RA02", "illumenate", notify=False)
		notify.spec_sheet_generated.assert_called_once()

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
			"https://site/spec-sheets/illumenate-lighting_kit-ra01.pdf",
		)
		self.route.detach_older.assert_called_once_with("ilL-Extrusion-Kit-Template", "KIT-RA01")
		self.listing.push_to_product.assert_called_once()

	def test_the_template_is_pointed_at_the_file_when_n8n_did_not(self):
		self.frappe.db.get_value.return_value = "/files/old.pdf"
		self.frappe.db.exists.return_value = True
		self.module.register_spec_sheet("ilL-Extrusion-Kit-Template", "KIT-RA01", "/files/a.pdf")
		self.frappe.db.set_value.assert_any_call(
			"ilL-Extrusion-Kit-Template", "KIT-RA01", "spec_sheet", "/files/a.pdf"
		)

	def test_a_refusal_from_erpnext_reads_cleanly(self):
		answer = {
			"error": {
				"message": "417 - ",
				"description": '{"exception":"frappe.exceptions.ValidationError: ilL-Extrusion-Kit-Template KIT-RA02 is not ready for a spec sheet. Missing: Sublabel; Hero Image"}',
			}
		}
		self.assertEqual(
			self.module.answer_error(answer), "Not ready for a spec sheet. Missing: Sublabel; Hero Image"
		)
		self.assertEqual(self.module.answer_error({"error": "Vercel timed out"}), "Vercel timed out")

	def test_the_listed_name_drops_the_tag(self):
		url = "/files/ilLumenate%20Lighting_Rainier%20%5BAN%5D%20Extrusion%20Kit_Spec%20Sheet_C2174D.pdf"
		self.assertEqual(
			self.module.display_name(url), "ilLumenate Lighting_Rainier [AN] Extrusion Kit_Spec Sheet.pdf"
		)
		self.assertEqual(self.module.display_name("/files/other.pdf"), "other.pdf")

	def test_a_failed_run_is_reported_and_changes_nothing(self):
		self.module.call_n8n = MagicMock(return_value={"success": False, "error": "Vercel timed out"})
		self.module.run("j1", "ilL-Extrusion-Kit-Template", "KIT-RA01", "illumenate")
		self.assertEqual(self.status()["status"], "Failed")
		self.assertEqual(self.status()["message"], "Vercel timed out")
		self.frappe.db.set_value.assert_not_called()


class Bulk(Job):
	def test_one_failure_does_not_stop_the_rest(self):
		def fake_run(job, doctype, name, brand, notify=True):
			# A bulk run pushes once at the end, not once per template.
			self.assertFalse(notify)
			ok = name != "KIT-BAD"
			self.cache[f"spec_sheet_job:{job}"] = {
				"status": "Done" if ok else "Failed",
				"file_url": f"/files/{name}.pdf" if ok else None,
				"message": None if ok else "Vercel timed out",
			}

		self.module.run = fake_run
		items = [
			{"template": ["ilL-Extrusion-Kit-Template", n], "brand": "illumenate"}
			for n in ("KIT-RA01", "KIT-BAD", "KIT-RA02")
		]
		self.module.run_bulk("b1", items)
		state = self.cache["spec_sheet_bulk:b1"]
		self.assertEqual(state["status"], "Done")
		self.assertEqual([d["template"] for d in state["done"]], ["KIT-RA01", "KIT-RA02"])
		self.assertEqual(state["failed"], [{"template": "KIT-BAD", "error": "Vercel timed out"}])


class Records(unittest.TestCase):
	def test_product_only_keys_are_ignored(self):
		with load_service(ROOT + ".spec_sheet_data") as (module, frappe):
			frappe.as_json = __import__("json").dumps
			real = {"name": "kit-ra01", "gallery_images": [1], "beam_angle": 110, "sublabel": "A"}
			built = {"name": "template:KIT", "gallery_images": [], "beam_angle": 110, "sublabel": "B"}
			self.assertEqual(module.compare_records(real, built), ["sublabel"])


class Route(unittest.TestCase):
	def setUp(self):
		context = load_service(ROOT + ".spec_sheet_route")
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)

	def test_public_link_domain(self):
		# The stable link takes site config spec_sheet_base_url when set (owner, 2026-11-25:
		# https://app.illumenate.lighting), else the site's own address.
		import sys

		sys.modules["frappe.utils"].get_url = lambda *args: "https://illumenatelighting.v.frappe.cloud"
		self.module.brand_name = lambda brand: "ilLumenate Lighting"
		self.frappe.conf = {}
		self.assertEqual(
			self.module.public_url("ILL-RA01-SW", "illumenate"),
			"https://illumenatelighting.v.frappe.cloud/spec-sheets/illumenate-lighting_ill-ra01-sw.pdf",
		)
		for configured in ("https://app.illumenate.lighting", " https://app.illumenate.lighting/ "):
			self.frappe.conf = {"spec_sheet_base_url": configured}
			self.assertEqual(
				self.module.public_url("ILL-RA01-SW", "illumenate"),
				"https://app.illumenate.lighting/spec-sheets/illumenate-lighting_ill-ra01-sw.pdf",
			)

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

	def test_only_the_current_file_stays_attached(self):
		files = [Record(file_url=f"/files/{n}.pdf") for n in ("new", "mid", "old")]
		older = self.module.files_to_detach(files, "/files/new.pdf")
		self.assertEqual([row.file_url for row in older], ["/files/mid.pdf", "/files/old.pdf"])

	def test_links_carry_the_brand(self):
		self.assertEqual(self.module.brand_slug("ilLumenate Lighting"), "illumenate-lighting")
		self.assertEqual(self.module.brand_slug("206 Lighting"), "206-lighting")
		self.assertEqual(
			self.module.split_key("illumenate-lighting_kit-ra01"), ("illumenate-lighting", "kit-ra01")
		)
		self.assertEqual(self.module.split_key("kit-ra01"), (None, "kit-ra01"))

	def test_a_link_for_another_brand_is_not_found(self):
		self.frappe.db.sql.side_effect = lambda query, values: (
			[("KIT-RA01",)] if "Extrusion-Kit" in query and values[0].lower() == "kit-ra01" else []
		)
		self.frappe.get_all.return_value = ["illumenate"]
		self.frappe.db.get_value.return_value = "/files/kit.pdf"
		self.assertEqual(self.module.current_file("illumenate-lighting_kit-ra01"), "/files/kit.pdf")
		self.assertEqual(self.module.current_file("kit-ra01"), "/files/kit.pdf")
		self.assertIsNone(self.module.current_file("206-lighting_kit-ra01"))

	def test_the_key_comes_from_the_stable_link(self):
		key = self.module.key_from_link
		self.assertEqual(
			key("https://site/spec-sheets/illumenate-lighting_kit-ra01.pdf"), "illumenate-lighting_kit-ra01"
		)
		self.assertEqual(key("/spec-sheets/kit-ra01.pdf"), "kit-ra01")
		self.assertEqual(key("illumenate-lighting_kit-ra01.pdf"), "illumenate-lighting_kit-ra01")
		self.assertEqual(key("https://site/spec-sheets/KIT%2DRA01.pdf"), "KIT-RA01")
		for link in ("", None, "https://site/files/kit.pdf", "https://site/spec-sheets/a/b.pdf"):
			self.assertIsNone(key(link), link)

	def test_the_current_pdf_is_served_only_when_public(self):
		self.module.current_file = MagicMock(return_value="/files/Kit_Spec Sheet_7DBFF4.pdf")
		self.frappe.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
		self.frappe.db.get_value.return_value = Record(name="F1", is_private=1)
		with self.assertRaises(self.frappe.DoesNotExistError):
			self.module.current_pdf("https://site/spec-sheets/kit-ra01.pdf")
		self.module.current_file.return_value = None
		with self.assertRaises(self.frappe.DoesNotExistError):
			self.module.current_pdf("https://site/spec-sheets/kit-ra01.pdf")
		self.module.current_file.assert_called_with("kit-ra01")


if __name__ == "__main__":
	unittest.main()


class Scope(unittest.TestCase):
	"""Site config ``webflow_sync_scope`` (plan 2026-11-23 Task 1)."""

	def setUp(self):
		Job.setUp(self)
		# n8n_config may already be imported against an earlier test's frappe stub.
		import importlib
		from unittest.mock import patch

		n8n_config = importlib.import_module(ROOT + ".api.n8n_config")
		patcher = patch.object(n8n_config, "frappe", self.frappe)
		patcher.start()
		self.addCleanup(patcher.stop)
		# n8n_config may keep this frappe stub after the test: never leave a scope behind.
		self.addCleanup(self.frappe.conf.pop, "webflow_sync_scope", None)
		self.frappe.conf["webflow_sync_scope"] = {
			"doctypes": ["ilL-Fixture-Template"],
			"brands": ["illumenate-lighting"],
		}
		self.frappe.enqueue = MagicMock()

	def stub(self, name, **attrs):
		import sys
		import types

		module = types.ModuleType(f"{ROOT}.{name}")
		module.__dict__.update(attrs)
		sys.modules[module.__name__] = module
		self.addCleanup(sys.modules.pop, module.__name__, None)
		package = sys.modules.get(ROOT)
		if package is not None:
			old = getattr(package, name, None)
			setattr(package, name, module)
			self.addCleanup(setattr, package, name, old)
		return module

	def test_generate_refuses_out_of_scope_doctype(self):
		self.stub("template_link", require_template_access=MagicMock())
		self.frappe.get_doc = MagicMock()
		with self.assertRaises(ValueError) as caught:
			self.module.generate_spec_sheet("ilL-Tape-Neon-Template", "TAPE-1")
		self.assertIn("ilL-Tape-Neon-Template is not enabled for spec generation", str(caught.exception))
		self.frappe.get_doc.assert_not_called()
		self.frappe.enqueue.assert_not_called()

	def test_generate_refuses_out_of_scope_brand(self):
		self.stub("template_link", require_template_access=MagicMock())
		check = MagicMock(return_value={"missing": [], "warnings": []})
		self.stub("spec_sheet_check", check=check)
		self.module._brand = lambda template, brand=None: "lighting_206"
		self.frappe.get_doc = MagicMock(return_value=Record(name="FX-1"))
		with self.assertRaises(ValueError) as caught:
			self.module.generate_spec_sheet("ilL-Fixture-Template", "FX-1")
		self.assertIn("Brand lighting_206 is not enabled for Webflow sync", str(caught.exception))
		check.assert_not_called()
		self.frappe.enqueue.assert_not_called()

	def test_plan_regeneration_skips_out_of_scope(self):
		self.stub(
			"spec_sheet_check",
			check=lambda template: {"missing": [], "warnings": []},
			page_slug=lambda template: "linear-fixtures",
		)
		rows = {
			"ilL-Fixture-Template": [Record(name="FX-1", webflow_product="fx-1", spec_sheet=None)],
			"ilL-Tape-Neon-Template": [Record(name="TAPE-1", webflow_product="tape-1", spec_sheet=None)],
		}
		self.frappe.get_all = MagicMock(side_effect=lambda doctype, **kw: rows.get(doctype, []))
		self.frappe.get_doc = MagicMock(side_effect=lambda doctype, name: Record(name=name))
		to_generate, skipped = self.module.plan_regeneration()
		self.assertEqual([entry["template"] for entry in to_generate], [("ilL-Fixture-Template", "FX-1")])
		self.assertEqual(
			[(entry["template"], entry["reason"]) for entry in skipped],
			[(("ilL-Tape-Neon-Template", "TAPE-1"), "not enabled on this site")],
		)
