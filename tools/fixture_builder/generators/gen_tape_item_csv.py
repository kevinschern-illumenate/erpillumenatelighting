"""Generator for tape/neon Item CSV.csv — ERPNext Item master data for LED Tape / LED Neon."""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv, TAPE_ITEM_GROUPS

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


def _row(item_code, item_group, item_name, brand, warranty_days, supplier=""):
    """Build a primary Item row for a tape/neon spec (non-variant)."""
    return [
        item_code,
        item_group,
        "Meter",
        item_name,
        1,                      # Maintain Stock
        0,                      # Has Variants (tape specs are not templates)
        brand,
        warranty_days,
        "",                     # Variant Of
        "",                     # Variant Based On
        "",                     # Attribute
        supplier,
        "",                     # Supplier Description
        "",                     # Supplier Part Number
    ]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate Item CSV.csv for tape/neon specs and return the filepath."""
    rows = []

    for ts in config.tape_specs:
        item_group = TAPE_ITEM_GROUPS.get(ts.product_category, ts.product_category)
        item_name = f"{config.series_name} {ts.led_package} {ts.product_category}"
        if ts.watts_per_foot:
            item_name += f" {ts.watts_per_foot}W/ft"

        rows.append(_row(
            item_code=ts.item_code,
            item_group=item_group,
            item_name=item_name,
            brand=config.brand,
            warranty_days=config.warranty_days,
            supplier=config.supplier,
        ))

    filepath = f"{output_dir}/Item CSV.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
