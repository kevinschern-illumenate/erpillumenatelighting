# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Document branding per brand: logos per product line, footer copy, colour overrides.

Each brand is a folder with ``brand.json`` and its artwork. Phase 1 moves these
values onto ``ilL-Webflow-Brand``; the folder is the seed and the offline source.
"""

import json
from functools import cache
from pathlib import Path

BRANDS_DIR = Path(__file__).resolve().parent


@cache
def _load(code):
	path = BRANDS_DIR / code / "brand.json"
	if not path.is_file():
		raise ValueError(f"Unknown document brand {code!r}")
	return json.loads(path.read_text(encoding="utf-8"))


def load_brand(code, overrides=None):
	"""Brand settings with per-document ``overrides`` (never the logos table)."""
	brand = json.loads(json.dumps(_load(code)))
	brand.update(
		{key: value for key, value in (overrides or {}).items() if key not in ("brand_code", "logos")}
	)
	brand["root"] = BRANDS_DIR / code
	return brand


def logo_for(brand, spec_line):
	entry = brand["logos"].get(spec_line)
	if not entry:
		raise ValueError(f"Brand {brand['brand_code']!r} has no logo for spec line {spec_line!r}")
	return entry
