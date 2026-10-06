"""Family facts and constant-query catalog loading at production-sized scopes."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"


class Facts(unittest.TestCase):
	def context(self):
		return load_service(
			BASE + ".facts",
			{
				ROOT + ".api.product_catalog": types.SimpleNamespace(
					_project=lambda p, activity, **kw: {
						"family": p.product_type,
						"capability": p.get("capability", "configure"),
					}
				),
				ROOT + ".portal.standard_products": types.SimpleNamespace(choices=lambda *a, **kw: []),
			},
		)

	def table_data(self, service, copies=1):
		tables = {}
		products = []
		for family, (doctype, link, child, specs) in service.TEMPLATES.items():
			name = family.replace(" ", "")
			products.extend(
				Record(
					name=name + str(i),
					product_type=family,
					product_slug=name,
					product_name=name,
					**{link: name},
				)
				for i in range(copies)
			)
			tables.setdefault(doctype, []).append(Record(name=name, is_active=1))
			tables.setdefault(child, []).extend(
				[
					Record(
						parent=name,
						is_active=1,
						finish="White",
						cct="3000K",
						environment_rating="Dry",
						mounting_method="Surface",
						lens_appearance="Frosted",
					),
					Record(parent=name, is_active=0, finish="Inactive"),
				]
			)
			if specs:
				tables.setdefault(specs, []).append(
					Record(
						parent=name,
						is_active=1,
						tape_offering="Offering",
						tape_spec="Tape",
						spec="Sheet",
						voltage_output="24V",
						wattage=96,
						controller_type="Wall",
						mounting_type="Box",
						channels=4,
						zones=2,
						output_protocol="DMX",
						input_protocol="0-10V",
					)
				)
		tables[service.PRODUCT] = [
			*products,
			Record(name="excluded", product_type="Accessory", capability="inquiry"),
		]
		tables["ilL-Rel-Tape Offering"] = [
			Record(
				name="Offering",
				is_active=1,
				led_package="RGB",
				cct="3000K",
				cri="90",
				output_level="450",
				tape_spec="Tape",
			)
		]
		tables["ilL-Spec-LED Tape"] = [
			Record(
				name="Tape",
				is_active=1,
				led_package="RGB",
				input_protocol="PWM",
				input_voltage="24V",
				lumens_per_foot=420,
			)
		]
		tables["ilL-Spec-LED-Sheet"] = [
			Record(name="Sheet", is_active=1, led_package="RGB", cct="3000K", cri="90", ip_rating="IP67")
		]
		tables["ilL-Attribute-LED Package"] = [Record(name="RGB", spectrum_type="RGBW", is_pixel=1)]
		tables["ilL-Attribute-CCT"] = [Record(name="3000K", kelvin=3000)]
		tables["ilL-Attribute-CRI"] = [Record(name="90", minimum_ra=90)]
		tables["ilL-Attribute-Output Level"] = [Record(name="450", value=450)]
		tables["ilL-Child-Webflow-Attribute-Link"] = [
			Record(parent="LinearFixture0", attribute_type="Environment Rating", attribute_name="Wet")
		]
		return tables

	def test_all_families_active_sources_and_derivation(self):
		with self.context() as (service, frappe):
			frappe._dict = Record
			tables = self.table_data(service)
			frappe.get_all.side_effect = lambda dt, **kw: tables.get(dt, [])
			by_family = {p["family"]: p for p in service.build_facts()}
			self.assertEqual(set(by_family), set(service.TEMPLATES))
			for p in by_family.values():
				self.assertEqual(p["facets"]["finish"], frozenset(["White"]))
			linear = by_family["Linear Fixture"]
			self.assertEqual(linear["facets"]["environment_rating"], frozenset(["Wet"]))
			self.assertEqual(linear["sources"]["environment_rating"], "attribute_link")
			self.assertEqual(linear["facets"]["lumens_per_ft"], (450.0,))
			for family in ("Linear Fixture", "LED Tape", "COB Tape", "LED Neon", "LED Sheet"):
				p = by_family[family]
				self.assertEqual(p["facets"]["color_mode"], frozenset(["Addressable pixel (SPI)"]))
				self.assertEqual(p["facets"]["light_type"], frozenset(["Full-color"]))
				self.assertEqual(p["facets"]["cct_range"], (3000, 3000))
			self.assertEqual(by_family["LED Sheet"]["facets"]["ip_rating"], frozenset(["IP67"]))
			self.assertEqual(by_family["Driver"]["facets"]["driver_wattage"], (96.0,))
			self.assertEqual(by_family["Controller"]["facets"]["channels"], (4.0,))
			frappe.get_doc.assert_not_called()

	def test_queries_are_bounded_above_500_products(self):
		with self.context() as (service, frappe):
			frappe._dict = Record
			counts = []
			for copies in (1, 72):
				tables = self.table_data(service, copies)
				frappe.get_all.reset_mock()
				frappe.get_all.side_effect = lambda dt, **kw: tables.get(dt, [])
				self.assertEqual(len(service.build_facts()), len(service.TEMPLATES) * copies)
				counts.append(frappe.get_all.call_count)
			self.assertEqual(counts[0], counts[1])
			self.assertLess(counts[1], 65)

	def test_stamp_cache_and_invalidation(self):
		with self.context() as (service, frappe):
			cache = {}
			frappe.cache().get_value.side_effect = cache.get
			frappe.cache().set_value.side_effect = lambda key, value, **kw: cache.update({key: value})
			frappe.cache().delete_value.side_effect = lambda key: cache.pop(key, None)
			frappe.db.sql.return_value = [Record(stamp="2026-10-01")]
			service.build_facts = MagicMock(return_value=[{"name": "P"}])
			self.assertEqual(service.load(), service.load())
			service.build_facts.assert_called_once()
			service.invalidate()
			frappe.db.sql.return_value = [Record(stamp="2026-10-01")]  # deleting an older row keeps MAX unchanged
			service.load()
			self.assertEqual(service.build_facts.call_count, 2)
