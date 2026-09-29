# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Document branding per brand: logos per product line, footer copy, colour overrides.

Each brand is a folder with ``brand.json`` and its artwork. Phase 1 moves these
values onto ``ilL-Webflow-Brand``; the folder is the seed and the offline source.
"""

import json
import re
from functools import cache
from pathlib import Path

from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import reject_fpo
from illumenate_lighting.illumenate_lighting.api.spec_sheets.tokens import ILLUMENATE_COLORS

BRANDS_DIR = Path(__file__).resolve().parent
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


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


def apply_site_overrides(brand, record):
	"""Merge an ``ilL-Webflow-Brand`` record's Document Branding fields into ``brand``.

	Blank fields keep the app defaults. ``document_branding_json`` may set
	``footer_lines``, ``notice`` and ``colors`` (merged over the app's colour roles);
	each ``document_logos`` row replaces the logo for its product line with an
	uploaded File URL.
	"""
	raw = record.get("document_branding_json")
	if raw:
		values = json.loads(raw) if isinstance(raw, str) else raw
		unknown = set(values) - {"footer_lines", "notice", "colors"}
		if unknown:
			raise ValueError(f"Unknown document branding keys: {', '.join(sorted(unknown))}")
		values = dict(values)
		colors = values.pop("colors", None) or {}
		for role, value in colors.items():
			if role not in ILLUMENATE_COLORS:
				raise ValueError(f"Unknown document colour role {role!r}")
			if not isinstance(value, str) or not HEX_COLOR.match(value):
				raise ValueError(f"Document colour {role!r} must be #rrggbb, not {value!r}")
			reject_fpo(value.encode(), f"document colour {role}")
		brand.update(values)
		brand["colors"] = {**(brand.get("colors") or {}), **colors}
	if record.get("default_document_initials"):
		brand["default_document_initials"] = record["default_document_initials"]
	for row in record.get("document_logos") or []:
		if row.get("spec_line") and row.get("logo"):
			entry = {"file": row["logo"], "source": "ilL-Webflow-Brand"}
			if row.get("is_placeholder"):
				entry["placeholder"] = row.get("placeholder_note") or "Placeholder logo"
			brand["logos"][row["spec_line"]] = entry
	return brand


def logo_for(brand, spec_line):
	entry = brand["logos"].get(spec_line)
	if not entry:
		raise ValueError(f"Brand {brand['brand_code']!r} has no logo for spec line {spec_line!r}")
	return entry
