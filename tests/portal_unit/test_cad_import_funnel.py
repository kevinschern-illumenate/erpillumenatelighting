"""Implementation plan WP 1.5: the draw-to-quote funnel by drawing tool and week."""

import json
import unittest
from datetime import date

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".report.cad_import_funnel.cad_import_funnel"


def event(day, name, **details):
	return Record(creation=day, message=json.dumps({"event": name, **details}))


class Funnel(unittest.TestCase):
	def test_tally_counts_each_stage_by_tool_and_week(self):
		with load_service(MODULE) as (module, frappe):
			frappe.utils.getdate = lambda value: (
				value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
			)
			rows = module.tally(
				[
					event("2026-11-16", "cad_preview", source_tool="dxf"),
					event("2026-11-17", "cad_preview", source_tool="dxf"),
					event("2026-11-17", "cad_preview_failed"),
					event("2026-11-18", "cad_import", source_tool="dxf"),
					event("2026-11-18", "design_opened"),
					Record(creation="2026-11-18", message="not json"),
					event("2026-11-10", "cad_import", source_tool="autocad"),
				],
				[{"creation": "2026-11-19", "tool": "dxf"}, {"creation": "2026-11-19", "tool": None}],
			)
		by_key = {(row["week"], row["tool"]): row for row in rows}
		dxf = by_key[("2026-W47", "dxf")]
		self.assertEqual((dxf["previews"], dxf["imports"], dxf["quote_requests"]), (2, 1, 1))
		self.assertEqual(by_key[("2026-W47", "unknown")]["failed"], 1)
		self.assertEqual(by_key[("2026-W47", "unknown")]["quote_requests"], 1)
		self.assertEqual(by_key[("2026-W46", "autocad")]["imports"], 1)
		self.assertEqual(rows[0]["week"], "2026-W47")


if __name__ == "__main__":
	unittest.main()
