"""Owner-bound Finder sessions, validated answers, and one-time public claims."""

import json
from datetime import timedelta
from urllib.parse import urlencode

import frappe
from frappe.utils import get_datetime, now_datetime

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	canonical_json,
	fingerprint,
	finite_number,
	string_list,
)
from illumenate_lighting.illumenate_lighting.portal.product_finder import engine

DOCTYPE = "ilL-Configurator-Session"
DENIED = "This Product Finder session is unavailable. Start a new Product Finder."


def decoded(value):
	return json.loads(value) if isinstance(value, str) else ({} if value is None else value)


def require_user():
	if frappe.session.user == "Guest":
		frappe.throw(DENIED, frappe.PermissionError)


def get_owned(token, *, for_update=False):
	require_user()
	if not isinstance(token, str) or not token or len(token) > 128:
		frappe.throw(DENIED, frappe.PermissionError)
	name = frappe.db.get_value(DOCTYPE, {"session_token": token, "user": frappe.session.user}, "name")
	if not name:
		frappe.throw(DENIED, frappe.PermissionError)
	doc = frappe.get_doc(DOCTYPE, name, for_update=for_update)
	if doc.user != frappe.session.user or doc.status == "Expired":
		frappe.throw(DENIED, frappe.PermissionError)
	return doc


def validate_answers(definition, answers):
	try:
		if isinstance(answers, str) and len(answers.encode()) > 16384:
			raise ValueError("answers must be at most 16 KB")
		answers = decoded(answers)
		if (
			not isinstance(answers, dict)
			or len(answers) > 40
			or len(canonical_json(answers).encode()) > 16384
		):
			raise ValueError("answers must be an object with at most 40 questions and 16 KB")
		questions = {q["id"]: q for q in definition["questions"]}
		for key in answers:
			if key not in questions:
				raise ValueError(f"{key}: unknown or inactive question")
		clean = dict(answers)
		for question in definition["questions"]:
			key = question["id"]
			if not engine.is_visible(question, clean, engine.family_of(definition, clean)):
				clean.pop(key, None)
				continue
			if key not in clean:
				continue
			value, kind = clean[key], question["type"]
			if kind in ("single", "multi", "family"):
				values = string_list(value, field=key) if kind == "multi" else [value]
				valid = {o["value"] for o in engine.visible_options(question, clean)}
				if not all(isinstance(v, str) and v in valid for v in values):
					raise ValueError(f"{key}: select a visible option")
				clean[key] = list(dict.fromkeys(values)) if kind == "multi" else value
			elif kind in ("number", "range"):
				bounds = question.get("number") or question
				if kind == "range" and (not isinstance(value, dict) or set(value) != {"low", "high"}):
					raise ValueError(f"{key}: enter low and high values")
				values = [value["low"], value["high"]] if kind == "range" else [value]
				numbers = [finite_number(v, minimum=bounds.get("min"), field=key) for v in values]
				if bounds.get("max") is not None and max(numbers) > bounds["max"]:
					raise ValueError(f"{key}: exceeds the maximum")
				if kind == "range" and numbers[0] > numbers[1]:
					raise ValueError(f"{key}: low must not exceed high")
				clean[key] = {"low": numbers[0], "high": numbers[1]} if kind == "range" else numbers[0]
			else:
				raise ValueError(f"{key}: this information question takes no answer")
		return engine.prune(definition, clean)
	except (TypeError, ValueError, OverflowError) as exc:
		frappe.throw(str(exc), frappe.ValidationError)


def start(import_answers=None, source="Portal", *, brand=None, guest=False, include_inactive=False):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import server_definition

	if not guest:
		require_user()
	elif source != "Webflow" or frappe.session.user != "Guest":
		frappe.throw(DENIED, frappe.PermissionError)
	definition = server_definition.load(include_inactive=include_inactive)
	answers = validate_answers(definition, import_answers or {})
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"source": source,
			"brand": brand,
			"quiz_answers": canonical_json(answers),
			"definition_version": definition["version"],
			"product_type": engine.family_of(definition, answers)
			if not engine.route(definition, answers)
			else "Mixed",
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.session_token


def save_answers(token, answers, *, include_inactive=False):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import server_definition

	doc = get_owned(token, for_update=True)
	definition = server_definition.load(include_inactive=include_inactive)
	doc.quiz_answers = canonical_json(validate_answers(definition, answers))
	doc.definition_version = definition["version"]
	doc.last_seen = now_datetime()
	doc.result_stamp = None
	doc.status = "Active"
	doc.save(ignore_permissions=True)
	return {"saved": True}


