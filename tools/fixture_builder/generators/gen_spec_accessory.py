"""Generator for ilL-Spec-Accessory.csv — accessory spec rows."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Accessory Item",
    "Accessory Type",
    "Profile Family",
    "Environment Rating",
    "Mounting Method",
    "Joiner System",
    "Joiner Angle",
    "Endcap Style",
    "Allowance Override per Side (mm)",
    "Leader Cable",
    "Feed Type",
    "QTY Rule Type",
    "QTY Rule Value",
]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Spec-Accessory.csv and return the filepath."""
    rows = []

    # Non-endcap accessories
    for acc in config.accessories:
        rows.append([
            acc.item_code,
            acc.accessory_type,
            acc.profile_family,
            acc.environment_rating,
            acc.mounting_method,
            acc.joiner_system,
            acc.joiner_angle,
            acc.endcap_style,
            acc.allowance_override_per_side_mm if acc.allowance_override_per_side_mm else "",
            acc.leader_cable,
            acc.feed_type,
            acc.qty_rule_type,
            acc.qty_rule_value if acc.qty_rule_value else "",
        ])

    # Endcap accessories (expanded from EndcapDef)
    for endcap_acc in config.get_all_endcap_accessories():
        rows.append([
            endcap_acc.item_code,
            endcap_acc.accessory_type,
            endcap_acc.profile_family,
            endcap_acc.environment_rating,
            endcap_acc.mounting_method,
            endcap_acc.joiner_system,
            endcap_acc.joiner_angle,
            endcap_acc.endcap_style,
            endcap_acc.allowance_override_per_side_mm if endcap_acc.allowance_override_per_side_mm else "",
            endcap_acc.leader_cable,
            endcap_acc.feed_type,
            endcap_acc.qty_rule_type if endcap_acc.qty_rule_type else "",
            endcap_acc.qty_rule_value if endcap_acc.qty_rule_value else "",
        ])

    filepath = f"{output_dir}/ilL-Spec-Accessory.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
