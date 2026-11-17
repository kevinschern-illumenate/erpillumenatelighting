"""Plan 2.6: the schedule page reads related records once per DocType, not once per line."""

import unittest
from unittest.mock import MagicMock

from test_services import Record, load_service

PAGE = "illumenate_lighting.templates.pages.schedule"


def database():
	fixtures = {
		f"CF-{i}": Record(
			name=f"CF-{i}",
			fixture_template=f"FT-{i % 2}",
			finish="BLK",
			lens_appearance="FROST",
			tape_offering=f"TO-{i % 3}",
			manufacturable_overall_length_mm=1000 + i,
			total_watts=10 + i,
			display_part_number=f"ILL-{i}",
			drivers=[Record(driver_item="DRV-1", driver_qty=2), Record(driver_item=f"DRV-{i % 2 + 2}", driver_qty=1)],
		)
		for i in range(6)
	}
	return {
		"ilL-Configured-Fixture": fixtures,
		"ilL-Configured-Tape-Neon": {
			f"CTN-{i}": Record(name=f"CTN-{i}", part_number=f"TN-{i}", manufacturable_length_mm=500) for i in range(4)
		},
		"ilL-Configured-LED-Sheet": {f"CLS-{i}": Record(name=f"CLS-{i}", part_number=f"LS-{i}", msrp=40 + i) for i in range(3)},
		"ilL-Fixture-Template": {f"FT-{i}": Record(name=f"FT-{i}", template_name=f"Linear {i}") for i in range(2)},
		"ilL-Tape-Neon-Template": {
			"TNT-1": Record(name="TNT-1", template_name="Neon", template_code="NN", description="Flex <neon>")
		},
		"ilL-LED-Sheet-Template": {"LST-1": Record(name="LST-1", template_name="Sheet")},
		"Item": {f"ACC-{i}": Record(name=f"ACC-{i}", item_name=f"Clip {i}", description="Clip") for i in range(5)},
		"ilL-Attribute-Finish": {"BLK": Record(name="BLK", code="BK", finish_name="Black")},
		"ilL-Attribute-Lens Appearance": {"FROST": Record(name="FROST", label="Frosted", transmission=0.8)},
		"ilL-Rel-Tape Offering": {
			f"TO-{i}": Record(name=f"TO-{i}", cct="30K", led_package="HD", output_level="OL-1", tape_spec="TS-1", cri="CRI-90")
			for i in range(3)
		},
		"ilL-Attribute-CRI": {"CRI-90": Record(name="CRI-90", cri_name="90+", code="9")},
		"ilL-Spec-LED Tape": {"TS-1": Record(name="TS-1", input_voltage="24V")},
		"ilL-Attribute-Output Level": {"OL-1": Record(name="OL-1", output_level_name="Standard", value=300)},
		"ilL-Spec-Driver": {
			f"SD-{i}": Record(name=f"SD-{i}", item=f"DRV-{i}", input_voltage="120-277V", max_wattage=96) for i in range(1, 4)
		},
		"Item Price": {
			**{
				f"IP-D{i}": Record(name=f"IP-D{i}", item_code=f"DRV-{i}", price_list="Standard Selling", selling=1, price_list_rate=20.0 * i)
				for i in range(1, 4)
			},
			**{
				f"IP-A{i}": Record(name=f"IP-A{i}", item_code=f"ACC-{i}", price_list="Standard Selling", selling=1, price_list_rate=3.0 + i)
				for i in range(5)
			},
			"IP-OTHER": Record(name="IP-OTHER", item_code="ACC-1", price_list="Wholesale", selling=1, price_list_rate=1.0),
		},
	}


def matches(row, filters):
	for field, condition in filters.items():
		if isinstance(condition, list) and condition[0] == "in":
			if row.get(field) not in condition[1]:
				return False
		elif row.get(field) != condition:
			return False
	return True


