"""Generate the component Items referenced by expanded family specifications."""

from collections import defaultdict

from ..catalog import csv_data
from ..catalog_schema import build_schema
from ..config_schema import ENDCAP_COLOR_NAMES, FINISH_NAMES
from .common import ITEM_GROUPS, LENS_APPEARANCE_CODES, write_csv


def generate(config, output_dir):
	items, attributes = [], defaultdict(dict)

	def variant(code, parent, group, choices):
		rows = []
		for name, value, abbreviation in choices:
			attributes[name][value] = abbreviation
			rows.append({"attribute": name, "attribute_value": value})
		items.append(
			{
				"item_code": code,
				"item_name": f"{config.series_name} {code}",
				"item_group": group,
				"stock_uom": "Ea",
				"is_stock_item": 1,
				"has_variants": 0,
				"variant_of": parent,
				"variant_based_on": "Item Attribute",
				"attributes": rows,
				"brand": config.brand,
				"warranty_period": config.warranty_days,
			}
		)

	for profile in config.profiles:
		for finish in profile.finishes:
			variant(
				f"CH-{profile.family}-{finish}",
				f"CH-{profile.family}",
				ITEM_GROUPS["profile"],
				[("Finish", FINISH_NAMES.get(finish, finish), finish)],
			)
	for lens in config.lenses:
		for appearance in lens.appearances:
			color = LENS_APPEARANCE_CODES.get(appearance, appearance[:2].upper())
			variant(
				f"LNS-{lens.family}-{lens.shape}-{color}",
				f"LNS-{lens.family}",
				ITEM_GROUPS["lens"],
				[("Lens Style", lens.shape, lens.shape), ("Lens Color", appearance, color)],
			)
	for endcap in config.endcaps:
		for color in endcap.colors:
			for style in endcap.styles:
				style_code = {"Solid": "NO", "Feed Through": "HO"}.get(style, style[:2].upper())
				variant(
					f"EC-{endcap.profile_family}-{color}-{style_code}",
					f"EC-{endcap.profile_family}",
					ITEM_GROUPS["endcap"],
					[
						("Endcap Color", ENDCAP_COLOR_NAMES.get(color, color), color),
						("Endcap Type", style, style_code),
					],
				)
	attribute_rows = [
		{
			"attribute_name": name,
			"item_attribute_values": [
				{"attribute_value": value, "abbr": abbreviation} for value, abbreviation in values.items()
			],
		}
		for name, values in attributes.items()
	]
	schema, results = build_schema(), {}
	for doctype, filename, records in (
		("Item Attribute", "Item Attribute.csv", attribute_rows),
		("Item", "Item Variants.csv", items),
	):
		headers, rows = csv_data(doctype, records, schema)
		path = f"{output_dir}/{filename}"
		write_csv(path, headers, rows)
		results[filename] = path
	return results
