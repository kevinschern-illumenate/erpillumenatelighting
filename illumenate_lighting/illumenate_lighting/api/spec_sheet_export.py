# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Spec Sheet CSV Export

Aggregates all fixture data from linked doctypes into a flat CSV
(one row per CCT × fixture_output_level, with fixed per-lens columns)
for InDesign data merge.

Supports two output formats:
  - ``"flat"`` – one row per CCT × output-level (original format)
	- ``"indesign"`` – one pivoted row per product with **fixed** columns
		(621 total) matching the marketing team's InDesign data-merge layout.
    Column positions never shift between products.
"""

import csv
import io
import re
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import get_url
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
	"minimum_bend_diameters",
]

CUSTOM_SPEC_COLUMNS = [
	# Branding
	"custom_image_illumenate_logo",
	"custom_image_spec_line",
	"custom_image_hero",
	# Component 1
	"custom_component_1_title",
	"custom_image_component_1_hero",
	"custom_component_1_url",
	# Component 2
	"custom_component_2_title",
	"custom_image_component_2_hero",
	"custom_component_2_url",
	# Component 3
	"custom_component_3_title",
	"custom_image_component_3_hero",
	"custom_component_3_url",
	# Icons
	"custom_image_etl_rated_icon",
	"custom_image_ul_rated_icon",
	"custom_image_5v_dc_icon",
	"custom_image_12v_dc_icon",
	"custom_image_24v_dc_icon",
	"custom_image_120v_dc_icon",
	"custom_image_dry_rated_icon",
	"custom_image_damp_rated_icon",
	"custom_image_wet_rated_icon",
	# Dimensions
	"custom_image_dimensions_1",
	"custom_dimensions_2_title",
	"custom_image_dimensions_2",
	"custom_dimensions_3_title",
	"custom_image_dimensions_3",
	"custom_dimensions_4_title",
	"custom_image_dimensions_4",
	"custom_dimensions_5_title",
	# Accessories
	"custom_acc_1_title",
	"custom_image_acc_dims_1",
	"custom_acc_2_title",
	"custom_image_acc_dims_2",
	"custom_acc_3_title",
	"custom_image_acc_dims_3",
	"custom_acc_4_title",
	"custom_image_acc_dims_4",
	"custom_acc_5_title",
	"custom_image_acc_dims_5",
]

# Ordered mapping of InDesign label → raw product_data key for each spec column.
# Label == field name for direct mapping.
_INDESIGN_SPEC_MAP = [(col, col) for col in CUSTOM_SPEC_COLUMNS]

CUSTOM_SPEC_FALLBACK_FIELDS = {
	"custom_image_hero": ("featured_image", "series_family_image", "image"),
	"custom_image_dimensions_1": ("dimensions_image",),
}

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
		cols.append(f"max_footage_per_100w_supply_{slug}")
	return cols


LENS_COLUMNS = _build_lens_columns()

# ──────────────────────────────────────────────────────────
# Standardized InDesign Column Constants
# ──────────────────────────────────────────────────────────

# 9 current part-number-builder sections + 2 buffer sections = 11 total.
STANDARD_PN_SECTIONS = [
	"Series", "Dry/Wet", "CCT", "Output", "Lens",
	"Mounting", "Finish", "Start Feed Type", "End Feed Type",
	"Buffer 1", "Buffer 2",
]

MAX_PN_OPTIONS_PER_SECTION = 10  # 10 option slots per section
MAX_CCTS = 8                     # fixed CCT column count
MAX_OUTPUT_LEVELS = 8            # fixed output-level block count

# Total column count of the unified InDesign data-merge CSV.
#   18 static + 39 custom_* + 8 CCT + 8 × (1 + 3×3 + 8×4) + 11 × 10 × 2 = 621
# Keep this in sync with INDESIGN_PRODUCT_COLUMNS / _INDESIGN_LENS_GROUPS /
# _INDESIGN_LUMEN_LENSES / STANDARD_PN_SECTIONS — an assert in
# ``_generate_indesign_csv`` / ``_generate_tape_neon_indesign_csv`` enforces
# that the two code paths can never drift apart.
INDESIGN_TOTAL_COLUMNS = 621
MAX_POWER_SUPPLY_USABLE_WATTS = 80


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
			values.append(getattr(row, "display_label", None) or row.attribute_name)
	return ", ".join(sorted(set(values)))


def _add_list_values(values, *raw_values):
	"""Add comma-separated display values into a set, skipping blanks."""
	for raw_value in raw_values:
		if not _has_value(raw_value):
			continue
		for value in str(raw_value).split(","):
			value = value.strip()
			if value:
				values.add(value)


def _join_list_values(values):
	return ", ".join(sorted(values))


def _collect_certification_values(*docs, attribute_links=None):
	values = set()
	for row in (attribute_links or []):
		if getattr(row, "attribute_type", None) == "Certification":
			_add_list_values(values, getattr(row, "display_label", None) or getattr(row, "attribute_name", None))
	for doc in docs:
		for row in (_doc_get(doc, "certifications", []) or []):
			_add_list_values(values, _doc_get(row, "certification"))
	return values


def _doc_get(doc, fieldname, default=None):
	"""Safely read a field from a Frappe doc, dict, or test namespace."""
	if not doc:
		return default
	if hasattr(doc, "get"):
		try:
			value = doc.get(fieldname)
		except TypeError:
			value = doc.get(fieldname, default)
		if value is not None:
			return value
	return getattr(doc, fieldname, default)


def _has_value(value):
	return value is not None and value != ""


def _is_checked(value):
	if value is None:
		return False
	if isinstance(value, str):
		return value.strip().lower() not in ("", "0", "false", "no", "none")
	return bool(value)


def _is_custom_link_column(fieldname):
	return fieldname.startswith("custom_image_") or fieldname.endswith("_url")


def _make_absolute_url(value):
	"""Return an absolute URL for stored Frappe file paths."""
	if not _has_value(value):
		return ""
	value = str(value).strip()
	if not value:
		return ""
	if re.match(r"^[a-z][a-z0-9+.-]*:", value, flags=re.IGNORECASE):
		return value
	if value.startswith("/"):
		return get_url(value)
	return value


def _copy_custom_spec_fields(result, wp_doc, *fallback_docs):
	"""Copy custom spec columns, using safe fallbacks for common media fields."""
	for col in CUSTOM_SPEC_COLUMNS:
		value = _doc_get(wp_doc, col, None)
		if not _has_value(value):
			for fallback_field in CUSTOM_SPEC_FALLBACK_FIELDS.get(col, ()):
				for doc in (wp_doc, *fallback_docs):
					value = _doc_get(doc, fallback_field, None)
					if _has_value(value):
						break
				if _has_value(value):
					break
		if _is_custom_link_column(col):
			value = _make_absolute_url(value)
		result[col] = value or ""


def _format_voltage_value(value, suffix):
	if not _has_value(value):
		return ""
	text = str(value).strip()
	compact = text.upper().replace(" ", "")
	if compact.endswith(suffix):
		return text
	if compact.endswith("V"):
		return f"{text}{suffix[1:]}"
	return f"{text}{suffix}"


def _format_output_voltage(voltage_name):
	"""Resolve an Output Voltage attribute to a display label."""
	if not voltage_name:
		return ""
	voltage_data = frappe.db.get_value(
		"ilL-Attribute-Output Voltage",
		voltage_name,
		["dc_voltage", "ac_voltage"],
		as_dict=True,
	)
	if voltage_data:
		dc_voltage = voltage_data.get("dc_voltage")
		if dc_voltage:
			return _format_voltage_value(dc_voltage, "VDC")
		ac_voltage = voltage_data.get("ac_voltage")
		if ac_voltage:
			return _format_voltage_value(ac_voltage, "VAC")
	return str(voltage_name)


def _format_driver_input_voltage(driver):
	if not driver:
		return ""
	if driver.input_voltage_min and driver.input_voltage_max:
		vtype = driver.input_voltage_type or "VAC"
		return f"{driver.input_voltage_min}V-{driver.input_voltage_max}{vtype}"
	return ""


def _format_mm_interval(length_mm):
	if not _has_value(length_mm):
		return ""
	try:
		length_mm = float(length_mm)
	except (TypeError, ValueError):
		return ""
	if not length_mm:
		return ""
	inches_str = format_length_inches(length_mm, precision=2)
	if not inches_str:
		return ""
	mm_val = int(length_mm) if length_mm == int(length_mm) else length_mm
	return f"{inches_str} ({mm_val}mm)"


def _max_footage_per_100w_supply(watts_per_foot):
	watts = _safe_float(watts_per_foot)
	if not watts:
		return ""
	return round(MAX_POWER_SUPPLY_USABLE_WATTS / watts, 1)


def _format_max_footage_per_100w_supply(watts_per_foot):
	footage = _max_footage_per_100w_supply(watts_per_foot)
	return f"{_fmt_num(footage)}ft" if footage != "" else ""


def _get_preferred_driver_info(template_type, template_name):
	"""Return preferred driver details for a template, if eligibility is configured."""
	info = {
		"input_voltage": "",
		"max_wattage": "",
		"dimming_protocols": set(),
	}
	if not template_name:
		return info

	filters = {
		"fixture_template": template_name,
		"is_active": 1,
		"is_allowed": 1,
	}
	if template_type:
		filters["template_type"] = template_type

	elig_rows = frappe.get_all(
		"ilL-Rel-Driver-Eligibility",
		filters=filters,
		fields=["driver_spec"],
		order_by="priority asc",
		limit=1,
	)
	if not elig_rows or not elig_rows[0].driver_spec:
		return info

	driver = frappe.get_cached_doc("ilL-Spec-Driver", elig_rows[0].driver_spec)
	info["input_voltage"] = _format_driver_input_voltage(driver)
	info["max_wattage"] = driver.max_wattage or ""
	for row in (driver.input_protocols or []):
		if row.protocol:
			info["dimming_protocols"].add(row.protocol)
	return info


def _get_tape_neon_spec_names(tnt_doc):
	"""Return allowed tape spec names, preserving template/default priority."""
	spec_names = []
	default_spec = _doc_get(tnt_doc, "default_tape_spec")
	if default_spec:
		spec_names.append(default_spec)
	for row in (_doc_get(tnt_doc, "allowed_tape_specs", []) or []):
		tape_spec = _doc_get(row, "tape_spec")
		if tape_spec and tape_spec not in spec_names:
			spec_names.append(tape_spec)
	return spec_names


def _iter_tape_neon_specs(tnt_doc):
	"""Yield cached tape spec docs for the template's allowed specs."""
	for tape_spec in _get_tape_neon_spec_names(tnt_doc):
		try:
			yield frappe.get_cached_doc("ilL-Spec-LED Tape", tape_spec)
		except frappe.DoesNotExistError:
			continue


