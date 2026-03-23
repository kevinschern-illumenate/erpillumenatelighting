"""Generator for ilL-Spec-Lens.csv — lens spec rows."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, LENS_APPEARANCE_CODES

HEADERS = [
    "Lens Item",
    "Lens Family",
    "Lens Appearance",
    "Series",
    "Stock Type",
    "Stock Length (mm)",
    "Continuous Max Length (mm)",
]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Spec-Lens.csv and return the filepath."""
    rows = []
    for lens in config.lenses:
        for appearance in lens.appearances:
            color_code = LENS_APPEARANCE_CODES.get(appearance, appearance[:2].upper())
            item_code = f"LNS-{lens.family}-{lens.shape}-{color_code}"
            rows.append([
                item_code,
                lens.family,
                appearance,
                config.series_name,
                lens.stock_type,
                lens.stock_length_mm,
                lens.continuous_max_length_mm if lens.continuous_max_length_mm else "",
            ])

    filepath = f"{output_dir}/ilL-Spec-Lens.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
