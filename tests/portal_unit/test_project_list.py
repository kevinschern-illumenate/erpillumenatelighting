"""FLOW-3 projects list and FLOW-9 schedule version families."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class Row(Record):
	def __setattr__(self, key, value):
		self[key] = value


class ProjectList(unittest.TestCase):
	def service(self):
		self.can_edit = MagicMock(side_effect=lambda project, user: project.name == "P-1")
		access = types.SimpleNamespace(
			can_edit_project=self.can_edit,
			schedule_query_conditions=MagicMock(return_value="visible = 1"),
		)
		context = load_service(ROOT + ".portal.project_list", {ROOT + ".portal.access": access})
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe._dict = Row
		frappe.get_list = MagicMock(return_value=[])
		frappe.get_all = MagicMock(return_value=[])
		frappe.db.sql = MagicMock(return_value=[])
		frappe.get_doc = MagicMock(side_effect=lambda doctype, name: Row(name=name))
		return module, frappe

	def test_unknown_options_fall_back_to_defaults(self):
		module, _frappe = self.service()
		self.assertEqual(module.options("bogus", "bogus", "x"), ("active", "recent", 1))
		self.assertEqual(module.options("archived", "name", "3"), ("archived", "name", 3))
		self.assertEqual(module.options("all", None, "-2"), ("all", "recent", 1))

	def test_version_families_keep_the_latest_first(self):
		module, _frappe = self.service()
		rows = [
			Row(name="S-1", version=1, version_parent=None),
			Row(name="S-3", version=3, version_parent="S-1"),
			Row(name="S-9", version=1, version_parent=None),
			Row(name="S-2", version=2, version_parent="S-1"),
		]
		families = module.version_families(rows)
		self.assertEqual([group.latest.name for group in families], ["S-3", "S-9"])
		self.assertEqual([row.name for row in families[0].earlier], ["S-2", "S-1"])
		self.assertEqual(families[1].earlier, [])

	def test_the_most_urgent_schedule_sets_the_next_step(self):
		module, _frappe = self.service()
		step = module.next_step([Row(status="DRAFT"), Row(status="QUOTED"), Row(status="ORDERED")])
		self.assertEqual(step, {"label": "Quote ready", "tone": "warning"})
		self.assertEqual(module.next_step([])["label"], "Add a schedule")
		self.assertEqual(module.next_step([Row(status="ISSUE"), Row(status="QUOTED")])["tone"], "danger")

	def test_search_filter_sort_and_pages_run_on_the_server(self):
		module, frappe = self.service()
		frappe.get_list.return_value = [
			Row(name=f"P-{i}", modified="2026-10-01", owner_customer=None) for i in range(3)
		]
		result = module.list_projects(
			"dana@acme.test", search=" lobby ", status="archived", sort="name", page="2", page_size=2
		)
		kwargs = frappe.get_list.call_args.kwargs
		self.assertEqual(kwargs["filters"], {"status": "ARCHIVED"})
		self.assertEqual(
			kwargs["or_filters"],
			{
				"project_name": ["like", "%lobby%"],
				"customer": ["like", "%lobby%"],
				"name": ["like", "%lobby%"],
			},
		)
		self.assertEqual(kwargs["order_by"], "project_name asc, name asc")
		self.assertEqual((kwargs["limit_start"], kwargs["limit_page_length"]), (2, 3))
		self.assertTrue(result["has_more"])
		self.assertEqual(len(result["projects"]), 2)
		self.assertEqual(
			(result["status_filter"], result["sort"], result["search"], result["page"]),
			("archived", "name", "lobby", 2),
		)

	def test_active_hides_only_archived_projects(self):
		module, frappe = self.service()
		module.list_projects("dana@acme.test")
		kwargs = frappe.get_list.call_args.kwargs
		self.assertEqual(kwargs["filters"], {"status": ["!=", "ARCHIVED"]})
		self.assertIsNone(kwargs["or_filters"])

	def test_each_project_carries_counts_activity_company_step_and_edit_right(self):
		module, frappe = self.service()
		frappe.get_list.return_value = [
			Row(name="P-1", modified="2026-10-01 09:00:00", owner_customer="CUST-1"),
			Row(name="P-2", modified="2026-10-05 09:00:00", owner_customer=None),
		]
		frappe.db.sql.return_value = [
			Row(
				name="S-1",
				ill_project="P-1",
				status="ORDERED",
				modified="2026-10-02",
				version=1,
				version_parent=None,
			),
			Row(
				name="S-2",
				ill_project="P-1",
				status="QUOTED",
				modified="2026-10-08",
				version=2,
				version_parent="S-1",
			),
			Row(
				name="S-5",
				ill_project="P-1",
				status="DRAFT",
				modified="2026-09-01",
				version=1,
				version_parent=None,
			),
		]
		frappe.get_all.return_value = [("CUST-1", "Acme Lighting")]
		first, second = module.list_projects("dana@acme.test")["projects"]
		sql, params = frappe.db.sql.call_args.args
		self.assertIn("AND visible = 1", sql)
		self.assertEqual(params, {"names": ("P-1", "P-2")})
		self.assertEqual(first.schedule_count, 2, "versions of one schedule count once")
		self.assertEqual(first.last_activity, "2026-10-08")
		self.assertEqual(first.company_name, "Acme Lighting")
		self.assertEqual(first.next_step["label"], "Quote ready")
		self.assertTrue(first.can_edit)
		self.assertEqual(second.schedule_count, 0)
		self.assertEqual(second.next_step["label"], "Add a schedule")
		self.assertFalse(second.can_edit)


if __name__ == "__main__":
	unittest.main()
