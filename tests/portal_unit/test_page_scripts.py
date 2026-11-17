"""Portal page scripts are plain /assets files whose URL carries a content hash (plan 2.2)."""

import tempfile
import unittest
from pathlib import Path

from test_services import load_service

MODULE = "illumenate_lighting.illumenate_lighting.portal.page_scripts"


class PageScriptVersion(unittest.TestCase):
	def test_each_extracted_page_has_a_versioned_script_folder(self):
		with load_service(MODULE) as (module, frappe):
			frappe.conf = {}
			module._folder_hash.cache_clear()
			versions = {folder: module.script_version(folder) for folder in ("edit_fixture", "configure_tape")}
			for folder, version in versions.items():
				self.assertTrue((module.PORTAL_JS / folder / "page.js").is_file(), folder)
				self.assertRegex(version, r"^[0-9a-f]{12}$")
			self.assertNotEqual(versions["edit_fixture"], versions["configure_tape"])

	def test_a_changed_script_changes_the_version_in_developer_mode_only(self):
		with load_service(MODULE) as (module, frappe), tempfile.TemporaryDirectory() as folder:
			frappe.conf = {}
			module.PORTAL_JS = Path(folder)
			(Path(folder) / "page").mkdir()
			script = Path(folder) / "page" / "page.js"
			script.write_text("var a = 1;\n", encoding="utf8")
			module._folder_hash.cache_clear()
			first = module.script_version("page")
			script.write_text("var a = 2;\n", encoding="utf8")
			self.assertEqual(module.script_version("page"), first, "production caches the hash per process")
			frappe.conf["developer_mode"] = 1
			self.assertNotEqual(module.script_version("page"), first, "developer mode rehashes on every request")

	def test_the_page_controllers_put_the_version_in_the_context(self):
		root = Path(__file__).resolve().parents[2] / "illumenate_lighting/templates/pages"
		for page, folder in (("edit_fixture", "edit_fixture"), ("configure_tape", "configure_tape")):
			source = (root / f"{page}.py").read_text(encoding="utf8")
			self.assertIn(f'context.{folder}_js_version = script_version("{folder}")', source)


if __name__ == "__main__":
	unittest.main()
