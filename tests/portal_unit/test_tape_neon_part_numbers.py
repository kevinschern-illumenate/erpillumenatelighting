"""LED Tape / COB Tape / LED Neon part numbers: CCT and output appear once, and are part of the build identity."""

import unittest

from test_services import ROOT, Record, load_service

CODES = {
	("ilL-Attribute-CCT", "3000K", "code"): "30",
	("ilL-Attribute-CCT", "4000K", "code"): "40",
	("ilL-Attribute-Output Level", "Standard", "sku_code"): "S",
	("ilL-Attribute-Output Level", "High", "sku_code"): "H",
	("ilL-Attribute-Power Feed Type", "Standard", "code"): "E",
	("ilL-Attribute-Feed-Direction", "End", "code"): "E",
}
CATALOG_CODES = {
	("ilL-Attribute-CCT", "3000K", "code"): "30K",
	("ilL-Attribute-Output Level", "300 lm/ft", "sku_code"): "300",
}
SPEC = Record(name="TAPE-SH01-24V-5W")
SEGMENT = {
	"segment_index": 1,
	"manufacturable_length_in": 150,
	"ip_rating": "IP67",
	"start_feed_direction": "End",
	"start_lead_length_inches": 24,
}


def offering(cct="3000K", output_level="Standard"):
	return Record(name=f"{SPEC.name}-{cct}-{output_level}", cct=cct, output_level=output_level)


class ServiceMixin:
	def service(self, codes=CODES, offerings_per_spec=4):
		context = load_service(ROOT + ".api.tape_neon_configurator")
		service, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.db.get_value.side_effect = lambda doctype, name, field: codes.get((doctype, name, field))
		frappe.db.exists.return_value = True
		frappe.db.count.return_value = offerings_per_spec
		self.frappe = frappe
		return service


class PartNumbers(ServiceMixin, unittest.TestCase):
	"""A spec shared by several CCT/output offerings: the codes keep its builds apart."""

	def test_tape_part_number_places_cct_and_output_after_the_spec(self):
		service = self.service()
		sel = {"feed_type": "Standard", "lead_length_inches": 12}
		self.assertEqual(
			service._build_tape_part_number(sel, SPEC, offering(), 120 * 25.4),
			"TAPE-SH01-24V-5W-30-S-120-E1-C",
		)

	def test_neon_part_number_places_cct_and_output_after_the_spec(self):
		service = self.service()
		self.assertEqual(
			service._build_neon_part_number({}, SPEC, offering(), [SEGMENT]),
			"TAPE-SH01-24V-5W-30-S-150-E2-C",
		)
		jumpered = service._build_neon_part_number({}, SPEC, offering(), [SEGMENT, {**SEGMENT, "segment_index": 2}])
		self.assertRegex(jumpered, r"^TAPE-SH01-24V-5W-30-S-300-J\([0-9A-F]{4}\)$")

	def test_builds_differing_only_in_cct_or_output_get_different_part_numbers(self):
		service = self.service()
		numbers = {
			service._build_neon_part_number({}, SPEC, offering(cct, output), [SEGMENT])
			for cct in ("3000K", "4000K")
			for output in ("Standard", "High")
		}
		self.assertEqual(len(numbers), 4)

	def test_part_number_starts_with_the_item_the_spec_currently_ships(self):
		# A spec autonamed from its I/O-era Item, then re-pointed at the IP-rated variant:
		# the BOM ships spec.item, so the part number must carry it too.
		service = self.service()
		repointed = Record(name="ILL-SH01-SW-I", item="ILL-SH01-SW-20")
		self.assertEqual(
			service._build_neon_part_number({}, repointed, offering(), [SEGMENT]),
			"ILL-SH01-SW-20-30-S-150-E2-C",
		)
		sel = {"feed_type": "Standard", "lead_length_inches": 12}
		self.assertEqual(
			service._build_tape_part_number(sel, repointed, offering(), 120 * 25.4),
			"ILL-SH01-SW-20-30-S-120-E1-C",
		)

	def test_selections_fill_in_when_no_offering_is_resolved_and_missing_codes_stay_visible(self):
		service = self.service()
		sel = {"cct": "4000K", "output_level": "Unknown"}
		self.assertEqual(
			service._build_neon_part_number(sel, SPEC, None, [SEGMENT]),
			"TAPE-SH01-24V-5W-40-xx-150-E2-C",
		)


