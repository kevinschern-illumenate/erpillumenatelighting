"""Generator for Item CSV.csv — ERPNext Item master data import.

Handles multi-line continuation rows for variant attributes.
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig, FINISH_NAMES
from .common import write_csv, ITEM_GROUPS, LENS_APPEARANCE_CODES

HEADERS = [
    "Item Code",
    "Item Group",
    "Default Unit of Measure",
    "Item Name",
    "Maintain Stock",
    "Has Variants",
    "Brand",
    "Warranty Period (in days)",
    "Variant Of",
    "Variant Based On",
    "Attribute (Variant Attributes)",
    "Supplier (Supplier Items)",
    "Supplier Description (Supplier Items)",
    "Supplier Part Number (Supplier Items)",
]


def _row(item_code, item_group, item_name, has_variants, brand, warranty_days,
         attribute="", supplier="", variant_of="", variant_based_on=""):
    """Build a primary Item row."""
    return [
        item_code,
        item_group,
        "Ea",
        item_name,
        1,                      # Maintain Stock
        1 if has_variants else 0,
        brand,
        warranty_days,
        variant_of,
        variant_based_on if has_variants else "",
        attribute,
        supplier,
        "",                     # Supplier Description
        "",                     # Supplier Part Number
    ]


def _continuation_row(attribute):
    """Build a continuation row (only the Attribute column populated)."""
    row = [""] * len(HEADERS)
    row[10] = attribute  # Attribute (Variant Attributes)
    return row


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate Item CSV.csv and return the filepath."""
    rows = []

    # ── Profile template Items ──
    for profile in config.profiles:
        label = profile.variant_label
        display = f"{config.series_name} {label}-Profile" if label else f"{config.series_name} [{profile.family}]-Profile"
        rows.append(_row(
            item_code=f"CH-{profile.family}",
            item_group=ITEM_GROUPS["profile"],
            item_name=display,
            has_variants=True,
            brand=config.brand,
            warranty_days=config.warranty_days,
            attribute="Finish",
            supplier=config.supplier,
            variant_based_on="Item Attribute",
        ))

    # ── Lens template Items ──
    for lens in config.lenses:
        # Determine display name
        if lens.family.endswith("XX"):
            display = f"{config.series_name} Series-Lens"
        else:
            label = ""
            for p in config.profiles:
                if p.family == lens.family:
                    label = p.variant_label
                    break
            display = f"{config.series_name} {label}-Lens" if label else f"{config.series_name} [{lens.family}]-Lens"

        rows.append(_row(
            item_code=f"LNS-{lens.family}",
            item_group=ITEM_GROUPS["lens"],
            item_name=display,
            has_variants=True,
            brand=config.brand,
            warranty_days=config.warranty_days,
            attribute="Lens Style",
            supplier=config.supplier,
            variant_based_on="Item Attribute",
        ))
        # Continuation row for Lens Color attribute
        rows.append(_continuation_row("Lens Color"))

    # ── Accessory Items (non-variant) ──
    for acc in config.accessories:
        if acc.accessory_type == "Endcap":
            continue  # Endcaps handled separately

        if acc.accessory_type == "Joiner":
            item_group = ITEM_GROUPS["accessory_joiner"]
            # Derive display name from item code
            display = f"{config.series_name} Series-{_joiner_display_name(acc)}"
        else:
            item_group = ITEM_GROUPS["accessory_mounting"]
            display = f"{config.series_name} Series-{acc.mounting_method}"
            if not acc.mounting_method:
                display = f"{config.series_name}-{acc.item_code}"

        rows.append(_row(
            item_code=acc.item_code,
            item_group=item_group,
            item_name=display,
            has_variants=False,
            brand=config.brand,
            warranty_days=config.warranty_days,
            supplier=config.supplier,
        ))

    # ── Endcap template Items (variant: Endcap Color × Endcap Type) ──
    for endcap in config.endcaps:
        label = config.get_profile_variant_label(endcap.profile_family)
        display = f"{config.series_name} {label}-Endcaps" if label else f"{config.series_name} [{endcap.profile_family}]-Endcaps"

        rows.append(_row(
            item_code=f"EC-{endcap.profile_family}",
            item_group=ITEM_GROUPS["endcap"],
            item_name=display,
            has_variants=True,
            brand=config.brand,
            warranty_days=config.warranty_days,
            attribute="Endcap Color",
            supplier=config.supplier,
            variant_based_on="Item Attribute",
        ))
        # Continuation row for Endcap Type attribute
        rows.append(_continuation_row("Endcap Type"))

    filepath = f"{output_dir}/Item CSV.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath


def _joiner_display_name(acc):
    """Derive a human-readable joiner name from the accessory def."""
    angle_map = {
        "180° Straight": "180° Straight Connector",
        "90° Horizontal": "90° Horizontal Connector",
        "90° Vertical": "90° Vertical Connector",
        "120° Horizontal": "120° Horizontal Connector",
        "X Connector": "X Connector",
    }
    if acc.joiner_angle:
        return angle_map.get(acc.joiner_angle, f"{acc.joiner_angle} Connector")
    # Guess from item code suffix
    suffix = acc.item_code.split("-")[-1]
    suffix_map = {
        "S": "180° Straight Connector",
        "H": "90° Horizontal Connector",
        "V": "90° Vertical Connector",
        "X": "X Connector",
        "T": "T Connector",
        "120": "120° Horizontal Connector",
    }
    return suffix_map.get(suffix, "Connector")
