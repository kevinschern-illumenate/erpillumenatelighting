"""Kit component ``webflow_description`` is now ``component_description`` (label Description,
owner 2026-11-03). Copies existing values on template and Webflow Product rows (same child
table) where the new column is empty. The old column is left in the database, unused.
"""

import frappe

CHILD = "ilL-Child-Webflow-Kit-Component"


def execute():
	if not (
		frappe.db.has_column(CHILD, "webflow_description")
		and frappe.db.has_column(CHILD, "component_description")
	):
		return
	frappe.db.sql(
		f"""update `tab{CHILD}` set component_description = webflow_description
		where ifnull(component_description, '') = '' and ifnull(webflow_description, '') != ''"""
	)
