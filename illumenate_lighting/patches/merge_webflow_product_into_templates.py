"""Copy linked Webflow Product content onto product templates (Webflow Product merge, step 3)."""

import frappe

from illumenate_lighting.illumenate_lighting.web_listing_migration import migrate


def execute():
	report = migrate(dry_run=0)
	problems = [row for row in report["listings"] if row["action"] == "skipped" or row.get("notes")]
	if problems:
		frappe.log_error(
			title="Webflow Product merge: listings to review",
			message=frappe.as_json(problems, indent=1),
		)
