# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""Local, framework-free unit tests for the LED Sheet math core.

These tests deliberately import only from :mod:`led_sheet_math`, which has no
``frappe`` dependency, so they can be run without a Frappe/ERPNext site::

    python -m unittest illumenate_lighting.illumenate_lighting.api.test_led_sheet_math

They cover unit conversion, panel tiling, cable math, electrical grouping,
power-supply aggregation, and the include/exclude power-supply behaviour.
"""

import unittest

from illumenate_lighting.illumenate_lighting.api.led_sheet_math import (
    aggregate_power_supplies,
    build_groups,
    compute_panel_layout,
    jumper_cable_qty,
    leader_cable_qty,
    normalize_dimension,
)


def _drivers():
    """A small ascending set of eligible drivers for grouping tests."""
    return [
        {"driver_spec": "DRV-60", "driver_item": "ITEM-DRV-60", "max_wattage": 60, "priority": 1},
        {"driver_spec": "DRV-100", "driver_item": "ITEM-DRV-100", "max_wattage": 100, "priority": 2},
        {"driver_spec": "DRV-200", "driver_item": "ITEM-DRV-200", "max_wattage": 200, "priority": 3},
    ]


class TestUnitConversion(unittest.TestCase):
    def test_inches_to_feet(self):
        self.assertAlmostEqual(normalize_dimension(24, "in"), 2.0)
        self.assertAlmostEqual(normalize_dimension(6, "inch"), 0.5)
        self.assertAlmostEqual(normalize_dimension(18, "inches"), 1.5)

    def test_feet_unchanged(self):
        self.assertAlmostEqual(normalize_dimension(2, "ft"), 2.0)
        self.assertAlmostEqual(normalize_dimension(3.5, "feet"), 3.5)

    def test_default_unit_is_feet(self):
        self.assertAlmostEqual(normalize_dimension(4, None), 4.0)
        self.assertAlmostEqual(normalize_dimension(4, ""), 4.0)

    def test_zero_and_none_value(self):
        self.assertEqual(normalize_dimension(0, "in"), 0.0)
        self.assertEqual(normalize_dimension(None, "ft"), 0.0)


class TestPanelLayout(unittest.TestCase):
    def test_exact_fit(self):
        # 4ft x 6ft over 1ft x 2ft sheets = 4 wide x 3 tall = 12
        layout = compute_panel_layout(4, 6, 1, 2)
        self.assertEqual(layout["panels_wide"], 4)
        self.assertEqual(layout["panels_tall"], 3)
        self.assertEqual(layout["panels_needed"], 12)

    def test_partial_width_and_height_requires_ceil(self):
        # 3.5ft wide over 1ft sheets -> 4; 5ft tall over 2ft sheets -> 3
        layout = compute_panel_layout(3.5, 5, 1, 2)
        self.assertEqual(layout["panels_wide"], 4)
        self.assertEqual(layout["panels_tall"], 3)
        self.assertEqual(layout["panels_needed"], 12)

    def test_area_only_edge_case_differs_from_tiling(self):
        # Coverage 1.5ft x 1.5ft over 1ft x 2ft sheets.
        # Area math: ceil((1.5*1.5)/(1*2)) = ceil(2.25/2) = ceil(1.125) = 2
        # Tiling math: ceil(1.5/1) * ceil(1.5/2) = 2 * 1 = 2  (same here)
        # But 1.5ft x 2.5ft: area = ceil(3.75/2)=2; tiling = 2*2 = 4 (differs).
        layout = compute_panel_layout(1.5, 2.5, 1, 2)
        import math
        area_only = math.ceil((1.5 * 2.5) / (1 * 2))
        self.assertEqual(area_only, 2)
        self.assertEqual(layout["panels_needed"], 4)
        self.assertNotEqual(layout["panels_needed"], area_only)

    def test_invalid_sheet_dims_raise(self):
        with self.assertRaises(ValueError):
            compute_panel_layout(4, 4, 0, 2)

    def test_invalid_coverage_raises(self):
        with self.assertRaises(ValueError):
            compute_panel_layout(0, 4, 1, 2)


class TestCableMath(unittest.TestCase):
    def test_jumper_qty_is_double_panels(self):
        self.assertEqual(jumper_cable_qty(12), 24)
        self.assertEqual(jumper_cable_qty(0), 0)
        self.assertEqual(jumper_cable_qty(1), 2)

    def test_leader_qty_equals_group_count(self):
        self.assertEqual(leader_cable_qty(3), 3)
        self.assertEqual(leader_cable_qty(0), 0)


class TestGrouping(unittest.TestCase):
    def test_single_group_when_within_capacity(self):
        # 4 panels x 20W = 80W fits in the 100W or 200W driver.
        groups = build_groups(4, 20, _drivers())
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["sheet_count"], 4)
        self.assertAlmostEqual(groups[0]["group_watts"], 80)

    def test_panels_split_across_multiple_groups(self):
        # 20 panels x 20W = 400W total; capacity packs against largest (200W).
        # 200 / 20 = 10 panels per group -> 2 groups of 10.
        groups = build_groups(20, 20, _drivers())
        self.assertEqual(len(groups), 2)
        self.assertEqual(sum(g["sheet_count"] for g in groups), 20)
        for g in groups:
            self.assertLessEqual(g["group_watts"], 200)

    def test_per_group_wattage_and_driver_selection(self):
        # 15W panels; group packs to 200W -> 13 panels/group = 195W.
        groups = build_groups(13, 15, _drivers())
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertAlmostEqual(g["group_watts"], 195)
        # Smallest compatible driver for 195W is the 200W driver.
        self.assertEqual(g["compatible_driver"], "ITEM-DRV-200")
        self.assertEqual(g["driver_max_wattage"], 200)
        self.assertEqual(g["leader_cable_qty"], 1)

    def test_small_group_selects_smallest_driver(self):
        # 1 panel x 50W -> smallest compatible driver is the 60W driver.
        groups = build_groups(1, 50, _drivers())
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["compatible_driver"], "ITEM-DRV-60")

    def test_leader_per_group(self):
        groups = build_groups(20, 20, _drivers())
        self.assertEqual(leader_cable_qty(len(groups)), len(groups))
        self.assertTrue(all(g["leader_cable_qty"] == 1 for g in groups))

    def test_zero_panels_returns_no_groups(self):
        self.assertEqual(build_groups(0, 20, _drivers()), [])

    def test_no_drivers_raises(self):
        with self.assertRaises(ValueError):
            build_groups(4, 20, [])

    def test_panel_exceeds_largest_driver_raises(self):
        with self.assertRaises(ValueError):
            build_groups(2, 250, _drivers())

    def test_zero_watts_per_panel_raises(self):
        with self.assertRaises(ValueError):
            build_groups(4, 0, _drivers())


class TestPowerSupplyAggregation(unittest.TestCase):
    def test_aggregates_by_driver_item(self):
        groups = build_groups(20, 20, _drivers())  # 2 groups, both 200W driver
        supplies = aggregate_power_supplies(groups)
        self.assertEqual(len(supplies), 1)
        self.assertEqual(supplies[0]["driver_item"], "ITEM-DRV-200")
        self.assertEqual(supplies[0]["qty"], 2)
        self.assertEqual(supplies[0]["max_wattage"], 200)

    def test_aggregates_distinct_drivers(self):
        groups = [
            {"compatible_driver": "ITEM-A", "driver_spec": "A", "driver_max_wattage": 100},
            {"compatible_driver": "ITEM-A", "driver_spec": "A", "driver_max_wattage": 100},
            {"compatible_driver": "ITEM-B", "driver_spec": "B", "driver_max_wattage": 200},
        ]
        supplies = {s["driver_item"]: s for s in aggregate_power_supplies(groups)}
        self.assertEqual(supplies["ITEM-A"]["qty"], 2)
        self.assertEqual(supplies["ITEM-B"]["qty"], 1)

    def test_empty_groups(self):
        self.assertEqual(aggregate_power_supplies([]), [])


class TestIncludeExcludePowerSupply(unittest.TestCase):
    """Groups are always computed for validation visibility; power-supply lines
    are only derived when the customer opts in.  These tests exercise the pure
    building blocks that the configurator composes for that behaviour."""

    def test_included_yields_priced_supplies(self):
        groups = build_groups(20, 20, _drivers())
        include_power_supply = True
        supplies = aggregate_power_supplies(groups) if include_power_supply else []
        self.assertTrue(supplies)
        self.assertEqual(sum(s["qty"] for s in supplies), len(groups))

    def test_excluded_still_groups_but_no_supplies(self):
        groups = build_groups(20, 20, _drivers())
        include_power_supply = False
        # Grouping is still available for validation visibility ...
        self.assertTrue(groups)
        # ... but no power-supply lines are derived.
        supplies = aggregate_power_supplies(groups) if include_power_supply else []
        self.assertEqual(supplies, [])


if __name__ == "__main__":
    unittest.main()
