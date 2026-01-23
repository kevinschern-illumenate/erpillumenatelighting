# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Webflow Integration API

This module provides API endpoints for Webflow CMS integration that pulls product data
from ERPNext including all custom doctypes (CCT, Output Level, Finish, Lens, etc.).
Implements a hybrid sync approach where base catalog syncs every 6 hours via n8n,
while real-time stock/pricing is fetched client-side via JavaScript.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import json

import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def get_product_detail(item_code: Optional[str] = None, sku: Optional[str] = None) -> dict:
	"""
	Get comprehensive product details for a single product.
	
	Accepts either item_code or sku parameter and returns comprehensive product data including:
	- Standard Item fields (name, description, images, weight)
	- Real-time pricing from Item Price
	- Real-time stock from Bin
	- Custom attribute data from linked doctypes
	- Driver information
	- Technical specifications
	
	Args:
		item_code: Item code (primary key)
		sku: SKU/Item name (alternate lookup)
		
	Returns:
		dict: {
			"success": True/False,
			"product": {...} or None,
			"error": str (if error),
			"cached_at": timestamp
		}
	"""
	try:
		# Validate that at least one parameter is provided
		if not item_code and not sku:
			return {
				"success": False,
				"error": "Either item_code or sku parameter is required",
				"product": None,
			}
		
		# Find the item by item_code or sku
		if item_code:
			item_name = item_code
		else:
			# Look up by sku (item_code field in Item doctype)
			item_name = frappe.db.get_value("Item", {"item_code": sku}, "name")
			if not item_name:
				# Try by name as fallback
				item_name = frappe.db.get_value("Item", {"name": sku}, "name")
		
		if not item_name or not frappe.db.exists("Item", item_name):
			return {
				"success": False,
				"error": f"Product not found: {item_code or sku}",
				"product": None,
			}
		
		# Get item document
		item_doc = frappe.get_doc("Item", item_name)
		
		# Check if item is disabled
		if item_doc.disabled:
			return {
				"success": False,
				"error": "Product is disabled",
				"product": None,
			}
		
		# Build product data
		product = {
			"item_code": item_doc.item_code or item_doc.name,
			"item_name": item_doc.item_name,
			"description": item_doc.description,
			"item_group": item_doc.item_group,
			"stock_uom": item_doc.stock_uom,
			"weight_per_unit": item_doc.weight_per_unit,
			"weight_uom": item_doc.weight_uom,
			"image": item_doc.image,
			"is_sales_item": item_doc.is_sales_item,
			"is_stock_item": item_doc.is_stock_item,
		}
		
		# Get pricing - look for standard selling price
		price_data = _get_item_price(item_name)
		product["price"] = price_data.get("price", 0.0)
		product["currency"] = price_data.get("currency", "USD")
		
		# Get stock quantity
		stock_data = _get_stock_qty(item_name)
		product["stock_qty"] = stock_data.get("qty", 0.0)
		product["in_stock"] = stock_data.get("qty", 0.0) > 0
		
		# Check if this is a configured fixture
		is_configured_fixture = False
		configured_fixture_name = None
		
		# Check if there's a configured fixture with this item as configured_item
		cf_exists = frappe.db.exists("ilL-Configured-Fixture", {"configured_item": item_name})
		if cf_exists:
			is_configured_fixture = True
			configured_fixture_name = cf_exists
		
		product["is_configured_fixture"] = is_configured_fixture
		
		# Get custom attributes if it's a configured fixture
		if is_configured_fixture and configured_fixture_name:
			custom_attributes = _get_configured_fixture_attributes(configured_fixture_name)
			product["custom_attributes"] = custom_attributes
			
			# Get technical specs
			technical_specs = _get_technical_specs(configured_fixture_name, custom_attributes)
			product["technical_specs"] = technical_specs
			
			# Get pricing from configured fixture if available
			cf_pricing = _get_configured_fixture_pricing(configured_fixture_name)
			if cf_pricing:
				product["msrp_unit"] = cf_pricing.get("msrp_unit")
				product["tier_unit"] = cf_pricing.get("tier_unit")
		else:
			product["custom_attributes"] = {}
			product["technical_specs"] = {}
		
		return {
			"success": True,
			"product": product,
			"cached_at": datetime.now().isoformat(),
		}
		
	except Exception as e:
		frappe.log_error(f"Error in get_product_detail: {str(e)}", "Webflow Integration Error")
		return {
			"success": False,
			"error": str(e),
			"product": None,
		}


