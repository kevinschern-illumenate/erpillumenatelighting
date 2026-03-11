# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Backfill ``template_type`` on existing ilL-Rel-Mounting-Accessory-Map and
ilL-Rel-Driver-Eligibility records.

All pre-existing records were linked to ilL-Fixture-Template, so we set
``template_type = 'ilL-Fixture-Template'`` for any rows where the field is
NULL or empty.
"""

import frappe


def execute():
    for doctype in (
        "ilL-Rel-Mounting-Accessory-Map",
        "ilL-Rel-Driver-Eligibility",
    ):
        table = frappe.qb.DocType(doctype)
        (
            frappe.qb.update(table)
            .set(table.template_type, "ilL-Fixture-Template")
            .where(
                (table.template_type.isnull()) | (table.template_type == "")
            )
            .run()
        )

    frappe.db.commit()
