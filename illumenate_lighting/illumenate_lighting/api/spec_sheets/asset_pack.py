# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Import a spec asset pack (zip + ``assets_manifest.json``) written by the YAML builder.

Run it **after** the CSV import, so the records it attaches artwork to exist. Upload
the zip as a private File, then from the System Console (tick **Commit** to apply):

	print(frappe.call(
		"illumenate_lighting.illumenate_lighting.api.spec_sheets.asset_pack.import_asset_pack",
		file_url="/private/files/st-helens-assets.zip",
		dry_run=0,
	))

Nothing is written unless every file and target in the pack is valid. Re-running a
pack is safe: files are matched by SHA-256 and rows by role, title and feed/bend.

Manifest format (version 1)::

        {
            "format": "ill-spec-asset-pack",
            "version": 1,
            "assets": [
                {
                    "path": "assets/SH01_cross_section.svg",
                    "sha256": "<hex>",
                    "targets": [
                        {
                            "doctype": "ilL-Spec-Profile",
                            "name": "SH01",
                            "table": "spec_assets",
                            "row": {"asset_role": "Cross Section", "title": "Cross Section"},
                        },
                        {"doctype": "ilL-Attribute-Environment Rating", "name": "Wet", "field": "spec_icon"},
                    ],
                }
            ],
        }
