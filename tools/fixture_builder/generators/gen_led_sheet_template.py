"""Generator for LED Sheet specs, templates, and child rows."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

SPEC_HEADERS = [
    "Item", "LED Package", "Sheet Width (ft)", "Sheet Height (ft)",
    "Watts per sqft", "Lumens per sqft", "Input Voltage", "CRI", "IP Rating",
    "SKU Series Code", "SKU LED Package Code", "Is Active",
]

TEMPLATE_HEADERS = [
    "Template Code", "Template Name", "Series", "SKU Series Code", "Webflow Product",
    "Price per Sheet MSRP", "Pricing Class", "Lead Time Class", "Jumper Cable Item",
    "Leader Cable Item", "Spec Submittal Template", "Spec Sheet", "Warranty", "Is Active",
    "Spec (Allowed Specs)", "Is Active (Allowed Specs)",
    "Option Type (Allowed Options)", "Attribute Link (Allowed Options)",
    "Option Code (Allowed Options)", "Is Default (Allowed Options)",
    "Is Active (Allowed Options)", "MSRP Adder (Allowed Options)",
]


def _spec_rows(config: FixtureBuilderConfig) -> list[list]:
    rows = []
    for spec in config.led_sheet_specs:
        rows.append([
            spec.item_code,
            spec.led_package or config.led_package,
            spec.sheet_dimensions.width_ft,
            spec.sheet_dimensions.height_ft,
            spec.watts_per_sqft,
            spec.lumens_per_sqft,
            spec.input_voltage,
            spec.cri,
            spec.ip_rating,
            spec.sku_series_code or config.series_code,
            spec.sku_led_package_code or spec.led_package or config.led_package,
            1,
        ])
    return rows


def _option_rows(tmpl) -> list[list]:
    rows = []
    for opt in tmpl.allowed_options:
        rows.append([
            opt.option_type,
            opt.attribute_link or opt.value,
            opt.option_code or opt.value,
            1 if opt.is_default else 0,
            1 if opt.is_active else 0,
            opt.msrp_adder or "",
        ])
    return rows


def generate_specs(config: FixtureBuilderConfig, output_dir: str) -> str:
    filepath = f"{output_dir}/ilL-Spec-LED-Sheet.csv"
    write_csv(filepath, SPEC_HEADERS, _spec_rows(config))
    return filepath


def generate_templates(config: FixtureBuilderConfig, output_dir: str) -> str:
    rows = []
    for tmpl in config.led_sheet_templates:
        child_rows = []
        for spec in tmpl.allowed_specs:
            child_rows.append(("spec", [spec.spec, 1 if spec.is_active else 0]))
        for opt_row in _option_rows(tmpl):
            child_rows.append(("option", opt_row))

        primary = [
            tmpl.template_code,
            tmpl.template_name,
            tmpl.series or config.series_name,
            tmpl.sku_series_code or config.series_code,
            tmpl.webflow_product,
            tmpl.price_per_sheet_msrp,
            tmpl.pricing_class,
            tmpl.lead_time_class,
            tmpl.jumper_cable_item or config.jumper_cable_item,
            tmpl.leader_cable_item or config.leader_cable_item,
            tmpl.spec_submittal_template,
            tmpl.spec_sheet,
            tmpl.warranty,
            1,
        ]
        if not child_rows:
            rows.append(primary + [""] * 8)
            continue
        for idx, (kind, data) in enumerate(child_rows):
            row = (primary if idx == 0 else [""] * 14)
            if kind == "spec":
                row += data + [""] * 6
            else:
                row += [""] * 2 + data
            rows.append(row)

    filepath = f"{output_dir}/ilL-LED-Sheet-Template.csv"
    write_csv(filepath, TEMPLATE_HEADERS, rows)
    return filepath


def generate(config: FixtureBuilderConfig, output_dir: str) -> dict[str, str]:
    return {
        "ilL-Spec-LED-Sheet.csv": generate_specs(config, output_dir),
        "ilL-LED-Sheet-Template.csv": generate_templates(config, output_dir),
    }