def _collect_tape_neon_voltage_labels(tnt_doc):
	labels = []
	for tape_spec in _iter_tape_neon_specs(tnt_doc):
		label = _format_output_voltage(getattr(tape_spec, "input_voltage", None))
		if label and label not in labels:
			labels.append(label)
	return labels


def _collect_tape_neon_template_values(tnt_doc, option_type, fieldname):
	values = set()
	for opt in (_doc_get(tnt_doc, "allowed_options", []) or []):
		if hasattr(opt, "is_active") and not opt.is_active:
			continue
		if _doc_get(opt, "option_type") != option_type:
			continue
		value = _doc_get(opt, fieldname)
		if value:
			values.add(value)
	return values


def _collect_tape_neon_offering_data(tnt_doc):
	"""Return offering-backed variant data for a Tape/Neon Template."""
	spec_names = _get_tape_neon_spec_names(tnt_doc)
	if not spec_names:
		return []

	offering_rows = frappe.get_all(
		"ilL-Rel-Tape Offering",
		filters={"tape_spec": ["in", spec_names], "is_active": 1},
		fields=[
			"name", "tape_spec", "cct", "cri", "sdcm", "led_package", "output_level",
			"watts_per_ft_override", "cut_increment_mm_override",
		],
		order_by="tape_spec asc, cct asc, output_level asc",
	)

	allowed_ccts = _collect_tape_neon_template_values(tnt_doc, "CCT", "cct")
	allowed_outputs = _collect_tape_neon_template_values(tnt_doc, "Output Level", "output_level")

	spec_rank = {name: idx for idx, name in enumerate(spec_names)}
	offering_data = []
	for offering in offering_rows:
		if allowed_ccts and offering.cct not in allowed_ccts:
			continue
		if allowed_outputs and offering.output_level not in allowed_outputs:
			continue
		try:
			tape_spec = frappe.get_cached_doc("ilL-Spec-LED Tape", offering.tape_spec)
		except frappe.DoesNotExistError:
			continue

		cct_kelvin = ""
		lumen_multiplier = 1.0
		if offering.cct:
			cct_data = frappe.db.get_value(
				"ilL-Attribute-CCT",
				offering.cct,
				["kelvin", "lumen_multiplier"],
				as_dict=True,
			) or {}
			cct_kelvin = cct_data.get("kelvin") or ""
			lumen_multiplier = cct_data.get("lumen_multiplier") or 1.0

		output_data = {}
		if offering.output_level:
			output_data = frappe.db.get_value(
				"ilL-Attribute-Output Level",
				offering.output_level,
				["output_level_name", "value", "sku_code"],
				as_dict=True,
			) or {}
		output_value = output_data.get("value") or 0
		output_label = output_data.get("output_level_name") or (
			f"{output_value} lm/ft" if output_value else offering.output_level or ""
		)

		cri_doc = None
		if offering.cri:
			try:
				cri_doc = frappe.get_cached_doc("ilL-Attribute-CRI", offering.cri)
			except frappe.DoesNotExistError:
				cri_doc = None

		sdcm_val = ""
		if offering.sdcm:
			try:
				sdcm_doc = frappe.get_cached_doc("ilL-Attribute-SDCM", offering.sdcm)
				sdcm_val = sdcm_doc.sdcm or ""
			except frappe.DoesNotExistError:
				sdcm_val = ""

		cri_quality = _format_cri_quality(cri_doc, sdcm_val)
		if not cri_quality and getattr(tape_spec, "cri_typical", None):
			from types import SimpleNamespace
			cri_quality = _format_cri_quality(
				SimpleNamespace(cri_name=f"{int(tape_spec.cri_typical)} CRI"),
				getattr(tape_spec, "sdcm", None),
			)

		tape_lumens = tape_spec.lumens_per_foot or output_value or 0
		template_free_cutting = _is_checked(_doc_get(tnt_doc, "is_free_cutting", 0))
		cut_mm = 0 if template_free_cutting else offering.cut_increment_mm_override or tape_spec.cut_increment_mm or 0
		production_interval = (
			"Free-Cutting" if template_free_cutting else _format_production_interval(offering, tape_spec)
		)

		offering_data.append({
			"offering": offering,
			"tape_spec": tape_spec,
			"cct_name": offering.cct or "",
			"cct_kelvin": cct_kelvin,
			"lumen_multiplier": lumen_multiplier,
			"output_level": offering.output_level or "",
			"output_label": output_label,
			"output_value": output_value,
			"led_package": offering.led_package or getattr(tape_spec, "led_package", "") or "",
			"cri_quality": cri_quality,
			"tape_lumens": tape_lumens,
			"watts_per_foot": offering.watts_per_ft_override or tape_spec.watts_per_foot or "",
			"max_run_ft": tape_spec.voltage_drop_max_run_length_ft or "",
			"cut_increment_mm": cut_mm,
			"production_interval": production_interval,
			"led_pitch_mm": tape_spec.led_pitch_mm or "",
			"sort_key": (
				output_value or 0,
				cct_kelvin or 0,
				spec_rank.get(offering.tape_spec, len(spec_rank)),
				offering.name,
			),
		})

	offering_data.sort(key=lambda item: item["sort_key"])
	return offering_data


