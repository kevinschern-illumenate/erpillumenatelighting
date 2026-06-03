# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add Section / Room field to Sales Order Item (mirrors Quotation Item)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    custom_fields = {
        "Sales Order Item": [
            {
                "fieldname": "ill_section_label",
                "fieldtype": "Data",
                "label": "Section / Room",
                "insert_after": "item_code",
                "in_list_view": 1,
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)
    frappe.db.commit()

    print("Added ill_section_label to Sales Order Item")
