"""Catalog service contracts with real catalog validation and explicit DB boundaries."""

import json
import re
import unittest
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_catalog_builder import API, catalog_service
from test_services import load_service


def catalog():
	return {
		"schema_version": 2,
		"product_type": "extrusion-kit",
		"series_name": "Test kit",
		"records": {"ilL-Extrusion-Kit-Template": [{"template_code": "KIT", "template_name": "Test kit"}]},
	}


@contextmanager
def engine(**access):
	with catalog_service(API, **access) as (service, frappe):
		state = SimpleNamespace(
			existing={}, passing=[], inserted=[], logs=[], events=[], failures={}, warnings={}
		)
		frappe.local.site = "test.local"
		frappe.local.message_log = []
		frappe.utils.now_datetime = lambda: datetime(2026, 10, 5, 12)
		frappe.utils.strip_html_tags = lambda text: re.sub(r"<[^>]*>", "", text)
		frappe.get_traceback = lambda: "private traceback"
		frappe.db.sql.return_value = [[1]]
		frappe.db.exists.return_value = True
		frappe.db.commit.side_effect = lambda: state.events.append("commit")
		frappe.db.rollback.side_effect = lambda **kw: state.events.append(
			"savepoint rollback" if kw else "rollback"
		)

		def get_all(doctype, **kwargs):
			if doctype == service.AUDIT:
				return state.passing
			return sorted(set(kwargs["filters"]["name"][1]) & set(state.existing.get(doctype, [])))

		def get_doc(data):
			doc = MagicMock()
			doc.name = (
				data.get("name")
				or data.get("template_code")
				or data.get("item_code")
				or data.get("series_name")
				or "generated-name"
			)

			def insert(**kwargs):
				if data["doctype"] == service.AUDIT:
					assert kwargs == {"ignore_permissions": True}
					state.logs.append(data)
					state.events.append("log")
					doc.name = f"CAT-IMP-{len(state.logs)}"
				else:
					assert kwargs == {}, "Catalog inserts must use native permission and validation checks"
					state.inserted.append(data)
					state.events.append("insert")
					frappe.local.message_log = state.warnings.get(data["doctype"], [])
					if data["doctype"] in state.failures:
						raise state.failures[data["doctype"]]
				return doc

			doc.insert.side_effect = insert
			return doc

		frappe.get_all.side_effect = get_all
		frappe.get_doc.side_effect = get_doc
		yield service, frappe, state


