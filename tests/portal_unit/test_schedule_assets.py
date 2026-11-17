"""The schedule page scripts are plain /assets files whose URL carries a content hash (plan 2.1)."""

import tempfile
import unittest
from pathlib import Path

from test_services import load_service

PAGE = "illumenate_lighting.templates.pages.schedule"


class ScheduleScriptVersion(unittest.TestCase):
	def test_the_version_hashes_every_page_script(self):
		with load_service(PAGE) as (module, _frappe):
			self.assertTrue(module.SCHEDULE_JS.is_dir())
			names = {path.stem for path in module.SCHEDULE_JS.glob("*.js")}
			self.assertTrue({"context", "lines", "pricing", "new"} <= names)
			module._schedule_js_hash.cache_clear()
			version = module.schedule_js_version()
			self.assertRegex(version, r"^[0-9a-f]{12}$")
			self.assertEqual(module.schedule_js_version(), version)

	def test_a_changed_script_changes_the_version(self):
		with load_service(PAGE) as (module, frappe), tempfile.TemporaryDirectory() as folder:
			module.SCHEDULE_JS = Path(folder)
			(module.SCHEDULE_JS / "lines.js").write_text("var a = 1;\n", encoding="utf8")
			module._schedule_js_hash.cache_clear()
			first = module.schedule_js_version()
			(module.SCHEDULE_JS / "lines.js").write_text("var a = 2;\n", encoding="utf8")
			self.assertEqual(module.schedule_js_version(), first, "production caches the hash per process")
			frappe.conf["developer_mode"] = 1
			self.assertNotEqual(module.schedule_js_version(), first, "developer mode rehashes on every request")


if __name__ == "__main__":
	unittest.main()
