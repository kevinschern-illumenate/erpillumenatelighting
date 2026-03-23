"""Generator for ilL-Spec-Submittal-Mapping.csv.

Clones submittal mappings from a user-specified source template CSV,
replacing the fixture_template reference with each new template code.
"""

from __future__ import annotations

import csv
import os

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Fixture Template",
    "PDF Field Name",
    "Source DocType",
    "Source Field",
    "Prefix",
    "Suffix",
    "Transformation",
    "Webflow Field",
    "Webflow Prefix/Suffix",
    "Webflow Prefix",
    "Webflow Suffix",
]

# Default mapping rows derived from the ILL-AX01-FS template pattern
DEFAULT_MAPPINGS = [
    ("form", "ilL-Configured-Fixture", "sku_driver_form_code", "", "", "", "", "", "", ""),
    ("maxwattoutput", "ilL-Configured-Fixture", "sku_driver_wattage_output_code", "", "", "", "", "", "", ""),
    ("control", "ilL-Configured-Fixture", "sku_driver_control_code", "", "", "", "", "", "", ""),
    ("endlength", "ilL-Configured-Fixture", "__end_length_indicator", "", "", "MM_TO_INCHES", "end_feed_length_ft", "", "", ""),
    ("startlength", "ilL-Configured-Fixture", "__start_leader_cable_len_mm", "", "", "MM_TO_INCHES", "start_feed_length_ft", "", "", ""),
    ("starttype", "ilL-Configured-Fixture", "sku_power_feed_code", "", "", "", "start_feed_direction", "", "", ""),
    ("outputcode", "ilL-Configured-Fixture", "sku_fixture_output_code", "", "", "", "", "", "", ""),
    ("mountingcode", "ilL-Configured-Fixture", "sku_mounting_code", "", "", "", "", "", "", ""),
    ("lenscode", "ilL-Configured-Fixture", "sku_lens_code", "", "", "", "", "", "", ""),
    ("length", "ilL-Configured-Fixture", "requested_overall_length_mm", "", "", "MM_TO_INCHES", "", "", "", ""),
    ("finishcode", "ilL-Configured-Fixture", "sku_finish_code", "", "", "", "", "", "", ""),
    ("endtype", "ilL-Configured-Fixture", "sku_feed_direction_end_code", "", "", "", "end_feed_direction", "", "", ""),
    ("cctcode", "ilL-Configured-Fixture", "sku_cct_code", "", "", "", "", "", "", ""),
    ("drywetcode", "ilL-Configured-Fixture", "sku_environment_code", "", "", "", "", "", "", ""),
    ("project_location", "ilL-Project", "location", "", "", "", "project_location", "", "", ""),
    ("fixture_type", "ilL-Child-Fixture-Schedule-Line", "line_id", "", "", "", "", "", "", ""),
    ("project_name", "ilL-Project", "project_name", "", "", "", "project_name", "", "", ""),
    ("productioninterval", "ilL-Spec-LED Tape", "cut_increment_mm", "", '""', "MM_TO_INCHES", "", "", "", ""),
    ("dims", "ilL-Spec-Profile", "dimensions", "", "", "", "", "", "", ""),
    ("dimming", "ilL-Spec-Driver", "input_protocols", "", "", "", "", "", "", ""),
    ("inputvoltage", "ilL-Spec-Driver", "voltage_output", "", "", "", "", "", "", ""),
    ("finish", "ilL-Configured-Fixture", "finish", "", "", "", "", "", "", ""),
    ("mounting", "ilL-Configured-Fixture", "mounting_method", "", "", "", "", "", "", ""),
    ("lens", "ilL-Configured-Fixture", "lens_appearance", "", "", "", "", "", "", ""),
    ("cri", "ilL-Rel-Tape Offering", "cri", "", "", "", "", "", "", ""),
    ("cct", "ilL-Rel-Tape Offering", "cct", "", "", "", "", "", "", ""),
    ("maxrunlength", "ilL-Configured-Fixture", "max_run_ft_effective", "", "ft", "", "", "", "", ""),
    ("wattage", "ilL-Configured-Fixture", "total_watts", "", "W", "", "", "", "", ""),
    ("output", "ilL-Configured-Fixture", "estimated_delivered_output", "", "lm/ft", "", "", "", "", ""),
]


def _load_source_mappings(source_csv_path: str, source_template: str) -> list[tuple]:
    """Load submittal mappings from an existing CSV for a given template."""
    if not os.path.exists(source_csv_path):
        return []

    mappings = []
    with open(source_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Fixture Template", "").strip() == source_template:
                mappings.append((
                    row.get("PDF Field Name", ""),
                    row.get("Source DocType", ""),
                    row.get("Source Field", ""),
                    row.get("Prefix", ""),
                    row.get("Suffix", ""),
                    row.get("Transformation", ""),
                    row.get("Webflow Field", ""),
                    row.get("Webflow Prefix/Suffix", ""),
                    row.get("Webflow Prefix", ""),
                    row.get("Webflow Suffix", ""),
                ))
    return mappings


def generate(config: FixtureBuilderConfig, output_dir: str,
             source_csv_path: str = "") -> str:
    """Generate ilL-Spec-Submittal-Mapping.csv and return the filepath.

    If source_csv_path is provided and the clone_from_template is set,
    loads mappings from the existing CSV. Otherwise uses defaults.
    """
    rows = []
    clone_from = config.submittal_mapping.clone_from_template

    # Try to load from source CSV
    source_mappings = []
    if clone_from and source_csv_path:
        source_mappings = _load_source_mappings(source_csv_path, clone_from)

    # Fall back to defaults
    if not source_mappings:
        source_mappings = DEFAULT_MAPPINGS

    for profile in config.profiles:
        for led_pkg in config.fixture_templates.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"

            for mapping in source_mappings:
                rows.append([template_code] + list(mapping))

    filepath = f"{output_dir}/ilL-Spec-Submittal-Mapping.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
