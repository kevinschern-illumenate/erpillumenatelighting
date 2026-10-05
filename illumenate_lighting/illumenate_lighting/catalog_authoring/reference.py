"""Reduce ERPNext records to the catalog authoring reference contract."""

TABLES = {"Table", "Table MultiSelect"}
# Supplier names and part numbers, like prices and costs, stay in ERPNext; the
# builder is a static site and only needs links.
SKIPPED_CHILDREN = {"ilL-Child-Webflow-Sync-State", "Item Supplier"}
SKIPPED_TYPES = {"Currency"}
# Large records that are referenced by name: keep short identifying fields only.
SUMMARY_ONLY = {"ilL-Webflow-Product"}
SHORT_TYPES = {"Data", "Link", "Dynamic Link", "Select", "Int", "Float", "Check"}


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


def catalog_key(config):
	"""Identify a catalog across builds: its product type and series name."""
	return f"{config.get('product_type', '')}/{config.get('series_name', '')}"


def reference_record(doctype, record, schema):
	"""Keep what an export would: current fields and child rows, without prices."""
	fields = {field["fieldname"]: field for field in schema["doctypes"][doctype]["fields"]}
	result = {}
	for key, value in record.items():
		field = fields.get(key)
		if not field or value in (None, "", []) or field["fieldtype"] in SKIPPED_TYPES:
			continue
		if field["fieldtype"] in TABLES:
			if doctype in SUMMARY_ONLY or field["options"] in SKIPPED_CHILDREN or not isinstance(value, list):
				continue
			rows = [reference_record(field["options"], row, schema) for row in value if isinstance(row, dict)]
			if any(rows):
				result[key] = [row for row in rows if row]
		elif doctype not in SUMMARY_ONLY or field["fieldtype"] in SHORT_TYPES:
			result[key] = value
	return result
