"""Re-sync Fixture Template Part Number Builders to the current Environment Rating codes.

Environment Ratings moved from I/O (indoor/outdoor) to IP-based order codes
(Dry 20 / Damp 54 / Wet 67).  The Part Number Builder copies those codes into
its Dry/Wet section, which feeds the spec-sheet ordering-guide export, and
"Populate Part Number Builder" used to leave a populated section alone, so
templates populated before the change kept exporting I/O.
"""

import frappe

from illumenate_lighting.illumenate_lighting.doctype.ill_fixture_template.ill_fixture_template import (
	sync_environment_section,
)


def execute():
	templates = frappe.get_all(
		"ilL-Child-PN-Builder-Row",
		filters={"parenttype": "ilL-Fixture-Template", "section_name": "Dry/Wet"},
		pluck="parent",
	)
	for name in sorted(set(templates)):
		try:
			doc = frappe.get_doc("ilL-Fixture-Template", name)
			if sync_environment_section(doc):
				doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="sync_environment_codes_in_part_number_builder",
				message=frappe.get_traceback(),
			)
	frappe.db.commit()
