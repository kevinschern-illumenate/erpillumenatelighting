# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Generated output uploads (WP-3.7, plan H6 ``upload_deliverable``).

The browser draws the riser (Frappe Cloud has no runtime Node), then sends each file here. The server
checks the bytes are the kind they claim to be, recomputes the SHA-256, stores a private File on the
design and records a deliverable row. Recording a file does not change the design, so the design's
``modified`` stays as it was. Documentation packages (WP-7.3) build on the same rows.
"""

import hashlib
import io
import re
import zipfile
from pathlib import PurePosixPath

import frappe
from frappe import _
from frappe.utils import now_datetime

from illumenate_lighting.illumenate_lighting.system_design import access, telemetry
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

DESIGN_DOCTYPE = "ilL-System-Design"
ROW_DOCTYPE = "ilL-Child-Design-Deliverable"
MAX_BYTES = 20 * 1024 * 1024
MAX_ZIP_MEMBERS = 200
MAX_ZIP_UNPACKED = 200 * 1024 * 1024
FILE_PREFIX = "ilLumenate-System-Designer"

# kind → file extension. Other kinds (presentation, 3D, packages) arrive with their work packages.
# Presentation is the client diagram: the riser's layout, colour-coded, for a homeowner (no schedules).
KINDS = {
	"Riser PDF": ".pdf",
	"Riser DXF ZIP": ".zip",
	"Riser SVG": ".svg",
	"Presentation PDF": ".pdf",
	"Presentation SVG": ".svg",
}
VARIANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Fonts travel with DXF so CAD shows the drawing's lettering; anything else in the ZIP is refused.
ZIP_MEMBER = re.compile(r"^(?:[\w.-]+\.dxf|fonts/[\w.-]+\.(?:ttf|txt))$", re.IGNORECASE)
SVG_ACTIVE = re.compile(
	rb"<\s*script|<\s*foreignObject|\bon[a-z]+\s*=|javascript:|<!ENTITY|xlink:href\s*=\s*[\"'](?!#|data:image/(?:png|jpeg);)"
	rb"|\bhref\s*=\s*[\"'](?!#|data:image/(?:png|jpeg);)",
	re.IGNORECASE,
)


def _invalid(message):
	raise DesignError("INVALID", message)


def validate_deliverable(kind, content):
	"""Check ``content`` is a safe file of ``kind``; returns its MIME type."""
	if kind not in KINDS:
		_invalid(_("Unknown deliverable kind"))
	if not isinstance(content, bytes) or not content or len(content) > MAX_BYTES:
		_invalid(_("The file must be between 1 byte and 20 MiB"))
	if KINDS[kind] == ".pdf":
		from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

		try:
			return validate_content("riser.pdf", content)["mime_type"]
		except ValueError as e:
			_invalid(str(e))
	if kind == "Riser DXF ZIP":
		try:
			with zipfile.ZipFile(io.BytesIO(content)) as archive:
				members = archive.infolist()
				if not members or len(members) > MAX_ZIP_MEMBERS:
					_invalid(_("The DXF ZIP must hold between 1 and {0} files").format(MAX_ZIP_MEMBERS))
				if sum(member.file_size for member in members) > MAX_ZIP_UNPACKED:
					_invalid(_("The DXF ZIP is too large once unpacked"))
				if not any(member.filename.lower().endswith(".dxf") for member in members):
					_invalid(_("The DXF ZIP holds no drawings"))
				for member in members:
					if member.is_dir() or not ZIP_MEMBER.match(member.filename):
						_invalid(_("The DXF ZIP may hold only DXF drawings and their fonts"))
					if member.filename.lower().endswith(".dxf"):
						head = archive.read(member)[:64].lstrip()
						if not (head.startswith(b"0\r\nSECTION") or head.startswith(b"999")):
							_invalid(_("{0} is not a DXF drawing").format(member.filename))
		except zipfile.BadZipFile:
			_invalid(_("The DXF ZIP could not be read"))
		return "application/zip"
	try:
		text = content.decode("utf-8")
	except UnicodeDecodeError:
		_invalid(_("The SVG must be UTF-8 text"))
	if not re.match(r"^\s*(?:<\?xml[^>]*\?>\s*)?<svg[\s>]", text):
		_invalid(_("The file is not an SVG drawing"))
	if SVG_ACTIVE.search(content):
		_invalid(_("The SVG may not hold scripts, external links or entities"))
	return "image/svg+xml"


def deliverable_filename(record, kind, variant):
	"""``ilLumenate-System-Designer_<schedule>_<revision>[_Client][_<variant>].<ext>`` (D2 file names)."""
	parts = [FILE_PREFIX, record.fixture_schedule, f"rev{record.revision}"]
	if kind.startswith("Presentation"):
		parts.append("Client")
	if variant:
		parts.append(variant)
	stem = "_".join(re.sub(r"[^\w.-]+", "-", part).strip("-") for part in parts)
	return f"{stem}{KINDS[kind]}"


def _row(row):
	return {
		"name": row.name,
		"kind": row.kind,
		"variant": row.variant or "",
		"file": row.file,
		"file_sha256": row.file_sha256,
		"revision": row.revision,
		"build_hash": row.build_hash,
		"created_by": row.created_by,
		"created_on": str(row.created_on),
	}


def list_deliverables(record):
	return [_row(row) for row in sorted(record.get("deliverables") or [], key=lambda row: row.idx)]


def upload_deliverable(design, kind, variant=None, sha256=None, build_hash=None, content=None, filename=None):
	"""Store a generated file on a design (H6). ``content`` defaults to the request's ``file`` part."""
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	record = access.require_design(design)
	# A deliverable leaves the schedule as it is, so a locked (ordered) version can still export.
	# Applications Engineers keep the drawings they review (WP-4.3).
	if not allowed("design_review"):
		access.require_edit(record.fixture_schedule, allow_locked=True)
	if kind not in KINDS:
		_invalid(_("Unknown deliverable kind"))
	variant = str(variant or "").strip()
	if variant and not VARIANT.match(variant):
		_invalid(_("Use a variant of letters, numbers, spaces, dots and dashes"))
	if not sha256 or not SHA256.match(str(sha256)):
		_invalid(_("Send the file's SHA-256"))
	if build_hash and build_hash != record.build_hash:
		raise DesignError("CONFLICT", _("Save the design before sending its drawings"))
	if content is None:
		source = (frappe.request.files if frappe.request else {}).get("file")
		if not source:
			_invalid(_("Select a file to upload"))
		content = source.stream.read(MAX_BYTES + 1)
		filename = source.filename
	if filename and PurePosixPath(str(filename)).suffix.lower() != KINDS[kind]:
		_invalid(_("The file name does not match its kind"))
	mime = validate_deliverable(kind, content)
	digest = hashlib.sha256(content).hexdigest()
	if digest != sha256:
		_invalid(_("The file changed in transit; try again"))
	for row in record.get("deliverables") or []:
		if (
			row.kind == kind
			and (row.variant or "") == variant
			and row.file_sha256 == digest
			and row.build_hash == record.build_hash
		):
			url = frappe.db.get_value("File", {"file_url": row.file}, "file_url") or row.file
			return {"file_url": url, "row": _row(row), "mime_type": mime}
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": deliverable_filename(record, kind, variant),
			"content": content,
			"is_private": 1,
			"attached_to_doctype": DESIGN_DOCTYPE,
			"attached_to_name": record.name,
			"attached_to_field": "deliverables",
		}
	)
	file.flags.ignore_permissions = True
	file.insert()
	if not file.is_private or not str(file.file_url).startswith("/private/files/"):
		raise DesignError("INTERNAL", _("Deliverable storage did not produce a private file"))
	row = frappe.get_doc(
		{
			"doctype": ROW_DOCTYPE,
			"parent": record.name,
			"parenttype": DESIGN_DOCTYPE,
			"parentfield": "deliverables",
			"idx": len(record.get("deliverables") or []) + 1,
			"kind": kind,
			"variant": variant,
			"file": file.file_url,
			"file_sha256": digest,
			"revision": record.revision,
			"build_hash": record.build_hash,
			"created_by": frappe.session.user,
			"created_on": now_datetime(),
		}
	)
	# Insert the row alone: the design's ``modified`` stays as it was, so the open editor can still save.
	row.db_insert()
	telemetry.record(
		"riser_exported",
		record.fixture_schedule,
		record.name,
		{"kind": kind, "sheet": variant, "stored": True},
	)
	return {"file_url": file.file_url, "row": _row(row), "mime_type": mime}
