"""Product authoring metadata, derived from the app's checked-in DocTypes.

No Frappe runtime is needed. Rebuild the browser snapshot with
``python -m tools.fixture_builder.catalog_schema`` after changing a DocType.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# npm/Vercel also invoke this file directly from outside the repository root.
if __package__ in (None, ""):
	sys.path.insert(0, str(ROOT))

from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import (
	DOCTYPE_ROOT,
	NON_VALUE,
	PRODUCTS,
	_field,
	build_schema,
	standard_doctypes,
)

SNAPSHOT = ROOT / "tools/yaml_builder_ui/src/catalog-schema.json"


def main():
	import argparse

	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--check", action="store_true", help="Fail if the browser schema is stale")
	args = parser.parse_args()
	content = json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"
	if args.check:
		if not SNAPSHOT.exists() or SNAPSHOT.read_text(encoding="utf-8") != content:
			parser.exit(1, "Browser schema is stale; run python -m tools.fixture_builder.catalog_schema\n")
	else:
		SNAPSHOT.write_text(content, encoding="utf-8")


if __name__ == "__main__":
	main()
