"""Read-only channel preflight. Incomplete authoring drafts remain saveable.

Readiness is evaluated against current linked records, not a cached green flag.
The dependency manifest invalidates approval when a referenced master changes.
"""

import hashlib
import io
import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.product_projection import project_product, safe_document_url
from illumenate_lighting.illumenate_lighting.portal.staff import allowed


def require_catalog_reader():
	if not any(allowed(capability) for capability in ("catalog", "engineering", "integration")):
		frappe.throw("Product authoring staff access required", frappe.PermissionError)


@frappe.whitelist()
def authoring_preview(doctype, name):
	require_catalog_reader()
	from illumenate_lighting.illumenate_lighting.api.authoring_contract import record_issues
	from illumenate_lighting.portal_staff_permissions import authoring_permissions

	if doctype not in authoring_permissions([doctype]) or not doctype.startswith("ilL-"):
		frappe.throw("Choose a supported authoring record")
	doc = frappe.get_doc(doctype, name)
	if not frappe.has_permission(doctype, "read", doc=doc):
		frappe.throw("Authoring record access required", frappe.PermissionError)
	_, issues = dependency_manifest(doc)
	issues.extend(record_issues(doctype, doc.as_dict()))
	return {"issues": issues, "ready": not issues, "affected": affected_products(doctype, name)}


TEMPLATES = {
	"Fixture Template": ("fixture_template", "ilL-Fixture-Template", "allowed_tape_offerings"),
	"LED Tape": ("tape_neon_template", "ilL-Tape-Neon-Template", "allowed_tape_specs"),
	"LED Neon": ("tape_neon_template", "ilL-Tape-Neon-Template", "allowed_tape_specs"),
	"LED Sheet": ("led_sheet_template", "ilL-LED-Sheet-Template", "allowed_specs"),
	"Driver": ("driver_template", "ilL-Driver-Template", "variants"),
	"Controller": ("controller_template", "ilL-Controller-Template", "variants"),
}
SKIP_LINKS = {
	"webflow_product",
	"target_brands",
	"sync_targets",
	"webflow_sync_targets",
	"compatible_products",
}
VOLATILE = {
	"modified",
	"modified_by",
	"owner",
	"creation",
	"sync_targets",
	"webflow_sync_targets",
	"sync_status",
	"sync_error_message",
	"last_synced_at",
	"webflow_item_id",
	"webflow_collection_slug",
	"_comments",
	"_assign",
	"_liked_by",
	"_user_tags",
}


def content_record(value):
	if isinstance(value, dict):
		return {key: content_record(item) for key, item in value.items() if key not in VOLATILE}
	if isinstance(value, list):
		return [content_record(item) for item in value]
	return value


def dependency_manifest(root):
	"""Bounded traversal of declared product/master links and child-row links."""
	seen, records, issues = set(), [], []

	def visit(doc, depth):
		key = (doc.doctype, doc.name)
		if key in seen:
			return
		seen.add(key)
		if len(seen) > 400 or depth > 8:
			issues.append(
				{
					"record": doc.name,
					"field": "dependencies",
					"message": "Dependency graph exceeds preflight bounds",
				}
			)
			return
		data = json.loads(frappe.as_json(doc.as_dict()))
		records.append({"doctype": doc.doctype, "name": doc.name, "hash": fingerprint(content_record(data))})
		if doc.get("disabled") or (doc.meta.has_field("is_active") and not doc.get("is_active")):
			issues.append(
				{"record": doc.name, "field": "is_active", "message": "Referenced record is inactive"}
			)
		walk(doc, doc.meta, depth)
		# Eligibility and compatibility maps point at templates/specs, so an
		# outbound-only Link traversal would miss safety-critical dependencies.
		for doctype, filters in related_dependencies(doc):
			rows = frappe.get_all(doctype, filters=filters, pluck="name", limit_page_length=201)
			if len(rows) > 200:
				issues.append(
					{
						"record": doc.name,
						"field": "dependencies",
						"message": f"Review more than 200 {doctype} associations",
					}
				)
			for name in rows[:200]:
				visit(frappe.get_doc(doctype, name), depth + 1)

	def walk(row, meta, depth):
		for field in meta.fields:
			link_type = row.get(field.options) if field.fieldtype == "Dynamic Link" else field.options
			if field.fieldname in SKIP_LINKS or not row.get(field.fieldname):
				continue
			if field.fieldtype == "Table":
				for child in row.get(field.fieldname):
					# Disabled choices are not offered or required by this product.
					child_meta = frappe.get_meta(field.options)
					if child_meta.has_field("is_active") and not child.get("is_active"):
						continue
					walk(child, child_meta, depth)
			elif field.fieldtype in ("Attach", "Attach Image") and str(row.get(field.fieldname)).startswith(
				("/files/", "/private/files/")
			):
				file_name = frappe.db.get_value("File", {"file_url": row.get(field.fieldname)}, "name")
				if not file_name:
					issues.append(
						{"record": row.name, "field": field.fieldname, "message": "Attached file is missing"}
					)
				elif ("File", file_name) not in seen:
					seen.add(("File", file_name))
					file = frappe.get_doc("File", file_name)
					if int(file.file_size or 0) > 20 * 1024 * 1024:
						issues.append(
							{
								"record": row.name,
								"field": field.fieldname,
								"message": "Publication files must be at most 20 MiB",
							}
						)
					else:
						content = file.get_content()
						records.append(
							{
								"doctype": "File",
								"name": file_name,
								"hash": hashlib.sha256(content).hexdigest(),
							}
						)
			elif field.fieldtype in ("Link", "Dynamic Link") and (
				link_type == "Item"
				or (link_type or "").startswith(
					(
						"ilL-Spec-",
						"ilL-Attribute-",
						"ilL-Rel-",
						"ilL-Fixture-Template",
						"ilL-Tape-Neon-Template",
						"ilL-LED-Sheet-Template",
						"ilL-Driver-Template",
						"ilL-Controller-Template",
					)
				)
			):
				name = row.get(field.fieldname)
				if frappe.db.exists(link_type, name):
					visit(frappe.get_doc(link_type, name), depth + 1)
				else:
					issues.append(
						{
							"record": row.name,
							"field": field.fieldname,
							"message": f"Missing {link_type}: {name}",
						}
					)

	visit(root, 0)
	return sorted(records, key=lambda row: (row["doctype"], row["name"])), issues


