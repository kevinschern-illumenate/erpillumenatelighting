"""Catalog Builder starters made from real products on the site.

    python -m tools.catalog_expansion.starters --snapshot <fetch_live dir>

Each starter is a complete product family copied from an active product (its Items, specs,
relationships, templates and submittal mappings) and renamed to the built-in starter
convention: product code ``DEMO``, series ``Example Series``. The Catalog Builder's New
product dialog rewrites those for the new product, so a starter carries real engineering
values, option sets and field mappings to review rather than placeholders.

Writes ``tools/fixture_builder/templates/starters/<id>.yaml``; run
``python -m tools.fixture_builder.catalog_starters`` afterwards to refresh the builder's
``catalog-starters.json``.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from .common import SYSTEM, Snapshot, declare_externals, schema, write_yaml

OUT = Path(__file__).resolve().parents[1] / "fixture_builder" / "templates" / "starters"
SERIES = "Example Series"
CODE = "DEMO"

# Records that belong to a starter's family, found from its templates: forward links whose
# target name carries a family token, and these relationship DocTypes pointing back at them.
REVERSE = {
	"ilL-Rel-Endcap-Map": ("fixture_template",),
	"ilL-Rel-Mounting-Accessory-Map": ("fixture_template",),
	"ilL-Rel-Driver-Eligibility": ("fixture_template",),
	"ilL-Spec-Submittal-Mapping": ("fixture_template",),
	"ilL-Neon-Submittal-Mapping": ("tape_neon_template",),
	"ilL-Rel-Profile Lens": ("profile_spec",),
	"ilL-Rel-Tape Offering": ("tape_spec",),
	"ilL-Rel-Leader-Cable-Map": ("tape_spec",),
	"ilL-Rel-Kit-Profile-Map": ("kit_template",),
	"ilL-Rel-Kit-Lens-Map": ("kit_template",),
	"ilL-Rel-Kit-Endcap-Map": ("kit_template",),
	"ilL-Rel-Kit-Mounting-Map": ("kit_template",),
}
# Family members found by their family field: every finish's profile, every lens and accessory.
FAMILY = {"ilL-Spec-Profile": "family", "ilL-Spec-Lens": "family", "ilL-Spec-Accessory": "profile_family"}
# Specs named by their Item: an included Item brings its spec.
ITEM_SPECS = (
	"ilL-Spec-Profile",
	"ilL-Spec-Lens",
	"ilL-Spec-Accessory",
	"ilL-Spec-LED Tape",
	"ilL-Spec-Driver",
	"ilL-Spec-Controller",
)
# Fields that never carry over: site files, publication links and computed copies.
DROP = {
	"webflow_product",
	"spec_sheet",
	"spec_submittal_template",
	"photometry",
	"image",
	"hero_image",
	"hero_image_alt",
	"dimensions_image",
	"component_image",
	"cross_section_json",
	"photometric_data",
	"colorimetry",
	"spec_gallery",
	"other_documents",
	"target_brands",
	"delivered_lumens",
	"output_options",
	"part_number_builder",
	"notes",
	"spec_sheet_public_url",
	"sync_status",
	"webflow_item_id",
}
ATTACH = {"Attach", "Attach Image"}

STARTERS = [
	dict(
		id="fixture-family",
		product_type="fixture",
		label="Linear fixture family: profile, lens, endcaps, clips and 4 LED packages",
		description="A complete new profile family (from Castle [SF]): profile, lens, endcap and clip Items with specs, the "
		"profile-lens relationship, Static White / Dim to Warm / Tunable White / Full Spectrum templates with tape offerings, "
		"endcap, mounting and driver maps, and the 30 spec submittal fields.",
		roots=("ilL-Fixture-Template", ["ILL-CA01-SW", "ILL-CA01-DW", "ILL-CA01-TW", "ILL-CA01-FS"]),
		tokens={"CA01": CODE, "CAXX": CODE + "XX"},
		series="Castle",
		series_text=True,
		name="Castle [SF]",
	),
	dict(
		id="fixture-packages",
		product_type="fixture",
		label="LED packages for an existing profile family",
		description="Four fixture templates (SW, DW, TW, FS) with endcap, mounting, driver and submittal maps that link the "
		"family's existing profile, lens, endcap and clip records. Enter the existing family code (e.g. CA02) as the product "
		"code; its CH-/LNS-/EC-/ACC- records are linked, not created.",
		roots=("ilL-Fixture-Template", ["ILL-CA01-SW", "ILL-CA01-DW", "ILL-CA01-TW", "ILL-CA01-FS"]),
		tokens={"CA01": CODE, "CAXX": CODE + "XX"},
		series="Castle",
		series_text=True,
		name="Castle [SF]",
		external_only=(
			"Item",
			"ilL-Spec-Profile",
			"ilL-Spec-Lens",
			"ilL-Spec-Accessory",
			"ilL-Rel-Profile Lens",
		),
	),
	dict(
		id="extrusion-kit",
		product_type="extrusion-kit",
		label="Extrusion kit: profile, lens, endcaps and clips",
		description="A sold-as-a-kit extrusion (from Castle [SF]): components with specs, kit components and quantities, "
		"allowed options, the four kit maps and the part number configurator.",
		roots=("ilL-Extrusion-Kit-Template", ["KIT-CA01"]),
		tokens={"CA01": CODE, "CAXX": CODE + "XX"},
		series="Castle",
		series_text=True,
		name="Castle [SF]",
	),
	dict(
		id="tape-static-white",
		product_type="tape",
		label="Static white tape: Dry / Damp / Wet x 4 CCTs",
		description="A static white tape family (from High CRI COB tape): one spec, offering and leader-cable map per "
		"environment rating and CCT, the template with environment adders, driver eligibility and submittal fields.",
		roots=("ilL-Tape-Neon-Template", ["cob-hd-sw"]),
		tokens={"HD": CODE},
		series="COB Tape",
		name="High CRI Static White COB Tape",
	),
	dict(
		id="tape-tunable-white",
		product_type="tape",
		label="Tunable white tape: 2-channel, Dry / Damp / Wet",
		description="A two-channel tunable white tape family (from Standard Tunable White COB tape) with its specs, "
		"offerings, leader cables, template, multichannel driver eligibility and submittal fields.",
		roots=("ilL-Tape-Neon-Template", ["cob-sd-tw"]),
		tokens={"SD": CODE},
		series="COB Tape",
		name="Standard Tunable White COB Tape",
	),
	dict(
		id="neon-static-white",
		product_type="neon",
		label="Static white LED neon: IP67, 4 CCTs x 2 outputs",
		description="An LED neon family (from Pinnacle [DB]): specs, offerings and leader cables per CCT and output, the "
		"template with IP ratings, feed directions and finish, driver eligibility and neon submittal fields.",
		roots=("ilL-Tape-Neon-Template", ["non-pnc-sw"]),
		tokens={"PNC": CODE},
		series="Glacier",
		name="Pinnacle [DB] Static White LED Neon",
	),
	dict(
		id="driver-family",
		product_type="driver",
		label="Dimming power supply family: several wattages",
		description="A constant voltage power supply family (from Universal Dimming): one spec per wattage with "
		"electrical ratings, and the template with wattage variants, option adders and certifications.",
		roots=("ilL-Driver-Template", ["PS-UNIV"]),
		tokens={"UNIV": CODE},
		series="Power Supply",
		name="Universal Dimming Power Supply",
	),
	dict(
		id="controller-wall",
		product_type="controller",
		label="In-wall controller (DMX512 / BLE Mesh)",
		description="An in-wall controller (from the DMX512 / BLE Mesh tunable white controller): spec with ports, "
		"zones and protocols, and its template variant.",
		roots=("ilL-Controller-Template", ["DMXC-TW-BK-WALL"]),
		tokens={"TW": CODE},
		series="Bluetooth Mesh Decoder",
		name="DMX512 / BLE Mesh In-Wall Tunable White Controller",
		overrides={
			"ilL-Spec-Controller": {
				"input_protocols": [{"protocol": "Touch"}, {"protocol": "Bluetooth Mesh"}]
			}
		},
	),
	dict(
		id="controller-decoder",
		product_type="controller",
		label="DMX decoder (5 channel PWM)",
		description="A DMX decoder (from the 5-channel DMX512 decoder): spec with channel loads, DMX footprint and ports, "
		"and its template variant.",
		roots=("ilL-Controller-Template", ["DMXD-PWM-5C-SF"]),
		tokens={"5C": CODE},
		series="Bluetooth Mesh Decoder",
		name="DMX512 Decoder - 5 Channels - 8Bit / 16Bit",
		overrides={"ilL-Spec-Controller": {"zones": 1}},
	),
]


def _tokens_pattern(tokens):
	"""Whole family tokens, in upper case or all lower case (slugs), never inside a longer code."""
	keys = sorted({variant for key in tokens for variant in (key, key.lower())}, key=len, reverse=True)
	return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in keys) + r")(?![A-Za-z0-9])")


def _renamer(starter):
	tokens = starter["tokens"]
	pattern = _tokens_pattern(tokens)

	def code(text):
		def swap(match):
			new = tokens[next(k for k in tokens if k.lower() == match.group(1).lower())]
			return new.lower() if match.group(1).islower() else new

		return pattern.sub(swap, text)

	series = starter["series"]
	series_pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(series) + r"(?: Series)?(?![A-Za-z0-9])")

	def rename(text, field=None):
		if field in ("series", "series_name"):
			return SERIES if text == series else text
		text = code(text)
		if starter.get("series_text"):
			text = series_pattern.sub(SERIES, text)
		return text

	return rename, pattern


def _belongs(name, pattern):
	return bool(name) and bool(pattern.search(name))


def _strip(doctype, row, meta, rename):
	out = {}
	fields = {f["fieldname"]: f for f in meta.get(doctype, {}).get("fields", [])}
	for key, value in row.items():
		if key in SYSTEM or key in DROP or value in (None, "", []):
			continue
		field = fields.get(key)
		if not field or field["fieldtype"] in ATTACH:
			continue
		if field["fieldtype"] in ("Table", "Table MultiSelect"):
			rows = [_strip(field["options"], child, meta, rename) for child in value]
			rows = [r for r in rows if r]
			if rows:
				out[key] = rows
			continue
		if isinstance(value, str):
			value = rename(value, key)
			if value.startswith("/files/") or "/files/" in value:
				continue
		out[key] = value
	return out


def build_starter(snapshot, starter, schema_):
	meta = schema_["doctypes"]
	rename, pattern = _renamer(starter)
	doctype, names = starter["roots"]
	include = {}  # (doctype, name) -> raw record
	queue = [(doctype, name) for name in names]
	external_only = set(starter.get("external_only", ()))
	items = {}
	while queue:
		key = queue.pop()
		if key in include:
			continue
		row = snapshot.get(*key)
		if row is None:
			continue
		include[key] = row

		def walk(dt, record):
			for field in meta.get(dt, {}).get("fields", []):
				value = record.get(field["fieldname"])
				if value in (None, "", []) or field["fieldname"] in DROP:
					continue
				if field["fieldtype"] in ("Table", "Table MultiSelect"):
					for child in value:
						walk(field["options"], child)
					continue
				target = (
					field["options"]
					if field["fieldtype"] == "Link"
					else record.get(field["options"])
					if field["fieldtype"] == "Dynamic Link"
					else None
				)
				if (
					not target
					or not isinstance(value, str)
					or not _belongs(value, pattern)
					or target in external_only
				):
					continue
				if target == "Item":
					if snapshot.exists("Item", value):
						items[value] = snapshot.get("Item", value)
						for spec in ITEM_SPECS:
							if spec not in external_only and snapshot.exists(spec, value):
								queue.append((spec, value))
				elif snapshot.exists(target, value):
					queue.append((target, value))

		walk(key[0], row)
		for reverse, fields in REVERSE.items():
			if reverse in external_only:
				continue
			for candidate in snapshot.all(reverse).values():
				if any(candidate.get(f) == key[1] for f in fields) and candidate.get("is_active", 1):
					queue.append((reverse, candidate["name"]))
		if key[0] == "ilL-Spec-Profile" and key[0] not in external_only:
			for spec, field in FAMILY.items():
				if spec in external_only:
					continue
				for candidate in snapshot.all(spec).values():
					if _belongs(candidate.get(field), pattern):
						queue.append((spec, candidate["name"]))
	records = {}
	for (dt, _name), row in include.items():
		records.setdefault(dt, []).append(_strip(dt, row, meta, rename))
	if items and "Item" not in external_only:
		records["Item"] = [
			{
				"item_code": rename(code),
				"item_name": rename(item.get("item_name") or code),
				"item_group": item.get("item_group") or "Products",
				"stock_uom": item.get("stock_uom") or "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"is_purchase_item": 1,
			}
			for code, item in sorted(items.items())
		]
	# Deterministic order: DocType, then name.
	ordered = {}
	for dt in sorted(records, key=lambda d: (d != "Item", d)):
		ordered[dt] = sorted(
			records[dt], key=lambda r: str([r.get(k) for k in sorted(r) if not isinstance(r[k], list)])
		)
	ordered = {"ilL-Attribute-Series": [{"series_name": SERIES, "code": CODE, "is_active": 1}], **ordered}
	for doctype, values in starter.get("overrides", {}).items():
		for row in ordered.get(doctype, []):
			row.update(values)
	for row in ordered.get(starter["roots"][0], []):
		row["product_status"] = "Draft"
	external, _missing = declare_externals(ordered, schema_, snapshot)
	external = {
		dt: [n for n in names if not (dt == "ilL-Attribute-Series" and n == SERIES)]
		for dt, names in external.items()
	}
	external = {dt: names for dt, names in external.items() if names}
	product_name = rename(starter["name"])
	if not starter.get("series_text") and SERIES not in product_name:
		product_name = f"{SERIES} {product_name}"
		for row in ordered.get(starter["roots"][0], []):
			if row.get("template_name") and not row["template_name"].startswith(SERIES):
				row["template_name"] = f"{SERIES} {row['template_name']}"
	return {
		"_comment": (
			f"Catalog Builder starter: {starter['label']}.\n"
			"Copied from an active product by tools/catalog_expansion/starters.py and renamed to code DEMO and\n"
			"series 'Example Series'. Review engineering values before importing a product made from it."
		),
		"schema_version": 2,
		"product_type": starter["product_type"],
		"series_name": SERIES,
		"builder": {
			"starter": {
				"id": starter["id"],
				"label": starter["label"],
				"description": starter["description"],
				"code": CODE,
				"series": SERIES,
				"name": product_name,
			}
		},
		"records": ordered,
		"external_links": external,
	}


def main(snapshot_dir, out=OUT):
	snap = Snapshot(snapshot_dir)
	schema_ = schema()
	out.mkdir(parents=True, exist_ok=True)
	for starter in STARTERS:
		data = build_starter(snap, starter, schema_)
		write_yaml(out / f"{starter['id']}.yaml", data)
		print(starter["id"], sum(len(v) for v in data["records"].values()), "records")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--snapshot", required=True)
	args = parser.parse_args()
	main(args.snapshot)
