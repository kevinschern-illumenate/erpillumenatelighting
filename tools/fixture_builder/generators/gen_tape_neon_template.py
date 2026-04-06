"""Generator for ilL-Tape-Neon-Template.csv — tape/neon template definitions.

Multi-line for child tables: allowed_tape_specs and allowed_options.
Same multi-line child table CSV pattern as gen_fixture_template.py.
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, TAPE_NEON_OPTION_TYPES

HEADERS = [
    "Template Code",
    "Template Name",
    "Is Active",
    "Product Category",
    "Series",
    "Default Tape Spec",
    "Base Price MSRP",
    "Price per ft MSRP",
    "Pricing Length Basis",
    "Leader Allowance mm per Fixture",
    # allowed_tape_specs child table
    "Tape Spec (Allowed Tape Specs)",
    "Is Default (Allowed Tape Specs)",
    "Environment Rating (Allowed Tape Specs)",
    # allowed_options child table
    "Option Type (Allowed Options)",
    "CCT (Allowed Options)",
    "Output Level (Allowed Options)",
    "Environment Rating (Allowed Options)",
    "IP Rating (Allowed Options)",
    "Feed Direction (Allowed Options)",
    "Power Feed Type (Allowed Options)",
    "PCB Mounting (Allowed Options)",
    "PCB Finish (Allowed Options)",
    "Mounting Method (Allowed Options)",
    "Finish (Allowed Options)",
    "Endcap Style (Allowed Options)",
    "Feed Position (Allowed Options)",
    "Is Default (Allowed Options)",
    "Is Active (Allowed Options)",
    "MSRP Adder (Allowed Options)",
]

NUM_COLS = len(HEADERS)

# Column indices for option type → value placement
_OPTION_VALUE_COL = {
    "CCT": 14,
    "Output Level": 15,
    "Environment Rating": 16,
    "IP Rating": 17,
    "Feed Direction": 18,
    "Power Feed Type": 19,
    "PCB Mounting": 20,
    "PCB Finish": 21,
    "Mounting Method": 22,
    "Finish": 23,
    "Endcap Style": 24,
}


def _build_spec_child(tape_spec, is_default, environment_rating):
    """Build allowed_tape_specs child columns (cols 10-12)."""
    return [tape_spec, 1 if is_default else 0, environment_rating]


def _build_option_child(opt):
    """Build allowed_options child columns (cols 13-29)."""
    cols = [""] * 17  # 17 columns for allowed_options section
    cols[0] = opt.option_type
    value_col = _OPTION_VALUE_COL.get(opt.option_type)
    if value_col is not None:
        cols[value_col - 13] = opt.value
    cols[12] = opt.feed_position  # Feed Position
    cols[13] = 1 if opt.is_default else 0  # Is Default
    cols[14] = 1 if opt.is_active else 0   # Is Active
    cols[15] = opt.msrp_adder if opt.msrp_adder else ""  # MSRP Adder
    return cols


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Tape-Neon-Template.csv and return the filepath."""
    rows = []

    for tmpl in config.tape_neon_templates:
        # Collect all child rows
        child_rows = []

        # Allowed tape specs
        for spec_def in tmpl.allowed_tape_specs:
            child_rows.append(("spec", _build_spec_child(
                spec_def.tape_spec, spec_def.is_default, spec_def.environment_rating
            )))

        # Allowed options
        for opt in tmpl.allowed_options:
            child_rows.append(("option", _build_option_child(opt)))

        # Primary row header columns (cols 0-9)
        primary = [
            tmpl.template_code,
            tmpl.template_name,
            1,  # Is Active
            tmpl.product_category,
            tmpl.series or config.series_name,
            tmpl.default_tape_spec,
            tmpl.base_price_msrp,
            tmpl.price_per_ft_msrp,
            tmpl.pricing_length_basis,
            tmpl.leader_allowance_mm,
        ]

        if child_rows:
            first_type, first_data = child_rows[0]
            row = primary + _expand_child(first_type, first_data)
            rows.append(row)

            for child_type, child_data in child_rows[1:]:
                row = [""] * 10 + _expand_child(child_type, child_data)
                rows.append(row)
        else:
            row = primary + [""] * (NUM_COLS - 10)
            rows.append(row)

    filepath = f"{output_dir}/ilL-Tape-Neon-Template.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath


def _expand_child(child_type, child_data):
    """Expand child data into the correct column positions."""
    # Columns: [10..12] = spec (3), [13..29] = option (17)
    if child_type == "spec":
        return child_data + [""] * 17
    elif child_type == "option":
        return [""] * 3 + child_data
    return [""] * (NUM_COLS - 10)
