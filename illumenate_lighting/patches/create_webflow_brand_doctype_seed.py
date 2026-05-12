# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Seed the ilL-Webflow-Brand DocType with the two MVP brands:
``illumenate`` (default, active) and ``lighting_206`` (inactive at install).

This patch is idempotent: re-running it is safe.
"""

import frappe


SEED_BRANDS = [
    {
        "brand_code": "illumenate",
        "brand_label": "ilLumenate",
        "is_active": 1,
        "is_default": 1,
        "sync_enabled": 1,
        "include_configurator_payload": 1,
        "n8n_webflow_credential_name": "webflow-illumenate",
        "webflow_site_url": "https://www.illumenatelighting.com",
    },
    {
        "brand_code": "lighting_206",
        "brand_label": "Lighting 206",
        "is_active": 0,
        "is_default": 0,
        "sync_enabled": 0,
        "include_configurator_payload": 0,
        "n8n_webflow_credential_name": "webflow-lighting_206",
        "webflow_site_url": "https://www.lighting206.com",
    },
]


def execute():
    if not frappe.db.exists("DocType", "ilL-Webflow-Brand"):
        return

    for seed in SEED_BRANDS:
        code = seed["brand_code"]
        if frappe.db.exists("ilL-Webflow-Brand", {"brand_code": code}):
            continue
        doc = frappe.new_doc("ilL-Webflow-Brand")
        doc.update(seed)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_validate = False
        doc.insert()

    frappe.db.commit()
