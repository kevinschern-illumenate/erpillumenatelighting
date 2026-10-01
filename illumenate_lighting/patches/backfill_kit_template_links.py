"""Fill missing kit forward links without regenerating editorial product options."""

import frappe


def execute():
	for row in frappe.get_all(
		"ilL-Extrusion-Kit-Template",
		filters={"webflow_product": ["is", "set"]},
		fields=["name", "webflow_product"],
	):
		current = frappe.db.get_value("ilL-Webflow-Product", row.webflow_product, "kit_template")
		if not current:
			frappe.db.set_value("ilL-Webflow-Product", row.webflow_product, "kit_template", row.name)
		elif current != row.name:
			frappe.log_error(
				title="Kit template link conflict", message=f"{row.webflow_product}: {current} / {row.name}"
			)