def _get_item_price(item_code: str) -> dict:
	"""
	Get the price for an item from Item Price doctype.
	
	Args:
		item_code: Item code
		
	Returns:
		dict: {"price": float, "currency": str}
	"""
	try:
		# Get standard selling price
		price_doc = frappe.db.get_value(
			"Item Price",
			filters={
				"item_code": item_code,
				"selling": 1,
			},
			fieldname=["price_list_rate", "currency"],
			as_dict=True,
			order_by="valid_from desc"
		)
		
		if price_doc:
			return {
				"price": price_doc.price_list_rate or 0.0,
				"currency": price_doc.currency or "USD"
			}
		
		return {"price": 0.0, "currency": "USD"}
	except Exception:
		return {"price": 0.0, "currency": "USD"}


def _get_stock_qty(item_code: str) -> dict:
	"""
	Get total stock quantity for an item from Bin.
	
	Args:
		item_code: Item code
		
	Returns:
		dict: {"qty": float}
	"""
	try:
		# Sum up actual qty from all bins
		result = frappe.db.sql("""
			SELECT SUM(actual_qty) as total_qty
			FROM `tabBin`
			WHERE item_code = %s
		""", (item_code,), as_dict=True)
		
		if result and result[0].total_qty:
			return {"qty": float(result[0].total_qty)}
		
		return {"qty": 0.0}
	except Exception:
		return {"qty": 0.0}


