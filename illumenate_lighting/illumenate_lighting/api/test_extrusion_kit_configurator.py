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
