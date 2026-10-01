"""Validation of Desk-edited Finder questions. Pure functions over plain dicts."""

import re

from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import COMPARISONS, FACETS, FAMILIES

QUESTION = "ilL-Finder-Question"
GLOSSARY = "ilL-Finder-Glossary-Term"
SETTINGS = "ilL-Product-Finder-Settings"

KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
# Hex colors or a simple linear-gradient of hex stops and angles; nothing that could
# carry url(), expressions or a second declaration into a style attribute.
SWATCH = re.compile(r"^(#[0-9a-fA-F]{3,8}|linear-gradient\([0-9a-zA-Z#%.,\s-]+\))$")
CHOICE_TYPES = ("Single", "Multi", "Family chooser")
VALUE_FREE_OPERATORS = ("answered", "not answered")
NUMERIC_OPERATORS = ("greater than", "at least", "less than", "at most")


def default_comparison(facet):
	kind = (FACETS.get(facet) or {}).get("kind")
	return COMPARISONS.get(kind, ("Any of",))[0]


def validate_question(doc, others) -> list:
	"""Return human-readable problems with a question; empty when it can be saved.

	``doc`` is the question as a dict (with child rows); ``others`` are the other
	questions as dicts with ``name``, ``sequence``, ``is_active`` and ``question_type``.
	"""
	errors = []
	key = doc.get("question_key") or ""
	qtype = doc.get("question_type")
	active = bool(doc.get("is_active"))
	if not KEY.match(key):
		errors.append(
			f"Question Key '{key}' must start with a lowercase letter and use only lowercase letters, numbers and underscores."
		)

	options = doc.get("options") or []
	values = [str(row.get("value") or "").strip() for row in options]
	duplicates = sorted({value for value in values if values.count(value) > 1})
	if duplicates:
		errors.append(f"Option values must be unique: {', '.join(duplicates)}.")
	for row in options:
		color = (row.get("swatch_color") or "").strip()
		if color and not SWATCH.match(color):
			errors.append(
				f"Option '{row.get('value')}': swatch color must be a hex color or a linear-gradient of hex colors."
			)
		low, high = row.get("numeric_min"), row.get("numeric_max")
		if low not in (None, "") and high not in (None, "") and float(low) > float(high):
			errors.append(f"Option '{row.get('value')}': numeric minimum is above the maximum.")
	if qtype in CHOICE_TYPES and active and not any(row.get("is_active") for row in options):
		errors.append("Add at least one active option.")
	if qtype not in CHOICE_TYPES and options:
		errors.append(f"{qtype} questions do not use options; remove them or change the question type.")

	if qtype in ("Number", "Range"):
		low, high = doc.get("number_min"), doc.get("number_max")
		if low not in (None, "") and high not in (None, "") and float(low) >= float(high):
			errors.append("Minimum must be below Maximum.")

	if qtype == "Family chooser":
		for row in options:
			if row.get("value") not in FAMILIES and row.get("routes_to") != "Catalog only":
				errors.append(
					f"Option '{row.get('value')}' must be a product type ({', '.join(FAMILIES)}) or route to the catalog."
				)
		if doc.get("conditions"):
			errors.append("The product-type question is always asked first and cannot have conditions.")
		if active:
			for other in others:
				if other.get("is_active") and other.get("question_type") == "Family chooser":
					errors.append(
						f"Only one active product-type question is allowed; '{other.get('name')}' is already active."
					)
				elif other.get("is_active") and int(other.get("sequence") or 0) <= int(
					doc.get("sequence") or 0
				):
					errors.append(
						f"The product-type question must come first; '{other.get('name')}' has a lower or equal sequence."
					)

	elif active:
		for other in others:
			if (
				other.get("is_active")
				and other.get("question_type") == "Family chooser"
				and int(other.get("sequence") or 0) >= int(doc.get("sequence") or 0)
			):
				errors.append(
					f"Use a sequence above {other.get('sequence')}: the product-type question '{other.get('name')}' must come first."
				)

	errors.extend(_condition_errors(doc, others, values))
	errors.extend(_matching_errors(doc, values))
	return errors


def _condition_errors(doc, others, values):
	errors = []
	by_name = {other.get("name"): other for other in others}
	sequence = int(doc.get("sequence") or 0)
	for row in doc.get("conditions") or []:
		target = row.get("depends_on_question")
		label = f"Condition on '{target}'"
		if target == doc.get("question_key") or target == doc.get("name"):
			errors.append("A question cannot depend on itself.")
			continue
		other = by_name.get(target)
		if other is None:
			errors.append(f"{label}: that question does not exist.")
			continue
		if not other.get("is_active"):
			errors.append(f"{label}: that question is not active.")
		elif int(other.get("sequence") or 0) >= sequence:
			errors.append(f"{label}: it must come earlier in the quiz (lower sequence).")
		operator = row.get("operator")
		value = str(row.get("value") or "").strip()
		if operator not in VALUE_FREE_OPERATORS and not value:
			errors.append(f"{label}: enter a value for '{operator}'.")
		if operator in NUMERIC_OPERATORS:
			try:
				float(value)
			except ValueError:
				errors.append(f"{label}: '{operator}' needs a number.")
		if row.get("applies_to") == "Hide option when" and row.get("option_value") not in values:
			errors.append(f"{label}: '{row.get('option_value')}' is not an option on this question.")
	return errors


def _matching_errors(doc, values):
	errors = []
	facet = doc.get("facet")
	mode = doc.get("match_mode") or "None"
	maps = doc.get("value_maps") or []
	if mode != "None" and not facet:
		errors.append("Choose the Product Fact this question filters on, or set Match Mode to None.")
	if not facet:
		if maps:
			errors.append("ERP mappings need a Product Fact.")
		return errors
	spec = FACETS.get(facet)
	if spec is None:
		return [f"Unknown Product Fact '{facet}'."]
	comparison = doc.get("comparison")
	allowed = COMPARISONS.get(spec["kind"], ())
	if comparison and comparison not in allowed:
		errors.append(f"'{comparison}' does not apply to {spec['label']}; use {', '.join(allowed)}.")
	if doc.get("question_type") == "Info":
		errors.append("Info questions have no answer to match on.")
	if spec.get("derived") and maps:
		errors.append(f"{spec['label']} is read from product data; it does not use ERP mappings.")
	seen = set()
	no_preference = {row.get("value") for row in doc.get("options") or [] if row.get("is_no_preference")}
	for row in maps:
		option = row.get("option_value")
		if option not in values:
			errors.append(f"Mapping for '{option}': that is not an option on this question.")
		elif option in no_preference:
			errors.append(
				f"Mapping for '{option}': a No Preference option matches every product; remove its mapping."
			)
		if row.get("attribute_doctype") not in spec["doctypes"]:
			errors.append(
				f"Mapping for '{option}': {spec['label']} maps to {', '.join(spec['doctypes']) or 'no ERP records'}."
			)
		identity = (option, row.get("attribute_doctype"), row.get("attribute_value"))
		if identity in seen:
			errors.append(f"Mapping for '{option}' to '{row.get('attribute_value')}' is listed twice.")
		seen.add(identity)
	return errors
