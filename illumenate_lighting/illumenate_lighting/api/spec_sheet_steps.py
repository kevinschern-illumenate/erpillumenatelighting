"""Work out what a schedule line's generated spec sheet should show.

``resolve(schedule, line)`` returns the line's template, the template's current spec sheet,
the part number, the Part Number Builder step codes and the footer text. The fill itself is
``spec_sheet_fill``.

The part number is the source of truth for the steps: it is what the customer orders, and the
builder on the sheet spells it out. ``steps_from_part_number`` walks the template's
``part_no_configurator`` rows in step order, each taking the first unused dash-separated token
of the part number that fits it (part numbers do not always follow the step order):

- a feed pair (Start/End Feed Direction, then its Feed Length) takes one token such as ``E1``
  (direction ``E``, length ``1``) or ``C``;
- a free Length (allowed value ``__length_metadata__``) takes a number such as ``216.0``;
- any other step takes the token when it is one of its codes, else its only or default code
  without using up the token (a kit's stock ``2M`` is not in its part number).

206 Lighting templates are left on the old submittal path (owner, 2026-11-23).
"""

import json
import re

import frappe

CONFIGURATOR_CHILD = "ilL-Child-Webflow-Configurator-Option"
CONFIGURATOR_FIELD = "part_no_configurator"
LOOKUP_STEP = 90
LENGTH_METADATA = "__length_metadata__"
FEED_PAIRS = (("Start Feed Direction", "Start Feed Length"), ("End Feed Direction", "End Feed Length"))
OUT_OF_SCOPE_BRANDS = ("lighting_206",)

# A configured build: (line field, build doctype).
_BUILDS = (
	("configured_group", "ilL-Configured-Group"),
	("configured_fixture", "ilL-Configured-Fixture"),
	("configured_tape_neon", "ilL-Configured-Tape-Neon"),
	("configured_led_sheet", "ilL-Configured-LED-Sheet"),
	("kit_template", "ilL-Extrusion-Kit-Template"),
)

# The build's stored codes, compared with what the part number gave each option type.
_SKU_FIELDS = {
	"ilL-Configured-Fixture": {
		"Environment Rating": "sku_environment_code",
		"CCT": "sku_cct_code",
		"Lens Appearance": "sku_lens_code",
		"Output Level": "sku_fixture_output_code",
		"Mounting Method": "sku_mounting_code",
		"Finish": "sku_finish_code",
	},
	"ilL-Configured-Tape-Neon": {
		"CCT": "sku_cct_code",
		"Output Level": "sku_output_code",
		"Environment Rating": "sku_environment_code",
	},
	"ilL-Configured-LED-Sheet": {
		"Environment Rating": "sku_environment_code",
		"CCT": "sku_cct_code",
		"Output Level": "sku_output_code",
		"Mounting Method": "sku_mounting_code",
		"Finish": "sku_finish_code",
	},
}

# Built length, runs and watts for the line summary: (doctype, length mm, runs, watts).
_SUMMARY_FIELDS = {
	"ilL-Configured-Fixture": ("manufacturable_overall_length_mm", "runs_count", "total_watts"),
	"ilL-Configured-Tape-Neon": ("manufacturable_length_mm", None, "total_watts"),
	"ilL-Configured-LED-Sheet": (None, None, "total_system_watts"),
}


def _allowed(row):
	raw = row.get("allowed_values_json")
	try:
		values = json.loads(raw) if isinstance(raw, str) else (raw or [])
	except (TypeError, ValueError):
		return []
	return [value for value in values if isinstance(value, dict)] if isinstance(values, list) else []


def _codes(row):
	return [str(value.get("code") or "").strip() for value in _allowed(row) if value.get("code")]


def _is_free_length(row):
	return any(value.get("value") == LENGTH_METADATA for value in _allowed(row))


def _default_code(row):
	codes = _codes(row)
	if len(codes) == 1:
		return codes[0]
	defaults = [
		str(value.get("code")) for value in _allowed(row) if value.get("is_default") and value.get("code")
	]
	return defaults[0] if len(defaults) == 1 else None


def _match(token, codes):
	return next((code for code in codes if code.lower() == token.lower()), None)


