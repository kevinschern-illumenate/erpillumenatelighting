# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Let templates' Other Documents take files again (owner, 2026-11-25).

A Customize Form setting (a Property Setter, production 2026-10-13) made the File column of
ilL-Child-Webflow-Document read-only, so files would not be added on the Webflow Product, which
takes its documents from the template. The template's Other Documents uses the same child
table, so it could not take files either, and it is where they belong. The setting is removed;
the Webflow Product form keeps its File column read-only in its own script.
"""

import frappe

CHILD = "ilL-Child-Webflow-Document"


def execute():
	names = frappe.get_all(
		"Property Setter",
		filters={"doc_type": CHILD, "field_name": "document_file", "property": "read_only"},
		pluck="name",
	)
	for name in names:
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype=CHILD)