def _format_production_interval(tape_offering, tape_spec):
	"""Return production interval as '<inches>" (<mm>mm)' string."""
	if _is_checked(getattr(tape_spec, "is_free_cutting", 0)):
		return "Free-Cutting"
	cut_mm = tape_offering.cut_increment_mm_override or tape_spec.cut_increment_mm or 0
	return _format_mm_interval(cut_mm)


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
			order_by="name asc",
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

	minimum_bend_diameters = ""
	if ft_doc:
		minimum_bend_diameters = _format_mm_interval(
			getattr(ft_doc, "minimum_bend_diameter_mm", None)
		)

	# --- Attribute lists ---
	attr_links = wp_doc.attribute_links or []
	finishes = _get_attribute_values_by_type(attr_links, "Finish")
	lenses = _get_attribute_values_by_type(attr_links, "Lens Appearance")
	mounting_set = set()
	if ft_doc:
		for opt in (ft_doc.allowed_options or []):
			if opt.option_type == "Mounting Method" and opt.mounting_method:
				mounting_set.add(opt.mounting_method)
	mountings = ", ".join(sorted(mounting_set))

	# --- Environment ratings from profile ---
	env_ratings = ""
	if profile:
		ratings = []
		for row in (profile.supported_environment_ratings or []):
			if row.environment_rating:
				ratings.append(row.environment_rating)
		env_ratings = ", ".join(sorted(set(ratings)))

	# --- Certifications ---
	certifications = _join_list_values(
		_collect_certification_values(wp_doc, attribute_links=attr_links)
	)

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
	dimming_protocols = ""
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
			# --- Dimming protocols from driver's input protocols ---
			dimming_set = set()
			for row in (driver.input_protocols or []):
				if row.protocol:
					dimming_set.add(row.protocol)
			dimming_protocols = ", ".join(sorted(dimming_set))

	if tape_voltage_label and driver_voltage_str:
		input_voltage = f"{tape_voltage_label} (Power Supply: {driver_voltage_str})"
	elif tape_voltage_label:
		input_voltage = tape_voltage_label
	elif driver_voltage_str:
		input_voltage = driver_voltage_str

	# --- Operating temp range ---
	temp_range = ""
	if wp_doc.operating_temp_min_c is not None and wp_doc.operating_temp_max_c is not None:
		c_min = wp_doc.operating_temp_min_c
		c_max = wp_doc.operating_temp_max_c
		f_min = round(c_min * 9 / 5 + 32)
		f_max = round(c_max * 9 / 5 + 32)
		temp_range = f"{f_min}°F ({c_min}°C) to {f_max}°F ({c_max}°C)"

	# --- Beam angle formatting ---
	beam_angle = ""
	if wp_doc.beam_angle:
		val = wp_doc.beam_angle
		beam_angle = f"{int(val)}°" if val == int(val) else f"{val}°"

	result = {
		"product_name": wp_doc.product_name or "",
		"short_description": wp_doc.short_description or "",
		"sublabel": wp_doc.sublabel or "",
		"profile_dimensions": profile_dimensions,
		"input_voltage": input_voltage,
		"beam_angle": beam_angle,
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
		"minimum_bend_diameters": minimum_bend_diameters,
	}

	_copy_custom_spec_fields(result, wp_doc)

	return result


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
					row[f"max_footage_per_100w_supply_{slug}"] = ""
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
					row[f"max_footage_per_100w_supply_{slug}"] = ""
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
					row[f"max_footage_per_100w_supply_{slug}"] = _max_footage_per_100w_supply(
						best["watts_per_foot"]
					)
					if shared_tape is None:
						shared_tape = best
				else:
					row[f"delivered_lumens_{slug}"] = ""
					row[f"watts_per_foot_{slug}"] = ""
					row[f"max_run_length_ft_{slug}"] = ""
					row[f"max_footage_per_100w_supply_{slug}"] = ""

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


# ──────────────────────────────────────────────────────────
# Part Number Builder helpers
# ──────────────────────────────────────────────────────────

def _collect_pn_builder_columns(ft_doc):
	"""Collect Part Number Builder columns from a Fixture Template.

	Always returns a fixed set of **220 columns** (11 standard sections ×
	10 option slots × 2 columns each).  Actual data is filled where it
	exists; unused slots are empty strings.

	Returns ``(headers, data_dict)`` where *headers* is the ordered list of
	column names and *data_dict* maps each column name to its value.

	Column naming always uses numbered suffixes:
	  ``Part Number - {Section} - Option {N}:`` / ``… - Description {N}:``
	"""
	headers = []
	data_dict = {}

	# Build the fixed 220-column skeleton
	for section_name in STANDARD_PN_SECTIONS:
		for idx in range(1, MAX_PN_OPTIONS_PER_SECTION + 1):
			opt_col = f"Part Number - {section_name} - Option {idx}:"
			desc_col = f"Part Number - {section_name} - Description {idx}:"
			headers.append(opt_col)
			headers.append(desc_col)
			data_dict[opt_col] = ""
			data_dict[desc_col] = ""

	if not ft_doc:
		return headers, data_dict

	rows = ft_doc.get("part_number_builder") or []
	if not rows:
		return headers, data_dict

	# Group by section_name
	sections = {}
	for r in rows:
		sname = r.section_name or ""
		if sname not in sections:
			sections[sname] = []
		sections[sname].append(r)

	# Fill actual data into matching standard-section slots
	for section_name, opts in sections.items():
		opts = sorted(opts, key=lambda o: (o.option_order or 0, o.option_code or ""))
		for idx, opt in enumerate(opts, 1):
			if idx > MAX_PN_OPTIONS_PER_SECTION:
				break
			opt_col = f"Part Number - {section_name} - Option {idx}:"
			desc_col = f"Part Number - {section_name} - Description {idx}:"
			if opt_col in data_dict:
				data_dict[opt_col] = opt.option_code or ""
				data_dict[desc_col] = opt.option_label or ""

	return headers, data_dict


# ──────────────────────────────────────────────────────────
# Tape / Neon flat CSV
# ──────────────────────────────────────────────────────────

# Columns for the tape/neon flat CSV (subset of PRODUCT_COLUMNS).
TAPE_NEON_COLUMNS = [
	"product_name",
	"product_type",
	"template_code",
	"short_description",
	"input_voltage",
	"operating_temp_range_c",
	"l70_life_hours",
	"warranty_years",
	"certifications",
	"dimming_protocols",
	"environment_ratings",
]

