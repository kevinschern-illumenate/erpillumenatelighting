"""Generator for ilL-Spec-Profile.csv — profile spec rows.

One row per profile variant. Multi-line for environment rating child rows
if more than one rating is supported.
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Item",
    "Family",
    "Variant Code",
    "Is Active?",
    "Series",
    "Width (mm)",
    "Height (mm)",
    "Stock Length (mm)",
    "Max Assembled Length (mm)",
    "Is Cuttable?",
    "Supports Joiners?",
    "Joiner System",
    "Lens Interface",
    "Environment Rating (Supported Environment Ratings)",
]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Spec-Profile.csv and return the filepath."""
    rows = []
    for profile in config.profiles:
        for finish in profile.finishes:
            item_code = f"CH-{profile.family}-{finish}"
            # First environment rating goes on the primary row
            first_rating = profile.environment_ratings[0] if profile.environment_ratings else ""
            rows.append([
                item_code,
                profile.family,
                finish,
                1,  # Is Active
                config.series_name,
                profile.width_mm,
                profile.height_mm,
                profile.stock_length_mm,
                profile.max_assembled_length_mm,
                1 if profile.is_cuttable else 0,
                1 if profile.supports_joiners else 0,
                profile.joiner_system,
                profile.lens_interface,
                first_rating,
            ])
            # Continuation rows for additional environment ratings
            for rating in profile.environment_ratings[1:]:
                row = [""] * len(HEADERS)
                row[13] = rating  # Environment Rating column
                rows.append(row)

    filepath = f"{output_dir}/ilL-Spec-Profile.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