def _get_configured_fixture_attributes(configured_fixture_name: str) -> dict:
	"""
	Get all custom attributes for a configured fixture.
	
	Traverses relationships to get data from linked attribute doctypes:
	- Finish, Lens Appearance, Mounting Method, Environment Rating
	- CCT, LED Package, Output Level, CRI (via tape_offering)
	- Power Feed Type
	
	Args:
		configured_fixture_name: Name of ilL-Configured-Fixture
		
	Returns:
		dict: Custom attributes organized by type
	"""
	attributes = {}
	
	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_name)
		
		# Finish
		if cf.finish:
			finish_data = frappe.db.get_value(
				"ilL-Attribute-Finish",
				cf.finish,
				["code", "display_name", "surface_treatment"],
				as_dict=True
			)
			if finish_data:
				attributes["finish"] = {
					"code": finish_data.code,
					"name": finish_data.display_name or finish_data.code,
					"surface_treatment": finish_data.surface_treatment,
				}
		
		# Lens Appearance
		if cf.lens_appearance:
			lens_data = frappe.db.get_value(
				"ilL-Attribute-Lens Appearance",
				cf.lens_appearance,
				["label", "code", "transmission"],
				as_dict=True
			)
			if lens_data:
				# Transmission is stored as decimal (0.56 = 56%), convert to percent for API
				trans_pct = (lens_data.transmission or 1.0) * 100
				attributes["lens"] = {
					"name": lens_data.label,
					"code": lens_data.code,
					"transmission_percent": trans_pct,
				}
		
		# Mounting Method
		if cf.mounting_method:
			mounting_data = frappe.db.get_value(
				"ilL-Attribute-Mounting Method",
				cf.mounting_method,
				["label", "code"],
				as_dict=True
			)
			if mounting_data:
				attributes["mounting_method"] = {
					"name": mounting_data.label,
					"code": mounting_data.code,
				}
		
		# Environment Rating
		if cf.environment_rating:
			env_data = frappe.db.get_value(
				"ilL-Attribute-Environment Rating",
				cf.environment_rating,
				["label", "code", "ip_rating"],
				as_dict=True
			)
			if env_data:
				attributes["environment_rating"] = {
					"name": env_data.label,
					"code": env_data.code,
					"ip_rating": env_data.ip_rating,
				}
		
		# Tape offering attributes (CCT, LED Package, Output Level, CRI)
		if cf.tape_offering:
			tape_offering = frappe.db.get_value(
				"ilL-Rel-Tape Offering",
				cf.tape_offering,
				["cct", "led_package", "output_level", "cri"],
				as_dict=True
			)
			
			if tape_offering:
				# CCT
				if tape_offering.cct:
					cct_data = frappe.db.get_value(
						"ilL-Attribute-CCT",
						tape_offering.cct,
						["cct_name", "code", "kelvin_value"],
						as_dict=True
					)
					if cct_data:
						attributes["cct"] = {
							"name": cct_data.cct_name,
							"code": cct_data.code,
							"kelvin": cct_data.kelvin_value,
							"display": f"{cct_data.kelvin_value}K" if cct_data.kelvin_value else cct_data.cct_name,
						}
				
				# LED Package
				if tape_offering.led_package:
					led_data = frappe.db.get_value(
						"ilL-Attribute-LED Package",
						tape_offering.led_package,
						["label", "code"],
						as_dict=True
					)
					if led_data:
						attributes["led_package"] = {
							"name": led_data.label,
							"code": led_data.code,
						}
				
				# Output Level
				if tape_offering.output_level:
					output_data = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						tape_offering.output_level,
						["output_level_name", "sku_code", "value"],
						as_dict=True
					)
					if output_data:
						attributes["output_level"] = {
							"name": output_data.output_level_name,
							"code": output_data.sku_code,
							"value_lm_per_ft": output_data.value,
						}
				
				# CRI
				if tape_offering.cri:
					cri_data = frappe.db.get_value(
						"ilL-Attribute-CRI",
						tape_offering.cri,
						["cri_name", "code", "minimum_ra"],
						as_dict=True
					)
					if cri_data:
						attributes["cri"] = {
							"name": cri_data.cri_name,
							"code": cri_data.code,
							"ra_value": cri_data.minimum_ra,
						}
		
		# Power Feed Type
		if cf.power_feed_type:
			power_feed_data = frappe.db.get_value(
				"ilL-Attribute-Power Feed Type",
				cf.power_feed_type,
				["label", "code"],
				as_dict=True
			)
			if power_feed_data:
				attributes["power_feed_type"] = {
					"name": power_feed_data.label,
					"code": power_feed_data.code,
				}
		
		# Driver information
		if cf.drivers:
			drivers_list = []
			for driver_alloc in cf.drivers:
				if driver_alloc.driver_item:
					driver_spec = frappe.db.get_value(
						"ilL-Spec-Driver",
						driver_alloc.driver_item,
						["item", "input_voltage", "max_wattage", "output_voltage", "dimming_protocol"],
						as_dict=True
					)
					if driver_spec:
						drivers_list.append({
							"item": driver_spec.item,
							"qty": driver_alloc.driver_qty,
							"input_voltage": driver_spec.input_voltage,
							"max_wattage": driver_spec.max_wattage,
							"output_voltage": driver_spec.output_voltage,
							"dimming_protocol": driver_spec.dimming_protocol,
						})
			
			if drivers_list:
				attributes["drivers"] = drivers_list
		
	except Exception as e:
		frappe.log_error(f"Error getting configured fixture attributes: {str(e)}", "Webflow Integration Error")
	
	return attributes


