"""Write the shared Web Listing fields into the six product template doctypes.

Run from the repository root after editing ``web_listing_schema.py``:

    python tools/stamp_web_listing_fields.py

Idempotent: fields it added before are replaced in place, and a doctype's
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
	TEMPLATE_DOCTYPES,
	fields_for,
)

DOCTYPE_DIR = ROOT / "illumenate_lighting" / "illumenate_lighting" / "doctype"


def stamp(doctype, module, now):
	path = DOCTYPE_DIR / module / f"{module}.json"
	data = json.loads(path.read_text(encoding="utf-8"))
	added = fields_for(doctype)
	names = {field["fieldname"] for field in added}
	fields = [field for field in data["fields"] if field["fieldname"] not in names] + [
		dict(field) for field in added
	]
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


if __name__ == "__main__":
	main()
