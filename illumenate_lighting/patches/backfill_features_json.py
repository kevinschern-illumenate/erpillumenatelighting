# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch to backfill NULL/empty `features` values on ilL-Webflow-Product.

When the `features` JSON field was added with default `[]`, existing records
were left with NULL which violates MariaDB's implicit JSON CHECK constraint,
causing a save error (OperationalError 4025).

Run with: bench execute illumenate_lighting.patches.backfill_features_json.execute
"""

import frappe


def execute():
	frappe.db.sql("""
		UPDATE `tabilL-Webflow-Product`
		SET `features` = '[]'
		WHERE `features` IS NULL OR `features` = ''
	""")
	frappe.db.commit()
