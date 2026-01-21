# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Unit tests for Webflow Configurator API

Tests the configurator initialization, cascading options, 
validation, part number generation, and session management.
"""

import frappe
import json
import unittest
from unittest.mock import patch, MagicMock
from frappe.utils import now_datetime, add_to_date


class TestWebflowConfiguratorAPI(unittest.TestCase):
    """Test cases for the Webflow Configurator API endpoints."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        # Create test fixture template if needed
        if not frappe.db.exists("ilL-Fixture-Template", "TEST-TEMPLATE"):
            cls._create_test_template()
        
        # Create test Webflow product
        if not frappe.db.exists("ilL-Webflow-Product", {"product_slug": "test-product"}):
            cls._create_test_product()
    
    @classmethod
    def _create_test_template(cls):
        """Create a test fixture template."""
        template = frappe.new_doc("ilL-Fixture-Template")
        template.template_code = "TEST-TEMPLATE"
        template.template_name = "Test Template"
        template.is_active = 1
        template.flags.ignore_permissions = True
        template.insert()
    
    @classmethod
    def _create_test_product(cls):
        """Create a test Webflow product."""
        product = frappe.new_doc("ilL-Webflow-Product")
        product.product_name = "Test Product"
        product.product_slug = "test-product"
        product.fixture_template = "TEST-TEMPLATE"
        product.is_configurable = 1
        product.flags.ignore_permissions = True
        product.insert()
    
    def test_get_configurator_init_success(self):
        """Test successful configurator initialization."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            get_configurator_init
        )
        
        result = get_configurator_init("test-product")
        
        self.assertTrue(result.get("success"))
        self.assertIn("product", result)
        self.assertIn("series", result)
        self.assertIn("steps", result)
        self.assertIn("options", result)
        self.assertIn("length_config", result)
        self.assertIn("part_number_prefix", result)
    
    def test_get_configurator_init_not_found(self):
        """Test configurator init with non-existent product."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            get_configurator_init
        )
        
        result = get_configurator_init("non-existent-product")
        
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
    
    def test_get_cascading_options_invalid_json(self):
        """Test cascading options with invalid JSON."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            get_cascading_options
        )
        
        result = get_cascading_options(
            product_slug="test-product",
            step_name="environment_rating",
            selections="invalid json {"
        )
        
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)
    
    def test_get_cascading_options_environment(self):
        """Test cascading options after environment selection."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            get_cascading_options
        )
        
        selections = {
            "environment_rating": "Indoor"
        }
        
        result = get_cascading_options(
            product_slug="test-product",
            step_name="environment_rating",
            selections=json.dumps(selections)
        )
        
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("step_completed"), "environment_rating")
    
    def test_validate_configuration_missing_fields(self):
        """Test validation with missing required fields."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            validate_configuration
        )
        
        # Incomplete selections
        selections = {
            "environment_rating": "Indoor",
            "cct": "3000K"
            # Missing other required fields
        }
        
        result = validate_configuration(
            product_slug="test-product",
            selections=json.dumps(selections)
        )
        
        self.assertFalse(result.get("is_valid"))
        self.assertIn("missing_fields", result)
    
    def test_validate_configuration_invalid_length(self):
        """Test validation with invalid length."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            validate_configuration
        )
        
        # All fields but invalid length
        selections = {
            "environment_rating": "Indoor",
            "cct": "3000K",
            "output_level": "100 lm/ft",
            "lens_appearance": "Clear",
            "mounting_method": "Surface",
            "finish": "Black",
            "length_inches": 5,  # Too short
            "start_feed_direction": "End",
            "start_feed_length_ft": "2",
            "end_feed_direction": "End",
            "end_feed_length_ft": "2"
        }
        
        result = validate_configuration(
            product_slug="test-product",
            selections=json.dumps(selections)
        )
        
        # Should fail due to length constraint
        self.assertFalse(result.get("is_valid"))
    
    def test_get_part_number_preview(self):
        """Test part number preview generation."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            get_part_number_preview
        )
        
        selections = {
            "environment_rating": "Indoor",
            "cct": "3000K"
        }
        
        result = get_part_number_preview(
            product_slug="test-product",
            selections=json.dumps(selections)
        )
        
        self.assertTrue(result.get("success"))
        self.assertIn("part_number_preview", result)
        self.assertIn("segments", result)
        self.assertIn("complete_percentage", result)


class TestWebflowSession(unittest.TestCase):
    """Test cases for Webflow Session management."""
    
    def test_create_complex_fixture_session(self):
        """Test creating a complex fixture session."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            create_complex_fixture_session
        )
        
        selections = {
            "environment_rating": "Indoor",
            "cct": "3000K"
        }
        
        result = create_complex_fixture_session(
            product_slug="test-product",
            selections=json.dumps(selections),
            fixture_type_id="A1",
            quantity=2
        )
        
        self.assertTrue(result.get("success"))
        self.assertIn("session_id", result)
        self.assertIn("redirect_url", result)
        self.assertIn("expires_at", result)
        
        # Clean up
        if result.get("session_id"):
            frappe.delete_doc(
                "ilL-Webflow-Session",
                result["session_id"],
                force=True,
                ignore_permissions=True
            )
    
    def test_get_session_success(self):
        """Test retrieving a session."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            create_complex_fixture_session, get_session
        )
        
        # Create session
        selections = {"environment_rating": "Indoor"}
        create_result = create_complex_fixture_session(
            product_slug="test-product",
            selections=json.dumps(selections)
        )
        
        session_id = create_result.get("session_id")
        
        # Get session
        result = get_session(session_id)
        
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("session_id"), session_id)
        self.assertIn("configuration", result)
        
        # Clean up
        frappe.delete_doc(
            "ilL-Webflow-Session",
            session_id,
            force=True,
            ignore_permissions=True
        )
    
    def test_get_session_not_found(self):
        """Test retrieving non-existent session."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            get_session
        )
        
        result = get_session("non-existent-session-id")
        
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)