def related_dependencies(doc):
	if doc.doctype in ("ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template"):
		yield (
			"ilL-Rel-Driver-Eligibility",
			{"template_type": doc.doctype, "fixture_template": doc.name, "is_active": 1, "is_allowed": 1},
		)
	if doc.doctype == "ilL-Fixture-Template":
		for doctype in ("ilL-Rel-Endcap-Map", "ilL-Rel-Mounting-Accessory-Map"):
			yield doctype, {"fixture_template": doc.name, "is_active": 1}
	if doc.doctype == "ilL-Spec-LED Tape":
		yield "ilL-Rel-Leader-Cable-Map", {"tape_spec": doc.name, "is_active": 1}
	if doc.doctype == "ilL-Spec-Profile":
		yield "ilL-Rel-Profile Lens", {"profile_spec": doc.name, "is_active": 1}
	if doc.doctype == "ilL-Attribute-Finish":
		yield "ilL-Rel-Finish Endcap Color", {"finish": doc.name, "is_active": 1}


def evaluate(product, channel="cms"):
	if channel not in ("cms", "portal", "configure", "pdf"):
		raise ValueError("Unknown product channel")
	if isinstance(product, str):
		product = frappe.get_doc("ilL-Webflow-Product", product)
	projection = project_product(product.as_dict())
	dependencies, issues = dependency_manifest(product)

	def issue(record, field, message):
		issues.append({"record": record, "field": field, "message": message})

	for field in ("product_name", "product_slug", "product_type"):
		if not product.get(field):
			issue(product.name, field, "Required for this channel")
	for error in projection["validation_errors"]:
		issue(product.name, error["field"], "Correct invalid configurator choice JSON")
	if channel in ("cms", "portal"):
		for field in ("featured_image", "short_description"):
			if not product.get(field):
				issue(product.name, field, "Add product imagery and description before publication")
		for row in product.get("documents") or []:
			if not safe_document_url(row.document_file):
				issue(product.name, "documents", "Public literature must use a public file or HTTPS URL")
		if product.featured_image and not safe_document_url(product.featured_image):
			issue(product.name, "featured_image", "Use an approved public image")
	template_info = TEMPLATES.get(product.product_type)
	if template_info and (product.is_configurable or channel in ("configure", "pdf")):
		field, doctype, choices = template_info
		if not product.get(field) or not frappe.db.exists(doctype, product.get(field)):
			issue(product.name, field, "Select the matching family template")
		else:
			template = frappe.get_doc(doctype, product.get(field))
			if not any(
				row.get("is_active") if "is_active" in row.as_dict() else True
				for row in template.get(choices) or []
			):
				issue(template.name, choices, "Add at least one active compatible specification")
			if (
				product.product_type in ("LED Tape", "LED Neon")
				and template.product_category != product.product_type
			):
				issue(template.name, "product_category", "Template family does not match product")
			if channel == "pdf" or (product.is_configurable and channel in ("cms", "portal")):
				_pdf_preflight(template, dependencies, issue)
			if product.is_configurable or channel in ("configure", "pdf"):
				from illumenate_lighting.illumenate_lighting.api.authoring_contract import record_issues

				for dependency in dependencies:
					if dependency["doctype"].startswith("ilL-"):
						master = frappe.get_doc(dependency["doctype"], dependency["name"])
						issues.extend(record_issues(master.doctype, master.as_dict()))
				if template.doctype == "ilL-Fixture-Template":
					from illumenate_lighting.illumenate_lighting.api.guardrail_audits import _audit_template

					coverage = _audit_template(template.name)
					for key in (
						"missing_endcap_maps",
						"missing_mounting_maps",
						"missing_leader_maps",
						"missing_tape_offerings",
						"ambiguous_mappings",
					):
						if coverage[key]:
							issue(
								template.name,
								key,
								"Resolve compatibility coverage: " + json.dumps(coverage[key], default=str),
							)
				_electrical_preflight(template, dependencies, issue)
	if channel in ("portal", "configure") and not template_info and product.get("portal_item"):
		from illumenate_lighting.illumenate_lighting.portal.standard_products import choices

		if not choices(product):
			issue(product.name, "portal_item", "Choose an enabled sales Item with a stock UOM")
	return {
		"product": product.name,
		"channel": channel,
		"ready": not issues,
		"issues": issues,
		"dependencies": dependencies,
		"revision_hash": fingerprint({"version": 1, "dependencies": dependencies}),
		"projection": projection,
	}


