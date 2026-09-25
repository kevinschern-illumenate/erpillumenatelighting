"""Mapping validation shared by authoring preflight and actual filled output."""


def set_value(values, mapping, raw, rendered):
	field = mapping.get("pdf_field_name")
	if not field or field in values:
		raise ValueError(f"PDF field must be mapped exactly once: {field or '(missing)'}")
	if mapping.get("required_value") and (raw is None or str(raw).strip() == ""):
		raise ValueError(
			f"Required engineering value is missing: {mapping.get('source_doctype')}.{mapping.get('source_field')} for {field}"
		)
	values[field] = rendered


def check_mappings(mappings, fields):
	seen, errors = set(), []
	for row in mappings:
		name = row.get("pdf_field_name")
		if not name or name in seen:
			errors.append(f"Map PDF field once: {name or '(missing)'}")
		if name not in fields:
			errors.append(f"PDF template has no field: {name}")
		if not row.get("source_doctype") or not row.get("source_field"):
			errors.append(f"Select the source record and field for {name}")
		seen.add(name)
	if not mappings:
		errors.append("Add field mappings for this template")
	return errors
