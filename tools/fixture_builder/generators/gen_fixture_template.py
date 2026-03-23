"""Generator for ilL-Fixture-Template.csv — fixture template definitions.

Multi-line for child tables: allowed_options, allowed_tape_offerings,
and part_number_builder.

Template code = ILL-{FAMILY}-{LED_PKG}
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, LED_PACKAGE_NAMES

HEADERS = [
    "Template Code",
    "Template Name",
    "Is Active",
    "Series",
    "Default Profile Family",
    "Default Profile Stock Len (mm)",
    "Assembled Max Len (mm)",
    "Leader Allowance mm per Fixture",
    "Base Price MSRP",
    "Price per ft MSRP",
    "Pricing Length Basis",
    "Notes",
    # allowed_options child table
    "Option Type (Allowed Options)",
    "Finish (Allowed Options)",
    "Lens Appearance (Allowed Options)",
    "Mounting Method (Allowed Options)",
    "Endcap Style (Allowed Options)",
    "Power Feed Type (Allowed Options)",
    "Environment Rating (Allowed Options)",
    "Is Default (Allowed Options)",
    "Is Active (Allowed Options)",
    # allowed_tape_offerings child table
    "Tape Offering (Allowed Tape Offerings)",
    "Is Default (Allowed Tape Offerings)",
    # part_number_builder child table
    "Section Name (Part Number Builder)",
    "Section Order (Part Number Builder)",
    "Option Code (Part Number Builder)",
    "Option Label (Part Number Builder)",
    "Option Order (Part Number Builder)",
]

NUM_COLS = len(HEADERS)


def _build_allowed_option_row(option_type, value, is_default=0, is_active=1):
    """Build the allowed_options portion of a row."""
    row = [""] * 9  # columns 12-20
    row[0] = option_type

    if option_type == "Finish":
        row[1] = value
    elif option_type == "Lens Appearance":
        row[2] = value
    elif option_type == "Mounting Method":
        row[3] = value
    elif option_type == "Endcap Style":
        row[4] = value
    elif option_type == "Power Feed Type":
        row[5] = value
    elif option_type == "Environment Rating":
        row[6] = value

    row[7] = is_default
    row[8] = is_active
    return row


def _build_tape_offering_row(tape_offering, is_default=0):
    """Build the tape_offering portion of a row."""
    return [tape_offering, is_default]


def _build_pn_builder_row(section_name, section_order, option_code, option_label, option_order):
    """Build the pn_builder portion of a row."""
    return [section_name, section_order, option_code, option_label, option_order]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Fixture-Template.csv and return the filepath."""
    rows = []
    ft = config.fixture_templates

    for profile in config.profiles:
        for led_pkg in ft.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"
            pkg_name = LED_PACKAGE_NAMES.get(led_pkg, led_pkg)
            label = profile.variant_label
            template_name = f"{config.series_name} {label} {pkg_name}" if label else f"{config.series_name} [{profile.family}] {pkg_name}"

            # Resolve per-template allowed options (override or global fallback)
            opts = config.get_options_for_template(profile.family, led_pkg)

            # Collect all child table rows we need
            child_rows = []

            # Allowed options
            for finish in (opts.allowed_finishes or profile.finishes):
                child_rows.append(("option", _build_allowed_option_row("Finish", finish)))
            for lens in opts.allowed_lenses:
                child_rows.append(("option", _build_allowed_option_row("Lens Appearance", lens)))
            for mount in opts.allowed_mountings:
                child_rows.append(("option", _build_allowed_option_row("Mounting Method", mount)))
            for es in opts.allowed_endcap_styles:
                child_rows.append(("option", _build_allowed_option_row("Endcap Style", es)))
            for pf in opts.allowed_power_feed_types:
                child_rows.append(("option", _build_allowed_option_row("Power Feed Type", pf)))
            for er in opts.allowed_environment_ratings:
                child_rows.append(("option", _build_allowed_option_row("Environment Rating", er)))

            # Tape offerings
            for i, to in enumerate(opts.tape_offerings):
                child_rows.append(("tape", _build_tape_offering_row(to, is_default=1 if i == 0 else 0)))

            # Primary row (with first child data if available)
            primary = [
                template_code,
                template_name,
                1,  # Is Active
                config.series_name,
                profile.family,
                ft.default_profile_stock_len_mm,
                ft.assembled_max_len_mm,
                ft.leader_allowance_mm_per_fixture,
                opts.base_price_msrp,
                opts.price_per_ft_msrp,
                ft.pricing_length_basis,
                "",  # Notes
            ]

            if child_rows:
                first_type, first_data = child_rows[0]
                row = primary + _expand_child(first_type, first_data)
                rows.append(row)

                # Continuation rows
                for child_type, child_data in child_rows[1:]:
                    row = [""] * 12 + _expand_child(child_type, child_data)
                    rows.append(row)
            else:
                row = primary + [""] * (NUM_COLS - 12)
                rows.append(row)

    filepath = f"{output_dir}/ilL-Fixture-Template.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath


def _expand_child(child_type, child_data):
    """Expand child data into the correct column positions."""
    # Columns: [12..20] = option (9), [21..22] = tape (2), [23..27] = pn_builder (5)
    if child_type == "option":
        return child_data + [""] * 2 + [""] * 5
    elif child_type == "tape":
        return [""] * 9 + child_data + [""] * 5
    elif child_type == "pn":
        return [""] * 9 + [""] * 2 + child_data
    return [""] * (NUM_COLS - 12)
