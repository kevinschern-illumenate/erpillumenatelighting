"""Build the YAML builder's reference of records that already exist in ERPNext.

Input is ERPNext's DocType export (Menu → Export, "Data Import Template" CSVs),
as individual files, a folder, or the zip of all of them. Output is the snapshot
``tools/yaml_builder_ui/src/erp-reference.json``. The browser editor and the CLI
both treat a link that names a reference record as an existing ERPNext record,
so a new fixture family can point at existing LED tape specs, attributes and Items
instead of re-creating them.

    python -m tools.fixture_builder.erp_reference DocType_Exports.zip

Only fields in the current DocType metadata are kept. Audit fields (owner,
creation, modified), Webflow sync state, prices and costs, and fields removed from
the DocType are dropped; Webflow Products keep only their short summary fields. Records that exported records link to (Items, UOMs, Item Groups, ...)
are listed as existing too, because ERPNext only saves a link to a real record.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path

from .catalog_schema import ROOT, build_schema

REFERENCE = ROOT / "tools/yaml_builder_ui/src/erp-reference.json"
TABLES = {"Table", "Table MultiSelect"}
SKIPPED_CHILDREN = {"ilL-Child-Webflow-Sync-State"}
# Prices and costs stay in ERPNext; the builder is a static site and only needs links.
SKIPPED_TYPES = {"Currency"}
# Large records that are referenced by name: keep short identifying fields only.
SUMMARY_ONLY = {"ilL-Webflow-Product"}
SHORT_TYPES = {"Data", "Link", "Dynamic Link", "Select", "Int", "Float", "Check"}
# Frappe prefixes cells that begin like spreadsheet formulas with an apostrophe.
FORMULA_START = ("'-", "'+", "'=", "'@")


def _rows(text):
	return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


def _cell(value):
	value = value.strip()
	if len(value) >= 2 and value[0] == value[-1] == '"':
		value = value[1:-1]  # The ID column is exported with an extra pair of quotes.
	if value.startswith(FORMULA_START):
		value = value[1:]
	return value


def _typed(field, raw):
	"""Convert a CSV cell to its YAML builder value, or None when it is empty."""
	value = _cell(raw)
	if value == "":
		return None
	kind = field["fieldtype"]
	try:
		if kind in {"Int", "Check"}:
			return int(float(value))
		if kind in {"Float", "Currency", "Percent"}:
			return float(value)
	except ValueError:
		return value  # Keep the exported text; catalog validation will flag it.
	return value


def parse_export(text, schema):
	"""Return ``(doctype, records)`` from one legacy Data Import Template export.

	Columns are split into the parent section and one section per child table,
	separated by ``~``. A row with a blank parent ID continues the record above it.
	"""
	rows = _rows(text)
	marker = {row[0]: row for row in rows if row and row[0] in {"DocType:", "Column Name:"}}
	if not rows or rows[0][:1] != ["Data Import Template"] or len(marker) != 2:
		raise ValueError("not an ERPNext Data Import Template export")
	doctype = marker["DocType:"][1]
	meta = schema["doctypes"].get(doctype)
	if not meta or meta.get("istable"):
		raise ValueError(f"{doctype} is not an authorable DocType in this repository")
	names, kinds = marker["Column Name:"], marker["DocType:"]
	sections, current = [], {"table": None, "doctype": doctype, "columns": []}
	for i, column in enumerate(names[1:], 1):
		if column == "~":
			sections.append(current)
			current = {"table": kinds[i + 2], "doctype": kinds[i + 1], "columns": []}
		else:
			current["columns"].append((i, column))
	sections.append(current)
	parent_fields = {field["fieldname"]: field for field in meta["fields"]}
	start = next(i for i, row in enumerate(rows) if row[:1] == ["Start entering data below this line"])
	records, record = [], None
	for row in rows[start + 1 :]:
		row = row + [""] * (len(names) - len(row))
		for section in sections:
			values = {column: row[i] for i, column in section["columns"]}
			if section["table"] is None:
				if _cell(values.get("name", "")):
					record = {"name": _cell(values["name"])}
					records.append(record)
					fields = parent_fields
				else:
					continue
			else:
				field = parent_fields.get(section["table"])
				if (
					record is None
					or doctype in SUMMARY_ONLY
					or not field
					or field["fieldtype"] not in TABLES
					or section["doctype"] in SKIPPED_CHILDREN
					or not any(_cell(v) for k, v in values.items() if k != "name")
				):
					continue
				child = {}
				record.setdefault(section["table"], []).append(child)
				fields = {f["fieldname"]: f for f in schema["doctypes"][field["options"]]["fields"]}
			target = record if section["table"] is None else child
			for column, raw in values.items():
				field = fields.get(column)
				if not field or field["fieldtype"] in TABLES | SKIPPED_TYPES:
					continue
				if doctype in SUMMARY_ONLY and field["fieldtype"] not in SHORT_TYPES:
					continue
				value = _typed(field, raw)
				if value is not None:
					target[column] = value
	return doctype, records


def _sources(paths):
	for path in map(Path, paths):
		if path.is_dir():
			for child in sorted(path.glob("*.csv")):
				yield child.name, child.read_text(encoding="utf-8-sig")
		elif path.suffix.lower() == ".zip":
			with zipfile.ZipFile(path) as archive:
				for info in sorted(archive.infolist(), key=lambda item: item.filename):
					if info.filename.lower().endswith(".csv") and not info.is_dir():
						yield info.filename, archive.read(info).decode("utf-8-sig")
		else:
			yield path.name, path.read_text(encoding="utf-8-sig")


def _linked(doctype, record, schema):
	for field in schema["doctypes"][doctype]["fields"]:
		value = record.get(field["fieldname"])
		if value in (None, ""):
			continue
		if field["fieldtype"] in TABLES:
			for child in value:
				yield from _linked(field["options"], child, schema)
		elif field["fieldtype"] in {"Link", "Dynamic Link"}:
			target = field["options"] if field["fieldtype"] == "Link" else record.get(field["options"])
			if target and target != "DocType":
				yield target, str(value)


def build_reference(paths, schema=None, exported_on=None):
	schema = schema or build_schema()
	doctypes, skipped = {}, []
	for filename, text in _sources(paths):
		try:
			doctype, records = parse_export(text, schema)
		except ValueError as error:
			skipped.append(f"{filename}: {error}")
			continue
		if doctype in doctypes:
			raise ValueError(f"{filename}: {doctype} was exported more than once; keep only the newest file")
		doctypes[doctype] = {
			"source": "export",
			"records": {record.pop("name"): record for record in sorted(records, key=lambda r: r["name"])},
		}
	exported = list(doctypes.items())
	for doctype, entry in exported:
		for record in entry["records"].values():
			for target, name in _linked(doctype, record, schema):
				if target not in doctypes:
					doctypes[target] = {"source": "links", "records": {}}
				if doctypes[target]["source"] == "links":
					doctypes[target]["records"].setdefault(name, {})
	for entry in doctypes.values():
		entry["records"] = dict(sorted(entry["records"].items()))
	reference = {
		"schema_version": 1,
		"exported_on": exported_on or date.today().isoformat(),
		"doctypes": dict(sorted(doctypes.items())),
	}
	return reference, skipped


def load_reference(path=REFERENCE):
	"""Return ``{doctype: set(names)}`` from a reference snapshot."""
	data = json.loads(Path(path).read_text(encoding="utf-8"))
	return {doctype: set(entry["records"]) for doctype, entry in data["doctypes"].items()}


def unconfirmed_links(config, path=REFERENCE):
	"""Declared external links that a fully exported DocType does not contain.

	DocTypes known only from links (such as Item) are partial lists, so they are
	not checked. A miss can be a typo or a record created after the export.
	"""
	data = json.loads(Path(path).read_text(encoding="utf-8"))["doctypes"]
	return [
		(doctype, name)
		for doctype, names in (config.get("external_links") or {}).items()
		if data.get(doctype, {}).get("source") == "export"
		for name in names
		if name not in data[doctype]["records"]
	]


def main():
	parser = argparse.ArgumentParser(
		description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
	)
	parser.add_argument("exports", nargs="+", help="ERPNext DocType export CSVs, folders, or zip files")
	parser.add_argument("--output", default=str(REFERENCE), help="Reference JSON to write")
	parser.add_argument("--exported-on", help="Export date (YYYY-MM-DD); defaults to today")
	args = parser.parse_args()
	reference, skipped = build_reference(args.exports, exported_on=args.exported_on)
	Path(args.output).write_text(json.dumps(reference, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
	for doctype, entry in reference["doctypes"].items():
		print(
			f"{len(entry['records']):5d}  {doctype}{'  (linked from exports)' if entry['source'] == 'links' else ''}"
		)
	for line in skipped:
		print(f"skipped {line}")


if __name__ == "__main__":
	main()