class CatalogPartNumbers(ServiceMixin, unittest.TestCase):
	"""Catalog specs ship one Item per offering whose code already names the CCT and output."""

	SPEC = Record(name="COB-SD-SW-20-30K-300-3M-WH-8MM", item="COB-SD-SW-20-30K-300-3M-WH-8MM")
	OFFERING = Record(name="COB-SD-SW-20-30K-300", cct="3000K", output_level="300 lm/ft")

	def catalog_service(self):
		return self.service(codes=CATALOG_CODES, offerings_per_spec=1)

	def test_cct_and_output_are_not_repeated_after_the_item_code(self):
		service = self.catalog_service()
		sel = {"lead_length_inches": 12}
		self.assertEqual(
			service._build_tape_part_number(sel, self.SPEC, self.OFFERING, 88.6 * 25.4),
			"COB-SD-SW-20-30K-300-3M-WH-8MM-88.6-1-C",
		)
		self.frappe.db.count.assert_called_with("ilL-Rel-Tape Offering", {"tape_spec": self.SPEC.name})

	def test_neon_part_numbers_do_not_repeat_cct_and_output(self):
		service = self.catalog_service()
		spec = Record(name="NON-PNC-SW-67-30K-150-WH", item="NON-PNC-SW-67-30K-150-WH")
		self.assertEqual(
			service._build_neon_part_number({}, spec, self.OFFERING, [SEGMENT]),
			"NON-PNC-SW-67-30K-150-WH-150-E2-C",
		)
		jumpered = service._build_neon_part_number({}, spec, self.OFFERING, [SEGMENT, {**SEGMENT, "segment_index": 2}])
		self.assertRegex(jumpered, r"^NON-PNC-SW-67-30K-150-WH-300-J\([0-9A-F]{4}\)$")

	def test_a_spec_with_no_recorded_offering_is_not_treated_as_shared(self):
		service = self.service(codes=CATALOG_CODES, offerings_per_spec=0)
		sel = {"lead_length_inches": 12}
		self.assertEqual(
			service._build_tape_part_number(sel, self.SPEC, self.OFFERING, 88.6 * 25.4),
			"COB-SD-SW-20-30K-300-3M-WH-8MM-88.6-1-C",
		)


class BuildIdentity(unittest.TestCase):
	def test_the_part_number_is_part_of_the_build_fingerprint(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

		with load_service(ROOT + ".api.tape_neon_configurator") as (service, frappe):
			frappe.db.get_value.return_value = {"input_voltage": "24V"}
			template = Record(name="T", template_code="T")

			def build(part_number):
				result = {
					"selections": {"cct": "3000K"},
					"computed": {"total_watts": 20},
					"resolved_items": {"tape_spec": "SPEC"},
					"components": [{"item_code": "TAPE", "qty": 5, "stock_uom": "Foot"}],
					"cables": [],
					"engineering_sources": {},
					"part_number": part_number,
				}
				return service._tape_neon_snapshot(template, result, True)

			old, new = build("TAPE-150-E2-C"), build("TAPE-30-S-150-E2-C")
			self.assertEqual(new["part_number"], "TAPE-30-S-150-E2-C")
			self.assertEqual(old["engineering_inputs"], new["engineering_inputs"])
			self.assertNotEqual(fingerprint(old), fingerprint(new))


if __name__ == "__main__":
	unittest.main()