def builder_steps(rows):
	"""The template's Part Number Builder steps in order (lookups 90 and up, and the series, left out)."""
	steps = []
	for row in rows or []:
		try:
			number = int(row.get("option_step"))
		except (TypeError, ValueError):
			continue
		if number <= 0 or number >= LOOKUP_STEP:
			continue
		steps.append({**row, "option_step": number})
	return sorted(steps, key=lambda row: row["option_step"])


def _strip_series(part_number, template):
	tokens = [token for token in str(part_number or "").strip().split("-") if token != ""]
	series = [token for token in str(template or "").strip().split("-") if token != ""]
	if series and [token.lower() for token in tokens[: len(series)]] == [token.lower() for token in series]:
		return tokens[len(series) :]
	return tokens


def steps_from_part_number(part_number, template, rows):
	"""``(steps, warnings)``: ``{"1": "20", "7": "216.0", ...}`` read from the part number."""
	steps, warnings = {}, []
	tokens = _strip_series(part_number, template)
	ordered = builder_steps(rows)
	labels = {row.get("option_label"): row for row in ordered}
	pairs = {
		labels[direction]["option_step"]: labels.get(length)
		for direction, length in FEED_PAIRS
		if direction in labels
	}
	paired_lengths = {row["option_step"] for row in pairs.values() if row}
	used = set()
	other_codes = {code.lower() for row in ordered for code in _codes(row)}

	def take(test):
		"""The first unused token that passes ``test``, in part number order.

		Part numbers do not always follow the step order (a fixture's output comes before its
		lens), so each step looks through every token not yet taken.
		"""
		for index, token in enumerate(tokens):
			if index in used:
				continue
			found = test(token)
			if found:
				used.add(index)
				return found
		return None

	for row in ordered:
		step = row["option_step"]
		if step in paired_lengths:
			continue
		label = row.get("option_label") or row.get("option_type") or f"Step {step}"
		if step in pairs:
			codes = _codes(row)

			def feed(token, codes=codes):
				match = re.fullmatch(r"([A-Za-z]+)(\d+(?:\.\d+)?)?", token)
				direction = _match(match.group(1), codes) if match else None
				return (direction, match.group(2)) if direction else None

			found = take(feed)
			if found:
				steps[str(step)] = found[0]
				length_row = pairs[step]
				if found[1] and length_row:
					steps[str(length_row["option_step"])] = found[1]
			else:
				warnings.append(f"{label}: no feed in the part number {part_number}")
			continue
		if _is_free_length(row):
			found = take(
				lambda token: (
					token
					if re.fullmatch(r"\d+(?:\.\d+)?", token) and token.lower() not in other_codes
					else None
				)
			)
			if found:
				steps[str(step)] = found
			else:
				warnings.append(f"{label}: no length in the part number {part_number}")
			continue
		codes = _codes(row)
		found = take(lambda token, codes=codes: _match(token, codes))
		if found:
			steps[str(step)] = found
			continue
		fallback = _default_code(row)
		if fallback:
			steps[str(step)] = fallback
			continue
		if row.get("is_required") in (0, "0", False):
			continue
		warnings.append(f"{label}: the part number {part_number} has no code this sheet offers")
	unused = [token for index, token in enumerate(tokens) if index not in used]
	if unused:
		warnings.append(
			f"Part number {part_number}: {', '.join(unused)} did not match a step on the spec sheet"
		)
	return steps, warnings


def compare_with_build(steps, rows, doctype, build):
	"""Warnings where the build's stored codes disagree with the part number."""
	fields = _SKU_FIELDS.get(doctype)
	if not fields or not build:
		return []
	warnings = []
	for row in builder_steps(rows):
		field = fields.get(row.get("option_type"))
		stored = str(build.get(field) or "").strip() if field else ""
		chosen = steps.get(str(row["option_step"]))
		if stored and chosen and stored.lower() != chosen.lower():
			warnings.append(
				f"{row.get('option_label') or row.get('option_type')}: the part number says {chosen}, the build says {stored}"
			)
	return warnings


def configurator_rows(template_doctype, template):
	return frappe.get_all(
		CONFIGURATOR_CHILD,
		filters={"parent": template, "parenttype": template_doctype, "parentfield": CONFIGURATOR_FIELD},
		fields=[
			"option_step",
			"option_type",
			"option_label",
			"is_required",
			"depends_on_step",
			"allowed_values_json",
		],
		order_by="option_step asc",
	)