def install(frappe, db):
	def pick(row, fields, as_dict=True):
		if row is None:
			return None
		if isinstance(fields, str):
			return row.get(fields)
		return Record({field: row.get(field) for field in fields})

	def get_value(doctype, key, fields, as_dict=False):
		rows = db.get(doctype, {})
		if isinstance(key, dict):
			row = next((row for row in rows.values() if matches(row, key)), None)
		else:
			row = rows.get(key)
		return pick(row, fields)

	def get_all(doctype, filters=None, fields=None, **_kwargs):
		return [pick(row, fields) for row in db.get(doctype, {}).values() if matches(row, filters or {})]

	def get_doc(doctype, name):
		try:
			return db[doctype][name]
		except KeyError:
			raise LookupError(name) from None

	frappe.db.get_value = MagicMock(side_effect=get_value)
	frappe.db.exists = MagicMock(side_effect=lambda doctype, name: name if name in db.get(doctype, {}) else None)
	frappe.get_all = MagicMock(side_effect=get_all)
	frappe.get_doc = MagicMock(side_effect=get_doc)
	frappe.log_error = MagicMock()
	frappe.get_traceback = MagicMock(return_value="")


def fifty_lines():
	lines = []
	for i in range(20):
		lines.append(Record(manufacturer_type="ILLUMENATE", configured_fixture=f"CF-{i % 6}", fixture_template=f"FT-{i % 2}", qty=2))
	lines.append(Record(manufacturer_type="ILLUMENATE", configured_fixture="CF-GONE", qty=1))
	for i in range(10):
		lines.append(Record(manufacturer_type="ILLUMENATE", configured_tape_neon=f"CTN-{i % 4}", tape_neon_template="TNT-1", qty=1))
	for i in range(9):
		lines.append(Record(manufacturer_type="ILLUMENATE", configured_led_sheet=f"CLS-{i % 3}", led_sheet_template="LST-1", qty=1))
	for i in range(10):
		lines.append(Record(manufacturer_type="ACCESSORY", accessory_item=f"ACC-{i % 5}", qty=3))
	assert len(lines) == 50
	return lines


def render(module, lines, lookup):
	"""The per-line reads ``get_context`` and the dealer pricing API make."""
	out = []
	for line in lines:
		cf = ctn = cls = None
		if line.configured_fixture:
			cf = module._get_configured_fixture_display_details(line.configured_fixture, lookup=lookup)
		if line.configured_tape_neon:
			ctn = module._get_configured_tape_neon_display_details(line.configured_tape_neon, lookup=lookup)
		if line.configured_led_sheet:
			cls = module._get_configured_led_sheet_display_details(line.configured_led_sheet, lookup=lookup)
		try:
			msrp = module.compute_line_msrp(line, cf_details=cf, cls_details=cls, lookup=lookup)
		except LookupError:
			msrp = "missing record"  # unchanged: pricing a deleted fixture raises, as before
		out.append((cf, ctn, cls, msrp))
	return out


