# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Attributes Export API

This module provides API endpoints for exporting ilL-Attribute doctypes to Webflow CMS
collections via n8n automation workflows.

Each attribute doctype maps to a corresponding Webflow CMS collection:
- ilL-Attribute-CCT -> CCT Options collection
- ilL-Attribute-Finish -> Finish Options collection
- ilL-Attribute-Dimming Protocol -> Dimming Protocols collection
- ilL-Attribute-CRI -> CRI Options collection
- ilL-Attribute-Environment Rating -> Environment Ratings collection
- ilL-Attribute-IP Rating -> IP Ratings collection
- ilL-Attribute-LED Package -> LED Packages collection
- ilL-Attribute-Lens Appearance -> Lens Appearances collection
- ilL-Attribute-Mounting Method -> Mounting Methods collection
- ilL-Attribute-Output Level -> Output Levels collection
- ilL-Attribute-Output Voltage -> Output Voltages collection
- ilL-Attribute-Certification -> Certifications collection
- ilL-Attribute-Endcap Style -> Endcap Styles collection
- ilL-Attribute-Endcap Color -> Endcap Colors collection
- ilL-Attribute-Feed Direction -> Feed Directions collection
- ilL-Attribute-Joiner Angle -> Joiner Angles collection
- ilL-Attribute-Joiner System -> Joiner Systems collection
- ilL-Attribute-Lead Time Class -> Lead Time Classes collection
- ilL-Attribute-Leader Cable -> Leader Cables collection
- ilL-Attribute-Lens Interface Type -> Lens Interface Types collection
- ilL-Attribute-Power Feed Type -> Power Feed Types collection
- ilL-Attribute-Pricing Class -> Pricing Classes collection
- ilL-Attribute-SDCM -> SDCM Options collection

Endpoints:
- get_webflow_attributes: Retrieve attributes for export to Webflow
- mark_attribute_synced: Mark an attribute as synced after successful Webflow push
- mark_attribute_error: Mark an attribute as having a sync error
- get_attribute_sync_statistics: Get sync status statistics
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

import frappe
from frappe import _


