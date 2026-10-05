"""Installed-site checks for the September 2026 migration repair.

Run on a migrated test site with bench run-tests --module
illumenate_lighting.illumenate_lighting.api.test_migration_assets.
The local portal_unit suite checks packaging without Frappe; these tests check
real controller imports, installed records and Frappe link validation.
"""

import ast
import hashlib
import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.model.base_document import get_controller
from frappe.model.document import Document

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from illumenate_lighting import portal_workspace


class TestMigrationAssets(IntegrationTestCase):
	def test_commercial_setup_extends_legacy_choices_without_resetting_site_settings(self):
		from illumenate_lighting.patches.b2b_commercial_schema import execute

		field = frappe.get_doc("Custom Field", {"dt": "Sales Order Item", "fieldname": "ill_product_type"})
		original_options, original_label = field.options, field.label
		count = frappe.db.count("Custom Field", {"dt": "Sales Order Item"})
		try:
			field.options = "\nLinear Fixture\nLED Tape\nLED Neon\nSite Product"
			field.label = "Site Product Family"
			field.save(ignore_permissions=True)
			execute()
			execute()
			field.reload()
			self.assertEqual(field.options.split("\n")[-3:], ["Site Product", "COB Tape", "LED Sheet"])
			self.assertEqual(field.label, "Site Product Family")
			self.assertEqual(frappe.db.count("Custom Field", {"dt": "Sales Order Item"}), count)
		finally:
			field.options, field.label = original_options, original_label
			field.save(ignore_permissions=True)

	def test_literal_portal_query_fields_have_physical_columns(self):
		app = Path(frappe.get_app_path("illumenate_lighting"))
		paths = [*(app / "illumenate_lighting/portal").glob("*.py"), *(app / "templates/pages").glob("*.py")]
		paths.extend(app / "illumenate_lighting/api" / filename for filename in (
			"configurator_engine.py", "tape_neon_configurator.py", "led_sheet_configurator.py",
			"extrusion_kit_configurator.py", "webflow_configurator.py", "desk_configurator.py",
			"configured_product_builder.py", "portal.py",
		))
		columns = {}
		for path in paths:
			for call in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
				if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
					continue
				if ast.unparse(call.func) not in ("frappe.get_all", "frappe.get_list", "frappe.db.get_value"):
					continue
				if not call.args or not isinstance(call.args[0], ast.Constant) or not isinstance(call.args[0].value, str):
					continue
				doctype = call.args[0].value
				fields = next((arg.value for arg in call.keywords if arg.arg in ("fields", "fieldname", "pluck")), None)
				if fields is None and call.func.attr == "get_value" and len(call.args) > 2:
					fields = call.args[2]
				try:
					fields = ast.literal_eval(fields)
				except (TypeError, ValueError):
					continue  # Dynamic selections and SQL expressions need runtime coverage.
				if isinstance(fields, str):
					fields = [fields]
				if not isinstance(fields, (list, tuple)):
					continue
				if doctype not in columns:
					columns[doctype] = set(frappe.db.get_table_columns(doctype))
				for field in fields:
					if isinstance(field, str) and field.isidentifier():
						with self.subTest(path=str(path.relative_to(app)), line=call.lineno, doctype=doctype, field=field):
							self.assertIn(field, columns[doctype])

	def test_commercial_lineage_fields_have_physical_columns(self):
		from illumenate_lighting.illumenate_lighting.portal.commercial_lineage import FIELDS

		for doctype in ("Quotation Item", "Sales Order Item", "Delivery Note Item", "Sales Invoice Item"):
			with self.subTest(doctype=doctype):
				meta = frappe.get_meta(doctype)
				self.assertFalse(set(FIELDS) - set(frappe.db.get_table_columns(doctype)))
				for field in FIELDS:
					self.assertTrue(meta.has_field(field), (doctype, field))
				self.assertIn("LED Sheet", meta.get_field("ill_product_type").options.split("\n"))
				self.assertEqual(meta.get_field("ill_configured_led_sheet").options, "ilL-Configured-LED-Sheet")
				# Query even an empty table so a missing physical column is caught.
				frappe.get_all(doctype, fields=list(FIELDS), limit_page_length=1)
		for doctype in ("Quotation", "Sales Order"):
			self.assertIn("ill_fixture_schedule", frappe.db.get_table_columns(doctype))

	def test_print_format_lookups_have_physical_columns(self):
		# Print formats render from disk before migrate adds columns, so a lookup of a
		# field that only exists in an unsynced fixture fails at print time.
		lookup = re.compile(r"frappe\.db\.get_value\(\s*'([^']+)'\s*,[^,]+,\s*(\[[^\]]*\]|'[^']*')")
		app = Path(frappe.get_app_path("illumenate_lighting"))
		for path in (app / "illumenate_lighting/print_format").glob("*/*.html"):
			for doctype, fields in lookup.findall(path.read_text(encoding="utf-8")):
				fields = ast.literal_eval(fields)
				for field in [fields] if isinstance(fields, str) else fields:
					with self.subTest(path=path.name, doctype=doctype, field=field):
						self.assertIn(field, frappe.db.get_table_columns(doctype))

	def test_staff_queue_count_runs_on_the_installed_framework(self):
		from illumenate_lighting.illumenate_lighting.portal.queues import _count

		self.assertEqual(_count("User", {"name": "Administrator"}), 1)

	def test_portal_pages_render_with_an_existing_order(self):
		from frappe.website.serve import get_response
		from werkzeug.wrappers import Request

		# A read-only route fixture, not a submitted commercial transaction.
		# The previous empty-site checks skipped the Sales Order Item query.
		order = frappe.get_doc({
			"doctype": "Sales Order", "name": "ILL-PORTAL-SCHEMA-TEST", "customer": "Schema Test",
			"customer_name": "Schema Test", "status": "Draft", "docstatus": 0,
			"transaction_date": "2026-09-28", "delivery_date": "2026-10-01",
			"currency": "USD", "grand_total": 10, "total": 10, "total_qty": 1,
		})
		order.db_insert()
		line = frappe.get_doc({
			"doctype": "Sales Order Item", "name": "ILL-PORTAL-SCHEMA-LINE", "parent": order.name,
			"parenttype": "Sales Order", "parentfield": "items", "item_code": "Schema Item",
			"item_name": "Schema Item", "qty": 1, "rate": 10, "amount": 10, "uom": "Nos",
			"conversion_factor": 1,
		})
		line.db_insert()
		try:
			for path, args in (("portal", {}), ("portal/orders", {}), (f"portal/orders/{order.name}", {"order": order.name})):
				with (
					self.subTest(path=path),
					patch.object(frappe.local, "request", Request.from_values(path="/" + path), create=True),
					patch.object(frappe.local, "form_dict", frappe._dict(args)),
				):
					response = get_response(path)
					self.assertEqual(response.status_code, 200)
					self.assertIn(order.name, response.get_data(as_text=True))
		finally:
			frappe.db.delete("Sales Order Item", {"name": line.name})
			frappe.db.delete("Sales Order", {"name": order.name})

	def test_populated_schedule_renders_when_stock_scope_is_unavailable(self):
		from frappe.website.serve import get_response
		from werkzeug.wrappers import Request

		from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
			_build_kit_stock_result,
		)

		# Read-model fixtures exercise the real queries and template, without
		# creating a commercial transaction or changing the site's stock setup.
		prefix = "ILL-STOCK-" + frappe.generate_hash(length=10)
		definitions = [
			{"doctype": "Item", "name": prefix, "item_code": prefix, "item_name": "Stock Test Accessory", "stock_uom": "Nos"},
			{"doctype": "ilL-Configured-Fixture", "name": prefix, "config_hash": prefix,
			 "display_part_number": "Stock Test Fixture", "profile_item": prefix, "build_schema_version": 1,
			 "manufacturable_overall_length_mm": 1000, "include_power_supply": 0},
			{"doctype": "ilL-Project", "name": prefix, "project_name": "Stock Test Project", "customer": prefix, "owner_customer": prefix},
			{"doctype": "ilL-Project-Fixture-Schedule", "name": prefix, "schedule_name": "Stock Test Schedule", "ill_project": prefix, "customer": prefix, "status": "DRAFT"},
			{"doctype": "ilL-Child-Fixture-Schedule-Line", "name": prefix, "parent": prefix,
			 "parenttype": "ilL-Project-Fixture-Schedule", "parentfield": "lines", "idx": 1,
			 "line_id": "A1", "manufacturer_type": "ACCESSORY", "qty": 2,
			 "accessory_item": prefix, "accessory_item_name": "Stock Test Accessory"},
			{"doctype": "ilL-Child-Fixture-Schedule-Line", "name": prefix + "-fixture", "parent": prefix,
			 "parenttype": "ilL-Project-Fixture-Schedule", "parentfield": "lines", "idx": 2,
			 "line_id": "F1", "manufacturer_type": "ILLUMENATE", "qty": 3,
			 "product_type": "Linear Fixture", "configured_fixture": prefix},
		]
		inserted = []
		try:
			for definition in definitions:
				doc = frappe.get_doc(definition)
				doc.db_insert()
				inserted.append(doc)
			path = f"portal/schedules/{prefix}"
			with (
				patch.dict(frappe.conf, {"ill_portal_stock_company": prefix}),
				patch.object(frappe.local, "_ill_portal_warehouses", None, create=True),
				patch.object(frappe.local, "request", Request.from_values(path="/" + path), create=True),
				patch.object(frappe.local, "form_dict", frappe._dict(schedule=prefix)),
				patch.object(frappe.local, "message_log", []),
			):
				response = get_response(path)
				self.assertEqual(response.status_code, 200)
				html = response.get_data(as_text=True)
				self.assertIn("Stock Test Schedule", html)
				self.assertIn("Stock Test Accessory", html)
				self.assertIn("Stock Test Fixture", html)
				self.assertIn("Stock availability unavailable", html)
				self.assertNotIn("No lines fully available now", html)
				self.assertNotIn("All Parts Available Now", html)
				# Edit Config must address the saved line, never a serialized null.
				self.assertIn(f"line_key={prefix}-fixture", html)
				self.assertNotIn("line_key=None", html)
				kit = _build_kit_stock_result([("Profile", prefix, 1)])
				self.assertEqual(kit["availability"], "unknown")
				self.assertEqual(kit["components"], [])
				self.assertEqual(frappe.local.message_log, [])
		finally:
			for doc in reversed(inserted):
				frappe.db.delete(doc.doctype, {"name": doc.name})

	def test_stock_queries_only_count_the_approved_company_and_warehouse(self):
		from illumenate_lighting.illumenate_lighting.api.pricing_utils import (
			_bulk_stock_query,
			batch_stock_for_schedule_lines,
		)

		prefix = "ILL-STOCK-" + frappe.generate_hash(length=10)
		inserted = []
		try:
			for index, (company, warehouse_name, disabled, is_group) in enumerate([
				(prefix, "ilL-Stores", 0, 0),
				(prefix + "-other", "ilL-Stores", 0, 0),
				(prefix, "Other Stores", 0, 0),
				(prefix, "ilL-Stores", 1, 0),
				(prefix, "ilL-Stores", 0, 1),
			]):
				warehouse = frappe.get_doc({
					"doctype": "Warehouse", "name": f"{prefix}-{index}", "company": company,
					"warehouse_name": warehouse_name, "disabled": disabled, "is_group": is_group,
				})
				warehouse.db_insert()
				inserted.append(warehouse)
				stock = frappe.get_doc({
					"doctype": "Bin", "name": f"{prefix}-{index}", "warehouse": warehouse.name,
					"item_code": prefix, "actual_qty": 7 if index == 0 else 1000,
					"reserved_qty": 4 if index == 0 else 0,
				})
				stock.db_insert()
				inserted.append(stock)
			with (
				patch.dict(frappe.conf, {"ill_portal_stock_company": prefix}),
				patch.object(frappe.local, "_ill_portal_warehouses", None, create=True),
			):
				self.assertEqual(_bulk_stock_query([prefix, prefix + "-empty"]), {prefix: 3, prefix + "-empty": 0})
				result = batch_stock_for_schedule_lines([
					{"key": key, "qty": 2, "components": [("Accessory", prefix, 1, "Nos")]}
					for key in (1, 2)
				])
				self.assertEqual(result["scope"]["warehouse_scope"], [prefix + "-0"])
				self.assertTrue(result["lines"][1]["all_in_stock"])
				self.assertFalse(result["lines"][2]["all_in_stock"])
				self.assertEqual(result["shortages"][0]["shortage"], 1)
		finally:
			for doc in reversed(inserted):
				frappe.db.delete(doc.doctype, {"name": doc.name})

	def test_shipped_doctypes_survive_orphan_cleanup(self):
		folder = Path(frappe.get_app_path("illumenate_lighting", "illumenate_lighting", "doctype"))
		for path in folder.glob("*/*.json"):
			name = json.loads(path.read_text(encoding="utf-8"))["name"]
			with self.subTest(doctype=name):
				self.assertTrue(frappe.db.exists("DocType", name))
				self.assertTrue(issubclass(get_controller(name), Document))

	def test_workspace_and_number_card_links_resolve(self):
		fixture = Path(frappe.get_app_path("illumenate_lighting", "fixtures", "number_card.json"))
		for definition in json.loads(fixture.read_text(encoding="utf-8")):
			with self.subTest(card=definition["name"]):
				card = frappe.get_doc("Number Card", definition["name"])
				card.save(ignore_permissions=True)
		workspace = frappe.get_doc("Workspace", "ilLumenate Lighting")
		# Exercise the complete pipeline, including mandatory/select/length
		# validation and Workspace.validate(), not just foreign-key checks.
		workspace.save(ignore_permissions=True)

	def test_legacy_pending_backups_pass_a_real_workspace_save(self):
		if not frappe.get_meta("Workspace").has_field("type"):
			self.skipTest("Workspace.type is a v16 field")
		for kind in ("absent", None, ""):
			with self.subTest(type=kind), tempfile.TemporaryDirectory() as temporary:
				directory = Path(temporary)
				site = frappe.get_doc("Workspace", "ilLumenate Lighting").as_dict()
				if kind == "absent":
					site.pop("type", None)
				else:
					site["type"] = kind
				blocks = json.loads(site["content"])
				blocks.append(
					{
						"id": "migration-test-site-block",
						"type": "header",
						"data": {"text": "Site customizations"},
					}
				)
				site["content"] = json.dumps(blocks)
				data = frappe.as_json(site).encode()
				name = hashlib.sha256(data).hexdigest() + ".json"
				(directory / name).write_bytes(data)
				(directory / "pending.json").write_text(json.dumps({"backup": name}), encoding="utf-8")
				frappe.db.set_value("Workspace", "ilLumenate Lighting", "type", None)
				with self.assertRaises(frappe.MandatoryError):
					frappe.get_doc("Workspace", "ilLumenate Lighting").save(ignore_permissions=True)
				with (
					patch.object(portal_workspace, "_directory", return_value=directory),
					patch.object(frappe.db, "after_commit") as after_commit,
				):
					portal_workspace.after_migrate()
					workspace = frappe.get_doc("Workspace", "ilLumenate Lighting")
					self.assertEqual(workspace.type, "Workspace")
					self.assertIn("Site customizations", workspace.content)
					self.assertTrue((directory / "pending.json").exists())
					self.assertEqual((directory / name).read_bytes(), data)
					after_commit.add.call_args.args[0]()
					self.assertFalse((directory / "pending.json").exists())

	def test_all_imported_assets_pass_framework_field_validation(self):
		module = Path(frappe.get_app_path("illumenate_lighting", "illumenate_lighting"))
		paths = list(Path(frappe.get_app_path("illumenate_lighting", "fixtures")).glob("*.json"))
		for folder in ("doctype", "workspace", "page", "report", "print_format"):
			paths.extend((module / folder).glob("*/*.json"))
		for path in paths:
			data = json.loads(path.read_text(encoding="utf-8"))
			for definition in data if isinstance(data, list) else [data]:
				with self.subTest(doctype=definition["doctype"], name=definition["name"]):
					doc = frappe.get_doc(definition["doctype"], definition["name"])
					doc._validate_mandatory()
					for row in [doc, *doc.get_all_children()]:
						row._validate_selects()
						row._validate_length()
						row._validate_data_fields()
						row._validate_code_fields()
