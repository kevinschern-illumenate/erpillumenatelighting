"""Endcap map coverage counts the template's own endcap colors (owner, 2026-11-19)."""

import unittest
from types import SimpleNamespace as Row

from test_services import ROOT, load_service

MODULE = ROOT + ".api.guardrail_audits"


def option(option_type, **values):
	fields = (
		"finish",
		"endcap_style",
		"mounting_method",
		"power_feed_type",
		"environment_rating",
		"lens_appearance",
	)
	return Row(is_active=1, option_type=option_type, **{field: values.get(field) for field in fields})


class EndcapCoverage(unittest.TestCase):
	def options(self):
		with load_service(MODULE) as (audits, frappe):

			def get_all(doctype, filters=None, fields=None, pluck=None, **_kwargs):
				if doctype == "ilL-Rel-Finish Endcap Color":
					return [
						Row(finish="White", endcap_color="WH"),
						Row(finish="Black", endcap_color="BK"),
						Row(finish="Anodized Silver", endcap_color="GR"),
						Row(finish="Bronze", endcap_color="BZ"),  # a finish this template lacks
						Row(finish="White", endcap_color="OLD"),  # an inactive color
					]
				if doctype == "ilL-Attribute-Endcap Color":
					return ["OLD"]
				return []

			frappe.get_all = get_all
			template = Row(
				allowed_options=[
					option("Finish", finish="White"),
					option("Finish", finish="Black"),
					option("Finish", finish="Anodized Silver"),
					option("Endcap Style", endcap_style="Solid"),
				]
			)
			return audits._get_allowed_options(template)

	def test_only_the_colors_of_the_templates_finishes_and_active(self):
		self.assertEqual(self.options()["endcap_colors"], ["WH", "BK", "GR"])


if __name__ == "__main__":
	unittest.main()
