"""Generator for ilL-Neon-Submittal-Mapping.csv.

Clones submittal mappings from a user-specified source template,
replacing the template reference with each new tape/neon template code.
Same pattern as gen_spec_submittal_mapping.py but targeting
the ilL-Neon-Submittal-Mapping doctype.
"""

from __future__ import annotations

import csv
import os

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Tape Neon Template",
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

# Default mapping rows for tape/neon submittal PDFs
DEFAULT_MAPPINGS = [
    ("cctcode", "ilL-Configured-Tape-Neon", "sku_cct_code", "", "", "", "", "", "", ""),
    ("outputcode", "ilL-Configured-Tape-Neon", "sku_output_code", "", "", "", "", "", "", ""),
    ("length", "ilL-Configured-Tape-Neon", "requested_length_mm", "", "", "MM_TO_INCHES", "", "", "", ""),
    ("drywetcode", "ilL-Configured-Tape-Neon", "environment_rating", "", "", "", "", "", "", ""),
    ("wattage", "ilL-Configured-Tape-Neon", "watts_per_foot", "", "W", "", "", "", "", ""),
    ("output", "ilL-Configured-Tape-Neon", "output_level", "", "W/ft", "", "", "", "", ""),
    ("cri", "ilL-Rel-Tape Offering", "cri", "", "", "", "", "", "", ""),
    ("cct", "ilL-Rel-Tape Offering", "cct", "", "", "", "", "", "", ""),
    ("productioninterval", "ilL-Spec-LED Tape", "cut_increment_mm", "", '""', "MM_TO_INCHES", "", "", "", ""),
    ("inputvoltage", "ilL-Spec-LED Tape", "input_voltage", "", "", "", "", "", "", ""),
    ("dimming", "ilL-Spec-LED Tape", "input_protocol", "", "", "", "", "", "", ""),
    ("maxfootage100w", "ilL-Spec-LED Tape", "watts_per_foot", "", "ft", "MAX_FOOTAGE_100W", "", "", "", ""),
    ("operatingtemp", "ilL-Spec-LED Tape", "operating_temp", "", "", "", "", "", "", ""),
    ("maxrunlength", "ilL-Spec-LED Tape", "voltage_drop_max_run_length_ft", "", "", "", "", "", "", ""),
    ("warranty", "ilL-Tape-Neon-Template", "warranty_years", "", " Years", "", "", "", "", ""),
    ("minbenddiameter", "ilL-Tape-Neon-Template", "minimum_side_bend_diameter_mm", "", "", "MM_TO_INCHES", "", "", "", ""),
    ("dims", "ilL-Tape-Neon-Template", "spec_sheet_dimensions", "", "", "", "", "", "", ""),
    ("available_mountings", "ilL-Tape-Neon-Template", "available_mountings", "", "", "", "", "", "", ""),
    ("finish", "ilL-Configured-Tape-Neon", "finish", "", "", "", "", "", "", ""),
    ("feedtype", "ilL-Configured-Tape-Neon", "feed_type", "", "", "", "", "", "", ""),
    ("feeddir", "ilL-Configured-Tape-Neon", "feed_direction", "", "", "", "", "", "", ""),
    # Start/End feed direction & length — sourced from segment #1 when not on
    # the parent (handled by _get_neon_source_value fallback).  Webflow flow
    # also forwards these as overrides so the PDF reflects user input.
    ("starttype", "ilL-Configured-Tape-Neon", "start_feed_direction", "", "", "", "start_feed_direction", "", "", ""),
    ("startlength", "ilL-Configured-Tape-Neon", "start_lead_length_inches", "", "", "", "start_feed_length_ft", "", "", ""),
    ("endtype", "ilL-Configured-Tape-Neon", "end_feed_direction", "", "", "", "end_feed_direction", "", "", ""),
    ("endlength", "ilL-Configured-Tape-Neon", "end_cable_length_inches", "", "", "", "end_feed_length_ft", "", "", ""),
    ("fixture_type", "ilL-Child-Fixture-Schedule-Line", "line_id", "", "", "", "", "", "", ""),
    ("project_name", "ilL-Project", "project_name", "", "", "", "project_name", "", "", ""),
    ("project_location", "ilL-Project", "location", "", "", "", "project_location", "", "", ""),
]


def _load_source_mappings(source_csv_path: str, source_template: str) -> list[tuple]:
    """Load submittal mappings from an existing CSV for a given template."""
    if not os.path.exists(source_csv_path):
        return []

    mappings = []
    with open(source_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Tape Neon Template", "").strip() == source_template:
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
    """Generate ilL-Neon-Submittal-Mapping.csv and return the filepath."""
    rows = []
    clone_from = config.neon_submittal_mapping.clone_from_template

    # Try to load from source CSV
    source_mappings = []
    if clone_from and source_csv_path:
        source_mappings = _load_source_mappings(source_csv_path, clone_from)

    # Fall back to defaults
    if not source_mappings:
        source_mappings = DEFAULT_MAPPINGS

    for tmpl in config.tape_neon_templates:
        for mapping in source_mappings:
            rows.append([tmpl.template_code] + list(mapping))

    filepath = f"{output_dir}/ilL-Neon-Submittal-Mapping.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