# Mapping of attribute doctypes to their configuration
# Each entry contains:
# - doctype: The ERPNext doctype name
# - name_field: The primary name/label field
# - code_field: The code field (if any)
# - webflow_collection_id: Webflow collection ID (to be configured)
# - fields: List of fields to export to Webflow
ATTRIBUTE_DOCTYPES = {
    "cct": {
        "doctype": "ilL-Attribute-CCT",
        "name_field": "cct_name",
        "code_field": "code",
        "slug_field": "cct_name",
        "webflow_collection_id": "",  # Set in Webflow Settings
        "fields": ["cct_name", "code", "label", "kelvin", "hex_color", "sample_photo", 
                   "lumen_multiplier", "description", "sort_order", "is_active"],
        "webflow_field_mapping": {
            "name": "cct_name",
            "slug": "cct_name",
            "cct-code": "code",
            "kelvin-value": "kelvin",
            "hex-color": "hex_color",
            "sample-photo": "sample_photo",
            "lumen-multiplier": "lumen_multiplier",
            "description": "description",
            "sort-order": "sort_order"
        }
    },
    "finish": {
        "doctype": "ilL-Attribute-Finish",
        "name_field": "finish_name",
        "code_field": "code",
        "slug_field": "finish_name",
        "webflow_collection_id": "",
        "fields": ["finish_name", "code", "status", "hex_color", "texture_feel", 
                   "image_attach", "type", "thermal_performance_factor", "moq", "notes"],
        "webflow_field_mapping": {
            "name": "finish_name",
            "slug": "finish_name",
            "finish-code": "code",
            "status": "status",
            "hex-color": "hex_color",
            "texture": "texture_feel",
            "image": "image_attach",
            "finish-type": "type",
            "thermal-factor": "thermal_performance_factor",
            "moq": "moq"
        }
    },
    "dimming_protocol": {
        "doctype": "ilL-Attribute-Dimming Protocol",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "protocol", "code", "signal_type", "requires_interface", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "protocol-code": "code",
            "protocol-type": "protocol",
            "signal-type": "signal_type",
            "requires-interface": "requires_interface",
            "notes": "notes"
        }
    },
    "cri": {
        "doctype": "ilL-Attribute-CRI",
        "name_field": "cri_name",
        "code_field": "code",
        "slug_field": "cri_name",
        "webflow_collection_id": "",
        "fields": ["cri_name", "code", "cri_value", "description", "sort_order"],
        "webflow_field_mapping": {
            "name": "cri_name",
            "slug": "cri_name",
            "cri-code": "code",
            "cri-value": "cri_value",
            "description": "description",
            "sort-order": "sort_order"
        }
    },
    "environment_rating": {
        "doctype": "ilL-Attribute-Environment Rating",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "rating-code": "code",
            "description": "description"
        }
    },
    "ip_rating": {
        "doctype": "ilL-Attribute-IP Rating",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "solid_protection", "liquid_protection", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "ip-code": "code",
            "solid-protection": "solid_protection",
            "liquid-protection": "liquid_protection",
            "description": "description"
        }
    },
    "led_package": {
        "doctype": "ilL-Attribute-LED Package",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "manufacturer", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "package-code": "code",
            "manufacturer": "manufacturer",
            "description": "description"
        }
    },
    "lens_appearance": {
        "doctype": "ilL-Attribute-Lens Appearance",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "transmission", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "lens-code": "code",
            "transmission": "transmission"
        }
    },
    "mounting_method": {
        "doctype": "ilL-Attribute-Mounting Method",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "mounting-code": "code",
            "description": "description"
        }
    },
    "output_level": {
        "doctype": "ilL-Attribute-Output Level",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "watts_per_meter", "lumens_per_meter", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "output-code": "code",
            "watts-per-meter": "watts_per_meter",
            "lumens-per-meter": "lumens_per_meter",
            "description": "description"
        }
    },
    "output_voltage": {
        "doctype": "ilL-Attribute-Output Voltage",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "voltage", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "voltage-code": "code",
            "voltage-value": "voltage",
            "description": "description"
        }
    },
    "certification": {
        "doctype": "ilL-Attribute-Certification",
        "name_field": "certification_name",
        "code_field": "certification_code",
        "slug_field": "certification_name",
        "webflow_collection_id": "",
        "fields": ["certification_name", "certification_code", "certification_body", 
                   "description", "badge_image", "sort_order", "is_active"],
        "webflow_field_mapping": {
            "name": "certification_name",
            "slug": "certification_name",
            "certification-code": "certification_code",
            "certification-body": "certification_body",
            "description": "description",
            "badge-image": "badge_image",
            "sort-order": "sort_order"
        }
    },
    "endcap_style": {
        "doctype": "ilL-Attribute-Endcap Style",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "endcap-code": "code",
            "description": "description"
        }
    },
    "endcap_color": {
        "doctype": "ilL-Attribute-Endcap Color",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "hex_color", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "color-code": "code",
            "hex-color": "hex_color"
        }
    },
    "feed_direction": {
        "doctype": "ilL-Attribute-Feed-Direction",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "direction-code": "code",
            "description": "description"
        }
    },
    "joiner_angle": {
        "doctype": "ilL-Attribute-Joiner Angle",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "angle_degrees", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "angle-code": "code",
            "angle-degrees": "angle_degrees",
            "description": "description"
        }
    },
    "joiner_system": {
        "doctype": "ilL-Attribute-Joiner System",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "system-code": "code",
            "description": "description"
        }
    },
    "lead_time_class": {
        "doctype": "ilL-Attribute-Lead Time Class",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "min_days", "max_days", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "class-code": "code",
            "min-days": "min_days",
            "max-days": "max_days",
            "description": "description"
        }
    },
    "leader_cable": {
        "doctype": "ilL-Attribute-Leader Cable",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "length_mm", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "cable-code": "code",
            "length-mm": "length_mm",
            "description": "description"
        }
    },
    "lens_interface_type": {
        "doctype": "ilL-Attribute-Lens Interface Type",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "interface-code": "code",
            "description": "description"
        }
    },
    "power_feed_type": {
        "doctype": "ilL-Attribute-Power Feed Type",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "feed-type-code": "code",
            "description": "description"
        }
    },
    "pricing_class": {
        "doctype": "ilL-Attribute-Pricing Class",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "multiplier", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "pricing-code": "code",
            "multiplier": "multiplier",
            "description": "description"
        }
    },
    "sdcm": {
        "doctype": "ilL-Attribute-SDCM",
        "name_field": "label",
        "code_field": "code",
        "slug_field": "label",
        "webflow_collection_id": "",
        "fields": ["label", "code", "sdcm_value", "description", "notes"],
        "webflow_field_mapping": {
            "name": "label",
            "slug": "label",
            "sdcm-code": "code",
            "sdcm-value": "sdcm_value",
            "description": "description"
        }
    }
}


