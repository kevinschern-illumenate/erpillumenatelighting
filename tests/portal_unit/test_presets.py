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

	# -- CAD drawing codes (CAD plan WP 1.2) ------------------------------------

	def get_all(self, doctype, filters=None, fields=None, pluck=None, **kwargs):
		"""``frappe.get_all`` over ``self.rows`` with equality filters."""
		rows = [
			row for row in self.rows.values() if all(row.get(key) == value for key, value in (filters or {}).items())
		]
		if pluck:
			return [row.get(pluck) for row in rows]
		return rows

	def test_cad_codes_are_uppercased_and_validated(self):
		with load_service(MODULE, self.extras) as (module, _frappe):
			self.assertEqual(module.normalize_cad_code("  hd27-dry "), "HD27-DRY")
			self.assertEqual(module.normalize_cad_code("A"), "A")
			self.assertEqual(module.normalize_cad_code("9" + "Z" * 23), "9" + "Z" * 23)
			self.assertIsNone(module.normalize_cad_code(""))
			self.assertIsNone(module.normalize_cad_code(None))
			for bad in ("-HD", "HD_27", "HD 27", "HD.27", "Ä1", "X" * 25, "HD/27"):
				with self.assertRaisesRegex(ValueError, "Drawing codes", msg=bad):
					module.normalize_cad_code(bad)
			self.assertTrue(module.is_cad_enabled(None), "presets made before the field are offered")
			self.assertTrue(module.is_cad_enabled(1))
			self.assertFalse(module.is_cad_enabled(0))
			self.assertFalse(module.is_cad_enabled("0"))

	def test_set_preset_cad_sets_and_clears_the_code_of_own_presets(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.get_all.side_effect = self.get_all
			self.store("P1")
			doc = Record(name="P1", user="buyer@example.com", customer="CUST-A", label="P1", family="Linear Fixture",
				shared_with_company=0, cad_code=None, cad_enabled=1)
			doc.save = MagicMock()
			frappe.get_doc.return_value = doc
			result = module.set_preset_cad("P1", cad_code=" hd27 ", schedule_name="SCH-1")
			frappe.get_doc.assert_called_once_with("ilL-Configuration-Preset", "P1")
			doc.save.assert_called_once_with(ignore_permissions=True)
			self.assertEqual(doc.cad_code, "HD27")
			self.assertEqual(doc.cad_enabled, 1, "the switch is left alone when not given")
			self.assertEqual(result["preset"]["cad_code"], "HD27")
			self.assertTrue(result["preset"]["cad_enabled"])
			self.assertEqual(self.configurator_calls, ["SCH-1"])
			module.set_preset_cad("P1", cad_enabled="0")
			self.assertEqual((doc.cad_code, doc.cad_enabled), ("HD27", 0), "the code is kept when not given")
			module.set_preset_cad("P1", cad_code="")
			self.assertIsNone(doc.cad_code)
			self.assertEqual(module.set_preset_cad.whitelist_options, {"methods": ["POST"]})
			with self.assertRaisesRegex(ValueError, "Drawing codes"):
				module.set_preset_cad("P1", cad_code="no spaces")

	def test_set_preset_cad_is_owner_only_and_flag_gated(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.get_all.side_effect = self.get_all
			self.store("P9", user="colleague@example.com", shared=1)
			with self.assertRaises(LookupError):
				module.set_preset_cad("P9", cad_code="MINE")
			with self.assertRaises(LookupError):
				module.set_preset_cad("missing", cad_code="MINE")
			frappe.get_doc.assert_not_called()
			self.enabled = False
			self.assertEqual(module.set_preset_cad("P9", cad_code="X"), {"success": False, "disabled": True})
			frappe.session.user = "Guest"
			self.enabled = True
			with self.assertRaises(PermissionError):
				module.set_preset_cad("P9", cad_code="X")

	def test_cad_codes_are_unique_within_the_company_or_the_user(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.get_all.side_effect = self.get_all
			self.store("P1")
			self.store("P2", user="colleague@example.com", shared=0)["cad_code"] = "COVE"
			self.store("P3", user="other@example.com", customer="CUST-B")["cad_code"] = "LOBBY"
			doc = Record(name="P1", user="buyer@example.com", customer="CUST-A", cad_code=None)
			doc.save = MagicMock()
			frappe.get_doc.return_value = doc
			with self.assertRaisesRegex(ValueError, "COVE is already used by another preset in your company"):
				module.set_preset_cad("P1", cad_code="cove")
			doc.save.assert_not_called()
			module.set_preset_cad("P1", cad_code="lobby")  # another company's code is free
			self.assertEqual(doc.cad_code, "LOBBY")
			self.rows["P1"]["cad_code"] = "LOBBY"
			module.set_preset_cad("P1", cad_code="LOBBY")  # re-setting its own code is fine
			# Users without a company: unique among their own presets only.
			self.actor = Record(user="solo@example.com", customer=None, is_dealer=False, is_internal=False)
			self.store("S1", user="solo@example.com", customer=None)["cad_code"] = "COVE"
			self.store("S2", user="solo@example.com", customer=None)
			solo = Record(name="S2", user="solo@example.com", customer=None, cad_code=None)
			solo.save = MagicMock()
			frappe.get_doc.return_value = solo
			with self.assertRaisesRegex(ValueError, "COVE is already used by another preset$"):
				module.set_preset_cad("S2", cad_code="COVE")
			module.set_preset_cad("S2", cad_code="LOBBY")
			self.assertEqual(solo.cad_code, "LOBBY")

	def test_save_validates_codes_and_keeps_cad_fields_when_not_given(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.get_all.side_effect = self.get_all
			self.store("P2", user="colleague@example.com")["cad_code"] = "COVE"
			frappe.get_doc.return_value.insert.return_value = Record(name="P1", label="Kitchen", cad_code="KIT")
			module.save_preset("Kitchen", self.request(), cad_code="kit")
			created = frappe.get_doc.call_args.args[0]
			self.assertEqual((created["cad_code"], created["cad_enabled"]), ("KIT", 1))
			with self.assertRaisesRegex(ValueError, "already used"):
				module.save_preset("Other", self.request(), cad_code="cove")
			module.save_preset("Plain", self.request())
			created = frappe.get_doc.call_args.args[0]
			self.assertNotIn("cad_code", created)
			self.assertEqual(created["cad_enabled"], 1, "new presets are offered to CAD")
			# Re-saving under the same label replaces the preset but keeps its code and switch.
			self.store("P1", label="Kitchen")["cad_code"] = "KIT"
			existing = MagicMock()
			existing.get.side_effect = {"cad_code": "KIT", "customer": "CUST-A"}.get
			frappe.get_doc.reset_mock()
			frappe.get_doc.return_value = existing
			module.save_preset("Kitchen", self.request())
			values = existing.update.call_args.args[0]
			self.assertNotIn("cad_code", values)
			self.assertNotIn("cad_enabled", values)
			module.save_preset("Kitchen", self.request(), cad_code="KIT", cad_enabled="0")
			values = existing.update.call_args.args[0]
			self.assertEqual((values["cad_code"], values["cad_enabled"]), ("KIT", 0), "its own code is not a clash")
			# A kept code must still be free in the company the re-saved preset now belongs to.
			self.store("P4", label="Moved", customer="CUST-OLD")["cad_code"] = "COVE"
			with self.assertRaisesRegex(ValueError, "COVE is already used"):
				module.save_preset("Moved", self.request())
			self.assertEqual(module.prepare(self.actor, "Fresh", self.request())[0], None, "prepare writes nothing")

	def test_list_and_get_carry_the_cad_fields(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			mine = self.store("P1", label="mine")
			mine.update(cad_code="HD27", cad_enabled=0)
			legacy = self.store("P2", label="legacy")
			frappe.get_all.side_effect = [[mine, legacy], []]
			presets = {row["name"]: row for row in module.list_presets()["presets"]}
			self.assertIn("cad_code", frappe.get_all.call_args_list[0].kwargs["fields"])
			self.assertIn("cad_enabled", frappe.get_all.call_args_list[0].kwargs["fields"])
			self.assertEqual((presets["P1"]["cad_code"], presets["P1"]["cad_enabled"]), ("HD27", False))
			self.assertEqual((presets["P2"]["cad_code"], presets["P2"]["cad_enabled"]), ("", True))
			loaded = module.get_preset("P1")["preset"]
			self.assertEqual((loaded["cad_code"], loaded["cad_enabled"]), ("HD27", False))

	def test_find_by_cad_code_sees_own_then_company_shared_enabled_presets(self):
		with load_service(MODULE, self.extras) as (module, frappe):
			self.wire(frappe)
			frappe.get_all.side_effect = self.get_all
			self.store("OWN", label="own")["cad_code"] = "HD27"
			self.store("SHARED", user="colleague@example.com", shared=1)["cad_code"] = "COVE"
			self.store("PRIVATE", user="colleague@example.com", shared=0)["cad_code"] = "SECRET"
			self.store("OTHERCO", user="other@example.com", customer="CUST-B", shared=1)["cad_code"] = "LOBBY"
			off = self.store("OFF", label="off")
			off.update(cad_code="OFF", cad_enabled=0)
			self.assertEqual(module.find_by_cad_code("hd27"), "OWN", "codes match case-insensitively")
			self.assertEqual(module.find_by_cad_code(" COVE "), "SHARED")
			self.assertIsNone(module.find_by_cad_code("SECRET"), "a colleague's private preset")
			self.assertIsNone(module.find_by_cad_code("LOBBY"), "another company's preset")
			self.assertIsNone(module.find_by_cad_code("OFF"), "switched off for CAD")
			self.assertIsNone(module.find_by_cad_code("bad code"))
			self.assertIsNone(module.find_by_cad_code(None))
			# An own preset wins over a company preset with the same code.
			self.store("SHARED-HD", user="colleague@example.com", shared=1)["cad_code"] = "HD27"
			self.assertEqual(module.find_by_cad_code("HD27"), "OWN")
			# Staff never see company-shared presets, as in the CAD catalog's styles.
			self.actor = Record(user="buyer@example.com", customer="CUST-A", is_dealer=False, is_internal=True)
			self.assertIsNone(module.find_by_cad_code("COVE"))
			self.assertEqual(module.find_by_cad_code("HD27", user="buyer@example.com"), "OWN")
			self.enabled = False
			self.assertIsNone(module.find_by_cad_code("HD27"))


if __name__ == "__main__":
	unittest.main()
