"""Draw-to-quote WP 1.1/1.3: older drawing imports get their source and scale filled in."""

import json
import unittest
from pathlib import Path

from test_services import load_service

PACKAGES = Path(__file__).resolve().parents[2] / "tools/system_designer/fixtures/cad/packages"


class Backfill(unittest.TestCase):
	def test_source_and_scale_come_from_the_stored_package(self):
		with load_service("illumenate_lighting.patches.backfill_cad_import_source") as (module, _frappe):
			minimal = (PACKAGES / "valid/minimal.json").read_text(encoding="utf-8")
			autocad = module.source_fields("0.3.0", minimal)
			dxf = json.loads(minimal)
			dxf["toolkit"] = {"version": "dxf-1", "platform": "DXF upload"}
			dxf["drawing"]["scale_verified"] = True
			from_dxf = module.source_fields("dxf-1", json.dumps(dxf))
			broken = module.source_fields("dxf-1", "{not json")
		self.assertEqual(
			(autocad["source_tool"], autocad["source_input"], autocad["scale_status"]),
			("autocad", "ilq", "declared"),
		)
		self.assertEqual((from_dxf["source_tool"], from_dxf["scale_status"]), ("dxf", "verified"))
		self.assertEqual(broken["source_tool"], "dxf")


if __name__ == "__main__":
	unittest.main()
