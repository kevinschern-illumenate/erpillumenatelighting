"""Cross-family configuration contract (hardening plan 6.1).

One set of assertions over the shared rules every family engine relies on:
canonical mm with the dealer's display unit, sum-then-round money, breakdown
shape, and reopen equality. It is the safety net for 6.2 and 6.3.
"""

import json
import types
import unittest

from test_services import ROOT, Record, load_service

UNIT_CASES = [
	("mm", 609.6),
	("in", 24),
	("in", 24.33),
	("in", 0.125),
	("ft", 12.5),
	("ft", 3),
	("m", 1.234),
]

# (base, $/ft, length_mm, option adders). The cases include half-cent boundaries
# where rounding each adder first would give a different total.
PRICE_CASES = [
	(10, 2.5, 304.8, [1.005]),
	(0, 3.333, 1000, [0.004, 0.004]),
	(12.345, 0, 0, [0.001]),
	(99.995, 1.11, 2540, []),
	(5, 7.77, 777.7, [2.225, 0.115]),
]


class Units(unittest.TestCase):
	def contract(self):
		return load_service(ROOT + ".api.configuration_contract")

	def test_every_unit_round_trips_through_canonical_mm(self):
		with self.contract() as (contract, _):
			for unit, value in UNIT_CASES:
				with self.subTest(unit=unit, value=value):
					mm = contract.dealer_length_mm(unit, value)
					self.assertEqual(contract.display_length(mm, unit), {"unit": unit, "value": float(value)})

	def test_feet_and_inches_round_trip_and_blank_parts_are_zero(self):
		with self.contract() as (contract, _):
			mm = contract.dealer_length_mm("ft_in", feet=3, inches=6.5)
			self.assertEqual(mm, 1079.5)
			self.assertEqual(contract.display_length(mm, "ft_in"), {"unit": "ft_in", "feet": 3, "inches": 6.5})
			self.assertEqual(contract.dealer_length_mm("ft_in", feet="", inches=None), 0)
			self.assertEqual(contract.dealer_length_mm("in", None), 0)
			with self.assertRaises(ValueError):
				contract.dealer_length_mm("furlong", 1)
			with self.assertRaises(ValueError):
				contract.dealer_length_mm("in", "abc")

	def test_tape_and_neon_parse_typed_lengths_identically(self):
		with load_service(ROOT + ".api.tape_neon_configurator") as (engine, _):
			for unit, typed in (("in", {"value": 24}), ("ft", {"value": 2}), ("ft_in", {"feet": 2, "inches": 0})):
				tape = {"tape_length_unit": unit, **{"tape_length_" + k: v for k, v in typed.items()}}
				neon = {"fixture_length_unit": unit, **{"fixture_length_" + k: v for k, v in typed.items()}}
				with self.subTest(unit=unit):
					self.assertEqual(engine._parse_tape_length(tape), 609.6)
					self.assertEqual(engine._parse_neon_fixture_length(neon), 609.6)
			# Units the parsers never supported keep meaning inches.
			self.assertEqual(engine._parse_tape_length({"tape_length_unit": "mm", "tape_length_value": 1}), 25.4)

	def test_exact_multiples_keep_every_cut_increment(self):
		with self.contract() as (contract, _):
			misses = [
				(pitch, count)
				for pitch in (0.5, 1, 1.5, 1.97, 2, 3.94)
				for count in range(1, 300)
				if contract.whole_increments(
					contract.dealer_length_mm("in", round(pitch * count, 6)),
					contract.dealer_length_mm("in", pitch),
				)
				!= count
			]
			self.assertEqual(misses, [])
			self.assertEqual(contract.whole_increments(100, 50.8), 1)


def fixture_template(base, per_ft, adders):
	return Record(
		base_price_msrp=base,
		price_per_ft_msrp=per_ft,
		pricing_length_basis="L_tape_cut",
		allowed_options=[
			Record(option_type="Finish", finish=f"F{i}", is_active=1, msrp_adder=adder) for i, adder in enumerate(adders)
		][:1]
		+ [
			Record(option_type="Mounting Method", mounting_method=f"M{i}", is_active=1, msrp_adder=adder)
			for i, adder in enumerate(adders)
		][1:2],
	)


