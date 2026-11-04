"""Dealer photos and imagery (hardening plan 4.3-4.7).

Purpose and caption on uploads, private WebP thumbnails, the project/line photo
gallery, dealer-logo self-service and Desk HEIC conversion for product imagery.
Every path reuses the upload verification in ``portal/files.py`` and the
schedule/project policies in ``portal/access.py``; nothing here widens access.
"""

import hashlib
import io
import warnings
from pathlib import PurePosixPath

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.file_validation import (
	HEIF_EXTENSIONS,
	MAX_FILES,
	MAX_IMAGE_PIXELS,
	normalize_upload,
)
from illumenate_lighting.illumenate_lighting.portal.site_flags import (
	dealer_logo_enabled,
	gallery_enabled,
	staff_heic_enabled,
	thumbnails_enabled,
	upload_purpose_enabled,
)

UPLOAD_DOCTYPE = "ilL-Portal-Upload"
LINE_DOCTYPE = "ilL-Line-Document"
SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"
REQUEST_DOCTYPE = "ilL-Document-Request"
PURPOSES = (
	"Site photo",
	"Reference image",
	"Existing fixture",
	"Drawing markup",
	"Logo",
	"PO",
	"Other",
)
MAX_CAPTION = 280
IMAGE_MIMES = ("image/jpeg", "image/png")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
THUMBNAIL_PX = 480
THUMBNAIL_QUALITY = 80
LOGO_BOX = (1200, 600)
OPEN_REQUEST_STATES = ("Draft", "Submitted", "In Progress", "Waiting on Customer")
LINE_DOWNLOAD = "/api/method/illumenate_lighting.illumenate_lighting.portal.line_documents.download?name="

# Desk uploads converted from HEIC: doctype → attach fields (4.7). Gallery rows upload
# through their parent form, so the child field name ``image`` arrives on the parent.
TEMPLATE_DOCTYPES = (
	"ilL-Fixture-Template",
	"ilL-Tape-Neon-Template",
	"ilL-LED-Sheet-Template",
	"ilL-Extrusion-Kit-Template",
	"ilL-Driver-Template",
	"ilL-Controller-Template",
)
STAFF_IMAGE_FIELDS = {
	**{doctype: frozenset(("hero_image", "image")) for doctype in TEMPLATE_DOCTYPES},
	"ilL-Webflow-Product": frozenset(("featured_image", "dimensions_image", "series_family_image", "image")),
	"ilL-Child-Webflow-Gallery-Image": frozenset(("image",)),
}


# 4.3 Purpose and caption -------------------------------------------------------------


def clean_purpose(value):
	value = str(value or "").strip()
	if not value:
		return ""
	for purpose in PURPOSES:
		if value.casefold() == purpose.casefold():
			return purpose
	raise ValueError("Choose one of the listed purposes")


def clean_caption(value):
	value = "".join(ch for ch in str(value or "") if ch in "\n\t" or ch.isprintable()).strip()
	if len(value) > MAX_CAPTION:
		raise ValueError(f"Captions can be at most {MAX_CAPTION} characters")
	return value


def annotations(purpose=None, caption=None):
	"""Validated purpose/caption values to store; empty when the feature is switched off."""
	if not upload_purpose_enabled():
		return {}
	values = {}
	if purpose is not None:
		values["purpose"] = clean_purpose(purpose)
	if caption is not None:
		values["caption"] = clean_caption(caption)
	return values


# 4.4 Thumbnails ------------------------------------------------------------------------


def make_thumbnail(content):
	"""A metadata-free WebP no larger than 480 px, or None when the bytes are not a PNG/JPEG."""
	from PIL import Image, ImageOps, UnidentifiedImageError

	with warnings.catch_warnings():
		warnings.simplefilter("error", Image.DecompressionBombWarning)
		try:
			source = Image.open(io.BytesIO(content))
		except UnidentifiedImageError:
			return None
		with source:
			if source.format not in ("PNG", "JPEG") or source.width * source.height > MAX_IMAGE_PIXELS:
				return None
			source.draft("RGB", (THUMBNAIL_PX * 2, THUMBNAIL_PX * 2))
			image = ImageOps.exif_transpose(source)
			image.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX))
			alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
			image = image.convert("RGBA" if alpha else "RGB")
	image.info = {}
	output = io.BytesIO()
	image.save(output, format="WEBP", quality=THUMBNAIL_QUALITY, method=4)
	return output.getvalue()