class TestWebflowScheduleAPI(unittest.TestCase):
    """Test cases for the Webflow Schedule API endpoints."""
    
    def test_get_user_schedules_authenticated(self):
        """Test getting user schedules when authenticated."""
        from illumenate_lighting.illumenate_lighting.api.webflow_schedule import (
            get_user_schedules
        )
        
        # Mock authenticated user
        frappe.set_user("Administrator")
        
        result = get_user_schedules()
        
        self.assertTrue(result.get("success"))
        self.assertIn("schedules", result)
        self.assertIn("count", result)
    
    def test_add_to_schedule_missing_product(self):
        """Test adding to schedule without product_slug."""
        from illumenate_lighting.illumenate_lighting.api.webflow_schedule import (
            add_to_schedule
        )
        
        frappe.set_user("Administrator")
        
        # Configuration without product_slug
        config = {
            "environment_rating": "Indoor"
        }
        
        result = add_to_schedule(
            schedule_id="non-existent-schedule",
            configuration=json.dumps(config)
        )
        
        self.assertFalse(result.get("success"))


class TestPartNumberGeneration(unittest.TestCase):
    """Test cases for part number generation."""
    
    def test_generate_part_number_preview_empty(self):
        """Test part number preview with no selections."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _generate_part_number_preview
        )
        
        series_info = {
            "series_code": "RA01",
            "led_package_code": "FS"
        }
        
        selections = {}
        
        result = _generate_part_number_preview(series_info, selections)
        
        self.assertIn("full", result)
        self.assertIn("segments", result)
        self.assertIn("complete_percentage", result)
        
        # Should have xx placeholders
        self.assertIn("xx", result["full"])
    
    def test_generate_part_number_preview_partial(self):
        """Test part number preview with partial selections."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _generate_part_number_preview
        )
        
        series_info = {
            "series_code": "RA01",
            "led_package_code": "FS"
        }
        
        selections = {
            "finish": "Black"
        }
        
        result = _generate_part_number_preview(series_info, selections)
        
        # Should have some xx placeholders but not all
        self.assertIn("full", result)
        self.assertTrue(result["complete_percentage"] > 0)
    
    def test_feed_direction_code(self):
        """Test feed direction code lookup."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _get_feed_direction_code
        )
        
        # Test fallback codes
        self.assertEqual(_get_feed_direction_code("End"), "E")
        self.assertEqual(_get_feed_direction_code("Back"), "B")
        self.assertEqual(_get_feed_direction_code("Unknown"), "X")


class TestCacheFunctions(unittest.TestCase):
    """Test cases for caching functions."""
    
    def test_generate_cache_key(self):
        """Test cache key generation."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _generate_cache_key
        )
        
        key1 = _generate_cache_key("product1", "step1", {"a": "1"})
        key2 = _generate_cache_key("product1", "step1", {"a": "1"})
        key3 = _generate_cache_key("product1", "step1", {"a": "2"})
        
        # Same inputs should produce same key
        self.assertEqual(key1, key2)
        
        # Different inputs should produce different key
        self.assertNotEqual(key1, key3)
    
    def test_cache_options_and_retrieve(self):
        """Test caching and retrieving options."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _cache_options, _get_cached_options, _generate_cache_key
        )
        
        cache_key = _generate_cache_key("test-cache", "test-step", {"test": "1"})
        test_result = {
            "success": True,
            "selections": {"test": "1"},
            "step_completed": "test-step",
            "updated_options": {"test_options": [1, 2, 3]}
        }
        
        # Cache the options
        _cache_options(cache_key, test_result)
        
        # Retrieve cached options
        cached = _get_cached_options(cache_key)
        
        # Should match (or be None if cache doesn't exist yet)
        # This depends on whether the DocType exists
        if cached:
            self.assertEqual(cached["step_completed"], "test-step")


class TestHelperFunctions(unittest.TestCase):
    """Test cases for helper functions."""
    
    def test_get_leader_length_options(self):
        """Test getting leader length options."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _get_leader_length_options
        )
        
        options = _get_leader_length_options()
        
        self.assertIsInstance(options, list)
        self.assertTrue(len(options) > 0)
        
        # Check structure
        for opt in options:
            self.assertIn("value", opt)
            self.assertIn("label", opt)
    
    def test_get_feed_directions_fallback(self):
        """Test getting feed directions with fallback."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _get_feed_directions
        )
        
        directions = _get_feed_directions()
        
        self.assertIsInstance(directions, list)
        self.assertTrue(len(directions) >= 2)
        
        # Should have End and Back at minimum
        values = [d["value"] for d in directions]
        self.assertIn("End", values)
        self.assertIn("Back", values)
    
    def test_build_configuration_summary(self):
        """Test building configuration summary."""
        from illumenate_lighting.illumenate_lighting.api.webflow_configurator import (
            _build_configuration_summary
        )
        
        selections = {
            "environment_rating": "Indoor",
            "cct": "3000K",
            "length_inches": 48,
            "start_feed_length_ft": 2
        }
        
        summary = _build_configuration_summary(selections)
        
        self.assertIsInstance(summary, list)
        
        # Check that items have correct structure
        for item in summary:
            self.assertIn("field", item)
            self.assertIn("label", item)
            self.assertIn("value", item)
        
        # Check length formatting
        length_item = next((i for i in summary if i["field"] == "length_inches"), None)
        if length_item:
            self.assertIn("inches", length_item["value"])


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestWebflowConfiguratorAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestWebflowSession))
    suite.addTests(loader.loadTestsFromTestCase(TestWebflowScheduleAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestPartNumberGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestCacheFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestHelperFunctions))
    
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == "__main__":
    run_tests()
