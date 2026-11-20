"""The AutoLISP math subset (draw-to-quote plan 1.7): golden cases, the Python reference and the
server rules it copies must agree, so a CAD hint never disagrees with the configurator it previews."""

import json
import math
import sys
import unittest
from pathlib import Path

from test_services import ROOT, load_service

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cad_toolkit.reference import cad_subset

CASES = json.loads((REPO / "tools/system_designer/fixtures/cad/lisp-subset.json").read_text(encoding="utf-8"))


class GoldenCases(unittest.TestCase):
	def test_cut_snap(self):
		for case in CASES["cut_snap"]:
			with self.subTest(case):
				self.assertEqual(
					cad_subset.cut_snap(case["length_in"], case["cut_mm"], case["free_cut"]), case["expected"]
				)

	def test_run_split(self):
		for case in CASES["run_split"]:
			args = [case[key] for key in ("length_in", "w_per_ft", "cut_mm", "free_cut", "max_run_vd_ft", "override_ft")]
			with self.subTest(case):
				self.assertEqual(cad_subset.run_split(*args), case["expected"])

	def test_psu_load(self):
		for case in CASES["psu_load"]:
			with self.subTest(case):
				self.assertEqual(
					cad_subset.psu_load(case["loads_w"], case["rated_w"], case["usable_load_factor"]), case["expected"]
				)

	def test_path_length(self):
		for case in CASES["path_length"]:
			with self.subTest(case):
				self.assertEqual(cad_subset.path_length(case["vertices"], case["closed"]), case["expected"])

	def test_quarter_arc_is_a_quarter_circle(self):
		result = cad_subset.path_length([[0, 0, math.tan(math.pi / 8)], [10, 10, 0]])
		self.assertAlmostEqual(result["length_in"], math.pi * 10 / 2, places=3)
		self.assertAlmostEqual(result["min_arc_radius_in"], 10, places=3)


class ServerParity(unittest.TestCase):
	"""The reference against the functions the configurator really runs."""

	def setUp(self):
		self.context = load_service(ROOT + ".api.tape_neon_configurator")
		self.server, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_constants(self):
		self.assertEqual(cad_subset.MAX_WATTS_PER_RUN, self.server.MAX_WATTS_PER_RUN)
		self.assertEqual(cad_subset.MM_PER_FT, self.server.MM_PER_FOOT)
		self.assertEqual(cad_subset.MM_PER_IN, self.server.MM_PER_INCH)
		with load_service(ROOT + ".system_design.cad_catalog") as (cad_catalog, _frappe):
			self.assertEqual(cad_catalog.CONFIGURATOR_MAX_WATTS_PER_RUN, self.server.MAX_WATTS_PER_RUN)

	def test_cut_snap_matches_whole_increments(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import whole_increments

		for case in CASES["cut_snap"]:
			if case["free_cut"] or not case["cut_mm"]:
				continue
			with self.subTest(case):
				increments = max(1, whole_increments(case["length_in"] * 25.4, case["cut_mm"]))
				self.assertEqual(case["expected"]["increments"], increments)

	def test_run_split_matches_compute_run_split(self):
		for case in CASES["run_split"]:
			with self.subTest(case):
				server = self.server._compute_run_split(
					case["length_in"] * 25.4,
					case["w_per_ft"],
					case["max_run_vd_ft"] or 0,
					case["cut_mm"] or 0,
					is_free_cutting=case["free_cut"],
					override_max_run_ft=case["override_ft"],
				)
				expected = case["expected"]
				self.assertEqual(server["runs_count"], expected["runs_count"])
				self.assertEqual(server["max_run_ft_effective"], expected["max_run_ft"])
				self.assertEqual([run["run_len_in"] for run in server["runs"]], expected["runs_in"])


if __name__ == "__main__":
	unittest.main()
