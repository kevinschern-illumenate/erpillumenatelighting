"""Pure visibility and pruning rules shared with the browser Finder engine."""

import math

CATALOG_ROUTES = {"accessories": "Accessory,Component"}
_MISSING = object()


def _equal(left, right):
	# JavaScript strict equality does not equate booleans with numbers.
	return (
		type(left) is type(right) or (type(left) in (int, float) and type(right) in (int, float))
	) and left == right


def test_clause(clause, answers):
	value = answers.get(clause.get("q"), _MISSING)
	if "eq" in clause:
		return _equal(value, clause["eq"])
	if "ne" in clause:
		return not _equal(value, clause["ne"])
	if "in" in clause:
		return isinstance(clause["in"], list) and any(_equal(value, v) for v in clause["in"])
	if "exists" in clause:
		has = value is not _MISSING and value is not None and value != ""
		return has if clause["exists"] else not has
	if value is None or isinstance(value, (bool, list, dict)) or value == "":
		return False
	try:
		number = float(value)
	except (TypeError, ValueError, OverflowError):
		return False
	if not math.isfinite(number):
		return False
	for operator in ("gt", "gte", "lt", "lte"):
		if operator in clause:
			threshold = clause[operator]
			return {
				"gt": number > threshold,
				"gte": number >= threshold,
				"lt": number < threshold,
				"lte": number <= threshold,
			}[operator]
	return False


def eval_condition(group, answers):
	if not group:
		return True
	return all(test_clause(c, answers) for c in group.get("all", [])) and (
		"any" not in group or any(test_clause(c, answers) for c in group["any"])
	)


def family_of(definition, answers):
	return next((answers.get(q["id"]) for q in definition["questions"] if q["type"] == "family"), None)


def is_visible(question, answers, family=None):
	families = question.get("families") or ["Any"]
	if question["type"] != "family" and family and "Any" not in families and family not in families:
		return False
	return eval_condition(question.get("visibleWhen"), answers) and not (
		question.get("skipWhen") and eval_condition(question["skipWhen"], answers)
	)


def visible_options(question, answers):
	return [
		o
		for o in question.get("options", [])
		if eval_condition(o.get("visibleWhen"), answers)
		and not (o.get("hideWhen") and eval_condition(o["hideWhen"], answers))
	]


def prune(definition, answers):
	result = {q["id"]: answers[q["id"]] for q in definition["questions"] if q["id"] in answers}
	for question in definition["questions"]:
		key = question["id"]
		if not is_visible(question, result, family_of(definition, result)):
			result.pop(key, None)
		elif key in result and question["type"] in ("single", "multi", "family"):
			valid = {o["value"] for o in visible_options(question, result)}
			if question["type"] == "multi" and isinstance(result[key], list):
				result[key] = [value for value in result[key] if value in valid]
			elif not isinstance(result[key], str) or result[key] not in valid:
				result.pop(key, None)
	return result


def route(definition, answers):
	for question in definition["questions"]:
		if question["type"] == "family":
			for option in question.get("options", []):
				if option["value"] == answers.get(question["id"]) and (
					option.get("routes_to") == "Catalog only" or option.get("routesTo") == "catalog"
				):
					return {
						"route": "catalog",
						"query": {"type": CATALOG_ROUTES.get(option["value"], "Accessory,Component")},
					}
	return None
