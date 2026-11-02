"""Template-owned spec rows and configurator steps (plan Phase 2, D10, D21, D25, D43, D58).

The calculations that build a Webflow Product's specification rows and configurator steps
live on ilL-Webflow-Product (``sync_custom_template_data`` and the
``populate_*_configurator_options`` methods). They only read the linked template, so the
template runs the very same code on a *shadow* product: an unsaved ilL-Webflow-Product that
points at the template being saved. The results are stored on the template:

- ``specifications``: the calculated rows plus any rows typed on the template by hand (rows
  whose label is not one of the calculated labels are kept, D43);
- ``part_no_configurator``: the configurator steps.

A linked product still runs its own calculations on save (they also fill its documents,
certifications, kit components and attribute links), so its calculated rows are always fresh.
From the template it takes what people decide there: hand-typed specification rows and each
configurator step's "Is Required" (``apply_template_rows``). Spec sheets generated from a
template calculate fresh too (``compute``).

Sharing the code means a product's rows are the same as before, apart from the D43 rules,
which apply everywhere: placeholder "TBD" rows and a 0 to 0 temperature range are left out.
``compare_listing`` checks that on real data.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	CONFIGURATOR_FIELD,
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)

PRODUCT = "ilL-Webflow-Product"
TAPE = "ilL-Tape-Neon-Template"
SPEC_FIELDS = ("spec_label", "spec_value", "display_order", "attribute_doctype", "attribute_options_json")
CONFIGURATOR_FIELDS = (
	"option_step",
	"option_type",
	"option_label",
	"option_description",
	"is_required",
	"depends_on_step",
	"allowed_values_json",
)
POPULATE = {
	"fixture_template": "populate_configurator_options",
	"tape_neon_template": "populate_tape_neon_configurator_options",
	"led_sheet_template": "populate_led_sheet_configurator_options",
	"driver_template": "populate_driver_configurator_options",
	"controller_template": "populate_controller_configurator_options",
	"kit_template": "populate_extrusion_kit_configurator_options",
}


def _rows(rows, fields):
	return [{field: row.get(field) for field in fields} for row in rows or []]


def product_type_for(template):
	"""The Webflow Product type a template is listed as (Tape/Neon: its tape family)."""
	field = WEBFLOW_PRODUCT_LINKS[template.doctype]
	if template.doctype == TAPE:
		return template.get("product_category") or WEBFLOW_PRODUCT_LINK_TYPES[field][0]
	return WEBFLOW_PRODUCT_LINK_TYPES[field][0]


def shadow_product(template):
	"""An unsaved Webflow Product that points at ``template`` and reads its unsaved values."""
	field = WEBFLOW_PRODUCT_LINKS[template.doctype]
	product = frappe.new_doc(PRODUCT)
	product.name = template.get("webflow_product") or f"template:{template.name}"
	product.product_name = template.get("template_name") or template.name
	product.product_type = product_type_for(template)
	product.set(field, template.name)
	product.is_configurable = 1
	product.flags.template_doc = template
	# Hand-typed template rows go in first so the calculation keeps them (it only replaces
	# rows with calculated labels).
	product.set("webflow_specifications", _rows(template.get("specifications"), SPEC_FIELDS))
	existing = _rows(template.get(CONFIGURATOR_FIELD), CONFIGURATOR_FIELDS)
	if not existing and template.get("webflow_product"):
		# First computation: carry "Is Required" choices made on the product.
		existing = frappe.get_all(
			"ilL-Child-Webflow-Configurator-Option",
			filters={"parenttype": PRODUCT, "parent": template.webflow_product},
			fields=["option_step", "is_required"],
		)
	product.flags.existing_is_required = {
		int(row["option_step"]): int(row["is_required"] or 0)
		for row in existing
		if row.get("option_step") is not None
	}
	return product, field


def compute(template):
	"""Run the product calculations for ``template``. Returns (specifications, configurator)."""
	product, field = shadow_product(template)
	product.sync_custom_template_data()
	getattr(product, POPULATE[field])()
	return (
		_rows(product.get("webflow_specifications"), SPEC_FIELDS),
		_rows(product.get("configurator_options"), CONFIGURATOR_FIELDS),
	)


def refresh_template(template):
	"""Fill the template's specifications and configurator. Call from the template's validate().

	A calculation error never blocks the template save: the previous rows are kept and the
	user is told.
	"""
	if template.flags.skip_listing_refresh:
		return
	try:
		specifications, configurator = compute(template)
	except Exception as error:
		frappe.log_error(title=f"Template listing refresh failed: {template.name}")
		frappe.msgprint(
			_("Specifications and configurator steps were not recalculated: {0}").format(error),
			indicator="orange",
			alert=True,
		)
		return
	template.set("specifications", specifications)
	template.set(CONFIGURATOR_FIELD, configurator)


def push_to_product(template):
	"""Save the linked product so it takes the template's rows (D21). Call from on_update().

	Never blocks the template save: a product that cannot be saved is reported.
	"""
	product = template.get("webflow_product")
	if not product or template.flags.skip_listing_push or not frappe.db.exists(PRODUCT, product):
		return
	field = WEBFLOW_PRODUCT_LINKS[template.doctype]
	if frappe.db.get_value(PRODUCT, product, field) != template.name:
		return
	frappe.db.savepoint("template_listing_push")
	try:
		doc = frappe.get_doc(PRODUCT, product)
		doc.flags.from_template_mirror = True
		doc.save(ignore_permissions=True)
	except Exception as error:
		frappe.db.rollback(save_point="template_listing_push")
		frappe.log_error(title=f"Template listing push failed: {template.name} -> {product}")
		frappe.msgprint(
			_("Webflow Product {0} was not updated from this template: {1}").format(product, error),
			indicator="orange",
			alert=True,
		)


def _linked_template(product):
	for doctype, field in WEBFLOW_PRODUCT_LINKS.items():
		name = product.get(field)
		if name and frappe.db.get_value(doctype, name, "webflow_product") == product.name:
			return frappe.get_doc(doctype, name)
	return None


def apply_template_rows(product):
	"""Product side: merge in what the linked template owns. Call at the end of before_save.

	The product has just run the same calculations the template runs, on fresh data, so its
	calculated rows are kept as they are (stored template rows can be older: a tape spec or
	attribute record may have changed since the template was last saved). From the template
	it takes what people decide there:

	- specification rows typed on the template (labels that are not calculated);
	- the "Is Required" choice of each configurator step.

	Rows typed on the product by hand are kept too.
	"""
	template = _linked_template(product)
	if not template:
		return
	calculated = set(_calculated_labels())
	template_manual = [
		row
		for row in _rows(template.get("specifications"), SPEC_FIELDS)
		if row["spec_label"] not in calculated
	]
	if template_manual:
		labels = {row["spec_label"] for row in template_manual}
		kept = [
			row
			for row in _rows(product.get("webflow_specifications"), SPEC_FIELDS)
			if row["spec_label"] not in labels
		]
		rows = sorted(
			kept + template_manual,
			key=lambda row: int(row["display_order"]) if row.get("display_order") not in (None, "") else 999,
		)
		product.set("webflow_specifications", rows)
	required = {
		row["option_step"]: row["is_required"]
		for row in _rows(template.get(CONFIGURATOR_FIELD), CONFIGURATOR_FIELDS)
		if row.get("option_step") is not None
	}
	if required:
		for row in product.get("configurator_options") or []:
			if row.get("option_step") in required:
				row.is_required = required[row.get("option_step")]


def _calculated_labels():
	"""The labels the product calculation rebuilds."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_webflow_product.ill_webflow_product import (
		MANAGED_LABELS,
	)

	return MANAGED_LABELS


