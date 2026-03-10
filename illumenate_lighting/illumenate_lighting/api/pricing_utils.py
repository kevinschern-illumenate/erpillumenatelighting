# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Pricing & Stock Utilities

Reusable helpers for resolving customer-specific tier pricing via ERPNext Pricing Rules
and BOM-level stock availability checks against ``tabBin``.
"""

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


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
            "rate_or_discount",      # "Discount Percentage" | "Rate" | "Discount Amount"
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

    rule_type = (rule.rate_or_discount or "").strip()

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


# =============================================================================
# Stock Availability Helpers
# =============================================================================

def _is_privileged_user() -> bool:
    """Return True when the session user may see raw stock quantities."""
    user = frappe.session.user
    if not user or user == "Guest":
        return False
    from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
        _is_dealer_user,
        _is_internal_user,
    )
    return _is_dealer_user(user) or _is_internal_user(user)


def _bulk_stock_query(item_codes: list[str]) -> dict[str, float]:
    """
    Query ``tabBin`` for actual_qty summed across all warehouses.

    Args:
        item_codes: List of distinct item codes.

    Returns:
        Mapping of item_code → total actual_qty (float).
    """
    if not item_codes:
        return {}

    placeholders = ", ".join(["%s"] * len(item_codes))
    rows = frappe.db.sql(
        f"""SELECT item_code, IFNULL(SUM(actual_qty), 0) AS total_qty
           FROM `tabBin`
           WHERE item_code IN ({placeholders})
           GROUP BY item_code""",
        tuple(item_codes),
        as_dict=True,
    )

    stock_map: dict[str, float] = {r.item_code: flt(r.total_qty) for r in rows}
    # Ensure every requested item appears (even with 0)
    for ic in item_codes:
        stock_map.setdefault(ic, 0.0)
    return stock_map


def get_bom_stock_availability(configured_fixture_id: str) -> dict[str, Any]:
    """
    Check stock for every BOM component of a configured fixture.

    Mirrors the BOM roles from ``manufacturing_generator._create_or_get_bom()``:
    profile, lens, endcap-start, endcap-end, mounting, tape, drivers.

    Access control:
        - Guests see only ``is_sufficient`` booleans per item.
        - Dealers / internal users also see ``qty_required`` and ``qty_available``.

    Args:
        configured_fixture_id: Name of an ``ilL-Configured-Fixture`` document.

    Returns:
        dict: ``{all_in_stock: bool, items: [...]}``.
    """
    if not configured_fixture_id or not frappe.db.exists("ilL-Configured-Fixture", configured_fixture_id):
        return {"all_in_stock": False, "items": []}

    cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_id)
    return _compute_stock_for_fixture(cf)


def _compute_stock_for_fixture(cf) -> dict[str, Any]:
    """
    Core logic shared by single-fixture and batch-fixture stock checks.

    Accepts an already-loaded ``ilL-Configured-Fixture`` document.
    """
    from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
        _calculate_profile_quantity,
        _calculate_lens_quantity,
        _calculate_endcap_quantities,
        _calculate_mounting_quantity,
        _get_tape_item,
        _calculate_total_tape_length,
    )

    # Build component list: (component_type, item_code, qty_required, uom)
    components: list[tuple[str, str, float, str]] = []

    if cf.profile_item:
        qty = _calculate_profile_quantity(cf)
        if qty > 0:
            components.append(("Profile", cf.profile_item, qty, "Nos"))

    if cf.lens_item:
        qty = _calculate_lens_quantity(cf)
        if qty > 0:
            components.append(("Lens", cf.lens_item, qty, "Nos"))

    endcap_counts = _calculate_endcap_quantities(cf)
    if endcap_counts.get("feed_through_qty", 0) > 0 and cf.endcap_item_start:
        components.append(("Endcap (Start)", cf.endcap_item_start, endcap_counts["feed_through_qty"], "Nos"))
    if endcap_counts.get("solid_qty", 0) > 0 and cf.endcap_item_end:
        components.append(("Endcap (End)", cf.endcap_item_end, endcap_counts["solid_qty"], "Nos"))

    if cf.mounting_item:
        qty = _calculate_mounting_quantity(cf)
        if qty > 0:
            components.append(("Mounting Accessory", cf.mounting_item, qty, "Nos"))

    tape_item = _get_tape_item(cf)
    if tape_item:
        total_tape_mm = _calculate_total_tape_length(cf)
        tape_length_ft = total_tape_mm / 304.8
        if tape_length_ft > 0:
            components.append(("LED Tape", tape_item, round(tape_length_ft, 2), "Foot"))

    # TODO: re-enable leader cables when ready to include in stock availability
    # if cf.leader_item:
    #     leader_qty = cf.runs_count or 1
    #     components.append(("Leader Cable", cf.leader_item, leader_qty, "Nos"))

    if cf.drivers:
        for driver in cf.drivers:
            if driver.driver_item and (driver.driver_qty or 0) > 0:
                components.append(("Driver", driver.driver_item, driver.driver_qty, "Nos"))

    if not components:
        return {"all_in_stock": False, "items": []}

    # Batch stock query
    distinct_items = list({c[1] for c in components})
    stock_map = _bulk_stock_query(distinct_items)

    # Build result items
    show_qty = _is_privileged_user()
    items: list[dict[str, Any]] = []
    all_ok = True

    for comp_type, item_code, qty_req, uom in components:
        qty_avail = stock_map.get(item_code, 0.0)
        sufficient = qty_avail >= qty_req
        if not sufficient:
            all_ok = False

        entry: dict[str, Any] = {
            "component_type": comp_type,
            "item_code": item_code,
            "is_sufficient": sufficient,
        }
        if show_qty:
            entry["qty_required"] = qty_req
            entry["qty_available"] = qty_avail

        items.append(entry)

    return {"all_in_stock": all_ok, "items": items}


def get_bom_stock_for_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Check stock for an ad-hoc list of items (e.g. accessories).

    Each element in *items* must have ``item_code`` (str) and ``qty`` (number).

    Returns:
        dict: ``{all_in_stock: bool, items: [...]}``.
    """
    if not items:
        return {"all_in_stock": True, "items": []}

    distinct_codes = list({it["item_code"] for it in items if it.get("item_code")})
    stock_map = _bulk_stock_query(distinct_codes)

    show_qty = _is_privileged_user()
    result_items: list[dict[str, Any]] = []
    all_ok = True

    for it in items:
        ic = it.get("item_code", "")
        qty_req = flt(it.get("qty", 0))
        qty_avail = stock_map.get(ic, 0.0)
        sufficient = qty_avail >= qty_req
        if not sufficient:
            all_ok = False

        entry: dict[str, Any] = {
            "item_code": ic,
            "is_sufficient": sufficient,
        }
        if show_qty:
            entry["qty_required"] = qty_req
            entry["qty_available"] = qty_avail

        result_items.append(entry)

    return {"all_in_stock": all_ok, "items": result_items}


