# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Product Catalog API

Endpoints for the dealer-facing product catalog pages. All endpoints are
guarded by ``portal.access.require_catalog_access`` (Dealers and internal
users).
"""

import json

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


def _per_foot_prices(products) -> dict:
    """Map product name → template MSRP per foot for linear, tape and neon products."""
    from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES
    from illumenate_lighting.illumenate_lighting.api.product_projection import (
        PER_FOOT_TEMPLATES,
        TEMPLATE_FIELDS,
    )

    wanted: dict = {}
    for product in products:
        family = FAMILY_ALIASES.get(product.get("product_type"), product.get("product_type"))
        doctype = PER_FOOT_TEMPLATES.get(family)
        template = product.get(TEMPLATE_FIELDS[family]) if doctype else None
        if template:
            wanted.setdefault(doctype, {})[product.get("name")] = template

    prices = {}
    for doctype, by_product in wanted.items():
        rows = frappe.get_all(
            doctype,
            filters={"name": ["in", list(set(by_product.values()))]},
            fields=["name", "price_per_ft_msrp"],
            ignore_permissions=True,
        )
        rates = {row.name: row.price_per_ft_msrp for row in rows}
        for name, template in by_product.items():
            if rates.get(template) is not None:
                prices[name] = rates[template]
    return prices


def _template_activity(products) -> dict:
    """Return ``(DocType, template) -> active`` using one query per template type."""
    from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES
    from illumenate_lighting.illumenate_lighting.api.product_projection import (
        TEMPLATE_DOCTYPES,
        TEMPLATE_FIELDS,
    )

    wanted = {}
    for product in products:
        family = FAMILY_ALIASES.get(product.get("product_type"), product.get("product_type"))
        template = product.get(TEMPLATE_FIELDS[family]) if family in TEMPLATE_FIELDS else None
        if template:
            wanted.setdefault(TEMPLATE_DOCTYPES[family], set()).add(template)

    activity = {}
    for doctype, names in wanted.items():
        rows = frappe.get_all(
            doctype,
            filters={"name": ["in", list(names)]},
            fields=["name", "is_active"],
            ignore_permissions=True,
        )
        activity.update({(doctype, row.name): bool(cint(row.is_active)) for row in rows})
    return activity


def _is_template_active(product, activity) -> bool:
    """A linked template that is inactive or no longer exists cannot be configured."""
    from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES
    from illumenate_lighting.illumenate_lighting.api.product_projection import (
        TEMPLATE_DOCTYPES,
        TEMPLATE_FIELDS,
    )

    family = FAMILY_ALIASES.get(product.get("product_type"), product.get("product_type"))
    template = product.get(TEMPLATE_FIELDS[family]) if family in TEMPLATE_FIELDS else None
    return activity.get((TEMPLATE_DOCTYPES[family], template), False) if template else True


def _project(product, activity, **kwargs) -> dict:
    """Project with the family rollout gate and template state the caller already resolved."""
    from illumenate_lighting.illumenate_lighting.api.product_projection import project_product
    from illumenate_lighting.illumenate_lighting.portal.rollout import reason

    gate = reason(product.get("product_type"))
    return project_product(
        product,
        commercial=True,
        configure_available=gate == "ok",
        rollout_reason=gate,
        template_active=_is_template_active(product, activity),
        **kwargs,
    )


def _standard_choices(product) -> list:
    """Orderable SKUs for a product without a configurator; a dangling spec link offers none."""
    from illumenate_lighting.illumenate_lighting.portal.standard_products import choices

    try:
        return choices(product)
    except frappe.DoesNotExistError:
        return []


# Filters on product columns; every other filter key is an attribute type.
PRODUCT_FIELD_FILTERS = ("product_type", "series", "product_category")
SEARCH_FIELDS = (
    "product_name",
    "short_description",
    "series",
    "fixture_template",
    "tape_neon_template",
    "led_sheet_template",
    "driver_spec",
    "controller_spec",
    "accessory_spec",
)


def _clean_filters(filters) -> tuple[dict, str | None]:
    """Return ``({key: [value, ...]}, None)``, or ``({}, error)`` for an unusable payload."""
    filters = _parse_json_param(filters) or {}
    if not isinstance(filters, dict):
        return {}, _("Filters must be an object")
    if len(filters) > 20 or any(
        not isinstance(value, (str, list))
        or (isinstance(value, list) and (len(value) > 50 or any(not isinstance(part, str) for part in value)))
        for value in filters.values()
    ):
        return {}, _("Choose up to 20 filters with at most 50 values each")
    return {key: [value] if isinstance(value, str) else value for key, value in filters.items() if value}, None


def _scope(filters: dict, search: str, exclude: str | None = None) -> tuple[str, str, dict]:
    """``(joins, where, params)`` selecting active products that match every filter but ``exclude``.

    Attribute filters AND across attribute types and OR within one type. Search covers
    marketing names and ERP model/template identifiers as well as series.
    """
    conditions = ["`tabilL-Webflow-Product`.is_active = 1"]
    params: dict = {}
    joins = ""
    for idx, (key, values) in enumerate(filters.items()):
        if key == exclude:
            continue
        placeholders = ", ".join(f"%(f{idx}_{j})s" for j in range(len(values)))
        params.update({f"f{idx}_{j}": value for j, value in enumerate(values)})
        if key in PRODUCT_FIELD_FILTERS:
            conditions.append(f"`tabilL-Webflow-Product`.`{key}` IN ({placeholders})")
            continue
        alias = f"al{idx}"
        joins += (
            f" INNER JOIN `tabilL-Child-Webflow-Attribute-Link` `{alias}` "
            f"ON `{alias}`.parent = `tabilL-Webflow-Product`.name "
            f"AND `{alias}`.parenttype = 'ilL-Webflow-Product' "
            f"AND `{alias}`.attribute_type = %(f{idx}_type)s "
            f"AND `{alias}`.display_label IN ({placeholders}) "
        )
        params[f"f{idx}_type"] = key

    search = str(search or "").strip()[:200]
    if search:
        conditions.append(
            "(" + " OR ".join(f"`tabilL-Webflow-Product`.{field} LIKE %(search)s" for field in SEARCH_FIELDS) + ")"
        )
        params["search"] = f"%{search}%"
    return joins, " AND ".join(conditions), params


def _scope_subquery(filters: dict, search: str, exclude: str | None = None) -> tuple[str, dict]:
    joins, where, params = _scope(filters, search, exclude)
    return f"SELECT DISTINCT `tabilL-Webflow-Product`.name FROM `tabilL-Webflow-Product` {joins} WHERE {where}", params


# ── public API ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_catalog_products(
    filters: str | dict | None = None,
    search: str = "",
    page: int | str | None = 1,
    page_size: int | str | None = 12,
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
    filters, error = _clean_filters(filters)
    if error:
        return {"success": False, "error": error}
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

    attr_join, where, params = _scope(filters, search)

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
        # Links read by standard_products.choices() for "Add to schedule" products.
        f"  `tabilL-Webflow-Product`.portal_item, "
        f"  `tabilL-Webflow-Product`.driver_spec, "
        f"  `tabilL-Webflow-Product`.driver_template, "
        f"  `tabilL-Webflow-Product`.controller_spec, "
        f"  `tabilL-Webflow-Product`.controller_template, "
        f"  `tabilL-Webflow-Product`.accessory_spec, "
        f"  `tabilL-Webflow-Product`.profile_spec, "
        f"  `tabilL-Webflow-Product`.lens_spec, "
        f"  `tabilL-Webflow-Product`.is_active "
        f"FROM `tabilL-Webflow-Product` {attr_join} "
        f"WHERE {where} "
        f"ORDER BY `tabilL-Webflow-Product`.{sort}, `tabilL-Webflow-Product`.name asc "
        f"LIMIT %(limit)s OFFSET %(offset)s"
    )
    params["limit"] = page_size
    params["offset"] = offset

    products = frappe.db.sql(data_sql, params, as_dict=True)

    # ── attach MSRP per foot from linear / tape / neon templates ─────
    pricing_map = _per_foot_prices(products)
    template_activity = _template_activity(products)

    result = []
    for product in products:
        projection = _project(product, template_activity, price=pricing_map.get(product.name))
        # Cards offer "Add to schedule" only when the product page will have an orderable SKU.
        if projection["capability"] == "inquiry" and _standard_choices(product):
            projection["capability"] = "quantity"
        result.append(projection)

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

    certifications = []
    for row in sorted(product.certifications or [], key=lambda r: r.display_order or 0):
        master = frappe.get_doc("ilL-Attribute-Certification", row.certification)
        applicable = {r.product_type for r in master.applies_to_types or []}
        if not master.is_active or (applicable and product.product_type not in applicable):
            continue
        certifications.append({key: master.get(key) for key in (
            "certification_name", "certification_body", "certification_code", "badge_image"
        )})
    price = _per_foot_prices([product]).get(product.name)
    projection = _project(
        product, _template_activity([product]), certifications=certifications, price=price
    )
    if not projection["configure_url"]:
        projection["standard_choices"] = _standard_choices(product)
        if projection["standard_choices"]:
            projection["capability"] = "quantity"
    return {"success": True, "product": projection}


@frappe.whitelist()
def get_catalog_filter_options(filters: str | dict | None = None, search: str = "") -> dict:
    """Facet values grouped by attribute_type with product counts.

    With no ``filters`` or ``search`` the counts cover every active product. Otherwise
    each group's counts apply every *other* active filter plus the search (disjunctive
    facets), so a count is the number of results that ticking that value would give.
    Selected values are always returned, with a zero count if nothing matches.

    Returns:
        dict with ``success``, ``filters`` (list of facet groups),
        ``product_types`` (list of {value, count}).
    """
    require_catalog_access()

    filters, error = _clean_filters(filters)
    if error:
        return {"success": False, "error": error}

    def selected(key, counts):
        # Blank labels cannot be ticked; order case-insensitively like the database collation.
        counts = {value: count for value, count in counts.items() if value not in (None, "")}
        for value in filters.get(key, []):
            counts.setdefault(value, 0)
        return [{"value": value, "count": counts[value]} for value in sorted(counts, key=str.casefold)]

    # ── product type facets ──────────────────────────────────────────
    scope, params = _scope_subquery(filters, search, exclude="product_type")
    type_rows = frappe.db.sql(
        f"""
        SELECT p.product_type, COUNT(*) AS cnt
        FROM `tabilL-Webflow-Product` p
        WHERE p.name IN ({scope})
        GROUP BY p.product_type
        """,
        params,
        as_dict=True,
    )
    product_types = selected("product_type", {row.product_type: row.cnt for row in type_rows})

    # ── attribute facets ─────────────────────────────────────────────
    attribute_sql = """
        SELECT al.attribute_type, al.display_label, COUNT(DISTINCT al.parent) AS cnt
        FROM `tabilL-Child-Webflow-Attribute-Link` al
        WHERE al.parenttype = 'ilL-Webflow-Product' AND al.parent IN ({scope}) {only}
        GROUP BY al.attribute_type, al.display_label
    """
    active_types = [key for key in filters if key not in PRODUCT_FIELD_FILTERS]
    attr_rows = []
    for attr_type in active_types:
        scope, params = _scope_subquery(filters, search, exclude=attr_type)
        attr_rows += frappe.db.sql(
            attribute_sql.format(scope=scope, only="AND al.attribute_type = %(facet_type)s"),
            {**params, "facet_type": attr_type},
            as_dict=True,
        )
    scope, params = _scope_subquery(filters, search)
    only = ""
    if active_types:
        only = "AND al.attribute_type NOT IN ({})".format(
            ", ".join(f"%(facet_type_{i})s" for i in range(len(active_types)))
        )
        params = {**params, **{f"facet_type_{i}": value for i, value in enumerate(active_types)}}
    attr_rows += frappe.db.sql(attribute_sql.format(scope=scope, only=only), params, as_dict=True)

    facets: dict = {attr_type: {} for attr_type in active_types}
    for row in attr_rows:
        if row.attribute_type:
            facets.setdefault(row.attribute_type, {})[row.display_label] = row.cnt
    filters_out = [
        {"attribute_type": attr_type, "options": selected(attr_type, facets[attr_type])}
        for attr_type in sorted(facets, key=str.casefold)
    ]

    for field in ("series", "product_category"):
        scope, params = _scope_subquery(filters, search, exclude=field)
        rows = frappe.db.sql(
            f"""
            SELECT p.`{field}` AS value, COUNT(*) AS cnt
            FROM `tabilL-Webflow-Product` p
            WHERE p.name IN ({scope}) AND p.`{field}` IS NOT NULL AND p.`{field}` != ''
            GROUP BY p.`{field}`
            """,
            params,
            as_dict=True,
        )
        options = selected(field, {row.value: row.cnt for row in rows})
        if options:
            filters_out.insert(0, {"attribute_type": field, "label": "Series" if field == "series" else "Application", "options": options})

    return {
        "success": True,
        "product_types": product_types,
        "filters": filters_out,
    }
