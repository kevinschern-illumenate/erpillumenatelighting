# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Unit tests for Product Bundle stock resolution in pricing_utils.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from illumenate_lighting.illumenate_lighting.api.pricing_utils import (
    _bulk_stock_query,
    _resolve_bundle_stock,
)


class TestResolveBundleStock(FrappeTestCase):
    """Tests for _resolve_bundle_stock() and its integration in _bulk_stock_query()."""

    # ─── Helpers ──────────────────────────────────────────────────────

    def _mock_sql(self, bundle_children, child_bins):
        """
        Return a side_effect function for frappe.db.sql that returns:
        - bundle_children on the first call (Product Bundle join query)
        - child_bins on the second call (Bin query for child items)
        """
        call_count = {"n": 0}

        def side_effect(query, values, as_dict=False):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bundle_children
            return child_bins

        return side_effect

    # ─── _resolve_bundle_stock ────────────────────────────────────────

    def test_empty_item_codes(self):
        """Empty input returns empty dict."""
        self.assertEqual(_resolve_bundle_stock([]), {})

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_no_bundles_found(self, mock_frappe):
        """Items that are not Product Bundles return empty dict."""
        mock_frappe.db.sql.return_value = []
        result = _resolve_bundle_stock(["ITEM-A", "ITEM-B"])
        self.assertEqual(result, {})

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_single_bundle_all_children_in_stock(self, mock_frappe):
        """Bundle with all children in stock computes min(floor(child/qty))."""
        bundle_children = [
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-A", qty=2),
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-B", qty=1),
        ]
        child_bins = [
            frappe._dict(item_code="CHILD-A", total_qty=10),
            frappe._dict(item_code="CHILD-B", total_qty=3),
        ]
        mock_frappe.db.sql.side_effect = self._mock_sql(bundle_children, child_bins)

        result = _resolve_bundle_stock(["BUNDLE-1"])
        # CHILD-A: floor(10/2)=5, CHILD-B: floor(3/1)=3 → min=3
        self.assertEqual(result, {"BUNDLE-1": 3})

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_child_out_of_stock(self, mock_frappe):
        """If any child has 0 stock, bundle stock = 0."""
        bundle_children = [
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-A", qty=1),
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-B", qty=1),
        ]
        child_bins = [
            frappe._dict(item_code="CHILD-A", total_qty=5),
            # CHILD-B not in Bin → 0 stock
        ]
        mock_frappe.db.sql.side_effect = self._mock_sql(bundle_children, child_bins)

        result = _resolve_bundle_stock(["BUNDLE-1"])
        self.assertEqual(result, {"BUNDLE-1": 0})

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_zero_qty_child(self, mock_frappe):
        """A child with qty=0 contributes 0 kits (division guard)."""
        bundle_children = [
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-A", qty=0),
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-B", qty=1),
        ]
        child_bins = [
            frappe._dict(item_code="CHILD-A", total_qty=100),
            frappe._dict(item_code="CHILD-B", total_qty=5),
        ]
        mock_frappe.db.sql.side_effect = self._mock_sql(bundle_children, child_bins)

        result = _resolve_bundle_stock(["BUNDLE-1"])
        # CHILD-A: qty=0 → 0, CHILD-B: floor(5/1)=5 → min=0
        self.assertEqual(result, {"BUNDLE-1": 0})

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_fractional_stock(self, mock_frappe):
        """Floor division is used for fractional results."""
        bundle_children = [
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-A", qty=3),
        ]
        child_bins = [
            frappe._dict(item_code="CHILD-A", total_qty=7),
        ]
        mock_frappe.db.sql.side_effect = self._mock_sql(bundle_children, child_bins)

        result = _resolve_bundle_stock(["BUNDLE-1"])
        # floor(7/3) = 2
        self.assertEqual(result, {"BUNDLE-1": 2})

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_multiple_bundles(self, mock_frappe):
        """Multiple bundles are resolved independently."""
        bundle_children = [
            frappe._dict(bundle_item="BUNDLE-1", item_code="CHILD-A", qty=1),
            frappe._dict(bundle_item="BUNDLE-2", item_code="CHILD-B", qty=2),
        ]
        child_bins = [
            frappe._dict(item_code="CHILD-A", total_qty=10),
            frappe._dict(item_code="CHILD-B", total_qty=6),
        ]
        mock_frappe.db.sql.side_effect = self._mock_sql(bundle_children, child_bins)

        result = _resolve_bundle_stock(["BUNDLE-1", "BUNDLE-2"])
        self.assertEqual(result, {"BUNDLE-1": 10, "BUNDLE-2": 3})

    # ─── _bulk_stock_query integration ────────────────────────────────

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils._resolve_bundle_stock")
    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_bulk_stock_query_merges_bundle_stock(self, mock_frappe, mock_resolve):
        """_bulk_stock_query replaces 0-stock entries with bundle-computed stock."""
        # Bin query returns nothing for BUNDLE-1, normal stock for ITEM-A
        mock_frappe.db.sql.return_value = [
            frappe._dict(item_code="ITEM-A", total_qty=15),
        ]
        mock_resolve.return_value = {"BUNDLE-1": 7}

        result = _bulk_stock_query(["ITEM-A", "BUNDLE-1"])
        self.assertEqual(result["ITEM-A"], 15)
        self.assertEqual(result["BUNDLE-1"], 7)

    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils._resolve_bundle_stock")
    @patch("illumenate_lighting.illumenate_lighting.api.pricing_utils.frappe")
    def test_bulk_stock_query_non_bundles_unaffected(self, mock_frappe, mock_resolve):
        """Non-bundle items retain their Bin stock values."""
        mock_frappe.db.sql.return_value = [
            frappe._dict(item_code="ITEM-A", total_qty=5),
            frappe._dict(item_code="ITEM-B", total_qty=12),
        ]
        mock_resolve.return_value = {}

        result = _bulk_stock_query(["ITEM-A", "ITEM-B"])
        self.assertEqual(result["ITEM-A"], 5)
        self.assertEqual(result["ITEM-B"], 12)

    def test_bulk_stock_query_empty_input(self):
        """Empty input returns empty dict without any DB calls."""
        self.assertEqual(_bulk_stock_query([]), {})