def template_brand(template_doctype, template):
	rows = frappe.get_all(
		"ilL-Child-Webflow-Brand-Target",
		filters={"parent": template, "parenttype": template_doctype, "enabled": 1},
		pluck="brand",
	)
	return rows[0] if rows else None


def _mm_to_inches(mm):
	try:
		value = float(mm or 0)
	except (TypeError, ValueError):
		return None
	return f"{value / 25.4:.1f}″" if value > 0 else None


def _watts(value):
	try:
		value = float(value or 0)
	except (TypeError, ValueError):
		return None
	return f"{value:g}W total" if value > 0 else None


def fed_lines(schedule, line):
	"""The fixture types a power supply line feeds (one, or several joined)."""
	targets = [
		part.strip() for part in str(line.get("power_supply_for_line") or "").split(",") if part.strip()
	]
	if not targets:
		return ""
	ids = {}
	for row in schedule.get("lines") or []:
		for key in (row.get("line_key"), row.get("name"), row.get("line_id")):
			if key:
				ids[str(key)] = row.get("line_id") or ""
	return ", ".join(dict.fromkeys(ids.get(target) or target for target in targets))


def line_summary(schedule, line, build_doctype=None, build=None):
	"""One line for the sheet: qty, built length, runs, watts and the supplies that power it."""
	from illumenate_lighting.illumenate_lighting.portal.packets import _part_number

	parts = []
	if line.get("qty"):
		parts.append(f"Qty {int(line.qty)}")
	length_field, runs_field, watts_field = _SUMMARY_FIELDS.get(build_doctype, (None, None, None))
	length = (build or {}).get(length_field) if length_field else None
	length = _mm_to_inches(length or line.get("manufacturable_length_mm"))
	if length:
		parts.append(f"Built length {length}")
	runs = (build or {}).get(runs_field) if runs_field else None
	if runs and int(runs) > 1:
		parts.append(f"{int(runs)} runs")
	watts = _watts((build or {}).get(watts_field)) if watts_field else None
	if watts:
		parts.append(watts)
	keys = {str(key) for key in (line.get("line_key"), line.get("name"), line.get("line_id")) if key}
	supplies = []
	for row in schedule.get("lines") or []:
		feeds = {
			part.strip() for part in str(row.get("power_supply_for_line") or "").split(",") if part.strip()
		}
		if feeds & keys:
			number = _part_number(row) or row.get("accessory_item")
			if number:
				supplies.append(f"{number} ({row.line_id})" if row.get("line_id") else number)
	if supplies:
		parts.append("Power: " + ", ".join(dict.fromkeys(supplies)))
	return " · ".join(parts)


def _build_for(line):
	for field, doctype in _BUILDS:
		if line.get(field):
			return doctype, line.get(field)
	return None, None


def _template_for(line):
	"""``(template doctype, template, build doctype, build name)`` behind an ilLumenate line."""
	from illumenate_lighting.illumenate_lighting.api import spec_submittal
	from illumenate_lighting.illumenate_lighting.portal.packets import _template_spec_sheet

	if line.get("manufacturer_type") == "ACCESSORY":
		for doctype, resolver in (
			("ilL-Driver-Template", spec_submittal._driver_document_source),
			("ilL-Controller-Template", spec_submittal._controller_document_source),
		):
			try:
				source = resolver(line)
			except ValueError:
				source = None
			if source and source.get("template") and not source.get("resolution_error"):
				return doctype, source["template"], None, None
		return None, None, None, None
	build_doctype, build_name = _build_for(line)
	if not build_doctype:
		return None, None, None, None
	template_doctype, template, _sheet = _template_spec_sheet({"doctype": build_doctype, "name": build_name})
	return template_doctype, template, build_doctype, build_name


def project_text(schedule, line):
	project = {}
	if schedule.get("ill_project"):
		project = (
			frappe.db.get_value(
				"ilL-Project", schedule.ill_project, ["project_name", "location"], as_dict=True
			)
			or {}
		)
	fixture_type = line.get("line_id") or ""
	if line.get("power_supply_for_line"):
		fixture_type = fed_lines(schedule, line) or fixture_type
	return {
		"project_name": project.get("project_name") or schedule.get("schedule_name") or "",
		"fixture_type": fixture_type,
		"project_location": (line.get("location") or "").strip() or project.get("location") or "",
	}


