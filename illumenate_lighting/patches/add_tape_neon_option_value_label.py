# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Add the custom_value_label field that tape and neon template option rows are read for.

The Webflow product sync (ill_webflow_product.py and template_calculations.py) shows
``row.custom_value_label or <attribute name>`` for an allowed option, but only sites where the
field was added by hand in the Desk had it, so on a fresh site every Check or sync of a tape or
neon product raised AttributeError. The field is created if it is missing; an existing field
is left as it is, in case the site changed it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DOCTYPE = "ilL-Child-Tape-Neon-Allowed-Option"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return
	create_custom_fields(
		{
			DOCTYPE: [
				{
					"fieldname": "custom_value_label",
					"fieldtype": "Data",
					"label": "Custom Value Label",
					"description": "Shown instead of the attribute name for this option (optional)",
					"insert_after": "msrp_adder",
				}
			]
		},
		update=False,
	)
