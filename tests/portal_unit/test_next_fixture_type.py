"""Default Fixture Types count up as L1, L2, L3… (first free number)."""

import types
import unittest

from test_services import ROOT, load_service


def lines(*ids):
	return types.SimpleNamespace(lines=[types.SimpleNamespace(line_id=i) for i in ids])


class NextFixtureType(unittest.TestCase):
	def test_counts_up_from_l1_and_fills_gaps(self):
		with load_service(ROOT + ".api.webflow_schedule") as (module, _frappe):
			nxt = module._get_next_fixture_type_id
			self.assertEqual(nxt(lines()), "L1")
			self.assertEqual(nxt(lines("L1", "L2")), "L3")
			self.assertEqual(nxt(lines("L1", "L3")), "L2")
			# Older A-style ids and blanks don't use up L numbers.
			self.assertEqual(nxt(lines("A1", "A2", None, "")), "L1")
			self.assertEqual(nxt(lines(*[f"L{n}" for n in range(1, 150)])), "L150")


if __name__ == "__main__":
	unittest.main()