@frappe.whitelist(allow_guest=False)
def get_attribute_type_mapping() -> dict:
    """
    Get the complete mapping of attribute types to their configuration.
    
    Useful for understanding what attribute types are available and their
    corresponding Webflow field mappings.
    
    Returns:
        dict: {
            "attribute_types": {
                "cct": {
                    "doctype": "ilL-Attribute-CCT",
                    "name_field": "cct_name",
                    "webflow_collection_id": str,
                    "webflow_field_mapping": {...}
                },
                ...
            }
        }
    """
    result = {"attribute_types": {}}
    
    for attr_type, config in ATTRIBUTE_DOCTYPES.items():
        collection_id = get_webflow_collection_id(attr_type) or config.get("webflow_collection_id", "")
        result["attribute_types"][attr_type] = {
            "doctype": config["doctype"],
            "name_field": config["name_field"],
            "code_field": config.get("code_field"),
            "webflow_collection_id": collection_id,
            "webflow_field_mapping": config["webflow_field_mapping"],
            "has_collection_id": bool(collection_id)
        }
    
    return result


def get_attribute_config(attribute_type: str) -> Dict[str, Any]:
    """
    Get configuration for a specific attribute type.
    
    Args:
        attribute_type: The attribute type key (e.g., "cct", "finish")
        
    Returns:
        dict: Configuration for the attribute type
    """
    config = ATTRIBUTE_DOCTYPES.get(attribute_type)
    if not config:
        frappe.throw(_("Unknown attribute type: {0}").format(attribute_type))
    return config


def slugify(text: str) -> str:
    """
    Convert text to a URL-safe slug.
    
    Args:
        text: The text to slugify
        
    Returns:
        str: URL-safe slug
    """
    import re
    if not text:
        return ""
    # Convert to lowercase and replace spaces with hyphens
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove non-word chars
    slug = re.sub(r'[-\s]+', '-', slug)   # Replace spaces/hyphens with single hyphen
    return slug