# ---------------------------------------------------------------- staging checks


def _spec_map(rows):
	return {row.get("spec_label"): row.get("spec_value") for row in rows or []}


def diff_listing(current_specs, new_specs, current_configurator, new_configurator):
	"""Pure: how the template's rows differ from what the product holds today.

	Differences the D43 rules cause (a "TBD" value, a 0 to 0 temperature range) are listed
	separately as expected.
	"""
	current, new = _spec_map(current_specs), _spec_map(new_specs)
	expected, unexpected = [], []
	for label in sorted(set(current) | set(new), key=str):
		if current.get(label) == new.get(label):
			continue
		row = {"label": label, "product": current.get(label), "template": new.get(label)}
		value = str(current.get(label) or "")
		if label not in new and (
			value.strip().upper() == "TBD" or value.startswith("32°F (0°C) to 32°F (0°C)")
		):
			expected.append(row)
		else:
			unexpected.append(row)
	steps_now = {row.get("option_step"): row for row in _rows(current_configurator, CONFIGURATOR_FIELDS)}
	steps_new = {row.get("option_step"): row for row in _rows(new_configurator, CONFIGURATOR_FIELDS)}
	configurator = [
		{"step": step, "product": steps_now.get(step), "template": steps_new.get(step)}
		for step in sorted(set(steps_now) | set(steps_new), key=lambda s: (s is None, s))
		if steps_now.get(step) != steps_new.get(step)
	]
	return {"expected": expected, "unexpected": unexpected, "configurator": configurator}


