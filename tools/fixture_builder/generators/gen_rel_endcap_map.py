"""Generator for ilL-Rel-Endcap-Map.csv."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, FINISH_TO_ENDCAP_COLOR, ENDCAP_COLOR_NAMES

HEADERS = [
    "Fixture Template",
    "Endcap Style",
    "Endcap Color",
    "Power Feed Type",
    "Environment Rating",
    "Endcap Item",
    "Is Default",
    "Is Active",
]

STYLE_CODES = {"Solid": "NO", "Feed Through": "HO"}


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Rel-Endcap-Map.csv and return the filepath."""
    rows = []

    for profile in config.profiles:
        for led_pkg in config.fixture_templates.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"

            # Find endcap def for this profile family
            endcap_def = None
            for ec in config.endcaps:
                if ec.profile_family == profile.family:
                    endcap_def = ec
                    break

            if not endcap_def:
                continue

            for color in endcap_def.colors:
                for style in endcap_def.styles:
                    style_code = STYLE_CODES.get(style, style[:2].upper())
                    endcap_item = f"EC-{profile.family}-{color}-{style_code}"
                    color_name = ENDCAP_COLOR_NAMES.get(color, color)

                    rows.append([
                        template_code,
                        style,
                        color_name,
                        "",          # Power Feed Type
                        "",          # Environment Rating
                        endcap_item,
                        0,           # Is Default
                        1,           # Is Active
                    ])

    filepath = f"{output_dir}/ilL-Rel-Endcap-Map.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
