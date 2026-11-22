"""Implementation plan WP 1.12: the Resources page offers the CAD toolkit to the CAD rollout only."""

import tempfile
import types
import unittest
from pathlib import Path

from test_services import ROOT, load_service

MODULE = "illumenate_lighting.templates.pages.resources"


class DrawingTools(unittest.TestCase):
	def tools(self, enabled):
		extras = {
			ROOT + ".system_design.cad_access": types.SimpleNamespace(enabled_for=lambda user=None: enabled)
		}
		with load_service(MODULE, extras) as (module, _frappe):
			return module.drawing_tools(), module

	def test_only_the_cad_rollout_sees_the_section(self):
		self.assertIsNone(self.tools(False)[0])
		tools, module = self.tools(True)
		self.assertTrue(tools["toolkit"]["url"].startswith(module.TOOLKIT_URL))
		self.assertIn("download_cad_catalog", tools["catalog_url"])

	def test_the_newest_committed_bundle_is_offered(self):
		_tools, module = self.tools(True)
		with tempfile.TemporaryDirectory() as folder:
			for name in (
				"ilLumenate-cad-toolkit-0.9.0.zip",
				"ilLumenate-cad-toolkit-0.10.0.zip",
				"other.zip",
			):
				Path(folder, name).write_bytes(b"")
			self.assertEqual(module.toolkit_zip(folder), ("ilLumenate-cad-toolkit-0.10.0.zip", "0.10.0"))
			self.assertIsNone(module.toolkit_zip(Path(folder, "missing")))


if __name__ == "__main__":
	unittest.main()
