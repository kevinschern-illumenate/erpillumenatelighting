# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Add ``auto_populate_configurator_options`` Check field to ilL-Webflow-Product.

The column itself is created by the updated doctype JSON during model sync.
This patch backfills the value to ``1`` on all existing records so their
current behaviour (configurator options auto-rebuilt from the linked template
on every save) is preserved. New, intentionally-unchecked records are created
after this patch runs and are therefore unaffected.
"""

import frappe


def execute():
	if not frappe.db.has_column("ilL-Webflow-Product", "auto_populate_configurator_options"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabilL-Webflow-Product`
		SET auto_populate_configurator_options = 1
		WHERE auto_populate_configurator_options IS NULL
		"""
	)