TAPE_NEON_VARIANT_COLUMNS = [
	"cct_name",
	"cct_kelvin",
	"output_level",
	"output_lm_ft",
	"led_package",
	"cri",
	"watts_per_foot",
	"max_run_length_ft",
	"cut_increment_mm",
	"production_interval",
]


def _collect_tape_neon_product_data(wp_doc):
	"""Build the product-level dict for LED Tape / LED Neon products."""
	tnt_doc = frappe.get_cached_doc("ilL-Tape-Neon-Template", wp_doc.tape_neon_template)
	result = _collect_tape_neon_product_data_indesign(wp_doc)
	result["product_type"] = wp_doc.product_type or ""
	result["template_code"] = tnt_doc.template_code or tnt_doc.name
	return result


def _collect_tape_neon_variant_rows(wp_doc, product_data):
	"""Yield one dict per (CCT × Output Level) from tape/neon template."""
	tnt_doc = frappe.get_cached_doc("ilL-Tape-Neon-Template", wp_doc.tape_neon_template)
	offering_data = _collect_tape_neon_offering_data(tnt_doc)
	if offering_data:
		seen_keys = set()
		for td in offering_data:
			key = (td["cct_name"], td["output_level"])
			if key in seen_keys:
				continue
			seen_keys.add(key)
			row = dict(product_data)
			row["cct_name"] = td["cct_name"]
			row["cct_kelvin"] = td["cct_kelvin"]
			row["output_level"] = td["output_label"]
			row["output_lm_ft"] = td["output_value"] or td["tape_lumens"]
			row["led_package"] = td["led_package"]
			row["cri"] = td["cri_quality"]
			row["watts_per_foot"] = td["watts_per_foot"]
			row["max_run_length_ft"] = td["max_run_ft"]
			row["cut_increment_mm"] = td["cut_increment_mm"]
			row["production_interval"] = td["production_interval"]
			yield row
		return

	# Collect CCTs and output levels from allowed_options
	ccts = OrderedDict()
	output_levels = OrderedDict()
	for opt in (tnt_doc.allowed_options or []):
		if hasattr(opt, "is_active") and not opt.is_active:
			continue
		otype = getattr(opt, "option_type", None)
		if otype == "CCT" and opt.cct and opt.cct not in ccts:
			cct_data = frappe.db.get_value(
				"ilL-Attribute-CCT", opt.cct, ["kelvin", "label"], as_dict=True
			)
			ccts[opt.cct] = {
				"kelvin": cct_data.get("kelvin", "") if cct_data else "",
				"label": cct_data.get("label", opt.cct) if cct_data else opt.cct,
			}
		elif otype == "Output Level" and opt.output_level and opt.output_level not in output_levels:
			level_data = frappe.db.get_value(
				"ilL-Attribute-Output Level", opt.output_level, ["value", "sku_code"], as_dict=True
			)
			output_levels[opt.output_level] = {
				"value": level_data.get("value", "") if level_data else "",
				"sku_code": level_data.get("sku_code", "") if level_data else "",
			}

	# Collect tape spec data for enrichment
	tape_specs = []
	for spec_row in (tnt_doc.allowed_tape_specs or []):
		if not spec_row.tape_spec:
			continue
		try:
			ts = frappe.get_cached_doc("ilL-Spec-LED Tape", spec_row.tape_spec)
			tape_specs.append(ts)
		except frappe.DoesNotExistError:
			continue

	# If no CCTs/outputs, yield a single row with product data
	if not ccts and not output_levels:
		row = dict(product_data)
		for col in TAPE_NEON_VARIANT_COLUMNS:
			row.setdefault(col, "")
		yield row
		return

	# Ensure at least one entry in each dimension
	if not ccts:
		ccts[""] = {"kelvin": "", "label": ""}
	if not output_levels:
		output_levels[""] = {"value": "", "sku_code": ""}

	# First tape spec for shared fields
	first_tape = tape_specs[0] if tape_specs else None

	for cct_name, cct_info in ccts.items():
		for level_name, level_info in output_levels.items():
			row = dict(product_data)
			row["cct_name"] = cct_info.get("label", cct_name)
			row["cct_kelvin"] = cct_info.get("kelvin", "")
			row["output_level"] = level_name
			row["output_lm_ft"] = level_info.get("value", "")
			row["led_package"] = first_tape.led_package if first_tape else ""
			row["cri"] = str(first_tape.cri_typical) if first_tape and first_tape.cri_typical else ""
			row["watts_per_foot"] = first_tape.watts_per_foot if first_tape else ""
			row["max_run_length_ft"] = first_tape.voltage_drop_max_run_length_ft if first_tape else ""
			row["cut_increment_mm"] = first_tape.cut_increment_mm if first_tape else ""
			cut_mm = first_tape.cut_increment_mm if first_tape else 0
			row["production_interval"] = format_length_inches(cut_mm, precision=2) if cut_mm else ""
			yield row


def _generate_tape_neon_csv(wp_doc):
	"""Return CSV content for LED Tape / LED Neon products (flat format).

	.. deprecated::
		This flat layout is incompatible with the marketing team's InDesign
		data-merge template.  The default export for LED Tape / LED Neon now
		uses :func:`_generate_tape_neon_indesign_csv` (same 621-column schema
		as Fixture Template).  This flat writer is kept as an opt-in and is
		only reached when ``format="tape_neon_flat"`` is explicitly passed
		to :func:`export_spec_sheet_csv`.
	"""
	return _generate_tape_neon_flat_csv(wp_doc)


def _generate_tape_neon_flat_csv(wp_doc):
	"""Return CSV content for LED Tape / LED Neon products (legacy flat)."""
	product_data = _collect_tape_neon_product_data(wp_doc)

	output = io.StringIO()
	writer = csv.writer(output)

	headers = TAPE_NEON_COLUMNS + TAPE_NEON_VARIANT_COLUMNS
	writer.writerow(headers)

	for row in _collect_tape_neon_variant_rows(wp_doc, product_data):
		writer.writerow([row.get(col, "") for col in headers])

	return output.getvalue()


# ──────────────────────────────────────────────────────────
# Tape / Neon InDesign CSV  (unified 621-column schema)
# ──────────────────────────────────────────────────────────
#
# LED Tape and LED Neon share the Fixture-Template InDesign layout so that
# marketing's single data-merge template accepts every product type.  Fields
# that don't apply to a specific tape/neon product are emitted as blank cells
# rather than being dropped — InDesign matches columns by header name, so a
# *missing* column silently shifts the remaining fields.  See the module
# docstring for the full contract.
#
# Lens-bucket convention for neon / tape
# --------------------------------------
# Neon/tape output is normally lens-agnostic even when the product records
# carry lens-like display metadata.  The fixture schema has four lens slugs
# (white / frosted / clear / black); we populate the ``frosted`` slug because
# ``_INDESIGN_LENS_GROUPS`` maps "Other Lenses" → "frosted", which is where
# the marketing template routes the lens-agnostic output on the neon/tape spec
# sheet.  The other three slugs stay blank so they merge as empty fields.


# option_type → STANDARD_PN_SECTIONS label for the tape/neon PN shim.
#
# "Feed Direction" / "Power Feed Type" fan out to Start/End based on
# ``feed_position`` and are handled separately below.
_TN_PN_SECTION_MAP = {
	"CCT": "CCT",
	"Output Level": "Output",
	"Lens Appearance": "Lens",
	"Environment Rating": "Dry/Wet",
	"IP Rating": "Dry/Wet",
	"PCB Mounting": "Mounting",
	"Mounting Method": "Mounting",
	"Finish": "Finish",
	"PCB Finish": "Finish",
}

