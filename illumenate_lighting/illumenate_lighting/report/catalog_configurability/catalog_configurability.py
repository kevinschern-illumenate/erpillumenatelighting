# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Why each catalog product does or does not open its configurator on the portal."""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES, parse_bool
from illumenate_lighting.illumenate_lighting.api.product_projection import (
	TEMPLATE_DOCTYPES,
	TEMPLATE_FIELDS,
	project_product,
)

OPTION = "ilL-Child-Webflow-Configurator-Option"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Product"),
			"fieldname": "product",
			"fieldtype": "Link",
			"options": "ilL-Webflow-Product",
			"width": 200,
		},
		{"label": _("Product Name"), "fieldname": "product_name", "fieldtype": "Data", "width": 220},
		{"label": _("Family"), "fieldname": "family", "fieldtype": "Data", "width": 120},
		{"label": _("Template Type"), "fieldname": "template_doctype", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("Template"),
			"fieldname": "template",
			"fieldtype": "Dynamic Link",
			"options": "template_doctype",
			"width": 160,
		},
		{"label": _("Template Active"), "fieldname": "template_active", "fieldtype": "Check", "width": 110},
		{"label": _("Is Configurable"), "fieldname": "is_configurable", "fieldtype": "Check", "width": 110},
		{"label": _("Capability"), "fieldname": "capability", "fieldtype": "Data", "width": 110},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 160},
		{"label": _("How to fix"), "fieldname": "fix", "fieldtype": "Data", "width": 420},
	]


def get_data(filters):
	from illumenate_lighting.illumenate_lighting.api.product_catalog import (
		_is_template_active,
		_template_activity,
	)
	from illumenate_lighting.illumenate_lighting.portal.catalog_repair import template_backlinks
	from illumenate_lighting.illumenate_lighting.portal.rollout import reason as rollout_reason

	product_types = [
		product_type for product_type, family in FAMILY_ALIASES.items() if family in TEMPLATE_FIELDS
	]
	conditions = {"product_type": ["in", product_types]}
	if filters.get("product_type"):
		conditions["product_type"] = filters.product_type
	if not parse_bool(filters.get("include_inactive")):
		conditions["is_active"] = 1
	fields = ["name", "product_name", "product_slug", "product_type", "is_active", "is_configurable"]
	products = frappe.get_all(
		"ilL-Webflow-Product",
		filters=conditions,
		fields=[*fields, *sorted(set(TEMPLATE_FIELDS.values()))],
		order_by="product_type asc, product_name asc",
	)
	if not products:
		return []

	options: dict = {}
	for row in frappe.get_all(
		OPTION,
		filters={"parenttype": "ilL-Webflow-Product", "parent": ["in", [p.name for p in products]]},
		fields=["parent", "option_step", "allowed_values_json"],
		ignore_permissions=True,
	):
		options.setdefault(row.parent, []).append(row)
	activity = _template_activity(products)
	backlinks = template_backlinks()

	data = []
	only_problems = parse_bool(filters.get("only_problems"), default=True)
	for product in products:
		family = FAMILY_ALIASES.get(product.product_type, product.product_type)
		# The family gate as dealers see it; the pilot cohort is per user and is ignored here.
		gate = rollout_reason(product.product_type, public=True)
		projection = project_product(
			{**product, "configurator_options": options.get(product.name, [])},
			configure_available=gate == "ok",
			rollout_reason=gate,
			template_active=_is_template_active(product, activity),
		)
		if only_problems and projection["capability"] == "configure":
			continue
		template = product.get(TEMPLATE_FIELDS[family])
		data.append(
			{
				"product": product.name,
				"product_name": product.product_name,
				"family": family,
				"template_doctype": TEMPLATE_DOCTYPES[family],
				"template": template,
				"template_active": 1 if template and _is_template_active(product, activity) else 0,
				"is_configurable": 1 if parse_bool(product.is_configurable) else 0,
				"capability": projection["capability"],
				"reason": projection["capability_reason"],
				"fix": how_to_fix(projection["capability_reason"], product, family, backlinks),
			}
		)
	return data


def how_to_fix(reason, product, family, backlinks) -> str:
	"""Plain-language next step for a capability reason."""
	doctype = TEMPLATE_DOCTYPES.get(family, "template")
	pointing = [
		name
		for linked, name, active, _category in backlinks.get(product.name, [])
		if linked == doctype and active
	]
	repairable = _(" Use Apply repair to link {0}.").format(pointing[0]) if len(pointing) == 1 else ""
	if reason == "ok":
		return ""
	if reason == "inactive":
		return _("The product is inactive.")
	if reason == "not_configurable":
		return _("Tick Is Configurable on the product.") + (
			_(" Apply repair can do this.") if pointing else ""
		)
	if reason == "missing_template":
		return _("Link an active {0} on the product.").format(doctype) + repairable
	if reason == "inactive_template":
		return _("Activate template {0}, or link an active {1}.").format(
			product.get(TEMPLATE_FIELDS[family]), doctype
		)
	if reason.startswith("invalid_options:"):
		step = reason.split(":", 1)[1]
		return _(
			"Configurator option step {0} has unreadable allowed values. Re-save the product to regenerate its options."
		).format(step)
	if reason == "family_not_enabled":
		return _("Add {0} to the ill_portal_enabled_families site config, or remove that key.").format(family)
	return _("Check the product and its template.")
