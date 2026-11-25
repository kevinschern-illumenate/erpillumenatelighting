"""A fixture template's unchecked "Is Required" survives its save (owner, 2026-11-25).

The fixture configurator steps are rebuilt on every save. They wrote Is Required = 1 on every
step, so unchecking Start/End Feed Direction never stuck; the LED Sheet, Extrusion Kit and
Tape/Neon steps already kept the template's own choice.
"""

import unittest

from test_services import ROOT, Record, load_service


class FixtureStepRequired(unittest.TestCase):
	def steps(self, existing):
		with load_service(ROOT + ".template_calculations") as (module, frappe):
			frappe._dict = Record
			frappe.as_json = lambda value: str(value)
			calculator = module.TemplateCalculator(
				name="ill-ra01-sw",
				product_type="Fixture Template",
				links={"fixture_template": "ILL-RA01-SW"},
				template_doc=Record(doctype="ilL-Fixture-Template", name="ILL-RA01-SW"),
				existing_is_required=existing,
			)
			calculator._template_doc = lambda doctype, name: Record(name=name)
			calculator._get_allowed_values_for_option = lambda template, option_type, step=None: [
				{"code": "X"}
			]
			calculator._get_finish_endcap_color_mapping = lambda: []
			calculator._get_fixture_output_level_table = lambda: []
			calculator.populate_configurator_options()
			return {row.option_step: row.is_required for row in calculator.configurator_options}

	def test_unchecked_steps_stay_unchecked(self):
		required = self.steps({8: 0, 9: 0, 10: 0, 11: 0, 2: 1})
		self.assertEqual([required[step] for step in (8, 9, 10, 11)], [0, 0, 0, 0])
		self.assertEqual(required[2], 1)

	def test_new_steps_are_required(self):
		self.assertEqual(set(self.steps({}).values()), {1})


if __name__ == "__main__":
	unittest.main()