def store_thumbnail(artifact, filename, content):
	"""Attach a private thumbnail to the upload artifact. Never fails the upload itself."""
	if not thumbnails_enabled() or artifact.mime_type not in IMAGE_MIMES:
		return None
	try:
		data = make_thumbnail(content)
		if not data:
			return None
		stem = PurePosixPath(filename or "image").stem[:150] or "image"
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{stem}.thumb.webp",
				"content": data,
				"is_private": 1,
				"owner": "Administrator",
				"attached_to_doctype": UPLOAD_DOCTYPE,
				"attached_to_name": artifact.name,
			}
		).insert(ignore_permissions=True)
		if not file.is_private or not str(file.file_url or "").startswith("/private/files/"):
			return None
		return file.name
	except Exception:
		frappe.log_error(title="Portal thumbnail generation failed", message=frappe.get_traceback())
		return None


def thumbnail_urls(file_names):
	"""{original File name: thumbnail URL}. Thumbnails are served by the private-file guard."""
	file_names = [name for name in set(file_names or []) if name]
	if not file_names or not thumbnails_enabled():
		return {}
	rows = frappe.get_all(
		UPLOAD_DOCTYPE,
		filters={"file": ["in", file_names], "thumbnail": ["is", "set"]},
		fields=["file", "thumbnail"],
	)
	if not rows:
		return {}
	urls = {
		row.name: row.file_url
		for row in frappe.get_all(
			"File", filters={"name": ["in", [row.thumbnail for row in rows]]}, fields=["name", "file_url"]
		)
	}
	return {row.file: urls[row.thumbnail] for row in rows if urls.get(row.thumbnail)}


def backfill_thumbnails(limit=500):
	"""Optional background job: thumbnails for image uploads made before 4.4. Safe to rerun."""
	done = 0
	for row in frappe.get_all(
		UPLOAD_DOCTYPE,
		filters={
			"mime_type": ["in", list(IMAGE_MIMES)],
			"thumbnail": ["is", "not set"],
			"file": ["is", "set"],
			"state": ["in", ["STAGING", "FINALIZED"]],
		},
		fields=["name"],
		limit=int(limit),
		order_by="creation desc",
	):
		artifact = frappe.get_doc(UPLOAD_DOCTYPE, row.name)
		try:
			file = frappe.get_doc("File", artifact.file)
			content = file.get_content()
		except Exception:
			frappe.log_error(title="Thumbnail backfill skipped", message=frappe.get_traceback())
			continue
		if hashlib.sha256(content).hexdigest() != artifact.sha256:
			continue
		thumbnail = store_thumbnail(artifact, file.file_name, content)
		if thumbnail:
			frappe.db.set_value(UPLOAD_DOCTYPE, artifact.name, "thumbnail", thumbnail, update_modified=False)
			done += 1
		frappe.db.commit()
	return done


@frappe.whitelist(methods=["POST"])
def enqueue_thumbnail_backfill(limit=500):
	frappe.only_for("System Manager")
	frappe.enqueue(
		"illumenate_lighting.illumenate_lighting.portal.media.backfill_thumbnails",
		queue="long",
		limit=int(limit),
		job_id="ill-portal-thumbnail-backfill",
		deduplicate=True,
	)
	return {"success": True}


# 4.5 Gallery ---------------------------------------------------------------------------


def _is_image(file_name):
	return PurePosixPath(str(file_name or "")).suffix.lower() in IMAGE_EXTENSIONS


def _gallery_schedules(project, schedule_name):
	from illumenate_lighting.illumenate_lighting.portal.access import can_read_project, can_read_schedule
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	if schedule_name:
		return [schedule_context(schedule_name)]
	if not project or not frappe.db.exists("ilL-Project", project):
		frappe.throw(_("Project is unavailable"), frappe.PermissionError)
	if not can_read_project(frappe.get_doc("ilL-Project", project)):
		frappe.throw(_("Project is unavailable"), frappe.PermissionError)
	schedules = []
	for name in frappe.get_all(SCHEDULE_DOCTYPE, filters={"ill_project": project}, pluck="name"):
		doc = frappe.get_doc(SCHEDULE_DOCTYPE, name)
		if can_read_schedule(doc):
			schedules.append(doc)
	return schedules


def _attachable_requests(project):
	from illumenate_lighting.illumenate_lighting.portal.files import _context_access

	if not project:
		return []
	return [
		{"name": row.name, "request_type": row.request_type, "status": row.status}
		for row in frappe.get_all(
			REQUEST_DOCTYPE,
			filters={"project": project, "status": ["in", list(OPEN_REQUEST_STATES)]},
			fields=["name", "request_type", "status"],
			order_by="creation desc",
			limit=50,
		)
		if _context_access(REQUEST_DOCTYPE, row.name, "write")
	]


