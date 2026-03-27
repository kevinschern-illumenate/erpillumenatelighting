# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch to make Purchase Order "Required By" (schedule_date) field optional.

This patch sets reqd=0 on schedule_date for both:
- Purchase Order (parent)
- Purchase Order Item (child table)

Rollback Note:
- Delete the two Property Setter records via Frappe UI to revert:
  /app/property-setter?doctype=Purchase+Order
  /app/property-setter?doctype=Purchase+Order+Item
"""

from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    """Make schedule_date optional on Purchase Order and Purchase Order Item."""

    make_property_setter(
        "Purchase Order",
        "schedule_date",
        "reqd",
        "0",
        "Check",
    )

    make_property_setter(
        "Purchase Order Item",
        "schedule_date",
        "reqd",
        "0",
        "Check",
    )
