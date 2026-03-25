# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch to add QBO sync fields to core ERPNext doctypes.

This patch adds the following fields to Customer, Supplier, Sales Invoice,
Purchase Invoice, and Payment Entry:
- custom_qbo_id: The QuickBooks Online entity ID
- custom_synced_from: Source identifier for the sync origin
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add QBO sync fields to core ERPNext doctypes."""

    custom_fields = {
        "Customer": [
            {
                "fieldname": "custom_qbo_id",
                "fieldtype": "Data",
                "label": "QBO ID",
                "read_only": 1,
                "insert_after": "customer_name",
            },
            {
                "fieldname": "custom_synced_from",
                "fieldtype": "Data",
                "label": "Synced From",
                "read_only": 1,
                "insert_after": "custom_qbo_id",
            },
        ],
        "Supplier": [
            {
                "fieldname": "custom_qbo_id",
                "fieldtype": "Data",
                "label": "QBO ID",
                "read_only": 1,
                "insert_after": "supplier_name",
            },
            {
                "fieldname": "custom_synced_from",
                "fieldtype": "Data",
                "label": "Synced From",
                "read_only": 1,
                "insert_after": "custom_qbo_id",
            },
        ],
        "Sales Invoice": [
            {
                "fieldname": "custom_qbo_id",
                "fieldtype": "Data",
                "label": "QBO ID",
                "read_only": 1,
                "insert_after": "customer",
            },
            {
                "fieldname": "custom_synced_from",
                "fieldtype": "Data",
                "label": "Synced From",
                "read_only": 1,
                "insert_after": "custom_qbo_id",
            },
        ],
        "Purchase Invoice": [
            {
                "fieldname": "custom_qbo_id",
                "fieldtype": "Data",
                "label": "QBO ID",
                "read_only": 1,
                "insert_after": "supplier",
            },
            {
                "fieldname": "custom_synced_from",
                "fieldtype": "Data",
                "label": "Synced From",
                "read_only": 1,
                "insert_after": "custom_qbo_id",
            },
        ],
        "Payment Entry": [
            {
                "fieldname": "custom_qbo_id",
                "fieldtype": "Data",
                "label": "QBO ID",
                "read_only": 1,
                "insert_after": "payment_type",
            },
            {
                "fieldname": "custom_synced_from",
                "fieldtype": "Data",
                "label": "Synced From",
                "read_only": 1,
                "insert_after": "custom_qbo_id",
            },
        ],
    }

    create_custom_fields(custom_fields, update=True)

    frappe.db.commit()

    print("Added QBO sync fields to Customer, Supplier, Sales Invoice, Purchase Invoice, Payment Entry")
