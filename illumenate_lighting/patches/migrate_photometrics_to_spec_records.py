"""Move template photometrics into ilL-Spec-Photometry / ilL-Spec-Colorimetry records (2026-10-28).

Each template with a beam angle, chart images or cone-of-light rows, and no photometry
link yet, gets its own photometry record holding those values. Each template with a
TM-30 chart and no colorimetry rows gets a colorimetry record holding the chart, as its
featured row. The template's own fields keep their values: they now mirror the records.

Links are written straight to the database so no save hooks run; the values are the
template's own, so no Webflow payload or publication approval changes. Records that need
a person (no LED package or CCT, or identical beam angles that could share one record)
are listed in an Error Log titled "Photometry migration review".
"""

import frappe

from illumenate_lighting.illumenate_lighting.photometrics import (
	COLORIMETRY,
	COLORIMETRY_TEMPLATES,
	CONE_TABLE,
	MIRRORED,
	PHOTOMETRY,
	TEMPLATES,
	cone_rows,
)

SUFFIX = {
	"ilL-Fixture-Template": "FX",
	"ilL-Tape-Neon-Template": "TN",
	"ilL-Extrusion-Kit-Template": "KT",
	"ilL-LED-Sheet-Template": "LS",
}


def execute():
	review = []
	for doctype in TEMPLATES:
		meta = frappe.get_meta(doctype)
		if not meta.has_field("photometry"):
			continue
		for name in frappe.get_all(doctype, pluck="name", order_by="name asc"):
			template = frappe.get_doc(doctype, name)
			review += migrate_photometry(template, meta)
			if doctype in COLORIMETRY_TEMPLATES:
				review += migrate_colorimetry(template, meta)
	review += shared_beam_angles()
	if review:
		frappe.log_error(title="Photometry migration review", message="\n".join(review))


def free_code(doctype, code, template):
	"""The template code, or the code with a template-type suffix when another type took it."""
	if not frappe.db.exists(doctype, code):
		return code
	return f"{code}-{SUFFIX[template.doctype]}"


def migrate_photometry(template, meta):
	if template.get("photometry"):
		return []
	values = {field: template.get(field) for field in MIRRORED if meta.has_field(field)}
	rows = cone_rows(template.get(CONE_TABLE)) if meta.has_field(CONE_TABLE) else []
	if not any(values.values()) and not rows:
		return []
	code = free_code(PHOTOMETRY, template.name, template)
	if frappe.db.exists(PHOTOMETRY, code):
		return [f"{template.doctype} {template.name}: photometry code {code} already taken; link it by hand"]
	record = frappe.get_doc(
		{
			"doctype": PHOTOMETRY,
			"photometry_code": code,
			"title": template.get("template_name") or template.name,
			"is_active": 1,
			**values,
			CONE_TABLE: rows,
			"notes": f"Moved from {template.doctype} {template.name} on 2026-10-28.",
		}
	)
	record.flags.ignore_permissions = True
	record.flags.ignore_links = True
	# Inserting fires on_update, which re-saves linked templates; none links it yet.
	record.insert()
	frappe.db.set_value(template.doctype, template.name, "photometry", record.name, update_modified=False)
	return []


def single(values):
	values = {value for value in values if value}
	return values.pop() if len(values) == 1 else None


def tape_source(template):
	"""(LED package, CCT) when a Tape/Neon template's allowed specs resolve to one of each."""
	if template.doctype != "ilL-Tape-Neon-Template":
		return None, None
	specs = [row.tape_spec for row in template.get("allowed_tape_specs") or [] if row.get("tape_spec")]
	if not specs:
		return None, None
	packages = frappe.get_all("ilL-Spec-LED Tape", filters={"name": ["in", specs]}, pluck="led_package")
	ccts = frappe.get_all(
		"ilL-Rel-Tape Offering", filters={"tape_spec": ["in", specs], "is_active": 1}, pluck="cct"
	)
	return single(packages), single(ccts)


def migrate_colorimetry(template, meta):
	chart = template.get("tm30_chart_image") if meta.has_field("tm30_chart_image") else None
	if not chart or template.get("colorimetry"):
		return []
	code = free_code(COLORIMETRY, template.name, template)
	if frappe.db.exists(COLORIMETRY, code):
		return [f"{template.doctype} {template.name}: colorimetry code {code} already taken; link it by hand"]
	package, cct = tape_source(template)
	record = frappe.get_doc(
		{
			"doctype": COLORIMETRY,
			"colorimetry_code": code,
			"title": template.get("template_name") or template.name,
			"is_active": 1,
			"led_package": package,
			"cct": cct,
			"tm30_chart_image": chart,
			"notes": f"TM-30 chart moved from {template.doctype} {template.name} on 2026-10-28.",
		}
	)
	record.flags.ignore_permissions = True
	record.flags.ignore_links = True
	record.insert()
	frappe.get_doc(
		{
			"doctype": "ilL-Child-Template-Colorimetry",
			"parent": template.name,
			"parenttype": template.doctype,
			"parentfield": "colorimetry",
			"idx": 1,
			"colorimetry": record.name,
			"cct": cct,
			"is_featured": 1,
		}
	).db_insert()
	if package and cct:
		return []
	return [f"{COLORIMETRY} {record.name}: set the LED package and CCT, then add the other CCTs' results"]


def shared_beam_angles():
	"""Photometry records that hold only the same beam angle and could be merged."""
	records = frappe.get_all(
		PHOTOMETRY,
		filters={"beam_angle": [">", 0]},
		fields=["name", "beam_angle", "photometric_image", "polar_chart_image"],
	)
	groups = {}
	for record in records:
		if not record.photometric_image and not record.polar_chart_image:
			groups.setdefault(record.beam_angle, []).append(record.name)
	return [
		f"Beam angle {angle:g}° only, on {len(names)} records ({', '.join(sorted(names))}); "
		"link the templates to one record if they share a build"
		for angle, names in sorted(groups.items())
		if len(names) > 1
	]
