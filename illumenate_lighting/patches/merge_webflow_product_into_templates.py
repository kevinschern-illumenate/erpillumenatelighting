"""Copy linked Webflow Product content onto product templates (Webflow Product merge, step 3).

This only copies data into hidden fields, so it never fails a migrate: anything that goes
wrong is written to the Error Log and can be re-run from the System Console with
``web_listing_migration.migrate(dry_run=0)``.
"""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_migration import migrate


def execute():
	try:
		report = migrate(dry_run=0)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Webflow Product merge: migration failed")
		return
	problems = [
		row for row in report["listings"] if row["action"] in ("skipped", "failed") or row.get("notes")
	]
	if problems:
		frappe.log_error(
			title="Webflow Product merge: listings to review",
			message=frappe.as_json(problems, indent=1),
		)
