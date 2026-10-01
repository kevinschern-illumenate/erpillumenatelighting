"""Authenticated Product Finder transport. All mutations require POST and CSRF."""

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from illumenate_lighting.illumenate_lighting.portal.product_finder import definition, sessions


def require_access(preview=0):
	from illumenate_lighting.illumenate_lighting.portal.access import require_catalog_access
	from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS
	from illumenate_lighting.illumenate_lighting.portal.product_finder.desk import can_edit_content

	sessions.require_user()
	require_catalog_access()
	preview = bool(cint(preview) and can_edit_content())
	if not frappe.db.get_single_value(SETTINGS, "portal_enabled") and not preview:
		frappe.throw(
			"The Product Finder is not enabled yet. Please browse the catalog.", frappe.PermissionError
		)
	return preview


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_definition(preview=0):
	return definition.load_definition(include_inactive=require_access(preview))


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def start(import_answers=None, preview=0):
	preview = require_access(preview)
	return {"token": sessions.start(import_answers, include_inactive=preview)}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_session(token, preview=0):
	require_access(preview)
	doc = sessions.get_owned(token)
	return {
		"answers": sessions.decoded(doc.quiz_answers),
		"status": doc.status,
		"stale": doc.definition_version != definition.current_version()
		or (bool(doc.result_json) and doc.result_stamp != sessions.stamp()),
		"definition_version": doc.definition_version,
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60)
def save_answers(token, answers, preview=0):
	preview = require_access(preview)
	return sessions.save_answers(token, answers, include_inactive=preview)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=120, seconds=60)
def evaluate(answers, question_id, preview=0):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import matcher, server_definition

	preview = require_access(preview)
	data = server_definition.load(include_inactive=preview)
	return matcher.evaluate(sessions.validate_answers(data, answers), question_id, definition=data)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60)
def complete(token, preview=0):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import facts

	preview = require_access(preview)
	result = sessions.complete(token, include_inactive=preview)
	products = {p["name"]: p for p in facts.load()}
	result["top"] = [
		{**m, **{k: products[m["name"]][k] for k in ("title", "image", "slug", "family")}}
		for m in result["matches"][:3]
	]
	return result


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def claim(token, preview=0):
	require_access(preview)
	return sessions.claim(token)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def dismiss_banner(preview=0):
	require_access(preview)
	frappe.defaults.set_user_default("ill_finder_banner_dismissed", str(definition.current_version()))
	return {"dismissed": True}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def request_verification(token, product_slug=None, schedule=None, line_key=None, message=None, preview=0):
	from illumenate_lighting.illumenate_lighting.portal.product_finder import verification

	require_access(preview)
	return {"request": verification.request(token, product_slug, schedule, line_key, message)}
