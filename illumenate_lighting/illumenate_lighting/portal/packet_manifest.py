"""Deterministic packet inventory and strict source validation, independent of Frappe."""

import hashlib
from io import BytesIO

from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content


def prepare_source(content, filename):
	"""Keep original bytes pinned; normalize supported raster sources to PDF."""
	metadata = validate_content(filename, content)
	if metadata["mime_type"] == "application/pdf":
		return content, metadata
	from PIL import Image, ImageOps

	with Image.open(BytesIO(content)) as source:
		oriented = ImageOps.exif_transpose(source)
		if oriented.mode in ("RGBA", "LA") or "transparency" in oriented.info:
			rgba = oriented.convert("RGBA")
			rgb = Image.new("RGB", rgba.size, "white")
			rgb.paste(rgba, mask=rgba.getchannel("A"))
		else:
			rgb = oriented.convert("RGB")
		stream = BytesIO()
		rgb.save(stream, "PDF", resolution=150)
	metadata["pages"] = 1
	return stream.getvalue(), metadata


def assemble_manifest(lines, load_source, *, filled=True, cover_pages=0):
	"""An optional exclusion is explicit; any missing required source blocks success."""
	manifest, parts, errors = [], [], []
	page = cover_pages + 1
	seen = set()
	for line in lines:
		key = line.get("line_key")
		if not key or key in seen:
			raise ValueError("Each packet line needs a unique stable key")
		seen.add(key)
		entry = {
			"line_key": key,
			"designation": line.get("line_id"),
			"quantity": line.get("qty"),
			"manufacturer_type": line.get("manufacturer_type"),
			"source_url": line.get("spec_document_url"),
			"source_kind": line.get("source_kind"),
			"build": line.get("build"),
			"provenance": line.get("provenance"),
			"required": line.get("required", True),
			"status": "pending",
		}
		manifest.append(entry)
		if not entry["required"] and not entry["source_url"]:
			entry.update(status="excluded", reason=line.get("exclusion_reason") or "No approved literature")
			continue
		try:
			if (
				filled
				and line.get("filled_required", True)
				and entry["manufacturer_type"] == "ILLUMENATE"
				and not line.get("has_submittal")
			):
				raise ValueError("A filled submittal is required; static literature cannot replace it")
			if not entry["source_url"]:
				raise ValueError("Required source document is missing")
			content, filename = load_source(entry["source_url"])
			pdf, metadata = prepare_source(content, filename)
			if line.get("expected_sha256") and line["expected_sha256"] != metadata["sha256"]:
				raise ValueError("Source bytes changed after document approval")
			pages = metadata["pages"]
			entry.update(
				status="included",
				sha256=metadata["sha256"],
				byte_size=metadata["size"],
				page_count=pages,
				page_start=page,
				page_end=page + pages - 1,
				pdf_sha256=hashlib.sha256(pdf).hexdigest(),
			)
			page += pages
			parts.append(pdf)
		except (ValueError, OSError) as error:
			entry.update(status="failed", reason=str(error))
			errors.append(f"Line {entry['designation']} ({key}): {error}")
	if not parts:
		errors.append("No required product documents are available; a cover alone is not a packet")
	return manifest, parts, errors
