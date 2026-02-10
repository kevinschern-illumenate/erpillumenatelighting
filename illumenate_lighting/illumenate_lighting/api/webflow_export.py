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

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.webflow_attributes import (
    ATTRIBUTE_DOCTYPES,
    resolve_attribute_webflow_ids,
    build_product_multiref_field_data,
    ATTRIBUTE_MULTIREF_FIELD_SLUGS,
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
            "short_description", "long_description", "featured_image",
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
        # Expand child tables for each product
        for product in products:
            doc = frappe.get_doc("ilL-Webflow-Product", product["name"])
            
            # Convert featured_image to absolute URL
            if product.get("featured_image"):
                product["featured_image"] = _make_absolute_url(product["featured_image"])
            
            # DEPRECATED: specifications table has been removed
            # Return empty array for backwards compatibility with n8n workflows
            # Use attribute_links and attribute_links_by_type instead
            product["specifications"] = []
            
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
            
            # Add attribute links for Webflow multi-reference fields
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
            
            # Build reverse mapping: attribute doctype -> code_field
            _doctype_to_code_field = {}
            for _cfg in ATTRIBUTE_DOCTYPES.values():
                _doctype_to_code_field[_cfg["doctype"]] = _cfg.get("code_field") or None

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
            
            # Multi-reference fields: resolve attribute links to Webflow Item ID arrays
            # This enables Webflow multi-reference fields for filtering products by attributes
            product["attribute_webflow_ids_by_type"] = resolve_attribute_webflow_ids(
                product["attribute_links"]
            )
            product["multiref_field_data"] = build_product_multiref_field_data(
                product["attribute_webflow_ids_by_type"]
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
