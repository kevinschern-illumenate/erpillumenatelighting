# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLFixtureTemplate(Document):
	pass


# ──────────────────────────────────────────────────────────
# Default section order for auto-populate
# ──────────────────────────────────────────────────────────
SECTION_ORDER_DEFAULTS = {
	"Series": 1,
	"Dry/Wet": 2,
	"CCT": 3,
	"Output": 4,
	"Lens": 5,
	"Mounting": 6,
	"Finish": 7,
	"Start Feed Type": 8,
	"End Feed Type": 9,
}


def _add_rows(doc, section_name, section_order, pairs):
	"""Append option rows for *section_name* if none already exist.

	*pairs* is a list of ``(code, label)`` tuples.  Duplicates (by code)
	are collapsed so each code appears at most once.
	"""
	existing = {
		r.section_name for r in (doc.get("part_number_builder") or [])
	}
	if section_name in existing:
		return

	seen = set()
	option_order = 0
	for code, label in pairs:
		if not code:
			continue
		if code in seen:
			continue
		seen.add(code)
		option_order += 1
		doc.append("part_number_builder", {
			"section_name": section_name,
			"section_order": section_order,
			"option_code": code,
			"option_label": label,
			"option_order": option_order,
		})


def _options_for_type(doc, option_type, link_field, attr_doctype, code_field="code", label_field="label"):
	"""Return ``(code, label)`` pairs from allowed_options of *option_type*."""
	pairs = []
	for opt in (doc.allowed_options or []):
		if getattr(opt, "option_type", None) != option_type:
			continue
		if not getattr(opt, "is_active", True):
			continue
		linked = getattr(opt, link_field, None)
		if not linked:
			continue
		attr_doc = frappe.get_cached_doc(attr_doctype, linked)
		code = getattr(attr_doc, code_field, "") or ""
		label = getattr(attr_doc, label_field, "") or ""
		if code:
			pairs.append((code, label))
	return pairs


@frappe.whitelist()
def populate_part_number_builder(docname):
	"""Auto-fill empty sections of the Part Number Builder child table.

	Only sections that have **no existing rows** are populated — manual
	edits are preserved.
	"""
	doc = frappe.get_doc("ilL-Fixture-Template", docname)

	# ── Series ──
	if doc.series:
		series_doc = frappe.get_cached_doc("ilL-Attribute-Series", doc.series)
		code = getattr(series_doc, "code", "") or ""
		label = getattr(series_doc, "series_name", "") or ""
		if code:
			_add_rows(doc, "Series", SECTION_ORDER_DEFAULTS["Series"], [(code, label)])

	# ── Dry/Wet  (Environment Rating) ──
	pairs = _options_for_type(
		doc, "Environment Rating", "environment_rating",
		"ilL-Attribute-Environment Rating",
	)
	if pairs:
		_add_rows(doc, "Dry/Wet", SECTION_ORDER_DEFAULTS["Dry/Wet"], pairs)

	# ── CCT  (from tape offerings) ──
	cct_pairs = []
	for ato in (doc.allowed_tape_offerings or []):
		to_doc = frappe.get_cached_doc("ilL-Rel-Tape Offering", ato.tape_offering)
		if to_doc.cct:
			cct_doc = frappe.get_cached_doc("ilL-Attribute-CCT", to_doc.cct)
			code = getattr(cct_doc, "code", "") or ""
			label = getattr(cct_doc, "cct_name", "") or ""
			if code:
				cct_pairs.append((code, label))
	if cct_pairs:
		_add_rows(doc, "CCT", SECTION_ORDER_DEFAULTS["CCT"], cct_pairs)

	# ── Output  (from tape offerings → output level) ──
	output_pairs = []
	for ato in (doc.allowed_tape_offerings or []):
		to_doc = frappe.get_cached_doc("ilL-Rel-Tape Offering", ato.tape_offering)
		if to_doc.output_level:
			ol_doc = frappe.get_cached_doc("ilL-Attribute-Output Level", to_doc.output_level)
			code = getattr(ol_doc, "sku_code", "") or ""
			label = getattr(ol_doc, "output_level_name", "") or ""
			if code:
				output_pairs.append((code, label))
	if output_pairs:
		_add_rows(doc, "Output", SECTION_ORDER_DEFAULTS["Output"], output_pairs)

	# ── Lens  (Lens Appearance) ──
	pairs = _options_for_type(
		doc, "Lens Appearance", "lens_appearance",
		"ilL-Attribute-Lens Appearance",
	)
	if pairs:
		_add_rows(doc, "Lens", SECTION_ORDER_DEFAULTS["Lens"], pairs)

	# ── Mounting  (Mounting Method) ──
	pairs = _options_for_type(
		doc, "Mounting Method", "mounting_method",
		"ilL-Attribute-Mounting Method",
	)
	if pairs:
		_add_rows(doc, "Mounting", SECTION_ORDER_DEFAULTS["Mounting"], pairs)

	# ── Finish ──
	pairs = _options_for_type(
		doc, "Finish", "finish",
		"ilL-Attribute-Finish",
		label_field="finish_name",
	)
	if pairs:
		_add_rows(doc, "Finish", SECTION_ORDER_DEFAULTS["Finish"], pairs)

	# ── Start Feed Type  (Power Feed Type) ──
	pairs = _options_for_type(
		doc, "Power Feed Type", "power_feed_type",
		"ilL-Attribute-Power Feed Type",
	)
	if pairs:
		_add_rows(doc, "Start Feed Type", SECTION_ORDER_DEFAULTS["Start Feed Type"], pairs)

	# ── End Feed Type  (Endcap Style) ──
	pairs = _options_for_type(
		doc, "Endcap Style", "endcap_style",
		"ilL-Attribute-Endcap Style",
	)
	if pairs:
		_add_rows(doc, "End Feed Type", SECTION_ORDER_DEFAULTS["End Feed Type"], pairs)

	doc.save(ignore_permissions=True)
	return doc.as_dict()