def _get_technical_specs(configured_fixture_name: str, custom_attributes: dict) -> dict:
	"""
	Get technical specifications for a configured fixture.
	
	Calculates:
	- Estimated delivered output (tape output * lens transmission / 100)
	- Total watts
	- Length in mm and inches
	- Input voltage from driver specs
	
	Args:
		configured_fixture_name: Name of ilL-Configured-Fixture
		custom_attributes: Custom attributes dict from _get_configured_fixture_attributes
		
	Returns:
		dict: Technical specifications
	"""
	specs = {}
	
	try:
		cf = frappe.get_doc("ilL-Configured-Fixture", configured_fixture_name)
		
		# Estimated delivered output
		if custom_attributes.get("output_level") and custom_attributes.get("lens"):
			tape_output = custom_attributes["output_level"].get("value_lm_per_ft", 0)
			lens_transmission = custom_attributes["lens"].get("transmission_percent", 100)
			delivered_output = (tape_output * lens_transmission) / 100
			
			specs["estimated_delivered_output"] = {
				"value": round(delivered_output, 1),
				"unit": "lm/ft",
				"display": f"{round(delivered_output, 1)} lm/ft",
			}
		
		# Total watts
		if cf.total_watts:
			specs["total_watts"] = {
				"value": cf.total_watts,
				"display": f"{cf.total_watts}W",
			}
		
		# Length
		if cf.manufacturable_overall_length_mm:
			length_mm = cf.manufacturable_overall_length_mm
			length_inches = length_mm / 25.4
			
			specs["length"] = {
				"mm": length_mm,
				"inches": round(length_inches, 2),
				"display": f"{length_mm}mm ({round(length_inches, 1)}\")",
			}
		elif cf.requested_overall_length_mm:
			length_mm = cf.requested_overall_length_mm
			length_inches = length_mm / 25.4
			
			specs["length"] = {
				"mm": length_mm,
				"inches": round(length_inches, 2),
				"display": f"{length_mm}mm ({round(length_inches, 1)}\")",
			}
		
		# Input voltage from drivers
		if custom_attributes.get("drivers"):
			input_voltages = []
			for driver in custom_attributes["drivers"]:
				if driver.get("input_voltage"):
					input_voltages.append(driver["input_voltage"])
			
			if input_voltages:
				# Remove duplicates and join
				unique_voltages = list(dict.fromkeys(input_voltages))
				specs["input_voltage"] = {
					"value": unique_voltages[0] if len(unique_voltages) == 1 else unique_voltages,
					"display": ", ".join(unique_voltages),
				}
		
	except Exception as e:
		frappe.log_error(f"Error getting technical specs: {str(e)}", "Webflow Integration Error")
	
	return specs


def _get_configured_fixture_pricing(configured_fixture_name: str) -> Optional[dict]:
	"""
	Get pricing information from configured fixture.
	
	Args:
		configured_fixture_name: Name of ilL-Configured-Fixture
		
	Returns:
		dict or None: {"msrp_unit": float, "tier_unit": float} if available
	"""
	try:
		pricing = frappe.db.get_value(
			"ilL-Configured-Fixture",
			configured_fixture_name,
			["msrp_unit", "tier_unit"],
			as_dict=True
		)
		
		if pricing and (pricing.msrp_unit or pricing.tier_unit):
			return {
				"msrp_unit": pricing.msrp_unit,
				"tier_unit": pricing.tier_unit,
			}
		
		return None
	except Exception:
		return None


@frappe.whitelist(allow_guest=True)
def get_related_products(item_code: str, limit: int = 6) -> dict:
	"""
	Get related products in the same item group.
	
	Args:
		item_code: Item code of the reference product
		limit: Maximum number of results (default: 6)
		
	Returns:
		dict: {
			"success": True/False,
			"products": [...],
			"error": str (if error)
		}
	"""
	try:
		# Get the item group of the reference item
		item_group = frappe.db.get_value("Item", item_code, "item_group")
		
		if not item_group:
			return {
				"success": False,
				"error": "Item not found",
				"products": [],
			}
		
		# Get related items in the same group (excluding the reference item)
		related_items = frappe.get_all(
			"Item",
			filters={
				"item_group": item_group,
				"disabled": 0,
				"is_sales_item": 1,
				"name": ["!=", item_code],
			},
			fields=["name", "item_code", "item_name", "image"],
			limit=limit,
		)
		
		# Enrich with pricing
		products = []
		for item in related_items:
			price_data = _get_item_price(item.name)
			products.append({
				"item_code": item.item_code or item.name,
				"item_name": item.item_name,
				"image": item.image,
				"price": price_data.get("price", 0.0),
			})
		
		return {
			"success": True,
			"products": products,
		}
		
	except Exception as e:
		frappe.log_error(f"Error in get_related_products: {str(e)}", "Webflow Integration Error")
		return {
			"success": False,
			"error": str(e),
			"products": [],
		}


