"""Plan 3.6: saved configuration presets, private or shared with the dealer's company."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.presets"
FIXTURE = "ilL-Fixture-Template"


class Presets(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.actor = Record(user="buyer@example.com", customer="CUST-A", is_dealer=True, is_internal=False)
		self.configurator_calls = []
		self.families = {"Linear Fixture", "LED Tape", "Driver"}
		self.visible = {"FT-1", "TN-1", "DRV-1"}
		self.active = {"FT-1": 1, "TN-1": 1, "DRV-1": 1, "FT-OLD": 1}
		self.template = Record(
			name="FT-1",
			allowed_options=[
				Record(option_type="Finish", finish="Black", is_active=1),
				Record(option_type="Finish", finish="Silver", is_active=0),
				Record(option_type="Mounting Method", mounting_method="Surface", is_active=1),
			],
			allowed_tape_offerings=[Record(tape_offering="TO-1"), Record(tape_offering="TO-2")],
		)
		self.offerings = {"TO-1": 1, "TO-2": 0}
		self.rows = {}

		def require_configurator(schedule=None, user=None):
			self.configurator_calls.append(schedule)

		def strip_prices(value):
			if isinstance(value, dict):
				return {k: strip_prices(v) for k, v in value.items() if "price" not in k}
			if isinstance(value, list):
				return [strip_prices(v) for v in value]
			return value

		self.extras = {
			ROOT + ".portal.site_flags": types.SimpleNamespace(presets_enabled=lambda: self.enabled),
			ROOT + ".portal.access": types.SimpleNamespace(get_actor=lambda user=None: self.actor),
			ROOT + ".portal.configurator_access": types.SimpleNamespace(
				require_configurator=require_configurator, strip_prices=strip_prices
			),
			ROOT + ".portal.rollout": types.SimpleNamespace(available=lambda family: family in self.families),
			ROOT + ".portal_listing": types.SimpleNamespace(
				template_visible=lambda doctype, name, staff=None: name in self.visible
			),
		}

	def wire(self, frappe):
		def exists(doctype, name):
			return name in self.active

		def get_value(doctype, name, field=None, as_dict=False, **kwargs):
			if doctype == "ilL-Configuration-Preset":
				if isinstance(name, dict):
					matches = [
						row.name
						for row in self.rows.values()
						if all(row.get(key) == value for key, value in name.items())
					]
					return matches[0] if matches else None
				return self.rows.get(name)
			if doctype == "ilL-Rel-Tape Offering":
				return self.offerings.get(name)
			if field == "is_active":
				return self.active.get(name)
			return None

		frappe.db.exists.side_effect = exists
		frappe.db.get_value.side_effect = get_value
		frappe.db.count.return_value = 0
		frappe.get_cached_doc = MagicMock(return_value=self.template)

	def request(self, **selections):
		return {"family": "Linear Fixture", "template": "FT-1", "selections": {"finish_code": "Black", **selections}}

	def store(self, name, user="buyer@example.com", customer="CUST-A", shared=0, request=None, label=None):
		request = request or self.request()
		self.rows[name] = Record(
			name=name,
			label=label or name,
			user=user,
			customer=customer,
			shared_with_company=shared,
			family=request["family"],
			template=request.get("template"),
			modified="2026-11-10 09:00:00",
			request_json=json.dumps(request),
		)
		return self.rows[name]

	# -- save ---------------------------------------------------------------

	def test_save_inserts_a_canonical_price_free_preset(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.get_doc.return_value.insert.return_value = Record(
				name="P1", label="Kitchen", user="buyer@example.com", shared_with_company=1,
				family="Linear Fixture", template="FT-1", modified="now",
			)
			request = {**self.request(), "unit_price": 99, "extra": "dropped"}
			result = module.save_preset("  Kitchen   run ", json.dumps(request), shared_with_company="1")
			doc = frappe.get_doc.call_args.args[0]
			self.assertEqual(doc["doctype"], "ilL-Configuration-Preset")
			self.assertEqual(doc["label"], "Kitchen run", "whitespace is collapsed")
			self.assertEqual(doc["user"], "buyer@example.com")
			self.assertEqual(doc["customer"], "CUST-A")
			self.assertEqual(doc["shared_with_company"], 1)
			stored = json.loads(doc["request_json"])
			self.assertEqual(stored, self.request(), "only request keys are kept, and never prices")
			self.assertEqual(doc["request_json"], json.dumps(stored, sort_keys=True, separators=(",", ":")))
			frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
			self.assertTrue(result["success"])
			self.assertEqual(result["preset"]["name"], "P1")
			self.assertEqual(module.save_preset.whitelist_options, {"methods": ["POST"]})

	def test_same_label_replaces_the_users_preset(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.store("P1", label="Kitchen")
			existing = MagicMock(name="P1", user="buyer@example.com", shared_with_company=0, family="Linear Fixture")
			frappe.get_doc.return_value = existing
			module.save_preset("Kitchen", self.request(finish_code="Black"))
			frappe.get_doc.assert_called_once_with("ilL-Configuration-Preset", "P1")
			existing.save.assert_called_once_with(ignore_permissions=True)
			self.assertEqual(existing.update.call_args.args[0]["shared_with_company"], 0)

	def test_save_refuses_unusable_templates_families_and_bad_input(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.visible.discard("FT-1")
			with self.assertRaisesRegex(ValueError, "no longer offered"):
				module.save_preset("A", self.request())
			self.visible.add("FT-1")
			with self.assertRaisesRegex(ValueError, "not available"):
				module.save_preset("A", {"family": "LED Neon", "template": "TN-1"})
			with self.assertRaisesRegex(ValueError, "product family"):
				module.save_preset("A", {"family": "Toaster", "template": "FT-1"})
			with self.assertRaisesRegex(ValueError, "Name the preset"):
				module.save_preset("   ", self.request())
			with self.assertRaisesRegex(ValueError, "Name the preset"):
				module.save_preset("x" * 141, self.request())
			with self.assertRaisesRegex(ValueError, "valid JSON"):
				module.save_preset("A", "{nope")
			with self.assertRaisesRegex(ValueError, "too large"):
				module.save_preset("A", self.request(notes="x" * 70000))
			frappe.db.count.return_value = module.MAX_PRESETS_PER_USER
			with self.assertRaisesRegex(ValueError, "delete some"):
				module.save_preset("New", self.request())
			frappe.get_doc.assert_not_called()

	def test_sharing_needs_a_dealer_company(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.actor = Record(user="staff@example.com", customer=None, is_dealer=False, is_internal=True)
			with self.assertRaisesRegex(ValueError, "dealer company"):
				module.save_preset("A", self.request(), shared_with_company=True)
			module.save_preset("A", self.request(), shared_with_company="0")
			self.assertIsNone(frappe.get_doc.call_args.args[0]["customer"])

	def test_only_the_owner_updates_or_deletes(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.store("P9", user="colleague@example.com", shared=1)
			with self.assertRaises(LookupError):
				module.save_preset("Mine now", self.request(), preset="P9")
			with self.assertRaises(LookupError):
				module.delete_preset("P9")
			self.store("P1")
			frappe.delete_doc = MagicMock()
			self.assertEqual(module.delete_preset("P1"), {"success": True})
			frappe.delete_doc.assert_called_once_with("ilL-Configuration-Preset", "P1", ignore_permissions=True)

	def test_guests_and_users_without_configurator_access_are_refused(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.session.user = "Guest"
			with self.assertRaises(PermissionError):
				module.list_presets()
			frappe.session.user = "buyer@example.com"
			module.list_presets(schedule_name="SCH-1")
			self.assertEqual(self.configurator_calls, ["SCH-1"], "schedule editors use the schedule grant")

	def test_kill_switch_turns_every_endpoint_off(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.enabled = False
			self.assertEqual(module.save_preset("A", self.request()), {"success": False, "disabled": True})
			self.assertEqual(module.list_presets(), {"success": True, "presets": [], "disabled": True})
			self.assertEqual(module.get_preset("P1"), {"success": False, "disabled": True})
			self.assertEqual(module.delete_preset("P1"), {"success": False, "disabled": True})
			frappe.get_all.assert_not_called()
			frappe.get_doc.assert_not_called()

	# -- list / load --------------------------------------------------------

	def test_list_returns_own_and_company_shared_presets_marked_available(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			mine = self.store("P1", label="b mine")
			gone = self.store("P2", label="a gone", request={"family": "Linear Fixture", "template": "FT-OLD"})
			shared = self.store("P3", user="colleague@example.com", shared=1, label="a shared")
			frappe.get_all.side_effect = [[mine, gone], [shared]]
			presets = module.list_presets(family="Linear Fixtures")["presets"]
			own, company = frappe.get_all.call_args_list
			self.assertEqual(own.kwargs["filters"], {"family": "Linear Fixture", "user": "buyer@example.com"})
			self.assertEqual(
				company.kwargs["filters"],
				{"family": "Linear Fixture", "customer": "CUST-A", "shared_with_company": 1},
			)
			self.assertNotIn("request_json", own.kwargs["fields"], "lists never carry the requests")
			self.assertEqual([(p["name"], p["mine"], p["available"]) for p in presets],
				[("P2", True, False), ("P1", True, True), ("P3", False, True)])
			self.assertEqual(module.list_presets.whitelist_options, {"methods": ["GET"]})

	def test_users_without_a_company_see_only_their_own(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.actor = Record(user="buyer@example.com", customer=None, is_dealer=False, is_internal=False)
			frappe.get_all.return_value = []
			module.list_presets()
			self.assertEqual(frappe.get_all.call_count, 1)

	def test_load_drops_options_the_template_no_longer_offers(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.store("P1", request=self.request(
				finish_code="Silver", mounting_method_code="Surface", tape_offering_id="TO-2", cct_code="30K"
			))
			loaded = module.get_preset("P1")["preset"]
			self.assertEqual(loaded["request"]["selections"], {"mounting_method_code": "Surface", "cct_code": "30K"})
			self.assertEqual(len(loaded["problems"]), 2)
			self.assertIn("Finish Silver", loaded["problems"][0])
			self.assertIn("TO-2", loaded["problems"][1])
			frappe.get_cached_doc.assert_called_once_with(FIXTURE, "FT-1")

	def test_load_of_a_withdrawn_template_returns_no_request(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.store("P1", request={"family": "Driver", "template": "DRV-1", "selections": {}})
			self.active["DRV-1"] = 0
			loaded = module.load("P1")
			self.assertIsNone(loaded["request"])
			self.assertEqual(loaded["problems"], ["DRV-1 is no longer offered"])

	def test_tape_templates_resolve_by_template_code(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.active.pop("TN-1")
			lookups = []

			def get_value(doctype, name, field=None, **kwargs):
				lookups.append((doctype, name))
				if name == {"template_code": "TN-CODE"}:
					return "TN-1"
				return 1 if name == "TN-1" else None

			frappe.db.get_value.side_effect = get_value
			self.assertIsNone(module.template_problem("LED Tape", "TN-CODE"))
			self.assertIn(("ilL-Tape-Neon-Template", {"template_code": "TN-CODE"}), lookups)

	def test_company_presets_are_hidden_from_other_companies(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			self.store("P5", user="other@example.com", customer="CUST-B", shared=1)
			self.store("P6", user="colleague@example.com", customer="CUST-A", shared=0)
			for name in ("P5", "P6", "missing", None):
				with self.assertRaises(LookupError):
					module.get_preset(name)


if __name__ == "__main__":
	unittest.main()
