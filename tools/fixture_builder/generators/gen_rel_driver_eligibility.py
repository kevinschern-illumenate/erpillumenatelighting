"""Generator for ilL-Rel-Driver-Eligibility.csv."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Template Type",
    "Product Template",
    "Driver Spec",
    "Is Allowed",
    "Priority",
    "Is Active",
]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Rel-Driver-Eligibility.csv and return the filepath."""
    rows = []

    if config.product_type == "led-sheet":
        templates = [("ilL-LED-Sheet-Template", row.template_code) for row in config.led_sheet_templates]
    elif config.product_type in ("tape", "neon"):
        templates = [("ilL-Tape-Neon-Template", row.template_code) for row in config.tape_neon_templates]
    else:
        templates = [("ilL-Fixture-Template", f"ILL-{profile.family}-{package}")
                     for profile in config.profiles for package in config.fixture_templates.led_packages]
    for template_type, template_code in templates:
        for driver_spec in config.drivers.driver_specs:
            rows.append([template_type, template_code, driver_spec, 1, config.drivers.priority, 1])

    filepath = f"{output_dir}/ilL-Rel-Driver-Eligibility.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
