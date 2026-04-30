# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Exports API
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestExportsAPI(FrappeTestCase):
	"""Test cases for the exports API."""

	def setUp(self):
		"""Set up test data."""
		# Create test customer
		if not frappe.db.exists("Customer", "Test Exports API Customer"):
			customer = frappe.new_doc("Customer")
			customer.customer_name = "Test Exports API Customer"
			customer.customer_type = "Company"
			customer.insert(ignore_permissions=True)

		# Create test project
		if not frappe.db.exists("ilL-Project", {"project_name": "Test Exports API Project"}):
			project = frappe.new_doc("ilL-Project")
			project.project_name = "Test Exports API Project"
			project.customer = "Test Exports API Customer"
			project.is_private = 0
			project.insert(ignore_permissions=True)
			self.project_name = project.name
		else:
			self.project_name = frappe.db.get_value(
				"ilL-Project", {"project_name": "Test Exports API Project"}, "name"
			)

		# Create test schedule with lines
		if not frappe.db.exists(
			"ilL-Project-Fixture-Schedule", {"schedule_name": "Test Exports API Schedule"}
		):
			schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
			schedule.schedule_name = "Test Exports API Schedule"
			schedule.ill_project = self.project_name
			schedule.customer = "Test Exports API Customer"
			schedule.append(
				"lines",
				{
					"line_id": "A",
					"qty": 2,
					"location": "Test Location",
					"manufacturer_type": "OTHER",
					"manufacturer_name": "Test Manufacturer",
					"model_number": "TM-100",
					"notes": "Test notes",
				},
			)
			schedule.insert(ignore_permissions=True)
			self.schedule_name = schedule.name
		else:
			self.schedule_name = frappe.db.get_value(
				"ilL-Project-Fixture-Schedule",
				{"schedule_name": "Test Exports API Schedule"},
				"name",
			)

	def test_check_schedule_access(self):
		"""Test schedule access check."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_check_schedule_access,
		)

		# Valid schedule with admin user should have access
		has_access, error = _check_schedule_access(self.schedule_name, "Administrator")
		self.assertTrue(has_access)
		self.assertIsNone(error)

		# Non-existent schedule should fail
		has_access, error = _check_schedule_access("NON-EXISTENT-SCHEDULE", "Administrator")
		self.assertFalse(has_access)
		self.assertIsNotNone(error)

	def test_check_pricing_permission_admin(self):
		"""Test pricing permission for admin user."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_check_pricing_permission,
		)

		# Administrator should have pricing permission
		has_permission = _check_pricing_permission("Administrator")
		self.assertTrue(has_permission)

	def test_create_export_job_function(self):
		"""Test _create_export_job function."""
		from illumenate_lighting.illumenate_lighting.api.exports import _create_export_job

		job_name = _create_export_job(
			self.schedule_name, "PDF_NO_PRICE", "Administrator"
		)

		self.assertIsNotNone(job_name)

		# Verify job was created
		job = frappe.get_doc("ilL-Export-Job", job_name)
		self.assertEqual(job.schedule, self.schedule_name)
		self.assertEqual(job.export_type, "PDF_NO_PRICE")
		self.assertEqual(job.status, "QUEUED")

	def test_get_schedule_data(self):
		"""Test _get_schedule_data function."""
		from illumenate_lighting.illumenate_lighting.api.exports import _get_schedule_data

		data = _get_schedule_data(self.schedule_name, include_pricing=False)

		self.assertIsNotNone(data)
		self.assertIn("schedule", data)
		self.assertIn("project", data)
		self.assertIn("customer", data)
		self.assertIn("lines", data)
		self.assertIn("export_date", data)

		# Verify lines data
		self.assertEqual(len(data["lines"]), 1)
		line = data["lines"][0]
		self.assertEqual(line["line_id"], "A")
		self.assertEqual(line["qty"], 2)
		self.assertEqual(line["manufacturer_type"], "OTHER")

	def test_generate_csv_content(self):
		"""Test _generate_csv_content function."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_generate_csv_content,
			_get_schedule_data,
		)

		schedule_data = _get_schedule_data(self.schedule_name, include_pricing=False)
		csv_content = _generate_csv_content(schedule_data, include_pricing=False)

		self.assertIsNotNone(csv_content)
		self.assertIn("Project", csv_content)
		self.assertIn("Schedule", csv_content)
		self.assertIn("Line ID", csv_content)
		self.assertIn("Test Manufacturer", csv_content)
		self.assertIn("TM-100", csv_content)

	def test_generate_pdf_content(self):
		"""Test _generate_pdf_content function."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_generate_pdf_content,
			_get_schedule_data,
		)

		schedule_data = _get_schedule_data(self.schedule_name, include_pricing=False)
		html_content = _generate_pdf_content(schedule_data, include_pricing=False)

		self.assertIsNotNone(html_content)
		self.assertIn("<html>", html_content)
		self.assertIn("Test Exports API Schedule", html_content)
		self.assertIn("Test Manufacturer", html_content)

	def test_get_export_history(self):
		"""Test get_export_history function."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			_create_export_job,
			get_export_history,
		)

		# Create some export jobs
		_create_export_job(self.schedule_name, "PDF_NO_PRICE", "Administrator")
		_create_export_job(self.schedule_name, "CSV_NO_PRICE", "Administrator")

		# Get export history
		result = get_export_history(self.schedule_name)

		self.assertTrue(result["success"])
		self.assertIn("exports", result)
		self.assertGreaterEqual(len(result["exports"]), 2)

	def test_check_pricing_permission_endpoint(self):
		"""Test check_pricing_permission endpoint."""
		from illumenate_lighting.illumenate_lighting.api.exports import (
			check_pricing_permission,
		)

		result = check_pricing_permission()

		self.assertIn("has_permission", result)
		# Admin should have permission
		self.assertTrue(result["has_permission"])

	def tearDown(self):
		"""Clean up test data."""
		# Delete test export jobs
		test_jobs = frappe.get_all(
			"ilL-Export-Job",
			filters={"schedule": self.schedule_name},
			pluck="name",
		)
		for job_name in test_jobs:
			frappe.delete_doc("ilL-Export-Job", job_name, force=True)

class TestDriverPricingInExports(FrappeTestCase):
	"""Test cases for driver/power supply pricing in exports."""

	def _make_schedule_data_with_driver_pricing(self):
		"""Build a schedule_data dict with driver pricing populated."""
		from types import SimpleNamespace

		schedule = SimpleNamespace(
			schedule_name="Test PS Pricing Schedule",
			status="Active",
			name="SCH-TEST-PS",
		)
		project = SimpleNamespace(project_name="Test PS Project")
		customer = SimpleNamespace(customer_name="Test PS Customer", name="CUST-PS")
		lines = [
			{
				"line_id": "A",
				"qty": 3,
				"location": "Lobby",
				"manufacturer_type": "ILLUMENATE",
				"notes": "",
				"template_code": "TPL-001",
				"configured_fixture_name": "CF-001",
				"config_summary": "Warm White",
				"requested_length_mm": 1000,
				"manufacturable_length_mm": 1016,
				"runs_count": 1,
				"environment_rating": "Dry",
				"finish": "White",
				"lens_appearance": "Frosted",
				"mounting_method": "Surface",
				"power_feed_type": "Single End",
				"cct": "3000K",
				"cri": "90",
				"output_level": "High",
				"estimated_delivered_output": "350",
				"power_supply": "DRV-100",
				"fixture_input_voltage": "24V",
				"driver_input_voltage": "120V",
				"total_watts": "25",
				"is_multi_segment": 0,
				"build_description": "",
				"unit_price": 100.00,
				"line_total": 300.00,
				"driver_unit_price": 45.50,
				"driver_line_total": 136.50,
			},
			{
				"line_id": "B",
				"qty": 1,
				"location": "Hallway",
				"manufacturer_type": "OTHER",
				"notes": "Other fixture",
				"template_code": "",
				"config_summary": "",
				"requested_length_mm": 0,
				"manufacturable_length_mm": 0,
				"runs_count": 0,
				"manufacturer_name": "Acme Lighting",
				"fixture_model_number": "ACM-200",
			},
		]
		return {
			"schedule": schedule,
			"project": project,
			"customer": customer,
			"lines": lines,
			"schedule_total": 436.50,
			"export_date": "2026-03-09",
		}

	def test_pdf_contains_driver_pricing_sub_line(self):
		"""Test that PDF content includes driver pricing sub-lines."""
		from illumenate_lighting.illumenate_lighting.api.exports import _generate_pdf_content

		schedule_data = self._make_schedule_data_with_driver_pricing()
		html = _generate_pdf_content(schedule_data, include_pricing=True)

		# Driver unit price sub-line should appear
		self.assertIn("pricing-sub-line", html)
		self.assertIn("$45.50", html)
		self.assertIn("$136.50", html)
		# Fixture price should also appear
		self.assertIn("$100.00", html)
		self.assertIn("$300.00", html)
		# Schedule total should include driver pricing
		self.assertIn("$436.50", html)

	def test_pdf_no_driver_pricing_when_not_priced(self):
		"""Test that non-priced PDF does not contain pricing."""
		from illumenate_lighting.illumenate_lighting.api.exports import _generate_pdf_content

		schedule_data = self._make_schedule_data_with_driver_pricing()
		html = _generate_pdf_content(schedule_data, include_pricing=False)

		# No pricing columns should appear
		self.assertNotIn("pricing-sub-line", html)
		self.assertNotIn("$45.50", html)
		self.assertNotIn("$100.00", html)

	def test_csv_contains_driver_pricing_columns(self):
		"""Test that CSV content includes PS Unit Price and PS Line Total columns."""
		from illumenate_lighting.illumenate_lighting.api.exports import _generate_csv_content

		schedule_data = self._make_schedule_data_with_driver_pricing()
		csv_content = _generate_csv_content(schedule_data, include_pricing=True)

		# PS pricing column headers should appear
		self.assertIn("PS Unit Price", csv_content)
		self.assertIn("PS Line Total", csv_content)
		# PS pricing values should appear for fixture line
		self.assertIn("45.50", csv_content)
		self.assertIn("136.50", csv_content)

	def test_csv_no_driver_pricing_when_not_priced(self):
		"""Test that non-priced CSV does not contain PS pricing columns."""
		from illumenate_lighting.illumenate_lighting.api.exports import _generate_csv_content

		schedule_data = self._make_schedule_data_with_driver_pricing()
		csv_content = _generate_csv_content(schedule_data, include_pricing=False)

		# PS pricing columns should not appear
		self.assertNotIn("PS Unit Price", csv_content)
		self.assertNotIn("PS Line Total", csv_content)

	def test_csv_other_manufacturer_no_ps_pricing(self):
		"""Test that OTHER manufacturer lines have empty PS pricing cells."""
		from illumenate_lighting.illumenate_lighting.api.exports import _generate_csv_content
		import csv
		import io

		schedule_data = self._make_schedule_data_with_driver_pricing()
		csv_content = _generate_csv_content(schedule_data, include_pricing=True)

		reader = csv.reader(io.StringIO(csv_content))
		rows = list(reader)
		headers = rows[0]
		ps_unit_idx = headers.index("PS Unit Price")
		ps_total_idx = headers.index("PS Line Total")

		# Line B (OTHER manufacturer) should have empty PS pricing
		line_b_row = rows[2]  # row 0=headers, 1=line A, 2=line B
		self.assertEqual(line_b_row[ps_unit_idx], "")
		self.assertEqual(line_b_row[ps_total_idx], "")

	def test_schedule_total_includes_driver_pricing(self):
		"""Test that schedule total in PDF includes both fixture and driver pricing."""
		from illumenate_lighting.illumenate_lighting.api.exports import _generate_pdf_content

		schedule_data = self._make_schedule_data_with_driver_pricing()
		html = _generate_pdf_content(schedule_data, include_pricing=True)

		# Schedule total = 300.00 (fixture) + 136.50 (driver) = 436.50
		self.assertIn("$436.50", html)
		self.assertIn("Schedule Total", html)


class TestSpecSheetExport(FrappeTestCase):
	"""Test cases for spec sheet CSV export restructuring."""

	def test_removed_columns_not_in_product_columns(self):
		"""Verify removed product columns are absent."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import PRODUCT_COLUMNS

		removed = [
			"series_name", "series_code", "template_code", "led_package_type",
			"profile_width_mm", "profile_height_mm", "profile_weight_per_meter_g",
			"max_assembled_length_mm", "fixture_weight_per_foot_g", "driver_input_voltage",
		]
		for col in removed:
			self.assertNotIn(col, PRODUCT_COLUMNS, f"{col} should have been removed from PRODUCT_COLUMNS")

	def test_removed_columns_not_in_variant_columns(self):
		"""Verify removed variant columns are absent."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import VARIANT_COLUMNS

		removed = [
			"cri_name", "cri_r9", "sdcm", "output_level",
			"cri_minimum_ra", "efficacy_lm_per_w", "tape_lumens_per_foot",
			"delivered_lumens_per_foot", "watts_per_foot", "max_run_length_ft",
		]
		for col in removed:
			self.assertNotIn(col, VARIANT_COLUMNS, f"{col} should have been removed from VARIANT_COLUMNS")

	def test_new_product_columns_present(self):
		"""Verify new product-level columns are included."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import PRODUCT_COLUMNS

		for col in ["sublabel", "profile_dimensions", "input_voltage"]:
			self.assertIn(col, PRODUCT_COLUMNS, f"{col} missing from PRODUCT_COLUMNS")

	def test_new_variant_columns_present(self):
		"""Verify new variant-level columns are present in VARIANT_COLUMNS."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import VARIANT_COLUMNS

		for col in ["cri_quality", "fixture_output_level", "production_interval"]:
			self.assertIn(col, VARIANT_COLUMNS, f"{col} missing from VARIANT_COLUMNS")

	def test_image_columns_count_and_names(self):
		"""Verify CUSTOM_SPEC_COLUMNS contains exactly 39 custom_* fields."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import CUSTOM_SPEC_COLUMNS

		self.assertEqual(len(CUSTOM_SPEC_COLUMNS), 39)
		for col in CUSTOM_SPEC_COLUMNS:
			self.assertTrue(col.startswith("custom_"), f"{col} must start with 'custom_'")
		# Spot-check a few known descriptive names
		self.assertIn("custom_image_illumenate_logo", CUSTOM_SPEC_COLUMNS)
		self.assertIn("custom_image_hero", CUSTOM_SPEC_COLUMNS)
		self.assertIn("custom_image_acc_dims_3", CUSTOM_SPEC_COLUMNS)
		self.assertIn("custom_component_1_title", CUSTOM_SPEC_COLUMNS)
		self.assertIn("custom_image_component_1_hero", CUSTOM_SPEC_COLUMNS)
		self.assertIn("custom_acc_5_title", CUSTOM_SPEC_COLUMNS)

	def test_image_columns_no_overlap(self):
		"""CUSTOM_SPEC_COLUMNS must not overlap with PRODUCT, VARIANT, or LENS columns."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			CUSTOM_SPEC_COLUMNS, PRODUCT_COLUMNS, VARIANT_COLUMNS, LENS_COLUMNS,
		)

		others = set(PRODUCT_COLUMNS + VARIANT_COLUMNS + LENS_COLUMNS)
		for col in CUSTOM_SPEC_COLUMNS:
			self.assertNotIn(col, others, f"{col} overlaps with another column set")

	def test_pivot_to_indesign_image_columns_present(self):
		"""Spec columns appear in InDesign headers using field names as labels."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign, INDESIGN_PRODUCT_COLUMNS, _INDESIGN_SPEC_MAP,
		)

		product_data = {
			"product_name": "Img Test", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": "",
			"custom_image_illumenate_logo": "https://example.com/img1.jpg",
			"custom_image_hero": "",
		}

		headers, data_row = _pivot_to_indesign(product_data, [])

		# Spec labels are part of INDESIGN_PRODUCT_COLUMNS (at the end of static block)
		spec_labels = [label for label, _field in _INDESIGN_SPEC_MAP]
		static_block = headers[:len(INDESIGN_PRODUCT_COLUMNS)]
		self.assertEqual(static_block[-len(spec_labels):], spec_labels)
		self.assertEqual(data_row["custom_image_illumenate_logo"], "https://example.com/img1.jpg")
		self.assertEqual(data_row["custom_image_hero"], "")
		self.assertEqual(data_row["custom_image_acc_dims_3"], "")

	def test_lens_slug(self):
		"""Test _lens_slug produces correct slugs."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _lens_slug

		self.assertEqual(_lens_slug("Clear"), "clear")
		self.assertEqual(_lens_slug("Frosted White"), "frosted_white")
		self.assertEqual(_lens_slug("  Opal  "), "opal")
		self.assertEqual(_lens_slug(None), "")
		self.assertEqual(_lens_slug(""), "")

	def test_build_lens_columns(self):
		"""Fixed 4 standard lens column groups are generated."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _build_lens_columns, LENS_COLUMNS

		cols = _build_lens_columns()

		expected = [
			"delivered_lumens_white", "watts_per_foot_white", "max_run_length_ft_white",
			"max_footage_per_100w_supply_white",
			"delivered_lumens_frosted", "watts_per_foot_frosted", "max_run_length_ft_frosted",
			"max_footage_per_100w_supply_frosted",
			"delivered_lumens_clear", "watts_per_foot_clear", "max_run_length_ft_clear",
			"max_footage_per_100w_supply_clear",
			"delivered_lumens_black", "watts_per_foot_black", "max_run_length_ft_black",
			"max_footage_per_100w_supply_black",
		]
		self.assertEqual(cols, expected)
		self.assertEqual(LENS_COLUMNS, expected)

	def test_standard_lenses_mapping(self):
		"""Verify STANDARD_LENSES maps codes to expected slugs."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import STANDARD_LENSES

		self.assertEqual(
			dict(STANDARD_LENSES),
			{"WH": "white", "FR": "frosted", "CL": "clear", "BK": "black"},
		)

	def test_format_production_interval(self):
		"""Test production interval formatting."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_production_interval

		tape_offering = SimpleNamespace(cut_increment_mm_override=0)
		tape_spec = SimpleNamespace(cut_increment_mm=50.0)
		result = _format_production_interval(tape_offering, tape_spec)
		self.assertIn("50mm", result)
		self.assertIn('"', result)  # should contain inches symbol

	def test_format_production_interval_override(self):
		"""Override on tape_offering takes precedence."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_production_interval

		tape_offering = SimpleNamespace(cut_increment_mm_override=25)
		tape_spec = SimpleNamespace(cut_increment_mm=50.0)
		result = _format_production_interval(tape_offering, tape_spec)
		self.assertIn("25mm", result)

	def test_format_production_interval_zero(self):
		"""Zero cut increment returns empty string."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_production_interval

		tape_offering = SimpleNamespace(cut_increment_mm_override=0)
		tape_spec = SimpleNamespace(cut_increment_mm=0)
		self.assertEqual(_format_production_interval(tape_offering, tape_spec), "")

	def test_format_production_interval_free_cutting(self):
		"""Free-cutting tape specs export a label instead of a numeric interval."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_production_interval

		tape_offering = SimpleNamespace(cut_increment_mm_override=25)
		tape_spec = SimpleNamespace(cut_increment_mm=50, is_free_cutting=1)
		self.assertEqual(_format_production_interval(tape_offering, tape_spec), "Free-Cutting")

	def test_format_cri_quality_full(self):
		"""CRI quality with cri_name and SDCM."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_cri_quality

		cri_doc = SimpleNamespace(cri_name="95 CRI")
		result = _format_cri_quality(cri_doc, 2)
		self.assertEqual(result, "95 CRI / 2 SDCM")

	def test_format_cri_quality_no_sdcm(self):
		"""CRI quality without SDCM."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_cri_quality

		cri_doc = SimpleNamespace(cri_name="90 CRI")
		result = _format_cri_quality(cri_doc, "")
		self.assertEqual(result, "90 CRI")

	def test_format_cri_quality_sdcm_only(self):
		"""SDCM only (no CRI doc) returns SDCM string."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_cri_quality

		self.assertEqual(_format_cri_quality(None, 3), "3 SDCM")

	def test_format_cri_quality_none(self):
		"""No CRI doc returns empty string."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _format_cri_quality

		self.assertEqual(_format_cri_quality(None, ""), "")

	def test_find_closest_fixture_level(self):
		"""Finds the output level closest to delivered lumens."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _find_closest_fixture_level

		levels = [
			{"name": "L1", "value": 200, "output_level_name": "Low"},
			{"name": "L2", "value": 400, "output_level_name": "Medium"},
			{"name": "L3", "value": 600, "output_level_name": "High"},
		]
		self.assertEqual(_find_closest_fixture_level(350, levels)["name"], "L2")
		self.assertEqual(_find_closest_fixture_level(100, levels)["name"], "L1")
		self.assertEqual(_find_closest_fixture_level(550, levels)["name"], "L3")
		self.assertIsNone(_find_closest_fixture_level(350, []))

	# ── InDesign pivot tests ──

	def test_parse_output_level_sort_key(self):
		"""Leading integer is extracted for sorting."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _parse_output_level_sort_key

		self.assertEqual(_parse_output_level_sort_key("200 lm/ft"), 200)
		self.assertEqual(_parse_output_level_sort_key("50 lm/ft"), 50)
		self.assertEqual(_parse_output_level_sort_key("High"), 0)
		self.assertEqual(_parse_output_level_sort_key(""), 0)
		self.assertEqual(_parse_output_level_sort_key(None), 0)

	def test_pivot_to_indesign_column_structure(self):
		"""Verify pivoted headers have fixed column count with expected columns."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign,
			INDESIGN_PRODUCT_COLUMNS,
			MAX_CCTS,
			MAX_OUTPUT_LEVELS,
		)

		product_data = {
			"product_name": "Test Product",
			"input_voltage": "24V",
			"certifications": "UL",
			"available_lenses": "White, Frosted",
			"available_finishes": "Silver",
			"profile_dimensions": "1×2×3",
			"minimum_side_bend_diameter": '3.94" (100mm)',
			"minimum_top_bend_diameter": '5.91" (150mm)',
		}

		variant_rows = [
			{
				"cct_name": "3000K", "cct_kelvin": 3000,
				"fixture_output_level": "200 lm/ft",
				"delivered_lumens_white": 190.0, "watts_per_foot_white": 4.5, "max_run_length_ft_white": 20,
				"delivered_lumens_frosted": 170.0, "watts_per_foot_frosted": 4.5, "max_run_length_ft_frosted": 20,
				"delivered_lumens_clear": 210.0, "watts_per_foot_clear": "", "max_run_length_ft_clear": "",
				"delivered_lumens_black": 160.0, "watts_per_foot_black": 4.5, "max_run_length_ft_black": 18,
			},
			{
				"cct_name": "4000K", "cct_kelvin": 4000,
				"fixture_output_level": "200 lm/ft",
				"delivered_lumens_white": 200.0, "watts_per_foot_white": 5.0, "max_run_length_ft_white": 18,
				"delivered_lumens_frosted": 180.0, "watts_per_foot_frosted": 5.0, "max_run_length_ft_frosted": 18,
				"delivered_lumens_clear": 220.0, "watts_per_foot_clear": "", "max_run_length_ft_clear": "",
				"delivered_lumens_black": 170.0, "watts_per_foot_black": 5.0, "max_run_length_ft_black": 16,
			},
			{
				"cct_name": "3000K", "cct_kelvin": 3000,
				"fixture_output_level": "400 lm/ft",
				"delivered_lumens_white": 390.0, "watts_per_foot_white": 9.0, "max_run_length_ft_white": 10,
				"delivered_lumens_frosted": 350.0, "watts_per_foot_frosted": 9.0, "max_run_length_ft_frosted": 10,
				"delivered_lumens_clear": "", "watts_per_foot_clear": "", "max_run_length_ft_clear": "",
				"delivered_lumens_black": "", "watts_per_foot_black": "", "max_run_length_ft_black": "",
			},
			{
				"cct_name": "4000K", "cct_kelvin": 4000,
				"fixture_output_level": "400 lm/ft",
				"delivered_lumens_white": 410.0, "watts_per_foot_white": 10.0, "max_run_length_ft_white": 9,
				"delivered_lumens_frosted": 370.0, "watts_per_foot_frosted": 10.0, "max_run_length_ft_frosted": 9,
				"delivered_lumens_clear": "", "watts_per_foot_clear": "", "max_run_length_ft_clear": "",
				"delivered_lumens_black": "", "watts_per_foot_black": "", "max_run_length_ft_black": "",
			},
		]

		headers, data_row = _pivot_to_indesign(product_data, variant_rows)

		# Fixed total: 58 static + 8 CCT + 336 output = 402
		self.assertEqual(len(headers), len(INDESIGN_PRODUCT_COLUMNS) + MAX_CCTS + MAX_OUTPUT_LEVELS * 42)

		# Static product columns come first
		for col in INDESIGN_PRODUCT_COLUMNS:
			self.assertIn(col, headers)

		# All 8 CCT columns present (even though only 2 have data)
		for i in range(1, MAX_CCTS + 1):
			self.assertIn(f"Light Color (CCT) {i}", headers)

		# All 8 output-level blocks present (even though only 2 have data)
		for j in range(1, MAX_OUTPUT_LEVELS + 1):
			self.assertIn(f"Output Options {j}", headers)

		# Per-output watt/run columns for lens groups
		self.assertIn("Watts per Foot (White Lens) 1", headers)
		self.assertIn("Max Run Length (White Lens) 1", headers)
		self.assertIn("Max Footage per 100W Supply (White Lens) 1", headers)
		self.assertIn("Watts per Foot (Black Lens) 1", headers)
		self.assertIn("Max Run Length (Other Lenses) 2", headers)
		self.assertIn("Max Footage per 100W Supply (Other Lenses) 2", headers)

		# Lumen columns per output × CCT (using full MAX_CCTS range)
		self.assertIn("White Lens - Output 1 - Lumen 1", headers)
		self.assertIn("Black Lens - Output 1 - Lumen 2", headers)
		self.assertIn("Frosted Lens - Output 2 - Lumen 1", headers)
		self.assertIn("Clear Lens - Output 2 - Lumen 2", headers)
		# Unused slots also present
		self.assertIn("White Lens - Output 8 - Lumen 8", headers)

	def test_pivot_to_indesign_values_and_aggregation(self):
		"""Verify aggregated values, suffixes, and lumen pass-through."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _pivot_to_indesign

		product_data = {
			"product_name": "Agg Test",
			"input_voltage": "24V",
			"certifications": "UL",
			"available_lenses": "White",
			"available_finishes": "Silver",
			"profile_dimensions": "1×2",
		}

		variant_rows = [
			{
				"cct_name": "3000K", "cct_kelvin": 3000,
				"fixture_output_level": "200 lm/ft",
				"delivered_lumens_white": 190.0, "watts_per_foot_white": 4.5, "max_run_length_ft_white": 20,
				"delivered_lumens_frosted": 170.0, "watts_per_foot_frosted": 4.5, "max_run_length_ft_frosted": 20,
				"delivered_lumens_clear": "", "watts_per_foot_clear": "", "max_run_length_ft_clear": "",
				"delivered_lumens_black": 160.0, "watts_per_foot_black": 4.0, "max_run_length_ft_black": 22,
			},
			{
				"cct_name": "4000K", "cct_kelvin": 4000,
				"fixture_output_level": "200 lm/ft",
				"delivered_lumens_white": 200.0, "watts_per_foot_white": 5.0, "max_run_length_ft_white": 18,
				"delivered_lumens_frosted": 180.0, "watts_per_foot_frosted": 5.0, "max_run_length_ft_frosted": 15,
				"delivered_lumens_clear": "", "watts_per_foot_clear": "", "max_run_length_ft_clear": "",
				"delivered_lumens_black": 170.0, "watts_per_foot_black": 5.0, "max_run_length_ft_black": 16,
			},
		]

		_headers, data_row = _pivot_to_indesign(product_data, variant_rows)

		# Static values
		self.assertEqual(data_row["Product Name"], "Agg Test")
		self.assertEqual(data_row["Input Voltage"], "24V")

		# CCT columns sorted by kelvin
		self.assertEqual(data_row["Light Color (CCT) 1"], "3000K")
		self.assertEqual(data_row["Light Color (CCT) 2"], "4000K")

		# Output options
		self.assertEqual(data_row["Output Options 1"], "200 lm/ft")

		# Watts per foot: max() across CCTs with "W" suffix
		# White: max(4.5, 5.0) = 5.0 → "5W"
		self.assertEqual(data_row["Watts per Foot (White Lens) 1"], "5W")
		# Black: max(4.0, 5.0) = 5.0 → "5W"
		self.assertEqual(data_row["Watts per Foot (Black Lens) 1"], "5W")
		# Other Lenses (frosted): max(4.5, 5.0) = 5.0 → "5W"
		self.assertEqual(data_row["Watts per Foot (Other Lenses) 1"], "5W")

		# Max run length: min() across CCTs with "ft" suffix
		# White: min(20, 18) = 18 → "18ft"
		self.assertEqual(data_row["Max Run Length (White Lens) 1"], "18ft")
		# Black: min(22, 16) = 16 → "16ft"
		self.assertEqual(data_row["Max Run Length (Black Lens) 1"], "16ft")
		# Other Lenses (frosted): min(20, 15) = 15 → "15ft"
		self.assertEqual(data_row["Max Run Length (Other Lenses) 1"], "15ft")

		# Max footage per 100W supply: 80W usable / max W/ft
		self.assertEqual(data_row["Max Footage per 100W Supply (White Lens) 1"], "16ft")
		self.assertEqual(data_row["Max Footage per 100W Supply (Black Lens) 1"], "16ft")
		self.assertEqual(data_row["Max Footage per 100W Supply (Other Lenses) 1"], "16ft")

		# Lumen pass-through (first value for each CCT × output)
		self.assertEqual(data_row["White Lens - Output 1 - Lumen 1"], 190.0)
		self.assertEqual(data_row["White Lens - Output 1 - Lumen 2"], 200.0)
		self.assertEqual(data_row["Black Lens - Output 1 - Lumen 1"], 160.0)
		self.assertEqual(data_row["Frosted Lens - Output 1 - Lumen 1"], 170.0)

	def test_pivot_to_indesign_empty_variant_rows(self):
		"""Pivot with no variant rows produces fixed columns (static + CCT + output blocks)."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign,
			INDESIGN_PRODUCT_COLUMNS,
			MAX_CCTS,
			MAX_OUTPUT_LEVELS,
		)

		product_data = {
			"product_name": "Empty", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": "",
		}

		headers, data_row = _pivot_to_indesign(product_data, [])

		# Fixed: 58 static + 8 CCT + 336 output = 402
		self.assertEqual(len(headers), len(INDESIGN_PRODUCT_COLUMNS) + MAX_CCTS + MAX_OUTPUT_LEVELS * 42)
		self.assertEqual(data_row["Product Name"], "Empty")

	def test_pivot_to_indesign_output_level_sort_order(self):
		"""Output levels are sorted by leading integer, not lexicographically."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign,
			INDESIGN_PRODUCT_COLUMNS,
			MAX_CCTS,
			MAX_OUTPUT_LEVELS,
		)

		product_data = {
			"product_name": "Sort Test", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": "",
		}

		variant_rows = [
			{"cct_name": "3000K", "cct_kelvin": 3000, "fixture_output_level": "400 lm/ft"},
			{"cct_name": "3000K", "cct_kelvin": 3000, "fixture_output_level": "50 lm/ft"},
			{"cct_name": "3000K", "cct_kelvin": 3000, "fixture_output_level": "200 lm/ft"},
		]

		headers, data_row = _pivot_to_indesign(product_data, variant_rows)

		# Fixed column count
		self.assertEqual(len(headers), len(INDESIGN_PRODUCT_COLUMNS) + MAX_CCTS + MAX_OUTPUT_LEVELS * 42)

		# Sorted by leading int: 50, 200, 400
		self.assertEqual(data_row["Output Options 1"], "50 lm/ft")
		self.assertEqual(data_row["Output Options 2"], "200 lm/ft")
		self.assertEqual(data_row["Output Options 3"], "400 lm/ft")

	# ── Part Number Builder tests ──

	def test_collect_pn_builder_columns_empty(self):
		"""Empty part_number_builder returns fixed 220 headers with empty data."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_collect_pn_builder_columns, STANDARD_PN_SECTIONS, MAX_PN_OPTIONS_PER_SECTION,
		)

		ft_doc = SimpleNamespace(part_number_builder=[])
		ft_doc.get = lambda key, default=None: getattr(ft_doc, key, default)
		headers, data = _collect_pn_builder_columns(ft_doc)
		self.assertEqual(len(headers), len(STANDARD_PN_SECTIONS) * MAX_PN_OPTIONS_PER_SECTION * 2)
		self.assertTrue(all(v == "" for v in data.values()))

	def test_collect_pn_builder_columns_none_doc(self):
		"""None ft_doc returns fixed 220 headers with empty data."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_collect_pn_builder_columns, STANDARD_PN_SECTIONS, MAX_PN_OPTIONS_PER_SECTION,
		)

		headers, data = _collect_pn_builder_columns(None)
		self.assertEqual(len(headers), len(STANDARD_PN_SECTIONS) * MAX_PN_OPTIONS_PER_SECTION * 2)
		self.assertTrue(all(v == "" for v in data.values()))

	def test_collect_pn_builder_columns_single_option_section(self):
		"""Single-option section uses numbered suffix (Option 1:)."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _collect_pn_builder_columns

		rows = [
			SimpleNamespace(section_name="Series", section_order=1, option_code="SH01", option_label="Shadow", option_order=1),
		]
		ft_doc = SimpleNamespace(part_number_builder=rows)
		ft_doc.get = lambda key, default=None: getattr(ft_doc, key, default)

		headers, data = _collect_pn_builder_columns(ft_doc)

		# Fixed 220 columns
		self.assertEqual(len(headers), 220)
		# Uses numbered suffix (breaking change from un-numbered)
		self.assertIn("Part Number - Series - Option 1:", headers)
		self.assertIn("Part Number - Series - Description 1:", headers)
		self.assertEqual(data["Part Number - Series - Option 1:"], "SH01")
		self.assertEqual(data["Part Number - Series - Description 1:"], "Shadow")
		# Unused slots are empty
		self.assertEqual(data["Part Number - Series - Option 2:"], "")

	def test_collect_pn_builder_columns_multi_option_section(self):
		"""Multi-option section uses numbered suffixes and fills correct slots."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _collect_pn_builder_columns

		rows = [
			SimpleNamespace(section_name="CCT", section_order=3, option_code="27K", option_label="2700K", option_order=1),
			SimpleNamespace(section_name="CCT", section_order=3, option_code="30K", option_label="3000K", option_order=2),
			SimpleNamespace(section_name="CCT", section_order=3, option_code="40K", option_label="4000K", option_order=3),
		]
		ft_doc = SimpleNamespace(part_number_builder=rows)
		ft_doc.get = lambda key, default=None: getattr(ft_doc, key, default)

		headers, data = _collect_pn_builder_columns(ft_doc)

		# Fixed 220 columns
		self.assertEqual(len(headers), 220)
		self.assertIn("Part Number - CCT - Option 1:", headers)
		self.assertIn("Part Number - CCT - Description 2:", headers)
		self.assertEqual(data["Part Number - CCT - Option 1:"], "27K")
		self.assertEqual(data["Part Number - CCT - Description 3:"], "4000K")
		# Slots beyond the 3 filled ones are empty
		self.assertEqual(data["Part Number - CCT - Option 4:"], "")

	def test_collect_pn_builder_columns_section_order(self):
		"""Sections are ordered by STANDARD_PN_SECTIONS, not data order."""
		from types import SimpleNamespace
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_collect_pn_builder_columns, STANDARD_PN_SECTIONS,
		)

		rows = [
			SimpleNamespace(section_name="Finish", section_order=7, option_code="BK", option_label="Black", option_order=1),
			SimpleNamespace(section_name="Series", section_order=1, option_code="SH01", option_label="Shadow", option_order=1),
		]
		ft_doc = SimpleNamespace(part_number_builder=rows)
		ft_doc.get = lambda key, default=None: getattr(ft_doc, key, default)

		headers, _data = _collect_pn_builder_columns(ft_doc)

		# Series comes before Finish in STANDARD_PN_SECTIONS
		series_idx = headers.index("Part Number - Series - Option 1:")
		finish_idx = headers.index("Part Number - Finish - Option 1:")
		self.assertLess(series_idx, finish_idx)

		# Verify order matches STANDARD_PN_SECTIONS order
		series_section_idx = STANDARD_PN_SECTIONS.index("Series")
		finish_section_idx = STANDARD_PN_SECTIONS.index("Finish")
		self.assertLess(series_section_idx, finish_section_idx)

	def test_pivot_to_indesign_with_pn_builder_columns(self):
		"""PN builder columns are appended at the end of the InDesign pivot (622 total)."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign, _collect_pn_builder_columns,
		)

		product_data = {
			"product_name": "PN Test", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": "",
		}

		pn_headers, pn_data = _collect_pn_builder_columns(None)
		# Populate one section
		pn_data["Part Number - Series - Option 1:"] = "SH01"
		pn_data["Part Number - Series - Description 1:"] = "Shadow"

		headers, data_row = _pivot_to_indesign(product_data, [], pn_builder_columns=(pn_headers, pn_data))

		# 402 (pivot) + 220 (PN) = 622
		self.assertEqual(len(headers), 622)
		# PN columns should be at the end
		self.assertTrue(headers[-1].startswith("Part Number"))
		self.assertEqual(data_row["Part Number - Series - Option 1:"], "SH01")
		self.assertEqual(data_row["Part Number - Series - Description 1:"], "Shadow")

	def test_pivot_to_indesign_without_pn_builder(self):
		"""Pivot without PN builder produces 402 columns (static + CCT + output blocks)."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign,
			INDESIGN_PRODUCT_COLUMNS,
			MAX_CCTS,
			MAX_OUTPUT_LEVELS,
		)

		product_data = {
			"product_name": "No PN", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": "",
		}

		headers, data_row = _pivot_to_indesign(product_data, [])

		# 58 static + 8 CCT + 336 output = 402
		self.assertEqual(len(headers), len(INDESIGN_PRODUCT_COLUMNS) + MAX_CCTS + MAX_OUTPUT_LEVELS * 42)
		# No Part Number columns
		self.assertFalse(any("Part Number" in h for h in headers))


class TestSpecSheetExportNeonInDesign(FrappeTestCase):
	"""Tape/Neon products must produce the same 622-column InDesign layout
	as Fixture Template products so marketing's data-merge template accepts
	both file types without column-shift garbage.
	"""

	def test_indesign_total_columns_constant(self):
		"""Sanity check on the shared guardrail constant."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			INDESIGN_TOTAL_COLUMNS, INDESIGN_PRODUCT_COLUMNS, MAX_CCTS, MAX_OUTPUT_LEVELS,
			STANDARD_PN_SECTIONS, MAX_PN_OPTIONS_PER_SECTION,
			_INDESIGN_LENS_GROUPS, _INDESIGN_LUMEN_LENSES,
		)

		output_block = 1 + len(_INDESIGN_LENS_GROUPS) * 3 + MAX_CCTS * len(_INDESIGN_LUMEN_LENSES)
		expected = (
			len(INDESIGN_PRODUCT_COLUMNS)
			+ MAX_CCTS
			+ MAX_OUTPUT_LEVELS * output_block
			+ len(STANDARD_PN_SECTIONS) * MAX_PN_OPTIONS_PER_SECTION * 2
		)
		self.assertEqual(INDESIGN_TOTAL_COLUMNS, 622)
		self.assertEqual(INDESIGN_TOTAL_COLUMNS, expected)

	def test_tn_pn_builder_empty_shape_matches_fixture(self):
		"""`_collect_tn_pn_builder_columns(None)` must yield the exact same
		220-column skeleton as the Fixture Template PN builder."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_collect_pn_builder_columns, _collect_tn_pn_builder_columns,
		)
		ft_headers, ft_data = _collect_pn_builder_columns(None)
		tn_headers, tn_data = _collect_tn_pn_builder_columns(None)
		self.assertEqual(tn_headers, ft_headers)
		self.assertEqual(len(tn_headers), 220)
		self.assertTrue(all(v == "" for v in tn_data.values()))

	def test_pivot_header_parity_with_fixture(self):
		"""Passing the neon PN shim into the same pivoter must yield an
		identical 622-column header list to the fixture export."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign, _collect_pn_builder_columns,
			_collect_tn_pn_builder_columns, INDESIGN_TOTAL_COLUMNS,
		)

		product_data = {
			"product_name": "Hdr", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": "",
		}
		fixture_headers, _ = _pivot_to_indesign(
			product_data, [], _collect_pn_builder_columns(None)
		)
		neon_headers, _ = _pivot_to_indesign(
			product_data, [], _collect_tn_pn_builder_columns(None)
		)
		self.assertEqual(neon_headers, fixture_headers)
		self.assertEqual(len(neon_headers), INDESIGN_TOTAL_COLUMNS)

	def test_tn_pn_builder_maps_option_types_to_standard_sections(self):
		"""allowed_options option_types are routed to STANDARD_PN_SECTIONS
		via the documented mapping (CCT→CCT, Output Level→Output,
		Lens Appearance→Lens, Environment Rating / IP Rating→Dry/Wet,
		Mounting Method→Mounting, Finish / PCB Finish→Finish)."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		# Fake attribute docs keyed by (doctype, name).
		attr_fixtures = {
			("ilL-Attribute-Series", "NT01"): SimpleNamespace(code="NT01", series_name="NeonOne"),
			("ilL-Attribute-CCT", "3000K"): SimpleNamespace(code="30K", label="3000K"),
			("ilL-Attribute-CCT", "4000K"): SimpleNamespace(code="40K", label="4000K"),
			("ilL-Attribute-Output Level", "200lm"): SimpleNamespace(
				code="02", output_level_name="200 lm/ft",
			),
			("ilL-Attribute-Lens Appearance", "Frosted"): SimpleNamespace(
				code="FR", label="Frosted",
			),
			("ilL-Attribute-IP Rating", "IP67"): SimpleNamespace(code="67", label="IP67"),
			("ilL-Attribute-Mounting Method", "Surface"): SimpleNamespace(
				code="SM", label="Surface Mount", mounting_method="Surface",
			),
			("ilL-Attribute-Finish", "Black"): SimpleNamespace(
				code="BK", finish_name="Black", label="Black",
			),
		}

		def fake_get_cached_doc(doctype, name):
			doc = attr_fixtures.get((doctype, name))
			if doc is None:
				raise sse.frappe.DoesNotExistError(f"{doctype} {name} not found")
			return doc

		allowed_options = [
			SimpleNamespace(option_type="CCT", cct="3000K", is_active=1),
			SimpleNamespace(option_type="CCT", cct="4000K", is_active=1),
			SimpleNamespace(option_type="Output Level", output_level="200lm", is_active=1),
			SimpleNamespace(option_type="Lens Appearance", lens_appearance="Frosted", is_active=1),
			SimpleNamespace(option_type="IP Rating", ip_rating="IP67", is_active=1),
			SimpleNamespace(option_type="Mounting Method", mounting_method="Surface", is_active=1),
			SimpleNamespace(option_type="Finish", finish="Black", is_active=1),
		]
		tnt_doc = SimpleNamespace(series="NT01", allowed_options=allowed_options)
		tnt_doc.template_code = "non-crb"
		tnt_doc.template_name = "Carbon Single-Bending"

		with patch.object(sse.frappe, "get_cached_doc", side_effect=fake_get_cached_doc), \
			 patch.object(sse.frappe.db, "has_column", return_value=True):
			headers, data = sse._collect_tn_pn_builder_columns(tnt_doc)

		self.assertEqual(len(headers), 220)
		# Series is filled from the full tape/neon template slug/code, not the shorter Series code.
		self.assertEqual(data["Part Number - Series - Option 1:"], "NON-CRB")
		self.assertEqual(data["Part Number - Series - Description 1:"], "Carbon Single-Bending")
		# CCT: two distinct entries
		self.assertEqual(data["Part Number - CCT - Option 1:"], "30K")
		self.assertEqual(data["Part Number - CCT - Option 2:"], "40K")
		# Output
		self.assertEqual(data["Part Number - Output - Option 1:"], "02")
		# Lens Appearance → Lens
		self.assertEqual(data["Part Number - Lens - Option 1:"], "FR")
		# IP Rating → Dry/Wet
		self.assertEqual(data["Part Number - Dry/Wet - Option 1:"], "67")
		# Mounting
		self.assertEqual(data["Part Number - Mounting - Option 1:"], "SM")
		# Finish
		self.assertEqual(data["Part Number - Finish - Option 1:"], "BK")
		self.assertEqual(data["Part Number - Lens - Description 1:"], "Frosted")

	def test_tn_pn_builder_feed_position_fanout(self):
		"""Feed Direction rows fan out to Start / End Feed Type based on
		`feed_position` (Both emits into both buckets)."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		attrs = {
			("ilL-Attribute-Feed-Direction", "Start-A"): SimpleNamespace(
				code="SA", direction_name="Start A",
			),
			("ilL-Attribute-Feed-Direction", "End-B"): SimpleNamespace(
				code="EB", direction_name="End B",
			),
			("ilL-Attribute-Feed-Direction", "Both-C"): SimpleNamespace(
				code="BC", direction_name="Both C",
			),
		}

		def fake_gcd(doctype, name):
			return attrs[(doctype, name)]

		tnt_doc = SimpleNamespace(
			series=None,
			allowed_options=[
				SimpleNamespace(option_type="Feed Direction", feed_direction="Start-A",
				                feed_position="Start", is_active=1),
				SimpleNamespace(option_type="Feed Direction", feed_direction="End-B",
				                feed_position="End", is_active=1),
				SimpleNamespace(option_type="Feed Direction", feed_direction="Both-C",
				                feed_position="Both", is_active=1),
			],
		)

		with patch.object(sse.frappe, "get_cached_doc", side_effect=fake_gcd), \
			 patch.object(sse.frappe.db, "has_column", return_value=True):
			_h, data = sse._collect_tn_pn_builder_columns(tnt_doc)

		# Start-A goes only to Start
		self.assertEqual(data["Part Number - Start Feed Type - Option 1:"], "SA")
		# End-B goes only to End
		self.assertEqual(data["Part Number - End Feed Type - Option 1:"], "EB")
		# Both-C appears in both
		self.assertIn("BC", [data["Part Number - Start Feed Type - Option 2:"],
		                      data["Part Number - Start Feed Type - Option 1:"]])
		self.assertIn("BC", [data["Part Number - End Feed Type - Option 2:"],
		                      data["Part Number - End Feed Type - Option 1:"]])

	def test_tn_pn_builder_inactive_options_skipped(self):
		"""Options with is_active=0 must not occupy a slot."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		attrs = {
			("ilL-Attribute-CCT", "3000K"): SimpleNamespace(code="30K", label="3000K"),
			("ilL-Attribute-CCT", "4000K"): SimpleNamespace(code="40K", label="4000K"),
		}
		tnt_doc = SimpleNamespace(series=None, allowed_options=[
			SimpleNamespace(option_type="CCT", cct="3000K", is_active=0),
			SimpleNamespace(option_type="CCT", cct="4000K", is_active=1),
		])
		with patch.object(sse.frappe, "get_cached_doc",
		                  side_effect=lambda dt, n: attrs[(dt, n)]), \
			 patch.object(sse.frappe.db, "has_column", return_value=True):
			_h, data = sse._collect_tn_pn_builder_columns(tnt_doc)

		# Only the active CCT is filled into slot 1
		self.assertEqual(data["Part Number - CCT - Option 1:"], "40K")
		self.assertEqual(data["Part Number - CCT - Option 2:"], "")

	def test_tn_option_label_code_uses_output_sku_code(self):
		"""Output Level PN options use sku_code when the attribute has no code field."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		def fake_has_column(_doctype, fieldname):
			return fieldname == "sku_code"

		with patch.object(
			sse.frappe,
			"get_cached_doc",
			return_value=SimpleNamespace(sku_code="HO", output_level_name="High Output"),
		), patch.object(sse.frappe.db, "has_column", side_effect=fake_has_column):
			code, label = sse._tn_option_label_code(
				SimpleNamespace(option_type="Output Level", output_level="High")
			)

		self.assertEqual(code, "HO")
		self.assertEqual(label, "High Output")

	def test_tape_neon_product_data_fills_template_driver_and_media_fields(self):
		"""Tape/neon product columns pull from template specs, options, drivers, and media fallbacks."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		wp_doc = SimpleNamespace(
			name="WP-NEON", tape_neon_template="TNT-1", product_type="LED Tape",
			product_name="Tape Product", short_description="Short", sublabel="Sub",
			beam_angle=120, operating_temp_min_c=-20, operating_temp_max_c=45,
			l70_life_hours=50000, warranty_years=5,
			attribute_links=[],
			certifications=[SimpleNamespace(certification="ETL")],
			featured_image="", series_family_image="", dimensions_image="/files/dims.png",
		)
		wp_doc.get = lambda fieldname, default=None: getattr(wp_doc, fieldname, default)

		tnt_doc = SimpleNamespace(
			name="TNT-1", template_code="TN01", image="/files/template-hero.png",
			default_tape_spec="TS-1",
			allowed_tape_specs=[SimpleNamespace(tape_spec="TS-1", environment_rating="Wet")],
			allowed_options=[
				SimpleNamespace(option_type="PCB Mounting", pcb_mounting="Adhesive", is_active=1),
				SimpleNamespace(option_type="PCB Finish", pcb_finish="White PCB", is_active=1),
			],
		)
		tape_doc = SimpleNamespace(
			input_voltage="24V Attribute", input_protocol="ELV",
			supported_dimming_protocols=[SimpleNamespace(protocol="PWM")],
		)
		driver_doc = SimpleNamespace(
			input_voltage_min=120, input_voltage_max=277, input_voltage_type="VAC",
			max_wattage=96,
			input_protocols=[SimpleNamespace(protocol="0-10V")],
		)

		def fake_get_cached_doc(doctype, name):
			if doctype == "ilL-Tape-Neon-Template" and name == "TNT-1":
				return tnt_doc
			if doctype == "ilL-Spec-LED Tape" and name == "TS-1":
				return tape_doc
			if doctype == "ilL-Spec-Driver" and name == "DRV-1":
				return driver_doc
			raise sse.frappe.DoesNotExistError(f"{doctype} {name}")

		def fake_get_all(doctype, **kwargs):
			if doctype == "ilL-Rel-Driver-Eligibility":
				return [SimpleNamespace(driver_spec="DRV-1")]
			return []

		def fake_get_value(doctype, name, fieldname, as_dict=False):
			if doctype == "ilL-Attribute-Output Voltage":
				return {"dc_voltage": "24V", "ac_voltage": ""}
			return None

		with patch.object(sse.frappe, "get_cached_doc", side_effect=fake_get_cached_doc), \
			 patch.object(sse.frappe, "get_all", side_effect=fake_get_all), \
			 patch.object(sse.frappe.db, "get_value", side_effect=fake_get_value), \
			 patch.object(sse, "get_url", side_effect=lambda url: f"https://erp.test{url}"):
			data = sse._collect_tape_neon_product_data_indesign(wp_doc)

		self.assertEqual(data["input_voltage"], "24VDC (Power Supply: 120V-277VAC)")
		self.assertEqual(data["available_mountings"], "Adhesive")
		self.assertEqual(data["available_finishes"], "White PCB")
		self.assertEqual(data["environment_ratings"], "Wet")
		self.assertEqual(data["certifications"], "ETL")
		self.assertEqual(data["dimming_protocols"], "0-10V, ELV, PWM")
		self.assertEqual(data["driver_max_wattage"], 96)
		self.assertEqual(data["custom_image_hero"], "https://erp.test/files/template-hero.png")
		self.assertEqual(data["custom_image_dimensions_1"], "https://erp.test/files/dims.png")

	def test_tape_neon_product_data_uses_spec_sheet_fallback_fields(self):
		"""Template spec-sheet fields fill CSV columns when structured relationships are sparse."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		wp_doc = SimpleNamespace(
			name="WP-NEON-FALLBACK", tape_neon_template="TNT-FALLBACK", product_type="LED Neon",
			product_name="Fallback Neon", short_description="", sublabel="",
			beam_angle=None, operating_temp_min_c=None, operating_temp_max_c=None,
			l70_life_hours=None, warranty_years=None,
			attribute_links=[], certifications=[],
			featured_image="", series_family_image="", dimensions_image="",
		)
		wp_doc.get = lambda fieldname, default=None: getattr(wp_doc, fieldname, default)

		tnt_doc = SimpleNamespace(
			name="TNT-FALLBACK", template_code="TN-FB", image="",
			default_tape_spec=None, allowed_tape_specs=[],
			allowed_options=[
				SimpleNamespace(option_type="Lens Appearance", lens_appearance="Frosted", is_active=1),
				SimpleNamespace(option_type="Mounting Method", mounting_method="Channel", is_active=1),
				SimpleNamespace(option_type="Finish", finish="Carbon", is_active=1),
			],
			spec_sheet_dimensions='0.63" W x 0.75" H',
			minimum_side_bend_diameter_mm=100,
			minimum_top_bend_diameter_mm=150,
			available_lenses="Soft diffused",
			available_finishes="Carbon",
			available_mountings="3M Adhesive Back",
			driver_max_wattage_override=60,
			production_interval_mm=50,
			certifications=[SimpleNamespace(certification="UL")],
		)

		attrs = {
			("ilL-Attribute-Lens Appearance", "Frosted"): SimpleNamespace(code="FR", label="Frosted"),
			("ilL-Attribute-Mounting Method", "Channel"): SimpleNamespace(
				code="CH", label="Channel Mount",
			),
			("ilL-Attribute-Finish", "Carbon"): SimpleNamespace(code="CB", finish_name="Carbon"),
		}

		def fake_get_cached_doc(doctype, name):
			if doctype == "ilL-Tape-Neon-Template" and name == "TNT-FALLBACK":
				return tnt_doc
			doc = attrs.get((doctype, name))
			if doc:
				return doc
			raise sse.frappe.DoesNotExistError(f"{doctype} {name}")

		with patch.object(sse.frappe, "get_cached_doc", side_effect=fake_get_cached_doc), \
			 patch.object(sse.frappe, "get_all", return_value=[]), \
			 patch.object(sse.frappe.db, "has_column", return_value=True):
			data = sse._collect_tape_neon_product_data_indesign(wp_doc)

		self.assertEqual(data["profile_dimensions"], '0.63" W x 0.75" H')
		self.assertIn("100mm", data["minimum_side_bend_diameter"])
		self.assertIn("150mm", data["minimum_top_bend_diameter"])
		self.assertEqual(data["available_lenses"], "Frosted, Soft diffused")
		self.assertEqual(data["available_finishes"], "Carbon")
		self.assertEqual(data["available_mountings"], "3M Adhesive Back, Channel Mount")
		self.assertEqual(data["certifications"], "UL")
		self.assertEqual(data["driver_max_wattage"], 60)
		self.assertIn("50mm", data["production_interval"])

	def test_tape_neon_product_data_exports_free_cutting_label(self):
		"""Template free-cutting flag wins over the numeric production interval fallback."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		wp_doc = SimpleNamespace(
			name="WP-FREE-CUT", tape_neon_template="TNT-FREE-CUT", product_type="LED Neon",
			product_name="Free Cut Neon", short_description="", sublabel="",
			beam_angle=None, operating_temp_min_c=None, operating_temp_max_c=None,
			l70_life_hours=None, warranty_years=None,
			attribute_links=[], certifications=[], featured_image="",
			series_family_image="", dimensions_image="",
		)
		wp_doc.get = lambda fieldname, default=None: getattr(wp_doc, fieldname, default)

		tnt_doc = SimpleNamespace(
			name="TNT-FREE-CUT", template_code="TN-FC", image="",
			default_tape_spec=None, allowed_tape_specs=[], allowed_options=[],
			production_interval_mm=50, is_free_cutting=1,
		)

		with patch.object(sse.frappe, "get_cached_doc", return_value=tnt_doc), \
			 patch.object(sse.frappe, "get_all", return_value=[]):
			data = sse._collect_tape_neon_product_data_indesign(wp_doc)

		self.assertEqual(data["production_interval"], "Free-Cutting")

	def test_pivot_uses_product_production_interval_fallback(self):
		"""Product-level production interval is used when rows do not carry one."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _pivot_to_indesign

		product_data = {
			"product_name": "Fallback Interval",
			"production_interval": '1.97" (50mm)',
		}
		_headers, data = _pivot_to_indesign(product_data, [{"fixture_output_level": "", "cct_name": ""}])

		self.assertEqual(data["Production Interval"], '1.97" (50mm)')

	def test_tape_neon_variant_rows_use_matching_tape_offerings(self):
		"""Tape/neon variant rows are populated per actual CCT/output offering."""
		from types import SimpleNamespace
		from unittest.mock import patch
		from illumenate_lighting.illumenate_lighting.api import spec_sheet_export as sse

		wp_doc = SimpleNamespace(tape_neon_template="TNT-1")
		tnt_doc = SimpleNamespace(
			name="TNT-1",
			default_tape_spec="TS-LOW",
			allowed_tape_specs=[
				SimpleNamespace(tape_spec="TS-LOW"),
				SimpleNamespace(tape_spec="TS-HIGH"),
			],
			allowed_options=[
				SimpleNamespace(option_type="CCT", cct="3000K", is_active=1),
				SimpleNamespace(option_type="Output Level", output_level="Low", is_active=1),
				SimpleNamespace(option_type="Output Level", output_level="High", is_active=1),
			],
		)
		offerings = [
			SimpleNamespace(
				name="TO-LOW", tape_spec="TS-LOW", cct="3000K", cri="CRI90",
				sdcm="SDCM2", led_package="PKG", output_level="Low",
				watts_per_ft_override=4.2, cut_increment_mm_override=25,
			),
			SimpleNamespace(
				name="TO-HIGH", tape_spec="TS-HIGH", cct="3000K", cri="CRI90",
				sdcm="SDCM2", led_package="PKG", output_level="High",
				watts_per_ft_override=0, cut_increment_mm_override=0,
			),
		]
		tape_docs = {
			"TS-LOW": SimpleNamespace(
				lumens_per_foot=180, watts_per_foot=3.5, voltage_drop_max_run_length_ft=20,
				cut_increment_mm=50, led_pitch_mm=8, led_package="PKG", cri_typical=90,
			),
			"TS-HIGH": SimpleNamespace(
				lumens_per_foot=400, watts_per_foot=8.0, voltage_drop_max_run_length_ft=12,
				cut_increment_mm=50, led_pitch_mm=6, led_package="PKG", cri_typical=90,
			),
		}

		def fake_get_cached_doc(doctype, name):
			if doctype == "ilL-Tape-Neon-Template" and name == "TNT-1":
				return tnt_doc
			if doctype == "ilL-Spec-LED Tape":
				return tape_docs[name]
			if doctype == "ilL-Attribute-CRI":
				return SimpleNamespace(cri_name="90 CRI")
			if doctype == "ilL-Attribute-SDCM":
				return SimpleNamespace(sdcm=2)
			raise sse.frappe.DoesNotExistError(f"{doctype} {name}")

		def fake_get_all(doctype, **kwargs):
			if doctype == "ilL-Rel-Tape Offering":
				return offerings
			return []

		def fake_get_value(doctype, name, fieldname, as_dict=False):
			if doctype == "ilL-Attribute-CCT":
				return {"kelvin": 3000, "lumen_multiplier": 0.95}
			if doctype == "ilL-Attribute-Output Level" and name == "Low":
				return {"output_level_name": "180 lm/ft", "value": 180, "sku_code": "LO"}
			if doctype == "ilL-Attribute-Output Level" and name == "High":
				return {"output_level_name": "400 lm/ft", "value": 400, "sku_code": "HI"}
			return None

		with patch.object(sse.frappe, "get_cached_doc", side_effect=fake_get_cached_doc), \
			 patch.object(sse.frappe, "get_all", side_effect=fake_get_all), \
			 patch.object(sse.frappe.db, "get_value", side_effect=fake_get_value):
			rows = list(sse._collect_tape_neon_variant_rows_indesign(wp_doc, {"product_name": "Tape"}))

		self.assertEqual(len(rows), 2)
		low = rows[0]
		high = rows[1]
		self.assertEqual(low["fixture_output_level"], "180 lm/ft")
		self.assertEqual(low["delivered_lumens_frosted"], 171.0)
		self.assertEqual(low["watts_per_foot_frosted"], 4.2)
		self.assertEqual(low["max_run_length_ft_frosted"], 20)
		self.assertEqual(low["max_footage_per_100w_supply_frosted"], 19.0)
		self.assertIn("25mm", low["production_interval"])
		self.assertEqual(low["cri_quality"], "90 CRI / 2 SDCM")
		self.assertEqual(low["delivered_lumens_white"], "")
		self.assertEqual(high["fixture_output_level"], "400 lm/ft")
		self.assertEqual(high["delivered_lumens_frosted"], 380.0)
		self.assertEqual(high["watts_per_foot_frosted"], 8.0)
		self.assertEqual(high["max_run_length_ft_frosted"], 12)
		self.assertEqual(high["max_footage_per_100w_supply_frosted"], 10.0)


class TestSpecSheetExportTapeNeonRouting(FrappeTestCase):
	"""Router must default LED Tape / LED Neon to the InDesign schema and
	reserve the legacy flat layout for ``format='tape_neon_flat'``."""

	def test_legacy_flat_helper_kept_as_alias(self):
		"""`_generate_tape_neon_csv` remains importable as an alias for
		back-compat (any existing downstream caller keeps working)."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_generate_tape_neon_csv, _generate_tape_neon_flat_csv,
		)
		# Both symbols should exist; one delegates to the other.
		self.assertTrue(callable(_generate_tape_neon_csv))
		self.assertTrue(callable(_generate_tape_neon_flat_csv))

	def test_tape_neon_indesign_generator_exists(self):
		"""The new unified generator must be importable."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_generate_tape_neon_indesign_csv,
			_collect_tape_neon_product_data_indesign,
			_collect_tape_neon_variant_rows_indesign,
		)
		self.assertTrue(callable(_generate_tape_neon_indesign_csv))
		self.assertTrue(callable(_collect_tape_neon_product_data_indesign))
		self.assertTrue(callable(_collect_tape_neon_variant_rows_indesign))
