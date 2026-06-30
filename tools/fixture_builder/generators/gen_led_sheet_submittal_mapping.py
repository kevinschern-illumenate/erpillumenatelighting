"""Generator for ilL-LED-Sheet-Submittal-Mapping.csv."""

from __future__ import annotations

import csv
import os

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "LED Sheet Template", "PDF Field Name", "Source DocType", "Source Field",
    "Prefix", "Suffix", "Transformation", "Logic", "Webflow Field",
    "Webflow Skip Transformation", "Webflow Prefix/Suffix", "Webflow Prefix", "Webflow Suffix",
]

DEFAULT_SHEET_MAPPINGS = [
    ("project_name", "ilL-Project", "project_name", "", "", "", "", "project_name", 0, "", "", ""),
    ("project_location", "ilL-Project", "location", "", "", "", "", "project_location", 0, "", "", ""),
    ("part_number", "ilL-Configured-LED-Sheet", "part_number", "", "", "", "", "", 0, "", "", ""),
    ("series_code", "ilL-Configured-LED-Sheet", "sku_series_code", "", "", "", "", "", 0, "", "", ""),
    ("environment_code", "ilL-Configured-LED-Sheet", "sku_environment_code", "", "", "", "", "environment_rating", 0, "", "", ""),
    ("cct_code", "ilL-Configured-LED-Sheet", "sku_cct_code", "", "", "", "", "", 0, "", "", ""),
    ("output_code", "ilL-Configured-LED-Sheet", "sku_output_code", "", "", "", "", "", 0, "", "", ""),
    ("sheets_needed", "ilL-Configured-LED-Sheet", "sheets_needed", "", "", "", "", "", 0, "", "", ""),
    ("total_coverage_sqft", "ilL-Configured-LED-Sheet", "total_coverage_sqft", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("total_system_watts", "ilL-Configured-LED-Sheet", "total_system_watts", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("total_groups", "ilL-Configured-LED-Sheet", "total_groups", "", "", "", "", "", 0, "", "", ""),
    ("leader_cable_qty", "ilL-Configured-LED-Sheet", "leader_cable_qty", "", "", "", "", "", 0, "", "", ""),
    ("jumper_cables_extra", "ilL-Configured-LED-Sheet", "jumper_cables_extra", "", "", "", "", "", 0, "", "", ""),
    ("watts_per_sqft", "ilL-Spec-LED-Sheet", "watts_per_sqft", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("lumens_per_sqft", "ilL-Spec-LED-Sheet", "lumens_per_sqft", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("sheet_width_ft", "ilL-Spec-LED-Sheet", "sheet_width_ft", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("sheet_height_ft", "ilL-Spec-LED-Sheet", "sheet_height_ft", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("sheet_area_sqft", "ilL-Spec-LED-Sheet", "sheet_area_sqft", "", "", "ROUND_2_DECIMALS", "", "", 0, "", "", ""),
    ("input_voltage", "ilL-Spec-LED-Sheet", "input_voltage", "", "", "", "", "", 0, "", "", ""),
    ("ip_rating", "ilL-Spec-LED-Sheet", "ip_rating", "", "", "", "", "", 0, "", "", ""),
    ("template_name", "ilL-LED-Sheet-Template", "template_name", "", "", "", "", "", 0, "", "", ""),
]


def _load_source_mappings(source_csv_path: str, source_template: str) -> list[tuple]:
    if not os.path.exists(source_csv_path):
        return []
    mappings = []
    with open(source_csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("LED Sheet Template", "").strip() == source_template:
                mappings.append(tuple(row.get(h, "") for h in HEADERS[1:]))
    return mappings


def generate(config: FixtureBuilderConfig, output_dir: str, source_csv_path: str = "") -> str:
    clone_from = config.led_sheet_submittal_mapping.clone_from_template
    mappings = _load_source_mappings(source_csv_path, clone_from) if clone_from and source_csv_path else []
    if not mappings:
        mappings = DEFAULT_SHEET_MAPPINGS
    rows = []
    for tmpl in config.led_sheet_templates:
        for mapping in mappings:
            rows.append([tmpl.template_code] + list(mapping))
    filepath = f"{output_dir}/ilL-LED-Sheet-Submittal-Mapping.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
