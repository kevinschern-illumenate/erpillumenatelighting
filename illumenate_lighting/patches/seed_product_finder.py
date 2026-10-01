"""Seed the Product Finder questions, glossary and settings from the shipped content.

Idempotent: questions and glossary terms that already exist are left untouched, so
staff edits survive. ERP value maps are filled in where an answer clearly names one
ERP record (exact name, label or code, or a single whole-word match); anything left
unmapped shows on the Product Finder Coverage report for staff to finish.
Both Desk switches (portal and public) stay off until staff turn them on.
"""

import json
from pathlib import Path

import frappe

from illumenate_lighting.illumenate_lighting.portal.product_finder.content import GLOSSARY, QUESTION, SETTINGS
from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import FACETS, needs_value_maps
from illumenate_lighting.illumenate_lighting.portal.quiz_prefill import match_option

SEED = Path(__file__).resolve().parents[1] / "illumenate_lighting/portal/product_finder/seed/content.json"
# Fields that name an ERP record the way staff and dealers would.
LABEL_FIELDS = {
	"ilL-Webflow-Category": ("category_name", "category_slug"),
	"ilL-Attribute-Environment Rating": ("label", "code"),
	"ilL-Attribute-IP Rating": ("label", "code"),
	"ilL-Attribute-CCT": ("label", "code", "kelvin"),
	"ilL-Attribute-Mounting Method": ("label", "code"),
	"ilL-Attribute-Lens Appearance": ("label", "code"),
	"ilL-Attribute-Finish": ("code",),
	"ilL-Attribute-Dimming Protocol": ("label", "code"),
	"ilL-Attribute-Output Voltage": ("voltage_name", "voltage_code"),
	"ilL-Attribute-LED Package": ("code",),
}


def execute():
	content = json.loads(SEED.read_text(encoding="utf-8"))
	for term in content["glossary"]:
		if not frappe.db.exists(GLOSSARY, term["term_key"]):
			frappe.get_doc({"doctype": GLOSSARY, **term}).insert(ignore_permissions=True)
	candidates = {}
	# Earlier questions first: conditions may only point at questions that already exist.
	for question in sorted(content["questions"], key=lambda row: row["sequence"]):
		if frappe.db.exists(QUESTION, question["question_key"]):
			continue
		doc = frappe.get_doc({"doctype": QUESTION, **question})
		doc.set("value_maps", value_maps(question, candidates))
		doc.insert(ignore_permissions=True)
	apply_settings_defaults()


def value_maps(question, candidates) -> list:
	facet = question.get("facet")
	if not facet or not needs_value_maps(facet):
		return []
	rows = []
	for doctype in FACETS[facet]["doctypes"]:
		if doctype not in candidates:
			candidates[doctype] = records(doctype)
		for option in question.get("options") or []:
			if option.get("is_no_preference"):
				continue
			match = match_option(option["value"], candidates[doctype]) or match_option(
				option["label"], candidates[doctype]
			)
			if match:
				rows.append(
					{"option_value": option["value"], "attribute_doctype": doctype, "attribute_value": match}
				)
	return rows


def records(doctype) -> list:
	if not frappe.db.table_exists(doctype):
		return []
	meta = frappe.get_meta(doctype)
	fields = [field for field in LABEL_FIELDS.get(doctype, ()) if meta.has_field(field)]
	rows = frappe.get_all(doctype, fields=["name", *fields], ignore_permissions=True)
	return [
		{
			"value": row.name,
			"label": next(
				(row.get(field) for field in fields if field not in ("code", "kelvin") and row.get(field)),
				None,
			),
			"code": row.get("code") or row.get("voltage_code"),
			"kelvin": row.get("kelvin"),
		}
		for row in rows
	]


def apply_settings_defaults():
	"""Give every empty setting its documented default; both switches stay off."""
	settings = frappe.get_single(SETTINGS)
	for field in settings.meta.fields:
		if field.default is not None and settings.get(field.fieldname) in (None, ""):
			settings.set(field.fieldname, field.default)
	settings.save(ignore_permissions=True)
