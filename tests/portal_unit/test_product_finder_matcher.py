"""Real eligibility and scoring with controlled catalog and rollout boundaries."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"


def question(facet="finish", **changes):
	return {
		"id": facet,
		"type": "single",
		"label": facet,
		"facet": facet,
		"match_mode": "Hard",
		"comparison": "Any of",
		"unknown_policy": "Verify",
		"options": [{"value": "white", "label": "White"}],
		"value_maps": {"white": [("ilL-Attribute-Finish", "ERP White")]},
		**changes,
	}


def product(name, facets, **changes):
	return {
		"name": name,
		"title": name,
		"family": "Linear Fixture",
		"product_type": "Linear Fixture",
		"capability": "configure",
		"facets": facets,
		**changes,
	}


class Matcher(unittest.TestCase):
	def context(self, questions, products):
		definition = {"version": 1, "settings": {"results_limit": 60}, "questions": questions}
		return load_service(
			BASE + ".matcher",
			{
				BASE + ".facts": types.SimpleNamespace(load=lambda: products, catalog_stamp=lambda: "stamp"),
				BASE + ".server_definition": types.SimpleNamespace(load=lambda: definition),
				ROOT + ".portal.rollout": types.SimpleNamespace(reason=lambda *a, **kw: "ok"),
			},
		)

	def test_hard_fail_unknown_policies_and_verification_penalty(self):
		products = [
			product("A", {"finish": frozenset(["ERP White"])}),
			product("B", {}),
			product("C", {"finish": frozenset(["Black"])}),
		]
		for policy, count, verify in [("Verify", 2, 1), ("Exclude", 1, 0), ("Include silently", 2, 0)]:
			with (
				self.subTest(policy=policy),
				self.context([question(unknown_policy=policy)], products) as (service, _frappe),
			):
				result = service.match({"finish": "white"})
				self.assertEqual((result["counts"]["match"], result["counts"]["verify"]), (count, verify))
				self.assertEqual(result["matches"][0]["name"], "A")
				if policy == "Verify":
					self.assertEqual(result["matches"][1]["score"], 45)

	def test_unmapped_rank_number_band_and_range(self):
		questions = [
			question(),
			question(
				"ip_rating",
				comparison="Meets or exceeds",
				options=[
					{"value": "67", "label": "IP67", "rank": 67},
					{"value": "68", "label": "IP68", "rank": 68},
				],
				value_maps={"67": [("ip", "IP67")], "68": [("ip", "IP68")]},
			),
			question("driver_wattage", type="number", comparison="At least", options=[], value_maps={}),
			question(
				"lumens_per_ft",
				comparison="Within band",
				options=[{"value": "task", "label": "Task", "numeric_min": 300, "numeric_max": 600}],
			),
			question("cct_range", type="range", comparison="Range covers", options=[]),
		]
		with self.context(questions, []) as (service, _frappe):
			answers = {
				"finish": "white",
				"ip_rating": "67",
				"driver_wattage": 80,
				"lumens_per_ft": "task",
				"cct_range": {"low": 2700, "high": 5000},
			}
			needed = service.requirements({"questions": questions}, answers)
			p = product(
				"P",
				{
					"ip_rating": {"IP68"},
					"driver_wattage": (60, 100),
					"lumens_per_ft": (450,),
					"cct_range": (2200, 6500),
				},
			)
			self.assertEqual(
				[service.assess(r, p) for r in needed], ["unknown", "pass", "pass", "pass", "pass"]
			)
			questions[0]["value_maps"] = {}
			self.assertEqual(
				service.assess(
					service.requirements({"questions": questions}, answers)[0],
					product("P", {"finish": {"ERP White"}}),
				),
				"unknown",
			)

	def test_relaxation_counts_limit_and_eliminating_question(self):
		q = question(match_mode="Soft", relax_priority=1)
		products = [product("A", {"finish": {"Black"}}), product("B", {"finish": {"Black"}})]
		with self.context([q], products) as (service, _frappe):
			result = service.match({"finish": "white"}, limit=1)
			self.assertEqual(result["relaxed"], ["finish"])
			self.assertEqual(result["counts"]["match"], 2)
			self.assertEqual(len(result["matches"]), 1)
		with self.context([question()], products) as (service, _frappe):
			result = service.match({"finish": "white"})
			self.assertTrue(result["no_hard_match"])
			self.assertEqual(result["eliminated_by"]["question"], "finish")

	def test_no_preference_and_rollout(self):
		q = question(options=[{"value": "any", "label": "Any", "no_preference": True}])
		with self.context([q], [product("A", {})]) as (service, _frappe):
			self.assertEqual(service.match({"finish": "any"})["matches"][0]["verify"], [])
			import sys

			sys.modules[ROOT + ".portal.rollout"].reason = lambda *a, **kw: "pilot_only"
			self.assertEqual(service.match({})["matches"], [])

	def test_companions_and_live_counts_cache(self):
		products = [
			product(
				"A", {"finish": {"ERP White"}, "output_voltage": {"24 V"}, "dimming_protocol": {"0-10V"}}
			),
			product(
				"D",
				{"output_voltage": {"24 V"}, "dimming_protocol": {"0-10V"}},
				family="Driver",
				product_type="Driver",
			),
			product("C", {"dimming_protocol": {"DMX"}}, family="Controller", product_type="Controller"),
		]
		with self.context([question()], products) as (service, frappe):
			self.assertEqual(
				service.companions([{"name": "A"}], {}, products),
				[{"name": "D", "relation": "Powers 24 V with 0-10V dimming"}],
			)
			cache = MagicMock()
			cache.get_value.return_value = None
			frappe.cache = lambda: cache
			result = service.evaluate({"finish": "white"}, "finish")
			self.assertEqual(result["options"]["white"], {"match": 1, "verify": 2})
			self.assertIn("ill_product_finder:eval:1:stamp:", cache.set_value.call_args.args[0])
