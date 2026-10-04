# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""What staff still need to map before the Product Finder can match every product."""

import frappe
from frappe import _
from frappe.utils import cint

from illumenate_lighting.illumenate_lighting.portal.product_finder.content import QUESTION
from illumenate_lighting.illumenate_lighting.portal.product_finder.facets import FACETS, needs_value_maps

ATTRIBUTE_LINK = "ilL-Child-Webflow-Attribute-Link"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_data()
	if filters.get("question"):
		rows = [row for row in rows if row["question"] == filters.question]
	if filters.get("issue"):
		rows = [row for row in rows if row["issue"] == filters.issue]
	return get_columns(), rows


def get_columns():
	return [
		{"label": _("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 210},
		{
			"label": _("Question"),
			"fieldname": "question",
			"fieldtype": "Link",
			"options": QUESTION,
			"width": 170,
		},
		{"label": _("Product Fact"), "fieldname": "facet", "fieldtype": "Data", "width": 150},
		{"label": _("ERP Type"), "fieldname": "erp_doctype", "fieldtype": "Data", "hidden": 1},
		{
			"label": _("ERP Value"),
			"fieldname": "erp_value",
			"fieldtype": "Dynamic Link",
			"options": "erp_doctype",
			"width": 180,
		},
		{"label": _("Products"), "fieldname": "products", "fieldtype": "Int", "width": 90},
		{"label": _("Detail"), "fieldname": "detail", "fieldtype": "Data", "width": 420},
	]


def get_data() -> list:
	questions = frappe.get_all(
		QUESTION, fields=["name", "label", "is_active", "facet", "match_mode"], order_by="sequence asc"
	)
	active = {row.name for row in questions if cint(row.is_active)}
	names = [row.name for row in questions]
	options, maps, conditions = {}, {}, {}
	if names:
		scope = {"parenttype": QUESTION, "parent": ["in", names]}
		for row in frappe.get_all(
			"ilL-Child-Finder-Option",
			filters=scope,
			fields=["parent", "value", "label", "is_active", "is_no_preference"],
		):
			options.setdefault(row.parent, []).append(row)
		for row in frappe.get_all(
			"ilL-Child-Finder-Value-Map",
			filters=scope,
			fields=["parent", "option_value", "attribute_doctype", "attribute_value"],
		):
			maps.setdefault(row.parent, []).append(row)
		for row in frappe.get_all(
			"ilL-Child-Finder-Condition", filters=scope, fields=["parent", "depends_on_question"]
		):
			conditions.setdefault(row.parent, []).append(row)
	usage = attribute_usage()

	data = []
	reachable: dict = {}
	for question in questions:
		if question.name not in active:
			continue
		facet = question.facet
		for condition in conditions.get(question.name, []):
			if condition.depends_on_question not in active:
				data.append(
					issue_row(
						"Condition on inactive question",
						question,
						None,
						None,
						None,
						_(
							"Depends on '{0}', which is inactive or missing, so this question is never shown as intended."
						).format(condition.depends_on_question),
					)
				)
		if not facet or question.match_mode == "None" or not needs_value_maps(facet):
			continue
		mapped = {m.option_value for m in maps.get(question.name, [])}
		for m in maps.get(question.name, []):
			reachable.setdefault(facet, set()).add((m.attribute_doctype, m.attribute_value))
		for option in options.get(question.name, []):
			if cint(option.is_active) and not cint(option.is_no_preference) and option.value not in mapped:
				data.append(
					issue_row(
						"Answer not mapped",
						question,
						None,
						None,
						None,
						_(
							"'{0}' has no ERP value, so choosing it matches no product data and every product needs verification."
						).format(option.label or option.value),
					)
				)

	for facet, spec in FACETS.items():
		if not needs_value_maps(facet) or not any(q.facet == facet and q.name in active for q in questions):
			continue
		for doctype in spec["doctypes"]:
			for value, count in sorted(usage.get(doctype, {}).items()):
				if (doctype, value) not in reachable.get(facet, set()):
					data.append(
						issue_row(
							"ERP value not reachable",
							None,
							facet,
							doctype,
							value,
							_("Active products use this {0}, but no answer maps to it.").format(
								spec["label"].lower()
							),
							products=count,
						)
					)

	if any(q.facet in ("light_type", "color_mode") and q.name in active for q in questions):
		missing = frappe.get_all(
			"ilL-Attribute-LED Package", filters={"spectrum_type": ["is", "not set"]}, pluck="name"
		)
		for name in missing:
			count = usage.get("ilL-Attribute-LED Package", {}).get(name, 0)
			if count:
				data.append(
					issue_row(
						"LED package without spectrum type",
						None,
						"light_type",
						"ilL-Attribute-LED Package",
						name,
						_("Set Spectrum Type so the Finder can tell which light type these products are."),
						products=count,
					)
				)
	return data


def attribute_usage() -> dict:
	"""``{attribute DocType: {record: active products using it}}`` from product attribute links."""
	usage: dict = {}
	for item in frappe.db.sql(
		f"""
		SELECT al.attribute_doctype, al.attribute_name, COUNT(DISTINCT al.parent) AS products
		FROM `tab{ATTRIBUTE_LINK}` al
		INNER JOIN `tabilL-Webflow-Product` p ON p.name = al.parent AND al.parenttype = 'ilL-Webflow-Product'
		WHERE p.is_active = 1 AND al.attribute_doctype IS NOT NULL AND al.attribute_name IS NOT NULL
		GROUP BY al.attribute_doctype, al.attribute_name
		""",
		as_dict=True,
	):
		usage.setdefault(item.attribute_doctype, {})[item.attribute_name] = item.products
	return usage


def issue_row(issue, question, facet, doctype, value, detail, products=None) -> dict:
	return {
		"issue": issue,
		"question": question.name if question else None,
		"facet": (FACETS.get(facet or (question.facet if question else None)) or {}).get("label"),
		"erp_doctype": doctype,
		"erp_value": value,
		"products": products,
		"detail": detail,
	}
