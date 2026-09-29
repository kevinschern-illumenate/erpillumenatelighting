"""One immutability rule for pinned configured builds, independent of Frappe save bookkeeping."""

import frappe

# Frappe restamps these on every child row during save (``set_user_and_timestamp``),
# so they must not count as a change to an immutable build.
ROW_BOOKKEEPING = frozenset(
	("name", "owner", "creation", "modified", "modified_by", "parent", "parenttype", "parentfield", "doctype")
)
LAYOUT_FIELDTYPES = frozenset(("Section Break", "Column Break", "Tab Break"))
TABLE_FIELDTYPES = frozenset(("Table", "Table MultiSelect"))


def build_value(doc, field):
	"""Serialize a field's build content for comparison with its stored version."""
	value = doc.get(field.fieldname)
	if field.fieldtype in TABLE_FIELDTYPES:
		value = [
			{
				key: val
				for key, val in (row.as_dict() if hasattr(row, "as_dict") else dict(row)).items()
				if key not in ROW_BOOKKEEPING and not key.startswith("__")
			}
			for row in value or []
		]
	return frappe.as_json(value)


def changed_fields(doc, old, mutable):
	"""Return the build fields of ``doc`` whose content differs from ``old``."""
	return [
		field.fieldname
		for field in doc.meta.fields
		if field.fieldtype not in LAYOUT_FIELDTYPES
		and field.fieldname not in mutable
		# Frappe re-fetches fetch_from fields from the linked record on every save;
		# they mirror that record, not this build's content.
		and not field.get("fetch_from")
		and build_value(doc, field) != build_value(old, field)
	]


def assert_unchanged(doc, old, mutable, message):
	"""Reject a save that changes pinned build content outside ``mutable`` links."""
	changed = changed_fields(doc, old, mutable)
	if changed:
		frappe.throw(f"{message} (changed: {', '.join(changed)})")