"""

import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath

import frappe

from illumenate_lighting.illumenate_lighting.api.spec_sheets.asset_targets import (
	ASSET_ROLES,
	FIELDS,
	FORMAT,
	MANIFEST,
	SPEC_LINES,
	TABLES,
)
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import check_svg, has_fpo

MAX_ASSETS = 500
MAX_ASSET_BYTES = 20 * 1024 * 1024
MAX_PACK_BYTES = 250 * 1024 * 1024
ROLES = ("System Manager", "ilL Catalog Publisher", "ilL Engineering")


class PackError(ValueError):
	pass


def read_pack(data):
	"""Parse and validate a pack's bytes; returns ``(assets, errors)`` without touching the site.

	Each asset is ``{"name", "content", "sha256", "fpo", "targets", "converted_from"}``.
	"""
	errors = []
	try:
		archive = zipfile.ZipFile(io.BytesIO(data))
	except zipfile.BadZipFile:
		raise PackError("The asset pack is not a zip file")
	entries = {info.filename: info for info in archive.infolist() if not info.is_dir()}
	if sum(info.file_size for info in entries.values()) > MAX_PACK_BYTES:
		raise PackError("The asset pack is larger than 250 MB uncompressed")
	if MANIFEST not in entries:
		raise PackError(f"The asset pack has no {MANIFEST}")
	try:
		manifest = json.loads(archive.read(MANIFEST))
	except ValueError as error:
		raise PackError(f"{MANIFEST} is not valid JSON: {error}")
	if manifest.get("format") != FORMAT or manifest.get("version") != 1:
		raise PackError(f"{MANIFEST} is not a version 1 {FORMAT} manifest")
	listed = manifest.get("assets")
	if not isinstance(listed, list) or not listed or len(listed) > MAX_ASSETS:
		raise PackError(f"{MANIFEST} must list 1 to {MAX_ASSETS} assets")
	assets = []
	for number, item in enumerate(listed, 1):
		path = item.get("path") if isinstance(item, dict) else None
		label = path or f"asset {number}"
		try:
			assets.append(_read_asset(archive, entries, item))
		except PackError as error:
			errors.append(f"{label}: {error}")
	return assets, errors


def _read_asset(archive, entries, item):
	path = item.get("path")
	if not isinstance(path, str) or path not in entries:
		raise PackError("listed in the manifest but missing from the zip")
	if entries[path].file_size > MAX_ASSET_BYTES:
		raise PackError("larger than 20 MB")
	content = archive.read(path)
	digest = hashlib.sha256(content).hexdigest()
	if item.get("sha256") != digest:
		raise PackError("SHA-256 does not match the manifest (file changed after the pack was built)")
	name = PurePosixPath(path).name
	content, name, converted_from = _printable(name, content)
	targets = item.get("targets")
	if not isinstance(targets, list) or not targets:
		raise PackError("has no targets")
	for target in targets:
		_check_target(target)
	return {
		"name": name,
		"content": content,
		"sha256": hashlib.sha256(content).hexdigest(),
		"source_sha256": digest,
		"fpo": name.lower().endswith(".svg") and has_fpo(content),
		"targets": targets,
		"converted_from": converted_from,
	}


def _printable(name, content):
	"""Validate artwork; TIFF photos become PNG (browsers cannot draw TIFF)."""
	suffix = PurePosixPath(name).suffix.lower()
	if suffix == ".svg":
		try:
			check_svg(content, name)
		except ValueError as error:
			raise PackError(str(error))
		return content, name, None
	if suffix in (".tif", ".tiff"):
		png = _tiff_to_png(content, name)
		return png, str(PurePosixPath(name).with_suffix(".png")), name
	if suffix in (".png", ".jpg", ".jpeg"):
		from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

		try:
			validate_content(name, content)
		except ValueError as error:
			raise PackError(str(error))
		return content, name, None
	raise PackError("use SVG for drawings and icons, PNG/JPEG/TIFF for photos (convert AI/PDF/EPS first)")


def _tiff_to_png(content, name):
	from PIL import Image

	try:
		with Image.open(io.BytesIO(content)) as source:
			if source.format != "TIFF" or source.width * source.height > 40_000_000:
				raise PackError("is not a TIFF of at most 40 million pixels")
			image = source.convert("RGBA" if "A" in source.getbands() else "RGB")
			dpi = source.info.get("dpi")
			output = io.BytesIO()
			image.save(output, "PNG", optimize=True, **({"dpi": dpi} if dpi else {}))
			return output.getvalue()
	except PackError:
		raise
	except Exception as error:
		raise PackError(f"TIFF could not be converted: {error}")


def _check_target(target):
	if not isinstance(target, dict) or not target.get("doctype") or not target.get("name"):
		raise PackError("each target needs a doctype and a name")
	doctype = target["doctype"]
	if target.get("table"):
		table = TABLES.get(target["table"])
		if not table or doctype not in table[0]:
			raise PackError(f"{doctype} has no artwork table {target['table']!r}")
		row = target.get("row")
		if not isinstance(row, dict):
			raise PackError(f"{doctype} {target['name']}: table targets need a row")
		unknown = set(row) - set(table[2])
		if unknown:
			raise PackError(f"unknown row fields {', '.join(sorted(unknown))}")
		if target["table"] == "spec_assets" and row.get("asset_role") not in ASSET_ROLES:
			raise PackError(f"asset_role must be one of {', '.join(ASSET_ROLES)}")
		if target["table"] == "document_logos" and row.get("spec_line") not in SPEC_LINES:
			raise PackError(f"spec_line must be one of {', '.join(SPEC_LINES)}")
	elif target.get("field"):
		if target["field"] not in FIELDS.get(doctype, ()):
			raise PackError(f"{doctype} has no artwork field {target['field']!r}")
	else:
		raise PackError("each target needs a table (with a row) or a field")


def _row_key(row, key_fields):
	return tuple((row.get(field) or "") for field in key_fields)


def _stored_name(asset):
	stem = re.sub(r"[^A-Za-z0-9._-]+", "-", asset["name"]).strip("-") or "asset"
	return f"spec-{asset['sha256'][:8]}-{stem}"


def _ensure_file(asset):
	"""Public File for the asset; reused when a File with the same content and name exists."""
	stored = _stored_name(asset)
	existing = frappe.db.get_value("File", {"file_name": stored, "is_private": 0}, "file_url")
	if existing:
		return existing, False
	file = frappe.get_doc(
		{"doctype": "File", "file_name": stored, "is_private": 0, "content": asset["content"]}
	).insert()
	return file.file_url, True


def _apply(asset, url, report):
	for target in asset["targets"]:
		doc = frappe.get_doc(target["doctype"], target["name"])
		if target.get("field"):
			if doc.get(target["field"]) == url:
				continue
			doc.set(target["field"], url)
			report["fields_set"] += 1
		else:
			_parents, file_field, _fields, key_fields = TABLES[target["table"]]
			wanted = {**target["row"], file_field: url}
			match = next(
				(
					row
					for row in doc.get(target["table"]) or []
					if _row_key(row, key_fields) == _row_key(wanted, key_fields)
				),
				None,
			)
			if match is None:
				doc.append(target["table"], wanted)
				report["rows_added"] += 1
			elif any(match.get(field) != value for field, value in wanted.items()):
				match.update(wanted)
				report["rows_updated"] += 1
			else:
				continue
		doc.save()


def import_pack(data, dry_run=True):
	"""Validate a pack and, unless ``dry_run``, create its Files and attach them."""
	assets, errors = read_pack(data)
	for asset in assets:
		for target in asset["targets"]:
			if not frappe.db.exists(target["doctype"], target["name"]):
				errors.append(f"{asset['name']}: {target['doctype']} {target['name']!r} does not exist")
	report = {
		"dry_run": bool(dry_run),
		"assets": len(assets),
		"errors": errors,
		"converted": [asset["converted_from"] for asset in assets if asset["converted_from"]],
		"fpo_placeholders": [asset["name"] for asset in assets if asset["fpo"]],
		"files_created": 0,
		"rows_added": 0,
		"rows_updated": 0,
		"fields_set": 0,
	}
	if errors or dry_run:
		return report
	for asset in assets:
		url, created = _ensure_file(asset)
		report["files_created"] += int(created)
		_apply(asset, url, report)
	return report


@frappe.whitelist(methods=["POST"])
def import_asset_pack(file_url, dry_run=1):
	"""Import an uploaded asset pack zip (a File URL). ``dry_run=1`` only validates."""
	frappe.only_for(ROLES)
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.site import _file_content

	try:
		return import_pack(_file_content(file_url), dry_run=frappe.utils.cint(dry_run))
	except PackError as error:
		return {"dry_run": bool(frappe.utils.cint(dry_run)), "errors": [str(error)]}
