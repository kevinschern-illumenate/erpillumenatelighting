# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Options every linear fixture and extrusion kit offers, and the data each option needs.

Custom finish (CU, "Provide RAL #") and Outdoor (O) are standard on every linear
fixture and extrusion kit (spec sheet plan, decision 13). Offering an option is not
enough: the configurators refuse a finish without a profile variant and an endcap
colour (fixtures) or a kit profile map (kits). This module reports both gaps; it
never blocks publishing.

System Console:

	print(frappe.call("illumenate_lighting.illumenate_lighting.api.standard_options.report"))
"""

import frappe

FIXTURE = "ilL-Fixture-Template"
KIT = "ilL-Extrusion-Kit-Template"

# (option_type, allowed-option field, master DocType, master code, label)
CUSTOM_FINISH = ("Finish", "finish", "ilL-Attribute-Finish", "CU", "Custom finish (CU, Provide RAL #)")
OUTDOOR = ("Environment Rating", "environment_rating", "ilL-Attribute-Environment Rating", "O", "Outdoor (O)")
STANDARD_OPTIONS = {
	FIXTURE: (CUSTOM_FINISH, OUTDOOR),
	# Kits have no environment option yet; Outdoor needs a kit option type and part number segment.
	KIT: (CUSTOM_FINISH,),
}


def active_values(rows, option_type, field):
	return [
		row.get(field)
		for row in rows or []
		if row.get("option_type") == option_type and row.get(field) and row.get("is_active", 1)
	]


def missing_standard_options(doctype, rows, code_of):
	"""Labels of the standard options missing from ``rows`` (a template's ``allowed_options``).

	``code_of(master_doctype, name)`` returns a master record's code; options are matched
	by code because names differ between sites ("Custom" vs "Custom RAL").
	"""
	missing = []
	for option_type, field, master, code, label in STANDARD_OPTIONS.get(doctype, ()):
		codes = {(code_of(master, value) or "").upper() for value in active_values(rows, option_type, field)}
		if code not in codes:
			missing.append(label)
	return missing


def _code(master, name):
	return frappe.db.get_value(master, name, "code")


def fixture_finish_gaps(template):
	"""Allowed finishes the fixture configurator would refuse, with the reason."""
	family = template.get("default_profile_family") or template.get("template_code") or template.get("name")
	gaps = []
	for finish in active_values(template.get("allowed_options"), "Finish", "finish"):
		variant = _code("ilL-Attribute-Finish", finish) or finish
		if not frappe.get_all(
			"ilL-Spec-Profile",
			filters={"family": family, "variant_code": variant, "is_active": 1},
			pluck="name",
			limit=1,
		):
			gaps.append({"finish": finish, "missing": f"ilL-Spec-Profile family {family} variant {variant}"})
		if not frappe.db.get_value("ilL-Rel-Finish Endcap Color", {"finish": finish, "is_active": 1}, "name"):
			gaps.append({"finish": finish, "missing": "ilL-Rel-Finish Endcap Color"})
	return gaps


def kit_finish_gaps(template):
	"""Allowed kit finishes without an active ilL-Rel-Kit-Profile-Map."""
	return [
		{"finish": finish, "missing": "ilL-Rel-Kit-Profile-Map"}
		for finish in active_values(template.get("allowed_options"), "Finish", "finish")
		if not frappe.db.get_value(
			"ilL-Rel-Kit-Profile-Map",
			{"kit_template": template.get("name"), "finish": finish, "is_active": 1},
			"name",
		)
	]


def audit(doctype, template):
	missing = missing_standard_options(doctype, template.get("allowed_options"), _code)
	gaps = fixture_finish_gaps(template) if doctype == FIXTURE else kit_finish_gaps(template)
	return {"missing_standard_options": missing, "finish_gaps": gaps}


@frappe.whitelist()
def report():
	"""Standard option coverage for every active linear fixture and extrusion kit template."""
	frappe.only_for(("System Manager", "ilL Catalog Publisher", "ilL Engineering"))
	templates = []
	for doctype in (FIXTURE, KIT):
		for name in frappe.get_all(doctype, filters={"is_active": 1}, pluck="name", order_by="name asc"):
			result = audit(doctype, frappe.get_doc(doctype, name).as_dict())
			if result["missing_standard_options"] or result["finish_gaps"]:
				templates.append({"doctype": doctype, "name": name, **result})
	return {"templates_with_gaps": len(templates), "templates": templates}
