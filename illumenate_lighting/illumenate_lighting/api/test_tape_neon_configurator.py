# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Tests for the LED Tape / LED Neon Configurator Engine.

Tests cover:
  - Length parsing (inches, feet, feet+inches)
  - Manufacturable length snapping to cut increment
  - Free cutting behaviour
  - Part number generation
  - Validation for missing fields
  - Neon multi-segment validation
"""

import json
import unittest
from unittest.mock import MagicMock, patch

# ── Import helpers under test directly ──
# We import the private helpers and constants from the module
from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
    MM_PER_FOOT,
    MM_PER_INCH,
    INCHES_PER_FOOT,
    _parse_tape_length,
    _parse_neon_fixture_length,
)


class TestParseTapeLength(unittest.TestCase):
    """Test _parse_tape_length with various unit modes."""

    def test_inches(self):
        sel = {"tape_length_unit": "in", "tape_length_value": 24}
        result = _parse_tape_length(sel)
        self.assertAlmostEqual(result, 24 * MM_PER_INCH, places=2)

    def test_feet(self):
        sel = {"tape_length_unit": "ft", "tape_length_value": 10}
        result = _parse_tape_length(sel)
        self.assertAlmostEqual(result, 10 * MM_PER_FOOT, places=2)

    def test_feet_and_inches(self):
        sel = {"tape_length_unit": "ft_in", "tape_length_feet": 3, "tape_length_inches": 6}
        result = _parse_tape_length(sel)
        expected = (3 * INCHES_PER_FOOT + 6) * MM_PER_INCH
        self.assertAlmostEqual(result, expected, places=2)

    def test_default_unit_is_inches(self):
        sel = {"tape_length_value": 12}
        result = _parse_tape_length(sel)
        self.assertAlmostEqual(result, 12 * MM_PER_INCH, places=2)

    def test_zero_length(self):
        sel = {"tape_length_unit": "in", "tape_length_value": 0}
        result = _parse_tape_length(sel)
        self.assertEqual(result, 0)

    def test_missing_value(self):
        sel = {"tape_length_unit": "in"}
        result = _parse_tape_length(sel)
        self.assertEqual(result, 0)


class TestParseNeonFixtureLength(unittest.TestCase):
    """Test _parse_neon_fixture_length."""

    def test_inches(self):
        seg = {"fixture_length_unit": "in", "fixture_length_value": 48}
        result = _parse_neon_fixture_length(seg)
        self.assertAlmostEqual(result, 48 * MM_PER_INCH, places=2)

    def test_feet(self):
        seg = {"fixture_length_unit": "ft", "fixture_length_value": 5}
        result = _parse_neon_fixture_length(seg)
        self.assertAlmostEqual(result, 5 * MM_PER_FOOT, places=2)

    def test_feet_and_inches(self):
        seg = {"fixture_length_unit": "ft_in", "fixture_length_feet": 2, "fixture_length_inches": 3}
        result = _parse_neon_fixture_length(seg)
        expected = (2 * INCHES_PER_FOOT + 3) * MM_PER_INCH
        self.assertAlmostEqual(result, expected, places=2)


class TestManufacturableLengthSnapping(unittest.TestCase):
    """
    Test the cut increment snapping logic extracted from validate_tape_configuration.

    We replicate the core snapping algorithm here to test without Frappe context.
    """

    @staticmethod
    def snap_to_cut_increment(requested_mm, cut_increment_mm, is_free_cutting):
        """Replicate the snapping logic from validate_tape_configuration."""
        import math
        if is_free_cutting or cut_increment_mm <= 0:
            return requested_mm
        increments = math.floor(requested_mm / cut_increment_mm)
        if increments < 1:
            increments = 1
        return increments * cut_increment_mm

    def test_exact_multiple(self):
        """When requested length is exact multiple of cut increment."""
        result = self.snap_to_cut_increment(500, 50, False)
        self.assertEqual(result, 500)

    def test_rounds_down(self):
        """Rounds down to nearest cut increment."""
        result = self.snap_to_cut_increment(530, 50, False)
        self.assertEqual(result, 500)

    def test_free_cutting_returns_exact(self):
        """Free cutting returns the exact requested length."""
        result = self.snap_to_cut_increment(537, 50, True)
        self.assertEqual(result, 537)

    def test_minimum_one_increment(self):
        """If requested length is less than one increment, use one increment."""
        result = self.snap_to_cut_increment(10, 50, False)
        self.assertEqual(result, 50)

    def test_zero_cut_increment_returns_exact(self):
        """If cut increment is 0, return exact requested length."""
        result = self.snap_to_cut_increment(123, 0, False)
        self.assertEqual(result, 123)

    def test_large_tape(self):
        """Test with a typical 16.67mm (5/8 inch) cut increment over 10 feet."""
        requested = 10 * MM_PER_FOOT  # 3048 mm
        cut = 16.67
        result = self.snap_to_cut_increment(requested, cut, False)
        # Should be floor(3048/16.67)*16.67 = 182*16.67 = 3033.94
        import math
        expected = math.floor(3048 / 16.67) * 16.67
        self.assertAlmostEqual(result, expected, places=2)


class TestPartNumberBuilding(unittest.TestCase):
    """Test part number format for LED Tape and LED Neon."""

    def test_tape_part_number_uses_spec_name(self):
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _build_tape_part_number,
        )

        sel = {
            "environment_rating": None,
            "cct": "3000K",
            "output_level": "Standard",
            "pcb_mounting": "Rigid",
            "pcb_finish": "White",
            "feed_type": "Standard",
            "lead_length_inches": 12,
            "tape_length_unit": "in",
            "tape_length_value": 120,
        }
        tape_spec = MagicMock()
        tape_spec.name = "TAPE-001"
        tape_offering = MagicMock()
        tape_offering.name = "TO-001"

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator._get_code",
            return_value="xx",
        ), patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.return_value = None
            pn = _build_tape_part_number(sel, tape_spec, tape_offering, 120 * 25.4)

        self.assertTrue(pn.startswith("TAPE-001"))
        self.assertTrue(pn.endswith("-C"))

    def test_neon_part_number_uses_spec_name_and_jumper(self):
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _build_neon_part_number,
        )

        sel = {
            "cct": "4000K",
            "output_level": "High",
            "mounting": "Surface",
            "finish": "Black",
        }
        tape_spec = MagicMock()
        tape_spec.name = "NEON-001"
        tape_offering = MagicMock()
        tape_offering.name = "NO-001"
        segments = [
            {
                "segment_index": 1,
                "manufacturable_length_in": 48,
                "ip_rating": "IP67",
                "start_feed_direction": "End",
                "start_lead_length_inches": 12,
                "end_feed_direction": "End",
                "end_feed_length_inches": 6,
            },
            {
                "segment_index": 2,
                "manufacturable_length_in": 24,
                "ip_rating": "IP67",
                "start_feed_direction": "End",
                "start_lead_length_inches": 6,
                "end_feed_direction": "End",
                "end_feed_length_inches": 6,
            },
        ]

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator._get_code",
            return_value="xx",
        ), patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.return_value = None
            mock_frappe.db.exists.return_value = False
            pn = _build_neon_part_number(sel, tape_spec, tape_offering, segments)

        self.assertTrue(pn.startswith("NEON-001"))
        self.assertIn("J(", pn)


class TestSOLineCreation(unittest.TestCase):
    """Test create_tape_neon_so_lines helper."""

    def test_tape_creates_two_lines(self):
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            create_tape_neon_so_lines,
        )

        so = MagicMock()
        items = []
        so.append = lambda table_name, d=None: items.append(MagicMock()) or items[-1]

        line = MagicMock()
        config_data = {
            "product_category": "LED Tape",
            "part_number": "ILL-TAPE-xxxx",
            "build_description": "Test tape",
            "computed": {
                "lead_length_inches": 12,
                "manufacturable_length_in": 120,
            },
            "resolved_items": {
                "tape_item": "ITEM-TAPE-001",
                "leader_cable_item": "ITEM-LEAD-001",
            },
            "selections": {},
        }

        result = create_tape_neon_so_lines(so, line, config_data)
        self.assertEqual(result["items_added"], 2)
        self.assertEqual(len(items), 2)
        # First item should be leader cable
        self.assertEqual(items[0].item_code, "ITEM-LEAD-001")
        self.assertEqual(items[0].qty, 12)
        # Second item should be tape
        self.assertEqual(items[1].item_code, "ITEM-TAPE-001")
        self.assertEqual(items[1].qty, 120)

    def test_neon_creates_lines_per_segment(self):
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            create_tape_neon_so_lines,
        )

        so = MagicMock()
        items = []
        so.append = lambda table_name, d=None: items.append(MagicMock()) or items[-1]

        line = MagicMock()
        config_data = {
            "product_category": "LED Neon",
            "part_number": "ILL-NEON-xxxx",
            "build_description": "Test neon",
            "computed": {
                "segments": [
                    {
                        "segment_index": 1,
                        "start_lead_length_inches": 12,
                        "manufacturable_length_in": 48,
                        "end_feed_length_inches": 6,
                    },
                ],
            },
            "resolved_items": {
                "tape_item": "ITEM-NEON-001",
                "leader_cable_item": "ITEM-LEAD-001",
            },
            "selections": {},
        }

        result = create_tape_neon_so_lines(so, line, config_data)
        # Segment 1: leader cable + neon tape + jumper cable = 3 items
        self.assertEqual(result["items_added"], 3)


class TestBuildTemplateOptionsFallback(unittest.TestCase):
    """Test _build_template_options fallback behaviour when no allowed option rows exist."""

    def test_tape_options_derived_from_specs_when_no_allowed_rows(self):
        """When allowed_option_rows is empty, options should be derived from tape specs."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _build_template_options,
        )

        tape_offerings = [
            MagicMock(cct="3000K", output_level="Standard", name="TO-1", tape_spec="SPEC-1"),
            MagicMock(cct="4000K", output_level="High", name="TO-2", tape_spec="SPEC-1"),
        ]
        tape_specs = [
            MagicMock(name="SPEC-1", pcb_mounting="Rigid", pcb_finish="White"),
        ]

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = lambda dt, name, fields, as_dict=False: {
                "name": name, "code": "xx", "kelvin": 3000, "description": "",
                "value": 100, "sku_code": "xx", "notes": "",
            }
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.has_column.return_value = True
            mock_frappe.get_all.return_value = [
                MagicMock(name="IP67", code="67", notes=""),
            ]

            # Empty allowed_option_rows → should derive from specs/offerings
            options = _build_template_options([], tape_offerings, tape_specs, "LED Tape")

        self.assertIn("ccts", options)
        self.assertIn("output_levels", options)
        self.assertIn("pcb_mountings", options)
        self.assertIn("pcb_finishes", options)
        self.assertEqual(len(options["pcb_mountings"]), 1)
        self.assertEqual(options["pcb_mountings"][0]["value"], "Rigid")

    def test_neon_options_derived_from_specs_when_no_allowed_rows(self):
        """When allowed_option_rows is empty for neon, mounting + finish come from specs."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _build_template_options,
        )

        tape_offerings = [
            MagicMock(cct="4000K", output_level="Standard", name="NO-1", tape_spec="NSPEC-1"),
        ]
        tape_specs = [
            MagicMock(name="NSPEC-1", pcb_mounting="Surface", pcb_finish="Black"),
        ]

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = lambda dt, name, fields, as_dict=False: {
                "name": name, "code": "xx", "kelvin": 4000, "description": "",
                "value": 100, "sku_code": "xx", "notes": "",
            }
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.has_column.return_value = True
            mock_frappe.get_all.return_value = [
                MagicMock(name="IP67", code="67", notes=""),
            ]

            options = _build_template_options([], tape_offerings, tape_specs, "LED Neon")

        self.assertIn("ccts", options)
        self.assertIn("output_levels", options)
        self.assertIn("mounting_methods", options)
        self.assertIn("finishes", options)
        self.assertIn("ip_ratings", options)
        self.assertEqual(len(options["mounting_methods"]), 1)
        self.assertEqual(options["mounting_methods"][0]["value"], "Surface")
        self.assertEqual(len(options["finishes"]), 1)
        self.assertEqual(options["finishes"][0]["value"], "Black")


class TestComputeTapeNeonPricing(unittest.TestCase):
    """Test _compute_tape_neon_pricing helper."""

    def test_tape_pricing_foot_uom(self):
        """Tape priced per Foot with length in mm."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
            MM_PER_FOOT,
        )

        # 10 feet of tape at $5.00/ft = $50.00
        length_mm = 10 * MM_PER_FOOT

        def mock_get_value(doctype, filters, field=None, **kwargs):
            if doctype == "Item Price" and filters.get("item_code") == "TAPE-001":
                return 5.0
            if doctype == "Item" and filters == "TAPE-001":
                return "Foot"
            return None

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            result = _compute_tape_neon_pricing("TAPE-001", None, length_mm)

        self.assertAlmostEqual(result["total_price_msrp"], 50.0, places=2)

    def test_tape_pricing_inch_uom(self):
        """Tape priced per Inch with length in mm."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
            MM_PER_INCH,
        )

        # 120 inches of tape at $0.50/in = $60.00
        length_mm = 120 * MM_PER_INCH

        def mock_get_value(doctype, filters, field=None, **kwargs):
            if doctype == "Item Price" and filters.get("item_code") == "TAPE-002":
                return 0.5
            if doctype == "Item" and filters == "TAPE-002":
                return "Inch"
            return None

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            result = _compute_tape_neon_pricing("TAPE-002", None, length_mm)

        self.assertAlmostEqual(result["total_price_msrp"], 60.0, places=2)

    def test_tape_pricing_meter_uom(self):
        """Tape priced per Meter with length in mm."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
        )

        # 5 meters of tape at $10.00/m = $50.00
        length_mm = 5000

        def mock_get_value(doctype, filters, field=None, **kwargs):
            if doctype == "Item Price" and filters.get("item_code") == "TAPE-003":
                return 10.0
            if doctype == "Item" and filters == "TAPE-003":
                return "Meter"
            return None

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            result = _compute_tape_neon_pricing("TAPE-003", None, length_mm)

        self.assertAlmostEqual(result["total_price_msrp"], 50.0, places=2)

    def test_tape_plus_leader_cable_pricing(self):
        """Tape + leader cable pricing combined."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
            MM_PER_FOOT,
        )

        # 10 ft tape at $5/ft = $50, leader cable 12 inches at $1/in = $12 → total $62
        length_mm = 10 * MM_PER_FOOT

        def mock_get_value(doctype, filters, field=None, **kwargs):
            if doctype == "Item Price":
                item = filters.get("item_code")
                if item == "TAPE-001":
                    return 5.0
                if item == "LEAD-001":
                    return 1.0
            if doctype == "Item" and filters == "TAPE-001":
                return "Foot"
            return None

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            result = _compute_tape_neon_pricing("TAPE-001", "LEAD-001", length_mm, 12)

        self.assertAlmostEqual(result["total_price_msrp"], 62.0, places=2)

    def test_no_tape_item_returns_zero(self):
        """When tape_item is None, total should be 0."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
        )

        result = _compute_tape_neon_pricing(None, None, 3048)
        self.assertEqual(result["total_price_msrp"], 0)

    def test_no_item_price_returns_zero(self):
        """When no Item Price exists, total should be 0."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
        )

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.return_value = None
            result = _compute_tape_neon_pricing("TAPE-001", None, 3048)

        self.assertEqual(result["total_price_msrp"], 0)

    def test_zero_length_returns_zero(self):
        """When length is 0, total should be 0."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_tape_neon_pricing,
        )

        result = _compute_tape_neon_pricing("TAPE-001", None, 0)
        self.assertEqual(result["total_price_msrp"], 0)


