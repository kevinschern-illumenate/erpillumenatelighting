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
    build_accessory_lines,
    build_groups,
    compute_panel_layout,
    generated_accessory_marker,
    is_generated_accessory_line,
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


class TestGeneratedAccessoryLines(unittest.TestCase):
    """The schedule line ``qty`` stays the user's bundle count; the generated
    jumper / leader / power-supply rows scale with that bundle quantity so totals
    cover every identical bundle (regression for the 13x13 double-count bug)."""

    def _power_supplies(self):
        return [
            {"driver_item": "ITEM-DRV-200", "qty": 2},
            {"driver_item": "ITEM-DRV-100", "qty": 1},
        ]

    def test_marker_is_configured_sheet_scoped(self):
        self.assertEqual(generated_accessory_marker("CLS-0001"), "for LED Sheet CLS-0001")
        self.assertNotEqual(
            generated_accessory_marker("CLS-0001"), generated_accessory_marker("CLS-0002")
        )

    def test_bundle_qty_one_keeps_per_config_quantities(self):
        # A 5ft x 5ft sheet -> 13 panels: qty 1 must NOT explode into 13x pricing.
        lines = build_accessory_lines(
            configured_name="CLS-0001",
            bundle_qty=1,
            jumper_item="ITEM-JUMPER",
            jumper_qty_per_bundle=jumper_cable_qty(13),
            leader_item="ITEM-LEADER",
            leader_qty_per_bundle=leader_cable_qty(2),
            power_supplies=self._power_supplies(),
            include_power_supply=True,
        )
        by_item = {l["item_code"]: l["qty"] for l in lines}
        self.assertEqual(by_item["ITEM-JUMPER"], 26)  # 13 panels * 2
        self.assertEqual(by_item["ITEM-LEADER"], 2)  # 2 groups
        self.assertEqual(by_item["ITEM-DRV-200"], 2)
        self.assertEqual(by_item["ITEM-DRV-100"], 1)

    def test_bundle_qty_scales_all_rows(self):
        lines = build_accessory_lines(
            configured_name="CLS-0001",
            bundle_qty=3,
            jumper_item="ITEM-JUMPER",
            jumper_qty_per_bundle=jumper_cable_qty(13),
            leader_item="ITEM-LEADER",
            leader_qty_per_bundle=leader_cable_qty(2),
            power_supplies=self._power_supplies(),
            include_power_supply=True,
        )
        by_item = {l["item_code"]: l["qty"] for l in lines}
        self.assertEqual(by_item["ITEM-JUMPER"], 78)  # 26 * 3
        self.assertEqual(by_item["ITEM-LEADER"], 6)  # 2 * 3
        self.assertEqual(by_item["ITEM-DRV-200"], 6)  # 2 * 3
        self.assertEqual(by_item["ITEM-DRV-100"], 3)  # 1 * 3

    def test_all_rows_tagged_with_marker(self):
        lines = build_accessory_lines(
            configured_name="CLS-0001",
            bundle_qty=2,
            jumper_item="ITEM-JUMPER",
            jumper_qty_per_bundle=jumper_cable_qty(4),
            leader_item="ITEM-LEADER",
            leader_qty_per_bundle=leader_cable_qty(1),
            power_supplies=self._power_supplies(),
            include_power_supply=True,
        )
        marker = generated_accessory_marker("CLS-0001")
        self.assertTrue(lines)
        for line in lines:
            self.assertIn(marker, line["notes"])

    def test_power_supply_excluded_omits_power_supply_rows(self):
        lines = build_accessory_lines(
            configured_name="CLS-0001",
            bundle_qty=2,
            jumper_item="ITEM-JUMPER",
            jumper_qty_per_bundle=jumper_cable_qty(4),
            leader_item="ITEM-LEADER",
            leader_qty_per_bundle=leader_cable_qty(1),
            power_supplies=self._power_supplies(),
            include_power_supply=False,
        )
        items = {l["item_code"] for l in lines}
        self.assertIn("ITEM-JUMPER", items)
        self.assertIn("ITEM-LEADER", items)
        self.assertNotIn("ITEM-DRV-200", items)
        self.assertNotIn("ITEM-DRV-100", items)

    def test_zero_per_config_quantities_are_skipped(self):
        lines = build_accessory_lines(
            configured_name="CLS-0001",
            bundle_qty=5,
            jumper_item="ITEM-JUMPER",
            jumper_qty_per_bundle=0,
            leader_item=None,
            leader_qty_per_bundle=0,
            power_supplies=[],
            include_power_supply=True,
        )
        self.assertEqual(lines, [])


class TestGeneratedAccessoryFiltering(unittest.TestCase):
    """Re-saving a configured LED Sheet must remove stale generated rows for both
    the old and new configured sheet while leaving unrelated lines untouched."""

    def _lines(self):
        # (manufacturer_type, notes)
        return [
            ("ILLUMENATE", "Configured LED Sheet CLS-0001 | ..."),
            ("ACCESSORY", "Jumpers " + generated_accessory_marker("CLS-0001")),
            ("ACCESSORY", "Leaders " + generated_accessory_marker("CLS-0001")),
            ("ACCESSORY", "Hand-added extra cable"),  # user accessory, keep
            ("ACCESSORY", "Power supplies " + generated_accessory_marker("CLS-0002")),
        ]

    def test_matches_only_generated_accessory_rows(self):
        rows = self._lines()
        markers = [generated_accessory_marker("CLS-0001"), generated_accessory_marker("CLS-0002")]
        kept = [r for r in rows if not is_generated_accessory_line(r[0], r[1], markers)]
        self.assertEqual(
            kept,
            [
                ("ILLUMENATE", "Configured LED Sheet CLS-0001 | ..."),
                ("ACCESSORY", "Hand-added extra cable"),
            ],
        )

    def test_non_accessory_rows_never_match(self):
        markers = [generated_accessory_marker("CLS-0001")]
        self.assertFalse(
            is_generated_accessory_line("ILLUMENATE", "Jumpers for LED Sheet CLS-0001", markers)
        )

    def test_unrelated_configured_sheet_not_removed(self):
        rows = self._lines()
        markers = [generated_accessory_marker("CLS-0001")]  # only the old sheet
        kept = [r for r in rows if not is_generated_accessory_line(r[0], r[1], markers)]
        # The CLS-0002 power supply row survives because its marker is not targeted.
        self.assertIn(("ACCESSORY", "Power supplies " + generated_accessory_marker("CLS-0002")), kept)


if __name__ == "__main__":
    unittest.main()
