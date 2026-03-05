# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Pricing Utilities

Reusable helpers for resolving customer-specific tier pricing via ERPNext Pricing Rules.
"""

from typing import Any

import frappe


def get_customer_for_session_user() -> str | None:
    """
    Look up the Customer linked to the current session user.

    Checks the Portal User child table on Customer documents to find a match
    for ``frappe.session.user``.  Falls back to a direct ``Dynamic Link`` lookup
    on the Contact doctype.

    Returns:
        Customer name (str) or None if the user is Guest or no link exists.
    """
    user = frappe.session.user
    if not user or user == "Guest":
        return None

    # Primary: Portal User child table on Customer
    customer = frappe.db.get_value(
        "Portal User",
        {"user": user, "parenttype": "Customer"},
        "parent",
    )
    if customer:
        return customer

    # Fallback: Contact → Dynamic Link → Customer
    contact_name = frappe.db.get_value("Contact", {"user": user}, "name")
    if contact_name:
        customer = frappe.db.get_value(
            "Dynamic Link",
            {"parent": contact_name, "parenttype": "Contact", "link_doctype": "Customer"},
            "link_name",
        )
        if customer:
            return customer

    return None


def get_tier_price_for_customer(msrp_unit: float, customer: str | None = None) -> dict[str, Any]:
    """
    Look up the customer's Customer Group, find applicable Pricing Rules,
    and calculate the tier price.

    The function queries ERPNext ``Pricing Rule`` documents that:
    - Are enabled (``disable = 0``)
    - Apply to Selling (``selling = 1``)
    - Target a Customer Group matching the customer's group
    - Support discount types: Discount Percentage, Rate, Discount Amount

    When multiple rules match, the one with the highest ``priority`` wins
    (ERPNext convention: higher number = higher priority).

    Args:
        msrp_unit: The MSRP unit price to discount from.
        customer: Customer name (primary key).  If *None*, the current
            session user's linked Customer is resolved automatically.

    Returns:
        dict with keys:
            - tier_unit (float)
            - discount_amount (float)
            - discount_percentage (float)
            - pricing_rule_name (str | None)
            - customer_group (str | None)
    """
    fallback = {
        "tier_unit": round(msrp_unit, 2),
        "discount_amount": 0.0,
        "discount_percentage": 0.0,
        "pricing_rule_name": None,
        "customer_group": None,
    }

    if msrp_unit <= 0:
        return fallback

    # Resolve customer if not provided
    if not customer:
        customer = get_customer_for_session_user()

    if not customer:
        return fallback

    # Resolve Customer Group
    customer_group = frappe.db.get_value("Customer", customer, "customer_group")
    if not customer_group:
        return fallback

    # Query active Pricing Rules for this Customer Group (selling side)
    pricing_rules = frappe.get_all(
        "Pricing Rule",
        filters={
            "disable": 0,
            "selling": 1,
            "applicable_for": "Customer Group",
            "customer_group": customer_group,
        },
        fields=[
            "name",
            "priority",
            "pricing_rule_for",      # "Discount Percentage" | "Rate" | "Discount Amount"
            "discount_percentage",
            "rate",
            "discount_amount",
        ],
        order_by="priority desc, modified desc",
    )

    if not pricing_rules:
        fallback["customer_group"] = customer_group
        return fallback

    # Use the highest-priority rule
    rule = pricing_rules[0]
    tier_unit = msrp_unit
    pricing_rule_name = rule.name

    rule_type = (rule.pricing_rule_for or "").strip()

    if rule_type == "Discount Percentage":
        pct = float(rule.discount_percentage or 0)
        tier_unit = msrp_unit * (1 - pct / 100)
    elif rule_type == "Rate":
        tier_unit = float(rule.rate or msrp_unit)
    elif rule_type == "Discount Amount":
        tier_unit = msrp_unit - float(rule.discount_amount or 0)

    # Ensure tier never goes below zero
    tier_unit = max(tier_unit, 0.0)

    discount_amount = msrp_unit - tier_unit
    discount_percentage = (discount_amount / msrp_unit * 100) if msrp_unit else 0.0

    return {
        "tier_unit": round(tier_unit, 2),
        "discount_amount": round(discount_amount, 2),
        "discount_percentage": round(discount_percentage, 2),
        "pricing_rule_name": pricing_rule_name,
        "customer_group": customer_group,
    }
