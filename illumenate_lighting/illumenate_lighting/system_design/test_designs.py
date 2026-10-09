# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for saved designs and revisions (WP-2.4)."""

import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import access, api, catalog

FIXTURE = (
	Path(__file__).resolve().parents[3]
	/ "tools/system_designer/packages/core-schemas/fixtures/designs/valid/runs-and-site.json"
)


def website_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	return email


def _tree_leaf(doctype, field, root, leaf):
	"""A non-group record in an ERPNext tree, creating the root on a site without setup data."""
	existing = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if existing:
		return existing
	if not frappe.db.exists(doctype, root):
		frappe.get_doc({"doctype": doctype, field: root, "is_group": 1}).insert(ignore_permissions=True)
	if not frappe.db.exists(doctype, leaf):
		parent_field = "parent_" + frappe.scrub(doctype)
		frappe.get_doc({"doctype": doctype, field: leaf, "is_group": 0, parent_field: root}).insert(
			ignore_permissions=True
		)
	return leaf


def designer_customer():
	"""The customer every ilL-Project needs, created once for these tests."""
	name = "ZZ Designer Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": _tree_leaf(
					"Customer Group", "customer_group_name", "All Customer Groups", "ZZ Designer Group"
				),
				"territory": _tree_leaf(
					"Territory", "territory_name", "All Territories", "ZZ Designer Territory"
				),
			}
		).insert(ignore_permissions=True)
	return name


