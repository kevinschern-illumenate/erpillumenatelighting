# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Spec Sheet CSV Export

Aggregates all fixture data from linked doctypes into a flat CSV
(one row per CCT × fixture_output_level, with fixed per-lens columns)
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
from illumenate_lighting.illumenate_lighting.doctype.ill_spec_profile.ill_spec_profile import (
	compute_profile_dimensions,
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
	"cri_quality",
	"fixture_output_level",
	"led_pitch_mm",
	"production_interval",
]

# Standard lens codes → column slugs.  All four groups are always present;
# columns are blank when a lens is unavailable for the fixture template.
STANDARD_LENSES = OrderedDict([
	("WH", "white"),
	("FR", "frosted"),
	("CL", "clear"),
	("BK", "black"),
])


def _build_lens_columns():
	"""Return the fixed per-lens column headers for the 4 standard lenses."""
	cols = []
	for slug in STANDARD_LENSES.values():
		cols.append(f"delivered_lumens_{slug}")
		cols.append(f"watts_per_foot_{slug}")
		cols.append(f"max_run_length_ft_{slug}")
	return cols


LENS_COLUMNS = _build_lens_columns()


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


def _format_cri_quality(cri_doc, sdcm_val):
	"""Format merged CRI quality string.

	Returns e.g. ``"95 CRI / 2 SDCM"`` when both are present,
	``"95 CRI"`` when SDCM is blank, or ``"2 SDCM"`` if CRI is absent.
	Uses the ``cri_name`` field (e.g. "95 CRI") per user preference
	rather than raw ``minimum_ra``.
	"""
	parts = []
	if cri_doc and getattr(cri_doc, "cri_name", None):
		parts.append(cri_doc.cri_name)
	if sdcm_val:
		parts.append(f"{sdcm_val} SDCM")
	return " / ".join(parts)


def _get_available_lenses(ft_doc):
	"""Return available lenses from fixture template allowed_options.

	Returns ``{lens_code: {"name": str, "transmission": float}}`` for each
	*Lens Appearance* option whose ``code`` matches one of the
	:data:`STANDARD_LENSES` keys.  Transmission is read directly as a
	decimal from ``ilL-Attribute-Lens Appearance`` (e.g. 0.56 = 56 %).
	"""
	lens_info = {}
	if not ft_doc:
		return lens_info
	for opt in (ft_doc.allowed_options or []):
		if getattr(opt, "option_type", None) != "Lens Appearance":
			continue
		if not getattr(opt, "lens_appearance", None):
			continue
		if not getattr(opt, "is_active", True):
			continue
		lens_doc = frappe.get_cached_doc("ilL-Attribute-Lens Appearance", opt.lens_appearance)
		code = (lens_doc.code or "").upper()
		if code not in STANDARD_LENSES:
			continue
		transmission = float(lens_doc.transmission) if lens_doc.transmission else 1.0
		lens_info[code] = {
			"name": opt.lens_appearance,
			"transmission": transmission,
		}
	return lens_info


def _find_closest_fixture_level(delivered_lm_ft, fixture_levels):
	"""Return the fixture-level output closest to *delivered_lm_ft*."""
	if not fixture_levels:
		return None
	closest = None
	min_diff = float("inf")
	for level in fixture_levels:
		diff = abs(level["value"] - delivered_lm_ft)
		if diff < min_diff:
			min_diff = diff
			closest = level
	return closest


def _delivered_lumens(tape_lumens, transmission, lumen_multiplier):
	"""Calculate delivered lumens: tape_lumens × lens_transmission × cct_multiplier."""
	return tape_lumens * transmission * lumen_multiplier


