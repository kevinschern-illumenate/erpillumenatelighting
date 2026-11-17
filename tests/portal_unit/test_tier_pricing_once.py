"""Schedule dealer pricing looks the customer's tier rule up once, with unchanged results."""

import unittest

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.pricing_utils"
RULES = {
	"pct": Record(
		name="PR-PCT",
		priority=2,
		rate_or_discount="Discount Percentage",
		discount_percentage=20,
		rate=0,
		discount_amount=0,
	),
	"rate": Record(
		name="PR-RATE", priority=1, rate_or_discount="Rate", discount_percentage=0, rate=70, discount_amount=0
	),
	"amount": Record(
		name="PR-AMT",
		priority=1,
		rate_or_discount="Discount Amount",
		discount_percentage=0,
		rate=0,
		discount_amount=150,
	),
}


class TierPricing(unittest.TestCase):
	def wire(self, frappe, group="Gold", rules=()):
		frappe.db.get_value.side_effect = lambda doctype, name, field: group
		frappe.get_all.side_effect = lambda *args, **kwargs: list(rules)

	def test_split_helpers_match_the_per_line_function(self):
		cases = [
			("Gold", [RULES["pct"]]),
			("Gold", [RULES["rate"]]),
			("Gold", [RULES["amount"]]),
			("Gold", []),
			(None, []),
		]
		for group, rules in cases:
			for msrp in (100.0, 49.99, 0.0, -5.0):
				with self.subTest(group=group, rules=[r.name for r in rules], msrp=msrp):
					with load_service(MODULE) as (pricing, frappe):
						self.wire(frappe, group, rules)
						expected = pricing.get_tier_price_for_customer(msrp, customer="CUST-1")
						self.assertEqual(
							pricing.apply_tier_rule(msrp, *pricing.customer_tier_rule("CUST-1")), expected
						)

	def test_rule_is_looked_up_once_for_many_lines(self):
		with load_service(MODULE) as (pricing, frappe):
			self.wire(frappe, "Gold", [RULES["pct"]])
			group, rule = pricing.customer_tier_rule("CUST-1")
			prices = [pricing.apply_tier_rule(msrp, group, rule)["tier_unit"] for msrp in (100, 200, 300)]
			self.assertEqual(prices, [80.0, 160.0, 240.0])
			self.assertEqual(frappe.db.get_value.call_count, 1)
			self.assertEqual(frappe.get_all.call_count, 1)

	def test_no_customer_makes_no_query(self):
		with load_service(MODULE) as (pricing, frappe):
			self.assertEqual(pricing.customer_tier_rule(None), (None, None))
			frappe.db.get_value.assert_not_called()
			self.assertEqual(pricing.apply_tier_rule(10, None, None)["tier_unit"], 10)


class ScheduleDealerPricingSource(unittest.TestCase):
	def test_endpoint_prices_lines_with_one_rule_lookup(self):
		import pathlib

		source = (pathlib.Path(ROOT.replace(".", "/")) / "api/portal.py").read_text()
		body = source[source.index("def get_schedule_dealer_pricing") :]
		ends = [i for i in (body.find("\n@frappe.whitelist"), body.find("\ndef ", 1)) if i > 0]
		body = body[: min(ends)] if ends else body
		self.assertEqual(body.count("customer_tier_rule(customer)"), 1)
		self.assertNotIn("get_tier_price_for_customer(", body)
		loop = body[body.index("for line in lines:") :]
		self.assertNotIn("customer_tier_rule", loop, "the rule is not looked up per line")


if __name__ == "__main__":
	unittest.main()
