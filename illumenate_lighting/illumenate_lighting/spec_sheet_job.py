"""Generate a spec sheet from a template (plan Phase 3, 4.5, 4.13).

The Generate Spec button on the six templates calls ``generate_spec_sheet``. It checks
permission (D28), queues a background job and returns a job id; the form shows a blocking
dialog and polls ``spec_sheet_job_status``. The job continues if the page is closed.

The job posts ``{template_doctype, template_id, brand}`` to the n8n spec webhook (site config
``n8n_spec_webhook_url``, with the shared-secret header). n8n reads ``get_spec_sheet_data``,
renders the PDF, uploads it through ``upload_spec_pdf`` and attaches it to the template's
Spec Sheet field (so the File records who it is attached to), then answers
``{success, file_url}``. The job then calls ``register_spec_sheet``: it checks the template
points at that file, sets the stable link (``spec_sheet_route``), unattaches the older spec
sheet files (they stay in File Manager) and saves the linked Webflow Product so its Spec Sheet row uses the link.

Nothing here talks to Webflow. Syncing stays with the Webflow sync (Phase 5 decides when).
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.web_listing_schema import TEMPLATE_DOCTYPES

STATUS_KEY = "spec_sheet_job:{0}"
STATUS_TTL = 6 * 60 * 60
TIMEOUT = 300


def _status_key(job_id):
	return STATUS_KEY.format(job_id)


def _set_status(job_id, **values):
	current = frappe.cache().get_value(_status_key(job_id)) or {}
	current.update(values)
	frappe.cache().set_value(_status_key(job_id), current, expires_in_sec=STATUS_TTL)
	return current


def _brand(template, brand=None):
	from illumenate_lighting.illumenate_lighting.spec_sheet_data import _brand as resolve

	return resolve(template, brand)


@frappe.whitelist(methods=["POST"])
def generate_spec_sheet(template_doctype, template_id, brand=None):
	"""Queue spec sheet generation for a saved template. Returns ``{job_id}``."""
	from illumenate_lighting.illumenate_lighting.template_link import require_template_access

	if template_doctype not in TEMPLATE_DOCTYPES:
		frappe.throw(_("{0} is not a product template.").format(template_doctype))
	require_template_access(template_doctype, template_id)
	template = frappe.get_doc(template_doctype, template_id)
	brand = _brand(template, brand)
	# What the spec sheet needs (owner, 2026-11-03): stop and list what is missing.
	from illumenate_lighting.illumenate_lighting.spec_sheet_check import check

	readiness = check(template)
	if readiness["missing"]:
		frappe.throw(
			_("Fill these in before generating the spec sheet:")
			+ "<ul>"
			+ "".join(f"<li>{frappe.utils.escape_html(item)}</li>" for item in readiness["missing"])
			+ "</ul>",
			title=_("Spec sheet not ready"),
		)
	# Fail now, not in the background, when the site is not set up for n8n.
	from illumenate_lighting.illumenate_lighting.api import n8n_config

	n8n_config.spec_webhook_url()
	n8n_config.auth_headers()
	job_id = frappe.generate_hash(length=16)
	_set_status(
		job_id,
		status="Queued",
		template_doctype=template_doctype,
		template_id=template_id,
		brand=brand,
		user=frappe.session.user,
	)
	frappe.enqueue(
		"illumenate_lighting.illumenate_lighting.spec_sheet_job.run",
		queue="long",
		timeout=TIMEOUT + 60,
		job_id=f"spec_sheet_{job_id}",
		spec_job=job_id,
		template_doctype=template_doctype,
		template_id=template_id,
		brand=brand,
	)
	return {"job_id": job_id, "warnings": readiness["warnings"]}


@frappe.whitelist()
def spec_sheet_job_status(job_id):
	"""The job's status for the dialog: Queued, Running, Done or Failed, with a message."""
	status = frappe.cache().get_value(_status_key(job_id))
	if not status:
		return {"status": "Unknown"}
	if status.get("user") not in (frappe.session.user, None) and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	return {key: status.get(key) for key in ("status", "message", "file_url")}


def call_n8n(template_doctype, template_id, brand):
	"""Post to the spec webhook and return its JSON answer (raises on failure)."""
	import requests

	from illumenate_lighting.illumenate_lighting.api import n8n_config

	response = requests.post(
		n8n_config.spec_webhook_url(),
		json={"template_doctype": template_doctype, "template_id": template_id, "brand": brand},
		headers={"Content-Type": "application/json", **n8n_config.auth_headers()},
		timeout=TIMEOUT,
	)
	response.raise_for_status()
	return response.json()