class BatchedScheduleReads(unittest.TestCase):
	def test_fifty_lines_match_the_legacy_reads_with_a_fixed_query_count(self):
		with load_service(PAGE) as (module, frappe):
			install(frappe, database())
			lines = fifty_lines()
			legacy = render(module, lines, None)
			legacy_reads = frappe.db.get_value.call_count + frappe.get_doc.call_count
			self.assertGreater(legacy_reads, 150, "the legacy path reads per line")

			install(frappe, database())
			lookup = module.Lookup()
			module.prefetch_schedule(lookup, lines)
			batched = render(module, lines, lookup)

			self.assertEqual(batched, legacy)
			frappe.db.get_value.assert_not_called()
			frappe.db.exists.assert_not_called()
			self.assertLessEqual(frappe.get_all.call_count, 18, "one get_all per DocType")
			loaded = [call.args for call in frappe.get_doc.call_args_list]
			self.assertEqual(len(loaded), len(set(loaded)), "each record is loaded once")
			self.assertEqual(
				sorted(name for doctype, name in loaded if doctype == "ilL-Configured-Fixture"),
				[*(f"CF-{i}" for i in range(6)), "CF-GONE"],
				"six fixtures once each; the deleted one only by the pricing call that raises",
			)
			self.assertEqual(legacy[20][0], {}, "a missing fixture still renders as empty")

	def test_prefetch_covers_the_template_and_item_names_read_in_get_context(self):
		with load_service(PAGE) as (module, frappe):
			install(frappe, database())
			lookup = module.Lookup()
			module.prefetch_schedule(lookup, fifty_lines())
			self.assertEqual(lookup.value("ilL-Fixture-Template", "FT-1", "template_name"), "Linear 1")
			tape = lookup.value("ilL-Tape-Neon-Template", "TNT-1", ["template_name", "template_code", "description"])
			self.assertEqual((tape.template_name, tape.description), ("Neon", "Flex <neon>"))
			self.assertEqual(lookup.value("ilL-LED-Sheet-Template", "LST-1", "template_name"), "Sheet")
			self.assertEqual(lookup.value("Item", "ACC-2", ["description", "item_name"]).item_name, "Clip 2")
			frappe.db.get_value.assert_not_called()

	def test_details_figures_come_through_the_lookup(self):
		with load_service(PAGE) as (module, frappe):
			install(frappe, database())
			lookup = module.Lookup()
			module.prefetch_schedule(lookup, fifty_lines())
			details = module._get_configured_fixture_display_details("CF-1", lookup=lookup)
			self.assertEqual(details["fixture_template_name"], "Linear 1")
			self.assertEqual((details["finish"], details["lens_appearance"], details["cri"]), ("Black", "Frosted", "90+"))
			self.assertEqual(details["fixture_input_voltage"], "24V")
			self.assertEqual(details["power_supply"], "DRV-1 (2), DRV-3")
			self.assertEqual(details["driver_msrp_unit"], 100.0)
			price = module.compute_line_msrp(Record(manufacturer_type="ACCESSORY", accessory_item="ACC-1"), lookup=lookup)
			self.assertEqual(price["unit"], 4.0, "only Standard Selling prices count")


class LookupUnit(unittest.TestCase):
	def test_unknown_names_cache_as_absent_and_fallback_reads_once(self):
		with load_service(ROOT_LOOKUP) as (lookup_module, frappe):
			install(frappe, database())
			lookup = lookup_module.Lookup()
			lookup.prefetch("ilL-Fixture-Template", ["FT-0", "NOPE", None, ""], "template_name")
			self.assertEqual(frappe.get_all.call_count, 1)
			self.assertIsNone(lookup.value("ilL-Fixture-Template", "NOPE", "template_name"))
			frappe.db.get_value.assert_not_called()
			self.assertEqual(lookup.value("ilL-Fixture-Template", "FT-1", "template_name"), "Linear 1")
			self.assertEqual(lookup.value("ilL-Fixture-Template", "FT-1", "template_name"), "Linear 1")
			self.assertEqual(frappe.db.get_value.call_count, 1)
			lookup.prefetch("ilL-Fixture-Template", ["FT-0", "FT-1"], "template_name")
			self.assertEqual(frappe.get_all.call_count, 1, "known names are not refetched")

	def test_large_name_sets_are_chunked(self):
		with load_service(ROOT_LOOKUP) as (lookup_module, frappe):
			install(frappe, database())
			lookup = lookup_module.Lookup()
			lookup.prefetch("Item", [f"X-{i}" for i in range(lookup_module.CHUNK * 2 + 1)], "item_name")
			self.assertEqual(frappe.get_all.call_count, 3)
			for call in frappe.get_all.call_args_list:
				self.assertLessEqual(len(call.kwargs["filters"]["name"][1]), lookup_module.CHUNK)

	def test_rows_support_attribute_access(self):
		with load_service(ROOT_LOOKUP) as (lookup_module, _frappe):
			row = lookup_module.Row(a=1)
			self.assertEqual(row.a, 1)
			self.assertFalse(hasattr(row, "missing"), "missing keys raise AttributeError")


ROOT_LOOKUP = "illumenate_lighting.illumenate_lighting.portal.schedule_lookup"


if __name__ == "__main__":
	unittest.main()