def resolve(schedule, line):
	"""Everything the fill needs for one line, or None when the line has no ilLumenate template
	with a spec sheet (other makers, approved literature, 206 Lighting)."""
	from illumenate_lighting.illumenate_lighting.portal.packets import _part_number

	if line.get("manufacturer_type") not in ("ILLUMENATE", "ACCESSORY"):
		return None
	template_doctype, template, build_doctype, build_name = _template_for(line)
	if not (template_doctype and template):
		return None
	if template_brand(template_doctype, template) in OUT_OF_SCOPE_BRANDS:
		return None
	sheet = frappe.db.get_value(template_doctype, template, "spec_sheet")
	if not sheet:
		return None
	part_number = _part_number(line) or ""
	rows = configurator_rows(template_doctype, template)
	warnings = []
	if not builder_steps(rows):
		warnings.append(f"{template} has no Part Number Builder steps; save the template to rebuild them")
		steps = {}
	else:
		steps, warnings = steps_from_part_number(part_number, template, rows)
	build = None
	if build_doctype in _SKU_FIELDS or build_doctype in _SUMMARY_FIELDS:
		fields = sorted(
			{
				*_SKU_FIELDS.get(build_doctype, {}).values(),
				*(field for field in _SUMMARY_FIELDS.get(build_doctype, ()) if field),
			}
		)
		build = frappe.db.get_value(build_doctype, build_name, fields, as_dict=True) if fields else None
		warnings += compare_with_build(steps, rows, build_doctype, build)
	text = project_text(schedule, line)
	text["line_summary"] = line_summary(schedule, line, build_doctype, build)
	return {
		"template_doctype": template_doctype,
		"template": template,
		"build": {"doctype": build_doctype, "name": build_name} if build_doctype else None,
		"sheet_url": sheet,
		"part_number": part_number,
		"steps": steps,
		"text": text,
		"warnings": warnings,
	}


@frappe.whitelist()
def readiness(template_doctype=None, limit=500):
	"""Read only (System Manager): which active ilLumenate templates a packet can fill.

	For each template: its Part Number Builder step count, whether its spec sheet has form
	fields and step radios, and its highlight style (``steps`` = current tags, ``rows`` = an
	older sheet to regenerate). ``ready`` is true when a packet would use the generated sheet.
	"""
	from illumenate_lighting.illumenate_lighting.api import spec_sheet_fill
	from illumenate_lighting.illumenate_lighting.api.spec_submittal import _get_file_doc_by_url
	from illumenate_lighting.illumenate_lighting.web_listing_schema import TEMPLATE_DOCTYPES

	frappe.only_for("System Manager")
	doctypes = [template_doctype] if template_doctype else list(TEMPLATE_DOCTYPES)
	report = []
	for doctype in doctypes:
		names = frappe.get_all(
			doctype,
			filters={"product_status": ["in", ["Active", "Internal Only"]]},
			pluck="name",
			limit=int(limit),
		)
		for name in names:
			if template_brand(doctype, name) in OUT_OF_SCOPE_BRANDS:
				continue
			entry = {
				"template_doctype": doctype,
				"template": name,
				"steps": len(builder_steps(configurator_rows(doctype, name))),
				"spec_sheet": frappe.db.get_value(doctype, name, "spec_sheet"),
				"has_form": False,
				"step_fields": 0,
				"highlight_style": "none",
			}
			try:
				file = _get_file_doc_by_url(entry["spec_sheet"]) if entry["spec_sheet"] else None
				if file:
					sheet = spec_sheet_fill.inspect(file.get_content())
					entry.update(
						has_form=sheet["has_form"],
						step_fields=len(sheet["steps"]),
						highlight_style=sheet["highlight_style"],
					)
			except Exception as error:
				entry["error"] = str(error)
			entry["ready"] = bool(entry["steps"] and entry["has_form"] and entry["step_fields"])
			report.append(entry)
	return {
		"ready": sum(1 for entry in report if entry["ready"]),
		"total": len(report),
		"templates": report,
	}