def _collect_product_data(wp_doc):
	"""Build the product-level dict that repeats on every CSV row."""
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)

	# --- Resolve profile (direct link → family fallback) ---
	profile = None
	if ft_doc and ft_doc.default_profile_spec:
		profile = frappe.get_cached_doc("ilL-Spec-Profile", ft_doc.default_profile_spec)
	elif ft_doc and ft_doc.default_profile_family:
		profile_rows = frappe.get_all(
			"ilL-Spec-Profile",
			filters={"family": ft_doc.default_profile_family, "is_active": 1},
			fields=["name"],
			limit=1,
		)
		if profile_rows:
			profile = frappe.get_cached_doc("ilL-Spec-Profile", profile_rows[0].name)

	# --- Profile dimensions (stored field → compute fallback) ---
	profile_dimensions = ""
	if profile:
		profile_dimensions = profile.dimensions or compute_profile_dimensions(
			profile.width_mm, profile.height_mm
		)

	# --- Attribute lists ---
	attr_links = wp_doc.attribute_links or []
	finishes = _get_attribute_values_by_type(attr_links, "Finish")
	lenses = _get_attribute_values_by_type(attr_links, "Lens Appearance")
	mountings = _get_attribute_values_by_type(attr_links, "Mounting")

	# --- Environment ratings from profile ---
	env_ratings = ""
	if profile:
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
		first_ato = ft_doc.allowed_tape_offerings[0]
		first_to = frappe.get_cached_doc("ilL-Rel-Tape Offering", first_ato.tape_offering)
		first_ts = frappe.get_cached_doc("ilL-Spec-LED Tape", first_to.tape_spec)
		tape_voltage_label = first_ts.input_voltage or ""

	# --- Driver info from ilL-Rel-Driver-Eligibility (highest-priority eligible) ---
	driver_max_wattage = ""
	driver_voltage_str = ""
	if ft_doc:
		elig_rows = frappe.get_all(
			"ilL-Rel-Driver-Eligibility",
			filters={
				"fixture_template": ft_doc.name,
				"is_active": 1,
				"is_allowed": 1,
			},
			fields=["driver_spec"],
			order_by="priority asc",
			limit=1,
		)
		if elig_rows and elig_rows[0].driver_spec:
			driver = frappe.get_cached_doc("ilL-Spec-Driver", elig_rows[0].driver_spec)
			if driver.input_voltage_min and driver.input_voltage_max:
				vtype = driver.input_voltage_type or "VAC"
				driver_voltage_str = f"{driver.input_voltage_min}V-{driver.input_voltage_max}{vtype}"
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


