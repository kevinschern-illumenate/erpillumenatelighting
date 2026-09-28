"""Current Webflow import contract for the legacy family expansion generators."""

from ..catalog import csv_data
from ..catalog_schema import build_schema
from .common import LED_PACKAGE_NAMES, led_sheet_attribute_doctype, write_csv

SCHEMA = build_schema()
DOCTYPE = "ilL-Webflow-Product"
PARENT_FIELDS = (
	"product_name",
	"product_slug",
	"product_type",
	"product_category",
	"series",
	"is_active",
	"fixture_template",
	"tape_neon_template",
	"led_sheet_template",
	"is_configurable",
	"sublabel",
	"auto_calculate_specs",
	"auto_populate_attributes",
	"beam_angle",
	"operating_temp_min_c",
	"operating_temp_max_c",
	"l70_life_hours",
	"warranty_years",
	"webflow_collection_slug",
)
PROTOTYPE = {
	**dict.fromkeys(PARENT_FIELDS, ""),
	"configurator_options": [{"option_step": "", "option_type": "", "option_label": "", "is_required": ""}],
	"attribute_links": [
		{
			"attribute_doctype": "",
			"attribute_name": "",
			"attribute_type": "",
			"display_label": "",
			"display_order": "",
		}
	],
}
HEADERS = csv_data(DOCTYPE, [PROTOTYPE], SCHEMA)[0]


def _templates(config, kind):
	if kind == "fixture":
		for profile in config.profiles:
			for package in config.fixture_templates.led_packages:
				code = f"ILL-{profile.family}-{package}"
				name = f"{config.series_name} {profile.variant_label} {LED_PACKAGE_NAMES.get(package, package)}".strip()
				options = config.get_options_for_template(profile.family, package)
				attributes = []
				for kind_name, values in (
					("Finish", options.allowed_finishes or profile.finishes),
					("Lens Appearance", options.allowed_lenses),
					("Mounting Method", options.allowed_mountings),
					("Endcap Style", options.allowed_endcap_styles),
				):
					attributes.extend((kind_name, value) for value in values)
				yield code, name, config.series_name, attributes
	else:
		rows = config.led_sheet_templates if kind == "led-sheet" else config.tape_neon_templates
		for template in rows:
			attributes = [
				(option.option_type, getattr(option, "attribute_link", "") or option.value)
				for option in template.allowed_options
				if option.is_active
			]
			yield (
				template.template_code,
				template.template_name,
				template.series or config.series_name,
				attributes,
			)


def generate(config, output_dir, kind):
	wf = (
		config.webflow
		if kind == "fixture"
		else config.led_sheet_webflow
		if kind == "led-sheet"
		else config.tape_neon_webflow
	)
	product_type = {
		"fixture": "Fixture Template",
		"led-sheet": "LED Sheet",
		"tape": "LED Tape",
		"neon": "LED Neon",
	}[kind]
	link_field = {
		"fixture": "fixture_template",
		"led-sheet": "led_sheet_template",
		"tape": "tape_neon_template",
		"neon": "tape_neon_template",
	}[kind]
	records = []
	for code, name, series, attributes in _templates(config, kind):
		record = {
			**dict.fromkeys(PARENT_FIELDS, ""),
			"product_name": name or code,
			"product_slug": code.lower().replace(" ", "-"),
			"product_type": product_type,
			"product_category": wf.product_category,
			"series": series,
			"is_active": 1,
			link_field: code,
			"is_configurable": 1,
			"sublabel": wf.sublabel,
			"auto_calculate_specs": 1,
			"auto_populate_attributes": 1,
			"beam_angle": wf.beam_angle,
			"operating_temp_min_c": wf.operating_temp_min_c,
			"operating_temp_max_c": wf.operating_temp_max_c,
			"l70_life_hours": wf.l70_life_hours,
			"warranty_years": wf.warranty_years,
			"webflow_collection_slug": "products",
		}
		steps = list(
			dict.fromkeys(
				"Coverage" if step in {"Coverage Width", "Coverage Height"} else step
				for step in wf.configurator_steps
			)
		)
		record["configurator_options"] = [
			{"option_step": i, "option_type": step, "option_label": step, "is_required": 1}
			for i, step in enumerate(steps, 1)
		]
		record["attribute_links"] = []
		for i, (option_type, value) in enumerate(dict.fromkeys(attributes), 1):
			target = (
				led_sheet_attribute_doctype(option_type)
				if kind == "led-sheet"
				else f"ilL-Attribute-{option_type}"
			)
			if option_type == "Feed Direction":
				target = "ilL-Attribute-Feed-Direction"
			record["attribute_links"].append(
				{
					"attribute_doctype": target,
					"attribute_name": value,
					"attribute_type": option_type,
					"display_label": value,
					"display_order": i,
				}
			)
		records.append(record)
	# Include a prototype to keep all product variants on the same column contract,
	# then discard its data row. It never becomes an imported product.
	headers, rows = csv_data(DOCTYPE, [PROTOTYPE, *records], SCHEMA)
	path = f"{output_dir}/ilL-Webflow-Product.csv"
	write_csv(path, headers, rows[1:])
	return path
