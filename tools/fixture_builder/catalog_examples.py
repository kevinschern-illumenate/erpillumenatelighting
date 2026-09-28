"""Illustrative product catalogs shared by the UI and CLI regression tests.

These values demonstrate the authoring structure, not approved product ratings.
Run with the fixture builder's Python environment to refresh YAML and UI examples.
"""

from __future__ import annotations

import json
from pathlib import Path

from .catalog import identity, links, prepare_catalog, with_defaults
from .catalog_schema import PRODUCTS, ROOT, build_schema


def example_catalog(product_type):
	schema = build_schema()
	records = {}

	def add(doctype, **row):
		records.setdefault(doctype, []).append(row)
		return row

	def item(code, uom="Nos"):
		add("Item", item_code=code, item_name=f"Example {code}", item_group="Products", stock_uom=uom,
			is_stock_item=1, is_sales_item=1, is_purchase_item=1)
		return code

	add("ilL-Attribute-Series", series_name="Example Series", code="DEMO", is_active=1)
	template = PRODUCTS[product_type]["template"]
	common = {"template_code": f"DEMO-{product_type.upper()}", "template_name": f"Example {PRODUCTS[product_type]['label']}",
		"series": "Example Series", "is_active": 1}
	code = common["template_code"]
	if product_type in {"fixture", "tape", "neon"}:
		tape = item("DEMO-TAPE", "Meter")
		add("ilL-Spec-LED Tape", item=tape, led_package="SW", product_category="LED Neon" if product_type == "neon" else "LED Tape",
			input_voltage="24V DC", input_protocol="PWM", watts_per_foot=4.4, voltage_drop_max_run_length_ft=16.4,
			cut_increment_mm=50, lumens_per_foot=400, leader_cable_item=item("DEMO-LEADER"))
		add("ilL-Rel-Tape Offering", tape_spec=tape, cct="3000K", cri="90", sdcm="3", led_package="SW", output_level="Standard")
		add("ilL-Rel-Leader-Cable-Map", tape_spec=tape, power_feed_type="Single End Feed", leader_item="DEMO-LEADER", default_length_mm=300)
	if product_type in {"fixture", "extrusion-kit"}:
		profile = item("CH-DEMO-WH")
		lens = item("LNS-DEMO-WH-FR")
		add("ilL-Spec-Profile", item=profile, family="DEMO", series="Example Series", width_mm=20, height_mm=10,
			stock_length_mm=2000, max_assembled_length_mm=2000, is_cuttable=1, lens_interface="Snap-in",
			supported_environment_ratings=[{"environment_rating": "Dry"}])
		add("ilL-Spec-Lens", item=lens, family="DEMO", series="Example Series", lens_appearance="Frosted", stock_type="Stick", stock_length_mm=2000)
		add("ilL-Rel-Profile Lens", profile_spec=profile, compatible_lenses=[{"lens_spec": lens}])
		for suffix, style in (("NO", "Solid"), ("HO", "Feed Through")):
			endcap = item(f"EC-DEMO-WH-{suffix}")
			add("ilL-Spec-Accessory", item=endcap, type="Endcap", profile_family="DEMO", endcap_style=style)
		mount = item("ACC-DEMO-MC")
		add("ilL-Spec-Accessory", item=mount, type="Mounting", mounting_method="Mounting Clip", profile_family="DEMO")
		add("ilL-Rel-Finish Endcap Color", finish="White", endcap_color="White", is_default=1)
		options = [{"option_type": "Finish", "finish": "White", "is_default": 1, "is_active": 1},
			{"option_type": "Lens Appearance", "lens_appearance": "Frosted", "is_default": 1, "is_active": 1},
			{"option_type": "Mounting Method", "mounting_method": "Mounting Clip", "is_default": 1, "is_active": 1},
			{"option_type": "Endcap Style", "endcap_style": "Solid", "is_default": 1, "is_active": 1}]
		if product_type == "fixture":
			add(template, **common, default_profile_family="DEMO", default_profile_spec=profile,
				default_profile_stock_len_mm=2000, assembled_max_len_mm=2000, base_price_msrp=20, price_per_ft_msrp=15,
				allowed_options=options + [{"option_type": "Environment Rating", "environment_rating": "Dry", "is_active": 1},
					{"option_type": "Power Feed Type", "power_feed_type": "Single End Feed", "is_active": 1}],
				allowed_tape_offerings=[{"tape_offering": "DEMO-TAPE-3000K-Standard", "is_default": 1}])
			for suffix, style in (("NO", "Solid"), ("HO", "Feed Through")):
				add("ilL-Rel-Endcap-Map", fixture_template=code, endcap_style=style, endcap_color="White", endcap_item=f"EC-DEMO-WH-{suffix}")
			add("ilL-Rel-Mounting-Accessory-Map", template_type=template, fixture_template=code, mounting_method="Mounting Clip",
				accessory_item=mount, qty_rule_type="PER_X_MM", qty_rule_value=304.8)
		else:
			add(template, **common, default_profile_family="DEMO", default_profile_spec=profile, default_lens_spec=lens,
				profile_stock_length_mm=2000, lens_stock_length_mm=2000, solid_endcap_qty=2, feed_through_endcap_qty=1,
				mounting_accessory_qty=4, base_price_msrp=35, allowed_options=options)
			add("ilL-Rel-Kit-Profile-Map", kit_template=code, finish="White", profile_spec=profile, profile_item=profile)
			add("ilL-Rel-Kit-Lens-Map", kit_template=code, lens_appearance="Frosted", lens_spec=lens, lens_item=lens)
			add("ilL-Rel-Kit-Mounting-Map", kit_template=code, mounting_method="Mounting Clip", accessory_item=mount, accessory_spec=mount)
			for suffix, kind in (("NO", "Solid"), ("HO", "Feed-Through")):
				add("ilL-Rel-Kit-Endcap-Map", kit_template=code, endcap_style="Solid", endcap_color="White", endcap_type=kind,
					endcap_item=f"EC-DEMO-WH-{suffix}", endcap_spec=f"EC-DEMO-WH-{suffix}")
	elif product_type in {"tape", "neon"}:
		add(template, **common, product_category="LED Neon" if product_type == "neon" else "LED Tape", default_tape_spec=tape,
			base_price_msrp=10, price_per_ft_msrp=12, production_interval_mm=50, leader_allowance_mm_per_fixture=15,
			allowed_tape_specs=[{"tape_spec": tape, "is_default": 1, "environment_rating": "Dry"}],
			allowed_options=[{"option_type": "CCT", "cct": "3000K", "is_default": 1, "is_active": 1},
				{"option_type": "Output Level", "output_level": "Standard", "is_default": 1, "is_active": 1},
				{"option_type": "Environment Rating", "environment_rating": "Dry", "is_default": 1, "is_active": 1}])
	elif product_type == "led-sheet":
		sheet = item("DEMO-SHEET")
		add("ilL-Spec-LED-Sheet", item=sheet, led_package="SW", sheet_width_ft=1, sheet_height_ft=2,
			watts_per_sqft=10, total_sheet_watts=20, lumens_per_sqft=1000, input_voltage="24V DC", input_protocol="PWM",
			cct="3000K", cut_interval_width_in=2, cut_interval_height_in=2, sku_series_code="DEMO", sku_led_package_code="SW")
		add(template, **common, sku_series_code="DEMO", price_per_sheet_msrp=50,
			leader_cable_item=item("DEMO-LEADER"), jumper_cable_item=item("DEMO-JUMPER"),
			allowed_specs=[{"spec": sheet, "is_active": 1}],
			allowed_options=[{"option_type": "CCT", "attribute_doctype": "ilL-Attribute-CCT", "attribute_link": "3000K", "option_code": "30", "is_default": 1, "is_active": 1}])
	elif product_type == "driver":
		driver = item("DEMO-DRIVER")
		add("ilL-Spec-Driver", item=driver, voltage_output="24V DC", output_type="Constant Voltage", output_protocol="PWM",
			outputs_count=1, independent_outputs_count=1, max_wattage=96, max_wattage_per_output=96, usable_load_factor=0.8,
			input_voltage_min=120, input_voltage_max=277, input_voltage_type="VAC", input_protocols=[{"protocol": "0-10V", "is_default": 1}])
		add(template, **common, sku_series_code="DEMO", base_price_msrp=90,
			variants=[{"driver_spec": driver, "wattage": 96, "voltage_output": "24V DC", "input_protocol": "0-10V", "output_protocol": "PWM", "is_default": 1, "is_active": 1}],
			allowed_options=[{"option_type": "Wattage", "option_value": "96", "option_code": "96W", "is_default": 1, "is_active": 1}])
	elif product_type == "controller":
		controller = item("DEMO-CONTROLLER")
		add("ilL-Spec-Controller", item=controller, controller_name="Example controller", controller_type="Wireless Receiver", mounting_type="Surface",
			input_voltage_type="VDC", input_voltage_min=12, input_voltage_max=24, channels=4, zones=1, max_load_watts=96,
			input_protocols=[{"protocol": "DMX"}], output_protocols=[{"protocol": "PWM"}])
		add(template, **common, sku_series_code="DEMO", base_price_msrp=60,
			variants=[{"controller_spec": controller, "channels": 4, "zones": 1, "input_protocol": "DMX", "output_protocol": "PWM", "is_default": 1, "is_active": 1}],
			allowed_options=[{"option_type": "Channels", "option_value": "4", "option_code": "4CH", "is_default": 1, "is_active": 1}])
	if product_type in {"fixture", "tape", "neon", "led-sheet"}:
		add("ilL-Rel-Driver-Eligibility", template_type=template, fixture_template=code, driver_spec="EXISTING-96W-DRIVER", is_allowed=1, priority=1)
	product_types = {"fixture": "Fixture Template", "tape": "LED Tape", "neon": "LED Neon", "led-sheet": "LED Sheet", "driver": "Driver", "controller": "Controller"}
	product_fields = {"fixture": "fixture_template", "tape": "tape_neon_template", "neon": "tape_neon_template", "led-sheet": "led_sheet_template", "driver": "driver_template", "controller": "controller_template"}
	# Extrusion kits use their dedicated portal configurator. Webflow's current
	# product schema has component tables but no extrusion kit template link.
	if product_type in product_types:
		add("ilL-Webflow-Product", product_name=common["template_name"], product_slug=f"example-{product_type}",
			product_type=product_types[product_type], is_configurable=1, is_active=1, series="Example Series",
			**{product_fields[product_type]: code})
	result = {"schema_version": 2, "product_type": product_type, "series_name": "Example Series", "records": records, "external_links": {}}
	known = {(dt, identity(dt, row, schema)) for dt, rows in records.items() for row in rows}
	for dt, rows in records.items():
		for row in rows:
			for target, name, _ in links(dt, with_defaults(dt, row, schema), schema):
				if (target, name) not in known and name not in result["external_links"].setdefault(target, []):
					result["external_links"][target].append(name)
	prepare_catalog(result, schema)
	return result


def main():
	import yaml
	examples = {key: example_catalog(key) for key in PRODUCTS}
	(ROOT / "tools/yaml_builder_ui/src/catalog-examples.json").write_text(json.dumps(examples, indent=2) + "\n", encoding="utf-8")
	for key, data in examples.items():
		path = Path(__file__).parent / "templates" / f"catalog_{key}.yaml"
		path.write_text("# Illustrative values only; verify engineering ratings and external links before import.\n"
			+ yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


if __name__ == "__main__":
	main()
