"""Spec artwork referenced by local path in version 2 catalogs → an asset pack for ERPNext.

Artwork fields (``spec_assets[].file``, ``document_logos[].logo``, ``spec_icon``,
``badge_image``) may hold a path relative to the catalog file, e.g.
``assets/st-helens/SH01_cross_section.svg``. Those values are taken out of the CSV
records and written to ``assets.zip`` with ``assets_manifest.json``, which the ERPNext
asset pack importer (``api/spec_sheets/asset_pack.py``) attaches after the CSV import.
Values that are already File URLs stay in the CSVs.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

from illumenate_lighting.illumenate_lighting.api.spec_sheets.asset_targets import (
	FIELDS,
	FORMAT,
	MANIFEST,
	SOURCE_TYPES,
	TABLES,
	is_uploaded,
)
from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import check_svg

PACK = "assets.zip"
MAX_ASSET_BYTES = 20 * 1024 * 1024
# Fixed timestamp so the same artwork always produces the same zip.
ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _local(value):
	return isinstance(value, str) and value.strip() != "" and not is_uploaded(value)


def extract_assets(records, identity, asset_root):
	"""Move local artwork paths out of ``records`` (in place) into asset pack entries.

	``identity(doctype, record)`` returns a record's ERPNext name. Returns
	``(assets, errors)``; ``assets`` maps each normalized path to its manifest entry.
	"""
	assets, errors = {}, []

	def add(path, value, target):
		entry = _asset(value, asset_root, errors, path)
		if entry is None:
			return
		if not target["name"]:
			errors.append(f"{path}: artwork needs a record with a fixed name")
			return
		assets.setdefault(entry["path"], entry)["targets"].append(target)

	for doctype, rows in records.items():
		for i, row in enumerate(rows):
			name = identity(doctype, row)
			for table, (parents, file_field, row_fields, _key) in TABLES.items():
				if doctype not in parents or not isinstance(row.get(table), list):
					continue
				kept = []
				for j, child in enumerate(row[table]):
					value = child.get(file_field) if isinstance(child, dict) else None
					if not _local(value):
						kept.append(child)
						continue
					fields = {key: child[key] for key in row_fields if child.get(key) not in (None, "")}
					add(
						f"{doctype}[{i}].{table}[{j}].{file_field}",
						value,
						{"doctype": doctype, "name": name, "table": table, "row": fields},
					)
				row[table] = kept
			for field in FIELDS.get(doctype, ()):
				if _local(row.get(field)):
					add(
						f"{doctype}[{i}].{field}",
						row.pop(field),
						{"doctype": doctype, "name": name, "field": field},
					)
	return assets, errors


def _asset(value, asset_root, errors, path):
	if asset_root is None:
		errors.append(f"{path}: local artwork {value!r} needs the catalog file's folder")
		return None
	root = Path(asset_root).resolve()
	source = (root / value).resolve()
	if root not in source.parents:
		errors.append(f"{path}: {value!r} is outside the catalog folder")
		return None
	if source.suffix.lower() not in SOURCE_TYPES:
		errors.append(f"{path}: {value!r} must be SVG (drawings, icons) or PNG/JPEG/TIFF (photos)")
		return None
	if not source.is_file():
		errors.append(f"{path}: {value!r} does not exist")
		return None
	content = source.read_bytes()
	if not content or len(content) > MAX_ASSET_BYTES:
		errors.append(f"{path}: {value!r} must be between 1 byte and 20 MB")
		return None
	if source.suffix.lower() == ".svg":
		try:
			check_svg(content, value)
		except ValueError as error:
			errors.append(f"{path}: {error}")
			return None
	relative = PurePosixPath(*source.relative_to(root).parts)
	return {
		"path": str(relative),
		"sha256": hashlib.sha256(content).hexdigest(),
		"targets": [],
		"_source": source,
	}


def write_pack(assets, output):
	"""Write ``assets.zip`` (manifest + files) to ``output``; returns its path."""
	manifest = {
		"format": FORMAT,
		"version": 1,
		"assets": [
			{key: value for key, value in entry.items() if not key.startswith("_")}
			for _path, entry in sorted(assets.items())
		],
	}
	path = Path(output) / PACK
	with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
		archive.writestr(zipfile.ZipInfo(MANIFEST, ZIP_TIME), json.dumps(manifest, indent=2) + "\n")
		for entry_path, entry in sorted(assets.items()):
			info = zipfile.ZipInfo(entry_path, ZIP_TIME)
			info.compress_type = zipfile.ZIP_DEFLATED
			archive.writestr(info, entry["_source"].read_bytes())
	return path
