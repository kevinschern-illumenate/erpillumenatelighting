"""Generator for ilL-Rel-Profile Lens.csv — profile-to-lens compatibility.

Multi-line format: first row has profile spec + first lens,
continuation rows have only lens spec in the child column.
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, LENS_APPEARANCE_CODES

HEADERS = [
    "Profile Spec",
    "Is Active",
    "Notes",
    "Lens Spec (Compatible Lenses)",
]


def _get_lens_items(config: FixtureBuilderConfig, lens_family: str) -> list[str]:
    """Get all lens item codes for a given lens family."""
    items = []
    for lens in config.lenses:
        if lens.family == lens_family:
            for appearance in lens.appearances:
                color_code = LENS_APPEARANCE_CODES.get(appearance, appearance[:2].upper())
                items.append(f"LNS-{lens.family}-{lens.shape}-{color_code}")
    return items


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Rel-Profile Lens.csv and return the filepath."""
    rows = []

    # Build mapping: profile_family → lens_family
    family_to_lens = {}
    for mapping in config.profile_lens_mappings:
        for pfam in mapping.profile_families:
            family_to_lens[pfam] = mapping.lens_family

    for profile in config.profiles:
        lens_family = family_to_lens.get(profile.family, "")
        if not lens_family:
            continue

        lens_items = _get_lens_items(config, lens_family)
        if not lens_items:
            continue

        for finish in profile.finishes:
            profile_spec = f"CH-{profile.family}-{finish}"
            # First row: profile spec + first lens
            rows.append([
                profile_spec,
                1,
                "",
                lens_items[0],
            ])
            # Continuation rows for additional lenses
            for lens_item in lens_items[1:]:
                rows.append(["", "", "", lens_item])

    filepath = f"{output_dir}/ilL-Rel-Profile Lens.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
