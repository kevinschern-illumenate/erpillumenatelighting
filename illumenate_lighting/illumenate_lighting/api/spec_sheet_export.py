# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Spec Sheet CSV Export

Aggregates all fixture data from linked doctypes into a flat CSV
(one row per CCT+CRI+SDCM group, with dynamic per-lens columns)
for InDesign data merge.
"""

import csv
import io
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
	format_length_inches,
)


# ──────────────────────────────────────────────────────────
# CSV Column Headers
# ──────────────────────────────────────────────────────────

PRODUCT_COLUMNS = [
	"product_name",
	"short_description",
	"long_description",
	"sublabel",
	"profile_dimensions",
	"input_voltage",
	"beam_angle",
	"operating_temp_range_c",
	"l70_life_hours",
	"warranty_years",
	"available_finishes",
	"available_lenses",
	"available_mountings",
	"environment_ratings",
	"certifications",
	"dimming_protocols",
	"driver_max_wattage",
]

VARIANT_COLUMNS = [
	"cct_name",
	"cct_kelvin",
	"cri_name",
	"cri_r9",
	"sdcm",
	"output_level",
	"led_pitch_mm",
	"production_interval",
]

# Dynamic per-lens columns are appended at runtime:
#   delivered_lumens_{lens_slug}
#   watts_per_foot_{lens_slug}
#   max_run_ft_{lens_slug}


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _lens_slug(lens_name):
	"""Convert a lens appearance name to a column-safe slug."""
	return (lens_name or "").strip().lower().replace(" ", "_")


def _get_attribute_values_by_type(attribute_links, attr_type):
	"""Return sorted, comma-separated attribute names of a given type."""
	values = []
	for row in attribute_links:
		if row.attribute_type == attr_type and row.attribute_name:
			values.append(row.attribute_name)
	return ", ".join(sorted(set(values)))


def _format_production_interval(tape_offering, tape_spec):
	"""Return production interval as '<inches>" (<mm>mm)' string."""
	cut_mm = tape_offering.cut_increment_mm_override or tape_spec.cut_increment_mm or 0
	if not cut_mm:
		return ""
	inches_str = format_length_inches(cut_mm, precision=2)
	if not inches_str:
		return ""
	mm_val = int(cut_mm) if cut_mm == int(cut_mm) else cut_mm
	return f"{inches_str} ({mm_val}mm)"


def _collect_product_data(wp_doc):
	"""Build the product-level dict that repeats on every CSV row."""
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)

	# --- Profile dimensions (pre-computed read-only field) ---
	profile_dimensions = ""
	if ft_doc and ft_doc.default_profile_spec:
		profile = frappe.get_cached_doc("ilL-Spec-Profile", ft_doc.default_profile_spec)
		profile_dimensions = profile.dimensions or ""

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

	# --- Combined input_voltage: tape voltage + driver voltage range ---
	input_voltage = ""
	tape_voltage_label = ""
	if ft_doc and ft_doc.allowed_tape_offerings:
		# Use the first tape offering's tape spec input_voltage
		first_ato = ft_doc.allowed_tape_offerings[0]
		first_to = frappe.get_cached_doc("ilL-Rel-Tape Offering", first_ato.tape_offering)
		first_ts = frappe.get_cached_doc("ilL-Spec-LED Tape", first_to.tape_spec)
		tape_voltage_label = first_ts.input_voltage or ""

	driver_max_wattage = ""
	driver_voltage_str = ""
	if wp_doc.driver_spec:
		driver = frappe.get_cached_doc("ilL-Spec-Driver", wp_doc.driver_spec)
		if driver.input_voltage_min and driver.input_voltage_max:
			driver_voltage_str = f"{driver.input_voltage_min}V-{driver.input_voltage_max}V{driver.input_voltage_type or 'AC'}"
		driver_max_wattage = driver.max_wattage or ""

	if tape_voltage_label and driver_voltage_str:
		input_voltage = f"{tape_voltage_label} (Power Supply: {driver_voltage_str})"
	elif tape_voltage_label:
		input_voltage = tape_voltage_label
	elif driver_voltage_str:
		input_voltage = driver_voltage_str

	# --- Operating temp range ---
	temp_range = ""
	if wp_doc.operating_temp_min_c is not None and wp_doc.operating_temp_max_c is not None:
		temp_range = f"{wp_doc.operating_temp_min_c} to {wp_doc.operating_temp_max_c}"

	return {
		"product_name": wp_doc.product_name or "",
		"short_description": wp_doc.short_description or "",
		"long_description": wp_doc.long_description or "",
		"sublabel": wp_doc.sublabel or "",
		"profile_dimensions": profile_dimensions,
		"input_voltage": input_voltage,
		"beam_angle": wp_doc.beam_angle or "",
		"operating_temp_range_c": temp_range,
		"l70_life_hours": wp_doc.l70_life_hours or "",
		"warranty_years": wp_doc.warranty_years or "",
		"available_finishes": finishes,
		"available_lenses": lenses,
		"available_mountings": mountings,
		"environment_ratings": env_ratings,
		"certifications": certifications,
		"dimming_protocols": dimming_protocols,
		"driver_max_wattage": driver_max_wattage,
	}


def _get_lens_appearances(wp_doc):
	"""Return an OrderedDict of {lens_name: transmission_decimal} from attribute_links.

	Lenses are sorted alphabetically by name.  Transmission is stored as
	a 0-100 percent on the attribute doc and normalised to 0.0-1.0 here.
	"""
	lens_map = OrderedDict()
	attr_links = wp_doc.attribute_links or []
	names = sorted({
		row.attribute_name
		for row in attr_links
		if row.attribute_type == "Lens Appearance" and row.attribute_name
	})
	for name in names:
		lens_doc = frappe.get_cached_doc("ilL-Attribute-Lens Appearance", name)
		transmission = (lens_doc.transmission / 100.0) if lens_doc.transmission else 1.0
		lens_map[name] = transmission
	return lens_map


def _build_lens_columns(lens_map):
	"""Return a list of dynamic column header strings for all lenses."""
	cols = []
	for lens_name in lens_map:
		slug = _lens_slug(lens_name)
		cols.append(f"delivered_lumens_{slug}")
		cols.append(f"watts_per_foot_{slug}")
		cols.append(f"max_run_ft_{slug}")
	return cols


def _collect_variant_rows(wp_doc, product_data, lens_map):
	"""Yield one dict per (CCT × CRI × SDCM) group with per-lens columns."""
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)

	dynamic_cols = _build_lens_columns(lens_map)

	if not ft_doc or not ft_doc.allowed_tape_offerings:
		# No tape offerings — emit a single row with product data only
		row = dict(product_data)
		for col in VARIANT_COLUMNS + dynamic_cols:
			row.setdefault(col, "")
		yield row
		return

	# ── Pre-fetch all tape offering data ──
	tape_data = []  # list of dicts with resolved tape info
	for ato in ft_doc.allowed_tape_offerings:
		tape_offering = frappe.get_cached_doc("ilL-Rel-Tape Offering", ato.tape_offering)
		tape_spec = frappe.get_cached_doc("ilL-Spec-LED Tape", tape_offering.tape_spec)

		cct_name = tape_offering.cct or ""
		cct_kelvin = ""
		lumen_multiplier = 1.0
		if tape_offering.cct:
			cct_doc = frappe.get_cached_doc("ilL-Attribute-CCT", tape_offering.cct)
			cct_kelvin = cct_doc.kelvin or ""
			lumen_multiplier = cct_doc.lumen_multiplier if cct_doc.lumen_multiplier else 1.0

		cri_name = tape_offering.cri or ""
		cri_r9 = ""
		if tape_offering.cri:
			cri_doc = frappe.get_cached_doc("ilL-Attribute-CRI", tape_offering.cri)
			cri_r9 = cri_doc.r9 or ""

		sdcm_val = ""
		if tape_offering.sdcm:
			sdcm_doc = frappe.get_cached_doc("ilL-Attribute-SDCM", tape_offering.sdcm)
			sdcm_val = sdcm_doc.sdcm or ""

		tape_data.append({
			"tape_offering": tape_offering,
			"tape_spec": tape_spec,
			"cct_name": cct_name,
			"cct_kelvin": cct_kelvin,
			"lumen_multiplier": lumen_multiplier,
			"cri_name": cri_name,
			"cri_r9": cri_r9,
			"sdcm": sdcm_val,
			"output_level": tape_offering.output_level or "",
			"tape_lumens": tape_spec.lumens_per_foot or 0,
			"watts_per_foot": tape_offering.watts_per_ft_override or tape_spec.watts_per_foot or 0,
			"max_run_ft": tape_spec.voltage_drop_max_run_length_ft or "",
			"led_pitch_mm": tape_spec.led_pitch_mm or "",
		})

	# ── Group by (cct_name, cri_name, sdcm) ──
	groups = OrderedDict()
	for td in tape_data:
		key = (td["cct_name"], td["cri_name"], td["sdcm"])
		groups.setdefault(key, []).append(td)

	# ── Emit one row per group ──
	for (cct_name, cri_name, sdcm_val), tapes in groups.items():
		row = dict(product_data)

		# Common variant fields from the first tape in the group (overridden below)
		first = tapes[0]
		row["cct_name"] = cct_name
		row["cct_kelvin"] = first["cct_kelvin"]
		row["cri_name"] = cri_name
		row["cri_r9"] = first["cri_r9"]
		row["sdcm"] = sdcm_val
		row["led_pitch_mm"] = first["led_pitch_mm"]
		row["production_interval"] = _format_production_interval(
			first["tape_offering"], first["tape_spec"]
		)

		# ── Per-lens: pick best tape (highest delivered lumens) ──
		best_tape_for_first_lens = first  # fallback
		for idx, (lens_name, transmission) in enumerate(lens_map.items()):
			slug = _lens_slug(lens_name)
			best = None
			best_delivered = -1
			for td in tapes:
				delivered = td["tape_lumens"] * transmission * td["lumen_multiplier"]
				if delivered > best_delivered:
					best_delivered = delivered
					best = td
			if best is None:
				best = first

			delivered_val = round(best["tape_lumens"] * transmission * best["lumen_multiplier"], 1) if best["tape_lumens"] else ""
			row[f"delivered_lumens_{slug}"] = delivered_val
			row[f"watts_per_foot_{slug}"] = best["watts_per_foot"] or ""
			row[f"max_run_ft_{slug}"] = best["max_run_ft"]

			# Use best tape of the first lens for shared variant columns
			if idx == 0:
				best_tape_for_first_lens = best

		row["output_level"] = best_tape_for_first_lens["output_level"]

		yield row


def _generate_csv(wp_doc):
	"""Return CSV content as a string."""
	product_data = _collect_product_data(wp_doc)
	lens_map = _get_lens_appearances(wp_doc)
	dynamic_cols = _build_lens_columns(lens_map)

	output = io.StringIO()
	writer = csv.writer(output)

	headers = PRODUCT_COLUMNS + VARIANT_COLUMNS + dynamic_cols
	writer.writerow(headers)

	for row in _collect_variant_rows(wp_doc, product_data, lens_map):
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
