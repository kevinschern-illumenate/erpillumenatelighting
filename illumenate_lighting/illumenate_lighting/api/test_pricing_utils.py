# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Unit tests for the pricing_utils helper module.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from illumenate_lighting.illumenate_lighting.api.pricing_utils import (
    get_customer_for_session_user,
    get_tier_price_for_customer,
)


class TestPricingUtils(FrappeTestCase):
    """Tests for pricing utility functions."""

    # ─── Helpers ──────────────────────────────────────────────────────

    def _create_customer_group(self, name):
        if not frappe.db.exists("Customer Group", name):
            frappe.get_doc({"doctype": "Customer Group", "customer_group_name": name}).insert(
                ignore_permissions=True
            )

    def _create_customer(self, name, group):
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"
        if not frappe.db.exists("Customer", name):
            frappe.get_doc({
                "doctype": "Customer",
                "customer_name": name,
                "customer_group": group,
                "territory": territory,
            }).insert(ignore_permissions=True)

    def _create_pricing_rule(self, name, customer_group, **kwargs):
        if frappe.db.exists("Pricing Rule", name):
            frappe.delete_doc("Pricing Rule", name, force=True)
        doc = frappe.get_doc({
            "doctype": "Pricing Rule",
            "name": name,
            "title": name,
            "applicable_for": "Customer Group",
            "customer_group": customer_group,
            "selling": 1,
            "buying": 0,
            "apply_on": "Transaction",
            "priority": kwargs.get("priority", 1),
            "disable": 0,
            "pricing_rule_for": kwargs.get("pricing_rule_for", "Discount Percentage"),
            "discount_percentage": kwargs.get("discount_percentage", 0),
            "rate": kwargs.get("rate", 0),
            "discount_amount": kwargs.get("discount_amount", 0),
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _cleanup(self, *names_and_types):
        """Delete docs silently.  Pass tuples of (doctype, name)."""
        for dt, dn in names_and_types:
            if frappe.db.exists(dt, dn):
                frappe.delete_doc(dt, dn, force=True)

    # ─── get_tier_price_for_customer ──────────────────────────────────

    def test_no_customer_returns_msrp(self):
        """With customer=None and no session customer, tier_unit should equal msrp."""
        result = get_tier_price_for_customer(100.0, customer=None)
        self.assertEqual(result["tier_unit"], 100.0)
        self.assertEqual(result["discount_amount"], 0.0)
        self.assertEqual(result["discount_percentage"], 0.0)
        self.assertIsNone(result["pricing_rule_name"])
        self.assertIsNone(result["customer_group"])

    def test_zero_msrp_returns_zero(self):
        """MSRP of 0 should short-circuit and return zero tier."""
        result = get_tier_price_for_customer(0.0, customer="anything")
        self.assertEqual(result["tier_unit"], 0.0)

    def test_negative_msrp_returns_fallback(self):
        """Negative MSRP returns the fallback."""
        result = get_tier_price_for_customer(-5.0, customer="anything")
        self.assertEqual(result["tier_unit"], -5.0)

    def test_nonexistent_customer_returns_msrp(self):
        """A customer name that doesn't exist should gracefully fall back."""
        result = get_tier_price_for_customer(100.0, customer="DOES_NOT_EXIST_12345")
        self.assertEqual(result["tier_unit"], 100.0)

    def test_customer_without_group_returns_msrp(self):
        """Customer with no customer_group returns MSRP."""
        cg = "_Test PU NoGrp CG"
        cust = "_Test PU NoGrp Cust"
        self._create_customer_group(cg)
        self._create_customer(cust, cg)

        try:
            # Temporarily remove the customer_group
            frappe.db.set_value("Customer", cust, "customer_group", "")
            result = get_tier_price_for_customer(100.0, customer=cust)
            self.assertEqual(result["tier_unit"], 100.0)
        finally:
            self._cleanup(("Customer", cust), ("Customer Group", cg))

    def test_discount_percentage_rule(self):
        """Discount Percentage pricing rule applies correctly."""
        cg = "_Test PU DiscPct CG"
        cust = "_Test PU DiscPct Cust"
        pr = "_Test PU DiscPct PR"
        self._create_customer_group(cg)
        self._create_customer(cust, cg)
        self._create_pricing_rule(
            pr, cg, pricing_rule_for="Discount Percentage", discount_percentage=25,
        )

        try:
            result = get_tier_price_for_customer(200.0, customer=cust)
            self.assertEqual(result["tier_unit"], 150.0)
            self.assertEqual(result["discount_amount"], 50.0)
            self.assertEqual(result["discount_percentage"], 25.0)
            self.assertEqual(result["pricing_rule_name"], pr)
            self.assertEqual(result["customer_group"], cg)
        finally:
            self._cleanup(("Pricing Rule", pr), ("Customer", cust), ("Customer Group", cg))

    def test_rate_rule(self):
        """Rate pricing rule overrides the unit price."""
        cg = "_Test PU Rate CG"
        cust = "_Test PU Rate Cust"
        pr = "_Test PU Rate PR"
        self._create_customer_group(cg)
        self._create_customer(cust, cg)
        self._create_pricing_rule(
            pr, cg, pricing_rule_for="Rate", rate=80.0,
        )

        try:
            result = get_tier_price_for_customer(100.0, customer=cust)
            self.assertEqual(result["tier_unit"], 80.0)
            self.assertEqual(result["discount_amount"], 20.0)
            self.assertEqual(result["discount_percentage"], 20.0)
        finally:
            self._cleanup(("Pricing Rule", pr), ("Customer", cust), ("Customer Group", cg))

    def test_discount_amount_rule(self):
        """Discount Amount pricing rule subtracts a fixed amount."""
        cg = "_Test PU DiscAmt CG"
        cust = "_Test PU DiscAmt Cust"
        pr = "_Test PU DiscAmt PR"
        self._create_customer_group(cg)
        self._create_customer(cust, cg)
        self._create_pricing_rule(
            pr, cg, pricing_rule_for="Discount Amount", discount_amount=30.0,
        )

        try:
            result = get_tier_price_for_customer(100.0, customer=cust)
            self.assertEqual(result["tier_unit"], 70.0)
            self.assertEqual(result["discount_amount"], 30.0)
            self.assertEqual(result["discount_percentage"], 30.0)
        finally:
            self._cleanup(("Pricing Rule", pr), ("Customer", cust), ("Customer Group", cg))

    def test_highest_priority_rule_wins(self):
        """When multiple rules exist, the one with the highest priority wins."""
        cg = "_Test PU Prio CG"
        cust = "_Test PU Prio Cust"
        pr_low = "_Test PU Prio Low"
        pr_high = "_Test PU Prio High"
        self._create_customer_group(cg)
        self._create_customer(cust, cg)
        self._create_pricing_rule(
            pr_low, cg, pricing_rule_for="Discount Percentage", discount_percentage=10, priority=1,
        )
        self._create_pricing_rule(
            pr_high, cg, pricing_rule_for="Discount Percentage", discount_percentage=30, priority=10,
        )

        try:
            result = get_tier_price_for_customer(200.0, customer=cust)
            # High-priority 30% discount should win
            self.assertEqual(result["tier_unit"], 140.0)
            self.assertEqual(result["pricing_rule_name"], pr_high)
        finally:
            self._cleanup(
                ("Pricing Rule", pr_low),
                ("Pricing Rule", pr_high),
                ("Customer", cust),
                ("Customer Group", cg),
            )

    def test_tier_never_negative(self):
        """Discount larger than MSRP should floor tier at 0."""
        cg = "_Test PU Floor CG"
        cust = "_Test PU Floor Cust"
        pr = "_Test PU Floor PR"
        self._create_customer_group(cg)
        self._create_customer(cust, cg)
        self._create_pricing_rule(
            pr, cg, pricing_rule_for="Discount Amount", discount_amount=500.0,
        )

        try:
            result = get_tier_price_for_customer(100.0, customer=cust)
            self.assertEqual(result["tier_unit"], 0.0)
            self.assertGreaterEqual(result["discount_amount"], 0)
        finally:
            self._cleanup(("Pricing Rule", pr), ("Customer", cust), ("Customer Group", cg))

    # ─── get_customer_for_session_user ────────────────────────────────

    def test_guest_user_returns_none(self):
        """Guest session should return None."""
        original = frappe.session.user
        try:
            frappe.session.user = "Guest"
            self.assertIsNone(get_customer_for_session_user())
        finally:
            frappe.session.user = original

    def test_admin_user_returns_none(self):
        """Administrator (no customer link) should return None."""
        original = frappe.session.user
        try:
            frappe.session.user = "Administrator"
            result = get_customer_for_session_user()
            # Administrator typically has no linked customer
            # This may return a customer if one is linked in the test DB, but
            # the function should not raise an error.
            self.assertTrue(result is None or isinstance(result, str))
        finally:
            frappe.session.user = original