def stamp():
	from illumenate_lighting.illumenate_lighting.portal.product_finder import definition, facts
	from illumenate_lighting.illumenate_lighting.portal.product_finder.matcher import _available

	scope = fingerprint([frappe.session.user, [p["name"] for p in _available(facts.load())]])
	return f"{definition.current_version()}:{facts.catalog_stamp()}:{scope}"


def catalog_url(token, result):
	return "/portal/products?" + urlencode(
		result["query"] if result.get("route") == "catalog" else {"finder": token}
	)


def _complete_doc(doc, *, public=False, facts=None, include_inactive=False):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import matcher, server_definition

	definition = server_definition.load(include_inactive=include_inactive)
	# Prune obsolete content when a previously valid session meets a newer definition.
	answers = engine.prune(definition, decoded(doc.quiz_answers))
	answers = validate_answers(definition, answers)
	result = matcher.match(answers, definition=definition, facts=facts, public=public)
	doc.quiz_answers = canonical_json(answers)
	doc.result_json = canonical_json(result)
	doc.result_stamp = stamp()
	doc.definition_version = definition["version"]
	doc.product_type = result.get("family") or "Mixed"
	doc.status = "Completed"
	doc.completed_on = now_datetime()
	doc.last_seen = now_datetime()
	doc.save(ignore_permissions=True)
	return {**result, "catalog_url": catalog_url(doc.session_token, result)}


def complete(token, *, include_inactive=False):
	return _complete_doc(get_owned(token, for_update=True), include_inactive=include_inactive)


def result(token):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import facts, matcher

	doc = get_owned(token, for_update=True)
	if not doc.result_json or doc.result_stamp != stamp():
		return _complete_doc(doc)
	result = decoded(doc.result_json)
	# Rollout is per request, even when settings changed without modifying a product.
	allowed = {p["name"] for p in matcher._available(facts.load())}
	if any(m["name"] not in allowed for m in result.get("matches", []) + result.get("companions", [])):
		return _complete_doc(doc)
	doc.db_set("last_seen", now_datetime(), update_modified=False)
	return {**result, "catalog_url": catalog_url(token, result)}


def claim(token):
	require_user()
	name = (
		frappe.db.get_value(DOCTYPE, {"session_token": token, "source": "Webflow"}, "name")
		if isinstance(token, str) and len(token) <= 128
		else None
	)
	if not name:
		frappe.throw(DENIED, frappe.PermissionError)
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	if (
		doc.user
		or doc.claimed_on
		or doc.status == "Expired"
		or get_datetime(doc.creation) <= get_datetime(now_datetime()) - timedelta(days=7)
	):
		frappe.throw(DENIED, frappe.PermissionError)
	doc.user = frappe.session.user
	doc.claimed_on = now_datetime()
	doc.last_seen = now_datetime()
	doc.result_stamp = None
	doc.save(ignore_permissions=True)
	computed = _complete_doc(doc)
	return {"token": token, "catalog_url": computed["catalog_url"]}


def mark_used(token):
	if token:
		doc = get_owned(token, for_update=True)
		doc.status = "Used"
		doc.last_seen = now_datetime()
		doc.save(ignore_permissions=True)


def expire_sessions():
	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS

	days = int(frappe.db.get_single_value(SETTINGS, "session_expiry_days") or 30)
	now = get_datetime(now_datetime())
	for row in frappe.get_all(
		DOCTYPE, fields=["name", "user", "source", "status", "creation", "last_seen", "modified"]
	):
		guest = not row.user
		if guest and row.status == "Expired" and get_datetime(row.creation) < now - timedelta(days=37):
			frappe.delete_doc(DOCTYPE, row.name, ignore_permissions=True)
		elif get_datetime(row.creation if guest else (row.last_seen or row.modified)) < now - timedelta(
			days=7 if guest else days
		):
			frappe.db.set_value(DOCTYPE, row.name, "status", "Expired")


def _staff(user):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	return allowed("finder", user) or allowed("sales", user)


def has_permission(doc, user=None, permission_type=None, ptype=None):
	user = user or frappe.session.user
	if user == "Guest":
		return False
	if _staff(user):
		return True
	return (permission_type or ptype or "read") in ("read", "select") and doc.user == user


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if user == "Guest":
		return "1=0"
	if _staff(user):
		return ""
	return f"`tab{DOCTYPE}`.user = {frappe.db.escape(user)}"
