"""Generator for ilL-Rel-Mounting-Accessory-Map.csv."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Template Type",
    "Product Template",
    "Mounting Method",
    "Environment Rating",
    "Accessory Item",
    "QTY Rule Type",
    "QTY Rule Value",
    "Min QTY",
    "Rounding",
    "Is Active",
]

# Map config qty_rule_type values to DocType enum values
QTY_RULE_MAP = {
    "Per x mm": "PER_X_MM",
    "Per Fixture": "PER_FIXTURE",
    "Per Joint": "PER_SEGMENT",
    "Per Run": "PER_RUN",
    "PER_X_MM": "PER_X_MM",
    "PER_FIXTURE": "PER_FIXTURE",
    "PER_SEGMENT": "PER_SEGMENT",
    "PER_RUN": "PER_RUN",
}


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Rel-Mounting-Accessory-Map.csv and return the filepath."""
    rows = []

    # Get mounting accessories
    mounting_accs = [a for a in config.accessories if a.accessory_type == "Mounting"]

    for profile in config.profiles:
        for led_pkg in config.fixture_templates.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"

            for acc in mounting_accs:
                # Match accessory to this profile family
                # Accessories use XX wildcard or specific family codes
                if not _matches_family(acc.profile_family, profile.family, config.series_code):
                    continue

                qty_rule_type = QTY_RULE_MAP.get(acc.qty_rule_type, acc.qty_rule_type)
                rows.append([
                    "ilL-Fixture-Template",
                    template_code,
                    acc.mounting_method,
                    acc.environment_rating,
                    acc.item_code,
                    qty_rule_type,
                    acc.qty_rule_value if acc.qty_rule_value else 1,
                    0,       # Min QTY
                    "CEIL",  # Rounding
                    1,       # Is Active
                ])

    filepath = f"{output_dir}/ilL-Rel-Mounting-Accessory-Map.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath


def _matches_family(acc_family: str, profile_family: str, series_code: str) -> bool:
    """Check if an accessory's profile_family applies to a given profile family.

    Supports XX wildcard: if acc_family ends with XX and the prefix matches
    the profile_family prefix, it's a match. Also matches exact family codes.
    """
    if acc_family == profile_family:
        return True
    # XX wildcard: e.g. "CAXX" matches "CA01", "CA02"
    if acc_family.endswith("XX"):
        prefix = acc_family[:-2]
        return profile_family.startswith(prefix)
    return False