@frappe.whitelist()
def gallery(project=None, schedule_name=None, line_key=None):
	"""Images attached to a project's lines, or to one schedule line, with captions and rights."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
	from illumenate_lighting.illumenate_lighting.portal.configuration import resolve_line

	if not gallery_enabled():
		return {"success": True, "enabled": False, "items": [], "requests": [], "purposes": list(PURPOSES)}
	schedules = _gallery_schedules(project, schedule_name)
	filters = {"schedule": ["in", [doc.name for doc in schedules] or [""]], "active": 1}
	if schedule_name and line_key:
		line = resolve_line(schedules[0], line_key)
		filters["line_key"] = line.get("line_key") or line.name
	by_name = {doc.name: doc for doc in schedules}
	labels = {
		(doc.name, line.get("line_key") or line.name): line.get("line_id") or ""
		for doc in schedules
		for line in doc.get("lines") or []
	}
	editable = {doc.name for doc in schedules if can_edit_schedule(doc) and not doc.get("is_locked")}
	rows = [
		row
		for row in frappe.get_all(
			LINE_DOCTYPE,
			filters=filters,
			fields=["name", "schedule", "line_key", "file", "file_name", "title", "purpose", "caption"],
			order_by="creation desc, name asc",
		)
		if _is_image(row.file_name)
	]
	thumbs = thumbnail_urls([row.file for row in rows])
	urls = {
		file.name: file.file_url
		for file in frappe.get_all(
			"File", filters={"name": ["in", [row.file for row in rows] or [""]]}, fields=["name", "file_url"]
		)
	}
	items = [
		{
			"name": row.name,
			"schedule": row.schedule,
			"schedule_name": by_name[row.schedule].get("schedule_name") or row.schedule,
			"schedule_modified": str(by_name[row.schedule].modified),
			"line_key": row.line_key,
			"line_id": labels.get((row.schedule, row.line_key), ""),
			"file_name": row.file_name,
			"title": row.title or row.file_name,
			"purpose": row.purpose or "",
			"caption": row.caption or "",
			"thumbnail_url": thumbs.get(row.file) or urls.get(row.file) or "",
			"image_url": urls.get(row.file) or "",
			"download_url": LINE_DOWNLOAD + row.name,
			"can_edit": row.schedule in editable,
		}
		for row in rows
	]
	project = project or (schedules[0].get("ill_project") if schedules else None)
	return {
		"success": True,
		"enabled": True,
		"items": items,
		"requests": _attachable_requests(project) if editable else [],
		"purposes": list(PURPOSES),
	}


@frappe.whitelist(methods=["POST"])
def attach_to_request(document, request_name):
	"""Copy a line photo into an open drawing request of the same project as a new private upload."""
	from illumenate_lighting.illumenate_lighting.portal.files import _context_access

	if not gallery_enabled():
		frappe.throw(_("The photo gallery is turned off"), frappe.PermissionError)
	if not frappe.db.exists(LINE_DOCTYPE, document) or not frappe.db.exists(REQUEST_DOCTYPE, request_name):
		frappe.throw(_("Photo or request is unavailable"), frappe.PermissionError)
	source = frappe.get_doc(LINE_DOCTYPE, document)
	from illumenate_lighting.illumenate_lighting.portal.configuration import schedule_context

	schedule = schedule_context(source.schedule, write=True)
	if not source.active or not _is_image(source.file_name):
		raise ValueError("Only active photos can be sent to a drawing request")
	if not _context_access(REQUEST_DOCTYPE, request_name, "write"):
		frappe.throw(_("Request is unavailable"), frappe.PermissionError)
	frappe.db.sql(f"select name from `tab{REQUEST_DOCTYPE}` where name=%s for update", request_name)
	request = frappe.get_doc(REQUEST_DOCTYPE, request_name)
	if request.status not in OPEN_REQUEST_STATES:
		raise ValueError("This request no longer accepts attachments")
	if not request.project or request.project != schedule.get("ill_project"):
		frappe.throw(_("Choose a request for the same project"), frappe.PermissionError)
	existing = frappe.get_all(
		UPLOAD_DOCTYPE,
		filters={"parent_type": REQUEST_DOCTYPE, "parent_name": request.name, "state": "FINALIZED"},
		fields=["sha256"],
	)
	if any(row.sha256 == source.sha256 for row in existing):
		return {"success": True, "already_attached": True}
	if len(existing) >= MAX_FILES:
		raise ValueError("An intake can contain at most 10 files")
	content = frappe.get_doc("File", source.file).get_content()
	if hashlib.sha256(content).hexdigest() != source.sha256:
		raise ValueError("Photo bytes changed. Upload the photo again.")
	extension = PurePosixPath(source.file_name).suffix.lower()
	artifact = frappe.get_doc(
		{
			"doctype": UPLOAD_DOCTYPE,
			"parent_type": REQUEST_DOCTYPE,
			"parent_name": request.name,
			"requested_by": frappe.session.user,
			"state": "FINALIZED",
			"sha256": source.sha256,
			"file_size": len(content),
			"mime_type": "image/png" if extension == ".png" else "image/jpeg",
			"purpose": source.get("purpose") or "",
			"caption": source.get("caption") or "",
		}
	).insert(ignore_permissions=True)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": source.file_name,
			"content": content,
			"is_private": 1,
			"owner": "Administrator",
			"attached_to_doctype": UPLOAD_DOCTYPE,
			"attached_to_name": artifact.name,
		}
	).insert(ignore_permissions=True)
	if not file.is_private or not str(file.file_url or "").startswith("/private/files/"):
		frappe.throw(_("Upload storage did not produce a private file"))
	artifact.file = file.name
	artifact.save(ignore_permissions=True)
	return {"success": True, "already_attached": False, "file_id": file.name}


# 4.6 Dealer logo -----------------------------------------------------------------------


def normalize_logo(content):
	"""Re-encode a PNG/JPEG logo as a metadata-free PNG inside 1200x600 px."""
	from PIL import Image, ImageOps

	try:
		with warnings.catch_warnings():
			warnings.simplefilter("error", Image.DecompressionBombWarning)
			with Image.open(io.BytesIO(content)) as source:
				if source.format not in ("PNG", "JPEG") or source.width * source.height > MAX_IMAGE_PIXELS:
					raise ValueError("Use a PNG or JPEG logo")
				image = ImageOps.exif_transpose(source)
				image.thumbnail(LOGO_BOX)
				alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
				image = image.convert("RGBA" if alpha else "RGB")
	except ValueError:
		raise
	except Exception as exc:
		raise ValueError(f"Logo could not be read: {exc}") from exc
	image.info = {}
	output = io.BytesIO()
	image.save(output, format="PNG", optimize=True)
	return output.getvalue(), image.width, image.height


def store_dealer_logo(file_id, customer):
	"""Publish a verified, unbound upload of the caller as ``Customer.dealer_logo``."""
	file = frappe.get_doc("File", file_id)
	if file.attached_to_doctype != UPLOAD_DOCTYPE or not file.is_private:
		frappe.throw(_("Use a verified private upload"), frappe.PermissionError)
	artifact = frappe.get_doc(UPLOAD_DOCTYPE, file.attached_to_name)
	if (
		artifact.requested_by != frappe.session.user
		or artifact.file != file.name
		or artifact.state != "STAGING"
		or artifact.parent_type
		or artifact.parent_name
	):
		frappe.throw(_("This upload is unavailable"), frappe.PermissionError)
	content = file.get_content()
	if hashlib.sha256(content).hexdigest() != artifact.sha256:
		raise ValueError("Uploaded content changed; upload the file again")
	if artifact.mime_type not in IMAGE_MIMES:
		raise ValueError("Use a PNG or JPEG logo")
	data, width, height = normalize_logo(content)
	# The title block and exports load the logo without a portal session (System Designer
	# worker, packet renderer), so the re-encoded copy is public. The original stays private.
	logo = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"dealer-logo-{hashlib.sha256(data).hexdigest()[:12]}.png",
			"content": data,
			"is_private": 0,
			"owner": "Administrator",
			"attached_to_doctype": "Customer",
			"attached_to_name": customer,
			"attached_to_field": "dealer_logo",
		}
	).insert(ignore_permissions=True)
	artifact.parent_type, artifact.parent_name, artifact.state = "Customer", customer, "FINALIZED"
	artifact.purpose = "Logo"
	artifact.save(ignore_permissions=True)
	frappe.db.set_value("Customer", customer, "dealer_logo", logo.file_url)
	return {"dealer_logo": logo.file_url, "width": width, "height": height}


def dealer_logo_available():
	return dealer_logo_enabled() and frappe.get_meta("Customer").has_field("dealer_logo")


# 4.7 Staff HEIC ------------------------------------------------------------------------


def convert_staff_heic(doc):
	"""Before a Desk File is written, turn a HEIC product image into a browser-viewable JPEG."""
	if doc.get("is_folder") or not doc.get("content"):
		return
	if PurePosixPath(str(doc.get("file_name") or "")).suffix.lower() not in HEIF_EXTENSIONS:
		return
	fields = STAFF_IMAGE_FIELDS.get(doc.get("attached_to_doctype"))
	if not fields or doc.get("attached_to_field") not in fields or not staff_heic_enabled():
		return
	content = doc.get_content()
	if isinstance(content, str):
		content = content.encode()
	try:
		file_name, converted = normalize_upload(doc.file_name, content)
	except ValueError as exc:
		frappe.throw(str(exc))
	doc.content = converted
	doc.decode = False
	doc.file_name = file_name
