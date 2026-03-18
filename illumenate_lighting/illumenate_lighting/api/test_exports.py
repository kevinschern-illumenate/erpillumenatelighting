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

		for col in ["long_description", "sublabel", "profile_dimensions", "input_voltage"]:
			self.assertIn(col, PRODUCT_COLUMNS, f"{col} missing from PRODUCT_COLUMNS")

	def test_new_variant_columns_present(self):
		"""Verify new variant-level columns are present in VARIANT_COLUMNS."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import VARIANT_COLUMNS

		for col in ["cri_quality", "fixture_output_level", "production_interval"]:
			self.assertIn(col, VARIANT_COLUMNS, f"{col} missing from VARIANT_COLUMNS")

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
			"delivered_lumens_frosted", "watts_per_foot_frosted", "max_run_length_ft_frosted",
			"delivered_lumens_clear", "watts_per_foot_clear", "max_run_length_ft_clear",
			"delivered_lumens_black", "watts_per_foot_black", "max_run_length_ft_black",
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
		"""Verify pivoted headers contain expected dynamic columns."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign,
			INDESIGN_PRODUCT_COLUMNS,
		)

		product_data = {
			"product_name": "Test Product",
			"input_voltage": "24V",
			"certifications": "UL",
			"available_lenses": "White, Frosted",
			"available_finishes": "Silver",
			"profile_dimensions": "1×2×3",
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

		# Static product columns come first
		for col in INDESIGN_PRODUCT_COLUMNS:
			self.assertIn(col, headers)

		# 2 CCTs → 2 Light Color columns
		self.assertIn("Light Color (CCT) 1", headers)
		self.assertIn("Light Color (CCT) 2", headers)

		# 2 output levels → Output Options 1, 2
		self.assertIn("Output Options 1", headers)
		self.assertIn("Output Options 2", headers)

		# Per-output watt/run columns for lens groups
		self.assertIn("Watts per Foot (White Lens) 1", headers)
		self.assertIn("Max Run Length (White Lens) 1", headers)
		self.assertIn("Watts per Foot (Black Lens) 1", headers)
		self.assertIn("Max Run Length (Other Lenses) 2", headers)

		# Lumen columns per output × CCT
		self.assertIn("White Lens - Output 1 - Lumen 1", headers)
		self.assertIn("Black Lens - Output 1 - Lumen 2", headers)
		self.assertIn("Frosted Lens - Output 2 - Lumen 1", headers)
		self.assertIn("Clear Lens - Output 2 - Lumen 2", headers)

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

		# Lumen pass-through (first value for each CCT × output)
		self.assertEqual(data_row["White Lens - Output 1 - Lumen 1"], 190.0)
		self.assertEqual(data_row["White Lens - Output 1 - Lumen 2"], 200.0)
		self.assertEqual(data_row["Black Lens - Output 1 - Lumen 1"], 160.0)
		self.assertEqual(data_row["Frosted Lens - Output 1 - Lumen 1"], 170.0)

	def test_pivot_to_indesign_empty_variant_rows(self):
		"""Pivot with no variant rows produces only static product columns."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import (
			_pivot_to_indesign,
			INDESIGN_PRODUCT_COLUMNS,
		)

		product_data = {"product_name": "Empty", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": ""}

		headers, data_row = _pivot_to_indesign(product_data, [])

		self.assertEqual(headers, INDESIGN_PRODUCT_COLUMNS)
		self.assertEqual(data_row["Product Name"], "Empty")

	def test_pivot_to_indesign_output_level_sort_order(self):
		"""Output levels are sorted by leading integer, not lexicographically."""
		from illumenate_lighting.illumenate_lighting.api.spec_sheet_export import _pivot_to_indesign

		product_data = {"product_name": "Sort Test", "input_voltage": "", "certifications": "",
			"available_lenses": "", "available_finishes": "", "profile_dimensions": ""}

		variant_rows = [
			{"cct_name": "3000K", "cct_kelvin": 3000, "fixture_output_level": "400 lm/ft"},
			{"cct_name": "3000K", "cct_kelvin": 3000, "fixture_output_level": "50 lm/ft"},
			{"cct_name": "3000K", "cct_kelvin": 3000, "fixture_output_level": "200 lm/ft"},
		]

		_headers, data_row = _pivot_to_indesign(product_data, variant_rows)

		# Sorted by leading int: 50, 200, 400
		self.assertEqual(data_row["Output Options 1"], "50 lm/ft")
		self.assertEqual(data_row["Output Options 2"], "200 lm/ft")
		self.assertEqual(data_row["Output Options 3"], "400 lm/ft")
