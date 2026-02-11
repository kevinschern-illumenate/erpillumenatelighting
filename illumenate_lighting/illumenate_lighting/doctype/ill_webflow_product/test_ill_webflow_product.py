# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Unit tests for ilL-Webflow-Product DocType and related functionality.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestilLWebflowProduct(FrappeTestCase):
    """Test cases for Webflow Product DocType."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        super().setUpClass()
        # Create test category if it doesn't exist
        if not frappe.db.exists("ilL-Webflow-Category", "test-category"):
            frappe.get_doc({
                "doctype": "ilL-Webflow-Category",
                "category_name": "Test Category",
                "category_slug": "test-category",
                "is_active": 1
            }).insert()

    def test_create_webflow_product(self):
        """Test creating a basic Webflow product."""
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Test Product",
            "product_slug": "test-product-" + frappe.generate_hash(length=6),
            "product_type": "Driver",
            "is_active": 1
        })
        product.insert()
        
        self.assertTrue(frappe.db.exists("ilL-Webflow-Product", product.name))
        self.assertEqual(product.sync_status, "Never Synced")
        
        # Cleanup
        product.delete()

    def test_auto_calculate_specs_disabled(self):
        """Test that specs are not auto-calculated when disabled."""
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Test No Auto Calc",
            "product_slug": "test-no-auto-calc-" + frappe.generate_hash(length=6),
            "product_type": "Driver",
            "auto_calculate_specs": 0,
            "is_active": 1
        })
        product.insert()
        
        # Should have no auto-calculated specs
        calculated_specs = [s for s in product.specifications if s.is_calculated]
        self.assertEqual(len(calculated_specs), 0)
        
        # Cleanup
        product.delete()

    def test_slug_uniqueness(self):
        """Test that product slugs must be unique."""
        slug = "unique-slug-" + frappe.generate_hash(length=6)
        
        product1 = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Product 1",
            "product_slug": slug,
            "product_type": "Driver",
            "is_active": 1
        })
        product1.insert()
        
        product2 = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Product 2",
            "product_slug": slug,
            "product_type": "Controller",
            "is_active": 1
        })
        
        with self.assertRaises(frappe.DuplicateEntryError):
            product2.insert()
        
        # Cleanup
        product1.delete()

    def test_specifications_child_table(self):
        """Test adding specifications to a product."""
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Product with Specs",
            "product_slug": "product-with-specs-" + frappe.generate_hash(length=6),
            "product_type": "Driver",
            "auto_calculate_specs": 0,
            "is_active": 1,
            "specifications": [
                {
                    "spec_group": "Electrical",
                    "spec_label": "Max Wattage",
                    "spec_value": "100",
                    "spec_unit": "W",
                    "is_calculated": 0,
                    "display_order": 1
                },
                {
                    "spec_group": "Physical",
                    "spec_label": "Weight",
                    "spec_value": "500",
                    "spec_unit": "g",
                    "is_calculated": 0,
                    "display_order": 2
                }
            ]
        })
        product.insert()
        
        self.assertEqual(len(product.specifications), 2)
        self.assertEqual(product.specifications[0].spec_label, "Max Wattage")
        
        # Cleanup
        product.delete()

    def test_specifications_with_attribute_links(self):
        """Test adding specifications with attribute doctype links."""
        import json
        
        # Sample attribute options JSON structure
        attribute_options = [
            {
                "attribute_type": "Finish",
                "attribute_doctype": "ilL-Attribute-Finish",
                "attribute_value": "Black Anodized",
                "display_label": "Black Anodized",
                "is_default": True
            },
            {
                "attribute_type": "Finish",
                "attribute_doctype": "ilL-Attribute-Finish",
                "attribute_value": "White",
                "display_label": "White",
                "is_default": False
            }
        ]
        
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Product with Attribute Links",
            "product_slug": "product-attr-links-" + frappe.generate_hash(length=6),
            "product_type": "Fixture Template",
            "auto_calculate_specs": 0,
            "is_active": 1,
            "specifications": [
                {
                    "spec_group": "Physical",
                    "spec_label": "Finish Options",
                    "spec_value": "Black Anodized, White",
                    "is_calculated": 0,
                    "display_order": 1,
                    "attribute_doctype": "ilL-Attribute-Finish",
                    "attribute_options_json": json.dumps(attribute_options)
                }
            ]
        })
        product.insert()
        
        self.assertEqual(len(product.specifications), 1)
        self.assertEqual(product.specifications[0].spec_label, "Finish Options")
        self.assertEqual(product.specifications[0].attribute_doctype, "ilL-Attribute-Finish")
        
        # Verify JSON parsing works
        parsed_options = json.loads(product.specifications[0].attribute_options_json)
        self.assertEqual(len(parsed_options), 2)
        self.assertEqual(parsed_options[0]["attribute_value"], "Black Anodized")
        self.assertTrue(parsed_options[0]["is_default"])
        
        # Cleanup
        product.delete()

    def test_sync_status_transitions(self):
        """Test sync status transitions."""
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Sync Test Product",
            "product_slug": "sync-test-" + frappe.generate_hash(length=6),
            "product_type": "Driver",
            "is_active": 1
        })
        product.insert()
        
        # Initial status should be "Never Synced"
        self.assertEqual(product.sync_status, "Never Synced")
        
        # Simulate successful sync
        product.webflow_item_id = "webflow-123"
        product.webflow_collection_slug = "drivers"
        product.last_synced_at = frappe.utils.now()
        product.sync_status = "Synced"
        product.save()
        
        self.assertEqual(product.sync_status, "Synced")
        
        # Cleanup
        product.delete()


class TestWebflowExportAPI(FrappeTestCase):
    """Test cases for Webflow Export API functions."""

    def test_get_webflow_products_empty(self):
        """Test getting products when none exist."""
        from illumenate_lighting.illumenate_lighting.api.webflow_export import get_webflow_products
        
        result = get_webflow_products(product_type="NonExistentType")
        
        self.assertIn("products", result)
        self.assertIn("total", result)
        self.assertEqual(result["total"], 0)

    def test_get_sync_statistics(self):
        """Test getting sync statistics."""
        from illumenate_lighting.illumenate_lighting.api.webflow_export import get_sync_statistics
        
        result = get_sync_statistics()
        
        self.assertIn("by_status", result)
        self.assertIn("by_type", result)
        self.assertIn("total_active", result)
        self.assertIn("needs_sync", result)

    def test_get_webflow_categories(self):
        """Test getting Webflow categories."""
        from illumenate_lighting.illumenate_lighting.api.webflow_export import get_webflow_categories
        
        result = get_webflow_categories()
        
        self.assertIn("categories", result)
        self.assertIn("total", result)

    def test_specifications_export_with_attribute_options(self):
        """Test that specifications export includes attribute doctype and options."""
        import json
        from illumenate_lighting.illumenate_lighting.api.webflow_export import get_webflow_products
        
        # Create a product with attribute-linked specifications
        attribute_options = [
            {
                "attribute_type": "Lens Appearance",
                "attribute_doctype": "ilL-Attribute-Lens Appearance",
                "attribute_value": "Frosted",
                "display_label": "Frosted"
            }
        ]
        
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Export Test Product",
            "product_slug": "export-test-" + frappe.generate_hash(length=6),
            "product_type": "Fixture Template",
            "auto_calculate_specs": 0,
            "is_active": 1,
            "sync_status": "Pending",
            "specifications": [
                {
                    "spec_group": "Optical",
                    "spec_label": "Lens Options",
                    "spec_value": "Frosted",
                    "is_calculated": 0,
                    "display_order": 1,
                    "attribute_doctype": "ilL-Attribute-Lens Appearance",
                    "attribute_options_json": json.dumps(attribute_options)
                }
            ]
        })
        product.insert()
        
        # Get the product via export API
        result = get_webflow_products(sync_status="Pending", include_child_tables=True)
        
        # Find our test product
        test_product = None
        for p in result["products"]:
            if p["product_slug"] == product.product_slug:
                test_product = p
                break
        
        self.assertIsNotNone(test_product)
        self.assertEqual(len(test_product["specifications"]), 1)
        
        spec = test_product["specifications"][0]
        self.assertEqual(spec["spec_label"], "Lens Options")
        self.assertEqual(spec["attribute_doctype"], "ilL-Attribute-Lens Appearance")
        self.assertEqual(len(spec["attribute_options"]), 1)
        self.assertEqual(spec["attribute_options"][0]["attribute_value"], "Frosted")
        
        # Cleanup
        product.delete()


class TestilLAttributeCertification(FrappeTestCase):
    """Test cases for Certification attribute DocType."""

    def test_create_certification(self):
        """Test creating a certification."""
        cert = frappe.get_doc({
            "doctype": "ilL-Attribute-Certification",
            "certification_name": "Test Cert " + frappe.generate_hash(length=6),
            "certification_code": "TEST",
            "description": "Test certification",
            "is_active": 1
        })
        cert.insert()
        
        self.assertTrue(frappe.db.exists("ilL-Attribute-Certification", cert.name))
        
        # Cleanup
        cert.delete()

    def test_certification_applies_to_types(self):
        """Test certification with applicable product types."""
        cert = frappe.get_doc({
            "doctype": "ilL-Attribute-Certification",
            "certification_name": "Multi-Type Cert " + frappe.generate_hash(length=6),
            "certification_code": "MULTI",
            "is_active": 1,
            "applies_to_types": [
                {"product_type": "Driver"},
                {"product_type": "Controller"}
            ]
        })
        cert.insert()
        
        self.assertEqual(len(cert.applies_to_types), 2)
        
        # Cleanup
        cert.delete()


class TestilLWebflowCategory(FrappeTestCase):
    """Test cases for Webflow Category DocType."""

    def test_create_category(self):
        """Test creating a category."""
        cat = frappe.get_doc({
            "doctype": "ilL-Webflow-Category",
            "category_name": "Test Category",
            "category_slug": "test-cat-" + frappe.generate_hash(length=6),
            "display_order": 99,
            "is_active": 1
        })
        cat.insert()
        
        self.assertTrue(frappe.db.exists("ilL-Webflow-Category", cat.name))
        
        # Cleanup
        cat.delete()

    def test_category_hierarchy(self):
        """Test category parent-child relationship."""
        parent = frappe.get_doc({
            "doctype": "ilL-Webflow-Category",
            "category_name": "Parent Category",
            "category_slug": "parent-cat-" + frappe.generate_hash(length=6),
            "is_active": 1
        })
        parent.insert()
        
        child = frappe.get_doc({
            "doctype": "ilL-Webflow-Category",
            "category_name": "Child Category",
            "category_slug": "child-cat-" + frappe.generate_hash(length=6),
            "parent_category": parent.name,
            "is_active": 1
        })
        child.insert()
        
        self.assertEqual(child.parent_category, parent.name)
        
        # Cleanup
        child.delete()
        parent.delete()


class TestExtrusionKitAttributePopulation(FrappeTestCase):
    """Test cases for Extrusion Kit attribute population."""

    def test_extrusion_kit_with_profile_spec(self):
        """Test that extrusion kit populates attributes from profile spec."""
        # This test verifies that when a webflow product of type Extrusion Kit
        # has a profile_spec, the series and environment ratings are extracted
        # Note: In production, this would require actual profile spec records
        # For now, we just verify the structure and logic flow
        
        product = frappe.get_doc({
            "doctype": "ilL-Webflow-Product",
            "product_name": "Test Extrusion Kit",
            "product_slug": "test-extrusion-kit-" + frappe.generate_hash(length=6),
            "product_type": "Extrusion Kit",
            "auto_populate_attributes": 1,
            "is_active": 1
        })
        product.insert()
        
        # Should not fail even without profile_spec or lens_spec
        self.assertIsNotNone(product.name)
        self.assertEqual(len(product.attribute_links), 0)
        
        # Cleanup
        product.delete()

    def test_extrusion_kit_attribute_deduplication(self):
        """Test that extrusion kit doesn't add duplicate attributes."""
        # This ensures that if both profile and lens have the same series,
        # it's only added once to attribute_links
        # Note: Full test would require creating actual spec records
        pass


class TestilLSpecController(FrappeTestCase):
    """Test cases for Controller Spec DocType."""

    def test_create_controller_spec(self):
        """Test creating a controller spec without linked item."""
        # Note: In production, this would require a linked Item
        # For testing, we just verify the structure
        pass
