"""Generator for ilL-Rel-Tape Offering.csv — tape offering rows.

One row per TapeOfferingDef (tape_spec × CCT × output_level matrix).
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Tape Spec",
    "CCT",
    "CRI",
    "SDCM",
    "LED Package",
    "Output Level",
    "Watts per Ft Override",
    "Cut Increment mm Override",
]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Rel-Tape Offering.csv and return the filepath."""
    rows = []

    for offering in config.tape_offerings:
        rows.append([
            offering.tape_spec,
            offering.cct,
            offering.cri,
            offering.sdcm,
            offering.led_package,
            offering.output_level,
            offering.watts_per_ft_override or "",
            offering.cut_increment_mm_override or "",
        ])

    filepath = f"{output_dir}/ilL-Rel-Tape Offering.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
