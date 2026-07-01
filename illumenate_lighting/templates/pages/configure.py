# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.utils import quote

no_cache = 1


def get_context(context):
	"""Get context for the unified configurator portal page.

	Supports three product categories via ?category= parameter:
	  - Linear Fixture (default) – uses ilL-Fixture-Template
	  - LED Tape – uses ilL-Tape-Neon-Template (product_category='LED Tape')
	  - LED Neon – uses ilL-Tape-Neon-Template (product_category='LED Neon')
	"""
	if frappe.session.user == "Guest":
		current_url = frappe.utils.get_url(frappe.request.path)
		qs = frappe.request.query_string
		if qs:
			current_url += f"?{qs.decode('utf-8') if isinstance(qs, bytes) else qs}"
		frappe.local.flags.redirect_location = f"/login?redirect-to={quote(current_url, safe='')}"
		raise frappe.Redirect

	allowed_roles = {"Dealer", "System Manager", "Administrator"}
	if not (set(frappe.get_roles(frappe.session.user)) & allowed_roles):
		frappe.local.flags.redirect_location = "/portal/request-dealer-access"
		raise frappe.Redirect

	quiz_handoff = {
		"template": frappe.form_dict.get("template"),
		"moisture": frappe.form_dict.get("moisture"),
		"ip_rating": frappe.form_dict.get("ip_rating"),
		"light_type": frappe.form_dict.get("light_type"),
		"cct": frappe.form_dict.get("cct"),
		"cct_low": frappe.form_dict.get("cct_low"),
		"cct_high": frappe.form_dict.get("cct_high"),
		"cri": frappe.form_dict.get("cri"),
		"dimming": frappe.form_dict.get("dimming"),
		"mounting": frappe.form_dict.get("mounting"),
		"lens": frappe.form_dict.get("lens"),
		"finish": frappe.form_dict.get("finish"),
		"lumen_class": frappe.form_dict.get("lumen_class"),
	}
	quiz_handoff = {k: v for k, v in quiz_handoff.items() if v is not None}

	# Product category selection (default to Linear Fixture)
	product_category = frappe.form_dict.get("category", "Linear Fixture")
	valid_categories = ["Linear Fixture", "LED Tape", "LED Neon"]
	if product_category not in valid_categories:
		product_category = "Linear Fixture"

	# Configurator UI mode: "coordinator" (default, multi-segment/tape-neon
	# builder) or "wizard" (guided step-by-step flow, Linear Fixture only,
	# reusing templates/includes/configurator_fixture_form.html + fixture_steps.js).
	configurator_mode = frappe.form_dict.get("mode", "coordinator")
	if configurator_mode not in ("coordinator", "wizard"):
		configurator_mode = "coordinator"
	if product_category != "Linear Fixture":
		configurator_mode = "coordinator"

	# Get optional schedule context (pre-fill from fixture schedule line UI)
	schedule_name = frappe.form_dict.get("schedule")
	line_idx = frappe.form_dict.get("line_idx")
	template_code = frappe.form_dict.get("template")

	schedule = None
	can_save = False
	project_name = None

	if schedule_name:
		if frappe.db.exists("ilL-Project-Fixture-Schedule", schedule_name):
			schedule = frappe.get_doc("ilL-Project-Fixture-Schedule", schedule_name)

			# Check permission
			from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
				has_permission,
			)

			if has_permission(schedule, "write", frappe.session.user):
				can_save = True

			# Get the project name for pre-filling the selector
			project_name = schedule.ill_project

	# Fetch templates based on product category
	templates = []
	if product_category == "Linear Fixture":
		templates = _get_linear_fixture_templates()
	else:
		templates = _get_tape_neon_templates(product_category)

	# Determine if pricing should be shown based on user role
	show_pricing = True

	# Check if user is a System Manager (for build item button)
	is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)

	# Map category to page title
	title_map = {
		"Linear Fixture": "Configure Fixture",
		"LED Tape": "Configure LED Tape",
		"LED Neon": "Configure LED Neon",
	}

	# For tape/neon, track whether templates exist.  When none are available
	# the front-end will fall back to spec-derived options automatically.
	has_templates = bool(templates)

	context.product_category = product_category
	context.is_tape_neon = product_category in ("LED Tape", "LED Neon")
	context.is_neon = product_category == "LED Neon"
	context.is_tape = product_category == "LED Tape"
	context.has_templates = has_templates
	context.schedule = schedule
	context.schedule_name = schedule_name or ""
	context.project_name = project_name or ""
	context.line_idx = int(line_idx) if line_idx is not None else None
	context.can_save = can_save
	context.is_system_manager = is_system_manager
	context.templates = templates
	context.selected_template = template_code
	context.configurator_mode = configurator_mode
	context.product_slug = frappe.form_dict.get("product_slug", "")
	context.show_pricing = show_pricing
	context.title = title_map.get(product_category, "Configure Fixture")
	context.quiz_handoff_json = frappe.as_json(quiz_handoff)
	context.has_quiz_handoff = bool(quiz_handoff)
	context.no_cache = 1

	return context


