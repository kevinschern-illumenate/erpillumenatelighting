"""Installed-site catalog transactions, real permissions, and migration regressions.

These endpoints commit their own audit receipts, so every test explicitly removes
its unique data rather than relying on the test runner's final rollback.
"""

import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.api import catalog_builder as service
from illumenate_lighting.illumenate_lighting.catalog_authoring.catalog import identity
from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import cached_schema
from illumenate_lighting.illumenate_lighting.doctype.ill_extrusion_kit_template.ill_extrusion_kit_template import (
	ilLExtrusionKitTemplate,
)
from illumenate_lighting.portal_staff_permissions import apply_staff_permissions


class TestCatalogImport(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.prefix = "ZZTEST-" + frappe.generate_hash(length=8)
		self.user = self.prefix.lower() + "@example.invalid"
		self.seeds, self.created = [], []
		self.addCleanup(self.cleanup_catalog)
		self.seed(
			"User",
			email=self.user,
			first_name="Catalog transaction test",
			send_welcome_email=0,
			user_type="System User",
			roles=[{"role": "ilL Catalog Publisher"}],
		)
		self.schema = cached_schema()
		self.catalog = json.loads(
			(
				Path(__file__).resolve().parents[3] / "tools/yaml_builder_ui/src/catalog-examples.json"
			).read_text()
		)["extrusion-kit"]
		self.catalog["series_name"] = self.prefix
		names = {}
		for doctype, rows in self.catalog["records"].items():
			for row in rows:
				name = identity(doctype, row, self.schema)
				if self.schema["doctypes"][doctype]["autoname"].startswith("field:"):
					names[doctype, name] = f"{self.prefix}-{name}"
		for doctype, values in self.catalog["external_links"].items():
			for index, value in enumerate(values):
				name = f"{self.prefix}-{value}"
				if doctype == "UOM":
					self.seed(doctype, uom_name=name)
				elif doctype == "Item Group":
					parent = frappe.db.get_value("Item Group", {"is_group": 1}, "name")
					self.seed(doctype, item_group_name=name, parent_item_group=parent, is_group=0)
				else:
					field = self.schema["doctypes"][doctype]["autoname"].removeprefix("field:")
					values = {"code": f"Z{self.prefix[-5:]}{index}", field: name}
					for required in self.schema["doctypes"][doctype]["fields"]:
						if required.get("reqd") and required["fieldtype"] == "Data":
							values.setdefault(required["fieldname"], name)
					self.seed(doctype, **values)
				names[doctype, value] = name

		def rename(doctype, row):
			autoname = self.schema["doctypes"][doctype].get("autoname", "")
			if autoname.startswith("field:"):
				field = autoname[6:]
				row[field] = names.get((doctype, row.get(field)), row.get(field))
			for field in self.schema["doctypes"][doctype]["fields"]:
				key = field["fieldname"]
				if field["fieldtype"] in {"Table", "Table MultiSelect"}:
					for child in row.get(key, []):
						rename(field["options"], child)
				elif field["fieldtype"] == "Link" and key in row:
					row[key] = names.get((field["options"], row[key]), row[key])

		for doctype, rows in self.catalog["records"].items():
			for row in rows:
				rename(doctype, row)
		self.catalog["external_links"] = {
			doctype: [names[doctype, value] for value in values]
			for doctype, values in self.catalog["external_links"].items()
		}
		self.catalog["records"]["ilL-Attribute-Series"][0]["code"] = self.prefix[-8:]
		self.catalog["records"]["ilL-Attribute-LED Package"] = [
			{"name": self.prefix + "-LED", "code": self.prefix[-8:], "spectrum_type": "Static White"}
		]
		price_list = self.seed(
			"Price List", price_list_name=self.prefix + "-Prices", currency="USD", selling=1
		)
		self.catalog["external_links"]["Price List"] = [price_list.name]
		self.catalog["external_links"]["Currency"] = ["USD"]
		self.catalog["records"]["Item Price"] = [
			{
				"item_code": self.catalog["records"]["Item"][0]["item_code"],
				"price_list": price_list.name,
				"currency": "USD",
				"price_list_rate": 12.5,
			}
		]
		# fixtures must survive the endpoint's dry-run rollback.
		frappe.db.commit()  # nosemgrep
		frappe.set_user(self.user)

	def seed(self, doctype, **values):
		doc = frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
		self.seeds.append((doctype, doc.name))
		return doc

	def run_catalog(self, mode="Check", value=None, digest=None):
		value = self.catalog if value is None else value
		result = service.check(value) if mode == "Check" else service.import_catalog(value, digest)
		self.created.extend((row["doctype"], row["name"]) for row in result["results"] if row["name"])
		return result

	def assert_catalog_absent(self):
		for doctype, rows in self.catalog["records"].items():
			for row in rows:
				if name := identity(doctype, row, self.schema):
					self.assertFalse(frappe.db.exists(doctype, name), (doctype, name))
		self.assertFalse(
			frappe.db.exists("Item Price", {"price_list": self.catalog["external_links"]["Price List"][0]})
		)

	def cleanup_catalog(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		logs = frappe.get_all(
			service.AUDIT, filters={"user": self.user}, pluck="name", order_by="creation desc"
		)
		for name in logs:
			frappe.delete_doc(service.AUDIT, name, ignore_permissions=True, force=True)
		for doctype, name in reversed(self.seeds + self.created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		# endpoint commits require durable removal of unique test data.
		frappe.db.commit()  # nosemgrep
		frappe.clear_cache(user=self.user)

	@contextmanager
	def other_connection(self):
		# Frappe's first secondary_connection() calls connect(), which also resets the
		# session user and current connection. Restore both, not only the helper's DB.
		previous, user = frappe.local.db, frappe.session.user
		try:
			with self.secondary_connection():
				yield
		finally:
			frappe.local.db = previous
			frappe.set_user(user)

	def test_check_rolls_back_parent_child_and_hook_writes(self):
		result = self.run_catalog()
		self.assertEqual(result["status"], "Passed", result)
		self.assertTrue(all(row["status"] == "checked" for row in result["results"]))
		self.assert_catalog_absent()
		with self.other_connection():
			self.assert_catalog_absent()
			self.assertTrue(frappe.db.exists(service.AUDIT, result["log"]))
		self.assertTrue(frappe.has_permission(service.AUDIT, "read"))
		self.assertFalse(frappe.has_permission(service.AUDIT, "create"))
		self.assertFalse(frappe.has_permission(service.AUDIT, "write"))
		self.assertFalse(frappe.has_permission(service.AUDIT, "delete"))
		self.assertTrue(all(row["batch"] >= 1 for row in result["results"]))

	def test_import_commits_all_records_and_replay_fails_validation(self):
		checked = self.run_catalog()
		self.assertEqual(checked["status"], "Passed", checked)
		result = self.run_catalog("Import", digest=checked["catalog_hash"])
		self.assertEqual(result["status"], "Imported", result)
		count = sum(map(len, self.catalog["records"].values()))
		self.assertEqual(result["summary"]["created"], count)
		with self.other_connection():
			for row in result["results"]:
				self.assertTrue(frappe.db.exists(row["doctype"], row["name"]), row)
		log = frappe.get_doc(service.AUDIT, result["log"])
		self.assertEqual(log.created_count, count)
		self.assertEqual(log.check_log, checked["log"])
		prompt = next(row for row in result["results"] if row["doctype"] == "ilL-Attribute-LED Package")
		self.assertEqual(prompt["name"], self.prefix + "-LED")
		price = next(row for row in result["results"] if row["doctype"] == "Item Price")
		self.assertTrue(price["name"])
		self.assertEqual(price["catalog_name"], "")
		self.assertEqual(frappe.db.get_value("Item Price", price["name"], "price_list_rate"), 12.5)
		self.assertEqual(self.run_catalog("Import", digest=checked["catalog_hash"])["stage"], "validate")

	def test_broken_link_fails_check_and_cannot_authorize_import(self):
		self.catalog["records"]["ilL-Rel-Kit-Lens-Map"][0]["lens_spec"] = self.prefix + "-missing"
		result = self.run_catalog()
		self.assertEqual((result["status"], result["stage"]), ("Failed", "validate"), result)
		self.assertEqual(self.run_catalog("Import", digest=result["catalog_hash"])["status"], "Refused")
		self.assert_catalog_absent()

	def test_user_without_catalog_capability_cannot_run_or_read_history(self):
		frappe.set_user("Guest")
		for endpoint, args in (
			(service.check, (self.catalog,)),
			(service.import_catalog, (self.catalog, "hash")),
			(service.history, ()),
		):
			with self.assertRaises(frappe.PermissionError):
				endpoint(*args)
		self.assertFalse(frappe.db.exists(service.AUDIT, {"user": "Guest", "series_name": self.prefix}))

	def test_changed_expired_or_other_users_check_is_refused(self):
		checked = self.run_catalog()
		self.assertEqual(checked["status"], "Passed", checked)
		changed = deepcopy(self.catalog)
		changed["series_name"] += " edited"
		self.assertEqual(self.run_catalog("Import", changed, checked["catalog_hash"])["stage"], "gate")
		frappe.set_user("Administrator")
		self.assertEqual(self.run_catalog("Import", digest=checked["catalog_hash"])["stage"], "gate")
		# Remove this administrator's refusal receipt in addition to user-scoped cleanup.
		frappe.db.delete(service.AUDIT, {"series_name": self.prefix, "user": "Administrator"})
		frappe.db.set_value(
			service.AUDIT, checked["log"], "creation", frappe.utils.now_datetime() - timedelta(minutes=31)
		)
		# emulate a persisted expired Check.
		frappe.db.commit()  # nosemgrep
		frappe.set_user(self.user)
		self.assertEqual(self.run_catalog("Import", digest=checked["catalog_hash"])["status"], "Refused")

	def test_import_validation_failure_rolls_back_prior_batches(self):
		checked = self.run_catalog()
		self.assertEqual(checked["status"], "Passed", checked)
		with patch.object(
			ilLExtrusionKitTemplate, "validate", side_effect=frappe.ValidationError("Site validation changed")
		):
			result = self.run_catalog("Import", digest=checked["catalog_hash"])
		self.assertEqual(result["status"], "Rolled Back", result)
		self.assertGreater(result["summary"]["skipped"], 0)
		self.assertEqual(result["summary"]["created"], 0)
		self.assert_catalog_absent()
		self.assertTrue(frappe.db.exists(service.AUDIT, result["log"]))

	def test_second_connection_cannot_run_while_site_lock_is_held(self):
		with self.other_connection():
			self.assertEqual(frappe.db.sql("select get_lock(%s, 0)", service._lock_name())[0][0], 1)
		try:
			result = self.run_catalog()
			self.assertEqual((result["status"], result["stage"]), ("Refused", "lock"), result)
		finally:
			with self.other_connection():
				frappe.db.sql("select release_lock(%s)", service._lock_name())

	def test_tracebacks_are_saved_but_hidden_from_publishers(self):
		with patch.object(service, "_existence_map", side_effect=RuntimeError("private detail")):
			result = self.run_catalog()
		self.assertEqual(result["status"], "Error", result)
		doc = frappe.get_doc(service.AUDIT, result["log"])
		self.assertIn("private detail", doc.error_detail)
		doc.apply_fieldlevel_read_permissions()
		self.assertFalse(doc.get("error_detail"))
		frappe.set_user("Administrator")
		self.assertIn("private detail", frappe.get_doc(service.AUDIT, result["log"]).error_detail)

	def test_permission_patch_is_idempotent_and_workspace_has_audit_shortcut(self):
		frappe.set_user("Administrator")
		fields = ["parent", "role", "permlevel", "read", "create", "write", "delete", "export"]
		filters = {"role": ["in", ["System Manager", "All", "Stock User"]]}
		before = frappe.get_all("Custom DocPerm", filters=filters, fields=fields, order_by="name")
		apply_staff_permissions()
		first = frappe.get_all("Custom DocPerm", fields=fields, order_by="name")
		apply_staff_permissions()
		self.assertEqual(first, frappe.get_all("Custom DocPerm", fields=fields, order_by="name"))
		self.assertEqual(
			before, frappe.get_all("Custom DocPerm", filters=filters, fields=fields, order_by="name")
		)
		workspace = frappe.get_doc("Workspace", "ilLumenate Lighting")
		self.assertEqual(
			sum(
				row.label == "Catalog Imports" and row.link_to == service.AUDIT for row in workspace.shortcuts
			),
			1,
		)
		self.assertEqual(sum(row["id"] == "ill_catalog_imports" for row in json.loads(workspace.content)), 1)
		self.assertTrue(
			frappe.db.exists(
				"Patch Log",
				{"patch": "illumenate_lighting.patches.catalog_builder_permissions", "skipped": 0},
			)
		)
		frappe.set_user(self.user)
		for doctype in self.schema["doctypes"]:
			if not self.schema["doctypes"][doctype].get("istable"):
				self.assertTrue(frappe.has_permission(doctype, "create"), doctype)
		for doctype in ("Item", "Item Price", "ilL-Extrusion-Kit-Template"):
			self.assertFalse(frappe.has_permission(doctype, "delete"), doctype)
		for doctype in ("Supplier", "Price List", "Currency"):
			self.assertTrue(frappe.has_permission(doctype, "read"), doctype)
			self.assertFalse(frappe.has_permission(doctype, "create"), doctype)
			self.assertFalse(frappe.has_permission(doctype, "write"), doctype)
