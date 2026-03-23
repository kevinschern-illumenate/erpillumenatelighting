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

    for profile in config.profiles:
        for led_pkg in config.fixture_templates.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"

            for driver_spec in config.drivers.driver_specs:
                rows.append([
                    "ilL-Fixture-Template",
                    template_code,
                    driver_spec,
                    1,                          # Is Allowed
                    config.drivers.priority,    # Priority
                    1,                          # Is Active
                ])

    filepath = f"{output_dir}/ilL-Rel-Driver-Eligibility.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