def _get_linear_fixture_templates():
	"""Fetch active ilL-Fixture-Template records with gallery images from Webflow."""
	templates = frappe.get_all(
		"ilL-Fixture-Template",
		filters={"is_active": 1},
		fields=["template_code", "template_name", "webflow_product"],
		order_by="template_name asc",
		ignore_permissions=True,
	)

	# Batch-fetch gallery images from linked Webflow products
	webflow_product_names = [t.webflow_product for t in templates if t.webflow_product]
	webflow_product_gallery = _fetch_webflow_gallery(webflow_product_names)

	# Attach gallery JSON to each template
	for t in templates:
		gallery = webflow_product_gallery.get(t.webflow_product, []) if t.webflow_product else []
		t.image = gallery[0]["image"] if gallery else None
		t.gallery_json = json.dumps(gallery) if gallery else "[]"

	return templates


def _get_tape_neon_templates(product_category):
	"""Fetch active ilL-Tape-Neon-Template records for the given product category."""
	templates = frappe.get_all(
		"ilL-Tape-Neon-Template",
		filters={"is_active": 1, "product_category": product_category},
		fields=["template_code", "template_name", "webflow_product", "image", "description"],
		order_by="template_name asc",
		ignore_permissions=True,
	)

	# Batch-fetch gallery images from linked Webflow products
	webflow_product_names = [t.webflow_product for t in templates if t.webflow_product]
	webflow_product_gallery = _fetch_webflow_gallery(webflow_product_names)

	# Attach gallery JSON to each template
	for t in templates:
		gallery = webflow_product_gallery.get(t.webflow_product, []) if t.webflow_product else []
		# If no Webflow gallery but has a direct image, use that
		if not gallery and t.image:
			gallery = [{"image": t.image, "alt_text": t.template_name or ""}]
		t.image = gallery[0]["image"] if gallery else t.image
		t.gallery_json = json.dumps(gallery) if gallery else "[]"

	return templates


def _fetch_webflow_gallery(webflow_product_names):
	"""Fetch gallery images from Webflow product records."""
	if not webflow_product_names:
		return {}

	webflow_product_gallery = {}

	# Fetch gallery images from child table ordered by idx
	gallery_rows = frappe.get_all(
		"ilL-Child-Webflow-Gallery-Image",
		filters={"parent": ["in", webflow_product_names], "parenttype": "ilL-Webflow-Product"},
		fields=["parent", "image", "alt_text", "display_order", "idx"],
		order_by="parent, idx asc",
		ignore_permissions=True,
	)
	for row in gallery_rows:
		if row.image:
			webflow_product_gallery.setdefault(row.parent, []).append(
				{"image": row.image, "alt_text": row.alt_text or ""}
			)

	# Fallback: also fetch featured_image for products with no gallery
	webflow_products = frappe.get_all(
		"ilL-Webflow-Product",
		filters={"name": ["in", webflow_product_names]},
		fields=["name", "featured_image"],
		ignore_permissions=True,
	)
	for wp in webflow_products:
		if wp.name not in webflow_product_gallery and wp.featured_image:
			webflow_product_gallery[wp.name] = [
				{"image": wp.featured_image, "alt_text": ""}
			]

	return webflow_product_gallery


@frappe.whitelist()
def get_configurator_markup(product_category="Linear Fixture", product_slug=None, selected_template=None):
	"""Render the reusable scoped-class configurator partial for embedding
	outside the portal page (e.g. the desk Quotation / Sales Order dialog).

	The markup is wired to the IllConfigurator.Fixture / IllConfigurator.TapeNeon
	classes:
	  - Linear Fixture -> templates/includes/configurator_fixture_form.html
	  - LED Tape / LED Neon -> templates/includes/configurator_tape_neon_form.html

	The caller mounts the returned HTML inside a host element carrying
	`.ill-configurator.ill-configurator-fixture` (fixtures) or
	`.ill-configurator.ill-configurator-tape-neon` (tape/neon) and instantiates
	the matching class against that root element.
	"""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to configure fixtures", frappe.PermissionError)

	valid_categories = ["Linear Fixture", "LED Tape", "LED Neon"]
	if product_category not in valid_categories:
		product_category = "Linear Fixture"

	if product_category == "Linear Fixture":
		templates = _get_linear_fixture_templates()
		context = {
			"templates": templates,
			"selected_template": selected_template,
			"product_slug": product_slug or "",
			"can_save": True,
			"show_pricing": True,
		}
		return frappe.render_template(
			"illumenate_lighting/templates/includes/configurator_fixture_form.html", context
		)

	title_map = {
		"LED Tape": "Configure LED Tape",
		"LED Neon": "Configure LED Neon",
	}
	context = {
		"is_neon": product_category == "LED Neon",
		"title": title_map.get(product_category, "Configure"),
		"templates": _get_tape_neon_templates(product_category),
	}
	return frappe.render_template(
		"illumenate_lighting/templates/includes/configurator_tape_neon_form.html", context
	)
