import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


def erpnext(defaults):
	"""ERPNext's default-BOM lookup, answering from ``defaults`` (Item -> BOM)."""
	details = types.ModuleType("erpnext.stock.get_item_details")
	details.get_default_bom = MagicMock(side_effect=lambda item_code=None: defaults.get(item_code))
	return {
		"erpnext": types.ModuleType("erpnext"),
		"erpnext.stock": types.ModuleType("erpnext.stock"),
		details.__name__: details,
	}


class MaterialRequestBoms(unittest.TestCase):
	def request(self, **row):
		return Record(material_request_type="Purchase", items=[Record(item_code="TAPE", **row)])

	def test_raw_material_request_refused_when_default_bom_is_not_pinned(self):
		with load_service(ROOT + ".api.material_planning", erpnext({"FIX-1": "BOM-NEW"})) as (module, frappe):
			frappe.get_all.return_value = [Record(idx=1, item_code="FIX-1", ill_bom="BOM-OLD", bom_no=None)]
			with self.assertRaises(ValueError) as refused:
				module.validate_material_request(self.request(sales_order="SO-1"))
			self.assertIn("SO-1", str(refused.exception))
			self.assertIn("BOM-OLD", str(refused.exception))

	def test_matching_and_unpinned_lines_pass(self):
		defaults = {"FIX-1": "BOM-1", "STOCK": "BOM-S"}
		with load_service(ROOT + ".api.material_planning", erpnext(defaults)) as (module, frappe):
			frappe.get_all.return_value = [
				Record(idx=1, item_code="FIX-1", ill_bom=None, bom_no="BOM-1"),
				Record(idx=2, item_code="STOCK", ill_bom=None, bom_no=None),
			]
			module.validate_material_request(self.request(sales_order="SO-1"))

	def test_plan_raised_and_unlinked_requests_are_not_checked(self):
		with load_service(ROOT + ".api.material_planning", erpnext({})) as (module, frappe):
			module.validate_material_request(self.request(sales_order="SO-1", production_plan="PP-1"))
			module.validate_material_request(self.request())
			module.validate_material_request(Record(material_request_type="Material Transfer", items=[]))
			frappe.get_all.assert_not_called()


class ProductionPlanBoms(unittest.TestCase):
	def test_order_row_uses_pinned_bom_and_bundle_members_are_left_alone(self):
		with load_service(ROOT + ".api.material_planning") as (module, frappe):
			lines = {
				"SOI-1": Record(item_code="FIX-1", ill_bom="BOM-PINNED", bom_no=None),
				"SOI-2": Record(item_code="BUNDLE", ill_bom=None, bom_no=None),
			}
			frappe.db.get_value.side_effect = lambda _doctype, name, *_args, **_kw: lines.get(name)
			plan = Record(
				po_items=[
					Record(item_code="FIX-1", sales_order_item="SOI-1", bom_no="BOM-DEFAULT"),
					Record(item_code="RUN-A", sales_order_item="SOI-2", bom_no="BOM-RUN"),
					Record(item_code="STOCK", sales_order_item=None, bom_no="BOM-S"),
				]
			)
			module.validate_production_plan(plan)
			self.assertEqual([row.bom_no for row in plan.po_items], ["BOM-PINNED", "BOM-RUN", "BOM-S"])


class PlannedWorkOrders(unittest.TestCase):
	def work_order(self, **values):
		base = dict(
			production_plan="PP-1", sales_order="SO-1", sales_order_item="SOI-1", production_item="FIX-1"
		)
		return Record(**{**base, **values})

	def test_plan_cannot_duplicate_order_work_order(self):
		with load_service(ROOT + ".api.material_planning") as (module, frappe):
			frappe.get_all.return_value = ["WO-1"]
			with self.assertRaises(ValueError) as refused:
				module.guard_planned_work_order(self.work_order())
			self.assertIn("WO-1", str(refused.exception))
			kwargs = frappe.get_all.call_args.kwargs
			self.assertEqual(kwargs["filters"]["sales_order"], "SO-1")
			self.assertEqual(kwargs["filters"]["production_plan"], ["is", "not set"])
			self.assertEqual(kwargs["or_filters"], {"production_item": "FIX-1", "sales_order_item": "SOI-1"})

	def test_uncovered_lines_and_other_work_orders_pass(self):
		with load_service(ROOT + ".api.material_planning") as (module, frappe):
			frappe.get_all.return_value = []
			module.guard_planned_work_order(self.work_order())
			frappe.get_all.reset_mock()
			module.guard_planned_work_order(self.work_order(production_plan=None))
			module.guard_planned_work_order(self.work_order(sales_order=None))
			frappe.get_all.assert_not_called()


class MaterialsQueue(unittest.TestCase):
	def dependencies(self):
		conversation = types.ModuleType(ROOT + ".portal.conversations")
		conversation._pagination = lambda page, size: (int(page), int(size))
		staff = types.ModuleType(ROOT + ".portal.staff")
		staff.allowed = MagicMock(side_effect=lambda capability: capability == "operations")
		return {conversation.__name__: conversation, staff.__name__: staff}

	def test_operations_sees_open_purchase_requests_and_overdue_uses_dates(self):
		with load_service(ROOT + ".portal.queues", self.dependencies()) as (module, _frappe):
			_label, doctype, filters, _fields = module.query("materials", "overdue")
			self.assertEqual(doctype, "Material Request")
			self.assertEqual(filters["schedule_date"], ["<", "2026-09-25"])
			self.assertEqual(filters["status"], ["in", ["Pending", "Partially Ordered"]])
			with self.assertRaises(ValueError):
				module.query("materials", "mine")
			with self.assertRaises(PermissionError):
				module.query("quotes")


if __name__ == "__main__":
	unittest.main()
