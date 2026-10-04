"""Private matching metadata; never returned by the client definition endpoint."""

import copy

import frappe

from illumenate_lighting.illumenate_lighting.portal.product_finder import definition
from illumenate_lighting.illumenate_lighting.portal.product_finder.content import QUESTION, SETTINGS

QUESTION_FIELDS = (
	"facet",
	"match_mode",
	"comparison",
	"unknown_policy",
	"relax_priority",
	"verification_reason_template",
)
SETTINGS_FIELDS = (
	"default_unknown_policy",
	"verification_gate",
	"results_limit",
	"session_expiry_days",
	"portal_enabled",
	"public_enabled",
)


def load(include_inactive=False):
	version = definition.current_version()
	key = f"ill_product_finder:server:{version}:{int(bool(include_inactive))}"
	cached = frappe.cache().get_value(key)
	if cached is not None:
		return cached
	result = build(include_inactive)
	frappe.cache().set_value(key, result, expires_in_sec=3600)
	return result


def build(include_inactive=False):
	result = copy.deepcopy(definition.load_definition(include_inactive))
	settings = frappe.get_cached_doc(SETTINGS)
	result["settings"].update({key: settings.get(key) for key in SETTINGS_FIELDS})
	result["settings"]["public_brands"] = [r.brand for r in settings.get("public_brands") or []]
	questions = frappe.get_all(
		QUESTION,
		filters={} if include_inactive else {"is_active": 1},
		fields=["name", "question_key", *QUESTION_FIELDS],
	)
	by_id = {r.question_key or r.name: r for r in questions}
	names = [r.name for r in questions]
	options, maps = {}, {}
	if names:
		scope = {"parenttype": QUESTION, "parent": ["in", names]}
		for row in frappe.get_all(
			"ilL-Child-Finder-Option",
			filters=scope,
			fields=["parent", "value", "rank", "numeric_min", "numeric_max", "is_no_preference", "routes_to"],
		):
			options[(row.parent, row.value)] = row
		for row in frappe.get_all(
			"ilL-Child-Finder-Value-Map",
			filters=scope,
			fields=["parent", "option_value", "attribute_doctype", "attribute_value"],
		):
			maps.setdefault(row.parent, {}).setdefault(row.option_value, []).append(
				(row.attribute_doctype, row.attribute_value)
			)
	for question in result["questions"]:
		row = by_id[question["id"]]
		question.update({key: row.get(key) for key in QUESTION_FIELDS})
		question["is_family"] = question["type"] == "family"
		question["number"] = {k: question.get(k) for k in ("min", "max", "step", "unit")}
		question["value_maps"] = maps.get(row.name, {})
		if question.get("unknown_policy") in (None, "", "Use default"):
			question["unknown_policy"] = settings.default_unknown_policy or "Verify"
		for option in question.get("options", []):
			detail = options.get((row.name, option["value"]), {})
			option.update(
				{key: detail.get(key) for key in ("rank", "numeric_min", "numeric_max", "routes_to")}
			)
			option["no_preference"] = bool(detail.get("is_no_preference"))
	return result
