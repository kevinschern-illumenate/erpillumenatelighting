"""Environment Rating codes that other records keep a copy of.

An Environment Rating's ``code`` is the order code its part numbers carry (Dry 20,
Damp 54, Wet 67, and later Wet+ 68). Two places store a copy:

- LED Sheet templates, on each Environment Rating option row (``option_code``),
  which the Sheet part number and panel matching read.
- Fixture Template Part Number Builders, in the Dry/Wet section exported to the
  spec-sheet ordering guide.

These helpers keep both copies equal to the rating.
"""

import frappe

ENVIRONMENT_RATING = "ilL-Attribute-Environment Rating"
SHEET_TEMPLATE = "ilL-LED-Sheet-Template"
FIXTURE_TEMPLATE = "ilL-Fixture-Template"


def sync_sheet_template(doc) -> bool:
	"""Give each Environment Rating option on an LED Sheet template its rating's current code."""
	changed = False
	for row in doc.get("allowed_options") or []:
		if row.option_type != "Environment Rating" or not row.attribute_link:
			continue
		code = frappe.db.get_value(ENVIRONMENT_RATING, row.attribute_link, "code")
		if code and row.option_code != code:
			row.option_code = code
			changed = True
	return changed


def propagate(environment_rating: str | None = None) -> list[str]:
	"""Re-sync the records that copy Environment Rating codes; return the ones that failed to save.

	With *environment_rating*, only templates that offer that rating are visited.
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_fixture_template.ill_fixture_template import (
		sync_environment_section,
	)

	sheet_filters = {"parenttype": SHEET_TEMPLATE, "option_type": "Environment Rating"}
	fixture_filters = {"parenttype": FIXTURE_TEMPLATE, "option_type": "Environment Rating"}
	if environment_rating:
		sheet_filters["attribute_link"] = environment_rating
		fixture_filters["environment_rating"] = environment_rating
	sheets = set(frappe.get_all("ilL-Child-LED-Sheet-Allowed-Option", filters=sheet_filters, pluck="parent"))
	# Only builders that already have a Dry/Wet section; Populate fills empty ones.
	fixtures = set(
		frappe.get_all("ilL-Child-Template-Allowed-Option", filters=fixture_filters, pluck="parent")
	) & set(
		frappe.get_all(
			"ilL-Child-PN-Builder-Row",
			filters={"parenttype": FIXTURE_TEMPLATE, "section_name": "Dry/Wet"},
			pluck="parent",
		)
	)

	failed = []
	for doctype, names, sync in (
		(SHEET_TEMPLATE, sheets, sync_sheet_template),
		(FIXTURE_TEMPLATE, fixtures, sync_environment_section),
	):
		for name in sorted(names):
			try:
				doc = frappe.get_doc(doctype, name)
				if sync(doc):
					doc.save(ignore_permissions=True)
			except Exception:
				frappe.log_error(title="Environment Rating code sync", message=frappe.get_traceback())
				failed.append(f"{doctype} {name}")
	return failed
