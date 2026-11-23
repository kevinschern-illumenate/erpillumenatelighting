"""Built-in Catalog Builder starters made from real products.

``templates/starters/*.yaml`` are version 2 catalogs copied from active products (see
``tools/catalog_expansion/starters.py``) and named with code ``DEMO`` and series
``Example Series``. Each carries a ``builder.starter`` block: its id, label, description and
the code, series and product name its records use. This module validates them and writes
``tools/yaml_builder_ui/src/catalog-starters.json`` for the New product dialog:

    python -m tools.fixture_builder.catalog_starters          # validate and write
    python -m tools.fixture_builder.catalog_starters --check  # validate, fail if the JSON is stale
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .catalog_schema import PRODUCTS, ROOT

STARTERS_DIR = Path(__file__).parent / "templates" / "starters"
OUTPUT = ROOT / "tools/yaml_builder_ui/src/catalog-starters.json"


def load_starters(directory=STARTERS_DIR):
	starters = []
	for path in sorted(Path(directory).glob("*.yaml")):
		catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
		meta = dict((catalog.get("builder") or {}).get("starter") or {})
		catalog = {key: value for key, value in catalog.items() if key != "builder"}
		starters.append(
			{
				"id": meta.get("id") or path.stem,
				"label": meta.get("label") or path.stem,
				"description": meta.get("description", ""),
				"product_type": catalog["product_type"],
				"code": meta.get("code", "DEMO"),
				"series": meta.get("series", catalog.get("series_name", "")),
				"name": meta.get("name", ""),
				"catalog": catalog,
			}
		)
	return starters


def problems(starters):
	from .__main__ import validate_config

	issues = []
	seen = set()
	for starter in starters:
		label = starter["id"]
		if starter["id"] in seen:
			issues.append(f"{label}: duplicate starter id")
		seen.add(starter["id"])
		if starter["product_type"] not in PRODUCTS:
			issues.append(f"{label}: unknown product type {starter['product_type']}")
			continue
		text = json.dumps(starter["catalog"]["records"])
		if starter["code"] not in text:
			issues.append(f"{label}: records never use the starter code {starter['code']}")
		issues += [f"{label}: {issue}" for issue in validate_config(starter["catalog"])]
	return issues


def render(starters):
	return json.dumps(starters, indent=1, ensure_ascii=False) + "\n"


def main(check=False):
	starters = load_starters()
	issues = problems(starters)
	if issues:
		raise SystemExit("Starter problems:\n" + "\n".join(f"  - {issue}" for issue in issues))
	text = render(starters)
	if check:
		if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != text:
			raise SystemExit(
				f"{OUTPUT.relative_to(ROOT)} is stale; run python -m tools.fixture_builder.catalog_starters"
			)
		print(f"{len(starters)} starters up to date")
		return
	OUTPUT.write_text(text, encoding="utf-8")
	print(f"Wrote {len(starters)} starters to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--check", action="store_true")
	main(parser.parse_args().check)
