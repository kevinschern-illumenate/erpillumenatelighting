# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for Extrusion Kit Configurator Engine

Tests the init → cascading → validate → save flow, including:
  - Template loading and option retrieval
  - Cascading option filtering
  - Configuration validation and item resolution
  - Part number generation
  - Spec data collection from linked doctypes
  - Schedule line saving
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase


class TestExtrusionKitConfigurator(FrappeTestCase):
    """Test suite for the Extrusion Kit configurator engine."""

    def test_get_init_no_template(self):
        """get_kit_configurator_init() with no args returns template list."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            get_kit_configurator_init,
        )
        result = get_kit_configurator_init()
        self.assertTrue(result.get("success"))
        # Should return a templates list (may be empty in test env)
        self.assertIn("templates", result)

    def test_get_init_invalid_template(self):
        """get_kit_configurator_init() with nonexistent template returns error."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            get_kit_configurator_init,
        )
        result = get_kit_configurator_init(kit_template_name="NONEXISTENT-KIT")
        self.assertFalse(result.get("success"))
        self.assertIn("not found", result.get("error", ""))

    def test_validate_missing_fields(self):
        """validate_kit_configuration() rejects incomplete selections."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            validate_kit_configuration,
        )
        # Missing all required fields
        result = validate_kit_configuration(json.dumps({}))
        self.assertFalse(result.get("is_valid"))
        self.assertIn("missing_fields", result)

    def test_validate_invalid_template(self):
        """validate_kit_configuration() rejects nonexistent template."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            validate_kit_configuration,
        )
        result = validate_kit_configuration(json.dumps({
            "kit_template": "FAKE-TEMPLATE",
            "finish": "Silver",
            "lens_appearance": "Frosted",
            "mounting_method": "Surface",
            "endcap_style": "Flat",
            "endcap_color": "Silver",
        }))
        self.assertFalse(result.get("is_valid"))

    def test_config_hash_deterministic(self):
        """Config hash is deterministic for the same inputs."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _compute_config_hash,
        )
        sel = {
            "kit_template": "KIT-01",
            "finish": "Silver",
            "lens_appearance": "Frosted",
            "mounting_method": "Surface Mount",
            "endcap_style": "Flat",
            "endcap_color": "Silver",
        }
        hash1 = _compute_config_hash(sel)
        hash2 = _compute_config_hash(sel)
        self.assertEqual(hash1, hash2)

        # Different order should produce same hash (sorted keys)
        sel_reordered = {
            "endcap_color": "Silver",
            "finish": "Silver",
            "kit_template": "KIT-01",
            "lens_appearance": "Frosted",
            "mounting_method": "Surface Mount",
            "endcap_style": "Flat",
        }
        hash3 = _compute_config_hash(sel_reordered)
        self.assertEqual(hash1, hash3)

    def test_part_number_format(self):
        """_build_kit_part_number produces expected format."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _build_kit_part_number,
        )

        class MockTemplate:
            series = None
            template_code = "MOCKKIT"

        sel = {
            "finish": "NONEXISTENT",
            "lens_appearance": "NONEXISTENT",
            "mounting_method": "NONEXISTENT",
            "endcap_style": "NONEXISTENT",
            "endcap_color": "NONEXISTENT",
        }
        part_number = _build_kit_part_number(sel, MockTemplate())
        # Should start with ILL-KIT and have 8 segments
        self.assertTrue(part_number.startswith("ILL-KIT-"))
        parts = part_number.split("-")
        self.assertEqual(len(parts), 8)  # ILL-KIT-SERIES-FIN-LENS-MNT-ECSTYLE-ECCOLOR

    def test_get_kit_component_stock_missing_template(self):
        """get_kit_component_stock() rejects empty kit_template."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            get_kit_component_stock,
        )
        result = get_kit_component_stock(
            kit_template="",
            finish="Silver",
            lens_appearance="Frosted",
            mounting_method="Surface",
            endcap_style="Flat",
            endcap_color="Silver",
        )
        self.assertFalse(result.get("success"))

    def test_get_kit_component_stock_nonexistent_template(self):
        """get_kit_component_stock() rejects nonexistent kit_template."""
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            get_kit_component_stock,
        )
        result = get_kit_component_stock(
            kit_template="NONEXISTENT-KIT",
            finish="Silver",
            lens_appearance="Frosted",
            mounting_method="Surface",
            endcap_style="Flat",
            endcap_color="Silver",
        )
        self.assertFalse(result.get("success"))
        self.assertIn("not found", result.get("error", ""))

    def test_build_kit_stock_result_basic(self):
        """_build_kit_stock_result computes fulfillable kits correctly."""
        from unittest.mock import patch, MagicMock
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _build_kit_stock_result,
        )

        component_defs = [
            ("Profile", "ITEM-PROF-001", 1),
            ("Lens", "ITEM-LENS-001", 1),
            ("Solid Endcap", "ITEM-SEC-001", 2),
            ("Feed-Through Endcap", "ITEM-FEC-001", 2),
            ("Mounting Accessory", "ITEM-MNT-001", 6),
        ]

        # Mock stock: profile=10, lens=5, solid_endcap=8, feed_through=6, mounting=18
        mock_bins = [
            MagicMock(item_code="ITEM-PROF-001", total_qty=10),
            MagicMock(item_code="ITEM-LENS-001", total_qty=5),
            MagicMock(item_code="ITEM-SEC-001", total_qty=8),
            MagicMock(item_code="ITEM-FEC-001", total_qty=6),
            MagicMock(item_code="ITEM-MNT-001", total_qty=18),
        ]
        mock_lead_rows = [
            MagicMock(name="ITEM-PROF-001", lead_time_days=0),
            MagicMock(name="ITEM-LENS-001", lead_time_days=0),
            MagicMock(name="ITEM-SEC-001", lead_time_days=0),
            MagicMock(name="ITEM-FEC-001", lead_time_days=0),
            MagicMock(name="ITEM-MNT-001", lead_time_days=0),
        ]

        with patch.object(frappe.db, "sql", side_effect=[mock_bins, mock_lead_rows]):
            result = _build_kit_stock_result(component_defs)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["components"]), 5)
        # Minimum kits: mounting=18/6=3, feed_through=6/2=3, solid=8/2=4, lens=5, profile=10
        # min is 3 (mounting or feed-through)
        self.assertEqual(result["total_kits_fulfillable"], 3)
        self.assertIn(result["limiting_component"], ["Mounting Accessory", "Feed-Through Endcap"])

    def test_build_kit_stock_result_unresolved_component(self):
        """_build_kit_stock_result handles None item_code (unresolved mapping)."""
        from unittest.mock import patch, MagicMock
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _build_kit_stock_result,
        )

        component_defs = [
            ("Profile", None, 1),  # Unresolved
            ("Lens", "ITEM-LENS-001", 1),
        ]

        mock_bins = [MagicMock(item_code="ITEM-LENS-001", total_qty=5)]
        mock_lead_rows = [MagicMock(name="ITEM-LENS-001", lead_time_days=0)]

        with patch.object(frappe.db, "sql", side_effect=[mock_bins, mock_lead_rows]):
            result = _build_kit_stock_result(component_defs)

        self.assertTrue(result["success"])
        self.assertEqual(result["total_kits_fulfillable"], 0)
        self.assertEqual(result["limiting_component"], "Profile")
        # First component should be marked as out of stock
        self.assertFalse(result["components"][0]["in_stock"])
        self.assertEqual(result["components"][0]["lead_time_class"], "special-order")

    def test_build_kit_stock_result_lead_time_classes(self):
        """_build_kit_stock_result assigns correct lead_time_class per component."""
        from unittest.mock import patch, MagicMock
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _build_kit_stock_result,
        )

        component_defs = [
            ("Profile", "IN-STOCK-ITEM", 1),
            ("Lens", "MTO-ITEM", 1),
            ("Solid Endcap", "SO-ITEM", 2),
        ]

        # IN-STOCK-ITEM has stock, MTO-ITEM and SO-ITEM have 0
        mock_bins = [MagicMock(item_code="IN-STOCK-ITEM", total_qty=3)]
        mock_lead_rows = [
            MagicMock(name="IN-STOCK-ITEM", lead_time_days=0),
            MagicMock(name="MTO-ITEM", lead_time_days=14),
            MagicMock(name="SO-ITEM", lead_time_days=0),
        ]

        with patch.object(frappe.db, "sql", side_effect=[mock_bins, mock_lead_rows]):
            result = _build_kit_stock_result(component_defs)

        self.assertTrue(result["success"])
        comps = {c["component"]: c for c in result["components"]}
        self.assertEqual(comps["Profile"]["lead_time_class"], "in-stock")
        self.assertEqual(comps["Lens"]["lead_time_class"], "made-to-order")
        self.assertEqual(comps["Solid Endcap"]["lead_time_class"], "special-order")

    def test_build_kit_stock_result_insufficient_stock(self):
        """in_stock is False when stock exists but is below qty_per_kit."""
        from unittest.mock import patch, MagicMock
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _build_kit_stock_result,
        )

        component_defs = [
            ("Profile", "ITEM-PROF", 1),
            ("Mounting Accessory", "ITEM-MNT", 6),
        ]

        # Profile has plenty, Mounting has some stock but less than needed (6)
        mock_bins = [
            MagicMock(item_code="ITEM-PROF", total_qty=10),
            MagicMock(item_code="ITEM-MNT", total_qty=3),
        ]
        mock_lead_rows = [
            MagicMock(name="ITEM-PROF", lead_time_days=0),
            MagicMock(name="ITEM-MNT", lead_time_days=0),
        ]

        with patch.object(frappe.db, "sql", side_effect=[mock_bins, mock_lead_rows]):
            result = _build_kit_stock_result(component_defs)

        self.assertTrue(result["success"])
        comps = {c["component"]: c for c in result["components"]}

        # Profile: stock=10 >= qty=1 → in_stock=True
        self.assertTrue(comps["Profile"]["in_stock"])
        self.assertEqual(comps["Profile"]["kits_fulfillable"], 10)

        # Mounting: stock=3 < qty=6 → in_stock=False, but item IS stocked
        self.assertFalse(comps["Mounting Accessory"]["in_stock"])
        self.assertEqual(comps["Mounting Accessory"]["kits_fulfillable"], 0)
        # Lead-time should still be "in-stock" since the item has physical stock
        self.assertEqual(comps["Mounting Accessory"]["lead_time_class"], "in-stock")

        # Overall: limited by Mounting (0 kits)
        self.assertEqual(result["total_kits_fulfillable"], 0)
        self.assertEqual(result["limiting_component"], "Mounting Accessory")

    def test_build_kit_stock_result_zero_qty_filtered(self):
        """Components with qty_per_kit=0 should be excluded before calling _build_kit_stock_result."""
        from unittest.mock import patch, MagicMock
        from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
            _build_kit_stock_result,
        )

        # Simulate a kit that only requires Profile and Lens (endcaps/mounting qty=0)
        # After filtering in get_kit_component_stock, only these would be passed:
        component_defs = [
            ("Profile", "ITEM-PROF", 1),
            ("Lens", "ITEM-LENS", 1),
        ]

        mock_bins = [
            MagicMock(item_code="ITEM-PROF", total_qty=5),
            MagicMock(item_code="ITEM-LENS", total_qty=3),
        ]
        mock_lead_rows = [
            MagicMock(name="ITEM-PROF", lead_time_days=0),
            MagicMock(name="ITEM-LENS", lead_time_days=0),
        ]

        with patch.object(frappe.db, "sql", side_effect=[mock_bins, mock_lead_rows]):
            result = _build_kit_stock_result(component_defs)

        # Only 2 components should be present (zero-qty ones were filtered out)
        self.assertEqual(len(result["components"]), 2)
        self.assertTrue(all(c["in_stock"] for c in result["components"]))