def run(spec_job, template_doctype, template_id, brand):
	"""Background job."""
	_set_status(spec_job, status="Running", message=_("Generating the spec sheet..."))
	try:
		answer = call_n8n(template_doctype, template_id, brand)
		if not answer.get("success") or not answer.get("file_url"):
			raise ValueError(answer.get("error") or answer.get("message") or _("n8n did not return a file."))
		register_spec_sheet(template_doctype, template_id, answer["file_url"])
	except Exception as error:
		frappe.log_error(title=f"Spec sheet generation failed: {template_doctype} {template_id}")
		_set_status(spec_job, status="Failed", message=str(error))
		return
	_set_status(spec_job, status="Done", message=_("Spec sheet generated."), file_url=answer["file_url"])


def register_spec_sheet(template_doctype, template_id, file_url):
	"""After n8n has uploaded and attached the PDF: check the template points at it.

	n8n attaches the file to the template's Spec Sheet field (that is what fills the File's
	attached-to fields). If the template does not point at the file, it is set here without
	running the template's hooks. Phase 4 adds the stable URL and removes older files.
	"""
	from illumenate_lighting.illumenate_lighting import spec_sheet_route

	current = frappe.db.get_value(template_doctype, template_id, "spec_sheet")
	if current != file_url:
		if not frappe.db.exists("File", {"file_url": file_url}):
			raise ValueError(_("The spec sheet file {0} was not found.").format(file_url))
		frappe.db.set_value(template_doctype, template_id, "spec_sheet", file_url)
	# The stable link (Phase 4): the same for every regeneration, for the template's brand.
	brand = spec_sheet_route.template_brand(template_doctype, template_id)
	frappe.db.set_value(
		template_doctype,
		template_id,
		"spec_sheet_public_url",
		spec_sheet_route.public_url(template_id, brand),
	)
	frappe.db.commit()
	try:
		spec_sheet_route.detach_older(template_doctype, template_id)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Spec sheet file cleanup failed: {template_doctype} {template_id}")
	# The Webflow Product's Spec Sheet document row is built from the stable link.
	from illumenate_lighting.illumenate_lighting.template_listing import push_to_product

	template = frappe.get_doc(template_doctype, template_id)
	push_to_product(template)
	try:
		spec_sheet_route.attach_to_product(template, file_url)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"Spec sheet not attached to product: {template_doctype} {template_id}")
	frappe.db.commit()
	return file_url


# ---------------------------------------------------------------- bulk regeneration (Phase 4)

BULK_KEY = "spec_sheet_bulk:{0}"
BULK_TTL = 24 * 60 * 60
DEFAULT_STATUSES = ("Active + Live",)


def plan_regeneration(statuses=DEFAULT_STATUSES, names=None, doctypes=None):
	"""Templates to regenerate: (to_generate, skipped). Each entry names the template, its brand
	and the stable link it will get. Templates without a Target Brand are skipped."""
	from illumenate_lighting.illumenate_lighting.spec_sheet_route import public_url, template_brand

	to_generate, skipped = [], []
	for doctype in TEMPLATE_DOCTYPES:
		if doctypes and doctype not in doctypes:
			continue
		filters = {"product_status": ["in", list(statuses)]}
		if names:
			filters["name"] = ["in", list(names)]
		for row in frappe.get_all(
			doctype, filters=filters, fields=["name", "webflow_product", "spec_sheet"], order_by="name asc"
		):
			brand = template_brand(doctype, row.name)
			entry = {"template": (doctype, row.name), "product": row.webflow_product, "brand": brand}
			if not brand:
				skipped.append({**entry, "reason": "no Target Brand"})
				continue
			from illumenate_lighting.illumenate_lighting.spec_sheet_check import check, page_slug

			template = frappe.get_doc(doctype, row.name)
			readiness = check(template)
			entry["webflow_page"] = page_slug(template)
			if readiness["missing"]:
				skipped.append({**entry, "reason": "missing: " + "; ".join(readiness["missing"])})
				continue
			entry["public_url"] = public_url(row.name, brand)
			entry["current_file"] = row.spec_sheet
			entry["warnings"] = readiness["warnings"]
			to_generate.append(entry)
	return to_generate, skipped


