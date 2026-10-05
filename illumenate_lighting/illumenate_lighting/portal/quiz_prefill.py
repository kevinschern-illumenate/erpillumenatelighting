"""Turn guided-quiz answers into configurator selections the chosen template offers.

The quiz sends plain answers such as ``moisture=Damp``, ``cct=3000K`` or ``finish=Silver``.
Configurator selects hold attribute record names (``Anodized Silver``), so the browser
could not match most answers. This resolves each answer on the server against the
options the template actually offers, and never invents a value the template lacks.
"""

import re

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import TAPE_NEON_CATEGORIES

# quiz key -> (attribute DocType, linear selection key, tape/neon selection key, linear option list)
FIELDS = {
	"moisture": (
		"ilL-Attribute-Environment Rating",
		"environment_rating_code",
		"environment_rating",
		"environment_ratings",
	),
	"cct": ("ilL-Attribute-CCT", "cct_code", "cct", "ccts"),
	"lens": ("ilL-Attribute-Lens Appearance", "lens_appearance_code", None, "lens_appearances"),
	"finish": ("ilL-Attribute-Finish", "finish_code", "finish", "finishes"),
	"mounting": ("ilL-Attribute-Mounting Method", "mounting_method_code", None, "mountings"),
}
LABEL_FIELDS = {
	"ilL-Attribute-Environment Rating": ["label", "code"],
	"ilL-Attribute-CCT": ["label", "code", "kelvin"],
	"ilL-Attribute-Lens Appearance": ["label", "code"],
	"ilL-Attribute-Finish": ["code"],
	"ilL-Attribute-Mounting Method": ["label", "code"],
}
# Tape/neon allowed-option rows: option_type -> field holding the attribute name.
TAPE_NEON_OPTIONS = {
	"ilL-Attribute-Environment Rating": ("Environment Rating", "environment_rating"),
	"ilL-Attribute-CCT": ("CCT", "cct"),
	"ilL-Attribute-Finish": ("Finish", "finish"),
}
SPECTRUM_TYPES = {
	"Static white": {"Static White"},
	"Tunable white": {"Tunable White"},
	"Dim-to-warm": {"Dim to Warm"},
	"Full-color": {"RGB", "RGB+W", "RGBW", "RGB+TW", "RGBTW"},
}
LINEAR, TAPE_NEON = "Linear Fixture", TAPE_NEON_CATEGORIES


def _norm(value) -> str:
	return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _kelvin(value):
	match = re.fullmatch(r"\s*(\d{4})\s*k?\s*", str(value or ""), re.IGNORECASE)
	return int(match.group(1)) if match else None


def match_option(answer, candidates):
	"""Return the ``value`` of the one candidate an answer names, or None.

	Exact name/label/code first, then Kelvin for CCTs ("3000K" ↔ 3000), then a single
	whole-word containment ("Silver" ↔ "Anodized Silver"). Ambiguity resolves to None.
	"""
	wanted = _norm(answer)
	if not wanted:
		return None
	exact = [
		c for c in candidates if wanted in {_norm(c.get(k)) for k in ("value", "label", "code") if c.get(k)}
	]
	if len(exact) == 1:
		return exact[0]["value"]
	kelvin = _kelvin(answer)
	if kelvin:
		by_kelvin = [c for c in candidates if c.get("kelvin") == kelvin or _kelvin(c.get("value")) == kelvin]
		if len(by_kelvin) == 1:
			return by_kelvin[0]["value"]
	pattern = re.compile(r"\b" + re.escape(wanted) + r"\b")
	partial = [
		c
		for c in candidates
		if pattern.search(_norm(c.get("value"))) or pattern.search(_norm(c.get("label")))
	]
	return partial[0]["value"] if len(partial) == 1 else None


def resolve(category, template, handoff) -> dict:
	"""``{"template", "selections", "applied", "unmatched"}`` for a configurator page.

	``applied`` and ``unmatched`` list ``{"field", "answer"[, "value"]}`` so the page can say
	which quiz answers were pre-filled and which this product does not offer.
	"""
	result = {"template": template, "selections": {}, "applied": [], "unmatched": []}
	if category not in (LINEAR, *TAPE_NEON):
		return result
	candidates = (
		_linear_candidates(template, handoff) if category == LINEAR else _tape_neon_candidates(template)
	)
	for key, (doctype, linear_key, tape_neon_key, _option_list) in FIELDS.items():
		answer = handoff.get(key)
		selection_key = linear_key if category == LINEAR else tape_neon_key
		if not answer or not selection_key:
			continue
		value = match_option(answer, candidates.get(doctype, []))
		if value is None:
			result["unmatched"].append({"field": key, "answer": answer})
			continue
		result["selections"][selection_key] = value
		result["applied"].append({"field": key, "answer": answer, "value": value})
	if category == LINEAR and candidates.get("led_package"):
		result["selections"]["led_package_code"] = candidates["led_package"]
	return result


def _linear_candidates(template, handoff) -> dict:
	"""The option lists the linear configurator itself loads for this template."""
	if not template or not frappe.db.exists("ilL-Fixture-Template", template):
		return _all_candidates()
	from illumenate_lighting.illumenate_lighting.api.configurator_engine import (
		get_cascading_options_for_template,
	)

	options = (get_cascading_options_for_template(template) or {}).get("options") or {}
	wanted = SPECTRUM_TYPES.get(handoff.get("light_type"), set())
	packages = [row for row in options.get("led_packages") or [] if row.get("spectrum_type") in wanted]
	led_package = packages[0]["value"] if len(packages) == 1 else None
	if led_package:
		# CCTs depend on the LED package, exactly as in the browser.
		options["ccts"] = (
			(get_cascading_options_for_template(template, led_package_code=led_package) or {}).get("options")
			or {}
		).get("ccts") or options.get("ccts")
	result = {doctype: options.get(option_list) or [] for doctype, _l, _t, option_list in FIELDS.values()}
	result["led_package"] = led_package
	return result


def _tape_neon_candidates(template) -> dict:
	"""Attributes on the template's active allowed rows; tape/neon selects hold their names."""
	if not template or not frappe.db.exists("ilL-Tape-Neon-Template", template):
		return _all_candidates()
	doc = frappe.get_cached_doc("ilL-Tape-Neon-Template", template)
	names = {doctype: set() for doctype in TAPE_NEON_OPTIONS}
	for row in doc.get("allowed_options") or []:
		for doctype, (option_type, field) in TAPE_NEON_OPTIONS.items():
			if row.get("option_type") == option_type and row.get("is_active") and row.get(field):
				names[doctype].add(row.get(field))
	for row in doc.get("allowed_tape_specs") or []:
		if row.get("environment_rating"):
			names["ilL-Attribute-Environment Rating"].add(row.get("environment_rating"))
	return {doctype: _details(doctype, sorted(values)) for doctype, values in names.items() if values}


def _all_candidates() -> dict:
	return {doctype: _details(doctype) for doctype, *_rest in FIELDS.values()}


def _details(doctype, names=None) -> list:
	filters = {"name": ["in", names]} if names is not None else {}
	rows = frappe.get_all(
		doctype, filters=filters, fields=["name", *LABEL_FIELDS[doctype]], ignore_permissions=True
	)
	return [{"value": row.name, **{key: row.get(key) for key in LABEL_FIELDS[doctype]}} for row in rows]
