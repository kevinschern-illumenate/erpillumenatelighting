"""Deterministic eligibility, ranking, relaxation, and option counts for the Finder."""

import hashlib
from collections import Counter

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json
from illumenate_lighting.illumenate_lighting.portal.product_finder import engine
from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import needs_value_maps
from illumenate_lighting.illumenate_lighting.portal.quiz_prefill import _norm


def requirements(definition, answers):
	result = []
	for question in definition["questions"]:
		answer = answers.get(question["id"])
		if (
			answer is None
			or not question.get("facet")
			or question.get("match_mode") in (None, "None")
			or question["type"] in ("family", "info")
		):
			continue
		if not engine.is_visible(question, answers, engine.family_of(definition, answers)):
			continue
		selected = answer if isinstance(answer, list) else [answer]
		options = [
			o for o in question.get("options", []) if o["value"] in selected and not o.get("no_preference")
		]
		if question["type"] in ("single", "multi") and not options:
			continue
		wanted = {
			name for o in options for _doctype, name in question.get("value_maps", {}).get(o["value"], [])
		}
		if not needs_value_maps(question["facet"]):
			wanted = {_norm(o["value"]) for o in options}
		label = (
			", ".join(o["label"] for o in options)
			if options
			else (f"{answer['low']}-{answer['high']}" if isinstance(answer, dict) else str(answer))
		)
		result.append(
			{**question, "answer": answer, "answer_label": label, "selected": options, "wanted": wanted}
		)
	return result


def assess(requirement, product):
	values = product.get("facets", {}).get(requirement["facet"])
	if not values:
		return "unknown"
	comparison = requirement.get("comparison") or "Any of"
	selected = requirement["selected"]
	if comparison == "Meets or exceeds":
		ranks = [
			o.get("rank")
			for o in requirement.get("options", [])
			if any(name in values for _doctype, name in requirement.get("value_maps", {}).get(o["value"], []))
			and o.get("rank") is not None
		]
		needed = [o["rank"] for o in selected if o.get("rank") is not None]
		if not ranks or not needed:
			return "unknown"
		passed = max(ranks) >= max(needed)
	elif comparison == "At least":
		threshold = selected[0].get("numeric_min") if selected else requirement["answer"]
		if threshold is None:
			return "unknown"
		passed = max(values) >= float(threshold)
	elif comparison == "Within band":
		band = selected[0] if selected else {}
		low, high = band.get("numeric_min"), band.get("numeric_max")
		if low is None or high is None:
			return "unknown"
		passed = any(low <= value <= high for value in values)
	elif comparison == "Range covers":
		answer = requirement["answer"]
		passed = min(values) <= answer["low"] and max(values) >= answer["high"]
	else:
		wanted = requirement["wanted"]
		if not wanted:
			return "unknown"
		actual = set(values) if needs_value_maps(requirement["facet"]) else {_norm(v) for v in values}
		passed = bool(actual & wanted)
	return "pass" if passed else "fail"


def verification_reason(requirement):
	label = requirement["answer_label"]
	try:
		text = (requirement.get("verification_reason_template") or "{answer}").format(answer=label)
	except (KeyError, ValueError, IndexError):
		text = label
	if not requirement.get("verification_reason_template"):
		text = f"{requirement['label']}: {label}"
	return {
		"question": requirement["id"],
		"question_label": requirement["label"],
		"answer": requirement["answer"],
		"reason": text,
	}


def inspect_product(product, needed):
	states, verify, excluded = {}, [], []
	for requirement in needed:
		state = assess(requirement, product)
		states[requirement["id"]] = state
		policy = requirement.get("unknown_policy") or "Verify"
		if state == "unknown" and policy == "Verify":
			verify.append(verification_reason(requirement))
		if requirement["match_mode"] == "Hard" and (
			state == "fail" or (state == "unknown" and policy == "Exclude")
		):
			excluded.append(requirement["id"])
	return states, verify, excluded


def _score(product, needed, states, verify):
	score = 50
	for req in needed:
		state = states[req["id"]]
		if req["match_mode"] != "Soft" or state == "unknown":
			continue
		facet = req["facet"]
		if facet == "lumens_per_ft" and req["selected"]:
			band = req["selected"][0]
			low, high = band["numeric_min"], band["numeric_max"]
			dist = min(abs(v - (low + high) / 2) for v in product["facets"][facet])
			spread = 400 if high >= 9000 else max(150, high - low)
			score += 20 if state == "pass" else max(-10, 15 - dist / spread * 15)
		else:
			positive, negative = (
				(12, -6) if facet in ("cct", "cct_range") else (10, -8) if facet == "cri_min" else (4, -2)
			)
			score += positive if state == "pass" else negative
	return int(max(0, min(100, score - (5 if verify else 0))) + 0.5)