def _electrical_preflight(template, dependencies, issue):
	from illumenate_lighting.illumenate_lighting.api.driver_catalog import candidates
	from illumenate_lighting.illumenate_lighting.api.led_sheet_bundle import feed_limit

	if template.doctype not in ("ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template"):
		return
	for dependency in dependencies:
		if dependency["doctype"] not in ("ilL-Spec-LED Tape", "ilL-Spec-LED-Sheet"):
			continue
		spec = frappe.get_doc(dependency["doctype"], dependency["name"])
		try:
			drivers, _ = candidates(template.doctype, template.name, spec.input_voltage, spec.input_protocol)
			if not drivers:
				raise ValueError("Add active compatible driver eligibility for included-power configurations")
			if spec.doctype == "ilL-Spec-LED-Sheet":
				watts = float(
					spec.total_sheet_watts
					or float(spec.watts_per_sqft or 0)
					* float(spec.sheet_width_ft or 0)
					* float(spec.sheet_height_ft or 0)
				)
				feed_limit(watts, drivers, spec.max_panels_per_feed)
		except (ValueError, frappe.ValidationError) as exc:
			issue(spec.name, "driver_eligibility", str(exc))


def _pdf_preflight(template, dependencies, issue):
	from pypdf import PdfReader

	file_name = (
		frappe.db.get_value("File", {"file_url": template.spec_submittal_template}, "name")
		if template.spec_submittal_template
		else None
	)
	if not file_name:
		issue(template.name, "spec_submittal_template", "Attach a fillable PDF template")
		return
	try:
		content = frappe.get_doc("File", file_name).get_content()
		reader = PdfReader(io.BytesIO(content), strict=True)
		if reader.is_encrypted or not reader.get_fields():
			raise ValueError("Template must be unencrypted and contain form fields")
		dependencies.append(
			{"doctype": "File", "name": file_name, "hash": hashlib.sha256(content).hexdigest()}
		)
		from illumenate_lighting.illumenate_lighting.portal.pdf_mapping import check_mappings

		registry = {
			"ilL-Fixture-Template": ("ilL-Spec-Submittal-Mapping", "fixture_template"),
			"ilL-Tape-Neon-Template": ("ilL-Neon-Submittal-Mapping", "tape_neon_template"),
			"ilL-LED-Sheet-Template": ("ilL-LED-Sheet-Submittal-Mapping", "led_sheet_template"),
			"ilL-Driver-Template": ("ilL-Driver-Submittal-Mapping", "driver_template"),
			"ilL-Controller-Template": ("ilL-Controller-Submittal-Mapping", "controller_template"),
		}
		doctype, field = registry[template.doctype]
		mappings = frappe.get_all(doctype, filters={field: template.name}, fields=["*"])
		for message in check_mappings(mappings, reader.get_fields()):
			issue(template.name, "field_mappings", message)
		for mapping in mappings:
			dependencies.append(
				{"doctype": doctype, "name": mapping.name, "hash": fingerprint(content_record(mapping))}
			)
			if not str(mapping.source_field or "").startswith("__") and not frappe.get_meta(
				mapping.source_doctype
			).has_field(mapping.source_field):
				issue(mapping.name, "source_field", "Source field is absent from the installed schema")
	except Exception as exc:
		issue(template.name, "spec_submittal_template", str(exc))


@frappe.whitelist()
def preview(product, channel="cms"):
	require_catalog_reader()
	return evaluate(product, channel)


@frappe.whitelist()
def affected_products(doctype, name, after=None, limit=25):
	"""Bounded dependency impact report, also covering maps reached in reverse."""
	require_catalog_reader()
	limit = max(1, min(int(limit), 50))
	rows = frappe.get_all(
		"ilL-Webflow-Product",
		filters={"name": [">", after]} if after else {},
		pluck="name",
		order_by="name asc",
		limit_page_length=limit + 1,
	)
	result = []
	for product in rows[:limit]:
		dependencies, issues = dependency_manifest(frappe.get_doc("ilL-Webflow-Product", product))
		if any(row["doctype"] == doctype and row["name"] == name for row in dependencies):
			result.append(
				{"product": product, "dependency_hash": fingerprint(dependencies), "issues": issues}
			)
	return {"products": result, "next_cursor": rows[limit - 1] if len(rows) > limit else None}
