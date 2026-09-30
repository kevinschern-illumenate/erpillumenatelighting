"""Copy exact source-row build evidence to new fulfillment/accounting documents."""

import frappe

FIELDS = (
	"additional_notes",
	"ill_configurator_request",
	"ill_section_label",
	"ill_fixture_type",
	"ill_fixture_schedule",
	"ill_schedule_line_id",
	"ill_product_type",
	"ill_configured_fixture",
	"ill_configured_tape_neon",
	"ill_configured_led_sheet",
	"ill_configured_group",
	"ill_configured_product_doctype",
	"ill_configured_product",
	"ill_configured_item",
	"ill_bom",
	"ill_configuration_json",
	"ill_bom_override_json",
	"ill_template_code",
	"ill_requested_length_mm",
	"ill_mfg_length_mm",
	"ill_runs_count",
	"ill_total_watts",
	"ill_finish",
	"ill_lens",
	"ill_engine_version",
)
# Descriptive text any row may carry; the other fields mark a configured build.
DESCRIPTIVE = frozenset(("additional_notes", "ill_section_label", "ill_fixture_type", "ill_product_type"))
LINEAGE = tuple(field for field in FIELDS if field not in DESCRIPTIVE)


def _carries_lineage(row):
	return any(row.get(field) for field in LINEAGE)


def validate(doc, method=None):
	"""Copy build evidence onto configured fulfillment rows from their exact source row.

	Rows where neither side carries configured lineage keep native ERPNext stock and
	invoicing behavior. Lineage on either side is enforced, so a value typed onto a
	plain row is still replaced from its source.
	"""
	if doc.docstatus == 2:
		return
	sources = {}
	checked = set()
	for row in doc.get("items") or []:
		if doc.doctype == "Sales Invoice" and row.get("dn_detail"):
			doctype, name, source_name = "Delivery Note", row.get("delivery_note"), row.dn_detail
		else:
			doctype, name, source_name = (
				"Sales Order",
				row.get("against_sales_order") or row.get("sales_order"),
				row.get("so_detail"),
			)
		if not name or not source_name:
			continue
		key = (doctype, name)
		if key not in sources:
			source = frappe.get_doc(doctype, name)
			sources[key] = source, {item.name: item for item in source.get("items") or []}
		source, rows = sources[key]
		original = rows.get(source_name)
		if not _carries_lineage(row) and not (original and _carries_lineage(original)):
			continue
		if key not in checked:
			if not frappe.has_permission(doctype, "read", doc=source):
				frappe.throw("Source transaction access required", frappe.PermissionError)
			if source.customer != doc.customer or source.company != doc.company or source.docstatus != 1:
				frappe.throw("Fulfillment source must be submitted for the same customer and company")
			checked.add(key)
		if not original or original.item_code != row.item_code:
			frappe.throw("The source row does not match this fulfillment Item")
		for field in FIELDS:
			if row.meta.has_field(field):
				row.set(field, original.get(field))