@frappe.whitelist(allow_guest=False)
def get_webflow_attributes(
    attribute_type: str,
    sync_status: str = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    Get attributes of a specific type for export to Webflow.
    
    Args:
        attribute_type: Type of attribute to fetch (e.g., "cct", "finish", "dimming_protocol")
        sync_status: Filter by sync status ("Pending", "Never Synced", "needs_sync")
        limit: Maximum records to return (default: 100)
        offset: Pagination offset (default: 0)
    
    Returns:
        dict: {
            "attributes": [...],
            "total": int,
            "limit": int,
            "offset": int,
            "attribute_type": str,
            "doctype": str,
            "webflow_collection_id": str
        }
    
    Example:
        >>> get_webflow_attributes(attribute_type="cct", sync_status="needs_sync")
    """
    config = get_attribute_config(attribute_type)
    doctype = config["doctype"]
    
    filters = {}
    
    # Check if doctype has is_active field
    meta = frappe.get_meta(doctype)
    has_is_active = meta.has_field("is_active")
    has_status = meta.has_field("status")
    has_webflow_item_id = meta.has_field("webflow_item_id")
    has_webflow_sync_status = meta.has_field("webflow_sync_status")
    
    # Apply active filter if field exists
    if has_is_active:
        filters["is_active"] = 1
    elif has_status:
        filters["status"] = "Active"
    
    # Apply sync status filter if field exists
    if sync_status and has_webflow_sync_status:
        if sync_status == "needs_sync":
            filters["webflow_sync_status"] = ["in", ["Pending", "Never Synced", ""]]
        else:
            filters["webflow_sync_status"] = sync_status
    
    # Get list of fields to fetch
    fields_to_fetch = ["name", "creation", "modified"]
    for field in config["fields"]:
        if meta.has_field(field):
            fields_to_fetch.append(field)
    
    # Add webflow tracking fields if they exist
    if has_webflow_item_id:
        fields_to_fetch.append("webflow_item_id")
    if has_webflow_sync_status:
        fields_to_fetch.append("webflow_sync_status")
    if meta.has_field("webflow_last_synced"):
        fields_to_fetch.append("webflow_last_synced")
    
    # Fetch attributes
    attributes = frappe.get_all(
        doctype,
        filters=filters,
        fields=fields_to_fetch,
        limit=limit,
        start=offset,
        order_by="modified desc"
    )
    
    # Add computed fields and webflow formatting
    for attr in attributes:
        # Generate slug from name field
        name_field = config["name_field"]
        attr["slug"] = slugify(attr.get(name_field, attr["name"]))
        attr["erp_doc_name"] = attr["name"]
        
        # Build webflow field data
        webflow_data = {}
        for wf_field, erp_field in config["webflow_field_mapping"].items():
            if wf_field == "slug":
                webflow_data[wf_field] = attr["slug"]
            elif erp_field in attr:
                value = attr[erp_field]
                # Convert booleans for Webflow
                if isinstance(value, int) and erp_field not in ["sort_order", "kelvin", "moq", 
                    "transmission", "watts_per_meter", "lumens_per_meter", "voltage",
                    "angle_degrees", "min_days", "max_days", "length_mm", "sdcm_value",
                    "thermal_performance_factor", "lumen_multiplier", "multiplier", "cri_value"]:
                    if meta.has_field(erp_field):
                        field_type = meta.get_field(erp_field).fieldtype
                        if field_type == "Check":
                            value = bool(value)
                webflow_data[wf_field] = value
        
        attr["webflow_field_data"] = webflow_data
    
    total = frappe.db.count(doctype, filters)
    
    # Get webflow collection ID from settings if available
    webflow_collection_id = config.get("webflow_collection_id", "")
    settings_collection_id = get_webflow_collection_id(attribute_type)
    if settings_collection_id:
        webflow_collection_id = settings_collection_id
    
    return {
        "attributes": attributes,
        "total": total,
        "limit": limit,
        "offset": offset,
        "attribute_type": attribute_type,
        "doctype": doctype,
        "webflow_collection_id": webflow_collection_id,
        "field_mapping": config["webflow_field_mapping"]
    }


@frappe.whitelist(allow_guest=False)
def get_all_attributes_for_sync(
    sync_status: str = "needs_sync"
) -> dict:
    """
    Get all attribute types that have items needing sync.
    
    Args:
        sync_status: Filter by sync status (default: "needs_sync")
    
    Returns:
        dict: {
            "attribute_types": [
                {
                    "type": str,
                    "doctype": str,
                    "count": int,
                    "webflow_collection_id": str
                },
                ...
            ],
            "total_pending": int
        }
    """
    result = {
        "attribute_types": [],
        "total_pending": 0
    }
    
    for attr_type, config in ATTRIBUTE_DOCTYPES.items():
        doctype = config["doctype"]
        
        # Check if doctype exists
        if not frappe.db.exists("DocType", doctype):
            continue
        
        meta = frappe.get_meta(doctype)
        filters = {}
        
        # Apply active filter if field exists
        if meta.has_field("is_active"):
            filters["is_active"] = 1
        elif meta.has_field("status"):
            filters["status"] = "Active"
        
        # Count based on sync status
        if meta.has_field("webflow_sync_status"):
            if sync_status == "needs_sync":
                filters["webflow_sync_status"] = ["in", ["Pending", "Never Synced", ""]]
            else:
                filters["webflow_sync_status"] = sync_status
            count = frappe.db.count(doctype, filters)
        else:
            # If no sync status field, all records need sync
            count = frappe.db.count(doctype, filters)
        
        if count > 0:
            webflow_collection_id = get_webflow_collection_id(attr_type) or config.get("webflow_collection_id", "")
            result["attribute_types"].append({
                "type": attr_type,
                "doctype": doctype,
                "count": count,
                "webflow_collection_id": webflow_collection_id
            })
            result["total_pending"] += count
    
    return result


@frappe.whitelist(allow_guest=False)
def mark_attribute_synced(
    attribute_type: str,
    doc_name: str,
    webflow_item_id: str
) -> dict:
    """
    Mark an attribute as synced after n8n pushes to Webflow.
    
    Called by n8n after successful Webflow API call.
    
    Args:
        attribute_type: The attribute type key (e.g., "cct", "finish")
        doc_name: The document name in ERPNext
        webflow_item_id: The Webflow CMS item ID
    
    Returns:
        dict: {"success": True, "synced_at": datetime}
    """
    config = get_attribute_config(attribute_type)
    doctype = config["doctype"]
    
    if not frappe.db.exists(doctype, doc_name):
        frappe.throw(_("{0} with name '{1}' not found").format(doctype, doc_name))
    
    meta = frappe.get_meta(doctype)
    
    # Update webflow fields if they exist
    update_fields = {}
    
    if meta.has_field("webflow_item_id"):
        update_fields["webflow_item_id"] = webflow_item_id
    if meta.has_field("webflow_sync_status"):
        update_fields["webflow_sync_status"] = "Synced"
    if meta.has_field("webflow_last_synced"):
        update_fields["webflow_last_synced"] = frappe.utils.now()
    if meta.has_field("webflow_sync_error"):
        update_fields["webflow_sync_error"] = None
    
    if update_fields:
        frappe.db.set_value(doctype, doc_name, update_fields)
        frappe.db.commit()
    
    return {
        "success": True,
        "synced_at": frappe.utils.now(),
        "doc_name": doc_name,
        "attribute_type": attribute_type
    }


@frappe.whitelist(allow_guest=False)
def mark_attribute_error(
    attribute_type: str,
    doc_name: str,
    error_message: str
) -> dict:
    """
    Mark an attribute as having a sync error.
    
    Called by n8n when Webflow API call fails.
    
    Args:
        attribute_type: The attribute type key (e.g., "cct", "finish")
        doc_name: The document name in ERPNext
        error_message: The error message from Webflow
    
    Returns:
        dict: {"success": True}
    """
    config = get_attribute_config(attribute_type)
    doctype = config["doctype"]
    
    if not frappe.db.exists(doctype, doc_name):
        frappe.throw(_("{0} with name '{1}' not found").format(doctype, doc_name))
    
    meta = frappe.get_meta(doctype)
    update_fields = {}
    
    if meta.has_field("webflow_sync_status"):
        update_fields["webflow_sync_status"] = "Error"
    if meta.has_field("webflow_sync_error"):
        update_fields["webflow_sync_error"] = error_message[:500] if error_message else "Unknown error"
    
    if update_fields:
        frappe.db.set_value(doctype, doc_name, update_fields)
        frappe.db.commit()
    
    frappe.log_error(
        message=error_message[:1000] if error_message else "Unknown error",
        title=f"Webflow Attribute Sync Error: {doctype} - {doc_name}"
    )
    
    return {
        "success": True,
        "doc_name": doc_name,
        "attribute_type": attribute_type
    }


@frappe.whitelist(allow_guest=False)
def trigger_attribute_sync(
    attribute_type: str = None,
    doc_names: list = None,
    sync_all: bool = False
) -> dict:
    """
    Mark attributes as pending sync to trigger n8n workflow.
    
    Args:
        attribute_type: The attribute type to sync (required unless sync_all=True)
        doc_names: List of specific document names to sync
        sync_all: Sync all active attributes of the specified type (or all types if attribute_type is None)
    
    Returns:
        dict: {"success": True, "marked_count": int, "attribute_types": list}
    """
    marked_count = 0
    attribute_types_marked = []
    
    types_to_process = []
    
    if sync_all and not attribute_type:
        # Sync all attribute types
        types_to_process = list(ATTRIBUTE_DOCTYPES.keys())
    elif attribute_type:
        types_to_process = [attribute_type]
    else:
        frappe.throw(_("Either attribute_type or sync_all=True is required"))
    
    for attr_type in types_to_process:
        config = get_attribute_config(attr_type)
        doctype = config["doctype"]
        
        if not frappe.db.exists("DocType", doctype):
            continue
        
        meta = frappe.get_meta(doctype)
        
        if not meta.has_field("webflow_sync_status"):
            continue
        
        if doc_names and attr_type == attribute_type:
            # Mark specific documents
            for name in doc_names:
                if frappe.db.exists(doctype, name):
                    frappe.db.set_value(doctype, name, "webflow_sync_status", "Pending")
                    marked_count += 1
        else:
            # Mark all active documents
            filters = {}
            if meta.has_field("is_active"):
                filters["is_active"] = 1
            elif meta.has_field("status"):
                filters["status"] = "Active"
            
            docs = frappe.get_all(doctype, filters=filters, pluck="name")
            for name in docs:
                frappe.db.set_value(doctype, name, "webflow_sync_status", "Pending")
                marked_count += 1
        
        if marked_count > 0:
            attribute_types_marked.append(attr_type)
    
    frappe.db.commit()
    
    return {
        "success": True,
        "marked_count": marked_count,
        "attribute_types": attribute_types_marked
    }


@frappe.whitelist(allow_guest=False)
def get_attribute_sync_statistics() -> dict:
    """
    Get statistics about Webflow sync status for all attribute types.
    
    Returns:
        dict: Statistics by attribute type including counts by sync status
    """
    stats = {
        "by_type": {},
        "totals": {
            "synced": 0,
            "pending": 0,
            "error": 0,
            "never_synced": 0,
            "total": 0
        }
    }
    
    for attr_type, config in ATTRIBUTE_DOCTYPES.items():
        doctype = config["doctype"]
        
        if not frappe.db.exists("DocType", doctype):
            continue
        
        meta = frappe.get_meta(doctype)
        
        type_stats = {
            "doctype": doctype,
            "by_status": {},
            "total_active": 0,
            "needs_sync": 0
        }
        
        # Base filter for active records
        base_filters = {}
        if meta.has_field("is_active"):
            base_filters["is_active"] = 1
        elif meta.has_field("status"):
            base_filters["status"] = "Active"
        
        type_stats["total_active"] = frappe.db.count(doctype, base_filters)
        
        if meta.has_field("webflow_sync_status"):
            for status in ["Pending", "Synced", "Error", "Never Synced"]:
                filters = dict(base_filters)
                if status == "Never Synced":
                    # Include empty and null values
                    count = frappe.db.count(doctype, dict(base_filters, webflow_sync_status=["in", ["Never Synced", ""]]))
                else:
                    filters["webflow_sync_status"] = status
                    count = frappe.db.count(doctype, filters)
                
                type_stats["by_status"][status] = count
                
                # Update totals
                if status == "Synced":
                    stats["totals"]["synced"] += count
                elif status == "Pending":
                    stats["totals"]["pending"] += count
                    type_stats["needs_sync"] += count
                elif status == "Error":
                    stats["totals"]["error"] += count
                elif status == "Never Synced":
                    stats["totals"]["never_synced"] += count
                    type_stats["needs_sync"] += count
        else:
            # No sync status field - all records need sync
            type_stats["by_status"]["Never Synced"] = type_stats["total_active"]
            type_stats["needs_sync"] = type_stats["total_active"]
            stats["totals"]["never_synced"] += type_stats["total_active"]
        
        stats["totals"]["total"] += type_stats["total_active"]
        stats["by_type"][attr_type] = type_stats
    
    return stats


def get_webflow_collection_id(attribute_type: str) -> str:
    """
    Get the Webflow collection ID for an attribute type from settings.
    
    Args:
        attribute_type: The attribute type key
        
    Returns:
        str: The Webflow collection ID or empty string
    """
    # Try to get from a settings doctype if it exists
    try:
        if frappe.db.exists("DocType", "ilL-Webflow-Settings"):
            settings = frappe.get_single("ilL-Webflow-Settings")
            field_name = f"collection_id_{attribute_type}"
            if hasattr(settings, field_name):
                return getattr(settings, field_name) or ""
    except Exception:
        pass
    
    return ""


def mark_attribute_needs_sync(doctype: str, doc_name: str):
    """
    Mark an attribute document as needing sync when it's updated.
    Called from doc_events hooks.
    
    Args:
        doctype: The doctype name
        doc_name: The document name
    """
    meta = frappe.get_meta(doctype)
    
    if meta.has_field("webflow_sync_status"):
        frappe.db.set_value(
            doctype, doc_name, 
            "webflow_sync_status", "Pending",
            update_modified=False
        )


def get_attribute_type_from_doctype(doctype: str) -> str:
    """
    Get the attribute type key from a doctype name.
    
    Args:
        doctype: The ERPNext doctype name
        
    Returns:
        str: The attribute type key or None
    """
    for attr_type, config in ATTRIBUTE_DOCTYPES.items():
        if config["doctype"] == doctype:
            return attr_type
    return None
