# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch for QBO Payment -> ERPNext Payment Entry reverse sync.

- Adds audit fields to Payment Entry (custom_qbo_event_type,
  custom_qbo_last_synced, custom_qbo_sync_note).
- Creates the "QuickBooks Online" Mode of Payment if missing, mapped to the
  trust account when that account exists.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODE_OF_PAYMENT = "QuickBooks Online"
PAID_TO_ACCOUNT = "1010 - ilLumenate Lighting WA Trust - ilL"


def execute():
    create_custom_fields(
        {
            "Payment Entry": [
                {
                    "fieldname": "custom_qbo_event_type",
                    "fieldtype": "Select",
                    "label": "QBO Event Type",
                    "options": "\nCreate\nUpdate\nDelete\nMerge",
                    "read_only": 1,
                    "no_copy": 1,
                    "allow_on_submit": 1,
                    "depends_on": "custom_qbo_id",
                    "insert_after": "custom_synced_from",
                },
                {
                    "fieldname": "custom_qbo_last_synced",
                    "fieldtype": "Datetime",
                    "label": "QBO Last Synced",
                    "read_only": 1,
                    "no_copy": 1,
                    "allow_on_submit": 1,
                    "depends_on": "custom_qbo_id",
                    "insert_after": "custom_qbo_event_type",
                },
                {
                    "fieldname": "custom_qbo_sync_note",
                    "fieldtype": "Small Text",
                    "label": "QBO Sync Note",
                    "read_only": 1,
                    "no_copy": 1,
                    "allow_on_submit": 1,
                    "depends_on": "custom_qbo_id",
                    "insert_after": "custom_qbo_last_synced",
                },
            ],
        },
        update=True,
    )

    _ensure_mode_of_payment()

    frappe.db.commit()
    print("Added QBO payment sync fields to Payment Entry")


def _ensure_mode_of_payment():
    if frappe.db.exists("Mode of Payment", MODE_OF_PAYMENT):
        return

    mop = frappe.new_doc("Mode of Payment")
    mop.mode_of_payment = MODE_OF_PAYMENT
    mop.enabled = 1
    mop.type = "Bank"

    if frappe.db.exists("Account", PAID_TO_ACCOUNT):
        company = frappe.db.get_value("Account", PAID_TO_ACCOUNT, "company")
        if company:
            mop.append("accounts", {"company": company, "default_account": PAID_TO_ACCOUNT})

    try:
        mop.insert(ignore_permissions=True)
        print(f"Created Mode of Payment '{MODE_OF_PAYMENT}'")
    except Exception:
        # Non-fatal: the account can be mapped manually in Desk later.
        frappe.log_error(title="QBO patch: could not create Mode of Payment")