# allowed_options.option_type → (link_fieldname, attribute_doctype) used to
# render the human label for a PN option when the option row itself only
# stores a link.  The option sku/code always comes from the attribute's
# ``code`` field when it exists.
_TN_OPTION_LINKS = {
	"CCT": ("cct", "ilL-Attribute-CCT"),
	"Output Level": ("output_level", "ilL-Attribute-Output Level"),
	"Lens Appearance": ("lens_appearance", "ilL-Attribute-Lens Appearance"),
	"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
	"IP Rating": ("ip_rating", "ilL-Attribute-IP Rating"),
	"Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
	"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
	"PCB Mounting": ("pcb_mounting", "ilL-Attribute-PCB Mounting"),
	"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
	"Finish": ("finish", "ilL-Attribute-Finish"),
	"PCB Finish": ("pcb_finish", "ilL-Attribute-PCB Finish"),
}


def _tn_option_label_code(opt):
	"""Return ``(option_code, option_label)`` for a tape/neon allowed_option row.

	The sku/code is read from the linked attribute doc's ``code`` field
	(falls back to the link name); the label prefers a ``label`` /
	``{type}_name`` field on the attribute, then the raw name.
	Returns ``("", "")`` when the option has no resolvable link.
	"""
	otype = getattr(opt, "option_type", None)
	link_spec = _TN_OPTION_LINKS.get(otype)
	if not link_spec:
		return "", ""
	field, doctype = link_spec
	link_name = getattr(opt, field, None)
	if not link_name:
		return "", ""

	code = ""
	label = link_name
	try:
		attr_doc = frappe.get_cached_doc(doctype, link_name)
	except frappe.DoesNotExistError:
		return "", link_name

	for code_field in ("code", "sku_code", "voltage_code"):
		if frappe.db.has_column(doctype, code_field):
			code = getattr(attr_doc, code_field, "") or ""
			if code:
				break
	# Prefer the most descriptive human-readable label we can find.
	for cand in ("label", "cct_name", "output_level_name", "lens_name", "appearance_name",
	             "finish_name", "direction_name", "mounting_method", "voltage_name"):
		val = getattr(attr_doc, cand, None)
		if val:
			label = val
			break
	return code, label


def _tn_option_display_label(opt):
	_code, label = _tn_option_label_code(opt)
	return label


def _collect_tn_pn_builder_columns(tnt_doc):
	"""Return the same 220-column skeleton as :func:`_collect_pn_builder_columns`.

	Populates the standard-section slots from a Tape/Neon Template's
	``allowed_options`` + ``series`` so the neon InDesign CSV carries an
	identically shaped Part Number Builder block (sparser, but same width).
	"""
	# Build the fixed 220-column skeleton via the canonical helper.
	headers, data_dict = _collect_pn_builder_columns(None)

	if not tnt_doc:
		return headers, data_dict

	# ── Series (single option slot) ──
	# Tape/neon PN builder uses the template slug/code, not the shorter Series code.
	if getattr(tnt_doc, "template_code", None):
		data_dict["Part Number - Series - Option 1:"] = str(tnt_doc.template_code).upper()
		data_dict["Part Number - Series - Description 1:"] = (
			getattr(tnt_doc, "template_name", None) or tnt_doc.template_code
		)
	elif getattr(tnt_doc, "series", None):
		try:
			series_doc = frappe.get_cached_doc("ilL-Attribute-Series", tnt_doc.series)
			data_dict["Part Number - Series - Option 1:"] = series_doc.code or ""
			data_dict["Part Number - Series - Description 1:"] = (
				series_doc.series_name or tnt_doc.series
			)
		except frappe.DoesNotExistError:
			data_dict["Part Number - Series - Option 1:"] = ""
			data_dict["Part Number - Series - Description 1:"] = tnt_doc.series

	# ── Group allowed_options into standard-section buckets ──
	section_buckets = {sec: [] for sec in STANDARD_PN_SECTIONS}
	seen_codes = {sec: set() for sec in STANDARD_PN_SECTIONS}

	for opt in (tnt_doc.allowed_options or []):
		if hasattr(opt, "is_active") and not opt.is_active:
			continue
		otype = getattr(opt, "option_type", None)

		# Feed Direction / Power Feed Type fan out to Start/End based on
		# the feed_position flag.  "Both" emits into both buckets so the
		# label is present wherever marketing looks for it.
		if otype in ("Feed Direction", "Power Feed Type"):
			code, label = _tn_option_label_code(opt)
			if not (code or label):
				continue
			position = (getattr(opt, "feed_position", None) or "Both")
			targets = []
			if position in ("Start", "Both"):
				targets.append("Start Feed Type")
			if position in ("End", "Both"):
				targets.append("End Feed Type")
			for section in targets:
				if code in seen_codes[section]:
					continue
				seen_codes[section].add(code)
				section_buckets[section].append((code, label))
			continue

		section = _TN_PN_SECTION_MAP.get(otype)
		if not section:
			continue
		code, label = _tn_option_label_code(opt)
		if not (code or label):
			continue
		if code in seen_codes[section]:
			continue
		seen_codes[section].add(code)
		section_buckets[section].append((code, label))

	# ── Emit up to MAX_PN_OPTIONS_PER_SECTION per bucket ──
	for section, opts in section_buckets.items():
		if section == "Series":
			continue  # already populated above
		for idx, (code, label) in enumerate(opts[:MAX_PN_OPTIONS_PER_SECTION], 1):
			data_dict[f"Part Number - {section} - Option {idx}:"] = code
			data_dict[f"Part Number - {section} - Description {idx}:"] = label

	return headers, data_dict


