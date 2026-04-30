# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add variant lineage fields to Configured Fixture / Tape-Neon and
power-supply tracking fields to Quotation Item / Sales Order Item.

This patch supports the Build / Add Configured Product flow.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


VARIANT_ORIGIN_OPTIONS = "Portal\nQuotation Tool\nSales Order Tool\nBuilder CLI\nAPI"


def _quote_order_power_supply_fields(insert_after: str) -> list[dict]:
    return [
        {
            "fieldname": "ill_is_power_supply_line",
            "fieldtype": "Check",
            "label": "Power Supply Line",
            "insert_after": insert_after,
            "default": "0",
            "read_only": 1,
        },
        {
            "fieldname": "ill_power_supply_for",
            "fieldtype": "Data",
            "label": "Power Supply For (Row)",
            "insert_after": "ill_is_power_supply_line",
            "read_only": 1,
        },
        {
            "fieldname": "ill_parent_configured_fixture",
            "fieldtype": "Link",
            "label": "Original Configured Fixture",
            "options": "ilL-Configured-Fixture",
            "insert_after": "ill_power_supply_for",
            "read_only": 1,
        },
    ]


def execute():
    # Reload doctypes that gained native fields via JSON edits.
    for dt in ("ilL-Configured-Fixture", "ilL-Configured-Tape-Neon"):
        try:
            frappe.reload_doctype(dt, force=True)
        except Exception:
            # Reload is best-effort; migrate will re-sync.
            pass

    # Quotation Item / Sales Order Item: track power-supply lines tied to a
    # configured row.  Inserted after ill_engine_version (the last field added
    # by add_quote_order_configurator_fields).
    custom_fields = {
        "Quotation Item": _quote_order_power_supply_fields("ill_engine_version"),
        "Sales Order Item": _quote_order_power_supply_fields("ill_engine_version"),
    }
    create_custom_fields(custom_fields, update=True)

    # Backfill variant_origin on existing records (these all pre-date the
    # Quotation/Sales Order Tool flow, so they came from the portal).
    if frappe.db.has_column("ilL-Configured-Fixture", "variant_origin"):
        frappe.db.sql(
            """
            UPDATE `tabilL-Configured-Fixture`
               SET variant_origin = 'Portal'
             WHERE variant_origin IS NULL OR variant_origin = ''
            """
        )

    if frappe.db.has_column("ilL-Configured-Tape-Neon", "variant_origin"):
        frappe.db.sql(
            """
            UPDATE `tabilL-Configured-Tape-Neon`
               SET variant_origin = 'Portal'
             WHERE variant_origin IS NULL OR variant_origin = ''
            """
        )

    frappe.db.commit()
    print("Added configured variant lineage + power-supply tracking fields")
