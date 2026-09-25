# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog API

Endpoints for the dealer-facing product catalog pages. All endpoints are
guarded by ``portal.access.require_catalog_access`` (Dealers and internal
users).
"""

import json
from typing import Optional, Union

import frappe
from frappe import _
from frappe.utils import cint

from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access

# ── helpers ──────────────────────────────────────────────────────────

def _parse_json_param(value):
    """Parse a JSON string parameter into a Python object, or return as-is."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


# ── public API ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_catalog_products(
    filters: Union[str, dict, None] = None,
    search: str = "",
    page: int = 1,
    page_size: int = 12,
    sort: str = "product_name asc",
) -> dict:
    """Paginated product list with multi-attribute filtering.

    Queries ``ilL-Webflow-Product`` (is_active=1) optionally joined with
    ``ilL-Child-Webflow-Attribute-Link`` for attribute-based filtering
    (AND across attribute types, OR within a type).  Text search covers
    ``product_name`` and ``short_description``.

    Args:
        filters: dict of ``{attribute_type: [value, ...]}``
        search: free-text search string
        page: 1-based page number
        page_size: results per page (max 50)
        sort: SQL ORDER BY fragment (whitelist-validated)

    Returns:
        dict with ``success``, ``products``, ``total``, ``page``, ``page_size``
    """
    require_catalog_access()

    # ── sanitise inputs ──────────────────────────────────────────────
    filters = _parse_json_param(filters) or {}
    if not isinstance(filters, dict):
        return {"success": False, "error": _("Filters must be an object")}
    filters = dict(filters)
    if len(filters) > 20 or any(not isinstance(value, (str, list)) or (isinstance(value, list) and (len(value) > 50 or any(not isinstance(part, str) for part in value))) for value in filters.values()):
        return {"success": False, "error": _("Choose up to 20 filters with at most 50 values each")}
    page = max(1, cint(page))
    page_size = min(50, max(1, cint(page_size)))

    allowed_sorts = {
        "product_name asc",
        "product_name desc",
        "modified desc",
        "modified asc",
        "product_type asc",
    }
    if sort not in allowed_sorts:
        sort = "product_name asc"

    # ── build WHERE clause ───────────────────────────────────────────
    conditions = ["`tabilL-Webflow-Product`.is_active = 1"]
    params: dict = {}

    # product_type filter (top-level, not an attribute)
    if filters.get("product_type"):
        pt = filters.pop("product_type")
        if isinstance(pt, list):
            placeholders = ", ".join(f"%(pt_{i})s" for i in range(len(pt)))
            conditions.append(f"`tabilL-Webflow-Product`.product_type IN ({placeholders})")
            for i, v in enumerate(pt):
                params[f"pt_{i}"] = v
        else:
            conditions.append("`tabilL-Webflow-Product`.product_type = %(product_type)s")
            params["product_type"] = pt

    for field in ("series", "product_category"):
        values = filters.pop(field, None)
        if values:
            values = [values] if isinstance(values, str) else values
            placeholders = ", ".join(f"%({field}_{i})s" for i in range(len(values)))
            conditions.append(f"`tabilL-Webflow-Product`.{field} IN ({placeholders})")
            params.update({f"{field}_{i}": value for i, value in enumerate(values)})

    # Search marketing names and ERP model/template identifiers as well as series.
    search = str(search or "").strip()[:200]
    if search:
        conditions.append(
            "(`tabilL-Webflow-Product`.product_name LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.short_description LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.series LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.fixture_template LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.tape_neon_template LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.led_sheet_template LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.driver_spec LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.controller_spec LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.accessory_spec LIKE %(search)s)"
        )
        params["search"] = f"%{search}%"

    # ── attribute filters (AND across types, OR within a type) ───────
    attr_join = ""
    if filters:
        for idx, (attr_type, attr_values) in enumerate(filters.items()):
            if not attr_values:
                continue
            if isinstance(attr_values, str):
                attr_values = [attr_values]

            alias = f"al{idx}"
            attr_join += (
                f" INNER JOIN `tabilL-Child-Webflow-Attribute-Link` `{alias}` "
                f"ON `{alias}`.parent = `tabilL-Webflow-Product`.name "
                f"AND `{alias}`.parenttype = 'ilL-Webflow-Product' "
                f"AND `{alias}`.attribute_type = %(attr_type_{idx})s "
            )
            params[f"attr_type_{idx}"] = attr_type

            placeholders = ", ".join(
                f"%(attr_val_{idx}_{j})s" for j in range(len(attr_values))
            )
            attr_join += f"AND `{alias}`.display_label IN ({placeholders}) "
            for j, val in enumerate(attr_values):
                params[f"attr_val_{idx}_{j}"] = val

    where = " AND ".join(conditions)

    # ── count total ──────────────────────────────────────────────────
    count_sql = (
        f"SELECT COUNT(DISTINCT `tabilL-Webflow-Product`.name) AS cnt "
        f"FROM `tabilL-Webflow-Product` {attr_join} WHERE {where}"
    )
    total = frappe.db.sql(count_sql, params, as_dict=True)[0].cnt

    # ── fetch page ───────────────────────────────────────────────────
    offset = (page - 1) * page_size
    data_sql = (
        f"SELECT DISTINCT "
        f"  `tabilL-Webflow-Product`.name, "
        f"  `tabilL-Webflow-Product`.product_name, "
        f"  `tabilL-Webflow-Product`.product_slug, "
        f"  `tabilL-Webflow-Product`.product_type, "
        f"  `tabilL-Webflow-Product`.series, "
        f"  `tabilL-Webflow-Product`.short_description, "
        f"  `tabilL-Webflow-Product`.featured_image, "
        f"  `tabilL-Webflow-Product`.is_configurable, "
        f"  `tabilL-Webflow-Product`.fixture_template, "
        f"  `tabilL-Webflow-Product`.tape_neon_template, "
        f"  `tabilL-Webflow-Product`.led_sheet_template, "
        f"  `tabilL-Webflow-Product`.is_active "
        f"FROM `tabilL-Webflow-Product` {attr_join} "
        f"WHERE {where} "
        f"ORDER BY `tabilL-Webflow-Product`.{sort}, `tabilL-Webflow-Product`.name asc "
        f"LIMIT %(limit)s OFFSET %(offset)s"
    )
    params["limit"] = page_size
    params["offset"] = offset

    products = frappe.db.sql(data_sql, params, as_dict=True)

    # ── attach pricing from fixture template where available ─────────
    template_codes = [p.fixture_template for p in products if p.fixture_template]
    pricing_map = {}
    if template_codes:
        prices = frappe.get_all(
            "ilL-Fixture-Template",
            filters={"name": ["in", template_codes]},
            fields=["name", "base_price_msrp"],
            ignore_permissions=True,
        )
        pricing_map = {p.name: p.base_price_msrp for p in prices}

    from illumenate_lighting.illumenate_lighting.api.product_projection import project_product
    from illumenate_lighting.illumenate_lighting.portal.rollout import available
    result = [project_product(product, price=pricing_map.get(product.fixture_template), commercial=True, configure_available=available(product.product_type)) for product in products]

    return {
        "success": True,
        "products": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@frappe.whitelist()
def get_catalog_product_detail(product_slug: str) -> dict:
    """Full product detail with all child tables.

    Args:
        product_slug: The URL-friendly slug of the product.

    Returns:
        dict with ``success`` and ``product`` (all fields + child tables).
    """
    require_catalog_access()

    if not product_slug:
        return {"success": False, "error": _("product_slug is required")}

    if not frappe.db.exists("ilL-Webflow-Product", {"product_slug": product_slug}):
        return {"success": False, "error": _("Product not found")}

    product = frappe.get_doc(
        "ilL-Webflow-Product", {"product_slug": product_slug}
    )

    if not product.is_active:
        return {"success": False, "error": _("Product not found")}

    from illumenate_lighting.illumenate_lighting.api.product_projection import project_product

    certifications = []
    for row in sorted(product.certifications or [], key=lambda r: r.display_order or 0):
        master = frappe.get_doc("ilL-Attribute-Certification", row.certification)
        applicable = {r.product_type for r in master.applies_to_types or []}
        if not master.is_active or (applicable and product.product_type not in applicable):
            continue
        certifications.append({key: master.get(key) for key in (
            "certification_name", "certification_body", "certification_code", "badge_image"
        )})
    price = None
    if product.product_type == "Fixture Template" and product.fixture_template:
        price = frappe.db.get_value("ilL-Fixture-Template", product.fixture_template, "base_price_msrp")
    from illumenate_lighting.illumenate_lighting.portal.rollout import available
    from illumenate_lighting.illumenate_lighting.portal.standard_products import choices
    projection = project_product(product, certifications=certifications, price=price, commercial=True, configure_available=available(product.product_type))
    if not projection["configure_url"]:
        projection["standard_choices"] = choices(product)
        if projection["standard_choices"]:
            projection["capability"] = "quantity"
    return {"success": True, "product": projection}


@frappe.whitelist()
def get_catalog_filter_options() -> dict:
    """Distinct attribute facets grouped by attribute_type with product counts.

    Only considers active products.  Returns the data needed to render the
    filter sidebar (attribute type → list of values with counts).

    Returns:
        dict with ``success``, ``filters`` (list of facet groups),
        ``product_types`` (list of {value, count}).
    """
    require_catalog_access()

    # ── product type facets ──────────────────────────────────────────
    type_rows = frappe.db.sql(
        """
        SELECT product_type, COUNT(*) AS cnt
        FROM `tabilL-Webflow-Product`
        WHERE is_active = 1
        GROUP BY product_type
        ORDER BY product_type
        """,
        as_dict=True,
    )
    product_types = [
        {"value": r.product_type, "count": r.cnt} for r in type_rows
    ]

    # ── attribute facets ─────────────────────────────────────────────
    attr_rows = frappe.db.sql(
        """
        SELECT
            al.attribute_type,
            al.display_label,
            COUNT(DISTINCT al.parent) AS cnt
        FROM `tabilL-Child-Webflow-Attribute-Link` al
        INNER JOIN `tabilL-Webflow-Product` p
            ON p.name = al.parent AND al.parenttype = 'ilL-Webflow-Product'
        WHERE p.is_active = 1
        GROUP BY al.attribute_type, al.display_label
        ORDER BY al.attribute_type, al.display_label
        """,
        as_dict=True,
    )

    # Group by attribute_type
    facets: dict = {}
    for row in attr_rows:
        facets.setdefault(row.attribute_type, []).append({
            "value": row.display_label,
            "count": row.cnt,
        })

    filters = [
        {"attribute_type": atype, "options": opts}
        for atype, opts in facets.items()
    ]

    for field in ("series", "product_category"):
        rows = frappe.db.sql(f"SELECT `{field}` AS value, COUNT(*) AS cnt FROM `tabilL-Webflow-Product` WHERE is_active=1 AND `{field}` IS NOT NULL AND `{field}` != '' GROUP BY `{field}` ORDER BY `{field}`", as_dict=True)
        if rows:
            filters.insert(0, {"attribute_type": field, "label": "Series" if field == "series" else "Application", "options": [{"value": row.value, "count": row.cnt} for row in rows]})

    return {
        "success": True,
        "product_types": product_types,
        "filters": filters,
    }
