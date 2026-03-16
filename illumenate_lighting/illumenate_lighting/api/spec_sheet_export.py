# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Spec Sheet CSV Export

Aggregates all fixture data from linked doctypes into a flat CSV
(one row per tape-offering / CCT-output variant) for InDesign data merge.
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils.file_manager import save_file


# ──────────────────────────────────────────────────────────
# CSV Column Headers
# ──────────────────────────────────────────────────────────

PRODUCT_COLUMNS = [
	"product_name",
	"series_name",
	"series_code",
	"short_description",
	"template_code",
	"led_package_type",
	"profile_width_mm",
	"profile_height_mm",
	"profile_weight_per_meter_g",
	"max_assembled_length_mm",
	"beam_angle",
	"operating_temp_range_c",
	"l70_life_hours",
	"warranty_years",
	"fixture_weight_per_foot_g",
	"available_finishes",
	"available_lenses",
	"available_mountings",
	"environment_ratings",
	"certifications",
	"dimming_protocols",
	"driver_input_voltage",
	"driver_max_wattage",
]

VARIANT_COLUMNS = [
	"cct_name",
	"cct_kelvin",
	"cri_name",
	"cri_minimum_ra",
	"cri_r9",
	"sdcm",
	"output_level",
	"tape_lumens_per_foot",
	"delivered_lumens_per_foot",
	"watts_per_foot",
	"efficacy_lm_per_w",
	"max_run_length_ft",
	"led_pitch_mm",
]


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _get_attribute_values_by_type(attribute_links, attr_type):
	"""Return sorted, comma-separated attribute names of a given type."""
	values = []
	for row in attribute_links:
		if row.attribute_type == attr_type and row.attribute_value:
			values.append(row.attribute_value)
	return ", ".join(sorted(set(values)))


def _collect_product_data(wp_doc):
	"""Build the product-level dict that repeats on every CSV row."""
	# --- Series ---
	series_name = ""
	series_code = ""
	if wp_doc.series:
		series = frappe.get_cached_doc("ilL-Attribute-Series", wp_doc.series)
		series_name = series.series_name
		series_code = series.code or ""

	# --- Fixture Template ---
	template_code = ""
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)
		template_code = ft_doc.template_code or ""

	# --- Profile ---
	profile_width = ""
	profile_height = ""
	profile_weight = ""
	max_assembled = ""
	if ft_doc and ft_doc.default_profile_spec:
		profile = frappe.get_cached_doc("ilL-Spec-Profile", ft_doc.default_profile_spec)
		profile_width = profile.width_mm or ""
		profile_height = profile.height_mm or ""
		profile_weight = profile.weight_per_meter_grams or ""
		max_assembled = profile.max_assembled_length_mm or ""

	# --- Attribute lists ---
	attr_links = wp_doc.attribute_links or []
	finishes = _get_attribute_values_by_type(attr_links, "Finish")
	lenses = _get_attribute_values_by_type(attr_links, "Lens Appearance")
	mountings = _get_attribute_values_by_type(attr_links, "Mounting")

	# --- Environment ratings from profile ---
	env_ratings = ""
	if ft_doc and ft_doc.default_profile_spec:
		profile = frappe.get_cached_doc("ilL-Spec-Profile", ft_doc.default_profile_spec)
		ratings = []
		for row in (profile.supported_environment_ratings or []):
			if row.environment_rating:
				ratings.append(row.environment_rating)
		env_ratings = ", ".join(sorted(set(ratings)))

	# --- Certifications ---
	certs = []
	for row in (wp_doc.certifications or []):
		if row.certification:
			certs.append(row.certification)
	certifications = ", ".join(sorted(set(certs)))

	# --- Dimming protocols (from tape offerings' tape specs) ---
	dimming_set = set()
	if ft_doc:
		for ato in (ft_doc.allowed_tape_offerings or []):
			tape_offering = frappe.get_cached_doc("ilL-Rel-Tape Offering", ato.tape_offering)
			tape_spec = frappe.get_cached_doc("ilL-Spec-LED Tape", tape_offering.tape_spec)
			for proto in (tape_spec.supported_dimming_protocols or []):
				if proto.dimming_protocol:
					dimming_set.add(proto.dimming_protocol)
	dimming_protocols = ", ".join(sorted(dimming_set))

	# --- Driver info (first linked driver from attribute links, or from driver_spec) ---
	driver_input_voltage = ""
	driver_max_wattage = ""
	if wp_doc.driver_spec:
		driver = frappe.get_cached_doc("ilL-Spec-Driver", wp_doc.driver_spec)
		if driver.input_voltage_min and driver.input_voltage_max:
			driver_input_voltage = f"{driver.input_voltage_min}-{driver.input_voltage_max} {driver.input_voltage_type or 'VAC'}"
		driver_max_wattage = driver.max_wattage or ""

	# --- Operating temp range ---
	temp_range = ""
	if wp_doc.operating_temp_min_c is not None and wp_doc.operating_temp_max_c is not None:
		temp_range = f"{wp_doc.operating_temp_min_c} to {wp_doc.operating_temp_max_c}"

	return {
		"product_name": wp_doc.product_name or "",
		"series_name": series_name,
		"series_code": series_code,
		"short_description": wp_doc.short_description or "",
		"template_code": template_code,
		"led_package_type": "",  # filled per-variant
		"profile_width_mm": profile_width,
		"profile_height_mm": profile_height,
		"profile_weight_per_meter_g": profile_weight,
		"max_assembled_length_mm": max_assembled,
		"beam_angle": wp_doc.beam_angle or "",
		"operating_temp_range_c": temp_range,
		"l70_life_hours": wp_doc.l70_life_hours or "",
		"warranty_years": wp_doc.warranty_years or "",
		"fixture_weight_per_foot_g": wp_doc.fixture_weight_per_foot_grams or "",
		"available_finishes": finishes,
		"available_lenses": lenses,
		"available_mountings": mountings,
		"environment_ratings": env_ratings,
		"certifications": certifications,
		"dimming_protocols": dimming_protocols,
		"driver_input_voltage": driver_input_voltage,
		"driver_max_wattage": driver_max_wattage,
	}