@frappe.whitelist(methods=["POST"])
def regenerate_spec_sheets(apply=False, statuses=None, templates=None, doctypes=None):
	"""Regenerate spec sheets in bulk so every template gets the new file name and stable link.

	Dry run by default: lists what would be generated (Active + Live templates unless
	``statuses``, ``templates`` or ``doctypes`` say otherwise, for example
	``doctypes="ilL-Extrusion-Kit-Template"``) and what is skipped. With ``apply`` one
	background job generates them one after another (so n8n and Vercel get one at a time)
	and ``spec_sheet_bulk_status`` reports progress. System Manager only.

	Each generation is the same as the Generate Spec button: it sets Spec Sheet and the stable
	link, unattaches older files and saves the linked Webflow Product (its Spec Sheet document
	row becomes the stable link; Webflow gets it on the product's next sync).
	"""
	frappe.only_for("System Manager")
	apply = frappe.parse_json(apply) if isinstance(apply, str) else bool(apply)
	statuses = frappe.parse_json(statuses) if isinstance(statuses, str) else statuses
	templates = frappe.parse_json(templates) if isinstance(templates, str) else templates
	doctypes = (
		frappe.parse_json(doctypes) if isinstance(doctypes, str) and doctypes.startswith("[") else doctypes
	)
	if isinstance(doctypes, str):
		doctypes = [doctypes]
	to_generate, skipped = plan_regeneration(statuses or DEFAULT_STATUSES, templates, doctypes)
	pages = {}
	for entry in to_generate:
		key = f"{entry['brand']}: /spec-sheet-templates/{entry['webflow_page']}"
		pages[key] = pages.get(key, 0) + 1
	result = {
		"applied": apply,
		"to_generate": len(to_generate),
		"skipped": skipped,
		# Each must exist on that brand's Webflow site, or the workflow stops at Fetch Webflow Template.
		"webflow_pages_needed": pages,
		"templates": to_generate,
	}
	if not apply or not to_generate:
		return result
	from illumenate_lighting.illumenate_lighting.api import n8n_config

	n8n_config.spec_webhook_url()
	n8n_config.auth_headers()
	bulk_id = frappe.generate_hash(length=16)
	frappe.cache().set_value(
		BULK_KEY.format(bulk_id),
		{"status": "Queued", "total": len(to_generate), "done": [], "failed": []},
		expires_in_sec=BULK_TTL,
	)
	frappe.db.commit()
	frappe.enqueue(
		"illumenate_lighting.illumenate_lighting.spec_sheet_job.run_bulk",
		queue="long",
		timeout=len(to_generate) * (TIMEOUT + 60),
		job_id=f"spec_sheet_bulk_{bulk_id}",
		bulk_id=bulk_id,
		items=[{"template": list(e["template"]), "brand": e["brand"]} for e in to_generate],
	)
	result["bulk_id"] = bulk_id
	return result


def run_bulk(bulk_id, items):
	"""Background job: generate each template in turn; one failure does not stop the rest.

	Anything that stops the job itself is recorded in its status and the Error Log, so the
	status never stays at Queued.
	"""
	key = BULK_KEY.format(bulk_id)
	try:
		_run_bulk(key, items)
	except Exception as error:
		frappe.log_error(title=f"Bulk spec sheet regeneration failed: {bulk_id}")
		state = frappe.cache().get_value(key) or {}
		state.update(status="Failed", error=str(error))
		frappe.cache().set_value(key, state, expires_in_sec=BULK_TTL)


def _run_bulk(key, items):
	bulk_id = key.split(":", 1)[1]
	state = frappe.cache().get_value(key) or {"total": len(items), "done": [], "failed": []}
	state["status"] = "Running"
	frappe.cache().set_value(key, state, expires_in_sec=BULK_TTL)
	for item in items:
		doctype, name = item["template"]
		job = f"{bulk_id}-{name}"
		run(job, doctype, name, item["brand"])
		status = frappe.cache().get_value(_status_key(job)) or {}
		if status.get("status") == "Done":
			state["done"].append({"template": name, "file_url": status.get("file_url")})
		else:
			state["failed"].append({"template": name, "error": status.get("message")})
		frappe.cache().set_value(key, state, expires_in_sec=BULK_TTL)
	state["status"] = "Done"
	frappe.cache().set_value(key, state, expires_in_sec=BULK_TTL)


@frappe.whitelist()
def spec_sheet_bulk_status(bulk_id):
	"""Progress of a bulk regeneration: status, total, done and failed. System Manager only."""
	frappe.only_for("System Manager")
	state = frappe.cache().get_value(BULK_KEY.format(bulk_id)) or {"status": "Unknown"}
	return {
		**state,
		"progress": f"{len(state.get('done', [])) + len(state.get('failed', []))}/{state.get('total', 0)}",
	}
