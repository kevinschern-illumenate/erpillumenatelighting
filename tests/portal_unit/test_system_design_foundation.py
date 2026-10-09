"""System Designer foundations: Settings defaults, rollout check, error contract and access wrappers."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

ACCESS = ROOT + ".portal.access"
STAFF = ROOT + ".portal.staff"


def doubles(allowed=(), customer=None, can_read=True, can_edit=True):
	access = types.SimpleNamespace(
		get_actor=MagicMock(return_value=Record(is_guest=False, customer=customer)),
		can_read_schedule=MagicMock(return_value=can_read),
		can_edit_schedule=MagicMock(return_value=can_edit),
	)
	staff = types.SimpleNamespace(allowed=MagicMock(side_effect=lambda name, user=None: name in allowed))
	return {ACCESS: access, STAFF: staff}


class SettingsDefaults(unittest.TestCase):
	def test_unsaved_single_returns_plan_defaults(self):
		with load_service(ROOT + ".system_design.settings") as (module, frappe):
			frappe.db.get_singles_dict.return_value = {}
			frappe.get_all.return_value = []
			values = module.settings()
			self.assertEqual(
				(
					values.vd_target_class2_pct,
					values.vd_target_line_pct,
					values.vd_target_landscape_pct,
					values.review_gate_watts,
					values.share_default_days,
					values.share_max_days,
				),
				(3.0, 3.0, 5.0, 1500.0, 90, 90),
			)
			self.assertEqual(values.enabled, 0)
			self.assertEqual(values.review_gate_enabled, 0)
			self.assertEqual(values.group_threshold_qty, 6)
			self.assertEqual(values.pilot_customers, [])

	def test_stored_strings_are_typed_and_blanks_fall_back(self):
		with load_service(ROOT + ".system_design.settings") as (module, frappe):
			frappe.db.get_singles_dict.return_value = {
				"vd_target_class2_pct": "2.5",
				"share_max_days": "60",
				"enabled": "1",
				"wire_waste_pct": "",
				"nec_edition": 2026,
			}
			frappe.get_all.return_value = ["Dealer B", "Dealer A", "Dealer A", None]
			values = module.settings()
			self.assertEqual(values.vd_target_class2_pct, 2.5)
			self.assertEqual(values.share_max_days, 60)
			self.assertEqual(values.enabled, 1)
			self.assertEqual(values.wire_waste_pct, 10.0)
			self.assertEqual(values.nec_edition, "2026")
			self.assertEqual(values.pilot_customers, ["Dealer A", "Dealer B"])


class Rollout(unittest.TestCase):
	def check(self, user="dealer@example.com", allowed=(), customer=None, enabled=0, pilots=()):
		with load_service(ROOT + ".system_design.settings", doubles(allowed=allowed, customer=customer)) as (
			module,
			frappe,
		):
			frappe.db.get_singles_dict.return_value = {"enabled": enabled}
			frappe.get_all.return_value = list(pilots)
			return module.is_enabled_for(user)

	def test_guest_never(self):
		self.assertFalse(self.check(user="Guest", enabled=1))

	def test_staff_before_rollout(self):
		self.assertTrue(self.check(allowed={"engineering"}))
		self.assertTrue(self.check(allowed={"design_review"}))

	def test_dealer_only_when_enabled_or_pilot(self):
		self.assertFalse(self.check(customer="Dealer A"))
		self.assertTrue(self.check(customer="Dealer A", enabled=1))
		self.assertTrue(self.check(customer="Dealer A", pilots=["Dealer A"]))
		self.assertFalse(self.check(customer="Dealer B", pilots=["Dealer A"]))
		self.assertFalse(self.check(customer=None, pilots=["Dealer A"]))


class DesignReviewCapability(unittest.TestCase):
	def test_applications_engineer_holds_design_review(self):
		with load_service(STAFF) as (staff, frappe):
			frappe.db.get_value.side_effect = lambda doctype, name, field: (
				1 if field == "enabled" else "System User"
			)
			frappe.get_roles.return_value = ["ilL Applications Engineer"]
			self.assertTrue(staff.allowed("design_review", "ae@example.com"))
			self.assertFalse(staff.allowed("engineering", "ae@example.com"))
			frappe.get_roles.return_value = ["ilL Engineering"]
			self.assertFalse(staff.allowed("design_review", "eng@example.com"))


class ErrorContract(unittest.TestCase):
	def test_respond_and_fail_shapes(self):
		with load_service(ROOT + ".system_design.api") as (api, _frappe):
			self.assertEqual(api.respond({"a": 1}), {"success": True, "data": {"a": 1}})
			self.assertEqual(
				api.fail("NOT_FOUND", "Schedule not found"),
				{"success": False, "error": "Schedule not found", "code": "NOT_FOUND"},
			)
			with self.assertRaises(ValueError):
				api.fail("TEAPOT", "no")

	def test_endpoint_maps_failures(self):
		with load_service(ROOT + ".system_design.api") as (api, frappe):
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="trace")

			class DoesNotExist(LookupError):
				pass

			frappe.DoesNotExistError = DoesNotExist

			def raising(error):
				@api.endpoint
				def body():
					raise error

				return body()

			self.assertEqual(api.endpoint(lambda: [1])(), {"success": True, "data": [1]})
			result = raising(api.DesignError("CONFLICT", "Saved elsewhere"))
			self.assertEqual((result["code"], result["error"]), ("CONFLICT", "Saved elsewhere"))
			self.assertEqual(raising(PermissionError("x"))["code"], "FORBIDDEN")
			self.assertEqual(raising(DoesNotExist("x"))["code"], "NOT_FOUND")
			result = raising(ValueError("Quantity must be positive"))
			self.assertEqual((result["code"], result["error"]), ("INVALID", "Quantity must be positive"))
			frappe.log_error.assert_not_called()
			result = raising(KeyError("tabSecret.column"))
			self.assertEqual(result["code"], "INTERNAL")
			self.assertNotIn("tabSecret", result["error"])
			frappe.log_error.assert_called_once()

	def test_parse_json(self):
		with load_service(ROOT + ".system_design.api") as (api, _frappe):
			self.assertEqual(api.parse_json('{"a": 1}'), {"a": 1})
			self.assertEqual(api.parse_json({"a": 1}), {"a": 1})
			with self.assertRaises(api.DesignError) as caught:
				api.parse_json("{nope", "design_json")
			self.assertEqual(caught.exception.code, "INVALID")


class AccessWrappers(unittest.TestCase):
	def load(self, **kwargs):
		return load_service(ROOT + ".system_design.access", doubles(**kwargs))

	def code(self, call, *args):
		try:
			call(*args)
		except Exception as e:
			return getattr(e, "code", type(e).__name__)
		return None

	def test_missing_and_unreadable_schedules_look_the_same(self):
		with self.load(can_read=False) as (access, frappe):
			frappe.db.exists.return_value = False
			self.assertEqual(self.code(access.require_read, "SCH-404"), "NOT_FOUND")
			self.assertEqual(self.code(access.require_read, None), "NOT_FOUND")
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="SCH-1")
			self.assertEqual(self.code(access.require_read, "SCH-1"), "NOT_FOUND")

	def test_reader_gets_the_document(self):
		with self.load() as (access, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="SCH-1")
			self.assertEqual(access.require_read("SCH-1").name, "SCH-1")

	def test_guest_is_refused_before_lookup(self):
		with self.load() as (access, frappe):
			frappe.session.user = "Guest"
			self.assertEqual(self.code(access.require_read, "SCH-1"), "FORBIDDEN")
			frappe.db.exists.assert_not_called()

	def test_edit_requires_write_and_an_unlocked_version(self):
		with self.load(can_edit=False) as (access, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="SCH-1")
			self.assertEqual(self.code(access.require_edit, "SCH-1"), "FORBIDDEN")
		with self.load() as (access, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="SCH-1", is_locked=1)
			self.assertEqual(self.code(access.require_edit, "SCH-1"), "LOCKED")
			frappe.get_doc.return_value = Record(name="SCH-1", is_locked=0)
			self.assertEqual(access.require_edit("SCH-1").name, "SCH-1")

	def test_reviewer_needs_design_review(self):
		with self.load(allowed={"engineering"}) as (access, _frappe):
			self.assertEqual(self.code(access.require_reviewer), "FORBIDDEN")
		with self.load(allowed={"design_review"}) as (access, _frappe):
			self.assertIsNone(self.code(access.require_reviewer))


if __name__ == "__main__":
	unittest.main()
