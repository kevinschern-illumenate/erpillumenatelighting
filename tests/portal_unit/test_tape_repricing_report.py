"""Read-only old-versus-new tape/neon repricing report (hardening plan 6.3, D3)."""

import types
import unittest

from test_services import ROOT, Record, load_service

REPORT = ROOT + ".report.tape_neon_repricing_preview.tape_neon_repricing_preview"


class RepricingPreview(unittest.TestCase):
	def run_report(self, filters, prices):
		calls = []

		def current_estimate(doc, *, legacy_rounding=False):
			calls.append((doc.name, legacy_rounding))
			price = prices[doc.name]
			if isinstance(price, Exception):
				raise price
			return price[0] if legacy_rounding else price[1]

		build = types.ModuleType(ROOT + ".api.tape_neon_build")
		build.current_estimate = current_estimate
		with load_service(REPORT, {ROOT + ".api.tape_neon_build": build}) as (report, frappe):
			frappe._dict = Record
			schedules = [Record(name="S1", status="QUOTED"), Record(name="S2", status="DRAFT")]
			lines = [
				Record(parent="S1", idx=1, configured_tape_neon="A", qty=3),
				Record(parent="S1", idx=2, configured_tape_neon="B", qty=1),
				Record(parent="S2", idx=1, configured_tape_neon="A", qty=2),
				Record(parent="S2", idx=2, configured_tape_neon="C", qty=1),
			]
			frappe.get_all.side_effect = lambda doctype, **kw: schedules if doctype.endswith("Schedule") else lines
			frappe.get_doc.side_effect = lambda doctype, name: Record(name=name, part_number="PN-" + name)
			columns, rows = report.execute(filters)
			return columns, rows, calls, frappe

	def test_lists_only_changed_lines_with_line_difference(self):
		columns, rows, calls, frappe = self.run_report(
			{}, {"A": (10.0, 10.01), "B": (5.0, 5.0), "C": ValueError("Reconfigure this build")}
		)
		self.assertEqual(
			[(r["schedule"], r["line"], r["old_unit"], r["new_unit"], r["line_difference"]) for r in rows],
			[("S1", 1, 10.0, 10.01, 0.03), ("S2", 1, 10.0, 10.01, 0.02), ("S2", 2, None, None, None)],
		)
		self.assertEqual(rows[2]["note"], "Reconfigure this build")
		# Each pinned build is priced once per rule, however many lines use it.
		self.assertEqual(sorted(calls), [("A", False), ("A", True), ("B", False), ("B", True), ("C", True)])
		self.assertIn("line_difference", [c["fieldname"] for c in columns])
		self.assertEqual(
			frappe.get_all.call_args_list[0].kwargs["filters"], {"status": ["in", ["DRAFT", "READY", "QUOTED"]]}
		)
		frappe.db.set_value.assert_not_called()
		frappe.db.commit.assert_not_called()

	def test_can_show_unchanged_lines_and_scope_one_status(self):
		_, rows, _, frappe = self.run_report(
			{"only_changed": 0, "status": "DRAFT"}, {"A": (1.0, 1.0), "B": (1.0, 1.0), "C": (2.0, 2.0)}
		)
		self.assertEqual(len(rows), 4)
		self.assertEqual(frappe.get_all.call_args_list[0].kwargs["filters"], {"status": ["in", ["DRAFT"]]})

	def test_issued_statuses_cannot_be_selected(self):
		_, _, _, frappe = self.run_report({"status": "ORDERED"}, {"A": (1, 1), "B": (1, 1), "C": (1, 1)})
		self.assertEqual(
			frappe.get_all.call_args_list[0].kwargs["filters"], {"status": ["in", ["DRAFT", "READY", "QUOTED"]]}
		)


if __name__ == "__main__":
	unittest.main()