class CatalogImport(unittest.TestCase):
	def test_authorization_precedes_any_db_mutation(self):
		for access in ({"roles": []}, {"roles": ["Dealer"]}, {"user": "Guest"}, {"enabled": 0}):
			with self.subTest(access=access), engine(**access) as (service, frappe, _):
				for endpoint, args in (
					(service.check, (catalog(),)),
					(service.import_catalog, (catalog(), "hash")),
					(service.history, ()),
				):
					with self.assertRaises(PermissionError):
						endpoint(*args)
				frappe.get_doc.assert_not_called()
				frappe.db.commit.assert_not_called()
				frappe.db.sql.assert_not_called()

	def test_http_methods_and_canonical_hash(self):
		with engine() as (service, _, __):
			for endpoint in (service.check, service.import_catalog):
				self.assertEqual(endpoint.whitelist_options, {"methods": ["POST"]})
			self.assertEqual(service.history.whitelist_options, {"methods": ["GET"]})
			self.assertEqual(
				service.catalog_hash({"b": {"y": 2, "x": 1}, "a": "é"}),
				service.catalog_hash({"a": "é", "b": {"x": 1, "y": 2}}),
			)

	def test_invalid_shape_and_json_are_refused_and_logged(self):
		for value in (None, [], "{invalid", {"records": []}, {"records": {"Item": {}}}):
			with self.subTest(value=value), engine() as (service, _, state):
				response = service.check(value)
				self.assertEqual((response["status"], response["stage"]), ("Refused", "shape"))
				self.assertTrue(response["log"])
				self.assertEqual(len(state.logs), 1)
				self.assertFalse(state.inserted)
		with engine() as (service, _, state):
			service.check("!" * 200_000)
			self.assertLessEqual(len(state.logs[0]["catalog_json"].encode()), 100 * 1024)

	def test_parent_count_limit_refuses_before_lock(self):
		with engine() as (service, frappe, state):
			value = catalog()
			value["records"]["Brand"] = [{"brand": str(i)} for i in range(500)]
			response = service.check(value)
			self.assertEqual(response["status"], "Refused")
			self.assertIn("501 records, limit 500", response["errors"][0])
			self.assertEqual(response["summary"]["records"], 501)
			self.assertEqual(len(state.logs), 1)
			frappe.db.sql.assert_not_called()

	def test_validation_errors_never_insert_catalog_records(self):
		variants = [catalog() for _ in range(5)]
		variants[0]["records"]["ilL-Extrusion-Kit-Template"][0]["typo"] = True
		variants[1]["records"] = {}
		variants[2]["records"]["ilL-Extrusion-Kit-Template"][0]["allowed_options"] = [None]
		variants[3]["external_links"] = []
		variants[4]["records"]["User"] = [{"name": "unauthorized"}]
		for value in variants:
			with self.subTest(value=value), engine() as (service, _, state):
				response = service.check(value)
				self.assertEqual((response["status"], response["stage"]), ("Failed", "validate"))
				self.assertFalse(state.inserted)

	def test_declared_links_must_exist_even_when_unused(self):
		with engine() as (service, _, state):
			value = catalog()
			value["external_links"] = {"UOM": ["TYPO"]}
			response = service.check(value)
			self.assertIn("Declared existing record not found in ERPNext: UOM TYPO", response["errors"])
			self.assertFalse(state.inserted)

	def test_existing_names_are_rejected_and_queries_are_bounded(self):
		with engine() as (service, frappe, state):
			state.existing["ilL-Extrusion-Kit-Template"] = ["KIT"]
			response = service.check(catalog())
			self.assertIn("already exists in ERPNext", response["errors"][0])
			state.existing["UOM"] = [str(i) for i in range(1001)]
			value = catalog()
			value["external_links"] = {"UOM": state.existing["UOM"]}
			service.check(value)
			queries = [call for call in frappe.get_all.call_args_list if call.args[0] == "UOM"]
			self.assertEqual([len(call.kwargs["filters"]["name"][1]) for call in queries], [500, 500, 1])

	def test_missing_create_permission_is_reported_before_inserts(self):
		with engine() as (service, frappe, state):
			frappe.has_permission.return_value = False
			response = service.check(catalog())
			self.assertEqual((response["status"], response["stage"]), ("Failed", "permissions"))
			self.assertEqual(response["errors"], ["You cannot create ilL-Extrusion-Kit-Template"])
			self.assertFalse(state.inserted)

	def test_check_rolls_back_before_committing_audit(self):
		with engine() as (service, frappe, state):
			response = service.check(json.dumps(catalog()))
			self.assertEqual(response["status"], "Passed")
			self.assertTrue(response["ok"])
			self.assertEqual(response["results"][0]["status"], "checked")
			self.assertEqual(response["summary"]["created"], 0)
			self.assertEqual(response["summary"]["checked"], 1)
			self.assertEqual(state.events, ["insert", "rollback", "log", "commit"])
			frappe.db.release_savepoint.assert_called_once_with(service.SAVEPOINT)
			self.assertEqual(
				frappe.db.sql.call_args.args, ("select release_lock(%s)", service.LOCK + ":test.local")
			)

	def test_failure_skips_dependents_and_checks_independent_rows(self):
		with engine() as (service, _, state):
			value = catalog()
			value["records"]["ilL-Attribute-Series"] = [{"series_name": "SERIES", "code": "S"}]
			value["records"]["ilL-Extrusion-Kit-Template"][0]["series"] = "SERIES"
			value["records"]["Brand"] = [{"brand": "independent"}]
			state.failures["ilL-Attribute-Series"] = ValueError("invalid series")
			response = service.check(value)
			self.assertEqual(response["status"], "Failed")
			self.assertEqual(
				{r["doctype"]: r["status"] for r in response["results"]},
				{
					"ilL-Attribute-Series": "error",
					"ilL-Extrusion-Kit-Template": "skipped",
					"Brand": "checked",
				},
			)
			self.assertIn("savepoint rollback", state.events)
			self.assertEqual(response["summary"]["errors"], 1)
			self.assertEqual(response["summary"]["skipped"], 1)

	def test_import_requires_same_user_recent_check_and_exact_payload_hash(self):
		for expected in (None, "changed", "matching"):
			with self.subTest(expected=expected), engine() as (service, frappe, state):
				value = catalog()
				response = service.import_catalog(
					value, service.catalog_hash(value) if expected == "matching" else expected
				)
				self.assertEqual((response["status"], response["stage"]), ("Refused", "gate"))
				self.assertFalse(state.inserted)
				frappe.db.sql.assert_not_called()
				if expected == "matching":
					filters = frappe.get_all.call_args.kwargs["filters"]
					self.assertEqual(filters["user"], frappe.session.user)
					self.assertEqual(filters["status"], "Passed")
					self.assertEqual(filters["creation"], [">=", datetime(2026, 10, 5, 11, 30)])

	def test_import_commits_records_before_audit_and_links_passing_check(self):
		with engine() as (service, _, state):
			state.passing = ["CHECK-1"]
			response = service.import_catalog(catalog(), service.catalog_hash(catalog()))
			self.assertEqual(response["status"], "Imported")
			self.assertEqual(response["summary"]["created"], 1)
			self.assertEqual(state.events, ["insert", "commit", "log", "commit"])
			self.assertEqual(state.logs[0]["check_log"], "CHECK-1")

	def test_import_error_rolls_back_everything_except_audit(self):
		with engine() as (service, _, state):
			state.passing = ["CHECK-1"]
			state.failures["ilL-Extrusion-Kit-Template"] = ValueError("site validation")
			response = service.import_catalog(catalog(), service.catalog_hash(catalog()))
			self.assertEqual(response["status"], "Rolled Back")
			self.assertEqual(response["summary"]["created"], 0)
			self.assertEqual(state.events, ["insert", "savepoint rollback", "rollback", "log", "commit"])

	def test_busy_lock_refuses_without_releasing_another_run(self):
		with engine() as (service, frappe, state):
			frappe.db.sql.return_value = [[0]]
			response = service.check(catalog())
			self.assertEqual((response["status"], response["stage"]), ("Refused", "lock"))
			self.assertFalse(state.inserted)
			self.assertEqual(frappe.db.sql.call_count, 1)

	def test_unexpected_pipeline_failure_rolls_back_logs_traceback_and_releases_lock(self):
		with (
			engine() as (service, frappe, state),
			patch.object(service, "_existence_map", side_effect=RuntimeError("private failure")),
		):
			response = service.check(catalog())
			self.assertEqual(response["status"], "Error")
			self.assertEqual(state.events, ["rollback", "log", "commit"])
			self.assertEqual(state.logs[0]["error_detail"], "private traceback")
			self.assertNotIn("private", json.dumps(response))
			self.assertIn("release_lock", frappe.db.sql.call_args.args[0])

	def test_messages_are_plain_deduplicated_and_errors_are_bounded(self):
		with engine() as (service, frappe, state):
			state.warnings["ilL-Extrusion-Kit-Template"] = [
				{"message": "<b>Review options</b>"},
				{"message": "Review options"},
			]
			response = service.check(catalog())
			self.assertEqual(response["results"][0]["warnings"], ["Review options"])
			state.failures["ilL-Extrusion-Kit-Template"] = RuntimeError("internal error")
			response = service.check(catalog())
			self.assertEqual(response["results"][0]["message"], "RuntimeError: Review options")
			frappe.local.message_log = []
			self.assertEqual(len(service._error_text(RuntimeError("x" * 1200))), 1000)

	def test_audit_failure_never_misreports_a_committed_import_as_rolled_back(self):
		with (
			engine() as (service, frappe, state),
			patch.object(service, "_write_log", side_effect=RuntimeError),
		):
			state.passing = ["CHECK-1"]
			response = service.import_catalog(catalog(), service.catalog_hash(catalog()))
			self.assertEqual(response["status"], "Imported")
			self.assertIn("records were imported", response["errors"][0])
			self.assertIsNone(response["log"])
			self.assertIn("release_lock", frappe.db.sql.call_args.args[0])
			self.assertEqual(service.check(catalog())["status"], "Error")

	def test_history_is_bounded_and_publishers_only_get_their_own_runs(self):
		for access, all_users in (
			({}, False),
			({"roles": ["System Manager"]}, True),
			({"user": "Administrator", "roles": []}, True),
		):
			with self.subTest(access=access), engine(**access) as (service, frappe, _):
				for limit, expected in ((-1, 1), (999, 100), (20, 20)):
					service.history(limit)
					args = frappe.get_all.call_args.kwargs
					self.assertEqual(args["limit_page_length"], expected)
					self.assertEqual(args["filters"], {} if all_users else {"user": frappe.session.user})
					self.assertNotIn("catalog_json", args["fields"])


