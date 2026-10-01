"""Build the quiz definition the Finder UI renders from the Desk records.

The output keeps the condition shape the quiz engine (``engine.js``) already
evaluates: ``visibleWhen`` / ``skipWhen`` / option ``hideWhen`` groups of
``{"all": [...], "any": [...]}`` clauses such as ``{"q": "moisture", "in": [...]}``.
"""

import frappe
from frappe.utils import cint

from illumenate_lighting.illumenate_lighting.portal.product_finder.content import GLOSSARY, QUESTION, SETTINGS

CACHE_PREFIX = "ill_product_finder:definition"
TYPES = {
	"Single": "single",
	"Multi": "multi",
	"Family chooser": "family",
	"Number": "number",
	"Range": "range",
	"Info": "info",
}
OPERATORS = {
	"equals": "eq",
	"not equals": "ne",
	"in": "in",
	"greater than": "gt",
	"at least": "gte",
	"less than": "lt",
	"at most": "lte",
}
QUESTION_FIELDS = [
	"name",
	"question_key",
	"label",
	"short_label",
	"is_active",
	"sequence",
	"question_type",
	"required",
	"tooltip",
	"learn_more",
	"glossary_term",
	"number_min",
	"number_max",
	"number_step",
	"unit",
	"placeholder",
	"range_default_low",
	"range_default_high",
]
OPTION_FIELDS = [
	"parent",
	"value",
	"label",
	"description",
	"image",
	"swatch_color",
	"glossary_term",
	"note",
	"is_featured",
	"badge_text",
	"routes_to",
	"is_active",
]
CONDITION_FIELDS = [
	"parent",
	"applies_to",
	"option_value",
	"match_group",
	"depends_on_question",
	"operator",
	"value",
]
SETTINGS_FIELDS = (
	"banner_enabled",
	"banner_headline",
	"banner_text",
	"banner_cta_label",
	"banner_image",
	"verification_title",
	"verification_text",
)


def current_version() -> int:
	return cint(frappe.db.get_single_value(SETTINGS, "definition_version"))


def content_changed(*_args, **_kwargs):
	"""Bump the content version so caches and in-progress sessions see the change.

	``set_single_value`` writes directly, so this does not re-trigger Settings hooks.
	"""
	frappe.db.set_single_value(SETTINGS, "definition_version", current_version() + 1)


def load_definition(include_inactive=False) -> dict:
	version = current_version()
	key = f"{CACHE_PREFIX}:{version}:{int(bool(include_inactive))}"
	cached = frappe.cache().get_value(key)
	if cached:
		return cached
	definition = build_definition(version, include_inactive=include_inactive)
	frappe.cache().set_value(key, definition, expires_in_sec=3600)
	return definition


def build_definition(version, include_inactive=False) -> dict:
	filters = {} if include_inactive else {"is_active": 1}
	questions = frappe.get_all(
		QUESTION, filters=filters, fields=QUESTION_FIELDS, order_by="sequence asc, name asc"
	)
	names = [row.name for row in questions]
	children = {"options": {}, "conditions": {}, "families": {}}
	if names:
		scope = {"parenttype": QUESTION, "parent": ["in", names]}
		for field, doctype, fields in (
			("options", "ilL-Child-Finder-Option", OPTION_FIELDS),
			("conditions", "ilL-Child-Finder-Condition", CONDITION_FIELDS),
			("families", "ilL-Child-Finder-Family", ["parent", "family"]),
		):
			for row in frappe.get_all(doctype, filters=scope, fields=fields, order_by="idx asc"):
				children[field].setdefault(row.parent, []).append(row)

	glossary = {
		row.name: {"label": row.label, "tooltip": row.tooltip or "", "learnMore": row.learn_more or ""}
		for row in frappe.get_all(GLOSSARY, fields=["name", "label", "tooltip", "learn_more"])
	}
	settings = frappe.get_cached_doc(SETTINGS)
	return {
		"version": version,
		"questions": [
			question_payload(
				row,
				children["options"].get(row.name, []),
				children["conditions"].get(row.name, []),
				children["families"].get(row.name, []),
				include_inactive=include_inactive,
			)
			for row in questions
		],
		"glossary": glossary,
		"settings": {field: settings.get(field) for field in SETTINGS_FIELDS},
	}


def question_payload(row, options, conditions, families, include_inactive=False) -> dict:
	payload = {
		"id": row.question_key or row.name,
		"label": row.label,
		"shortLabel": row.short_label or row.label,
		"type": TYPES.get(row.question_type, "single"),
		"required": bool(cint(row.required)),
		"families": sorted({family.family for family in families}) or ["Any"],
		"tooltip": row.tooltip or "",
		"learnMore": row.learn_more or "",
		"glossaryKey": row.glossary_term or None,
	}
	if include_inactive:
		payload["draft"] = not cint(row.is_active)
	if row.question_type in ("Number", "Range"):
		payload.update(
			{
				"min": row.number_min,
				"max": row.number_max,
				"step": row.number_step,
				"unit": row.unit or "",
				"placeholder": row.placeholder or "",
			}
		)
		if row.question_type == "Range":
			payload.update({"defaultLow": row.range_default_low, "defaultHigh": row.range_default_high})
	visible = condition_group(c for c in conditions if c.applies_to == "Show question when")
	skip = condition_group(c for c in conditions if c.applies_to == "Skip question when")
	if visible:
		payload["visibleWhen"] = visible
	if skip:
		payload["skipWhen"] = skip
	if row.question_type in TYPES and TYPES[row.question_type] in ("single", "multi", "family"):
		payload["options"] = [
			option_payload(
				option,
				[
					c
					for c in conditions
					if c.applies_to == "Hide option when" and c.option_value == option.value
				],
			)
			for option in options
			if cint(option.is_active)
		]
	return payload


def option_payload(option, hide_conditions) -> dict:
	payload = {
		"value": option.value,
		"label": option.label,
		"description": option.description or "",
		"image": option.image or None,
		"color": option.swatch_color or None,
		"glossaryKey": option.glossary_term or None,
		"note": option.note or "",
		"featured": bool(cint(option.is_featured)),
		"badge": option.badge_text or "",
	}
	if option.routes_to:
		payload["routesTo"] = "catalog"
	hide = condition_group(hide_conditions)
	if hide:
		payload["hideWhen"] = hide
	return payload


def condition_group(rows) -> dict | None:
	"""Rows marked All must all pass, and at least one Any row must pass (engine.js semantics)."""
	group = {"all": [], "any": []}
	for row in rows:
		group["any" if row.match_group == "Any" else "all"].append(clause(row))
	group = {key: clauses for key, clauses in group.items() if clauses}
	return group or None


def clause(row) -> dict:
	operator, value = row.operator, str(row.value or "").strip()
	if operator in ("answered", "not answered"):
		return {"q": row.depends_on_question, "exists": operator == "answered"}
	if operator == "in":
		return {
			"q": row.depends_on_question,
			"in": [part.strip() for part in value.split(",") if part.strip()],
		}
	if operator in ("equals", "not equals"):
		return {"q": row.depends_on_question, OPERATORS[operator]: value}
	return {"q": row.depends_on_question, OPERATORS[operator]: float(value)}