class TestComputeTemplateTapeNeonPricing(unittest.TestCase):
    """Test _compute_template_tape_neon_pricing helper."""

    def test_known_values_tape(self):
        """Base=$50, per_ft=$15, 15ft → $50 + $225 = $275 + adders."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
            MM_PER_FOOT,
        )

        length_mm = 15 * MM_PER_FOOT

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.return_value = {
                "base_price_msrp": 50.0,
                "price_per_ft_msrp": 15.0,
            }
            mock_frappe.get_all.return_value = []

            result = _compute_template_tape_neon_pricing(
                "TMPL-001", {"cct": "3000K"}, length_mm, is_neon=False
            )

        self.assertAlmostEqual(result["total_price_msrp"], 275.0, places=2)
        self.assertIsInstance(result["adder_breakdown"], list)
        # Should have base + length entries
        components = [a["component"] for a in result["adder_breakdown"]]
        self.assertIn("base", components)
        self.assertIn("length", components)

    def test_known_values_with_option_adders(self):
        """Base=$50, per_ft=$15, 15ft + $10 CCT adder → $285."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
            MM_PER_FOOT,
        )

        length_mm = 15 * MM_PER_FOOT

        def mock_get_value(doctype, filters, fields=None, as_dict=False, **kwargs):
            if doctype == "ilL-Tape-Neon-Template":
                return {
                    "base_price_msrp": 50.0,
                    "price_per_ft_msrp": 15.0,
                }
            return None

        def mock_get_all(doctype, filters=None, fields=None, **kwargs):
            if doctype == "ilL-Child-Tape-Neon-Allowed-Option":
                if filters and filters.get("option_type") == "CCT":
                    return [MagicMock(msrp_adder=10.0)]
            return []

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            mock_frappe.get_all.side_effect = mock_get_all

            result = _compute_template_tape_neon_pricing(
                "TMPL-001",
                {"cct": "3000K", "output_level": "Standard"},
                length_mm,
                is_neon=False,
            )

        # $50 base + $225 length + $10 CCT = $285
        self.assertAlmostEqual(result["total_price_msrp"], 285.0, places=2)
        components = [a["component"] for a in result["adder_breakdown"]]
        self.assertIn("cct", components)

    def test_zero_template_pricing_returns_zero(self):
        """When template has zero pricing fields, returns $0."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
            MM_PER_FOOT,
        )

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.return_value = {
                "base_price_msrp": 0,
                "price_per_ft_msrp": 0,
            }
            mock_frappe.get_all.return_value = []

            result = _compute_template_tape_neon_pricing(
                "TMPL-002", {"cct": "3000K"}, 15 * MM_PER_FOOT, is_neon=False
            )

        self.assertEqual(result["total_price_msrp"], 0)
        self.assertIsInstance(result["adder_breakdown"], list)

    def test_no_template_name_returns_zero(self):
        """When template_name is None/empty, returns $0."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
        )

        result = _compute_template_tape_neon_pricing(None, {}, 3048)
        self.assertEqual(result["total_price_msrp"], 0)
        self.assertEqual(result["adder_breakdown"], [])

    def test_template_not_found_returns_zero(self):
        """When template doesn't exist in DB, returns $0."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
        )

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.return_value = None

            result = _compute_template_tape_neon_pricing(
                "TMPL-MISSING", {"cct": "3000K"}, 3048
            )

        self.assertEqual(result["total_price_msrp"], 0)
        self.assertEqual(result["adder_breakdown"], [])

    def test_leader_cable_pricing_applies(self):
        """Leader cable pricing adds to total when _leader_cable_item is in selections."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
            MM_PER_FOOT,
        )

        length_mm = 10 * MM_PER_FOOT

        def mock_get_value(doctype, filters, fields=None, as_dict=False, **kwargs):
            if doctype == "ilL-Tape-Neon-Template":
                return {
                    "base_price_msrp": 50.0,
                    "price_per_ft_msrp": 10.0,
                }
            if doctype == "Item Price" and isinstance(filters, dict):
                if filters.get("item_code") == "LEAD-001":
                    return 2.0
            return None

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            mock_frappe.get_all.return_value = []

            result = _compute_template_tape_neon_pricing(
                "TMPL-001",
                {"cct": "3000K", "_leader_cable_item": "LEAD-001"},
                length_mm,
                lead_length_inches=12,
                is_neon=False,
            )

        # $50 base + $100 length (10ft × $10) + $24 leader (12in × $2) = $174
        self.assertAlmostEqual(result["total_price_msrp"], 174.0, places=2)
        components = [a["component"] for a in result["adder_breakdown"]]
        self.assertIn("leader_cable", components)

    def test_neon_option_map(self):
        """LED Neon uses neon-specific option map (mounting_method, finish)."""
        from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
            _compute_template_tape_neon_pricing,
            MM_PER_FOOT,
        )

        length_mm = 10 * MM_PER_FOOT

        def mock_get_value(doctype, filters, fields=None, as_dict=False, **kwargs):
            if doctype == "ilL-Tape-Neon-Template":
                return {
                    "base_price_msrp": 100.0,
                    "price_per_ft_msrp": 20.0,
                }
            return None

        def mock_get_all(doctype, filters=None, fields=None, **kwargs):
            if doctype == "ilL-Child-Tape-Neon-Allowed-Option":
                if filters and filters.get("option_type") == "Mounting Method":
                    return [MagicMock(msrp_adder=5.0)]
                if filters and filters.get("option_type") == "Finish":
                    return [MagicMock(msrp_adder=3.0)]
            return []

        with patch(
            "illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.frappe"
        ) as mock_frappe:
            mock_frappe.db.get_value.side_effect = mock_get_value
            mock_frappe.get_all.side_effect = mock_get_all

            result = _compute_template_tape_neon_pricing(
                "TMPL-NEON",
                {"cct": "4000K", "mounting": "Surface", "finish": "Black"},
                length_mm,
                is_neon=True,
            )

        # $100 base + $200 length (10ft × $20) + $5 mounting + $3 finish = $308
        self.assertAlmostEqual(result["total_price_msrp"], 308.0, places=2)


if __name__ == "__main__":
    unittest.main()
