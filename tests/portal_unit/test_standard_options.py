"""Standard options (Custom finish, Outdoor) and the data each allowed finish needs."""

import unittest

from test_services import ROOT, load_service

MODULE = ROOT + ".api.standard_options"
CODES = {
	("ilL-Attribute-Finish", "White"): "WH",
	("ilL-Attribute-Finish", "Custom RAL"): "cu",
	("ilL-Attribute-Environment Rating", "Dry"): "I",
	("ilL-Attribute-Environment Rating", "Outdoor"): "O",
}


def option(option_type, field, value, active=1):
	return {"option_type": option_type, field: value, "is_active": active}


class StandardOptions(unittest.TestCase):
	def missing(self, doctype, rows):
		with load_service(MODULE) as (module, _frappe):
			return module.missing_standard_options(
				doctype, rows, lambda master, name: CODES.get((master, name))
			)

	def test_fixture_needs_custom_finish_and_outdoor_matched_by_code(self):
		rows = [
			option("Finish", "finish", "White"),
			option("Environment Rating", "environment_rating", "Dry"),
		]
		self.assertEqual(
			self.missing("ilL-Fixture-Template", rows),
			["Custom finish (CU, Provide RAL #)", "Outdoor (O)"],
		)
		rows += [
			option("Finish", "finish", "Custom RAL"),
			option("Environment Rating", "environment_rating", "Outdoor"),
		]
		self.assertEqual(self.missing("ilL-Fixture-Template", rows), [])

	def test_inactive_rows_do_not_count_and_kits_only_need_the_finish(self):
		rows = [option("Finish", "finish", "Custom RAL", active=0)]
		self.assertEqual(
			self.missing("ilL-Extrusion-Kit-Template", rows), ["Custom finish (CU, Provide RAL #)"]
		)
		rows[0]["is_active"] = 1
		self.assertEqual(self.missing("ilL-Extrusion-Kit-Template", rows), [])

	def test_finishes_without_a_profile_variant_or_endcap_colour_are_reported(self):
		template = {
			"name": "SH01",
			"default_profile_family": "SH",
			"allowed_options": [
				option("Finish", "finish", "White"),
				option("Finish", "finish", "Custom RAL"),
			],
		}
		with load_service(MODULE) as (module, frappe):
			frappe.db.get_value.side_effect = lambda doctype, filters, field: (
				CODES.get((doctype, filters))
				if isinstance(filters, str)
				else ("map" if filters.get("finish") == "White" else None)
			)
			frappe.get_all.side_effect = lambda doctype, filters, **kwargs: (
				["CH-SH-WH"] if filters["variant_code"] == "WH" else []
			)
			gaps = module.fixture_finish_gaps(template)
			kit = module.kit_finish_gaps(template)
		self.assertEqual(
			gaps,
			[
				{"finish": "Custom RAL", "missing": "ilL-Spec-Profile family SH variant cu"},
				{"finish": "Custom RAL", "missing": "ilL-Rel-Finish Endcap Color"},
			],
		)
		self.assertEqual(kit, [{"finish": "Custom RAL", "missing": "ilL-Rel-Kit-Profile-Map"}])


if __name__ == "__main__":
	unittest.main()
