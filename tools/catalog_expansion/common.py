"""Shared helpers: the live snapshot, catalog assembly and external-link declaration."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "yaml_builder_ui" / "src" / "catalog-schema.json"
TABLES = {"Table", "Table MultiSelect"}
SYSTEM = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
}


class Snapshot:
	"""Records from ``fetch_live`` keyed by DocType, then name."""

	def __init__(self, directory):
		self.directory = Path(directory)
		self._cache = {}

	def all(self, doctype):
		if doctype not in self._cache:
			path = self.directory / f"{doctype}.json"
			rows = json.loads(path.read_text()) if path.exists() else []
			self._cache[doctype] = {row["name"]: row for row in rows}
		return self._cache[doctype]

	def get(self, doctype, name):
		return self.all(doctype).get(name)

	def exists(self, doctype, name):
		return name in self.all(doctype)

	def where(self, doctype, **filters):
		return [row for row in self.all(doctype).values() if all(row.get(k) == v for k, v in filters.items())]


def schema():
	return json.loads(SCHEMA_PATH.read_text())


def clean_child(row, keep=None):
	"""A child row without system fields and empty values, for copying into a new parent."""
	out = {}
	for key, value in row.items():
		if key in SYSTEM or value in (None, "", []):
			continue
		if keep is not None and key not in keep:
			continue
		out[key] = value
	return out


def _identity(doctype, row, meta):
	"""The name a generated record will get, where the schema's autoname makes it knowable."""
	if "name" in row:
		return row["name"]
	autoname = meta.get("autoname") or ""
	if autoname.startswith("field:"):
		return row.get(autoname[6:])
	if autoname.startswith("format:"):
		import re

		return re.sub(r"\{(\w+)\}", lambda m: str(row.get(m.group(1), "")), autoname[7:])
	return None


def declare_externals(records, schema_, snapshot, extra=None):
	"""``external_links`` for every Link/Dynamic Link value the catalog does not create.

	Values the catalog generates are skipped; everything else must already exist on the
	site. Returns (external_links, missing) where missing lists links the snapshot lacks.
	"""
	doctypes = schema_["doctypes"]
	generated = {}
	for doctype, rows in records.items():
		for row in rows:
			name = _identity(doctype, row, doctypes.get(doctype, {}))
			if name:
				generated.setdefault(doctype, set()).add(name)
	external, missing = {}, []

	def visit(doctype, row):
		for field in doctypes.get(doctype, {}).get("fields", []):
			value = row.get(field["fieldname"])
			if value in (None, ""):
				continue
			if field["fieldtype"] in TABLES and isinstance(value, list):
				for child in value:
					visit(field["options"], child)
				continue
			target = None
			if field["fieldtype"] == "Link":
				target = field["options"]
			elif field["fieldtype"] == "Dynamic Link":
				target = row.get(field["options"])
			if not target or value in generated.get(target, ()):
				continue
			external.setdefault(target, set()).add(value)

	for doctype, rows in records.items():
		for row in rows:
			visit(doctype, row)
	for doctype, names in (extra or {}).items():
		external.setdefault(doctype, set()).update(names)
	for doctype, names in external.items():
		for name in names:
			if snapshot.all(doctype) and not snapshot.exists(doctype, name):
				missing.append((doctype, name))
	return {doctype: sorted(names) for doctype, names in sorted(external.items())}, missing


def catalog(product_type, series_name, records, external_links, comment):
	return {
		"_comment": comment,
		"schema_version": 2,
		"product_type": product_type,
		"series_name": series_name,
		"records": {doctype: rows for doctype, rows in records.items() if rows},
		"external_links": external_links,
	}


class _Dumper(yaml.SafeDumper):
	pass


def _str(dumper, value):
	style = (
		"'"
		if value
		and (value[0] in "0123456789" or value.lower() in {"yes", "no", "on", "off", "true", "false"})
		else None
	)
	return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def write_yaml(path, data):
	comment = data.pop("_comment", "")
	text = yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=140)
	header = "".join(f"# {line}\n" if line else "#\n" for line in comment.splitlines())
	Path(path).parent.mkdir(parents=True, exist_ok=True)
	Path(path).write_text(header + text, encoding="utf-8")
