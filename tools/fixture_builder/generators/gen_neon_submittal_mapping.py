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
    ("form", "ilL-Configured-Tape-Neon", "part_number", "", "", "", "", "", "", ""),
    ("cctcode", "ilL-Configured-Tape-Neon", "cct", "", "", "", "", "", "", ""),
    ("outputcode", "ilL-Configured-Tape-Neon", "output_level", "", "", "", "", "", "", ""),
    ("length", "ilL-Configured-Tape-Neon", "requested_length_mm", "", "", "MM_TO_INCHES", "", "", "", ""),
    ("drywetcode", "ilL-Configured-Tape-Neon", "environment_rating", "", "", "", "", "", "", ""),
    ("wattage", "ilL-Configured-Tape-Neon", "total_watts", "", "W", "", "", "", "", ""),
    ("output", "ilL-Configured-Tape-Neon", "watts_per_foot", "", "W/ft", "", "", "", "", ""),
    ("maxfootage100w", "ilL-Spec-LED Tape", "watts_per_foot", "", "ft", "MAX_FOOTAGE_100W", "", "", "", ""),
    ("operatingtemp", "ilL-Spec-LED Tape", "operating_temp", "", "", "", "", "", "", ""),
    ("warranty", "ilL-Tape-Neon-Template", "warranty_years", "", " Year Limited", "", "", "", "", ""),
    ("productioninterval", "ilL-Spec-LED Tape", "cut_increment_mm", "", '""', "MM_TO_INCHES", "", "", "", ""),
    ("cri", "ilL-Rel-Tape Offering", "cri", "", "", "", "", "", "", ""),
    ("cct", "ilL-Rel-Tape Offering", "cct", "", "", "", "", "", "", ""),
    ("inputvoltage", "ilL-Spec-LED Tape", "input_voltage", "", "", "", "", "", "", ""),
    ("dimming", "ilL-Spec-LED Tape", "dimming_protocols", "", "", "", "", "", "", ""),
    ("project_name", "ilL-Project", "project_name", "", "", "", "project_name", "", "", ""),
    ("project_location", "ilL-Project", "location", "", "", "", "project_location", "", "", ""),
    ("fixture_type", "ilL-Child-Fixture-Schedule-Line", "line_id", "", "", "", "", "", "", ""),
    ("feeddir", "ilL-Configured-Tape-Neon", "feed_direction", "", "", "", "feed_direction", "", "", ""),
    ("feedtype", "ilL-Configured-Tape-Neon", "feed_type", "", "", "", "", "", "", ""),
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
