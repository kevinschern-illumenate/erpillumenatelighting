# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Pure calculation helpers for LED Sheet configuration.

This module intentionally has **no** ``frappe`` (or other framework) imports so
the core sizing / grouping / cable math can be unit-tested locally without a
running Frappe/ERPNext site.  Callers in ``led_sheet_configurator.py`` translate
the ``ValueError``s raised here into user-facing ``frappe.throw`` messages.
"""

import math
from typing import Any

# Units accepted for coverage width / height inputs.
INCH_UNITS = {"in", "inch", "inches", '"', "in.", "inches."}
FOOT_UNITS = {"ft", "foot", "feet", "'", "ft."}


def normalize_dimension(value: float, unit: str) -> float:
    """Return a dimension in feet given a raw ``value`` and ``unit``.

    ``unit`` of ``"in"`` (or any alias in :data:`INCH_UNITS`) divides by 12.
    Feet (the default) are returned unchanged.
    """
    value = float(value or 0)
    unit_key = (unit or "ft").strip().lower()
    if unit_key in INCH_UNITS:
        return value / 12.0
    return value


def compute_panel_layout(
    width_ft: float, height_ft: float, sheet_width_ft: float, sheet_height_ft: float
) -> dict[str, Any]:
    """Compute how many panels tile a coverage area using *actual* sheet sizes.

    Uses per-axis ``ceil`` tiling (not area-only division), so a coverage area
    whose ``width``/``height`` do not evenly divide the sheet dimensions rounds
    up on each axis independently.
    """
    if sheet_width_ft <= 0 or sheet_height_ft <= 0:
        raise ValueError("LED Sheet spec must have positive sheet width and height.")
    if width_ft <= 0 or height_ft <= 0:
        raise ValueError("Coverage width and height must be greater than zero.")
    panels_wide = int(math.ceil(width_ft / sheet_width_ft))
    panels_tall = int(math.ceil(height_ft / sheet_height_ft))
    panels_needed = panels_wide * panels_tall
    return {
        "panels_wide": panels_wide,
        "panels_tall": panels_tall,
        "panels_needed": panels_needed,
    }


def jumper_cable_qty(panels_needed: int) -> int:
    """Two jumper cables per panel."""
    return int(panels_needed or 0) * 2


def leader_cable_qty(total_groups: int) -> int:
    """One leader cable per electrical group."""
    return int(total_groups or 0)


def build_groups(
    panels_needed: int, watts_per_panel: float, drivers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Split ``panels_needed`` panels into electrical groups by driver capacity.

    ``drivers`` is a list of dicts with ``driver_spec``, ``driver_item``,
    ``max_wattage`` and ``priority`` keys (see
    ``led_sheet_configurator._get_eligible_drivers``).  Groups are packed
    against the largest eligible driver capacity, then each finalized group is
    matched to the smallest compatible driver.  Raises ``ValueError`` when the
    inputs cannot yield a valid grouping.
    """
    if panels_needed <= 0:
        return []
    if watts_per_panel <= 0:
        raise ValueError("LED Sheet spec must have total sheet watts greater than zero.")
    if not drivers:
        raise ValueError("No compatible drivers are configured for this LED Sheet template.")
    compatible_drivers = [d for d in drivers if d["max_wattage"] >= watts_per_panel]
    if not compatible_drivers:
        largest = max(drivers, key=lambda d: d["max_wattage"])
        raise ValueError(
            f"One LED Sheet ({watts_per_panel}W) exceeds the largest compatible "
            f"driver ({largest['max_wattage']}W)."
        )

    group_capacity = max(d["max_wattage"] for d in compatible_drivers)
    groups: list[dict[str, Any]] = []
    current_count = 0
    current_watts = 0.0
    for _idx in range(int(panels_needed)):
        if current_count and current_watts + watts_per_panel > group_capacity:
            groups.append(_finish_group(len(groups) + 1, current_count, current_watts, drivers))
            current_count = 0
            current_watts = 0.0
        current_count += 1
        current_watts += watts_per_panel
    if current_count:
        groups.append(_finish_group(len(groups) + 1, current_count, current_watts, drivers))
    return groups


def _finish_group(
    group_number: int, panel_count: int, group_watts: float, drivers: list[dict[str, Any]]
) -> dict[str, Any]:
    driver = next((d for d in drivers if d["max_wattage"] >= group_watts), None)
    if not driver:
        raise ValueError(f"No compatible driver can support a {group_watts}W LED Sheet group.")
    return {
        "group_number": group_number,
        "sheet_count": panel_count,
        "group_watts": round(group_watts, 3),
        "compatible_driver": driver["driver_item"],
        "driver_spec": driver["driver_spec"],
        "driver_max_wattage": driver["max_wattage"],
        "leader_cable_qty": 1,
    }


def aggregate_power_supplies(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate driver/power-supply usage across groups by driver item.

    Returns one entry per unique driver item with the number of groups that use
    it and the driver's supported wattage.
    """
    aggregated: dict[str, dict[str, Any]] = {}
    for group in groups or []:
        item = group.get("compatible_driver")
        if not item:
            continue
        entry = aggregated.setdefault(
            item,
            {
                "driver_item": item,
                "driver_spec": group.get("driver_spec"),
                "qty": 0,
                "max_wattage": group.get("driver_max_wattage"),
            },
        )
        entry["qty"] += 1
    return list(aggregated.values())
