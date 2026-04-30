# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Copy the old generic bend diameter into the new side-bend field.

The spec-sheet export split ``minimum_bend_diameter_mm`` into separate
side/top bend fields.  Existing generic values are treated as side-bend values
so previously-entered data remains visible after the DocType migration.
"""

import frappe


def execute():
	for doctype in ("ilL-Fixture-Template", "ilL-Tape-Neon-Template"):
		if not frappe.db.has_column(doctype, "minimum_bend_diameter_mm"):
			continue
		if not frappe.db.has_column(doctype, "minimum_side_bend_diameter_mm"):
			continue

		frappe.db.sql(f"""
			UPDATE `tab{doctype}`
			SET minimum_side_bend_diameter_mm = minimum_bend_diameter_mm
			WHERE minimum_bend_diameter_mm IS NOT NULL
				AND minimum_bend_diameter_mm != 0
				AND (
					minimum_side_bend_diameter_mm IS NULL
					OR minimum_side_bend_diameter_mm = 0
				)
		""")

	frappe.db.commit()