def _available(facts, public=False):
	from illumenate_lighting.illumenate_lighting.portal.rollout import reason

	return [
		p
		for p in facts
		if p["capability"] == "quantity"
		or (p["capability"] == "configure" and reason(p["product_type"], public=public) == "ok")
	]


def companions(matches, answers, facts, definition=None):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import server_definition

	definition = definition or server_definition.load()
	by_name = {p["name"]: p for p in facts}
	matched = {p["name"] for p in matches}
	top = [by_name[m["name"]] for m in matches[:10] if m["name"] in by_name]
	voltage = set().union(*(p["facets"].get("output_voltage") or set() for p in top))
	protocols = set().union(*(p["facets"].get("dimming_protocol") or set() for p in top))
	for req in requirements(definition, answers):
		if req["facet"] == "dimming_protocol" and req["wanted"]:
			protocols = req["wanted"]
	result = {}
	for product in facts:
		if product["name"] in matched or product["capability"] not in ("configure", "quantity"):
			continue
		shared = protocols & set(product["facets"].get("dimming_protocol") or [])
		if (
			product["family"] == "Driver"
			and shared
			and voltage & set(product["facets"].get("output_voltage") or [])
		):
			result[product["name"]] = (
				"Powers "
				+ ", ".join(sorted(voltage & set(product["facets"]["output_voltage"])))
				+ " with "
				+ ", ".join(sorted(shared))
				+ " dimming"
			)
		elif product["family"] == "Controller" and shared:
			result[product["name"]] = "Controls " + ", ".join(sorted(shared))
	for product in top:
		for row in product.get("compatible_products", []):
			name = row.get("related_product")
			if name in by_name and name not in matched:
				result.setdefault(name, row.get("relationship_type") or "Works with")
	return [{"name": name, "relation": relation} for name, relation in list(result.items())[:24]]


def match(answers, *, user=None, definition=None, facts=None, limit=None, public=False):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import facts as catalog
	from illumenate_lighting.illumenate_lighting.portal.product_finder import server_definition

	# Explicit fact sets support previews and brand scopes without sharing their cached results.
	if facts is not None:
		return _match(answers, user=user, definition=definition, facts=facts, limit=limit, public=public)
	definition = definition if definition is not None else server_definition.load()
	products = _available(catalog.load(), public)
	digest = hashlib.sha1(
		canonical_json(
			[answers, definition, frappe.session.user, public, limit, [p["name"] for p in products]]
		).encode()
	).hexdigest()
	key = f"ill_product_finder:match:{definition['version']}:{catalog.catalog_stamp()}:{digest}"
	cached = frappe.cache().get_value(key)
	if cached is None:
		cached = _match(answers, user=user, definition=definition, facts=products, limit=limit, public=public)
		frappe.cache().set_value(key, cached, expires_in_sec=600)
	# Callers enrich the transport result; do not mutate a shared cache value.
	import copy

	return copy.deepcopy(cached)