class Money(unittest.TestCase):
	def fixture_total(self, base, per_ft, length, adders):
		with load_service(ROOT + ".api.configurator_engine") as (engine, _):
			engine.get_tier_price_for_customer = lambda msrp, customer=None: {
				"tier_unit": msrp,
				"discount_amount": 0,
				"discount_percentage": 0,
				"pricing_rule_name": None,
				"customer_group": None,
			}
			return engine._calculate_pricing(
				"T",
				{"profile_item": "P"},
				{"tape_cut_length_mm": length},
				"F0" if adders else None,
				None,
				"M1" if len(adders) > 1 else None,
				None,
				None,
				None,
				None,
				None,
				1,
				template_doc=fixture_template(base, per_ft, adders),
			)

	def tape_pricing(self, base, per_ft, length, adders):
		with load_service(ROOT + ".api.tape_neon_configurator") as (engine, frappe):
			frappe.db.get_value.return_value = {"base_price_msrp": base, "price_per_ft_msrp": per_ft}
			by_type = {"CCT": adders[:1], "Output Level": adders[1:2]}
			frappe.get_all.side_effect = lambda doctype, filters=None, **_: [
				Record(msrp_adder=adder) for adder in by_type.get(filters["option_type"], [])
			]
			return engine._compute_template_tape_neon_pricing(
				"TN", {"cct": "30K", "output_level": "HO"}, length, 0, is_neon=True
			)

	def test_fixture_and_tape_neon_round_their_sums_once(self):
		for case in PRICE_CASES:
			with self.subTest(case=case):
				fixture = self.fixture_total(*case)
				tape = self.tape_pricing(*case)
				base, per_ft, length, adders = case
				# Fixture option adders are per foot, so they scale with the priced length.
				feet = length / 304.8
				self.assertEqual(fixture["msrp_unit"], round(base + feet * (per_ft + sum(adders)), 2))
				# Tape and neon option adders stay a flat amount.
				exact = base + feet * per_ft + sum(adders)
				self.assertEqual(tape["total_price_msrp"], round(exact, 2))
				self.assertAlmostEqual(tape["total_price_msrp_exact"], exact, places=9)

	def test_breakdowns_share_one_shape(self):
		fixture = self.fixture_total(*PRICE_CASES[4])["adder_breakdown"]
		tape = self.tape_pricing(*PRICE_CASES[4])["adder_breakdown"]
		for rows in (fixture, tape):
			self.assertEqual([row["component"] for row in rows[:2]], ["base", "length"])
			for row in rows:
				self.assertEqual(set(row), {"component", "description", "amount"})
				self.assertEqual(row["amount"], round(row["amount"], 2))

	def test_tape_build_rounds_template_and_parts_once(self):
		template = types.SimpleNamespace(
			_compute_template_tape_neon_pricing=lambda *args: {
				"total_price_msrp": 10.0,
				"total_price_msrp_exact": 10.004,
			}
		)
		with load_service(
			ROOT + ".api.tape_neon_pricing", {ROOT + ".api.tape_neon_configurator": template}
		) as (engine, _):
			engine.selling_amount = lambda item, qty: 0.004 * qty
			result = {
				"product_category": "LED Tape",
				"selections": {},
				"resolved_items": {},
				"computed": {"segments": [{"manufacturable_length_mm": 100}]},
				"components": [
					{"item_code": "TAPE", "qty": 1, "role": "light engine"},
					{"item_code": "CLIP", "qty": 1, "role": "mounting"},
				],
			}
			new = engine.price_result(json.loads(json.dumps(result)), "T")["computed"]["total_price_msrp"]
			old = engine.price_result(result, "T", legacy_rounding=True)["computed"]["total_price_msrp"]
		self.assertEqual((old, new), (10.0, 10.01))

	def test_kit_sums_components_then_rounds_once(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (engine, frappe):
			frappe.db.get_value.side_effect = lambda doctype, filters, field: {"A": 0.004, "B": 0.004}[filters["item_code"]]
			total = engine._compute_kit_pricing({"profile": {"item": "A", "qty": 1}, "lens": {"item": "B", "qty": 1}})
		self.assertEqual(total, {"total_price_msrp": 0.01})

	def test_shared_rule(self):
		with load_service(ROOT + ".api.pricing_utils") as (pricing, _):
			self.assertEqual(pricing.sum_then_round(0.004, 0.004), 0.01)
			self.assertEqual(pricing.sum_then_round(), 0)
			self.assertEqual(pricing.sum_then_round(None, "1.005", 2), 3.0)


class Reopen(unittest.TestCase):
	def reopen(self):
		adapter = types.ModuleType(ROOT + ".portal.configuration")
		adapter.FAMILIES = {"LED Tape": ("configured_tape_neon", "ilL-Configured-Tape-Neon", "tape_neon_template")}
		adapter.resolve_line = adapter.schedule_context = lambda *a: None
		planner = types.ModuleType(ROOT + ".api.power_planner")
		planner.GROUPED = "GROUPED"
		return load_service(
			ROOT + ".portal.configuration_reopen",
			{ROOT + ".portal.configuration": adapter, ROOT + ".api.power_planner": planner},
		)

	def test_saved_request_keeps_the_dealers_unit(self):
		request = {"schema_version": 2, "family": "LED Tape", "segments": [{"tape_length_unit": "ft", "tape_length_value": 2}]}
		with self.reopen() as (reopen, _):
			line = Record(ill_configurator_request=json.dumps(request))
			self.assertEqual(reopen.for_line(line), request)

	def test_snapshot_fallback_reopens_exact_inches(self):
		build = {"selections": {"cct": "30K"}, "segments": [{"requested_length_mm": 609.6, "end_cable_length_inches": 6}]}
		with self.reopen() as (reopen, frappe):
			frappe.get_doc.return_value = Record(build_snapshot_json=json.dumps(build), assembly_mode=None, power_plan_json=None)
			line = Record(product_type="LED Tape", configured_tape_neon="CTN-1", tape_neon_template="TN")
			segment = reopen.for_line(line)["segments"][0]
		self.assertEqual((segment["tape_length_unit"], segment["tape_length_value"]), ("in", 24.0))
		self.assertEqual(segment["end_feed_length_inches"], 6)


if __name__ == "__main__":
	unittest.main()
