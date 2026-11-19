# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Stamp spec and load on existing catalog LED Tape / Neon / Sheet rows.

Drafts and submitted Quotations / Sales Orders are written in place, so their printed
documents show the spec line straight away. A failure is logged and does not stop the
migration: run ``line_power.backfill`` again afterwards.
"""

import frappe


def execute():
	try:
		from illumenate_lighting.illumenate_lighting.api import line_power

		print("Line power backfill:", line_power.backfill())
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Line power backfill failed during migrate")
		print("Line power backfill failed; see Error Log and run line_power.backfill by hand.")