def _match(answers, *, user=None, definition=None, facts=None, limit=None, public=False):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import (
		facts as catalog,
	)
	from illumenate_lighting.illumenate_lighting.portal.product_finder import (
		server_definition,
	)

	definition = definition if definition is not None else server_definition.load()
	facts = facts if facts is not None else catalog.load()
	answers = engine.prune(definition, answers)
	routed = engine.route(definition, answers)
	if routed:
		return {
			**routed,
			"matches": [],
			"companions": [],
			"counts": {"match": 0, "verify": 0, "excluded": 0, "by_family": {}},
			"relaxed": [],
			"definition_version": definition["version"],
			"catalog_stamp": catalog.catalog_stamp(),
		}
	family = engine.family_of(definition, answers)
	available = _available(facts, public)
	products = [p for p in available if not family or p["family"] == family]
	needed = requirements(definition, answers)
	eligible, excluded = [], Counter()
	for product in products:
		states, verify, failed = inspect_product(product, needed)
		excluded.update(failed)
		if not failed:
			eligible.append((product, states, verify))
	soft = sorted(
		[r for r in needed if r["match_mode"] == "Soft"],
		key=lambda r: r.get("relax_priority") if r.get("relax_priority") is not None else 999,
	)
	remaining, relaxed = list(soft), []
	while True:
		# Unknown values survive for verification (or silent inclusion); they are not failures.
		survivors = [row for row in eligible if all(row[1][r["id"]] != "fail" for r in remaining)]
		if survivors or not remaining:
			break
		relaxed.append(remaining.pop(0)["label"])
	matches = []
	for product, states, verify in survivors:
		reasons = [
			f"{r.get('shortLabel') or r['label']}: {r['answer_label']}"
			for r in needed
			if states[r["id"]] == "pass"
		][:3]
		tradeoffs = [
			f"{r.get('shortLabel') or r['label']}: {r['answer_label']} not offered"
			for r in needed
			if r["match_mode"] == "Soft" and states[r["id"]] == "fail"
		]
		matches.append(
			{
				"name": product["name"],
				"score": _score(product, needed, states, verify),
				"reasons": reasons,
				"tradeoffs": tradeoffs,
				"verify": list(dict.fromkeys(v["reason"] for v in verify)),
			}
		)
	titles = {p["name"]: p["title"] for p in products}
	matches.sort(key=lambda m: (-m["score"], titles[m["name"]]))
	for index, item in enumerate(matches):
		item["best"] = index == 0
	worst = max(needed, key=lambda r: excluded[r["id"]], default=None)
	by_name = {p["name"]: p for p in products}
	counts = {
		"match": len(matches),
		"verify": sum(bool(m["verify"]) for m in matches),
		"excluded": len(products) - len(eligible),
		"by_family": dict(Counter(by_name[m["name"]]["family"] for m in matches)),
	}
	return {
		"route": None,
		"family": family,
		"matches": matches[
			: limit if limit is not None else int(definition["settings"].get("results_limit") or 60)
		],
		"companions": companions(matches, answers, available, definition),
		"relaxed": relaxed,
		"counts": counts,
		"no_hard_match": not eligible,
		"eliminated_by": {"question": worst["id"], "answer": worst["answer_label"]}
		if worst and excluded[worst["id"]]
		else None,
		"excluded_by": dict(excluded),
		"definition_version": definition["version"],
		"catalog_stamp": catalog.catalog_stamp(),
	}


def evaluate(answers, question_id, *, definition=None, facts=None, public=False):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import (
		facts as catalog,
	)
	from illumenate_lighting.illumenate_lighting.portal.product_finder import (
		server_definition,
	)

	definition = definition if definition is not None else server_definition.load()
	facts = _available(facts if facts is not None else catalog.load(), public)
	answers = engine.prune(definition, answers)
	question = next((q for q in definition["questions"] if q["id"] == question_id), None)
	if question is None:
		frappe.throw("Unknown question", frappe.ValidationError)
	# Include actual available names and actor: pilot users and public brand scopes cannot share counts.
	digest = hashlib.sha1(
		canonical_json(
			[answers, question_id, definition, public, frappe.session.user, [p["name"] for p in facts]]
		).encode()
	).hexdigest()
	key = f"ill_product_finder:eval:{definition['version']}:{catalog.catalog_stamp()}:{digest}"
	cached = frappe.cache().get_value(key)
	if cached is not None:
		return cached

	def count(candidate):
		candidate = engine.prune(definition, candidate)
		family = engine.family_of(definition, candidate)
		needed = requirements(definition, candidate)
		plain = verify = 0
		excluded = Counter()
		for product in facts:
			if family and product["family"] != family:
				continue
			_states, reasons, failed = inspect_product(product, needed)
			excluded.update(failed)
			if not failed:
				verify += bool(reasons)
				plain += not reasons
		worst = max(needed, key=lambda r: excluded[r["id"]], default=None)
		return {"match": plain, "verify": verify}, (
			worst["label"] if worst and excluded[worst["id"]] else "this product type"
		)

	result = {"options": {}, "disabled": []}
	if question["type"] in ("number", "range"):
		counts, _why = count(answers)
		result.update(match_count=counts["match"], verify_count=counts["verify"])
	else:
		for option in engine.visible_options(question, answers):
			value = option["value"]
			candidate = {**answers, question_id: [value] if question["type"] == "multi" else value}
			counts, why = count(candidate)
			result["options"][value] = counts
			if not sum(counts.values()) and not option.get("no_preference") and not option.get("routes_to"):
				result["disabled"].append({"value": value, "reason": "No products match " + why})
	frappe.cache().set_value(key, result, expires_in_sec=600)
	return result
