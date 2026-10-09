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


class TestDesigns(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		project = frappe.get_doc({"doctype": "ilL-Project", "project_name": "ZZ Designer Save Test"})
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
		self.assertEqual(api.open_design(schedule=self.schedule.name)["data"]["design_meta"]["revision"], "B")
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
