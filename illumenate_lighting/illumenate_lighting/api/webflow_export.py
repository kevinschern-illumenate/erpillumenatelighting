# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Export API

This module provides API endpoints for exporting product data to Webflow CMS
via n8n automation workflows.

Endpoints:
- get_webflow_products: Retrieve products for export to Webflow
- mark_webflow_synced: Mark a product as synced after successful Webflow push
- get_webflow_categories: Retrieve categories for Webflow navigation
- trigger_sync: Manually trigger a sync for specific products
"""

import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.webflow_attributes import (
    ATTRIBUTE_DOCTYPES,
    build_product_filter_field_data,
    ATTRIBUTE_FILTER_FIELD_SLUGS,
)
from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
    format_length_inches,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_spec_profile.ill_spec_profile import (
    compute_profile_dimensions,
)

# Base URL for converting relative file paths to absolute URLs
ERPNEXT_BASE_URL = "https://illumenatelighting.v.frappe.cloud"


def _make_absolute_url(url: str) -> str:
    """Convert relative URL to absolute URL for Webflow.
    
    Args:
        url: The URL to convert (e.g., '/files/image.jpg')
    
    Returns:
        Absolute URL (e.g., 'https://illumenatelighting.v.frappe.cloud/files/image.jpg')
    """
    if not url:
        return url
    
    # Already absolute
    if url.startswith('http://') or url.startswith('https://'):
        return url
    
    # Relative URL - prepend base URL
    if url.startswith('/'):
        return f"{ERPNEXT_BASE_URL}{url}"
    else:
        return f"{ERPNEXT_BASE_URL}/{url}"


@frappe.whitelist(allow_guest=False)
def get_webflow_products(
    product_type: str = None,
    sync_status: str = None,
    limit: int = 100,
    offset: int = 0,
    include_child_tables: bool = True
) -> dict:
    """
    Get Webflow products for n8n export.
    
    Args:
        product_type: Filter by product type (e.g., "Fixture Template", "Driver")
        sync_status: Filter by sync status ("Pending", "Never Synced", "Error")
        limit: Maximum records to return (default: 100)
        offset: Pagination offset (default: 0)
        include_child_tables: Whether to include expanded child table data (default: True)
    
    Returns:
        dict: {
            "products": [...],
            "total": int,
            "limit": int,
            "offset": int
        }
    
    Example:
        >>> get_webflow_products(product_type="Fixture Template", sync_status="Pending")
    """
    filters = {"is_active": 1}
    
    if product_type:
        filters["product_type"] = product_type
    
    if sync_status:
        if sync_status == "needs_sync":
            # Special filter for products that need syncing
            filters["sync_status"] = ["in", ["Pending", "Never Synced"]]
        else:
            filters["sync_status"] = sync_status
    
    # Get product list with basic fields
    products = frappe.get_all(
        "ilL-Webflow-Product",
        filters=filters,
        fields=[
            "name", "product_name", "product_slug", "product_type",
            "product_category", "series", "is_active", "is_configurable",
            "fixture_template", "driver_spec", "controller_spec",
            "profile_spec", "lens_spec", "tape_spec", "accessory_spec",
            "short_description", "sublabel", "long_description", "features", "featured_image", "dimensions_image", "series_family_image",
            "configurator_intro_text", "min_length_mm", "max_length_mm",
            "length_increment_mm", "auto_calculate_specs",
            "webflow_item_id", "webflow_collection_slug",
            "last_synced_at", "sync_status", "sync_error_message",
            "creation", "modified"
        ],
        limit=limit,
        start=offset,
        order_by="modified desc"
    )
    
    if include_child_tables:
        # Build reverse mapping: attribute doctype -> code_field (once, outside loop)
        _doctype_to_code_field = {}
        for _cfg in ATTRIBUTE_DOCTYPES.values():
            _doctype_to_code_field[_cfg["doctype"]] = _cfg.get("code_field") or None

        # Expand child tables for each product
        for product in products:
            doc = frappe.get_doc("ilL-Webflow-Product", product["name"])
            
            # Convert featured_image to absolute URL
            if product.get("featured_image"):
                product["featured_image"] = _make_absolute_url(product["featured_image"])
            
            # Convert dimensions_image to absolute URL
            if product.get("dimensions_image"):
                product["dimensions_image"] = _make_absolute_url(product["dimensions_image"])
            
            # Convert series_family_image to absolute URL
            if product.get("series_family_image"):
                product["series_family_image"] = _make_absolute_url(product["series_family_image"])
            
            # Export specifications (supports both auto-calculated and manually-added specs)
            product["specifications"] = []
            for s in doc.specifications:
                spec_data = {
                    "spec_group": s.spec_group,
                    "spec_label": s.spec_label,
                    "spec_value": s.spec_value,
                    "spec_unit": s.spec_unit,
                    "is_calculated": s.is_calculated,
                    "display_order": s.display_order,
                    "show_on_card": s.show_on_card,
                    "attribute_doctype": s.attribute_doctype,
                    "attribute_options_json": s.attribute_options_json,
                }
                # Parse attribute_options_json into a list for convenience
                if s.attribute_options_json:
                    try:
                        spec_data["attribute_options"] = json.loads(s.attribute_options_json)
                    except (json.JSONDecodeError, TypeError):
                        spec_data["attribute_options"] = []
                else:
                    spec_data["attribute_options"] = []
                product["specifications"].append(spec_data)
            
            # Enrich specifications with data from linked doctypes
            _enrich_specifications_from_linked_doctypes(product, doc)
            
            product["certifications"] = [
                {
                    "certification": c.certification,
                    "display_order": c.display_order,
                    "certification_details": _get_certification_details(c.certification)
                }
                for c in doc.certifications
            ]
            
            product["configurator_options"] = [
                {
                    "option_step": o.option_step,
                    "option_type": o.option_type,
                    "option_label": o.option_label,
                    "option_description": o.option_description,
                    "is_required": o.is_required,
                    "depends_on_step": o.depends_on_step,
                    "allowed_values_json": o.allowed_values_json
                }
                for o in doc.configurator_options
            ]
            
            product["kit_components"] = [
                {
                    "component_type": k.component_type,
                    "component_item": k.component_item,
                    "component_spec_doctype": k.component_spec_doctype,
                    "component_spec_name": k.component_spec_name,
                    "quantity": k.quantity,
                    "notes": k.notes
                }
                for k in doc.kit_components
            ]
            
            product["gallery_images"] = [
                {
                    "image": _make_absolute_url(g.image),
                    "alt_text": g.alt_text,
                    "caption": g.caption,
                    "display_order": g.display_order
                }
                for g in doc.gallery_images
            ]
            
            product["documents"] = [
                {
                    "document_file": _make_absolute_url(d.document_file),
                    "document_type": d.document_type,
                    "document_title": d.document_title,
                    "display_order": d.display_order
                }
                for d in doc.documents
            ]
            
            product["compatible_products"] = [
                {
                    "related_product": cp.related_product,
                    "relationship_type": cp.relationship_type,
                    "notes": cp.notes
                }
                for cp in doc.compatible_products
            ]
            
            # Add attribute links for Webflow filter fields
            product["attribute_links"] = [
                {
                    "attribute_type": al.attribute_type,
                    "attribute_doctype": al.attribute_doctype,
                    "attribute_name": al.attribute_name,
                    "display_label": al.display_label,
                    "webflow_item_id": al.webflow_item_id,
                    "display_order": al.display_order
                }
                for al in getattr(doc, 'attribute_links', [])
            ]
            
            # Group attribute links by type for easier Webflow mapping
            product["attribute_links_by_type"] = {}
            for al in getattr(doc, 'attribute_links', []):
                attr_type = al.attribute_type
                if attr_type not in product["attribute_links_by_type"]:
                    product["attribute_links_by_type"][attr_type] = []

                # Look up the attribute code from the linked doctype
                attribute_code = ""
                if al.attribute_doctype and al.attribute_name:
                    code_field = _doctype_to_code_field.get(al.attribute_doctype)
                    if code_field:
                        try:
                            attribute_code = frappe.db.get_value(
                                al.attribute_doctype, al.attribute_name, code_field
                            ) or ""
                        except Exception:
                            attribute_code = ""

                product["attribute_links_by_type"][attr_type].append({
                    "attribute_name": al.attribute_name,
                    "display_label": al.display_label,
                    "attribute_code": attribute_code,
                    "webflow_item_id": al.webflow_item_id
                })
            
            # "name, code | name, code" plain text for each attribute type (for Webflow plain text fields)
            product["attribute_text_by_type"] = {}
            for attr_type, attrs in product["attribute_links_by_type"].items():
                pairs = []
                for a in attrs:
                    label = a.get("display_label") or a.get("attribute_name") or ""
                    code = a.get("attribute_code") or ""
                    if label:
                        pairs.append(f"{label}, {code}" if code else label)
                product["attribute_text_by_type"][attr_type] = " | ".join(pairs)
            
            # Filter fields: plain-text comma-separated attribute names
            # These enable Webflow CMS filtering by attribute type
            product["filter_field_data"] = build_product_filter_field_data(
                product["attribute_links_by_type"]
            )
            
            # Add category details if available (includes webflow_item_id for reference field)
            if product.get("product_category"):
                product["category_details"] = _get_category_details(product["product_category"])
                product["category_webflow_item_id"] = _get_category_webflow_item_id(product["product_category"])
            
            # Add full series details if series is set
            if product.get("series"):
                series_details = _get_series_details(product["series"])
                product["series_webflow_item_id"] = series_details.get("webflow_item_id")
                product["series_code"] = series_details.get("series_code")
                product["series_display_name"] = series_details.get("display_name")
    
            # Add features JSON (if present, parse and re-stringify to ensure valid JSON)
            if product.get("features"):
                try:
                    features_data = json.loads(product["features"]) if isinstance(product["features"], str) else product["features"]
                    product["features_json"] = json.dumps(features_data)
                except (json.JSONDecodeError, TypeError):
                    product["features_json"] = "[]"
            else:
                product["features_json"] = "[]"

    total = frappe.db.count("ilL-Webflow-Product", filters)
    
    return {
        "products": products,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@frappe.whitelist(allow_guest=False)
def mark_webflow_synced(
    product_slug: str,
    webflow_item_id: str,
    webflow_collection_slug: str
) -> dict:
    """
    Mark a product as synced after n8n pushes to Webflow.
    
    Called by n8n after successful Webflow API call.
    
    Args:
        product_slug: The product slug (document name)
        webflow_item_id: The Webflow CMS item ID
        webflow_collection_slug: The Webflow collection slug
    
    Returns:
        dict: {"success": True, "synced_at": datetime}
    
    Raises:
        frappe.DoesNotExistError: If product_slug doesn't exist
    """
    if not frappe.db.exists("ilL-Webflow-Product", product_slug):
        frappe.throw(_("Product with slug '{0}' not found").format(product_slug))
    
    # Use set_value to update fields directly without triggering before_save,
    # which runs heavy populate_attribute_links / populate_configurator_options
    # logic that can fail if linked records have issues.
    synced_at = frappe.utils.now()
    frappe.db.set_value("ilL-Webflow-Product", product_slug, {
        "webflow_item_id": webflow_item_id,
        "webflow_collection_slug": webflow_collection_slug,
        "last_synced_at": synced_at,
        "sync_status": "Synced",
        "sync_error_message": None,
    }, update_modified=True)
    frappe.db.commit()
    
    return {
        "success": True,
        "synced_at": synced_at,
        "product_slug": product_slug
    }


@frappe.whitelist(allow_guest=False)
def mark_webflow_error(
    product_slug: str,
    error_message: str
) -> dict:
    """
    Mark a product as having a sync error.
    
    Called by n8n when Webflow API call fails.
    
    Args:
        product_slug: The product slug (document name)
        error_message: The error message from Webflow
    
    Returns:
        dict: {"success": True}
    """
    if not frappe.db.exists("ilL-Webflow-Product", product_slug):
        frappe.throw(_("Product with slug '{0}' not found").format(product_slug))
    
    # Use set_value to avoid triggering before_save hooks
    frappe.db.set_value("ilL-Webflow-Product", product_slug, {
        "sync_status": "Error",
        "sync_error_message": (error_message[:500] if error_message else "Unknown error"),
    }, update_modified=True)
    frappe.db.commit()
    
    return {
        "success": True,
        "product_slug": product_slug
    }


@frappe.whitelist(allow_guest=False)
def get_webflow_categories(
    include_inactive: bool = False,
    sync_status: str = None
) -> dict:
    """
    Get Webflow categories for navigation and filtering.
    
    Args:
        include_inactive: Whether to include inactive categories
        sync_status: Filter by sync status ("Pending", "Never Synced", "needs_sync")
    
    Returns:
        dict: {"categories": [...], "total": int}
    """
    filters = {}
    if not include_inactive:
        filters["is_active"] = 1
    
    if sync_status:
        if sync_status == "needs_sync":
            filters["sync_status"] = ["in", ["Pending", "Never Synced"]]
        else:
            filters["sync_status"] = sync_status
    
    categories = frappe.get_all(
        "ilL-Webflow-Category",
        filters=filters,
        fields=[
            "name", "category_name", "category_slug",
            "parent_category", "display_order", "description",
            "category_image", "is_active",
            "webflow_item_id", "last_synced_at", "sync_status"
        ],
        order_by="display_order asc"
    )
    
    # Build hierarchical structure
    category_map = {c["name"]: c for c in categories}
    for cat in categories:
        cat["children"] = []
        cat["product_count"] = frappe.db.count(
            "ilL-Webflow-Product",
            {"product_category": cat["name"], "is_active": 1}
        )
    
    # Assign children to parents
    for cat in categories:
        if cat.get("parent_category") and cat["parent_category"] in category_map:
            category_map[cat["parent_category"]]["children"].append(cat)
    
    # Filter to only top-level categories for root response
    root_categories = [c for c in categories if not c.get("parent_category")]
    
    return {
        "categories": root_categories,
        "all_categories": categories,
        "total": len(categories)
    }


@frappe.whitelist(allow_guest=False)
def mark_category_synced(
    category_slug: str,
    webflow_item_id: str
) -> dict:
    """
    Mark a category as synced after n8n pushes to Webflow.
    
    Called by n8n after successful Webflow API call.
    
    Args:
        category_slug: The category slug (document name)
        webflow_item_id: The Webflow CMS item ID
    
    Returns:
        dict: {"success": True, "synced_at": datetime}
    """
    if not frappe.db.exists("ilL-Webflow-Category", category_slug):
        frappe.throw(_("Category with slug '{0}' not found").format(category_slug))
    
    doc = frappe.get_doc("ilL-Webflow-Category", category_slug)
    doc.webflow_item_id = webflow_item_id
    doc.last_synced_at = frappe.utils.now()
    doc.sync_status = "Synced"
    doc.save(ignore_permissions=True)
    
    return {
        "success": True,
        "synced_at": doc.last_synced_at,
        "category_slug": category_slug
    }


@frappe.whitelist(allow_guest=False)
def mark_category_error(
    category_slug: str,
    error_message: str
) -> dict:
    """
    Mark a category as having a sync error.
    
    Called by n8n when Webflow API call fails.
    
    Args:
        category_slug: The category slug (document name)
        error_message: The error message from Webflow
    
    Returns:
        dict: {"success": True}
    """
    if not frappe.db.exists("ilL-Webflow-Category", category_slug):
        frappe.throw(_("Category with slug '{0}' not found").format(category_slug))
    
    doc = frappe.get_doc("ilL-Webflow-Category", category_slug)
    doc.sync_status = "Error"
    doc.save(ignore_permissions=True)
    
    frappe.log_error(
        message=error_message[:1000] if error_message else "Unknown error",
        title=f"Webflow Category Sync Error: {category_slug}"
    )
    
    return {
        "success": True,
        "category_slug": category_slug
    }


@frappe.whitelist(allow_guest=False)
def trigger_sync(
    product_slugs: list = None,
    product_type: str = None,
    category_slugs: list = None,
    sync_all_categories: bool = False
) -> dict:
    """
    Mark products and/or categories as pending sync to trigger n8n workflow.
    
    Args:
        product_slugs: List of specific product slugs to sync
        product_type: Sync all products of this type
        category_slugs: List of specific category slugs to sync
        sync_all_categories: Sync all active categories
    
    Returns:
        dict: {"success": True, "products_marked": int, "categories_marked": int}
    """
    products_marked = 0
    categories_marked = 0
    
    # Handle products
    if product_slugs:
        for slug in product_slugs:
            if frappe.db.exists("ilL-Webflow-Product", slug):
                frappe.db.set_value(
                    "ilL-Webflow-Product", slug,
                    "sync_status", "Pending"
                )
                products_marked += 1
    
    elif product_type:
        products = frappe.get_all(
            "ilL-Webflow-Product",
            filters={"product_type": product_type, "is_active": 1},
            pluck="name"
        )
        for slug in products:
            frappe.db.set_value(
                "ilL-Webflow-Product", slug,
                "sync_status", "Pending"
            )
            products_marked += 1
    
    # Handle categories
    if category_slugs:
        for slug in category_slugs:
            if frappe.db.exists("ilL-Webflow-Category", slug):
                frappe.db.set_value(
                    "ilL-Webflow-Category", slug,
                    "sync_status", "Pending"
                )
                categories_marked += 1
    
    elif sync_all_categories:
        categories = frappe.get_all(
            "ilL-Webflow-Category",
            filters={"is_active": 1},
            pluck="name"
        )
        for slug in categories:
            frappe.db.set_value(
                "ilL-Webflow-Category", slug,
                "sync_status", "Pending"
            )
            categories_marked += 1
    
    frappe.db.commit()
    
    return {
        "success": True,
        "products_marked": products_marked,
        "categories_marked": categories_marked
    }


@frappe.whitelist(allow_guest=False)
def get_sync_statistics() -> dict:
    """
    Get statistics about Webflow sync status for products and categories.
    
    Returns:
        dict: Counts by sync status, product type, and category stats
    """
    stats = {
        "products": {
            "by_status": {},
            "by_type": {},
            "total_active": 0,
            "needs_sync": 0
        },
        "categories": {
            "by_status": {},
            "total_active": 0,
            "needs_sync": 0
        }
    }
    
    # Product stats - Count by sync status
    for status in ["Pending", "Synced", "Error", "Never Synced"]:
        count = frappe.db.count(
            "ilL-Webflow-Product",
            {"sync_status": status, "is_active": 1}
        )
        stats["products"]["by_status"][status] = count
        if status in ["Pending", "Never Synced"]:
            stats["products"]["needs_sync"] += count
    
    # Product stats - Count by product type
    for ptype in ["Fixture Template", "Driver", "Controller", "Extrusion Kit", "LED Tape", "Component", "Accessory"]:
        count = frappe.db.count(
            "ilL-Webflow-Product",
            {"product_type": ptype, "is_active": 1}
        )
        if count > 0:
            stats["products"]["by_type"][ptype] = count
    
    stats["products"]["total_active"] = frappe.db.count(
        "ilL-Webflow-Product",
        {"is_active": 1}
    )
    
    # Category stats - Count by sync status
    for status in ["Pending", "Synced", "Error", "Never Synced"]:
        count = frappe.db.count(
            "ilL-Webflow-Category",
            {"sync_status": status, "is_active": 1}
        )
        stats["categories"]["by_status"][status] = count
        if status in ["Pending", "Never Synced"]:
            stats["categories"]["needs_sync"] += count
    
    stats["categories"]["total_active"] = frappe.db.count(
        "ilL-Webflow-Category",
        {"is_active": 1}
    )
    
    return stats


def _get_certification_details(certification_name: str) -> dict:
    """Helper to get certification details for export."""
    if not certification_name:
        return {}
    
    cert = frappe.db.get_value(
        "ilL-Attribute-Certification",
        certification_name,
        ["certification_code", "certification_body", "description", "badge_image"],
        as_dict=True
    )
    return cert or {}


def _get_category_details(category_name: str) -> dict:
    """Helper to get category details for export."""
    if not category_name:
        return {}
    
    cat = frappe.db.get_value(
        "ilL-Webflow-Category",
        category_name,
        ["category_name", "category_slug", "description", "category_image", "webflow_item_id"],
        as_dict=True
    )
    return cat or {}


def _get_category_webflow_item_id(category_name: str) -> str:
    """Helper to get the Webflow item ID for a category."""
    if not category_name:
        return None
    
    webflow_item_id = frappe.db.get_value(
        "ilL-Webflow-Category",
        category_name,
        "webflow_item_id"
    )
    return webflow_item_id


def _get_series_details(series_name: str) -> dict:
    """Helper to get full series details for export."""
    if not series_name:
        return {}
    
    # Get series record with all relevant fields
    series = frappe.db.get_value(
        "ilL-Attribute-Series",
        series_name,
        ["series_name", "code", "short_description", "webflow_item_id"],
        as_dict=True
    )
    if series:
        return {
            "series_code": series.get("code"),
            "display_name": series.get("series_name"),
            "short_description": series.get("short_description"),
            "webflow_item_id": series.get("webflow_item_id")
        }
    return {}


def _get_series_webflow_item_id(series_name: str) -> str:
    """Helper to get the Webflow item ID for a series attribute."""
    if not series_name:
        return None
    
    # Get the webflow_item_id from webflow_attributes API
    # Series attributes are stored in ilL-Attribute-Series doctype
    from illumenate_lighting.illumenate_lighting.api.webflow_attributes import get_attribute_webflow_item_id
    
    try:
        return get_attribute_webflow_item_id("series", series_name)
    except Exception:
        return None


# ============================================================
# Specification Enrichment from Linked Doctypes
# ============================================================


def _enrich_specifications_from_linked_doctypes(product: dict, doc) -> None:
    """Enrich the product specifications list with data from linked doctypes.

    Adds missing spec entries for: Color Rendering (CRI), Input Voltage,
    Dimensions, Dimming, Production Interval, and Certifications & Ratings.
    """
    existing_labels = {s["spec_label"] for s in product["specifications"]}
    additional_specs = []

    product_type = product.get("product_type")

    if product_type == "Fixture Template" and product.get("fixture_template"):
        additional_specs.extend(
            _enrich_fixture_template_specs(product, existing_labels)
        )
    elif product_type == "Driver" and product.get("driver_spec"):
        additional_specs.extend(
            _enrich_driver_specs(product, existing_labels)
        )
    elif product_type == "Controller" and product.get("controller_spec"):
        additional_specs.extend(
            _enrich_controller_specs(product, existing_labels)
        )
    elif product_type == "LED Tape" and product.get("tape_spec"):
        additional_specs.extend(
            _enrich_tape_specs(product, existing_labels)
        )
    elif product_type in ("Component", "Extrusion Kit") and product.get("profile_spec"):
        additional_specs.extend(
            _enrich_profile_specs(product, existing_labels)
        )

    # Certifications & Ratings (icons) — applies to all product types
    if "Certifications & Ratings" not in existing_labels:
        cert_spec = _build_certifications_spec(doc)
        if cert_spec:
            additional_specs.append(cert_spec)

    product["specifications"].extend(additional_specs)


def _enrich_fixture_template_specs(product: dict, existing_labels: set) -> list:
    """Add missing specs for Fixture Template products from linked doctypes."""
    specs = []
    template = frappe.get_doc("ilL-Fixture-Template", product["fixture_template"])

    # ── Color Rendering (CRI) ──────────────────────────────────
    if "Color Rendering" not in existing_labels:
        cri_options = []
        seen_cri = set()
        for tape_row in template.allowed_tape_offerings or []:
            offering_name = getattr(tape_row, "tape_offering", None)
            if not offering_name:
                continue
            cri_name = frappe.db.get_value(
                "ilL-Rel-Tape Offering", offering_name, "cri"
            )
            if cri_name and cri_name not in seen_cri:
                seen_cri.add(cri_name)
                cri_data = frappe.db.get_value(
                    "ilL-Attribute-CRI", cri_name,
                    ["cri_name", "minimum_ra", "code"],
                    as_dict=True,
                )
                if cri_data:
                    cri_options.append({
                        "attribute_type": "CRI",
                        "attribute_doctype": "ilL-Attribute-CRI",
                        "attribute_value": cri_name,
                        "display_label": cri_data.get("cri_name") or cri_name,
                        "code": cri_data.get("code") or "",
                        "minimum_ra": cri_data.get("minimum_ra") or 0,
                    })
        if cri_options:
            display_values = sorted(
                set(str(o["minimum_ra"]) for o in cri_options if o["minimum_ra"]),
            )
            specs.append({
                "spec_group": "Optical",
                "spec_label": "Color Rendering",
                "spec_value": ", ".join(display_values) if display_values else ", ".join(o["display_label"] for o in cri_options),
                "spec_unit": "CRI",
                "is_calculated": 1,
                "display_order": 85,
                "show_on_card": 0,
                "attribute_doctype": "ilL-Attribute-CRI",
                "attribute_options_json": frappe.as_json(cri_options),
                "attribute_options": cri_options,
            })

    # ── Input Voltage ──────────────────────────────────────────
    if "Input Voltage" not in existing_labels:
        voltages = set()
        voltage_options = []
        for tape_row in template.allowed_tape_offerings or []:
            offering_name = getattr(tape_row, "tape_offering", None)
            if not offering_name:
                continue
            tape_spec_name = frappe.db.get_value(
                "ilL-Rel-Tape Offering", offering_name, "tape_spec"
            )
            if not tape_spec_name:
                continue
            input_voltage = frappe.db.get_value(
                "ilL-Spec-LED Tape", tape_spec_name, "input_voltage"
            )
            if input_voltage and input_voltage not in voltages:
                voltages.add(input_voltage)
                voltage_val = frappe.db.get_value(
                    "ilL-Attribute-Output Voltage", input_voltage, "dc_voltage"
                )
                if voltage_val:
                    voltage_options.append({
                        "attribute_type": "Output Voltage",
                        "attribute_doctype": "ilL-Attribute-Output Voltage",
                        "attribute_value": input_voltage,
                        "display_label": f"{voltage_val} VDC",
                    })
        if voltage_options:
            specs.append({
                "spec_group": "Electrical",
                "spec_label": "Input Voltage",
                "spec_value": ", ".join(o["display_label"] for o in voltage_options),
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 90,
                "show_on_card": 0,
                "attribute_doctype": "ilL-Attribute-Output Voltage",
                "attribute_options_json": frappe.as_json(voltage_options),
                "attribute_options": voltage_options,
            })

    # ── Dimensions (from default profile spec) ─────────────────
    if "Dimensions" not in existing_labels:
        profile_spec_name = getattr(template, "default_profile_spec", None)
        if profile_spec_name:
            dimensions = frappe.db.get_value(
                "ilL-Spec-Profile", profile_spec_name, "dimensions"
            )
            if not dimensions:
                # Profile may not have been re-saved since dimensions field was added;
                # compute it on the fly from width_mm / height_mm.
                raw = frappe.db.get_value(
                    "ilL-Spec-Profile", profile_spec_name, ["width_mm", "height_mm"]
                )
                if raw:
                    width_mm, height_mm = raw
                    dimensions = compute_profile_dimensions(width_mm, height_mm)
            if dimensions:
                specs.append({
                    "spec_group": "Physical",
                    "spec_label": "Dimensions",
                    "spec_value": dimensions,
                    "spec_unit": "",
                    "is_calculated": 1,
                    "display_order": 95,
                    "show_on_card": 0,
                    "attribute_doctype": "",
                    "attribute_options_json": None,
                    "attribute_options": [],
                })

    # ── Dimming ────────────────────────────────────────────────
    if "Dimming" not in existing_labels:
        protocol_options = []
        seen_protocols = set()
        eligible_drivers = frappe.get_all(
            "ilL-Rel-Driver-Eligibility",
            filters={"fixture_template": product["fixture_template"], "is_active": 1},
            fields=["driver_spec"],
        )
        for elig in eligible_drivers:
            try:
                driver_doc = frappe.get_doc("ilL-Spec-Driver", elig.driver_spec)
            except frappe.DoesNotExistError:
                continue
            for ip in getattr(driver_doc, "input_protocols", []):
                protocol_name = getattr(ip, "protocol", None)
                if not protocol_name or protocol_name in seen_protocols:
                    continue
                seen_protocols.add(protocol_name)
                proto_data = frappe.db.get_value(
                    "ilL-Attribute-Dimming Protocol", protocol_name,
                    ["label", "code"],
                    as_dict=True,
                )
                if proto_data:
                    protocol_options.append({
                        "attribute_type": "Dimming Protocol",
                        "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                        "attribute_value": protocol_name,
                        "display_label": proto_data.get("label") or protocol_name,
                        "code": proto_data.get("code") or "",
                    })
        if protocol_options:
            specs.append({
                "spec_group": "Control",
                "spec_label": "Dimming",
                "spec_value": ", ".join(o["display_label"] for o in protocol_options),
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 100,
                "show_on_card": 0,
                "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                "attribute_options_json": frappe.as_json(protocol_options),
                "attribute_options": protocol_options,
            })

    # ── Production Interval (cut increment from linked tape, in inches) ──
    if "Production Interval" not in existing_labels:
        increments_mm = set()
        for tape_row in template.allowed_tape_offerings or []:
            offering_name = getattr(tape_row, "tape_offering", None)
            if not offering_name:
                continue
            offering_data = frappe.db.get_value(
                "ilL-Rel-Tape Offering", offering_name,
                ["cut_increment_mm_override", "tape_spec"],
                as_dict=True,
            )
            if not offering_data:
                continue
            cut_mm = offering_data.get("cut_increment_mm_override")
            if not cut_mm and offering_data.get("tape_spec"):
                cut_mm = frappe.db.get_value(
                    "ilL-Spec-LED Tape", offering_data["tape_spec"],
                    "cut_increment_mm",
                )
            if cut_mm:
                increments_mm.add(cut_mm)
        if increments_mm:
            display_parts = [
                format_length_inches(v, precision=2)
                for v in sorted(increments_mm)
                if format_length_inches(v, precision=2)
            ]
            if display_parts:
                specs.append({
                    "spec_group": "Physical",
                    "spec_label": "Production Interval",
                    "spec_value": ", ".join(display_parts),
                    "spec_unit": "",
                    "is_calculated": 1,
                    "display_order": 110,
                    "show_on_card": 0,
                    "attribute_doctype": "",
                    "attribute_options_json": None,
                    "attribute_options": [],
                })

    return specs


def _enrich_driver_specs(product: dict, existing_labels: set) -> list:
    """Add missing specs for Driver products from linked doctype."""
    specs = []
    try:
        driver = frappe.get_doc("ilL-Spec-Driver", product["driver_spec"])
    except frappe.DoesNotExistError:
        return specs

    # ── Input Voltage (from min/max if legacy field is empty) ──
    if "Input Voltage" not in existing_labels:
        voltage_str = ""
        if driver.input_voltage:
            voltage_str = driver.input_voltage
        elif driver.input_voltage_min and driver.input_voltage_max:
            voltage_str = f"{driver.input_voltage_min}-{driver.input_voltage_max}"
            if driver.input_voltage_type:
                voltage_str += f" {driver.input_voltage_type}"
        if voltage_str:
            specs.append({
                "spec_group": "Electrical",
                "spec_label": "Input Voltage",
                "spec_value": voltage_str,
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 15,
                "show_on_card": 0,
                "attribute_doctype": "",
                "attribute_options_json": None,
                "attribute_options": [],
            })

    # ── Dimensions ─────────────────────────────────────────────
    if "Dimensions" not in existing_labels:
        dim_parts = []
        if driver.width_mm:
            dim_parts.append(f"{driver.width_mm}mm W")
        if driver.height_mm:
            dim_parts.append(f"{driver.height_mm}mm H")
        if driver.depth_mm:
            dim_parts.append(f"{driver.depth_mm}mm D")
        if dim_parts:
            specs.append({
                "spec_group": "Physical",
                "spec_label": "Dimensions",
                "spec_value": " x ".join(dim_parts),
                "spec_unit": "mm",
                "is_calculated": 1,
                "display_order": 55,
                "show_on_card": 0,
                "attribute_doctype": "",
                "attribute_options_json": None,
                "attribute_options": [],
            })

    # ── Dimming ────────────────────────────────────────────────
    if "Dimming" not in existing_labels and "Dimming Protocols" not in existing_labels:
        protocol_options = []
        seen = set()
        if getattr(driver, "output_protocol", None):
            proto_data = frappe.db.get_value(
                "ilL-Attribute-Dimming Protocol", driver.output_protocol,
                ["label", "code"], as_dict=True,
            )
            if proto_data:
                seen.add(driver.output_protocol)
                protocol_options.append({
                    "attribute_type": "Dimming Protocol",
                    "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                    "attribute_value": driver.output_protocol,
                    "display_label": proto_data.get("label") or driver.output_protocol,
                    "code": proto_data.get("code") or "",
                })
        for ip in getattr(driver, "input_protocols", []):
            pname = getattr(ip, "protocol", None)
            if pname and pname not in seen:
                seen.add(pname)
                proto_data = frappe.db.get_value(
                    "ilL-Attribute-Dimming Protocol", pname,
                    ["label", "code"], as_dict=True,
                )
                if proto_data:
                    protocol_options.append({
                        "attribute_type": "Dimming Protocol",
                        "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                        "attribute_value": pname,
                        "display_label": proto_data.get("label") or pname,
                        "code": proto_data.get("code") or "",
                    })
        if protocol_options:
            specs.append({
                "spec_group": "Control",
                "spec_label": "Dimming",
                "spec_value": ", ".join(o["display_label"] for o in protocol_options),
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 55,
                "show_on_card": 0,
                "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                "attribute_options_json": frappe.as_json(protocol_options),
                "attribute_options": protocol_options,
            })

    return specs


def _enrich_controller_specs(product: dict, existing_labels: set) -> list:
    """Add missing specs for Controller products from linked doctype."""
    specs = []
    try:
        controller = frappe.get_doc("ilL-Spec-Controller", product["controller_spec"])
    except frappe.DoesNotExistError:
        return specs

    # ── Input Voltage ──────────────────────────────────────────
    if "Input Voltage" not in existing_labels:
        if controller.input_voltage_min and controller.input_voltage_max:
            voltage_str = f"{controller.input_voltage_min}-{controller.input_voltage_max}"
            if controller.input_voltage_type:
                voltage_str += f" {controller.input_voltage_type}"
            specs.append({
                "spec_group": "Electrical",
                "spec_label": "Input Voltage",
                "spec_value": voltage_str,
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 15,
                "show_on_card": 0,
                "attribute_doctype": "",
                "attribute_options_json": None,
                "attribute_options": [],
            })

    # ── Dimensions ─────────────────────────────────────────────
    if "Dimensions" not in existing_labels:
        dim_parts = []
        if controller.width_mm:
            dim_parts.append(f"{controller.width_mm}mm W")
        if controller.height_mm:
            dim_parts.append(f"{controller.height_mm}mm H")
        if controller.depth_mm:
            dim_parts.append(f"{controller.depth_mm}mm D")
        if dim_parts:
            specs.append({
                "spec_group": "Physical",
                "spec_label": "Dimensions",
                "spec_value": " x ".join(dim_parts),
                "spec_unit": "mm",
                "is_calculated": 1,
                "display_order": 75,
                "show_on_card": 0,
                "attribute_doctype": "",
                "attribute_options_json": None,
                "attribute_options": [],
            })

    # ── Dimming ────────────────────────────────────────────────
    if "Dimming" not in existing_labels and "Input Protocols" not in existing_labels:
        protocol_options = []
        seen = set()
        for row in getattr(controller, "input_protocols", []):
            pname = getattr(row, "protocol", None)
            if pname and pname not in seen:
                seen.add(pname)
                proto_data = frappe.db.get_value(
                    "ilL-Attribute-Dimming Protocol", pname,
                    ["label", "code"], as_dict=True,
                )
                if proto_data:
                    protocol_options.append({
                        "attribute_type": "Dimming Protocol",
                        "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                        "attribute_value": pname,
                        "display_label": proto_data.get("label") or pname,
                        "code": proto_data.get("code") or "",
                    })
        for row in getattr(controller, "output_protocols", []):
            pname = getattr(row, "protocol", None)
            if pname and pname not in seen:
                seen.add(pname)
                proto_data = frappe.db.get_value(
                    "ilL-Attribute-Dimming Protocol", pname,
                    ["label", "code"], as_dict=True,
                )
                if proto_data:
                    protocol_options.append({
                        "attribute_type": "Dimming Protocol",
                        "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                        "attribute_value": pname,
                        "display_label": proto_data.get("label") or pname,
                        "code": proto_data.get("code") or "",
                    })
        if protocol_options:
            specs.append({
                "spec_group": "Control",
                "spec_label": "Dimming",
                "spec_value": ", ".join(o["display_label"] for o in protocol_options),
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 65,
                "show_on_card": 0,
                "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                "attribute_options_json": frappe.as_json(protocol_options),
                "attribute_options": protocol_options,
            })

    return specs


def _enrich_tape_specs(product: dict, existing_labels: set) -> list:
    """Add missing specs for LED Tape products from linked doctype."""
    specs = []
    try:
        tape = frappe.get_doc("ilL-Spec-LED Tape", product["tape_spec"])
    except frappe.DoesNotExistError:
        return specs

    # ── Color Rendering (CRI) ─────────────────────────────────
    if "Color Rendering" not in existing_labels and "CRI" not in existing_labels:
        if tape.cri_typical:
            specs.append({
                "spec_group": "Optical",
                "spec_label": "Color Rendering",
                "spec_value": str(tape.cri_typical),
                "spec_unit": "CRI",
                "is_calculated": 1,
                "display_order": 55,
                "show_on_card": 0,
                "attribute_doctype": "",
                "attribute_options_json": None,
                "attribute_options": [],
            })

    # ── Input Voltage ──────────────────────────────────────────
    if "Input Voltage" not in existing_labels:
        if tape.input_voltage:
            voltage_val = frappe.db.get_value(
                "ilL-Attribute-Output Voltage", tape.input_voltage, "dc_voltage"
            )
            if voltage_val:
                specs.append({
                    "spec_group": "Electrical",
                    "spec_label": "Input Voltage",
                    "spec_value": f"{voltage_val} VDC",
                    "spec_unit": "",
                    "is_calculated": 1,
                    "display_order": 25,
                    "show_on_card": 0,
                    "attribute_doctype": "ilL-Attribute-Output Voltage",
                    "attribute_options_json": None,
                    "attribute_options": [],
                })

    # ── Dimming ────────────────────────────────────────────────
    if "Dimming" not in existing_labels:
        protocol_options = []
        seen = set()
        if getattr(tape, "input_protocol", None):
            seen.add(tape.input_protocol)
            proto_data = frappe.db.get_value(
                "ilL-Attribute-Dimming Protocol", tape.input_protocol,
                ["label", "code"], as_dict=True,
            )
            if proto_data:
                protocol_options.append({
                    "attribute_type": "Dimming Protocol",
                    "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                    "attribute_value": tape.input_protocol,
                    "display_label": proto_data.get("label") or tape.input_protocol,
                    "code": proto_data.get("code") or "",
                })
        for row in getattr(tape, "supported_dimming_protocols", []):
            pname = getattr(row, "protocol", None)
            if pname and pname not in seen:
                seen.add(pname)
                proto_data = frappe.db.get_value(
                    "ilL-Attribute-Dimming Protocol", pname,
                    ["label", "code"], as_dict=True,
                )
                if proto_data:
                    protocol_options.append({
                        "attribute_type": "Dimming Protocol",
                        "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                        "attribute_value": pname,
                        "display_label": proto_data.get("label") or pname,
                        "code": proto_data.get("code") or "",
                    })
        if protocol_options:
            specs.append({
                "spec_group": "Control",
                "spec_label": "Dimming",
                "spec_value": ", ".join(o["display_label"] for o in protocol_options),
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 60,
                "show_on_card": 0,
                "attribute_doctype": "ilL-Attribute-Dimming Protocol",
                "attribute_options_json": frappe.as_json(protocol_options),
                "attribute_options": protocol_options,
            })

    # ── Production Interval (cut increment in inches) ─────────
    if "Production Interval" not in existing_labels:
        if tape.cut_increment_mm:
            formatted = format_length_inches(tape.cut_increment_mm, precision=2)
            if formatted:
                specs.append({
                    "spec_group": "Physical",
                    "spec_label": "Production Interval",
                    "spec_value": formatted,
                    "spec_unit": "",
                    "is_calculated": 1,
                    "display_order": 65,
                    "show_on_card": 0,
                    "attribute_doctype": "",
                    "attribute_options_json": None,
                    "attribute_options": [],
                })

    return specs


def _enrich_profile_specs(product: dict, existing_labels: set) -> list:
    """Add missing specs for Component/Extrusion Kit products from profile."""
    specs = []
    try:
        profile = frappe.get_doc("ilL-Spec-Profile", product["profile_spec"])
    except frappe.DoesNotExistError:
        return specs

    # ── Dimensions ─────────────────────────────────────────────
    if "Dimensions" not in existing_labels:
        dimensions = profile.dimensions or compute_profile_dimensions(profile.width_mm, profile.height_mm)
        if dimensions:
            specs.append({
                "spec_group": "Physical",
                "spec_label": "Dimensions",
                "spec_value": dimensions,
                "spec_unit": "",
                "is_calculated": 1,
                "display_order": 45,
                "show_on_card": 0,
                "attribute_doctype": "",
                "attribute_options_json": None,
                "attribute_options": [],
            })

    return specs


def _build_certifications_spec(doc) -> dict | None:
    """Build a Certifications & Ratings spec entry from the product's certifications."""
    if not getattr(doc, "certifications", None):
        return None

    cert_options = []
    for c in doc.certifications:
        cert_name = c.certification
        if not cert_name:
            continue
        details = _get_certification_details(cert_name)
        cert_options.append({
            "attribute_type": "Certification",
            "attribute_doctype": "ilL-Attribute-Certification",
            "attribute_value": cert_name,
            "display_label": details.get("certification_code") or cert_name,
            "certification_body": details.get("certification_body") or "",
            "badge_image": _make_absolute_url(details.get("badge_image")) if details.get("badge_image") else "",
        })

    if not cert_options:
        return None

    return {
        "spec_group": "Compliance",
        "spec_label": "Certifications & Ratings",
        "spec_value": ", ".join(o["display_label"] for o in cert_options),
        "spec_unit": "",
        "is_calculated": 1,
        "display_order": 120,
        "show_on_card": 0,
        "attribute_doctype": "ilL-Attribute-Certification",
        "attribute_options_json": frappe.as_json(cert_options),
        "attribute_options": cert_options,
    }
