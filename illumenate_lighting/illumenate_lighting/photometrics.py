"""Photometry and colorimetry records shared by the product templates.

An ilL-Spec-Photometry record holds one tested build's beam angle, charts and cone of
light; a template links one. An ilL-Spec-Colorimetry record holds one light source's CRI
and TM-30 results; a template lists one per CCT and features one for the product page.

The template fields that predate these records (beam_angle, the chart images and the
Cone of Light table) stay on the templates as copies of the linked records, refreshed on
every template save and whenever a linked record changes. Exports, the portal, spec
sheets and submittal mappings keep reading them by name, so their output does not move.
"""

import frappe

# Templates that carry the Photometrics block, and which of them list colorimetry.
TEMPLATES = (
	"ilL-Fixture-Template",
	"ilL-Tape-Neon-Template",
	"ilL-Extrusion-Kit-Template",
	"ilL-LED-Sheet-Template",
)
COLORIMETRY_TEMPLATES = ("ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template")

PHOTOMETRY = "ilL-Spec-Photometry"
COLORIMETRY = "ilL-Spec-Colorimetry"
# Template field <- photometry field, copied while a photometry record is linked.
MIRRORED = ("beam_angle", "photometric_image", "polar_chart_image")
CONE_TABLE = "photometric_data"
CONE_FIELDS = ("mounting_height", "light_level", "beam_diameter", "display_order")


def cone_rows(rows):
	"""Cone-of-light rows reduced to their values, in display order."""
	rows = [{key: row.get(key) for key in CONE_FIELDS} for row in rows or []]
	return sorted(rows, key=lambda row: row.get("display_order") or 0)


def featured_row(template):
	"""The colorimetry row the product page uses: the one marked featured, else the first."""
	rows = [row for row in template.get("colorimetry") or [] if row.get("colorimetry")]
	return next((row for row in rows if row.get("is_featured")), rows[0] if rows else None)


def _mark_featured(template):
	rows = [row for row in template.get("colorimetry") or [] if row.get("colorimetry")]
	if not rows:
		return None
	seen = set()
	for row in rows:
		if row.colorimetry in seen:
			frappe.throw(f"Colorimetry {row.colorimetry} is listed twice; keep one row per record.")
		seen.add(row.colorimetry)
	featured = [row for row in rows if row.get("is_featured")]
	if len(featured) > 1:
		frappe.throw("Mark one colorimetry row as Featured; the product page shows one TM-30 chart.")
	if not featured:
		rows[0].is_featured = 1
		featured = rows[:1]
	return featured[0]


def apply_to_template(template, method=None):
	"""Copy the linked records onto a template's own fields. Hooked to template validate."""
	meta = frappe.get_meta(template.doctype)
	if meta.has_field("photometry") and template.get("photometry"):
		record = frappe.get_doc(PHOTOMETRY, template.photometry)
		for field in MIRRORED:
			if meta.has_field(field):
				template.set(field, record.get(field))
		if meta.has_field(CONE_TABLE) and cone_rows(template.get(CONE_TABLE)) != cone_rows(
			record.get(CONE_TABLE)
		):
			template.set(CONE_TABLE, [])
			for row in cone_rows(record.get(CONE_TABLE)):
				template.append(CONE_TABLE, row)
	if meta.has_field("colorimetry"):
		row = _mark_featured(template)
		if row and meta.has_field("tm30_chart_image"):
			template.tm30_chart_image = frappe.db.get_value(COLORIMETRY, row.colorimetry, "tm30_chart_image")


def linked_templates(doctype, name):
	"""(template doctype, template name) pairs that link one photometry or colorimetry record."""
	pairs = []
	if doctype == PHOTOMETRY:
		for template in TEMPLATES:
			if frappe.get_meta(template).has_field("photometry"):
				pairs += [
					(template, n)
					for n in frappe.get_all(template, filters={"photometry": name}, pluck="name")
				]
	else:
		parents = frappe.get_all(
			"ilL-Child-Template-Colorimetry",
			filters={"colorimetry": name, "parenttype": ["in", list(COLORIMETRY_TEMPLATES)]},
			fields=["parenttype", "parent"],
			distinct=True,
		)
		pairs = [(row.parenttype, row.parent) for row in parents]
	return sorted(set(pairs))


def refresh_templates(record, method=None):
	"""Re-save the templates that link a changed record so their copies, and their Webflow
	Products, pick up the change. A template that fails its own validation is reported and
	left as it was rather than blocking the record's save."""
	failed = []
	for doctype, name in linked_templates(record.doctype, record.name):
		template = frappe.get_doc(doctype, name)
		try:
			template.flags.ignore_permissions = True
			template.save()
		except Exception:
			frappe.log_error(title=f"{record.doctype} {record.name}: template not refreshed")
			failed.append(name)
	if failed:
		frappe.msgprint(
			"Saved, but these templates could not be refreshed; open and save them to see why: "
			+ ", ".join(failed),
			indicator="orange",
		)
	return failed
