import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class StaffQueues(unittest.TestCase):
	def dependencies(self):
		conversation = types.ModuleType(ROOT + ".portal.conversations")
		conversation._pagination = lambda page, size: (int(page), int(size))
		staff = types.ModuleType(ROOT + ".portal.staff")
		staff.allowed = MagicMock(return_value=True)
		return {conversation.__name__: conversation, staff.__name__: staff}

	def test_native_count_and_rows_have_identical_predicates(self):
		with load_service(ROOT + ".portal.queues", self.dependencies()) as (module, frappe):
			frappe.get_list = MagicMock(side_effect=[[Record(total=1)], [Record(name="REQ1")]])
			result = module.items("drawings", "unassigned", "REQ")
			self.assertEqual(result["total"], len(result["rows"]))
			count, rows = frappe.get_list.call_args_list
			self.assertEqual(count.kwargs["filters"], rows.kwargs["filters"])
			self.assertEqual(rows.kwargs["filters"]["assigned_to"], ["is", "not set"])
			self.assertNotIn("assigned_to", module.QUEUES["drawings"][3])

	def test_direct_financial_queue_denied_to_engineering(self):
		with load_service(ROOT + ".portal.queues", self.dependencies()) as (module, frappe):
			module.allowed.side_effect = lambda capability: capability == "engineering"
			with self.assertRaises(PermissionError):
				module.items("orders")
			frappe.get_all.assert_not_called()

	def test_missing_native_permission_is_unavailable_not_zero(self):
		with load_service(ROOT + ".portal.queues", self.dependencies()) as (module, frappe):
			frappe.has_permission.return_value = False
			result = module.summary()
			self.assertTrue(result["queues"])
			self.assertTrue(all(not row["available"] and "total" not in row for row in result["queues"]))


class DrawingImpact(unittest.TestCase):
	def test_price_terms_and_dates_do_not_change_physical_hash(self):
		with load_service(ROOT + ".portal.drawing_impact") as (module, _frappe):
			doc = Record(
				doctype="Sales Order",
				items=[Record(item_code="BUILD1", qty=2, ill_bom="BOM1", rate=100)],
				terms="A",
			)
			before = module.build_hash(doc)
			doc["items"][0]["rate"] = 200
			doc["terms"] = "B"
			self.assertEqual(before, module.build_hash(doc))
			doc["items"][0]["ill_bom"] = "BOM2"
			self.assertNotEqual(before, module.build_hash(doc))

	def test_group_quantity_change_is_material(self):
		with load_service(ROOT + ".portal.drawing_impact") as (module, _frappe):
			doc = Record(
				doctype="ilL-Project-Fixture-Schedule",
				lines=[Record(line_key="L1", configured_group="G1", qty=1)],
			)
			before = module.build_hash(doc)
			doc["lines"][0]["qty"] = 2
			self.assertNotEqual(before, module.build_hash(doc))

	def test_existing_impact_key_reuses_task(self):
		with load_service(ROOT + ".portal.drawing_impact") as (module, frappe):
			frappe.db.get_value.return_value = "TASK1"
			self.assertEqual(module._task(Record(name="REQ1"), "BUILDHASH"), "TASK1")
			frappe.get_doc.assert_not_called()


class WorkspaceMerge(unittest.TestCase):
	def test_site_layout_preserved_and_new_destinations_added_once(self):
		with load_service("illumenate_lighting.portal_workspace") as (module, _frappe):
			site = {
				"content": json.dumps([{"id": "site-block", "data": {"text": "Our process"}}]),
				"shortcuts": [{"type": "DocType", "link_to": "Customer", "label": "Our customers"}],
			}
			shipped = {
				"content": json.dumps([{"id": "queue-block"}]),
				"shortcuts": [
					{"type": "Page", "link_to": "ill-portal-operations", "label": "Portal Operations"}
				],
			}
			once = module.merge_workspace(site, shipped)
			self.assertEqual(once, module.merge_workspace(once, shipped))
			self.assertEqual(json.loads(once["content"])[0]["data"]["text"], "Our process")
			self.assertEqual(len(once["shortcuts"]), 2)
