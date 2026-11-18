# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Phase 4: labour minutes on Work Orders, and a default Build operation and workstation.

"Actual Build Minutes" lets the floor record labour time on a Work Order when Job
Cards are not used; the calibration report prefers it over Job Card time. The
"Build" Operation and "Production Floor" Workstation are created only when missing
and are only used once "Add Build Operation to Work Orders" is turned on.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

OPERATION = "Build"
WORKSTATION = "Production Floor"


def execute():
	meta = frappe.get_meta("Work Order")
	create_custom_fields(
		{
			"Work Order": [
				{
					"fieldname": "ill_actual_build_minutes",
					"fieldtype": "Float",
					"label": "Actual Build Minutes",
					"insert_after": "ill_build_points" if meta.has_field("ill_build_points") else meta.fields[-1].fieldname,
					"allow_on_submit": 1,
					"no_copy": 1,
					"description": "Labour minutes (all people) spent building. Used to calibrate build point weights; leave blank if Job Cards record the time.",
				}
			]
		},
		update=True,
	)
	try:
		if not frappe.db.exists("Workstation", WORKSTATION):
			frappe.get_doc({"doctype": "Workstation", "workstation_name": WORKSTATION}).insert(ignore_permissions=True)
		if not frappe.db.exists("Operation", OPERATION):
			frappe.get_doc(
				{
					"doctype": "Operation",
					"name": OPERATION,
					"workstation": WORKSTATION,
					"description": "Building a configured product. Time comes from build points.",
				}
			).insert(ignore_permissions=True)
		settings = "ilL-Production-Settings"
		for field, value in (("build_operation", OPERATION), ("build_workstation", WORKSTATION)):
			if not frappe.db.get_single_value(settings, field):
				frappe.db.set_single_value(settings, field, value)
	except Exception:
		frappe.log_error(title="Build operation defaults could not be created")
