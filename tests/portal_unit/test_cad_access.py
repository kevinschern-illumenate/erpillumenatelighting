"""Who may use the CAD toolkit (draw-to-quote plan 1.4, 2.9): staff first, then pilot dealers."""

import types
import unittest

from test_services import ROOT, Record, load_service


class CadAccess(unittest.TestCase):
	def run_case(self, user="dealer@example.com", flag=True, all_dealers=False, staff=(), catalog=True, customer="CUST-1", pilots=(), designer_pilots=()):
		flags = types.SimpleNamespace(
			cad_import_enabled=lambda: flag,
			cad_all_dealers_enabled=lambda: all_dealers,
			cad_pilot_customers=lambda: list(pilots),
		)
		extras = {
			ROOT + ".portal.site_flags": flags,
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda name, user=None: name in staff),
			ROOT + ".portal.access": types.SimpleNamespace(
				can_view_catalog=lambda user=None: catalog, get_actor=lambda user=None: Record(customer=customer)
			),
			ROOT + ".system_design.settings": types.SimpleNamespace(pilot_customers=lambda: list(designer_pilots)),
		}
		with load_service(ROOT + ".system_design.cad_access", extras) as (module, frappe):
			frappe.session.user = user
			return module.enabled_for()

	def test_flag_off_refuses_everyone(self):
		self.assertFalse(self.run_case(flag=False, staff=("engineering",)))

	def test_guest_is_refused(self):
		self.assertFalse(self.run_case(user="Guest", staff=("engineering",)))

	def test_staff_first(self):
		for capability in ("engineering", "design_review", "sales"):
			self.assertTrue(self.run_case(staff=(capability,), catalog=False))

	def test_dealer_only_in_a_pilot(self):
		self.assertFalse(self.run_case())
		self.assertTrue(self.run_case(pilots=("CUST-1",)))
		self.assertTrue(self.run_case(designer_pilots=("CUST-1",)))
		self.assertFalse(self.run_case(pilots=("CUST-2",)))

	def test_all_dealers_switch_still_needs_catalog_access(self):
		self.assertTrue(self.run_case(all_dealers=True))
		self.assertFalse(self.run_case(all_dealers=True, catalog=False))


class CadCatalogEndpoint(unittest.TestCase):
	def call(self, enabled=True, staff=False, catalog=True):
		calls = []

		class DesignError(Exception):
			def __init__(self, code, message):
				super().__init__(message)
				self.code, self.message = code, message

		def require_cad():
			if not enabled:
				raise DesignError("FORBIDDEN", "not available")

		extras = {
			ROOT + ".system_design.cad_access": types.SimpleNamespace(require_cad=require_cad, is_cad_staff=lambda: staff),
			ROOT + ".system_design.cad_catalog": types.SimpleNamespace(cad_catalog=lambda: calls.append(1) or {"schema": "cad-catalog/1"}),
			ROOT + ".portal.access": types.SimpleNamespace(can_view_catalog=lambda: catalog),
			ROOT + ".system_design.errors": types.SimpleNamespace(DesignError=DesignError, CODES={"FORBIDDEN", "INVALID", "INTERNAL", "NOT_FOUND"}),
		}
		with load_service(ROOT + ".system_design.api", extras) as (module, _frappe):
			return module.get_cad_catalog(), calls

	def test_pilot_dealer_gets_the_catalog(self):
		result, calls = self.call()
		self.assertEqual(result, {"success": True, "data": {"schema": "cad-catalog/1"}})
		self.assertEqual(calls, [1])

	def test_not_enabled_is_forbidden(self):
		result, calls = self.call(enabled=False)
		self.assertEqual(result["code"], "FORBIDDEN")
		self.assertEqual(calls, [])

	def test_collaborator_without_catalog_access_is_forbidden(self):
		result, _calls = self.call(catalog=False)
		self.assertEqual(result["code"], "FORBIDDEN")
		result, _calls = self.call(catalog=False, staff=True)
		self.assertTrue(result["success"])


if __name__ == "__main__":
	unittest.main()



class CadRunIdCopy(unittest.TestCase):
	def test_line_copies_drop_the_cad_run_id(self):
		import ast
		from pathlib import Path

		source = (Path(__file__).resolve().parents[2] / "illumenate_lighting/illumenate_lighting/portal/line_copy.py").read_text()
		tree = ast.parse(source)
		exclude = next(node for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "EXCLUDE")
		names = {item.value for item in exclude.value.args[0].elts}
		self.assertIn("cad_run_id", names)
		self.assertNotIn("line_key", names)