def _collect_tape_neon_product_data_indesign(wp_doc):
	"""Build a fixture-shaped product dict for LED Tape / LED Neon products.

	Returns the same keys as :func:`_collect_product_data` (including every
	:data:`CUSTOM_SPEC_COLUMNS` entry) so :func:`_pivot_to_indesign` can
	consume it identically.  Tape/neon can fill product-level display columns
	from structured options first, then from template-level spec-sheet fallback
	fields.  InDesign data merge silently shifts columns when a header is
	missing, so every column must exist even when empty.
	"""
	tnt_doc = frappe.get_cached_doc("ilL-Tape-Neon-Template", wp_doc.tape_neon_template)
	attr_links = wp_doc.attribute_links or []
	is_tape = wp_doc.product_type == "LED Tape"

	# --- Certifications ---
	certifications = _join_list_values(
		_collect_certification_values(wp_doc, tnt_doc, attribute_links=attr_links)
	)

	# --- Dimming protocols: prefer explicit links, then tape specs and driver eligibility ---
	dimming_set = set()
	for row in attr_links:
		if row.attribute_type == "Dimming Protocol" and row.attribute_name:
			dimming_set.add(row.attribute_name)
	for ts in _iter_tape_neon_specs(tnt_doc):
		if getattr(ts, "input_protocol", None):
			dimming_set.add(ts.input_protocol)
		for p in (getattr(ts, "supported_dimming_protocols", None) or []):
			proto = getattr(p, "protocol", None) or getattr(p, "dimming_protocol", None)
			if proto:
				dimming_set.add(proto)

	# --- Gather allowed_options lookups (done in one pass) ---
	env_set = set()
	lens_set = set()
	mounting_set = set()
	finish_set = set()
	for opt in (tnt_doc.allowed_options or []):
		if hasattr(opt, "is_active") and not opt.is_active:
			continue
		otype = getattr(opt, "option_type", None)
		if otype == "Environment Rating" and opt.environment_rating:
			env_set.add(opt.environment_rating)
		elif otype == "IP Rating" and opt.ip_rating:
			env_set.add(opt.ip_rating)
		elif otype == "Lens Appearance" and getattr(opt, "lens_appearance", None):
			_add_list_values(lens_set, _tn_option_display_label(opt) or opt.lens_appearance)
		elif otype == "Mounting Method" and opt.mounting_method:
			_add_list_values(mounting_set, _tn_option_display_label(opt) or opt.mounting_method)
		elif otype == "PCB Mounting" and is_tape and getattr(opt, "pcb_mounting", None):
			_add_list_values(mounting_set, _tn_option_display_label(opt) or opt.pcb_mounting)
		elif otype == "Finish" and opt.finish:
			_add_list_values(finish_set, _tn_option_display_label(opt) or opt.finish)
		elif otype == "PCB Finish" and is_tape and getattr(opt, "pcb_finish", None):
			_add_list_values(finish_set, _tn_option_display_label(opt) or opt.pcb_finish)

	for spec_row in (tnt_doc.allowed_tape_specs or []):
		if getattr(spec_row, "environment_rating", None):
			env_set.add(spec_row.environment_rating)

	# Back-fill environment ratings from attribute_links when template has none.
	if not env_set:
		for row in attr_links:
			if row.attribute_type in ("Environment Rating", "IP Rating") and row.attribute_name:
				env_set.add(row.attribute_name)

	_add_list_values(lens_set, _get_attribute_values_by_type(attr_links, "Lens Appearance"))
	_add_list_values(finish_set, _get_attribute_values_by_type(attr_links, "Finish"))
	_add_list_values(mounting_set, _get_attribute_values_by_type(attr_links, "Mounting Method"))

	for row in frappe.get_all(
		"ilL-Rel-Mounting-Accessory-Map",
		filters={
			"template_type": "ilL-Tape-Neon-Template",
			"fixture_template": tnt_doc.name,
			"is_active": 1,
		},
		fields=["mounting_method"],
	):
		_add_list_values(mounting_set, _doc_get(row, "mounting_method"))

	_add_list_values(lens_set, _doc_get(tnt_doc, "available_lenses"))
	_add_list_values(finish_set, _doc_get(tnt_doc, "available_finishes"))
	_add_list_values(mounting_set, _doc_get(tnt_doc, "available_mountings"))

	env_ratings = _join_list_values(env_set)
	lenses = _join_list_values(lens_set)
	mountings = _join_list_values(mounting_set)
	finishes = _join_list_values(finish_set)

	# --- Input voltage: tape voltage + preferred power supply, mirroring fixtures ---
	tape_voltage_label = ", ".join(_collect_tape_neon_voltage_labels(tnt_doc))
	driver_info = _get_preferred_driver_info("ilL-Tape-Neon-Template", tnt_doc.name)
	dimming_set.update(driver_info["dimming_protocols"])
	dimming_protocols = ", ".join(sorted(dimming_set))
	driver_voltage_str = driver_info["input_voltage"]
	driver_max_wattage = _doc_get(tnt_doc, "driver_max_wattage_override") or driver_info["max_wattage"]
	if tape_voltage_label and driver_voltage_str:
		input_voltage = f"{tape_voltage_label} (Power Supply: {driver_voltage_str})"
	elif tape_voltage_label:
		input_voltage = tape_voltage_label
	else:
		input_voltage = driver_voltage_str

	# --- Operating temp range ---
	temp_range = ""
	if wp_doc.operating_temp_min_c is not None and wp_doc.operating_temp_max_c is not None:
		c_min = wp_doc.operating_temp_min_c
		c_max = wp_doc.operating_temp_max_c
		f_min = round(c_min * 9 / 5 + 32)
		f_max = round(c_max * 9 / 5 + 32)
		temp_range = f"{f_min}°F ({c_min}°C) to {f_max}°F ({c_max}°C)"

	# --- Beam angle (typically blank for neon) ---
	beam_angle = ""
	if wp_doc.beam_angle:
		val = wp_doc.beam_angle
		beam_angle = f"{int(val)}°" if val == int(val) else f"{val}°"

	result = {
		"product_name": wp_doc.product_name or "",
		"short_description": wp_doc.short_description or "",
		"sublabel": wp_doc.sublabel or "",
		"profile_dimensions": _doc_get(tnt_doc, "spec_sheet_dimensions", ""),
		"input_voltage": input_voltage,
		"beam_angle": beam_angle,
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
		"minimum_bend_diameters": _format_mm_interval(_doc_get(tnt_doc, "minimum_bend_diameter_mm")),
		"production_interval": (
			"Free-Cutting" if _is_checked(_doc_get(tnt_doc, "is_free_cutting", 0))
			else _format_mm_interval(_doc_get(tnt_doc, "production_interval_mm"))
		),
	}

	_copy_custom_spec_fields(result, wp_doc, tnt_doc)

	return result


def _collect_tape_neon_variant_rows_indesign(wp_doc, product_data):
	"""Yield fixture-shaped variant rows for LED Tape / LED Neon products.

	Produces one row per (CCT × Output Level) drawn from
	``tnt_doc.allowed_options``.  For each cell the single available lens
	bucket is populated — "frosted" — so the marketing InDesign template's
	"Other Lenses" column (which maps to `frosted`) renders the data and
	the remaining lens slugs stay blank.

	Yields the same keys :func:`_collect_variant_rows` does, so
	:func:`_pivot_to_indesign` can consume them identically.
	"""
	tnt_doc = frappe.get_cached_doc("ilL-Tape-Neon-Template", wp_doc.tape_neon_template)
	all_cols = VARIANT_COLUMNS + LENS_COLUMNS
	primary_slug = "frosted"

	offering_data = _collect_tape_neon_offering_data(tnt_doc)
	if offering_data:
		seen_keys = set()
		for td in offering_data:
			key = (td["output_label"], td["cct_name"])
			if key in seen_keys:
				continue
			seen_keys.add(key)

			row = dict(product_data)
			row["cct_name"] = td["cct_name"]
			row["cct_kelvin"] = td["cct_kelvin"]
			row["fixture_output_level"] = td["output_label"]
			row["cri_quality"] = td["cri_quality"]
			row["production_interval"] = td["production_interval"]
			row["led_pitch_mm"] = td["led_pitch_mm"]

			for slug in STANDARD_LENSES.values():
				row[f"delivered_lumens_{slug}"] = ""
				row[f"watts_per_foot_{slug}"] = ""
				row[f"max_run_length_ft_{slug}"] = ""
				row[f"max_footage_per_100w_supply_{slug}"] = ""

			delivered = td["tape_lumens"] * (td["lumen_multiplier"] or 1.0)
			if delivered:
				row[f"delivered_lumens_{primary_slug}"] = round(delivered, 1)
			row[f"watts_per_foot_{primary_slug}"] = td["watts_per_foot"]
			row[f"max_run_length_ft_{primary_slug}"] = td["max_run_ft"]
			row[f"max_footage_per_100w_supply_{primary_slug}"] = _max_footage_per_100w_supply(
				td["watts_per_foot"]
			)

			for col in all_cols:
				row.setdefault(col, "")
			yield row
		return

	# ── Fallback: sparse rows from allowed_options when no offerings exist ──
	ccts = OrderedDict()
	output_levels = OrderedDict()
	for opt in (tnt_doc.allowed_options or []):
		if hasattr(opt, "is_active") and not opt.is_active:
			continue
		otype = getattr(opt, "option_type", None)
		if otype == "CCT" and opt.cct and opt.cct not in ccts:
			cct_data = frappe.db.get_value(
				"ilL-Attribute-CCT", opt.cct,
				["kelvin", "lumen_multiplier"], as_dict=True,
			) or {}
			ccts[opt.cct] = {
				"kelvin": cct_data.get("kelvin") or 0,
				"lumen_multiplier": cct_data.get("lumen_multiplier") or 1.0,
			}
		elif otype == "Output Level" and opt.output_level and opt.output_level not in output_levels:
			level_data = frappe.db.get_value(
				"ilL-Attribute-Output Level", opt.output_level,
				["output_level_name", "value", "sku_code"], as_dict=True,
			) or {}
			output_levels[opt.output_level] = {
				"name": level_data.get("output_level_name") or opt.output_level,
				"value": level_data.get("value") or 0,
				"sku_code": level_data.get("sku_code") or "",
			}

	if not ccts:
		ccts[""] = {"kelvin": "", "lumen_multiplier": 1.0}
	if not output_levels:
		output_levels[""] = {"name": "", "value": 0, "sku_code": ""}

	# The "frosted" slug is the primary (and only) lens bucket for tape/neon.
	for ol_name, ol_info in output_levels.items():
		for cct_name, cct_info in ccts.items():
			row = dict(product_data)
			row["cct_name"] = cct_name
			row["cct_kelvin"] = cct_info["kelvin"]
			row["fixture_output_level"] = ol_info["name"]
			for slug in STANDARD_LENSES.values():
				row[f"delivered_lumens_{slug}"] = ""
				row[f"watts_per_foot_{slug}"] = ""
				row[f"max_run_length_ft_{slug}"] = ""
				row[f"max_footage_per_100w_supply_{slug}"] = ""
			for col in all_cols:
				row.setdefault(col, "")
			yield row


