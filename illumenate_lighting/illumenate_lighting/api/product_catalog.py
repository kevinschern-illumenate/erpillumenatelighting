# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog API

Internal-only endpoints for the System Manager product catalog pages.
All endpoints are guarded by ``frappe.only_for("System Manager")``.
"""

import json
from typing import Optional, Union

import frappe
from frappe import _
from frappe.utils import cint


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
    frappe.only_for("System Manager")

    # ── sanitise inputs ──────────────────────────────────────────────
    filters = _parse_json_param(filters) or {}
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

    # text search
    search = (search or "").strip()
    if search:
        conditions.append(
            "(`tabilL-Webflow-Product`.product_name LIKE %(search)s "
            "OR `tabilL-Webflow-Product`.short_description LIKE %(search)s)"
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
        f"  `tabilL-Webflow-Product`.fixture_template "
        f"FROM `tabilL-Webflow-Product` {attr_join} "
        f"WHERE {where} "
        f"ORDER BY `tabilL-Webflow-Product`.{sort} "
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

    result = []
    for p in products:
        result.append({
            "name": p.name,
            "product_name": p.product_name,
            "product_slug": p.product_slug,
            "product_type": p.product_type,
            "series": p.series,
            "short_description": p.short_description,
            "featured_image": p.featured_image,
            "is_configurable": bool(p.is_configurable),
            "base_price_msrp": pricing_map.get(p.fixture_template),
        })

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
    frappe.only_for("System Manager")

    if not product_slug:
        return {"success": False, "error": _("product_slug is required")}

    if not frappe.db.exists("ilL-Webflow-Product", {"product_slug": product_slug}):
        return {"success": False, "error": _("Product not found")}

    product = frappe.get_doc(
        "ilL-Webflow-Product", {"product_slug": product_slug}
    )

    # Gallery images
    gallery = []
    for img in product.gallery_images or []:
        gallery.append({
            "image": img.image,
            "alt_text": img.alt_text or "",
            "display_order": img.display_order if hasattr(img, "display_order") else img.idx,
        })
    if not gallery and product.featured_image:
        gallery = [{"image": product.featured_image, "alt_text": product.product_name or ""}]

    # Specifications
    specs = []
    for s in product.specifications or []:
        specs.append({
            "spec_label": s.spec_label if hasattr(s, "spec_label") else getattr(s, "label", ""),
            "spec_value": s.spec_value if hasattr(s, "spec_value") else getattr(s, "value", ""),
        })

    # Certifications
    certs = []
    for c in product.certifications or []:
        certs.append({
            "certification_name": getattr(c, "certification_name", ""),
            "certification_body": getattr(c, "certification_body", ""),
            "file_url": getattr(c, "file_url", ""),
        })

    # Documents
    docs = []
    for d in product.documents or []:
        docs.append({
            "document_name": getattr(d, "document_name", ""),
            "document_type": getattr(d, "document_type", ""),
            "file_url": getattr(d, "file_url", ""),
        })

    # Attribute links
    attributes = []
    for a in product.attribute_links or []:
        attributes.append({
            "attribute_type": a.attribute_type,
            "attribute_name": a.attribute_name,
            "display_label": a.display_label or "",
        })

    # Configurator options
    config_options = []
    for o in product.configurator_options or []:
        config_options.append({
            "option_type": getattr(o, "option_type", ""),
            "option_value": getattr(o, "option_value", ""),
            "display_label": getattr(o, "display_label", ""),
        })

    # Compatible products
    compatible = []
    for cp in product.compatible_products or []:
        compatible.append({
            "linked_product": getattr(cp, "linked_product", ""),
            "relationship_type": getattr(cp, "relationship_type", ""),
        })

    # Pricing from fixture template
    base_price_msrp = None
    if product.fixture_template:
        base_price_msrp = frappe.db.get_value(
            "ilL-Fixture-Template", product.fixture_template, "base_price_msrp"
        )

    return {
        "success": True,
        "product": {
            "name": product.name,
            "product_name": product.product_name,
            "product_slug": product.product_slug,
            "product_type": product.product_type,
            "product_category": product.product_category,
            "series": product.series,
            "is_active": product.is_active,
            "is_configurable": bool(product.is_configurable),
            "fixture_template": product.fixture_template,
            "short_description": product.short_description,
            "long_description": product.long_description,
            "featured_image": product.featured_image,
            "configurator_intro_text": product.configurator_intro_text,
            "min_length_mm": product.min_length_mm,
            "max_length_mm": product.max_length_mm,
            "length_increment_mm": product.length_increment_mm,
            "base_price_msrp": base_price_msrp,
            "gallery": gallery,
            "specifications": specs,
            "certifications": certs,
            "documents": docs,
            "attribute_links": attributes,
            "configurator_options": config_options,
            "compatible_products": compatible,
        },
    }


@frappe.whitelist()
def get_catalog_filter_options() -> dict:
    """Distinct attribute facets grouped by attribute_type with product counts.

    Only considers active products.  Returns the data needed to render the
    filter sidebar (attribute type → list of values with counts).

    Returns:
        dict with ``success``, ``filters`` (list of facet groups),
        ``product_types`` (list of {value, count}).
    """
    frappe.only_for("System Manager")

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

    return {
        "success": True,
        "product_types": product_types,
        "filters": filters,
    }
