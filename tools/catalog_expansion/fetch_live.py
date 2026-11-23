"""Snapshot the live ERPNext records the catalog expansion reads.

    python -m tools.catalog_expansion.fetch_live --site https://<site> --out <dir>

Writes one ``<DocType>.json`` file per DocType: full records (child tables included) for
the template, spec and relationship DocTypes, and list rows for Item and Item Price.
Authentication is whatever the HTTP client already sends (an API key header or an
authenticating proxy); nothing is written to the site.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

FULL = (
	"ilL-Fixture-Template",
	"ilL-Tape-Neon-Template",
	"ilL-LED-Sheet-Template",
	"ilL-Extrusion-Kit-Template",
	"ilL-Driver-Template",
	"ilL-Controller-Template",
	"ilL-Spec-Profile",
	"ilL-Spec-Lens",
	"ilL-Spec-Accessory",
	"ilL-Spec-LED Tape",
	"ilL-Spec-Driver",
	"ilL-Spec-Controller",
	"ilL-Rel-Profile Lens",
	"ilL-Rel-Tape Offering",
	"ilL-Rel-Endcap-Map",
	"ilL-Rel-Mounting-Accessory-Map",
	"ilL-Rel-Driver-Eligibility",
	"ilL-Rel-Leader-Cable-Map",
	"ilL-Rel-Kit-Profile-Map",
	"ilL-Rel-Kit-Lens-Map",
	"ilL-Rel-Kit-Endcap-Map",
	"ilL-Rel-Kit-Mounting-Map",
	"ilL-Kit-Submittal-Mapping",
	"ilL-Neon-Submittal-Mapping",
	"ilL-Attribute-Series",
	"ilL-Attribute-Finish",
	"ilL-Attribute-Lens Appearance",
	"ilL-Attribute-Mounting Method",
	"ilL-Attribute-LED Package",
)
LISTS = {
	"Item": ["name", "item_name", "item_group", "stock_uom", "disabled", "has_variants", "variant_of"],
	"Item Price": ["name", "item_code", "price_list", "price_list_rate", "uom"],
	"ilL-Spec-Submittal-Mapping": ["*"],
}


def _get(site, path, **params):
	url = site.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
	with urllib.request.urlopen(url, timeout=300) as response:
		return json.load(response)


def _resource(doctype):
	return "/api/resource/" + urllib.parse.quote(doctype)


def snapshot(site, out):
	out = Path(out)
	out.mkdir(parents=True, exist_ok=True)
	for doctype in FULL:
		names = [
			row["name"]
			for row in _get(site, _resource(doctype), fields='["name"]', limit_page_length=0)["data"]
		]
		records = [
			_get(site, _resource(doctype) + "/" + urllib.parse.quote(name, safe=""))["data"] for name in names
		]
		(out / f"{doctype}.json").write_text(json.dumps(records, indent=1, default=str))
		print(doctype, len(records))
	for doctype, fields in LISTS.items():
		rows = _get(site, _resource(doctype), fields=json.dumps(fields), limit_page_length=0)["data"]
		(out / f"{doctype}.json").write_text(json.dumps(rows, indent=1, default=str))
		print(doctype, len(rows))


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--site", required=True)
	parser.add_argument("--out", required=True)
	args = parser.parse_args()
	snapshot(args.site, args.out)
