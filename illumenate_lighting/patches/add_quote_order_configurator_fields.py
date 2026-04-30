# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add custom fields needed by the ERPNext quote/order configurator."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _configured_product_fields(insert_after: str) -> list[dict]:
    return [
        {
            "fieldname": "ill_product_type",
            "fieldtype": "Select",
            "label": "Configured Product Type",
            "options": "\nLinear Fixture\nLED Tape\nLED Neon",
            "insert_after": insert_after,
            "read_only": 1,
        },
        {
            "fieldname": "ill_configured_fixture",
            "fieldtype": "Link",
            "label": "Configured Fixture",
            "options": "ilL-Configured-Fixture",
            "insert_after": "ill_product_type",
            "read_only": 1,
        },
        {
            "fieldname": "ill_configured_tape_neon",
            "fieldtype": "Link",
            "label": "Configured Tape/Neon",
            "options": "ilL-Configured-Tape-Neon",
            "insert_after": "ill_configured_fixture",
            "read_only": 1,
        },
        {
            "fieldname": "ill_configured_product_doctype",
            "fieldtype": "Link",
            "label": "Configured Product DocType",
            "options": "DocType",
            "insert_after": "ill_configured_tape_neon",
            "read_only": 1,
        },
        {
            "fieldname": "ill_configured_product",
            "fieldtype": "Dynamic Link",
            "label": "Configured Product",
            "options": "ill_configured_product_doctype",
            "insert_after": "ill_configured_product_doctype",
            "read_only": 1,
        },
        {
            "fieldname": "ill_configured_item",
            "fieldtype": "Link",
            "label": "Configured Item",
            "options": "Item",
            "insert_after": "ill_configured_product",
            "read_only": 1,
        },
        {
            "fieldname": "ill_bom",
            "fieldtype": "Link",
            "label": "Configured BOM",
            "options": "BOM",
            "insert_after": "ill_configured_item",
            "read_only": 1,
        },
        {
            "fieldname": "ill_configuration_json",
            "fieldtype": "Long Text",
            "label": "Configuration JSON",
            "insert_after": "ill_bom",
            "read_only": 1,
        },
        {
            "fieldname": "ill_bom_override_json",
            "fieldtype": "Long Text",
            "label": "BOM Override JSON",
            "insert_after": "ill_configuration_json",
            "read_only": 1,
        },
        {
            "fieldname": "ill_template_code",
            "fieldtype": "Data",
            "label": "Template Code",
            "insert_after": "ill_bom_override_json",
            "read_only": 1,
        },
        {
            "fieldname": "ill_requested_length_mm",
            "fieldtype": "Int",
            "label": "Requested Length (mm)",
            "insert_after": "ill_template_code",
            "read_only": 1,
        },
        {
            "fieldname": "ill_mfg_length_mm",
            "fieldtype": "Int",
            "label": "Mfg Length (mm)",
            "insert_after": "ill_requested_length_mm",
            "read_only": 1,
        },
        {
            "fieldname": "ill_runs_count",
            "fieldtype": "Int",
            "label": "Runs Count",
            "insert_after": "ill_mfg_length_mm",
            "read_only": 1,
        },
        {
            "fieldname": "ill_total_watts",
            "fieldtype": "Float",
            "label": "Total Watts",
            "insert_after": "ill_runs_count",
            "read_only": 1,
        },
        {
            "fieldname": "ill_finish",
            "fieldtype": "Data",
            "label": "Finish",
            "insert_after": "ill_total_watts",
            "read_only": 1,
        },
        {
            "fieldname": "ill_lens",
            "fieldtype": "Data",
            "label": "Lens",
            "insert_after": "ill_finish",
            "read_only": 1,
        },
        {
            "fieldname": "ill_engine_version",
            "fieldtype": "Data",
            "label": "Engine Version",
            "insert_after": "ill_lens",
            "read_only": 1,
        },
    ]


def execute():
    custom_fields = {
        "Quotation Item": [
            {
                "fieldname": "ill_section_label",
                "fieldtype": "Data",
                "label": "Section / Room",
                "insert_after": "item_code",
                "in_list_view": 1,
            },
            *_configured_product_fields("ill_section_label"),
        ],
        "Sales Order Item": _configured_product_fields("item_code"),
        "Item": [
            {
                "fieldname": "custom_ill_configured_fixture",
                "fieldtype": "Link",
                "label": "Configured Fixture",
                "options": "ilL-Configured-Fixture",
                "insert_after": "description",
                "read_only": 1,
            },
            {
                "fieldname": "custom_ill_configured_tape_neon",
                "fieldtype": "Link",
                "label": "Configured Tape/Neon",
                "options": "ilL-Configured-Tape-Neon",
                "insert_after": "custom_ill_configured_fixture",
                "read_only": 1,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)
    frappe.db.commit()

    print("Added quote/order configurator custom fields")