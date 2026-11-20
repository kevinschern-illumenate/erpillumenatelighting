# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Fill blank Supplier "Purchasing Email" from each supplier's contacts.

POs and RFQs address suppliers by this field (email_templates/recipients.py) and new
email in the purchasing mailbox is matched to a supplier by it. Only blanks are filled.
"""

import frappe

from illumenate_lighting.illumenate_lighting.email_templates.recipients import backfill_purchasing_emails


def execute():
	filled = backfill_purchasing_emails()
	frappe.db.commit()
	return filled
