"""A line whose pinned parts were disabled is shown unpriced; it must not break the schedule page.

Seen live: one tape/neon line whose pinned component had been disabled made ``current_estimate``
raise ``ValueError`` and the whole schedule page returned a 500.
"""

import types
import unittest
from unittest.mock import MagicMock

from test_services import Record, load_service

PAGE = "illumenate_lighting.templates.pages.schedule"
API = "illumenate_lighting.illumenate_lighting.api"


def failing(_doc):
	raise ValueError("A pinned tape/neon component is inactive or its stock UOM has changed")


def builds(estimate):
	return {
		f"{API}.tape_neon_build": types.SimpleNamespace(current_estimate=estimate),
		f"{API}.linear_build": types.SimpleNamespace(current_estimate=estimate),
		f"{API}.fixture_group_bom": types.SimpleNamespace(current_estimate=estimate),
	}


class Lookup:
	def __init__(self, docs):
		self.docs = docs

	def doc(self, _doctype, name):
		return self.docs[name]


class LinePriceProblem(unittest.TestCase):
	def test_a_disabled_part_leaves_the_tape_line_unpriced_with_a_reason(self):
		with load_service(PAGE, builds(failing)) as (module, _frappe):
			line = Record(manufacturer_type="ILLUMENATE", configured_tape_neon="CTN-1", product_type="LED Tape")
			module._get_msrp_from_variant_selections = MagicMock(return_value=99.0)
			msrp = module.compute_line_msrp(
				line, lookup=Lookup({"CTN-1": Record(build_schema_version=2)}), ctn_snapshot_price=50.0
			)
		self.assertIsNone(msrp["unit"])
		self.assertEqual(msrp["price_problem"], module.PRICE_PROBLEM)
		# The saved selections price is not shown for a build that can no longer be made.
		module._get_msrp_from_variant_selections.assert_not_called()

	def test_a_disabled_part_leaves_the_linear_line_unpriced_with_a_reason(self):
		with load_service(PAGE, builds(failing)) as (module, _frappe):
			line = Record(manufacturer_type="ILLUMENATE", configured_fixture="CF-1")
			msrp = module.compute_line_msrp(
				line, cf_details={}, lookup=Lookup({"CF-1": Record(build_schema_version=2)})
			)
		self.assertIsNone(msrp["unit"])
		self.assertEqual(msrp["price_problem"], module.PRICE_PROBLEM)

	def test_a_disabled_part_leaves_the_group_line_unpriced_with_a_reason(self):
		with load_service(PAGE, builds(failing)) as (module, frappe):
			frappe.get_doc.return_value = Record(name="GRP-1")
			msrp = module.compute_line_msrp(
				Record(manufacturer_type="ILLUMENATE", configured_group="GRP-1"), lookup=Lookup({})
			)
		self.assertIsNone(msrp["unit"])
		self.assertEqual(msrp["price_problem"], module.PRICE_PROBLEM)

	def test_a_buildable_line_keeps_its_price_and_no_problem(self):
		with load_service(PAGE, builds(lambda _doc: 125.5)) as (module, _frappe):
			msrp = module.compute_line_msrp(
				Record(manufacturer_type="ILLUMENATE", configured_tape_neon="CTN-1"),
				lookup=Lookup({"CTN-1": Record(build_schema_version=2)}),
			)
		self.assertEqual(msrp["unit"], 125.5)
		self.assertIsNone(msrp["price_problem"])


if __name__ == "__main__":
	unittest.main()
