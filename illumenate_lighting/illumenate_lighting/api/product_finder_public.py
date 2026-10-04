"""Public live-data quiz. Explicit projections never expose prices, stock, or Items."""

import copy
from urllib.parse import quote, urlsplit

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.portal.product_finder import (
	definition,
	facts,
	matcher,
	server_definition,
	sessions,
)
from illumenate_lighting.illumenate_lighting.portal.product_finder.content import SETTINGS


def require_brand(brand):
	from illumenate_lighting.illumenate_lighting.api.webflow_brand import resolve_brand

	settings = frappe.get_cached_doc(SETTINGS)
	if (
		not settings.public_enabled
		or not brand
		or brand not in {r.brand for r in settings.public_brands or []}
	):
		frappe.throw("This public Product Finder is unavailable", frappe.PermissionError)
	try:
		config = resolve_brand(brand)
	except frappe.ValidationError:
		frappe.throw("This public Product Finder is unavailable", frappe.PermissionError)
	return config


def absolute_image(path):
	if not path:
		return None
	parts = urlsplit(path)
	if parts.scheme and parts.scheme != "https":
		return None
	if path.startswith("//") or path.startswith("/private/"):
		return None
	return frappe.utils.get_url(path)


def published(brand):
	products = facts.load()
	names = [p["name"] for p in products]
	if not names:
		return [], {}
	scope = {"parenttype": "ilL-Webflow-Product", "parent": ["in", names], "brand": brand}
	enabled = set(
		frappe.get_all("ilL-Child-Webflow-Brand-Target", filters={**scope, "enabled": 1}, pluck="parent")
	)
	rows = frappe.get_all(
		"ilL-Child-Webflow-Sync-State",
		filters={**scope, "sync_status": "Synced"},
		fields=["parent", "webflow_collection_slug"],
	)
	collections = {
		r.parent: r.webflow_collection_slug for r in rows if r.webflow_collection_slug and r.parent in enabled
	}
	return [
		p for p in products if p["name"] in collections and p["capability"] in ("configure", "quantity")
	], collections


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_definition(brand):
	require_brand(brand)
	result = copy.deepcopy(definition.load_definition())
	for question in result["questions"]:
		for option in question.get("options", []):
			option["image"] = absolute_image(option.get("image"))
	result["settings"]["banner_image"] = absolute_image(result["settings"].get("banner_image"))
	return result


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def evaluate(brand, answers, question_id):
	require_brand(brand)
	if not isinstance(answers, str) or len(answers.encode()) > 4096:
		frappe.throw("Answers must be JSON of at most 4 KB", frappe.ValidationError)
	data = server_definition.load()
	products, _collections = published(brand)
	return matcher.evaluate(
		sessions.validate_answers(data, answers), question_id, definition=data, facts=products, public=True
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def complete(brand, answers):
	config = require_brand(brand)
	if frappe.session.user != "Guest":
		frappe.throw("Use the public quiz without portal credentials", frappe.PermissionError)
	# get_base_url() is the ERP asset host; product links must use webflow_site_url.
	base = (config.get("webflow_site_url") or "").rstrip("/")
	if urlsplit(base).scheme != "https" or not urlsplit(base).netloc:
		frappe.throw("The public product website is not configured", frappe.ValidationError)
	products, collections = published(brand)
	token = sessions.start(answers, source="Webflow", brand=brand, guest=True)
	name = frappe.db.get_value(sessions.DOCTYPE, {"session_token": token}, "name")
	doc = frappe.get_doc(sessions.DOCTYPE, name)
	result = sessions._complete_doc(doc, public=True, facts=products)
	by_name = {p["name"]: p for p in products}
	matches = []
	for match in result["matches"]:
		product = by_name[match["name"]]
		matches.append(
			{
				"title": product["title"],
				"image": absolute_image(product["image"]),
				"url": base
				+ "/"
				+ quote(collections[product["name"]].strip("/"), safe="/")
				+ "/"
				+ quote(product["slug"], safe=""),
				"family": product["family"],
				"reasons": match["reasons"],
				"verify": match["verify"],
			}
		)
	return {
		"token": token,
		"claim_url": frappe.utils.get_url("/portal/product-finder?claim=" + quote(token, safe="")),
		"matches": matches,
		"counts": result["counts"],
		"relaxed": result["relaxed"],
		"route": result["route"],
		"no_hard_match": result.get("no_hard_match", False),
		"eliminated_by": result.get("eliminated_by"),
		**({"catalog_url": result["catalog_url"]} if result["route"] else {}),
	}