@frappe.whitelist(methods=["POST"])
def compare_listing(template_doctype=None, template_id=None, limit=0):
	"""Compare what each linked template would store with what its product holds today.

	Read-only, System Manager only. Without arguments every linked template is checked.
	``unexpected`` and ``configurator`` should be empty; ``expected`` lists the D43 rows.
	"""
	frappe.only_for("System Manager")
	targets = []
	for doctype in [template_doctype] if template_doctype else TEMPLATE_DOCTYPES:
		filters = {"webflow_product": ["is", "set"]}
		if template_id:
			filters["name"] = template_id
		targets += [(doctype, name) for name in frappe.get_all(doctype, filters=filters, pluck="name")]
	if limit:
		targets = targets[: int(limit)]
	report = []
	for doctype, name in targets:
		template = frappe.get_doc(doctype, name)
		product = frappe.get_doc(PRODUCT, template.webflow_product)
		entry = {"template": (doctype, name), "product": product.name}
		try:
			specs, configurator = compute(template)
		except Exception as error:
			entry["error"] = str(error)
			report.append(entry)
			continue
		configurator_now = product.get("configurator_options") if product.get("is_configurable") else []
		entry.update(
			diff_listing(
				product.get("webflow_specifications"),
				specs,
				configurator_now,
				configurator if product.get("is_configurable") else [],
			)
		)
		report.append(entry)
	return {
		"checked": len(report),
		"with_unexpected_differences": [
			r for r in report if r.get("unexpected") or r.get("configurator") or r.get("error")
		],
		"expected_only": sum(
			1
			for r in report
			if r.get("expected") and not (r.get("unexpected") or r.get("configurator") or r.get("error"))
		),
	}


@frappe.whitelist(methods=["POST"])
def refresh_all_templates(apply=False, push=False):
	"""Store specifications and configurator steps on every template. Dry run by default.

	``apply`` saves each template (its rows are recalculated on save). ``push`` also saves
	the linked products so they take the rows; without it products update on their next save.
	System Manager only.
	"""
	frappe.only_for("System Manager")
	apply = frappe.parse_json(apply) if isinstance(apply, str) else bool(apply)
	push = frappe.parse_json(push) if isinstance(push, str) else bool(push)
	result = {"applied": apply, "pushed": push, "templates": 0, "failed": []}
	for doctype in TEMPLATE_DOCTYPES:
		for name in frappe.get_all(doctype, pluck="name"):
			result["templates"] += 1
			if not apply:
				continue
			frappe.db.savepoint("refresh_template")
			try:
				doc = frappe.get_doc(doctype, name)
				doc.flags.skip_listing_push = not push
				doc.flags.ignore_permissions = True
				doc.save()
			except Exception as error:
				frappe.db.rollback(save_point="refresh_template")
				result["failed"].append({"template": (doctype, name), "error": str(error)})
	if apply:
		frappe.db.commit()
	return result
