"""Read-only Cloud/Bench preflight. Contains operational IDs; store privately."""

import frappe

ENGINEERING_REFERENCES = {
	"Linear Fixture": ("ilL-Fixture-Template", "ILL-SH01-SW"),
	"LED Tape": ("ilL-Tape-Neon-Template", "led-hd-sw"),
	"LED Neon": ("ilL-Tape-Neon-Template", "non-pnc-sw"),
	"LED Sheet": ("ilL-LED-Sheet-Template", "Snowfield Static White LED Sheet"),
}


def inventory():
	frappe.only_for("System Manager")
	return {
		"schema_version": 1,
		"site": frappe.local.site,
		"apps": frappe.get_installed_apps(),
		"engineering_references": [
			{
				"family": family,
				"doctype": doctype,
				"name": name,
				"present": bool(frappe.db.exists(doctype, name)),
				"expected_numerical_results": "Awaiting engineering reference manifest",
			}
			for family, (doctype, name) in ENGINEERING_REFERENCES.items()
		],
		"draft_orders_missing_intake": frappe.db.sql(
			"""select so.name, so.customer, so.ill_fixture_schedule
			from `tabSales Order` so where so.docstatus=0 and ifnull(so.ill_fixture_schedule, '')!=''
			and not exists(select 1 from `tabilL-Order-Intake` i where i.sales_order=so.name)""",
			as_dict=True,
		),
		"dealer_desk_access": frappe.db.get_value("Role", "Dealer", "desk_access"),
		"stock_company": frappe.conf.get("ill_portal_stock_company")
		or frappe.db.get_single_value("Global Defaults", "default_company"),
		"warehouses": frappe.get_all(
			"Warehouse",
			filters={"warehouse_name": "ilL-Stores"},
			fields=["name", "company", "disabled", "is_group"],
		),
		"public_project_files": frappe.get_all(
			"File",
			filters={
				"is_private": 0,
				"attached_to_doctype": [
					"in",
					["ilL-Document-Request", "ilL-Project-Fixture-Schedule", "ilL-Export-Job", "Issue"],
				],
			},
			fields=["name", "file_url", "attached_to_doctype", "attached_to_name", "content_hash"],
		),
		"other_spec_references": frappe.get_all(
			"ilL-Child-Fixture-Schedule-Line",
			filters={"manufacturer_type": "OTHER", "spec_sheet": ["like", "/files/%"]},
			fields=["name", "parent", "spec_sheet"],
		),
		"ambiguous_quoted_schedules": frappe.db.sql(
			"""
			select s.name from `tabilL-Project-Fixture-Schedule` s
			where s.status='QUOTED' and not exists
			(select 1 from `tabQuotation Item` qi join `tabQuotation` q on q.name=qi.parent
			where qi.ill_fixture_schedule=s.name and q.docstatus=1)
		""",
			as_dict=True,
		)
		if frappe.get_meta("Quotation Item").has_field("ill_fixture_schedule")
		else {"status": "unknown", "reason": "No quotation-row schedule link"},
		"shared_sheet_items": frappe.db.sql(
			"""
			select configured_item, count(*) as build_count from `tabilL-Configured-LED-Sheet`
			where ifnull(configured_item, '') != '' group by configured_item having count(*) > 1
		""",
			as_dict=True,
		),
		"policy": "Report only. No deletion, role reassignment, status rewrite, or remote publication performed.",
	}
