# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import json

import frappe

no_cache = 1


def get_context(context):
	"""Get context for the unified configurator portal page.

	Supports three product categories via ?category= parameter:
	  - Linear Fixture (default) – uses ilL-Fixture-Template
	  - LED Tape – uses ilL-Tape-Neon-Template (product_category='LED Tape')
	  - LED Neon – uses ilL-Tape-Neon-Template (product_category='LED Neon')
	"""
	if frappe.session.user == "Guest":
		frappe.throw("Please login to configure fixtures", frappe.PermissionError)

	# Product category selection (default to Linear Fixture)
	product_category = frappe.form_dict.get("category", "Linear Fixture")
	valid_categories = ["Linear Fixture", "LED Tape", "LED Neon"]
	if product_category not in valid_categories:
		product_category = "Linear Fixture"

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
	context.show_pricing = show_pricing
	context.title = title_map.get(product_category, "Configure Fixture")
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
