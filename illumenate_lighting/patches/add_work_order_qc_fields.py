# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add the Work Order QC section and the Configured Fixture link.

manufacturing_generator sets ill_configured_fixture on every Work Order it creates,
and the QC fields give production a place to record the functional test and serial
number. They were only listed in the module-level custom_field.json, which Frappe's
fixture sync never reads, so Work Orders silently dropped the fixture link and had
no QC fields. Existing fields are left as they are, in case a site added them by hand.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Work Order": [
				{
					"fieldname": "ill_section_break",
					"fieldtype": "Section Break",
					"label": "ilLumenate QC",
					"insert_after": "batch_size",
				},
				{
					"fieldname": "ill_functional_test_result",
					"fieldtype": "Select",
					"label": "Functional Test Result",
					"options": "\nPass\nFail",
					"insert_after": "ill_section_break",
				},
				{
					"fieldname": "ill_serial_no",
					"fieldtype": "Data",
					"label": "Serial Number",
					"insert_after": "ill_functional_test_result",
				},
				{
					"fieldname": "ill_column_break",
					"fieldtype": "Column Break",
					"insert_after": "ill_serial_no",
				},
				{
					"fieldname": "ill_configured_fixture",
					"fieldtype": "Link",
					"label": "Configured Fixture",
					"options": "ilL-Configured-Fixture",
					"insert_after": "ill_column_break",
					"read_only": 1,
				},
				{
					"fieldname": "ill_test_notes",
					"fieldtype": "Small Text",
					"label": "Test Notes",
					"insert_after": "ill_configured_fixture",
				},
			],
		},
		update=False,
	)
	frappe.db.commit()