@frappe.whitelist(allow_guest=True)
def get_bom_stock_for_items_api(items_json: str) -> dict[str, Any]:
    """
    Public API endpoint wrapping :func:`get_bom_stock_for_items`.

    Args:
        items_json: JSON array of ``{item_code, qty}`` objects.

    Returns:
        dict: ``{all_in_stock, items}``.
    """
    import json
    try:
        items = json.loads(items_json) if isinstance(items_json, str) else items_json
    except (json.JSONDecodeError, TypeError):
        return {"all_in_stock": False, "items": [], "error": _("Invalid JSON")}
    return get_bom_stock_for_items(items)


def batch_stock_for_fixtures(configured_fixture_ids: list[str]) -> dict[str, dict[str, Any]]:
    """
    Batch-check stock for multiple configured fixtures with a single Bin query.

    Used by the schedule page to avoid N+1 queries.

    Args:
        configured_fixture_ids: List of ``ilL-Configured-Fixture`` names.

    Returns:
        Mapping of configured_fixture_id → stock availability dict.
    """
    from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
        _calculate_profile_quantity,
        _calculate_lens_quantity,
        _calculate_endcap_quantities,
        _calculate_mounting_quantity,
        _get_tape_item,
        _calculate_total_tape_length,
    )

    if not configured_fixture_ids:
        return {}

    # Load all fixture docs
    fixtures: dict[str, Any] = {}
    for cf_id in configured_fixture_ids:
        if frappe.db.exists("ilL-Configured-Fixture", cf_id):
            fixtures[cf_id] = frappe.get_doc("ilL-Configured-Fixture", cf_id)

    if not fixtures:
        return {}

    # Collect all component lists per fixture
    fixture_components: dict[str, list[tuple[str, str, float, str]]] = {}
    all_item_codes: set[str] = set()

    for cf_id, cf in fixtures.items():
        comps: list[tuple[str, str, float, str]] = []

        if cf.profile_item:
            qty = _calculate_profile_quantity(cf)
            if qty > 0:
                comps.append(("Profile", cf.profile_item, qty, "Nos"))
                all_item_codes.add(cf.profile_item)

        if cf.lens_item:
            qty = _calculate_lens_quantity(cf)
            if qty > 0:
                comps.append(("Lens", cf.lens_item, qty, "Nos"))
                all_item_codes.add(cf.lens_item)

        endcap_counts = _calculate_endcap_quantities(cf)
        if endcap_counts.get("feed_through_qty", 0) > 0 and cf.endcap_item_start:
            comps.append(("Endcap (Start)", cf.endcap_item_start, endcap_counts["feed_through_qty"], "Nos"))
            all_item_codes.add(cf.endcap_item_start)
        if endcap_counts.get("solid_qty", 0) > 0 and cf.endcap_item_end:
            comps.append(("Endcap (End)", cf.endcap_item_end, endcap_counts["solid_qty"], "Nos"))
            all_item_codes.add(cf.endcap_item_end)

        if cf.mounting_item:
            qty = _calculate_mounting_quantity(cf)
            if qty > 0:
                comps.append(("Mounting Accessory", cf.mounting_item, qty, "Nos"))
                all_item_codes.add(cf.mounting_item)

        tape_item = _get_tape_item(cf)
        if tape_item:
            total_tape_mm = _calculate_total_tape_length(cf)
            tape_length_ft = total_tape_mm / 304.8
            if tape_length_ft > 0:
                comps.append(("LED Tape", tape_item, round(tape_length_ft, 2), "Foot"))
                all_item_codes.add(tape_item)

        # TODO: re-enable leader cables when ready to include in stock availability
        # if cf.leader_item:
        #     leader_qty = cf.runs_count or 1
        #     comps.append(("Leader Cable", cf.leader_item, leader_qty, "Nos"))
        #     all_item_codes.add(cf.leader_item)

        if cf.drivers:
            for driver in cf.drivers:
                if driver.driver_item and (driver.driver_qty or 0) > 0:
                    comps.append(("Driver", driver.driver_item, driver.driver_qty, "Nos"))
                    all_item_codes.add(driver.driver_item)

        fixture_components[cf_id] = comps

    # Single bulk stock query
    stock_map = _bulk_stock_query(list(all_item_codes))

    # Distribute results
    show_qty = _is_privileged_user()
    results: dict[str, dict[str, Any]] = {}

    for cf_id, comps in fixture_components.items():
        if not comps:
            results[cf_id] = {"all_in_stock": False, "items": []}
            continue

        items_list: list[dict[str, Any]] = []
        all_ok = True
        for comp_type, item_code, qty_req, uom in comps:
            qty_avail = stock_map.get(item_code, 0.0)
            sufficient = qty_avail >= qty_req
            if not sufficient:
                all_ok = False
            entry: dict[str, Any] = {
                "component_type": comp_type,
                "item_code": item_code,
                "is_sufficient": sufficient,
            }
            if show_qty:
                entry["qty_required"] = qty_req
                entry["qty_available"] = qty_avail
            items_list.append(entry)

        results[cf_id] = {"all_in_stock": all_ok, "items": items_list}

    return results
