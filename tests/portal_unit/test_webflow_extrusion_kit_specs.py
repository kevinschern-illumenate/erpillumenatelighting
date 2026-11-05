"""Saving an Extrusion Kit Webflow Product calculates specifications without failing.

The Extrusion Kit specs block reads the kit template, so it belongs with the other
template-driven specs in sync_custom_template_data. Placed in calculate_specifications
it raised NameError on template_doc, and every Extrusion Kit save and catalog import failed.
"""

import types
import unittest
from pathlib import Path

from test_services import ROOT, load_service


class Meta:
	def get_field(self, fieldname):
		return object() if fieldname == "specifications" else None

	def has_field(self, fieldname):
		return False


class ExtrusionKitSpecs(unittest.TestCase):
	def test_the_kit_branch_lives_in_template_sync_with_managed_labels(self):
		path = (
			Path(__file__)
			.resolve()
			.parents[2]
			.joinpath(*ROOT.split("."), "doctype", "ill_webflow_product", "ill_webflow_product.py")
		)
		source = path.read_text(encoding="utf-8")
		# The old calculate_specifications was removed (plan 4.17).
		self.assertNotIn("def calculate_specifications", source)
		sync = source[source.index("def sync_custom_template_data") :]
		self.assertIn('elif self.product_type == "Extrusion Kit":', sync)
		# The calculated labels are a module-level tuple, shared with template_listing.
		managed = source[
			source.index("MANAGED_LABELS = (") : source.index("def _resolve_attribute_code_field")
		]
		self.assertIn('"Lenses",', managed)


if __name__ == "__main__":
	unittest.main()
