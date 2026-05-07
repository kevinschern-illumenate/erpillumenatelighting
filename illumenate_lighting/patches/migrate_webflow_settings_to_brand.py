# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Migrate the legacy ``ilL-Webflow-Settings`` collection_id_* scalars into a
per-brand ``ilL-Webflow-Brand-Collection`` table on the ``illumenate`` brand.

Idempotent: existing rows for the same ``collection_kind`` are updated rather
than duplicated.
"""

import frappe


# ilL-Webflow-Settings field name -> ilL-Webflow-Brand-Collection.collection_kind
SETTINGS_FIELD_TO_KIND = {
    "products_collection_id": "Products",
    "categories_collection_id": "Categories",
    "collection_id_series": "Series",
    "collection_id_cct": "CCT",
    "collection_id_cri": "CRI",
    "collection_id_certification": "Certification",
    "collection_id_dimming_protocol": "Dimming Protocol",
    "collection_id_endcap_color": "Endcap Color",
    "collection_id_endcap_style": "Endcap Style",
    "collection_id_environment_rating": "Environment Rating",
    "collection_id_feed_direction": "Feed-Direction",
    "collection_id_finish": "Finish",
    "collection_id_ip_rating": "IP Rating",
    "collection_id_joiner_angle": "Joiner Angle",
    "collection_id_joiner_system": "Joiner System",
    "collection_id_lead_time_class": "Lead Time Class",
    "collection_id_leader_cable": "Leader Cable",
    "collection_id_led_package": "LED Package",
    "collection_id_lens_appearance": "Lens Appearance",
    "collection_id_lens_interface_type": "Lens Interface Type",
    "collection_id_mounting_method": "Mounting Method",
    "collection_id_output_level": "Output Level",
    "collection_id_output_voltage": "Output Voltage",
    "collection_id_power_feed_type": "Power Feed Type",
    "collection_id_pricing_class": "Pricing Class",
    "collection_id_sdcm": "SDCM",
}


def execute():
    if not (
        frappe.db.exists("DocType", "ilL-Webflow-Settings")
        and frappe.db.exists("DocType", "ilL-Webflow-Brand")
        and frappe.db.exists("DocType", "ilL-Webflow-Brand-Collection")
    ):
        return

    brand_name = frappe.db.get_value("ilL-Webflow-Brand", {"brand_code": "illumenate"}, "name")
    if not brand_name:
        return

    settings = frappe.get_single("ilL-Webflow-Settings")
    brand = frappe.get_doc("ilL-Webflow-Brand", brand_name)

    # Build map of existing rows by kind for idempotency
    existing = {row.collection_kind: row for row in (brand.collections or [])}

    # Top-level webflow_site_id (mirrored to brand for back-compat)
    site_id = getattr(settings, "site_id", None) or getattr(settings, "webflow_site_id", None)
    if site_id and not brand.webflow_site_id:
        brand.webflow_site_id = site_id

    changed = False
    for fieldname, kind in SETTINGS_FIELD_TO_KIND.items():
        value = getattr(settings, fieldname, None)
        if not value:
            continue
        if kind in existing:
            row = existing[kind]
            if row.webflow_collection_id != value:
                row.webflow_collection_id = value
                changed = True
        else:
            brand.append("collections", {
                "collection_kind": kind,
                "webflow_collection_id": value,
            })
            changed = True

    if changed or site_id:
        brand.flags.ignore_permissions = True
        brand.save()
        frappe.db.commit()
