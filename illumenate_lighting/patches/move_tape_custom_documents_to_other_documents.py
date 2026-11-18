"""Move the Tape/Neon template's site Custom Field ``custom_documents`` to the app's
``other_documents`` table (plan 4.9, D47), then delete the Custom Field.

Both tables use the child doctype ilL-Child-Webflow-Document, so the rows only change
which table they belong to; nothing is copied or lost.
"""

import frappe

TAPE = "ilL-Tape-Neon-Template"
CHILD = "ilL-Child-Webflow-Document"


def execute():
	custom_field = frappe.db.get_value("Custom Field", {"dt": TAPE, "fieldname": "custom_documents"}, "name")
	if not custom_field:
		return
	frappe.db.sql(
		f"""update `tab{CHILD}` set parentfield = 'other_documents'
		where parenttype = %s and parentfield = 'custom_documents'""",
		(TAPE,),
	)
	frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype=TAPE)