def _generate_tape_neon_indesign_csv(wp_doc):
	"""Return CSV content for LED Tape / LED Neon in the InDesign pivot format.

	Produces the **same 621-column layout** as :func:`_generate_indesign_csv`
	so a single marketing InDesign data-merge template accepts both fixture
	and tape/neon exports.  The guardrail ``assert`` below prevents the two
	code paths from drifting apart.
	"""
	tnt_doc = frappe.get_cached_doc("ilL-Tape-Neon-Template", wp_doc.tape_neon_template)

	product_data = _collect_tape_neon_product_data_indesign(wp_doc)
	variant_rows = list(_collect_tape_neon_variant_rows_indesign(wp_doc, product_data))
	pn_builder_columns = _collect_tn_pn_builder_columns(tnt_doc)

	headers, data_row = _pivot_to_indesign(product_data, variant_rows, pn_builder_columns)

	# Guardrail: neon and fixture exports MUST share the same header width.
	assert len(headers) == INDESIGN_TOTAL_COLUMNS, (
		f"Tape/Neon InDesign CSV produced {len(headers)} columns, "
		f"expected {INDESIGN_TOTAL_COLUMNS} (drift from fixture schema)."
	)

	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(headers)
	writer.writerow([data_row.get(col, "") for col in headers])
	return output.getvalue()


def _generate_csv(wp_doc):
	"""Return CSV content as a string (flat: one row per CCT × output level)."""
	product_data = _collect_product_data(wp_doc)

	# ── Part Number Builder columns ──
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)
	pn_headers, pn_data = _collect_pn_builder_columns(ft_doc)

	output = io.StringIO()
	writer = csv.writer(output)

	headers = PRODUCT_COLUMNS + CUSTOM_SPEC_COLUMNS + VARIANT_COLUMNS + LENS_COLUMNS + pn_headers
	writer.writerow(headers)

	for row in _collect_variant_rows(wp_doc, product_data):
		row.update(pn_data)
		writer.writerow([row.get(col, "") for col in headers])

	return output.getvalue()


# ──────────────────────────────────────────────────────────
# InDesign pivot format
# ──────────────────────────────────────────────────────────

# Static product columns in the InDesign layout.
INDESIGN_PRODUCT_COLUMNS = [
	"Product Name",
	"Sublabel",
	"Input Voltage",
	"Beam Angle",
	"Operating Temp Range",
	"L70 Life Hours",
	"Warranty Years",
	"Certifications",
	"Lenses",
	"Finish",
	"Available Mountings",
	"Environment Ratings",
	"Dimming Protocols",
	"Driver Max Wattage",
	"Dimensions (L×W×H)",
	"CRI Quality",
	"Production Interval",
	"Minimum Bend Diameters",
] + [label for label, _field in _INDESIGN_SPEC_MAP]

# Lens groupings used for per-output-level watt/run columns.
_INDESIGN_LENS_GROUPS = [
	("White Lens", "white"),
	("Black Lens", "black"),
	("Other Lenses", "frosted"),  # "Other Lenses" = frosted lens data
]

# Lens names for per-CCT lumen columns (all four standard lenses).
_INDESIGN_LUMEN_LENSES = [
	("White Lens", "white"),
	("Black Lens", "black"),
	("Frosted Lens", "frosted"),
	("Clear Lens", "clear"),
]


def _parse_output_level_sort_key(output_level_str):
	"""Extract leading integer from an output-level string for sorting.

	>>> _parse_output_level_sort_key("200 lm/ft")
	200
	>>> _parse_output_level_sort_key("High")
	0
	"""
	match = re.match(r"(\d+)", output_level_str or "")
	return int(match.group(1)) if match else 0


def _fmt_num(val):
	"""Format a numeric value, stripping trailing '.0' for whole numbers."""
	if val == int(val):
		return str(int(val))
	return str(val)


def _safe_float(val):
	"""Convert *val* to float, returning ``None`` for blanks / non-numeric."""
	if val == "" or val is None:
		return None
	try:
		return float(val)
	except (TypeError, ValueError):
		return None


