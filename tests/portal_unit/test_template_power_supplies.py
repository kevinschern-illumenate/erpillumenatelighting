"""Compatible power supplies live on the template (owner, 2026-11-05; plan 4.17 item 10)."""

import unittest

from test_services import ROOT, load_service

MODULE = ROOT + ".template_power_supplies"


def driver(name, wattage, **extra):
	return {
		"name": name,
		"input_voltage_min": 120,
		"input_voltage_max": 277,
		"input_voltage_type": "VAC",
		"voltage_output": "24V",
		"max_wattage": wattage,
		"location_rating": "Dry",
		"outputs_count": 2,
		**extra,
	}


class Rows(unittest.TestCase):
	def test_a_row_keeps_the_seven_columns_and_links_its_eligibility(self):
		with load_service(MODULE) as (module, _frappe):
			row = module.power_supply_row(driver("PS-96", 96.0), ["0-10V", "DALI"], "ELIG-1")
		self.assertEqual(
			row,
			{
				"part_number": "PS-96",
				"input_protocol": "0-10V, DALI",
				"voltagefrequency": "120 - 277VAC",
				"output_voltage": "24V",
				"max_wattage": "96W",
				"output_count": "2",
				"location_rating": "Dry",
				"eligibility": "ELIG-1",
			},
		)

	def test_sorted_by_max_wattage_then_part_number(self):
		with load_service(MODULE) as (module, _frappe):
			drivers = [driver("B", 96.0), driver("C", None), driver("A", 96.0), driver("D", 30.0)]
			self.assertEqual([d["name"] for d in sorted(drivers, key=module.sort_key)], ["D", "A", "B", "C"])

	def test_voltage_with_one_value(self):
		with load_service(MODULE) as (module, _frappe):
			self.assertEqual(module.voltage_frequency(None, 24, "VDC"), "24VDC")
			self.assertEqual(module.voltage_frequency(None, None, "VDC"), "")

	def test_only_active_and_allowed_eligibility_for_this_template(self):
		with load_service(MODULE) as (module, frappe):
			frappe.get_all.return_value = []
			self.assertEqual(module.rows_for("ilL-Tape-Neon-Template", "TN-1"), [])
			filters = frappe.get_all.call_args.kwargs["filters"]
			self.assertEqual(
				filters,
				{
					"template_type": "ilL-Tape-Neon-Template",
					"fixture_template": "TN-1",
					"is_active": 1,
					"is_allowed": 1,
				},
			)
			frappe.get_all.reset_mock()
			self.assertEqual(module.rows_for("ilL-Extrusion-Kit-Template", "KIT-1"), [])
			frappe.get_all.assert_not_called()


class Products(unittest.TestCase):
	def test_drivers_map_to_their_power_supply_products_through_the_driver_template(self):
		with load_service(MODULE) as (module, frappe):

			def get_all(doctype, **kwargs):
				if doctype == "ilL-Child-Driver-Template-Variant":
					return [
						{"parent": "PS-UNIV", "driver_spec": "PS-UNIV-24V-30W"},
						{"parent": "PS-UNIV", "driver_spec": "PS-UNIV-24V-96W"},
						{"parent": "PS-NOWEB", "driver_spec": "PS-NOWEB-12V"},
					]
				return [
					{"name": "PS-UNIV", "webflow_product": "ps-univ"},
					{"name": "PS-NOWEB", "webflow_product": None},
				]

			frappe.get_all.side_effect = get_all
			products, missing = module.power_supply_products(
				["PS-UNIV-24V-30W", "PS-UNIV-24V-96W", "PS-NOWEB-12V", "PS-UNKNOWN"]
			)
		self.assertEqual(products, ["ps-univ"])
		self.assertEqual(missing, ["PS-NOWEB-12V", "PS-UNKNOWN"])


if __name__ == "__main__":
	unittest.main()
