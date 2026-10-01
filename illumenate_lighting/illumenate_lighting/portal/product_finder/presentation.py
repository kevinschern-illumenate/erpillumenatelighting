"""Small portal view models for Finder entry points and catalog context."""

from urllib.parse import urlencode

import frappe

from illumenate_lighting.illumenate_lighting.portal.product_finder import definition, engine, sessions
from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS
from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import FAMILIES


def chooser(query):
	data = definition.load_definition()
	question = next((q for q in data["questions"] if q["type"] == "family"), None)
	options = (
		question["options"]
		if question
		else [{"value": f, "label": f, "featured": f == "Linear Fixture"} for f in FAMILIES]
	)
	context = {k: query[k] for k in ("schedule", "line_key", "line_idx", "draft", "finder") if query.get(k)}
	result = []
	for option in sorted(options, key=lambda o: not o.get("featured")):
		routed = option.get("routesTo") == "catalog"
		result.append(
			{
				**option,
				"href": ("/portal/products?" if routed else "/portal/configure?")
				+ urlencode(
					{
						**context,
						**({"type": "Accessory,Component"} if routed else {"category": option["value"]}),
					}
				),
			}
		)
	return result


def banner():
	from illumenate_lighting.illumenate_lighting.portal.jinja_methods import ill_finder_enabled

	if not ill_finder_enabled():
		return None
	settings = frappe.get_cached_doc(SETTINGS)
	if not settings.banner_enabled or str(
		frappe.defaults.get_user_default("ill_finder_banner_dismissed")
	) == str(definition.current_version()):
		return None
	result = {
		"headline": settings.banner_headline,
		"text": settings.banner_text,
		"cta": settings.banner_cta_label,
		"image": settings.banner_image,
		"resume": None,
	}
	rows = frappe.get_all(
		sessions.DOCTYPE,
		filters={"user": frappe.session.user, "status": "Active"},
		fields=["session_token", "quiz_answers"],
		order_by="modified desc",
		limit=1,
	)
	if rows:
		data = definition.load_definition()
		answers = engine.prune(data, sessions.decoded(rows[0].quiz_answers))
		questions = [
			q
			for q in data["questions"]
			if q.get("required") and engine.is_visible(q, answers, engine.family_of(data, answers))
		]
		percent = (
			round(sum(bool(answers.get(q["id"])) for q in questions) / len(questions) * 100)
			if questions
			else 0
		)
		result["resume"] = {
			"percent": percent,
			"url": "/portal/product-finder?" + urlencode({"session": rows[0].session_token}),
		}
	return result


def answer_chips(answers):
	chips = []
	for question in definition.load_definition()["questions"]:
		value = answers.get(question["id"])
		if value is None:
			continue
		chosen = value if isinstance(value, list) else [value]
		options = [
			o for o in question.get("options", []) if o["value"] in chosen and not o.get("noPreference")
		]
		if question.get("options") and not options:
			continue
		label = (
			", ".join(o["label"] for o in options)
			if options
			else (f"{value['low']}-{value['high']}" if isinstance(value, dict) else str(value))
			+ (" " + question["unit"] if question.get("unit") else "")
		)
		chips.append(
			{
				"question_id": question["id"],
				"label": f"{question.get('shortLabel') or question['label']}: {label}",
			}
		)
	return chips