def _pivot_to_indesign(product_data, variant_rows, pn_builder_columns=None):
	"""Pivot flat variant rows into one InDesign data-merge row.

	Returns ``(headers, data_row)`` where *headers* is a fixed-width list of
	column names and *data_row* is a dict keyed by those names.  The header
	list always has the same length regardless of how many CCTs or output
	levels the product actually uses (empty strings for unused slots).

	*pn_builder_columns* is an optional ``(pn_headers, pn_data)`` tuple
	from :func:`_collect_pn_builder_columns`; when provided the part-number
	builder columns are appended after the output-level columns.
	"""
	# ── 1. Unique CCTs sorted by kelvin ──
	ccts = []
	seen_ccts = set()
	for row in variant_rows:
		cct = row.get("cct_name", "")
		if cct and cct not in seen_ccts:
			seen_ccts.add(cct)
			ccts.append((cct, row.get("cct_kelvin", 0)))
	ccts.sort(key=lambda x: x[1] or 0)

	# ── 2. Unique output levels sorted by leading integer ──
	output_levels = []
	seen_ols = set()
	for row in variant_rows:
		ol = row.get("fixture_output_level", "")
		if ol and ol not in seen_ols:
			seen_ols.add(ol)
			output_levels.append(ol)
	output_levels.sort(key=_parse_output_level_sort_key)

	# ── 3. Build fixed headers ──
	headers = list(INDESIGN_PRODUCT_COLUMNS)

	for i in range(1, MAX_CCTS + 1):
		headers.append(f"Light Color (CCT) {i}")

	for j in range(1, MAX_OUTPUT_LEVELS + 1):
		headers.append(f"Output Options {j}")
		for label, _slug in _INDESIGN_LENS_GROUPS:
			headers.append(f"Watts per Foot ({label}) {j}")
			headers.append(f"Max Run Length ({label}) {j}")
			headers.append(f"Max Footage per 100W Supply ({label}) {j}")
		for i in range(1, MAX_CCTS + 1):
			for label, _slug in _INDESIGN_LUMEN_LENSES:
				headers.append(f"{label} - Output {j} - Lumen {i}")

	# ── 4. Build data row ──
	# Aggregate variant-level fields (unique non-empty values, comma-separated)
	cri_values = []
	prod_interval_values = []
	seen_cri = set()
	seen_pi = set()
	for row in variant_rows:
		cri = row.get("cri_quality", "")
		if cri and cri not in seen_cri:
			seen_cri.add(cri)
			cri_values.append(cri)
		pi = row.get("production_interval", "")
		if pi and pi not in seen_pi:
			seen_pi.add(pi)
			prod_interval_values.append(pi)

	data_row = {
		"Product Name": product_data.get("product_name", ""),
		"Sublabel": product_data.get("sublabel", ""),
		"Input Voltage": product_data.get("input_voltage", ""),
		"Beam Angle": product_data.get("beam_angle", ""),
		"Operating Temp Range": product_data.get("operating_temp_range_c", ""),
		"L70 Life Hours": product_data.get("l70_life_hours", ""),
		"Warranty Years": product_data.get("warranty_years", ""),
		"Certifications": product_data.get("certifications", ""),
		"Lenses": product_data.get("available_lenses", ""),
		"Finish": product_data.get("available_finishes", ""),
		"Available Mountings": product_data.get("available_mountings", ""),
		"Environment Ratings": product_data.get("environment_ratings", ""),
		"Dimming Protocols": product_data.get("dimming_protocols", ""),
		"Driver Max Wattage": product_data.get("driver_max_wattage", ""),
		"Dimensions (L×W×H)": product_data.get("profile_dimensions", ""),
		"CRI Quality": ", ".join(cri_values),
		"Production Interval": ", ".join(prod_interval_values) or product_data.get("production_interval", ""),
		"Minimum Bend Diameters": product_data.get("minimum_bend_diameters", ""),
	}

	for label, field in _INDESIGN_SPEC_MAP:
		data_row[label] = product_data.get(field, "")

	for i, (cct_name, _kelvin) in enumerate(ccts, 1):
		data_row[f"Light Color (CCT) {i}"] = cct_name

	# Index variant rows by (output_level, cct_name)
	row_lookup = {}
	for row in variant_rows:
		key = (row.get("fixture_output_level", ""), row.get("cct_name", ""))
		row_lookup.setdefault(key, row)

	for j, ol in enumerate(output_levels, 1):
		data_row[f"Output Options {j}"] = ol

		# Aggregate watts / max-run per lens group across all CCTs
		for label, slug in _INDESIGN_LENS_GROUPS:
			watts_vals = []
			run_vals = []
			for cct_name, _ in ccts:
				row = row_lookup.get((ol, cct_name), {})
				w = _safe_float(row.get(f"watts_per_foot_{slug}", ""))
				if w is not None:
					watts_vals.append(w)
				r = _safe_float(row.get(f"max_run_length_ft_{slug}", ""))
				if r is not None:
					run_vals.append(r)
			data_row[f"Watts per Foot ({label}) {j}"] = f"{_fmt_num(max(watts_vals))}W" if watts_vals else ""
			data_row[f"Max Run Length ({label}) {j}"] = f"{_fmt_num(min(run_vals))}ft" if run_vals else ""
			data_row[f"Max Footage per 100W Supply ({label}) {j}"] = (
				_format_max_footage_per_100w_supply(max(watts_vals)) if watts_vals else ""
			)

		# Per-CCT lumen values
		for i, (cct_name, _) in enumerate(ccts, 1):
			row = row_lookup.get((ol, cct_name), {})
			for label, slug in _INDESIGN_LUMEN_LENSES:
				data_row[f"{label} - Output {j} - Lumen {i}"] = row.get(f"delivered_lumens_{slug}", "")

	# ── Append Part Number Builder columns ──
	if pn_builder_columns:
		pn_headers, pn_data = pn_builder_columns
		headers.extend(pn_headers)
		data_row.update(pn_data)

	return headers, data_row


def _generate_indesign_csv(wp_doc):
	"""Return CSV content in the InDesign data-merge pivot format."""
	product_data = _collect_product_data(wp_doc)
	variant_rows = list(_collect_variant_rows(wp_doc, product_data))

	# ── Part Number Builder columns ──
	ft_doc = None
	if wp_doc.fixture_template:
		ft_doc = frappe.get_cached_doc("ilL-Fixture-Template", wp_doc.fixture_template)
	pn_builder_columns = _collect_pn_builder_columns(ft_doc)

	headers, data_row = _pivot_to_indesign(product_data, variant_rows, pn_builder_columns)

	# Guardrail: header width must stay in lockstep with the tape/neon export.
	assert len(headers) == INDESIGN_TOTAL_COLUMNS, (
		f"Fixture InDesign CSV produced {len(headers)} columns, "
		f"expected {INDESIGN_TOTAL_COLUMNS} (drift from unified schema)."
	)

	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(headers)
	writer.writerow([data_row.get(col, "") for col in headers])
	return output.getvalue()


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

@frappe.whitelist()
def export_spec_sheet_csv(webflow_product: str, format: str = "indesign") -> dict:
	"""Generate a spec-sheet CSV for a Webflow Product and attach it.

	Args:
		webflow_product: Name of the ilL-Webflow-Product document.
		format: ``"indesign"`` (default) for the pivoted InDesign
			data-merge layout, ``"flat"`` for the legacy fixture
			one-row-per-CCT×output-level format, or
			``"tape_neon_flat"`` to opt into the legacy flat layout
			for LED Tape / LED Neon products.

	Returns:
		dict with ``success``, ``file_url``, and ``file_name``.
	"""
	wp_doc = frappe.get_doc("ilL-Webflow-Product", webflow_product)

	if wp_doc.product_type in ("LED Tape", "LED Neon"):
		if not wp_doc.tape_neon_template:
			return {"success": False, "error": _("No Tape/Neon Template linked — please set the 'Tape / Neon Template' field to generate a spec sheet.")}
		# Default to the unified InDesign schema so marketing's data-merge
		# template accepts tape/neon exports identically to fixtures.  The
		# original flat layout remains available as an opt-in.
		if format == "tape_neon_flat":
			csv_content = _generate_tape_neon_flat_csv(wp_doc)
		else:
			csv_content = _generate_tape_neon_indesign_csv(wp_doc)
	elif wp_doc.product_type == "Fixture Template":
		if not wp_doc.fixture_template:
			return {"success": False, "error": _("No Fixture Template linked — cannot generate spec sheet.")}
		if format == "flat":
			csv_content = _generate_csv(wp_doc)
		else:
			csv_content = _generate_indesign_csv(wp_doc)
	else:
		return {"success": False, "error": _("Spec sheet export is only available for Fixture Template, LED Tape, and LED Neon products.")}

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
