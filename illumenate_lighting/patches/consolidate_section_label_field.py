# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Consolidate the Section / Room field and add schedule traceability fields.

Two problems are fixed here:

1. The app owns ``ill_section_label`` (fixtures + patches + client scripts) but
   the print formats used to read ``custom_ill_section_label`` — the name Frappe
   gives a field created through the Customize Form UI. Sites therefore ended up
   with two "Section / Room" fields. Any value living in the stray field is
   copied onto the canonical one and the stray Custom Field is removed.

2. ``ill_section_label`` only existed on Quotation Item / Sales Order Item, so
   ``get_mapped_doc`` dropped it at SO → DN → SI (it only copies a custom field
   when the *same* fieldname exists on both doctypes). The field is now created
   on every downstream item doctype, together with ``ill_fixture_type`` and the
   schedule traceability links.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CANONICAL = "ill_section_label"
STRAY = "custom_ill_section_label"

# Every item doctype in the Quotation → SO → DN → SI / PO chain that should
# carry the section grouping.
SECTION_LABEL_DOCTYPES = (
	"Quotation Item",
	"Sales Order Item",
	"Delivery Note Item",
	"Sales Invoice Item",
	"Purchase Order Item",
)

# Fixture Type must use the identical fieldname on every doctype so that
# get_mapped_doc carries it through the whole document chain.
FIXTURE_TYPE_DOCTYPES = (
	"Quotation Item",
	"Sales Order Item",
	"Delivery Note Item",
	"Sales Invoice Item",
)


def _section_label_field():
	return {
		"fieldname": CANONICAL,
		"fieldtype": "Data",
		"label": "Section / Room",
		"insert_after": "item_code",
		"in_list_view": 1,
	}


def _fixture_type_field():
	return {
		"fieldname": "ill_fixture_type",
		"fieldtype": "Data",
		"label": "Fixture Type",
		"insert_after": CANONICAL,
		"in_list_view": 1,
	}


def _schedule_line_id_field():
	return {
		"fieldname": "ill_schedule_line_id",
		"fieldtype": "Data",
		"label": "Schedule Line ID",
		"insert_after": "ill_engine_version",
		"read_only": 1,
	}


def _fixture_schedule_field(insert_after):
	return {
		"fieldname": "ill_fixture_schedule",
		"fieldtype": "Link",
		"label": "Fixture Schedule",
		"options": "ilL-Project-Fixture-Schedule",
		"insert_after": insert_after,
		"read_only": 1,
	}


def _add_fields():
	custom_fields = {dt: [_section_label_field()] for dt in SECTION_LABEL_DOCTYPES}

	for dt in FIXTURE_TYPE_DOCTYPES:
		custom_fields.setdefault(dt, []).append(_fixture_type_field())

	for dt in ("Quotation Item", "Sales Order Item"):
		custom_fields.setdefault(dt, []).append(_schedule_line_id_field())

	custom_fields["Sales Order"] = [_fixture_schedule_field("project")]
	custom_fields["Quotation"] = [_fixture_schedule_field("company")]

	create_custom_fields(custom_fields, update=True)


def _column_exists(doctype, fieldname):
	"""True when the physical column is present on the doctype's table."""
	try:
		return fieldname in frappe.db.get_table_columns(doctype)
	except Exception:
		return False


def _migrate_stray_values():
	"""Copy any data from custom_ill_section_label onto ill_section_label."""
	for doctype in SECTION_LABEL_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		if not _column_exists(doctype, STRAY):
			continue
		if not _column_exists(doctype, CANONICAL):
			continue

		table = f"tab{doctype}"
		frappe.db.sql(
			f"""
			UPDATE `{table}`
			SET `{CANONICAL}` = `{STRAY}`
			WHERE IFNULL(`{CANONICAL}`, '') = ''
			  AND IFNULL(`{STRAY}`, '') != ''
			"""
		)


def _drop_stray_custom_fields():
	"""Remove the duplicate "Section / Room" Custom Field records."""
	stray_fields = frappe.get_all(
		"Custom Field",
		filters={"dt": ["in", list(SECTION_LABEL_DOCTYPES)], "fieldname": STRAY},
		pluck="name",
	)
	for name in stray_fields:
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	for doctype in SECTION_LABEL_DOCTYPES:
		frappe.clear_cache(doctype=doctype)


def execute():
	_add_fields()
	_migrate_stray_values()
	_drop_stray_custom_fields()
	frappe.db.commit()

	print("Consolidated ill_section_label and added fixture-type / schedule traceability fields")