class TestDesigns(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		project = frappe.get_doc(
			{
				"doctype": "ilL-Project",
				"project_name": "ZZ Designer Save Test",
				"customer": designer_customer(),
			}
		)
		project.insert(ignore_permissions=True)
		self.schedule = frappe.get_doc(
			{
				"doctype": "ilL-Project-Fixture-Schedule",
				"schedule_name": "ZZ Designer Save Schedule",
				"ill_project": project.name,
				"lines": [
					{
						"line_id": "TP1",
						"qty": 1,
						"location": "Hall",
						"manufacturer_type": "OTHER",
						"watts_each": 12,
						"input_voltage_v": 120,
						"voltage_class": "Line Voltage",
					}
				],
			}
		).insert(ignore_permissions=True)
		self.design = json.loads(FIXTURE.read_text(encoding="utf-8"))
		self.design["schedule"] = {"name": self.schedule.name, "version": self.schedule.get("version") or 0}
		self.design["catalogSnapshotHash"] = catalog.current_snapshot_hash()

	def save(self, **kwargs):
		kwargs.setdefault("terms_accepted", 1)
		return api.save_design(schedule=self.schedule.name, design_json=json.dumps(self.design), **kwargs)

	def test_save_update_conflict_and_revision(self):
		first = self.save()
		self.assertTrue(first["success"], first)
		data = first["data"]
		self.assertEqual(data["revision"], "A")
		self.assertEqual(len(data["build_hash"]), 64)
		record = frappe.get_doc("ilL-System-Design", data["name"])
		self.assertEqual(
			(record.status, record.is_current, record.ill_project), ("Draft", 1, self.schedule.ill_project)
		)
		self.assertEqual(record.terms_accepted_by, "Administrator")

		self.assertEqual(self.save()["code"], "CONFLICT")
		updated = self.save(design_name=data["name"], expected_modified=data["modified"])
		self.assertTrue(updated["success"], updated)
		stale = self.save(design_name=data["name"], expected_modified=data["modified"])
		self.assertEqual(stale["code"], "CONFLICT")

		opened = api.open_design(schedule=self.schedule.name)["data"]
		self.assertEqual(opened["design_meta"]["name"], data["name"])
		self.assertEqual(opened["design"]["schedule"]["name"], self.schedule.name)
		found = api.find_schedules(query="ZZ Designer Save")["data"]
		self.assertTrue(next(row for row in found if row["name"] == self.schedule.name)["has_design"])

		revision = api.create_revision(design=data["name"], note="Second pass")
		self.assertTrue(revision["success"], revision)
		self.assertEqual(revision["data"]["revision"], "B")
		self.assertEqual(frappe.db.get_value("ilL-System-Design", data["name"], "is_current"), 0)
		self.assertEqual(api.create_revision(design=data["name"])["code"], "CONFLICT")
		meta = api.open_design(schedule=self.schedule.name)["data"]["design_meta"]
		self.assertEqual((meta["revision"], meta["terms_accepted"]), ("B", False))
		unaccepted = self.save(
			design_name=revision["data"]["name"],
			expected_modified=meta["modified"],
			terms_accepted=0,
		)
		self.assertEqual(unaccepted["code"], "INVALID")
		self.assertEqual(api.open_design(schedule="NOPE-404", design=data["name"])["code"], "NOT_FOUND")

	def test_review_status_and_locked_schedule(self):
		data = self.save()["data"]
		frappe.db.set_value("ilL-System-Design", data["name"], "status", "In Review")
		modified = str(frappe.db.get_value("ilL-System-Design", data["name"], "modified"))
		self.assertEqual(self.save(design_name=data["name"], expected_modified=modified)["code"], "LOCKED")
		self.schedule.db_set("is_locked", 1)
		self.assertEqual(self.save()["code"], "LOCKED")

	def test_size_limit(self):
		self.design["views"] = {"riser": "x" * (5 * 1024 * 1024)}
		self.assertEqual(self.save()["code"], "INVALID")

	def test_permission_follows_the_schedule(self):
		data = self.save()["data"]
		record = frappe.get_doc("ilL-System-Design", data["name"])
		owner = website_user("zz-designer-owner@example.com")
		stranger = website_user("zz-designer-stranger@example.com")
		self.schedule.db_set("owner", owner)
		self.assertTrue(access.design_permission(record, "read", owner))
		self.assertFalse(access.design_permission(record, "read", stranger))
		self.assertFalse(access.design_permission(record, "read", "Guest"))
		self.assertTrue(access.design_permission(record, "write", "Administrator"))
		visible = frappe.db.sql(
			f"select name from `tabilL-System-Design` where {access.design_query_conditions(stranger)}",
			pluck="name",
		)
		self.assertNotIn(record.name, visible)
		frappe.set_user(stranger)
		try:
			self.assertEqual(
				api.open_design(schedule=self.schedule.name, design=record.name)["code"], "NOT_FOUND"
			)
		finally:
			frappe.set_user("Administrator")

	def test_reconcile_after_a_schedule_change(self):
		data = self.save()["data"]
		self.assertTrue(api.open_design(schedule=self.schedule.name)["data"]["reconcile"]["in_sync"])
		self.schedule.reload()
		self.schedule.append(
			"lines",
			{
				"line_id": "TP2",
				"qty": 1,
				"location": "Hall",
				"manufacturer_type": "OTHER",
				"watts_each": 8,
				"input_voltage_v": 120,
				"voltage_class": "Line Voltage",
			},
		)
		self.schedule.save(ignore_permissions=True)
		diff = api.reconcile_design(design=data["name"])["data"]
		self.assertEqual([item["lineId"] for item in diff["added"]], ["TP2"])
		self.assertEqual(api.open_design(schedule=self.schedule.name)["data"]["reconcile"], diff)
		blocked = self.save(design_name=data["name"], expected_modified=data["modified"])
		self.assertEqual(blocked["code"], "CONFLICT")
		saved = self.save(design_name=data["name"], expected_modified=data["modified"], reconciled=1)
		self.assertTrue(saved["success"], saved)
		self.assertTrue(api.reconcile_design(design=data["name"])["data"]["in_sync"])

	def test_verify_design_on_the_server(self):
		data = self.save()["data"]
		alone = api.verify_design(design=data["name"])
		self.assertTrue(alone["success"], alone)
		self.assertEqual((alone["data"]["ok"], alone["data"]["mismatches"]), (True, []))
		summary = alone["data"]["summary"]
		self.assertEqual(set(summary), {"loading", "runs", "messages", "review"})
		agreed = api.verify_design(design=data["name"], client=json.dumps(summary))["data"]
		self.assertTrue(agreed["ok"])
		disputed = api.verify_design(
			design=data["name"], client=json.dumps({**summary, "messages": ["PSU_OVERLOAD|PS-9"]})
		)["data"]
		self.assertFalse(disputed["ok"])
		self.assertIn(
			{"code": "PSU_OVERLOAD", "entityRef": "PS-9", "client": True, "server": False},
			disputed["mismatches"],
		)
		stored = json.loads(frappe.db.get_value("ilL-System-Design", data["name"], "verification_json"))
		self.assertEqual((stored["ok"], stored["compared"]), (False, True))
		self.assertEqual(api.verify_design(design="nope")["code"], "NOT_FOUND")
		self.assertEqual(api.verify_design(design=data["name"], client="[1")["code"], "INVALID")

	def test_copy_forward_to_the_next_version(self):
		data = self.save()["data"]
		next_name = self.schedule.create_new_version(version_notes="ZZ designer copy test")
		copied = api.copy_design_to_version(design=data["name"], target_schedule=next_name)
		self.assertTrue(copied["success"], copied)
		record = frappe.get_doc("ilL-System-Design", copied["data"]["name"])
		self.assertEqual((record.fixture_schedule, record.revision_parent), (next_name, data["name"]))
		self.assertEqual(json.loads(record.design_json)["schedule"]["name"], next_name)
		opened = api.open_design(schedule=next_name)["data"]
		self.assertEqual(opened["design_meta"]["name"], record.name)
		self.assertIsNone(opened["newer_version"])
		locked = api.open_design(schedule=self.schedule.name)["data"]
		self.assertTrue(locked["schedule"]["is_locked"])
		self.assertEqual(locked["newer_version"]["name"], next_name)
		self.assertTrue(opened["reconcile"]["in_sync"])
		self.assertEqual(
			api.copy_design_to_version(design=data["name"], target_schedule=next_name)["code"], "CONFLICT"
		)
		other = frappe.get_doc(
			{
				"doctype": "ilL-Project-Fixture-Schedule",
				"schedule_name": "ZZ Other",
				"ill_project": self.schedule.ill_project,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(
			api.copy_design_to_version(design=data["name"], target_schedule=other.name)["code"], "INVALID"
		)
