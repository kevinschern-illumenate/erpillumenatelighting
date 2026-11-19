# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Stamp spec and load on existing catalog LED Tape / Neon / Sheet rows.

Drafts and submitted Quotations / Sales Orders are written in place, so their printed
documents show the spec line straight away. A failure is logged and does not stop the
migration: run ``line_power.backfill`` again afterwards. The stamped and failed row
counts are printed, so rows that could not be written show in the migrate output.
"""

import frappe


def execute():
	try:
		from illumenate_lighting.illumenate_lighting.api import line_power

		counts = line_power.backfill()
		print("Line power backfill:", counts)
		failed = sum(count.get("failed", 0) for count in counts.values() if isinstance(count, dict))
		if failed:
			print(
				f"Line power backfill: {failed} rows failed; see Error Log and run line_power.backfill by hand."
			)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Line power backfill failed during migrate")
		print("Line power backfill failed; see Error Log and run line_power.backfill by hand.")
