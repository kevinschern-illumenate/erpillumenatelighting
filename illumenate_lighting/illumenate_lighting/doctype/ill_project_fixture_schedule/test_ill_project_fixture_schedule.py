# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestilLProjectFixtureSchedule(FrappeTestCase):
	def setUp(self):
		"""Set up test data"""
		# Create test customer
		self.customer_name = "_Test Customer for Schedule"
		if not frappe.db.exists("Customer", self.customer_name):
			customer = frappe.new_doc("Customer")
			customer.customer_name = self.customer_name
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		# Create test ilL-Project
		self.project_name = "_Test ilL Project for Schedule"
		if frappe.db.exists("ilL-Project", {"project_name": self.project_name}):
			self.project = frappe.get_doc("ilL-Project", {"project_name": self.project_name})
		else:
			self.project = frappe.new_doc("ilL-Project")
			self.project.project_name = self.project_name
			self.project.customer = self.customer_name
			self.project.insert(ignore_permissions=True)

		# Create test item for configured fixture
		self.item_code = "_Test Configured Fixture Item"
		if not frappe.db.exists("Item", self.item_code):
			item = frappe.new_doc("Item")
			item.item_code = self.item_code
			item.item_name = self.item_code
			item.item_group = "Products"
			item.stock_uom = "Nos"
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)

		# Create test fixture template
		self.template_code = "_Test Template"
		if not frappe.db.exists("ilL-Fixture-Template", self.template_code):
			template = frappe.new_doc("ilL-Fixture-Template")
			template.template_code = self.template_code
			template.template_name = "Test Template"
			template.is_active = 1
			template.insert(ignore_permissions=True)

		# Create test configured fixture
		self.config_hash = "_test_config_hash_12345678"
		if not frappe.db.exists("ilL-Configured-Fixture", self.config_hash):
			config_fixture = frappe.new_doc("ilL-Configured-Fixture")
			config_fixture.config_hash = self.config_hash
			config_fixture.fixture_template = self.template_code
			config_fixture.engine_version = "1.0.0"
			config_fixture.requested_overall_length_mm = 1000
			config_fixture.manufacturable_overall_length_mm = 995
			config_fixture.runs_count = 1
			config_fixture.total_watts = 15.5
			config_fixture.finish = "Silver"
			config_fixture.lens_appearance = "Clear"
			config_fixture.configured_item = self.item_code
			config_fixture.insert(ignore_permissions=True)

	def tearDown(self):
		"""Clean up test data"""
		# Delete test schedules
		test_schedules = frappe.get_all(
			"ilL-Project-Fixture-Schedule",
			filters={"schedule_name": ["like", "_Test%"]},
			pluck="name"
		)
		for schedule in test_schedules:
			frappe.delete_doc("ilL-Project-Fixture-Schedule", schedule, force=True)

		# Delete test sales orders
		test_orders = frappe.get_all(
			"Sales Order",
			filters={"customer": self.customer_name},
			pluck="name"
		)
		for order in test_orders:
			frappe.delete_doc("Sales Order", order, force=True)

		# Delete test configured fixtures created during tests
		test_config_hashes = ["_test_config_hash_22222222"]
		for config_hash in test_config_hashes:
			if frappe.db.exists("ilL-Configured-Fixture", config_hash):
				frappe.delete_doc("ilL-Configured-Fixture", config_hash, force=True)

		# Delete test configured tape/neon records created during tests
		test_ctn = frappe.get_all(
			"ilL-Configured-Tape-Neon",
			filters={"config_hash": ["like", "_test_ctn_hash%"]},
			pluck="name",
		)
		for ctn in test_ctn:
			frappe.delete_doc("ilL-Configured-Tape-Neon", ctn, force=True)

	def test_create_sales_order_basic(self):
		"""Test basic Sales Order creation from fixture schedule"""
		# Create a schedule with ILLUMENATE lines
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Basic"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 2,
			"location": "Office A",
			"notes": "Install above desk",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()

		# Verify Sales Order was created
		self.assertIsNotNone(so_name)
		so = frappe.get_doc("Sales Order", so_name)

		# Verify customer
		self.assertEqual(so.customer, self.customer_name)

		# Verify SO items
		self.assertEqual(len(so.items), 1)
		so_item = so.items[0]

		# Verify item code
		self.assertEqual(so_item.item_code, self.item_code)

		# Verify qty
		self.assertEqual(so_item.qty, 2)

		# Verify custom fields
		self.assertEqual(so_item.ill_configured_fixture, self.config_hash)
		self.assertEqual(so_item.ill_template_code, self.template_code)
		self.assertEqual(so_item.ill_requested_length_mm, 1000)
		self.assertEqual(so_item.ill_mfg_length_mm, 995)
		self.assertEqual(so_item.ill_runs_count, 1)
		self.assertEqual(so_item.ill_total_watts, 15.5)
		self.assertEqual(so_item.ill_finish, "Silver")
		self.assertEqual(so_item.ill_lens, "Clear")
		self.assertEqual(so_item.ill_engine_version, "1.0.0")

		# Verify schedule status was updated
		schedule.reload()
		self.assertEqual(schedule.status, "ORDERED")

	def test_create_sales_order_filters_illumenate_only(self):
		"""Test that only ILLUMENATE lines are included in the Sales Order"""
		# Create a schedule with mixed lines
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Mixed"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "READY"

		# ILLUMENATE line
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})

		# OTHER line (should be excluded)
		schedule.append("lines", {
			"line_id": "L2",
			"qty": 3,
			"manufacturer_type": "OTHER",
			"manufacturer_name": "Other Mfr",
			"model_number": "XYZ-123",
		})

		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()

		# Verify only ILLUMENATE line is included
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual(len(so.items), 1)
		self.assertEqual(so.items[0].ill_configured_fixture, self.config_hash)

	def test_create_sales_order_no_illumenate_lines_throws(self):
		"""Test that schedule with no ILLUMENATE lines throws an error"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule No ILL Lines"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"manufacturer_type": "OTHER",
			"manufacturer_name": "Other Mfr",
		})
		schedule.insert(ignore_permissions=True)

		# Attempt to create Sales Order - should throw
		with self.assertRaises(frappe.exceptions.ValidationError):
			schedule.create_sales_order()

	def test_create_sales_order_multiple_lines(self):
		"""Test Sales Order creation with multiple ILLUMENATE lines"""
		# Create another configured fixture
		config_hash_2 = "_test_config_hash_22222222"
		if not frappe.db.exists("ilL-Configured-Fixture", config_hash_2):
			config_fixture = frappe.new_doc("ilL-Configured-Fixture")
			config_fixture.config_hash = config_hash_2
			config_fixture.fixture_template = self.template_code
			config_fixture.engine_version = "1.0.0"
			config_fixture.requested_overall_length_mm = 2000
			config_fixture.manufacturable_overall_length_mm = 1995
			config_fixture.runs_count = 2
			config_fixture.total_watts = 31.0
			config_fixture.finish = "Black"
			config_fixture.lens_appearance = "Frosted"
			config_fixture.configured_item = self.item_code
			config_fixture.insert(ignore_permissions=True)

		# Create schedule with multiple ILLUMENATE lines
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Multi"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "READY"

		schedule.append("lines", {
			"line_id": "L1",
			"qty": 2,
			"location": "Room A",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.append("lines", {
			"line_id": "L2",
			"qty": 4,
			"location": "Room B",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": config_hash_2,
		})

		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()

		# Verify SO has both items
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual(len(so.items), 2)

		# Verify first item
		self.assertEqual(so.items[0].qty, 2)
		self.assertEqual(so.items[0].ill_configured_fixture, self.config_hash)
		self.assertEqual(so.items[0].ill_mfg_length_mm, 995)

		# Verify second item
		self.assertEqual(so.items[1].qty, 4)
		self.assertEqual(so.items[1].ill_configured_fixture, config_hash_2)
		self.assertEqual(so.items[1].ill_mfg_length_mm, 1995)

	def test_create_sales_order_description_includes_details(self):
		"""Location/fixture type move to dedicated fields, not the description."""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Description"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 1,
			"location": "Reception Desk",
			"notes": "Under cabinet mount",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.insert(ignore_permissions=True)

		# Create Sales Order
		so_name = schedule.create_sales_order()
		so = frappe.get_doc("Sales Order", so_name)

		# Description carries the build spec only
		description = so.items[0].description
		self.assertIn(self.template_code, description)
		self.assertNotIn("Location:", description)
		self.assertNotIn("Notes:", description)

		# Location / fixture type / notes live on dedicated fields
		self.assertEqual(so.items[0].ill_section_label, "Reception Desk")
		self.assertIn("Fixture Type: L1", so.items[0].additional_notes)
		self.assertIn("Under cabinet mount", so.items[0].additional_notes)

	def test_schedule_inherits_customer_from_project(self):
		"""Test that schedule auto-syncs customer from linked project"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Inherit Customer"
		schedule.ill_project = self.project.name
		# Intentionally leave customer blank
		schedule.customer = None
		schedule.insert(ignore_permissions=True)

		# Customer should be synced from project
		self.assertEqual(schedule.customer, self.customer_name)

	def test_duplicate_line(self):
		"""Test duplicate_line method"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Duplicate Line"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "DRAFT"
		schedule.append("lines", {
			"line_id": "L1",
			"qty": 3,
			"location": "Main Hall",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.insert(ignore_permissions=True)

		# Duplicate the line
		new_idx = schedule.duplicate_line(0)

		# Reload and verify
		schedule.reload()
		self.assertEqual(len(schedule.lines), 2)
		self.assertEqual(schedule.lines[1].qty, 3)
		self.assertEqual(schedule.lines[1].location, "Main Hall")
		self.assertIn("(copy)", schedule.lines[1].line_id)

	def test_request_quote(self):
		"""Test request_quote method"""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Request Quote"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "READY"
		schedule.insert(ignore_permissions=True)

		# Request quote
		schedule.request_quote()

		# Verify status changed
		schedule.reload()
		self.assertEqual(schedule.status, "QUOTED")

	# ── Versioning Tests ──────────────────────────────────────────────────

	def _create_schedule(self, name="_Test Schedule Versioning", status="DRAFT", with_line=True):
		"""Helper to create a test schedule."""
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = name
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = status
		if with_line:
			schedule.append("lines", {
				"line_id": "L1",
				"qty": 2,
				"location": "Main Hall",
				"manufacturer_type": "ILLUMENATE",
				"configured_fixture": self.config_hash,
			})
		schedule.insert(ignore_permissions=True)
		return schedule

	def test_create_new_version_creates_duplicate(self):
		"""Test that create_new_version duplicates the schedule with all lines."""
		schedule = self._create_schedule()

		new_name = schedule.create_new_version(version_notes="Testing v2")
		new_schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", new_name)

		# Verify basic fields are copied
		self.assertEqual(new_schedule.schedule_name, schedule.schedule_name)
		self.assertEqual(new_schedule.ill_project, schedule.ill_project)
		self.assertEqual(new_schedule.customer, schedule.customer)

		# Verify lines are deep-copied
		self.assertEqual(len(new_schedule.lines), len(schedule.lines))
		self.assertEqual(new_schedule.lines[0].line_id, "L1")
		self.assertEqual(new_schedule.lines[0].qty, 2)
		self.assertEqual(new_schedule.lines[0].location, "Main Hall")
		self.assertEqual(new_schedule.lines[0].configured_fixture, self.config_hash)

		# Verify version notes
		self.assertEqual(new_schedule.version_notes, "Testing v2")

	def test_create_new_version_locks_original(self):
		"""Test that create_new_version locks the original schedule."""
		schedule = self._create_schedule()

		schedule.create_new_version()
		schedule.reload()

		self.assertEqual(schedule.get("is_locked"), 1)
		self.assertIsNotNone(schedule.locked_at)
		self.assertIsNotNone(schedule.locked_by)

	def test_locked_schedule_cannot_be_modified(self):
		"""Test that a locked schedule cannot be saved."""
		schedule = self._create_schedule()

		# Create new version (which locks the original)
		schedule.create_new_version()
		schedule.reload()

		# Attempt to modify the locked schedule
		schedule.notes = "Trying to modify locked schedule"
		with self.assertRaises(frappe.exceptions.ValidationError):
			schedule.save()

	def test_locked_schedule_can_still_export(self):
		"""Test that a locked schedule can still be read (for exports)."""
		schedule = self._create_schedule()

		# Lock via versioning
		schedule.create_new_version()
		schedule.reload()

		# Read operations should still work
		self.assertTrue(schedule.get("is_locked"))
		self.assertEqual(len(schedule.lines), 1)
		self.assertEqual(schedule.lines[0].line_id, "L1")

	def test_version_number_increments(self):
		"""Test that version numbers increment correctly."""
		schedule = self._create_schedule()
		self.assertEqual(schedule.version or 1, 1)

		# Create v2
		v2_name = schedule.create_new_version()
		v2 = frappe.get_doc("ilL-Project-Fixture-Schedule", v2_name)
		self.assertEqual(v2.version, 2)
		self.assertEqual(v2.status, "DRAFT")

		# Create v3 from v2
		v3_name = v2.create_new_version()
		v3 = frappe.get_doc("ilL-Project-Fixture-Schedule", v3_name)
		self.assertEqual(v3.version, 3)

		# version_parent should always point to the original (v1)
		self.assertEqual(v2.version_parent, schedule.name)
		self.assertEqual(v3.version_parent, schedule.name)

	def test_version_history_returns_all_versions(self):
		"""Test that get_schedule_version_history returns all versions."""
		from illumenate_lighting.illumenate_lighting.api.portal import get_schedule_version_history

		schedule = self._create_schedule()

		# Create v2 and v3
		v2_name = schedule.create_new_version()
		v2 = frappe.get_doc("ilL-Project-Fixture-Schedule", v2_name)
		v3_name = v2.create_new_version()

		# Get history from v3's perspective
		result = get_schedule_version_history(v3_name)

		self.assertTrue(result["success"])
		self.assertEqual(len(result["versions"]), 3)

		# Should be ordered by version asc
		self.assertEqual(result["versions"][0]["version"] or 1, 1)
		self.assertEqual(result["versions"][1]["version"], 2)
		self.assertEqual(result["versions"][2]["version"], 3)

	# ── append_quote_lines: grouping fields & tape/neon modes ─────────────

	def _ensure_item(self, item_code, uom="Nos"):
		"""Create a simple non-stock test Item if missing."""
		if not frappe.db.exists("Item", item_code):
			item = frappe.new_doc("Item")
			item.item_code = item_code
			item.item_name = item_code
			item.item_group = "Products"
			item.stock_uom = uom
			item.is_stock_item = 0
			item.insert(ignore_permissions=True)
		return item_code

	def _ensure_configured_tape_neon(self):
		"""Create (once) a configured LED Tape record with an Item + MSRP."""
		config_hash = "_test_ctn_hash_11111111"
		existing = frappe.db.get_value(
			"ilL-Configured-Tape-Neon", {"config_hash": config_hash}, "name"
		)
		if existing:
			return frappe.get_doc("ilL-Configured-Tape-Neon", existing)

		template_code = "_Test Tape Neon Template"
		if not frappe.db.exists("ilL-Tape-Neon-Template", template_code):
			template = frappe.new_doc("ilL-Tape-Neon-Template")
			template.template_code = template_code
			template.template_name = "Test Tape Neon Template"
			template.product_category = "LED Tape"
			template.is_active = 1
			template.insert(ignore_permissions=True)

		self.ctn_item_code = self._ensure_item("_Test Configured Tape Item")

		ctn = frappe.new_doc("ilL-Configured-Tape-Neon")
		ctn.config_hash = config_hash
		ctn.product_category = "LED Tape"
		ctn.tape_neon_template = template_code
		ctn.engine_version = "1.0.0"
		ctn.part_number = "_TEST-CTN-0001"
		ctn.requested_length_mm = 3000
		ctn.manufacturable_length_mm = 2950
		ctn.total_watts = 42.5
		ctn.total_segments = 1
		ctn.lead_length_inches = 12
		ctn.configured_item = self.ctn_item_code
		ctn.append("pricing_snapshot", {"msrp_unit": 250.0})
		ctn.insert(ignore_permissions=True)
		return ctn

	def _tape_variant_selections(self):
		"""JSON payload matching what create_tape_neon_so_lines expects."""
		import json

		return json.dumps({
			"product_category": "LED Tape",
			"part_number": "_TEST-CTN-0001",
			"build_description": "Test tape build",
			"resolved_items": {
				"tape_item": self._ensure_item("_Test Tape Item", uom="Foot"),
				"leader_cable_item": self._ensure_item("_Test Leader Cable Item"),
			},
			"computed": {
				"lead_length_inches": 12,
				"manufacturable_length_in": 116,
			},
			"selections": {},
		})

	def _kit_variant_selections(self):
		"""JSON payload matching what create_kit_so_lines expects."""
		import json

		return json.dumps({
			"part_number": "_TEST-KIT-0001",
			"build_description": "Test kit build",
			"kit_composition": {
				"profile": {"item": self._ensure_item("_Test Kit Profile Item"), "qty": 1},
				"lens": {"item": self._ensure_item("_Test Kit Lens Item"), "qty": 1},
				"solid_endcap": {"item": self._ensure_item("_Test Kit Solid Endcap Item"), "qty": 2},
				"feed_through_endcap": {
					"item": self._ensure_item("_Test Kit Feed Endcap Item"), "qty": 2
				},
				"mounting": {"item": self._ensure_item("_Test Kit Mounting Item"), "qty": 6},
			},
		})

	def _new_quotation(self):
		"""An unsaved Quotation to append schedule rows onto."""
		quotation = frappe.new_doc("Quotation")
		quotation.quotation_to = "Customer"
		quotation.party_name = self.customer_name
		return quotation

	def _schedule_with_line(self, name, line):
		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = name
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "DRAFT"
		schedule.append("lines", line)
		schedule.insert(ignore_permissions=True)
		return schedule

	def test_append_quote_lines_tape_neon_configured_item(self):
		"""configured_item mode adds exactly one row for the configured SKU."""
		ctn = self._ensure_configured_tape_neon()
		schedule = self._schedule_with_line("_Test Schedule Tape Configured", {
			"line_id": "T1",
			"qty": 3,
			"location": "Lobby",
			"notes": "Cove detail",
			"manufacturer_type": "ILLUMENATE",
			"product_type": "LED Tape",
			"configured_tape_neon": ctn.name,
			"variant_selections": self._tape_variant_selections(),
		})

		quotation = self._new_quotation()
		counts = schedule.append_quote_lines(quotation, tape_neon_mode="configured_item")

		self.assertEqual(counts["rows_added"], 1)
		self.assertEqual(counts["tape_neon"], 1)

		row = quotation.items[0]
		self.assertEqual(row.item_code, ctn.configured_item)
		self.assertEqual(row.qty, 3)
		self.assertEqual(row.ill_configured_item, ctn.configured_item)
		self.assertEqual(row.ill_configured_tape_neon, ctn.name)
		self.assertEqual(row.ill_product_type, "LED Tape")
		self.assertEqual(row.ill_mfg_length_mm, 2950)
		self.assertEqual(row.ill_section_label, "Lobby")
		self.assertIn("Fixture Type: T1", row.additional_notes)

		# MSRP Item Price is ensured so the saved quotation picks up a rate
		price = frappe.db.get_value(
			"Item Price",
			{
				"item_code": ctn.configured_item,
				"selling": 1,
				"price_list": "Standard Selling",
			},
			"price_list_rate",
		)
		self.assertIsNotNone(price)
		self.assertAlmostEqual(float(price), 250.0, places=2)

	def test_append_quote_lines_tape_neon_raw_components_stamps_every_row(self):
		"""raw_components mode explodes the line and stamps all rows."""
		ctn = self._ensure_configured_tape_neon()
		schedule = self._schedule_with_line("_Test Schedule Tape Raw", {
			"line_id": "T2",
			"qty": 1,
			"location": "Corridor",
			"notes": "Continuous run",
			"manufacturer_type": "ILLUMENATE",
			"product_type": "LED Tape",
			"configured_tape_neon": ctn.name,
			"variant_selections": self._tape_variant_selections(),
		})

		quotation = self._new_quotation()
		counts = schedule.append_quote_lines(quotation, tape_neon_mode="raw_components")

		self.assertGreater(counts["rows_added"], 1)
		self.assertEqual(len(quotation.items), counts["rows_added"])
		for row in quotation.items:
			self.assertEqual(row.ill_section_label, "Corridor")
			self.assertIn("Fixture Type: T2", row.additional_notes)
			self.assertIn("Continuous run", row.additional_notes)

	def test_append_quote_lines_tape_neon_falls_back_without_configured_record(self):
		"""Missing configured_tape_neon falls back to raw components."""
		schedule = self._schedule_with_line("_Test Schedule Tape Fallback", {
			"line_id": "T3",
			"qty": 1,
			"location": "Stair",
			"manufacturer_type": "ILLUMENATE",
			"product_type": "LED Tape",
			"variant_selections": self._tape_variant_selections(),
		})

		quotation = self._new_quotation()
		counts = schedule.append_quote_lines(quotation, tape_neon_mode="configured_item")

		self.assertGreater(counts["rows_added"], 1)
		self.assertTrue(
			any("raw components" in msg for msg in counts["messages"])
		)

	def test_append_quote_lines_extrusion_kit_stamps_every_row(self):
		"""Every exploded kit component row carries location + fixture type."""
		schedule = self._schedule_with_line("_Test Schedule Kit", {
			"line_id": "K1",
			"qty": 1,
			"location": "Conference Room",
			"notes": "Recessed",
			"manufacturer_type": "ILLUMENATE",
			"product_type": "Extrusion Kit",
			"variant_selections": self._kit_variant_selections(),
		})

		quotation = self._new_quotation()
		counts = schedule.append_quote_lines(quotation)

		self.assertEqual(counts["kits"], 1)
		self.assertEqual(counts["rows_added"], 5)
		for row in quotation.items:
			self.assertEqual(row.ill_section_label, "Conference Room")
			self.assertIn("Fixture Type: K1", row.additional_notes)
			self.assertIn("Recessed", row.additional_notes)

	def test_append_quote_lines_fixture_and_accessory_group_fields(self):
		"""Fixture + accessory rows use dedicated fields, not the description."""
		accessory_item = self._ensure_item("_Test Accessory Driver Item")

		schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		schedule.schedule_name = "_Test Schedule Group Fields"
		schedule.ill_project = self.project.name
		schedule.customer = self.customer_name
		schedule.status = "DRAFT"
		schedule.append("lines", {
			"line_id": "A1",
			"qty": 2,
			"location": "Open Office",
			"notes": "Suspended",
			"manufacturer_type": "ILLUMENATE",
			"configured_fixture": self.config_hash,
		})
		schedule.append("lines", {
			"line_id": "PS1",
			"qty": 1,
			"location": "Electrical Room",
			"notes": "Remote driver",
			"manufacturer_type": "ACCESSORY",
			"accessory_item": accessory_item,
		})
		schedule.insert(ignore_permissions=True)

		quotation = self._new_quotation()
		counts = schedule.append_quote_lines(quotation, include_accessories=True)

		self.assertEqual(counts["fixtures"], 1)
		self.assertEqual(counts["accessories"], 1)
		self.assertEqual(counts["rows_added"], 2)

		fixture_row, accessory_row = quotation.items[0], quotation.items[1]

		self.assertEqual(fixture_row.ill_section_label, "Open Office")
		self.assertIn("Fixture Type: A1", fixture_row.additional_notes)
		self.assertIn("Suspended", fixture_row.additional_notes)
		self.assertNotIn("Location:", fixture_row.description or "")
		self.assertNotIn("Notes:", fixture_row.description or "")

		self.assertEqual(accessory_row.ill_section_label, "Electrical Room")
		self.assertIn("Fixture Type: PS1", accessory_row.additional_notes)
		self.assertIn("Remote driver", accessory_row.additional_notes)
		self.assertNotIn("Location:", accessory_row.description or "")

	def test_append_quote_lines_rejects_invalid_tape_neon_mode(self):
		"""An unknown tape_neon_mode is rejected."""
		schedule = self._create_schedule("_Test Schedule Bad Mode")
		quotation = self._new_quotation()

		with self.assertRaises(frappe.exceptions.ValidationError):
			schedule.append_quote_lines(quotation, tape_neon_mode="nope")