def _collect_variant_rows(wp_doc, product_data):
	"""Yield one dict per tape offering (CCT / output variant)."""
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)

	if not ft_doc or not ft_doc.allowed_tape_offerings:
		# No tape offerings — emit a single row with product data only
		row = dict(product_data)
		for col in VARIANT_COLUMNS:
			row.setdefault(col, "")
		yield row
		return

	# Collect all lens appearances from allowed_tape_offerings to find a
	# reference transmission %.  Use the first non-null lens.
	reference_transmission = 1.0
	for ato in ft_doc.allowed_tape_offerings:
		if ato.lens_appearance:
			lens_doc = frappe.get_cached_doc("ilL-Attribute-Lens Appearance", ato.lens_appearance)
			if lens_doc.transmission:
				reference_transmission = lens_doc.transmission / 100.0
				break

	for ato in ft_doc.allowed_tape_offerings:
		tape_offering = frappe.get_cached_doc("ilL-Rel-Tape Offering", ato.tape_offering)
		tape_spec = frappe.get_cached_doc("ilL-Spec-LED Tape", tape_offering.tape_spec)

		# Resolve attributes
		cct_name = tape_offering.cct or ""
		cct_kelvin = ""
		lumen_multiplier = 1.0
		if tape_offering.cct:
			cct_doc = frappe.get_cached_doc("ilL-Attribute-CCT", tape_offering.cct)
			cct_kelvin = cct_doc.kelvin or ""
			lumen_multiplier = cct_doc.lumen_multiplier if cct_doc.lumen_multiplier else 1.0

		cri_name = tape_offering.cri or ""
		cri_ra = ""
		cri_r9 = ""
		if tape_offering.cri:
			cri_doc = frappe.get_cached_doc("ilL-Attribute-CRI", tape_offering.cri)
			cri_ra = cri_doc.minimum_ra or ""
			cri_r9 = cri_doc.r9 or ""

		sdcm_val = ""
		if tape_offering.sdcm:
			sdcm_doc = frappe.get_cached_doc("ilL-Attribute-SDCM", tape_offering.sdcm)
			sdcm_val = sdcm_doc.sdcm or ""

		output_level = tape_offering.output_level or ""
		led_package = tape_offering.led_package or ""

		tape_lumens = tape_spec.lumens_per_foot or 0
		watts_per_foot = tape_offering.watts_per_ft_override or tape_spec.watts_per_foot or 0

		# Delivered lumens = tape_lumens_per_foot × lens_transmission% × cct_lumen_multiplier
		delivered_lumens = round(tape_lumens * reference_transmission * lumen_multiplier, 1) if tape_lumens else ""
		efficacy = round(delivered_lumens / watts_per_foot, 1) if delivered_lumens and watts_per_foot else ""

		row = dict(product_data)
		row["led_package_type"] = led_package
		row["cct_name"] = cct_name
		row["cct_kelvin"] = cct_kelvin
		row["cri_name"] = cri_name
		row["cri_minimum_ra"] = cri_ra
		row["cri_r9"] = cri_r9
		row["sdcm"] = sdcm_val
		row["output_level"] = output_level
		row["tape_lumens_per_foot"] = tape_lumens or ""
		row["delivered_lumens_per_foot"] = delivered_lumens
		row["watts_per_foot"] = watts_per_foot or ""
		row["efficacy_lm_per_w"] = efficacy
		row["max_run_length_ft"] = tape_spec.voltage_drop_max_run_length_ft or ""
		row["led_pitch_mm"] = tape_spec.led_pitch_mm or ""

		yield row


def _generate_csv(wp_doc):
	"""Return CSV content as a string."""
	product_data = _collect_product_data(wp_doc)

	output = io.StringIO()
	writer = csv.writer(output)

	headers = PRODUCT_COLUMNS + VARIANT_COLUMNS
	writer.writerow(headers)

	for row in _collect_variant_rows(wp_doc, product_data):
		writer.writerow([row.get(col, "") for col in headers])

	return output.getvalue()


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

@frappe.whitelist()
def export_spec_sheet_csv(webflow_product: str) -> dict:
	"""Generate a spec-sheet CSV for a Webflow Product and attach it.

	Args:
		webflow_product: Name of the ilL-Webflow-Product document.

	Returns:
		dict with ``success``, ``file_url``, and ``file_name``.
	"""
	wp_doc = frappe.get_doc("ilL-Webflow-Product", webflow_product)

	if wp_doc.product_type != "Fixture Template":
		return {"success": False, "error": _("Spec sheet export is only available for Fixture Template products.")}

	if not wp_doc.fixture_template:
		return {"success": False, "error": _("No Fixture Template linked — cannot generate spec sheet.")}

	csv_content = _generate_csv(wp_doc)

	slug = wp_doc.product_slug or wp_doc.name
	fname = f"spec-sheet-{slug}.csv"

	_prev = frappe.flags.ignore_permissions
	try:
		frappe.flags.ignore_permissions = True
		file_doc = save_file(fname, csv_content, "ilL-Webflow-Product", wp_doc.name, is_private=1)
	finally:
		frappe.flags.ignore_permissions = _prev

	return {
		"success": True,
		"file_url": file_doc.file_url,
		"file_name": file_doc.file_name,
	}
