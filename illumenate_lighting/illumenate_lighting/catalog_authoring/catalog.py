"""Validate version 2 product YAML and export ordered ERPNext Data Import CSVs."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from copy import deepcopy

from ..api.authoring_contract import record_issues
from .schema import PRODUCTS, build_schema

TABLES = {"Table", "Table MultiSelect"}
NUMBERS = {"Int", "Float", "Currency", "Percent"}
CONFIGURATION_TABLES = {
	"ilL-Fixture-Template": "allowed_tape_offerings",
	"ilL-Tape-Neon-Template": "allowed_tape_specs",
	"ilL-LED-Sheet-Template": "allowed_specs",
	"ilL-Driver-Template": "variants",
	"ilL-Controller-Template": "variants",
}
WEBFLOW_TEMPLATES = {
	"Fixture Template": ("fixture_template", "ilL-Fixture-Template"),
	"LED Tape": ("tape_neon_template", "ilL-Tape-Neon-Template"),
	"LED Neon": ("tape_neon_template", "ilL-Tape-Neon-Template"),
	"LED Sheet": ("led_sheet_template", "ilL-LED-Sheet-Template"),
	"Driver": ("driver_template", "ilL-Driver-Template"),
	"Controller": ("controller_template", "ilL-Controller-Template"),
}
AXES = {
	"ilL-Driver-Template": {
		"Wattage": "wattage",
		"Voltage Output": "voltage_output",
		"Input Protocol": "input_protocol",
		"Output Protocol": "output_protocol",
	},
	"ilL-Controller-Template": {
		"Controller Type": "controller_type",
		"Channels": "channels",
		"Zones": "zones",
		"Input Protocol": "input_protocol",
		"Output Protocol": "output_protocol",
		"Wireless Protocol": "wireless_protocol",
		"Mounting Type": "mounting_type",
	},
}


def identity(doctype, record, schema):
	autoname = schema["doctypes"][doctype].get("autoname", "")
	if autoname.startswith("field:"):
		return str(record.get(autoname[6:]) or "")
	if autoname.startswith("format:"):
		return re.sub(r"\{([^}]+)\}", lambda m: str(record.get(m[1]) or ""), autoname[7:])
	return str(record.get("name") or "")


def with_defaults(doctype, record, schema):
	result = deepcopy(record)
	for field in schema["doctypes"][doctype]["fields"]:
		key, kind = field["fieldname"], field["fieldtype"]
		if key not in result and "default" in field and not field.get("read_only"):
			value = field["default"]
			if kind in NUMBERS | {"Check"}:
				try:
					value = float(value) if kind not in {"Int", "Check"} else int(value)
				except (ValueError, TypeError):
					continue  # Runtime defaults such as Today are not guessed offline.
			result[key] = value
		if kind in TABLES and isinstance(result.get(key), list):
			result[key] = [
				with_defaults(field["options"], row, schema) if isinstance(row, dict) else row
				for row in result[key]
			]
	return result


def _record_errors(doctype, record, schema, path):
	if not isinstance(record, dict):
		return [f"{path}: expected a record mapping"]
	fields = {f["fieldname"]: f for f in schema["doctypes"][doctype]["fields"]}
	errors = [f"{path}.{key}: unknown field" for key in record if key not in fields and key != "name"]
	for key, field in fields.items():
		value, kind = record.get(key), field["fieldtype"]
		if value is None or value == "" or value == []:
			if field.get("reqd"):
				errors.append(f"{path}.{key}: required")
			continue
		if kind in TABLES:
			if not isinstance(value, list):
				errors.append(f"{path}.{key}: expected a list of child records")
			else:
				for i, row in enumerate(value):
					errors.extend(_record_errors(field["options"], row, schema, f"{path}.{key}[{i}]"))
		elif kind in NUMBERS:
			if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
				errors.append(f"{path}.{key}: expected a finite number")
			elif kind == "Int" and value != int(value):
				errors.append(f"{path}.{key}: expected a whole number")
		elif kind == "Check":
			if value not in (True, False, 0, 1):
				errors.append(f"{path}.{key}: expected a boolean or 0/1")
		elif kind == "JSON":
			try:
				json.loads(value) if isinstance(value, str) else json.dumps(value, allow_nan=False)
			except (ValueError, TypeError):
				errors.append(f"{path}.{key}: invalid JSON")
		elif not isinstance(value, str):
			errors.append(f"{path}.{key}: expected text (quote numeric attribute names in YAML)")
		elif kind == "Select" and value not in field.get("options", "").split("\n"):
			errors.append(f"{path}.{key}: unsupported choice {value!r}")
	if not errors:
		errors.extend(f"{path}.{row['field']}: {row['message']}" for row in record_issues(doctype, record))
		errors.extend(_configuration_errors(doctype, record, path))
	return errors


def _configuration_errors(doctype, record, path):
	errors = []
	choices = CONFIGURATION_TABLES.get(doctype)
	if (
		choices
		and record.get("is_active", 1)
		and not any(row.get("is_active", 1) for row in record.get(choices, []))
	):
		errors.append(f"{path}.{choices}: at least one active compatible specification is required")
	if doctype == "ilL-Webflow-Product" and record.get("is_configurable"):
		info = WEBFLOW_TEMPLATES.get(record.get("product_type"))
		if info and not record.get(info[0]):
			errors.append(f"{path}.{info[0]}: select the matching product template")
	return errors


def links(doctype, record, schema, path=""):
	"""Yield static and dynamic links, including all child tables."""
	for field in schema["doctypes"][doctype]["fields"]:
		key, kind = field["fieldname"], field["fieldtype"]
		value = record.get(key)
		if value in (None, ""):
			continue
		if kind in TABLES:
			for i, row in enumerate(value):
				yield from links(field["options"], row, schema, f"{path}{key}[{i}].")
		elif kind in {"Link", "Dynamic Link"}:
			target = field.get("options") if kind == "Link" else record.get(field.get("options"))
			if target != "DocType":
				yield target, str(value), path + key


def _axis_value(value):
	try:
		return f"{float(value):g}"
	except (ValueError, TypeError):
		return str(value or "").strip()


def _variant_errors(doctype, record, path):
	"""Match the active axes used by the driver/controller configurator."""
	axes = AXES.get(doctype)
	if not axes:
		return []
	errors, choices = [], defaultdict(set)
	for option in record.get("allowed_options", []):
		kind = option.get("option_type")
		value = (
			option.get("option_value")
			if kind in {"Wattage", "Channels", "Zones", "Wireless Protocol"}
			else option.get("attribute_link")
		)
		if value in (None, ""):
			errors.append(f"{path}.allowed_options: {kind} requires an option value or attribute link")
		elif option.get("is_active", 1):
			if kind not in axes:
				errors.append(f"{path}.allowed_options: {kind} is not a configurable axis for {doctype}")
			choices[kind].add(_axis_value(value))
	active = [row for row in record.get("variants", []) if row.get("is_active", 1)]
	if not active:
		errors.append(f"{path}.variants: at least one active orderable variant is required")
	if sum(bool(row.get("is_default")) for row in record.get("variants", [])) > 1:
		errors.append(f"{path}.variants: only one default variant is allowed")
	seen = set()
	for row in active:
		key = tuple(_axis_value(row.get(axes[kind])) for kind in choices if kind in axes)
		if key in seen:
			errors.append(f"{path}.variants: ambiguous variants for the exposed configuration choices")
		seen.add(key)
		for kind, values in choices.items():
			if kind in axes and _axis_value(row.get(axes[kind])) not in values:
				errors.append(f"{path}.variants: {kind} is missing from allowed options")
	for kind, values in choices.items():
		if kind in axes and values - {_axis_value(row.get(axes[kind])) for row in active}:
			errors.append(f"{path}.allowed_options: {kind} includes choices with no active variant")
	return errors


def prepare_catalog(config, schema=None, reference=None):
	"""Return normalized records, ordered import batches, and explicit dependencies.

	Fail before writing any output when data is malformed or links are unresolved.
	External links must be declared or appear in ``reference`` ({DocType: names}
	from an ERPNext export); a typo is never assumed to exist. A record that the
	reference already holds is rejected, because Insert New Records would fail.
	"""
	schema = schema or build_schema()
	reference = reference or {}
	errors = []
	if not isinstance(config, dict):
		raise ValueError("Catalog must be a mapping")
	for key in config:
		if key not in {
			"schema_version",
			"product_type",
			"series_name",
			"records",
			"external_links",
			"add_to_reference",
		}:
			errors.append(f"Unknown catalog key: {key}")
	if config.get("add_to_reference") not in (None, True, False):
		errors.append("add_to_reference must be true or false")
	if config.get("add_to_reference") and not str(config.get("series_name") or "").strip():
		errors.append("series_name is required to add the catalog to the ERPNext reference")
	if config.get("schema_version") != 2:
		errors.append("schema_version must be 2")
	if config.get("product_type") not in PRODUCTS:
		errors.append("Unsupported product_type")
	raw = config.get("records")
	if not isinstance(raw, dict) or not raw:
		raise ValueError("records must contain DocType names mapped to lists of records")
	external = config.get("external_links", {})
	if not isinstance(external, dict) or any(
		not isinstance(v, list) or any(not isinstance(s, str) or not s for s in v) for v in external.values()
	):
		raise ValueError("external_links must map DocType names to lists of existing record names")
	records, nodes, names = {}, {}, {}
	for doctype, rows in raw.items():
		meta = schema["doctypes"].get(doctype)
		if not meta or meta.get("istable"):
			errors.append(f"{doctype}: not an authorable parent DocType")
			continue
		if not isinstance(rows, list):
			errors.append(f"{doctype}: expected a list of records")
			continue
		records[doctype] = []
		for i, row in enumerate(rows):
			path = f"{doctype}[{i}]"
			row = with_defaults(doctype, row, schema) if isinstance(row, dict) else row
			issues = _record_errors(doctype, row, schema, path)
			errors.extend(issues)
			if issues:
				continue
			name = identity(doctype, row, schema)
			if not name and (
				meta.get("autoname", "").startswith("field:") or meta.get("autoname") == "prompt"
			):
				errors.append(f"{path}: a record name is required by {meta['autoname']}")
			if name and (doctype, name) in names:
				errors.append(f"{path}: duplicate record {name}")
			if name in reference.get(doctype, ()):
				errors.append(
					f"{path}: {name} already exists in ERPNext; remove this record and link to the existing one"
				)
			node = (doctype, i)
			if name:
				names[doctype, name] = node
			nodes[node] = row
			records[doctype].append(row)
			errors.extend(_variant_errors(doctype, row, path))
	product = PRODUCTS.get(config.get("product_type"))
	if product and not records.get(product["template"]):
		errors.append(f"At least one {product['template']} record is required")
	if errors:
		raise ValueError("\n".join(errors))
	dependencies = {}
	used_external = set()
	for node, row in nodes.items():
		dependencies[node] = set()
		for target, value, field in links(node[0], row, schema):
			if (target, value) in names:
				dependencies[node].add(names[target, value])
			elif value in external.get(target, []) or value in reference.get(target, ()):
				used_external.add((target, value))
			else:
				errors.append(
					f"{node[0]}[{node[1]}].{field}: unresolved {target or 'Dynamic Link DocType'} / {value}; add the record or declare an external link"
				)
	if errors:
		raise ValueError("\n".join(errors))
	batches = []
	while dependencies:
		ready = [node for node, deps in dependencies.items() if not deps]
		if not ready:
			raise ValueError(
				"Circular import links: "
				+ ", ".join(sorted({node[0] for node in dependencies}))
				+ ". Remove optional reverse links (such as template.webflow_product), import, then set them in ERPNext."
			)
		groups = defaultdict(list)
		for node in ready:
			groups[node[0]].append(nodes[node])
			del dependencies[node]
		batches.extend(groups.items())
		for deps in dependencies.values():
			deps.difference_update(ready)
	return records, batches, sorted(used_external)


def csv_data(doctype, records, schema):
	"""Frappe label headers and aligned child continuation rows, in metadata order."""
	meta = schema["doctypes"][doctype]
	columns = []
	if any("name" in row for row in records):
		columns.append((None, "name", "ID"))
	for field in meta["fields"]:
		key = field["fieldname"]
		if field["fieldtype"] in TABLES:
			children = [child for row in records for child in row.get(key, [])]
			for child_field in schema["doctypes"][field["options"]]["fields"]:
				child_key = child_field["fieldname"]
				if any(child_key in child for child in children):
					# A site's custom field label is unknown offline; Frappe also matches table.fieldname.
					label = (
						f"{key}.{child_key}"
						if child_key.startswith("custom_")
						else f"{child_field.get('label', child_key)} ({field.get('label', key)})"
					)
					columns.append((key, child_key, label))
		elif any(key in row for row in records):
			columns.append((None, key, key if key.startswith("custom_") else field.get("label", key)))
	headers = []
	for parent, key, label in columns:
		headers.append((f"{parent}.{key}" if parent else key) if label in headers else label)
	rows = []
	for record in records:
		count = max([1] + [len(record.get(parent, [])) for parent, _, _ in columns if parent])
		for i in range(count):
			row = []
			for parent, key, _ in columns:
				if parent:
					children = record.get(parent, [])
					value = children[i].get(key, "") if i < len(children) else ""
				else:
					value = record.get(key, "") if i == 0 else ""
				if isinstance(value, bool):
					value = int(value)
				elif isinstance(value, (dict, list)):
					value = json.dumps(value, ensure_ascii=False)
				row.append(value)
			rows.append(row)
	return headers, rows