def _collect_variant_rows(wp_doc, product_data):
	"""Yield one dict per (fixture_output_level × CCT) with per-lens columns."""
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)

	all_cols = VARIANT_COLUMNS + LENS_COLUMNS

	if not ft_doc or not ft_doc.allowed_tape_offerings:
		row = dict(product_data)
		for col in all_cols:
			row.setdefault(col, "")
		yield row
		return

	# ── Step 1: Available lens appearances (from fixture template allowed_options) ──
	available_lenses = _get_available_lenses(ft_doc)

	# ── Step 2: Pre-fetch all tape offering data ──
	tape_data = []
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

		cri_doc = None
		if tape_offering.cri:
			cri_doc = frappe.get_cached_doc("ilL-Attribute-CRI", tape_offering.cri)

		sdcm_val = ""
		if tape_offering.sdcm:
			sdcm_doc = frappe.get_cached_doc("ilL-Attribute-SDCM", tape_offering.sdcm)
			sdcm_val = sdcm_doc.sdcm or ""

		tape_data.append({
			"tape_offering": tape_offering,
			"tape_spec": tape_spec,
			"ato_row": ato,
			"cct_name": cct_name,
			"cct_kelvin": cct_kelvin,
			"lumen_multiplier": lumen_multiplier,
			"cri_doc": cri_doc,
			"sdcm": sdcm_val,
			"tape_lumens": tape_spec.lumens_per_foot or 0,
			"watts_per_foot": tape_offering.watts_per_ft_override or tape_spec.watts_per_foot or 0,
			"max_run_ft": tape_spec.voltage_drop_max_run_length_ft or "",
			"led_pitch_mm": tape_spec.led_pitch_mm or "",
		})

	# ── Step 3: Fixture-level output levels ──
	fixture_levels_raw = frappe.get_all(
		"ilL-Attribute-Output Level",
		filters={"is_fixture_level": 1},
		fields=["name", "output_level_name", "value", "sku_code"],
		order_by="value asc",
	)
	fixture_levels = [
		{"name": fl.name, "output_level_name": fl.output_level_name, "value": fl.value, "sku_code": fl.sku_code}
		for fl in fixture_levels_raw
	]

	# ── Step 4: Distinct CCTs ──
	ccts = OrderedDict()
	for td in tape_data:
		if td["cct_name"] and td["cct_name"] not in ccts:
			ccts[td["cct_name"]] = {
				"kelvin": td["cct_kelvin"],
				"lumen_multiplier": td["lumen_multiplier"],
			}

	# ── Step 5: Determine reachable fixture output levels ──
	output_level_set = set()
	for td in tape_data:
		for code, lens_info in available_lenses.items():
			ato_lens = getattr(td["ato_row"], "lens_appearance", None) or ""
			if ato_lens and ato_lens != lens_info["name"]:
				continue
			delivered = _delivered_lumens(td["tape_lumens"], lens_info["transmission"], td["lumen_multiplier"])
			closest = _find_closest_fixture_level(delivered, fixture_levels)
			if closest:
				output_level_set.add(closest["name"])

	available_output_levels = sorted(
		[fl for fl in fixture_levels if fl["name"] in output_level_set],
		key=lambda x: x["value"],
	)

	if not available_output_levels:
		# Fallback: one row per CCT, no output level
		for cct_name, cct_info in ccts.items():
			row = dict(product_data)
			row["cct_name"] = cct_name
			row["cct_kelvin"] = cct_info["kelvin"]
			row["fixture_output_level"] = ""
			cct_tapes = [td for td in tape_data if td["cct_name"] == cct_name]
			if cct_tapes:
				st = cct_tapes[0]
				row["cri_quality"] = _format_cri_quality(st["cri_doc"], st["sdcm"])
				row["led_pitch_mm"] = st["led_pitch_mm"]
				row["production_interval"] = _format_production_interval(
					st["tape_offering"], st["tape_spec"]
				)
			for col in all_cols:
				row.setdefault(col, "")
			yield row
		return

	# ── Step 6: Emit one row per (fixture_output_level × CCT) ──
	for output_level in available_output_levels:
		for cct_name, cct_info in ccts.items():
			row = dict(product_data)
			row["cct_name"] = cct_name
			row["cct_kelvin"] = cct_info["kelvin"]
			row["fixture_output_level"] = output_level["output_level_name"]

			cct_tapes = [td for td in tape_data if td["cct_name"] == cct_name]

			shared_tape = None
			for lens_code, slug in STANDARD_LENSES.items():
				lens_info = available_lenses.get(lens_code)
				if not lens_info:
					row[f"delivered_lumens_{slug}"] = ""
					row[f"watts_per_foot_{slug}"] = ""
					row[f"max_run_length_ft_{slug}"] = ""
					continue

				# Filter tapes respecting lens_appearance constraint
				compatible = []
				for td in cct_tapes:
					ato_lens = getattr(td["ato_row"], "lens_appearance", None) or ""
					if ato_lens and ato_lens != lens_info["name"]:
						continue
					compatible.append(td)

				if not compatible:
					row[f"delivered_lumens_{slug}"] = ""
					row[f"watts_per_foot_{slug}"] = ""
					row[f"max_run_length_ft_{slug}"] = ""
					continue

				# Pick tape whose delivered lumens maps closest to this output level
				best = None
				best_diff = float("inf")
				for td in compatible:
					delivered = _delivered_lumens(td["tape_lumens"], lens_info["transmission"], td["lumen_multiplier"])
					diff = abs(delivered - output_level["value"])
					if diff < best_diff:
						best_diff = diff
						best = td

				if best:
					delivered_val = round(
						_delivered_lumens(best["tape_lumens"], lens_info["transmission"], best["lumen_multiplier"]), 1
					)
					row[f"delivered_lumens_{slug}"] = delivered_val
					row[f"watts_per_foot_{slug}"] = best["watts_per_foot"] or ""
					row[f"max_run_length_ft_{slug}"] = best["max_run_ft"]
					if shared_tape is None:
						shared_tape = best
				else:
					row[f"delivered_lumens_{slug}"] = ""
					row[f"watts_per_foot_{slug}"] = ""
					row[f"max_run_length_ft_{slug}"] = ""

			if shared_tape is None:
				shared_tape = cct_tapes[0] if cct_tapes else tape_data[0]

			row["cri_quality"] = _format_cri_quality(shared_tape["cri_doc"], shared_tape["sdcm"])
			row["led_pitch_mm"] = shared_tape["led_pitch_mm"]
			row["production_interval"] = _format_production_interval(
				shared_tape["tape_offering"], shared_tape["tape_spec"]
			)

			for col in all_cols:
				row.setdefault(col, "")

			yield row


def _generate_csv(wp_doc):
	"""Return CSV content as a string."""
	product_data = _collect_product_data(wp_doc)

	output = io.StringIO()
	writer = csv.writer(output)

	headers = PRODUCT_COLUMNS + VARIANT_COLUMNS + LENS_COLUMNS
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