@frappe.whitelist()
def get_active_products_for_webflow(
	item_group: Optional[str] = None,
	modified_since: Optional[str] = None
) -> dict:
	"""
	Get all active, sellable products for Webflow sync (authenticated endpoint).
	
	Returns all active products (disabled=0, is_sales_item=1) with stock qty,
	pricing, and basic metadata. Used by n8n for periodic sync.
	
	Args:
		item_group: Optional filter by item group
		modified_since: Optional ISO datetime string to get only updated products
		
	Returns:
		dict: {
			"success": True/False,
			"products": [...],
			"count": int,
			"error": str (if error)
		}
	"""
	try:
		# Build filters
		filters = {
			"disabled": 0,
			"is_sales_item": 1,
		}
		
		if item_group:
			filters["item_group"] = item_group
		
		if modified_since:
			filters["modified"] = [">", modified_since]
		
		# Get all matching items
		items = frappe.get_all(
			"Item",
			filters=filters,
			fields=[
				"name",
				"item_code",
				"item_name",
				"description",
				"item_group",
				"stock_uom",
				"image",
				"modified",
			],
		)
		
		# Enrich with stock and pricing
		products = []
		for item in items:
			price_data = _get_item_price(item.name)
			stock_data = _get_stock_qty(item.name)
			
			products.append({
				"item_code": item.item_code or item.name,
				"item_name": item.item_name,
				"description": item.description,
				"item_group": item.item_group,
				"stock_uom": item.stock_uom,
				"image": item.image,
				"price": price_data.get("price", 0.0),
				"currency": price_data.get("currency", "USD"),
				"stock_qty": stock_data.get("qty", 0.0),
				"in_stock": stock_data.get("qty", 0.0) > 0,
				"modified": item.modified.isoformat() if item.modified else None,
			})
		
		return {
			"success": True,
			"products": products,
			"count": len(products),
		}
		
	except Exception as e:
		frappe.log_error(f"Error in get_active_products_for_webflow: {str(e)}", "Webflow Integration Error")
		return {
			"success": False,
			"error": str(e),
			"products": [],
			"count": 0,
		}


@frappe.whitelist()
def get_products_by_codes(item_codes: Union[List[str], str]) -> dict:
	"""
	Bulk fetch products by list of item codes (authenticated endpoint).
	
	Used by n8n for batch processing.
	
	Args:
		item_codes: List of item codes (as JSON string or list)
		
	Returns:
		dict: {
			"success": True/False,
			"products": [...],
			"count": int,
			"error": str (if error)
		}
	"""
	try:
		# Handle JSON string input
		if isinstance(item_codes, str):
			try:
				item_codes = json.loads(item_codes)
			except (ValueError, json.JSONDecodeError) as e:
				return {
					"success": False,
					"error": f"Invalid JSON string for item_codes: {str(e)}",
					"products": [],
					"count": 0,
				}
		
		if not isinstance(item_codes, list):
			return {
				"success": False,
				"error": "item_codes must be a list",
				"products": [],
				"count": 0,
			}
		
		# Get items
		items = frappe.get_all(
			"Item",
			filters={
				"name": ["in", item_codes],
			},
			fields=[
				"name",
				"item_code",
				"item_name",
				"description",
				"item_group",
				"stock_uom",
				"image",
				"disabled",
				"is_sales_item",
			],
		)
		
		# Enrich with stock and pricing
		products = []
		for item in items:
			price_data = _get_item_price(item.name)
			stock_data = _get_stock_qty(item.name)
			
			products.append({
				"item_code": item.item_code or item.name,
				"item_name": item.item_name,
				"description": item.description,
				"item_group": item.item_group,
				"stock_uom": item.stock_uom,
				"image": item.image,
				"price": price_data.get("price", 0.0),
				"currency": price_data.get("currency", "USD"),
				"stock_qty": stock_data.get("qty", 0.0),
				"in_stock": stock_data.get("qty", 0.0) > 0,
				"disabled": item.disabled,
				"is_sales_item": item.is_sales_item,
			})
		
		return {
			"success": True,
			"products": products,
			"count": len(products),
		}
		
	except Exception as e:
		frappe.log_error(f"Error in get_products_by_codes: {str(e)}", "Webflow Integration Error")
		return {
			"success": False,
			"error": str(e),
			"products": [],
			"count": 0,
		}