class CatalogPermissions(unittest.TestCase):
	def test_publisher_can_create_catalog_masters_without_delete_or_transaction_rights(self):
		permissions = SimpleNamespace(add_permission=MagicMock(), update_permission_property=MagicMock())
		with load_service(
			"illumenate_lighting.portal_staff_permissions", {"frappe.permissions": permissions}
		) as (service, frappe):
			frappe.db.exists.return_value = True
			frappe.clear_cache = MagicMock()
			frappe.get_all.return_value = ["ilL-Extrusion-Kit-Template", "ilL-Spec-Profile", "Sales Order"]
			service.apply_service_permissions()
			grants = {
				(dt, role, ptype): value
				for dt, role, level, ptype, value in (
					call.args for call in permissions.update_permission_property.call_args_list
				)
			}
			for dt in (
				"Item",
				"Item Attribute",
				"Item Group",
				"UOM",
				"Brand",
				"Item Price",
				"ilL-Extrusion-Kit-Template",
			):
				self.assertEqual(grants[dt, "ilL Catalog Publisher", "create"], 1)
				self.assertEqual(grants[dt, "ilL Catalog Publisher", "delete"], 0)
			for dt in ("Supplier", "Price List", "Currency", "ilL-Catalog-Import"):
				self.assertEqual(grants[dt, "ilL Catalog Publisher", "read"], 1)
				self.assertEqual(grants[dt, "ilL Catalog Publisher", "create"], 0)
			self.assertEqual(grants["ilL-Catalog-Import", "ilL Catalog Publisher", "export"], 1)
			self.assertEqual(grants["ilL-Extrusion-Kit-Template", "ilL Engineering", "create"], 1)
			self.assertNotIn(("Sales Order", "ilL Catalog Publisher", "create"), grants)
