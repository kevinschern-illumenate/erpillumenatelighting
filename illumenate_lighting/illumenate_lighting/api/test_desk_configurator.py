# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Tests for the desk "Configure & Add Fixture" backend (``api.desk_configurator``).

The engine is patched out (``_dispatch_save`` / ``_fixture_payload_from_portal_selections``)
so these tests exercise the schedule-line write, the row-values contract and the
project/schedule create-or-get logic without needing full catalogue seed data.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from illumenate_lighting.illumenate_lighting.api import desk_configurator as dc
from illumenate_lighting.illumenate_lighting.api import quote_order_configurator as qoc
from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
	DEFAULT_SELLING_PRICE_LIST,
)

MODULE = "illumenate_lighting.illumenate_lighting.api.desk_configurator"


class TestDeskConfigurator(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

		self.customer_name = "_Test Customer Desk Cfg"
		if not frappe.db.exists("Customer", self.customer_name):
			customer = frappe.new_doc("Customer")
			customer.customer_name = self.customer_name
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		self.other_customer = "_Test Customer Desk Cfg Other"
		if not frappe.db.exists("Customer", self.other_customer):
			customer = frappe.new_doc("Customer")
			customer.customer_name = self.other_customer
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		self.project = self._ensure_project("_Test Desk Cfg Project", self.customer_name)

		self.item_code = self._ensure_item("_Test Desk Cfg Fixture Item")
		self.profile_item_code = self._ensure_item("_Test Desk Cfg Profile Item")

		self.template_code = "_Test Desk Cfg Template"
		if not frappe.db.exists("ilL-Fixture-Template", self.template_code):
			template = frappe.new_doc("ilL-Fixture-Template")
			template.template_code = self.template_code
			template.template_name = "Desk Cfg Template"
			template.is_active = 1
			template.insert(ignore_permissions=True)

		self.config_hash = "_test_desk_cfg_hash_00000001"
		existing = frappe.db.get_value("ilL-Configured-Fixture", {"config_hash": self.config_hash}, "name")
		if existing:
			self.fixture = frappe.get_doc("ilL-Configured-Fixture", existing)
		else:
			fixture = frappe.new_doc("ilL-Configured-Fixture")
			fixture.config_hash = self.config_hash
			fixture.fixture_template = self.template_code
			fixture.engine_version = "1.0.0"
			fixture.requested_overall_length_mm = 1000
			fixture.manufacturable_overall_length_mm = 995
			fixture.runs_count = 1
			fixture.total_watts = 15.5
			fixture.finish = "Silver"
			fixture.lens_appearance = "Clear"
			fixture.configured_item = self.item_code
			fixture.profile_item = self.profile_item_code
			fixture.append("pricing_snapshot", {"msrp_unit": 199.0})
			fixture.insert(ignore_permissions=True)
			self.fixture = fixture

		frappe.db.delete("Item Price", {"item_code": self.item_code})

	def tearDown(self):
		for name in frappe.get_all(
			"ilL-Project-Fixture-Schedule", filters={"schedule_name": ["like", "_Test Desk Cfg%"]}, pluck="name"
		):
			frappe.db.set_value("ilL-Project-Fixture-Schedule", name, "is_locked", 0)
			frappe.delete_doc("ilL-Project-Fixture-Schedule", name, force=True, ignore_permissions=True)
		for name in frappe.get_all(
			"ilL-Project", filters={"project_name": ["like", "_Test Desk Cfg New%"]}, pluck="name"
		):
			frappe.delete_doc("ilL-Project", name, force=True, ignore_permissions=True)
		for name in frappe.get_all(
			"ilL-Configured-Tape-Neon", filters={"config_hash": ["like", "_test_desk_cfg_ctn%"]}, pluck="name"
		):
			frappe.delete_doc("ilL-Configured-Tape-Neon", name, force=True, ignore_permissions=True)

	# ── helpers ─────────────────────────────────────────────────────────

	def _ensure_item(self, item_code, uom="Nos"):
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = item_code
			item.item_group = "Products"
			item.stock_uom = uom
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)
		return item_code

	def _ensure_project(self, project_name, customer):
		existing = frappe.db.get_value("ilL-Project", {"project_name": project_name}, "name")
		if existing:
			return frappe.get_doc("ilL-Project", existing)
		project = frappe.new_doc("ilL-Project")
		project.project_name = project_name
		project.customer = customer
		project.insert(ignore_permissions=True)
		return project

	def _create_schedule(self, name="_Test Desk Cfg Schedule", status="DRAFT", lines=None):
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = name
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = status
		for line in lines or []:
			schedule.append("lines", line)
		schedule.insert(ignore_permissions=True)
		return schedule

	def _fixture_artifact(self):
		return {
			"product_type": qoc.PRODUCT_TYPE_FIXTURE,
			"source_doctype": "ilL-Configured-Fixture",
			"source_name": self.fixture.name,
			"configured_fixture": self.fixture.name,
			"configured_tape_neon": None,
			"item_code": self.item_code,
			"bom": None,
			"description": "Test fixture",
			"template_code": self.template_code,
			"requested_length_mm": 1000,
			"mfg_length_mm": 995,
			"runs_count": 1,
			"total_watts": 15.5,
			"finish": "Silver",
			"lens": "Clear",
			"engine_version": "1.0.0",
			"configuration_snapshot": {"product_type": qoc.PRODUCT_TYPE_FIXTURE},
			"messages": [],
		}

	def _fixture_validation(self):
		return {
			"is_valid": True,
			"configured_fixture_id": self.fixture.name,
			"pricing": {"msrp_unit": 199.0},
			"messages": [],
		}

	def _patched_fixture_engine(self):
		"""Patch the engine + artifact builders so only the desk layer runs."""
		return (
			patch(f"{MODULE}._fixture_payload_from_portal_selections", return_value={"qty": 1}),
			patch(f"{MODULE}._dispatch_save", return_value=self._fixture_validation()),
			patch(f"{MODULE}._ensure_fixture_artifacts", return_value=self._fixture_artifact()),
		)

	def _build_fixture(self, **kwargs):
		args = {
			"parent_doctype": "Quotation",
			"product_type": "Linear Fixture",
			"selections_json": json.dumps({"finish": "Silver"}),
			"header_json": json.dumps({
				"quotation_to": "Customer",
				"party_name": self.customer_name,
				"selling_price_list": DEFAULT_SELLING_PRICE_LIST,
			}),
			"qty": 2,
			"fixture_type": "A1",
			"location": "Lobby",
			"notes": "Ceiling cove",
			"product_slug": self.template_code,
		}
		args.update(kwargs)
		p1, p2, p3 = self._patched_fixture_engine()
		with p1, p2, p3:
			return dc.build_configured_line(**args)

	# ── ensure_project_and_schedule ─────────────────────────────────────

	def test_ensure_project_and_schedule_creates_with_customer(self):
		result = dc.ensure_project_and_schedule(
			customer=self.customer_name,
			project_name="_Test Desk Cfg New Project",
			schedule_name="_Test Desk Cfg New Schedule",
		)
		self.assertTrue(result["success"], result)
		self.assertTrue(result["created_project"])
		self.assertTrue(result["created_schedule"])

		project = frappe.get_doc("ilL-Project", result["project"])
		self.assertEqual(project.customer, self.customer_name)
		self.assertEqual(project.status, "ACTIVE")

		schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", result["schedule"])
		self.assertEqual(schedule.status, "DRAFT")
		self.assertEqual(schedule.customer, self.customer_name)
		self.assertEqual(schedule.ill_project, project.name)

		# Idempotent: passing the ids back returns the same records untouched.
		again = dc.ensure_project_and_schedule(
			customer=self.customer_name, project=result["project"], schedule=result["schedule"]
		)
		self.assertTrue(again["success"], again)
		self.assertFalse(again["created_project"])
		self.assertFalse(again["created_schedule"])
		self.assertEqual(again["schedule"], result["schedule"])

	def test_ensure_project_rejects_customer_mismatch(self):
		result = dc.ensure_project_and_schedule(customer=self.other_customer, project=self.project.name)
		self.assertFalse(result["success"])
		self.assertIn("belongs to customer", result["error"])

	def test_ensure_project_requires_customer(self):
		result = dc.ensure_project_and_schedule(customer="", project_name="_Test Desk Cfg New X")
		self.assertFalse(result["success"])

	# ── build_configured_line ───────────────────────────────────────────

	def test_build_configured_line_fixture_writes_schedule_and_row(self):
		schedule = self._create_schedule()
		result = self._build_fixture(schedule=schedule.name)
		self.assertTrue(result["success"], result)

		schedule.reload()
		self.assertEqual(len(schedule.lines), 1)
		line = schedule.lines[0]
		self.assertEqual(line.line_id, "A1")
		self.assertEqual(line.location, "Lobby")
		self.assertEqual(line.qty, 2)
		self.assertEqual(line.notes, "Ceiling cove")
		self.assertEqual(line.configured_fixture, self.fixture.name)
		self.assertEqual(line.ill_item_code, self.item_code)
		self.assertEqual(line.configuration_status, "Configured")
		self.assertEqual(line.manufacturer_type, "ILLUMENATE")

		row = result["row_values"]
		self.assertEqual(row["item_code"], self.item_code)
		self.assertEqual(flt(row["qty"]), 2)
		self.assertGreater(flt(row["rate"]), 0)
		self.assertEqual(row["ill_section_label"], "Lobby")
		self.assertEqual(row["ill_fixture_type"], "A1")
		self.assertEqual(row["ill_schedule_line_id"], line.name)
		self.assertEqual(row["ill_configured_fixture"], self.fixture.name)
		self.assertEqual(row["additional_notes"], "Ceiling cove")

		self.assertEqual(result["header_values"]["ill_fixture_schedule"], schedule.name)
		self.assertEqual(result["schedule_line_name"], line.name)
		self.assertEqual(result["next_fixture_type"], "A2")

		# MSRP Item Price was published so get_item_details finds a rate.
		self.assertEqual(flt(qoc._get_selling_rate(self.item_code)), 199.0)

	def test_build_configured_line_tape_sets_variant_selections(self):
		schedule = self._create_schedule(name="_Test Desk Cfg Tape Schedule")
		ctn_item = self._ensure_item("_Test Desk Cfg Tape Item")
		ctn = frappe.new_doc("ilL-Configured-Tape-Neon")
		ctn.config_hash = "_test_desk_cfg_ctn_0001"
		ctn.product_category = "LED Tape"
		ctn.engine_version = "1.0.0"
		ctn.part_number = "_TEST-DESK-CTN-0001"
		ctn.requested_length_mm = 3000
		ctn.manufacturable_length_mm = 2950
		ctn.total_watts = 42.5
		ctn.total_segments = 1
		ctn.configured_item = ctn_item
		ctn.append("pricing_snapshot", {"msrp_unit": 250.0})
		ctn.insert(ignore_permissions=True)

		validation = {
			"is_valid": True,
			"configured_tape_neon": ctn.name,
			"product_category": "LED Tape",
			"part_number": ctn.part_number,
			"build_description": "Test tape build",
			"computed": {"manufacturable_length_mm": 2950, "lead_length_inches": 12},
			"resolved_items": {"tape_item": ctn_item},
			"selections": {"cct": "3000K"},
			"messages": [],
		}
		artifact = {
			"product_type": qoc.PRODUCT_TYPE_TAPE,
			"source_doctype": "ilL-Configured-Tape-Neon",
			"source_name": ctn.name,
			"configured_fixture": None,
			"configured_tape_neon": ctn.name,
			"item_code": ctn_item,
			"bom": None,
			"description": "Test tape",
			"template_code": None,
			"requested_length_mm": 3000,
			"mfg_length_mm": 2950,
			"runs_count": 1,
			"total_watts": 42.5,
			"finish": None,
			"lens": None,
			"configuration_snapshot": {"product_type": qoc.PRODUCT_TYPE_TAPE},
			"messages": [],
		}
		with patch(f"{MODULE}._dispatch_save", return_value=validation), patch(
			f"{MODULE}._ensure_tape_neon_artifacts", return_value=artifact
		):
			result = dc.build_configured_line(
				parent_doctype="Sales Order",
				product_type="LED Tape",
				selections_json={"cct": "3000K"},
				header_json={"customer": self.customer_name, "delivery_date": frappe.utils.today()},
				qty=1,
				fixture_type="T1",
				location="Bar",
				notes="Under counter",
				schedule=schedule.name,
			)
		self.assertTrue(result["success"], result)

		schedule.reload()
		line = schedule.lines[0]
		self.assertEqual(line.product_type, "LED Tape")
		self.assertEqual(line.configured_tape_neon, ctn.name)
		self.assertEqual(line.notes, "Under counter")
		self.assertTrue(line.variant_selections)
		variant = json.loads(line.variant_selections)
		self.assertEqual(variant["product_category"], "LED Tape")
		self.assertEqual(variant["part_number"], ctn.part_number)

		# READY requires variant_selections on tape lines; must not raise.
		schedule.status = "READY"
		schedule.save(ignore_permissions=True)

		row = result["row_values"]
		self.assertEqual(row["ill_configured_tape_neon"], ctn.name)
		self.assertEqual(row["ill_section_label"], "Bar")
		self.assertEqual(row["ill_fixture_type"], "T1")

	def test_build_configured_line_overwrites_existing_pending_line(self):
		schedule = self._create_schedule(
			name="_Test Desk Cfg Overwrite",
			lines=[{
				"line_id": "B3",
				"location": "Corridor",
				"qty": 4,
				"manufacturer_type": "ILLUMENATE",
				"configuration_status": "Pending",
			}],
		)
		result = self._build_fixture(schedule=schedule.name, line_idx=0, fixture_type="B3", location="Corridor", qty=4)
		self.assertTrue(result["success"], result)

		schedule.reload()
		self.assertEqual(len(schedule.lines), 1)
		line = schedule.lines[0]
		self.assertEqual(line.line_id, "B3")
		self.assertEqual(line.configured_fixture, self.fixture.name)
		self.assertEqual(line.configuration_status, "Configured")
		self.assertEqual(result["row_values"]["ill_schedule_line_id"], line.name)

	def test_build_configured_line_without_schedule(self):
		before = frappe.db.count("ilL-Project-Fixture-Schedule")
		result = self._build_fixture(schedule=None, fixture_type="Z9", location="Kitchen")
		self.assertTrue(result["success"], result)
		self.assertEqual(frappe.db.count("ilL-Project-Fixture-Schedule"), before)
		self.assertIsNone(result["schedule"])
		self.assertIsNone(result["header_values"]["ill_fixture_schedule"])

		row = result["row_values"]
		self.assertEqual(row["ill_fixture_type"], "Z9")
		self.assertEqual(row["ill_section_label"], "Kitchen")
		self.assertNotIn("ill_schedule_line_id", row)

	def test_build_configured_line_refuses_locked_or_quoted_schedule(self):
		quoted = self._create_schedule(name="_Test Desk Cfg Quoted", status="DRAFT")
		frappe.db.set_value("ilL-Project-Fixture-Schedule", quoted.name, "status", "QUOTED")

		fixtures_before = frappe.db.count("ilL-Configured-Fixture")
		with patch(f"{MODULE}._dispatch_save") as engine:
			result = dc.build_configured_line(
				parent_doctype="Quotation",
				product_type="Linear Fixture",
				selections_json={},
				schedule=quoted.name,
				product_slug=self.template_code,
			)
			engine.assert_not_called()
		self.assertFalse(result["success"])
		self.assertTrue(result.get("schedule_not_editable"))
		self.assertEqual(frappe.db.count("ilL-Configured-Fixture"), fixtures_before)

		locked = self._create_schedule(name="_Test Desk Cfg Locked")
		frappe.db.set_value("ilL-Project-Fixture-Schedule", locked.name, "is_locked", 1)
		with patch(f"{MODULE}._dispatch_save") as engine:
			result = dc.build_configured_line(
				parent_doctype="Quotation",
				product_type="Linear Fixture",
				selections_json={},
				schedule=locked.name,
				product_slug=self.template_code,
			)
			engine.assert_not_called()
		self.assertFalse(result["success"])
		self.assertIn("locked", result["error"].lower())

	def test_create_schedule_version_for_quoted(self):
		quoted = self._create_schedule(
			name="_Test Desk Cfg Version",
			lines=[{
				"line_id": "A1",
				"qty": 1,
				"manufacturer_type": "ILLUMENATE",
				"configured_fixture": self.fixture.name,
			}],
		)
		frappe.db.set_value("ilL-Project-Fixture-Schedule", quoted.name, "status", "QUOTED")
		result = dc.create_schedule_version(quoted.name)
		self.assertTrue(result["success"], result)
		self.assertNotEqual(result["name"], quoted.name)
		self.assertEqual(result["status"], "DRAFT")
		self.assertTrue(result["is_editable"])
		self.assertEqual(frappe.db.get_value("ilL-Project-Fixture-Schedule", quoted.name, "is_locked"), 1)

	# ── fixture type helpers ────────────────────────────────────────────

	def test_next_fixture_type_considers_form_ids(self):
		schedule = self._create_schedule(
			name="_Test Desk Cfg Next Id",
			lines=[{"line_id": "A1", "qty": 1, "manufacturer_type": "OTHER", "manufacturer_name": "X"}],
		)
		self.assertEqual(dc.get_next_fixture_type(schedule.name), "A2")
		self.assertEqual(dc.get_next_fixture_type(schedule.name, json.dumps(["A2", "A3"])), "A4")
		self.assertEqual(dc.get_next_fixture_type(None, ["A1"]), "A2")

	def test_get_schedule_picker_data(self):
		schedule = self._create_schedule(
			name="_Test Desk Cfg Picker",
			lines=[
				{"line_id": "A1", "location": "Lobby", "qty": 1, "manufacturer_type": "ILLUMENATE"},
				{
					"line_id": "A2",
					"location": "Lobby",
					"qty": 2,
					"manufacturer_type": "ILLUMENATE",
					"configured_fixture": self.fixture.name,
					"configuration_status": "Configured",
				},
			],
		)
		data = dc.get_schedule_picker_data(schedule.name)
		self.assertTrue(data["success"], data)
		self.assertEqual(data["locations"], ["Lobby"])
		self.assertEqual(data["next_fixture_type"], "A3")
		self.assertEqual(len(data["lines"]), 2)
		self.assertTrue(data["lines"][0]["is_pending"])
		self.assertFalse(data["lines"][1]["is_pending"])
		self.assertEqual(data["lines"][1]["name"], schedule.lines[1].name)

	# ── row contract ────────────────────────────────────────────────────

	def test_row_values_only_contain_child_meta_fields(self):
		result = self._build_fixture(schedule=None)
		self.assertTrue(result["success"], result)
		row = result["row_values"]
		meta = frappe.get_meta("Quotation Item")
		for key in row:
			self.assertTrue(meta.has_field(key), f"{key} is not a Quotation Item field")
		for forbidden in ("name", "parent", "parentfield", "parenttype", "idx", "doctype", "docstatus"):
			self.assertNotIn(forbidden, row)

	def test_apply_artifact_to_row_stamps_grouping_fields(self):
		quotation = frappe.new_doc("Quotation")
		quotation.quotation_to = "Customer"
		quotation.party_name = self.customer_name
		row = quotation.append("items", {})
		qoc._apply_artifact_to_row(
			quotation,
			row,
			self._fixture_artifact(),
			3,
			None,
			section_label="Lobby",
			fixture_type="A1",
			schedule_line_id="LINE-0001",
			additional_notes="  keep me  ",
		)
		self.assertEqual(row.ill_section_label, "Lobby")
		self.assertEqual(row.ill_fixture_type, "A1")
		self.assertEqual(row.ill_schedule_line_id, "LINE-0001")
		self.assertEqual(row.additional_notes, "keep me")
		self.assertEqual(row.item_code, self.item_code)
		self.assertEqual(flt(row.qty), 3)

	def test_internal_user_guard(self):
		user = "_test_desk_cfg_dealer@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({
				"doctype": "User",
				"email": user,
				"first_name": "Desk Dealer",
				"send_welcome_email": 0,
				"roles": [{"role": "Dealer"}],
			}).insert(ignore_permissions=True)
		try:
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				dc.get_desk_context("Quotation", customer=self.customer_name)
		finally:
			frappe.set_user("Administrator")
