"""Remove the retired ilL-Spec-Driver PS-UNIV-24V-100W-IP66 without touching submitted records.

A pinned LED Sheet build still points at it from its group rows, and those builds are
immutable through the form, so the pointer is cleared with a direct write. The row keeps
compatible_driver (the driver Item), and the build's snapshot JSON and config hash are
unchanged, so the quotes, orders, BOMs and receipts built on it keep working. The driver's
Item is kept: order lines and BOMs still use it.

A reference this patch does not recognise is logged and the spec is left in place, so a
deploy never fails here.
"""

import frappe

DRIVER = "PS-UNIV-24V-100W-IP66"
SPEC = "ilL-Spec-Driver"

# Immutable build history: clear the pointer only.
CLEAR = {"ilL-Child-LED-Sheet-Group", "ilL-Webflow-Product"}
# Standalone catalog records.
DELETE = {"ilL-Rel-Driver-Eligibility"}
# Catalog child rows whose link is mandatory: drop the row.
DROP_ROWS = {"ilL-Child-Driver-Template-Variant", "ilL-Child-Compatible-Driver"}


def references():
	filters = {"fieldtype": "Link", "options": SPEC}
	links = [
		(row.parent, row.fieldname)
		for row in frappe.get_all("DocField", filters=filters, fields=["parent", "fieldname"])
	] + [
		(row.dt, row.fieldname)
		for row in frappe.get_all("Custom Field", filters=filters, fields=["dt", "fieldname"])
	]
	for doctype, field in links:
		if doctype == SPEC or not frappe.db.table_exists(doctype):
			continue
		for name in frappe.get_all(doctype, filters={field: DRIVER}, pluck="name"):
			yield doctype, field, name


def execute():
	if not frappe.db.exists(SPEC, DRIVER):
		return
	refs = list(references())
	unknown = [ref for ref in refs if ref[0] not in CLEAR | DELETE | DROP_ROWS]
	if unknown:
		frappe.log_error(
			title=f"{DRIVER} not removed",
			message=f"Unrecognised references to {SPEC} {DRIVER}, left in place: {unknown}",
		)
		return
	for doctype, field, name in refs:
		if doctype in CLEAR:
			frappe.db.set_value(doctype, name, field, None, update_modified=False)
		elif doctype in DELETE:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		else:
			frappe.db.delete(doctype, {"name": name})
	try:
		frappe.delete_doc(SPEC, DRIVER, ignore_permissions=True)
	except frappe.LinkExistsError:
		frappe.db.rollback()
		frappe.log_error(title=f"{DRIVER} not removed", message=frappe.get_traceback())
		return
	frappe.db.commit()
