"""Write the shared Product Data fields and Product Status into the six template doctypes.

Run from the repository root after editing ``web_listing_schema.py``:

    python tools/stamp_web_listing_fields.py

It also refreshes the YAML builder's doctype snapshot (tools/yaml_builder_ui/src/catalog-schema.json).

Idempotent: everything from the Product Data tab on is replaced, Product Status sits right
after is_active (which becomes read only), the first section is laid out as IDENTITY_LEFT |
IDENTITY_RIGHT, generated fields in PLACED_FIELDS go after their anchors, webflow_product becomes editable while empty,
and a doctype's
``modified`` stamp only moves when its fields actually change, so ``bench migrate``
reloads exactly the doctypes that changed.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	IDENTITY_FIELDS,
	IDENTITY_LEFT,
	IDENTITY_RIGHT,
	IS_ACTIVE_OVERRIDES,
	PLACED_FIELDS,
	STATUS_AFTER,
	STATUS_FIELD,
	TAB,
	TEMPLATE_DOCTYPES,
	WEBFLOW_PRODUCT_FIELD,
	WEBFLOW_PRODUCT_OVERRIDES,
	fields_for,
)

DOCTYPE_DIR = ROOT / "illumenate_lighting" / "illumenate_lighting" / "doctype"
IDENTITY_COLUMN = "identity_column_break"


def _is_break(field):
	return field["fieldtype"] in ("Section Break", "Tab Break")


def arrange_identity(fields):
	"""Lay out the first section: IDENTITY_LEFT, a column break, then IDENTITY_RIGHT and
	every other field of the section in its current order (owner layout, 2026-11-02)."""
	start = next(i for i, field in enumerate(fields) if field["fieldtype"] == "Section Break")
	end = next((i for i in range(start + 1, len(fields)) if _is_break(fields[i])), len(fields))
	section = fields[start + 1 : end]
	columns = [field for field in section if field["fieldtype"] == "Column Break"]
	by_name = {field["fieldname"]: field for field in section if field["fieldtype"] != "Column Break"}
	left = [by_name.pop(name) for name in IDENTITY_LEFT if name in by_name]
	right = [by_name.pop(name) for name in IDENTITY_RIGHT if name in by_name]
	right += [field for field in section if field["fieldname"] in by_name]
	column = columns[0] if columns else {"fieldname": IDENTITY_COLUMN, "fieldtype": "Column Break"}
	return fields[: start + 1] + left + [column] + right + fields[end:]


def stamp(doctype, module, now):
	path = DOCTYPE_DIR / module / f"{module}.json"
	data = json.loads(path.read_text(encoding="utf-8"))
	added = fields_for(doctype)
	placed = PLACED_FIELDS[doctype]
	names = {field["fieldname"] for field in added}
	# The Product Data tab is always last, so everything from it on is replaced wholesale;
	# fields dropped from the definition disappear with it.
	existing = data["fields"]
	tab = next((i for i, field in enumerate(existing) if field["fieldname"] == TAB), len(existing))
	names.add(STATUS_FIELD["fieldname"])
	names.update(field["fieldname"] for field in IDENTITY_FIELDS)
	names.update(field["fieldname"] for field, _anchor in placed)
	fields = []
	for field in existing[:tab]:
		if field["fieldname"] in names:
			continue
		if field["fieldname"] == STATUS_AFTER:
			fields += [{**field, **IS_ACTIVE_OVERRIDES}, dict(STATUS_FIELD)]
		elif field["fieldname"] == WEBFLOW_PRODUCT_FIELD:
			fields.append({**field, **WEBFLOW_PRODUCT_OVERRIDES})
		else:
			fields.append(field)
	# Identity fields join the first section, which is then laid out by arrange_identity.
	first_break = next((i for i, field in enumerate(fields) if i and _is_break(field)), len(fields))
	fields[first_break:first_break] = [dict(field) for field in IDENTITY_FIELDS]
	fields = arrange_identity(fields)
	# Generated fields kept above the tab go right after their anchor.
	for field, anchor in placed:
		at = next(i for i, existing_field in enumerate(fields) if existing_field["fieldname"] == anchor)
		fields.insert(at + 1, dict(field))
	fields += [dict(field) for field in added]
	if fields == data["fields"]:
		return False
	data["fields"] = fields
	data["field_order"] = [field["fieldname"] for field in fields]
	data["modified"] = now
	path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
	return True


def main():
	now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.000000")
	for doctype, module in TEMPLATE_DOCTYPES.items():
		print(f"{doctype}: {'updated' if stamp(doctype, module, now) else 'unchanged'}")
	# The YAML builder ships a snapshot of these doctypes; CI and the Vercel build fail
	# when it is stale, so refresh it with every stamp.
	from tools.fixture_builder.catalog_schema import SNAPSHOT, build_schema

	SNAPSHOT.write_text(json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
	print(f"{SNAPSHOT.relative_to(ROOT)}: refreshed")


if __name__ == "__main__":
	main()
