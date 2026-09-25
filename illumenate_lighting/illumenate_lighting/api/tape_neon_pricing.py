"""Explicit commercial prices and stock quantities for resolved tape/neon builds."""

import frappe
from frappe.utils import getdate, nowdate

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	cable_stock_quantity,
	finite_number,
)


def stock_quantity(item, length, unit="in"):
	stock_uom = frappe.db.get_value("Item", item, "stock_uom")
	if not stock_uom:
		raise ValueError(f"Stock UOM is required for {item}")
	return cable_stock_quantity(length, unit, stock_uom)


def selling_amount(item, quantity):
	"""No procurement-cost fallback or invented free component."""
	stock_uom = frappe.db.get_value("Item", item, "stock_uom")
	prices = frappe.get_all(
		"Item Price",
		filters={
			"item_code": item,
			"price_list": "Standard Selling",
			"selling": 1,
			"customer": ["is", "not set"],
			"supplier": ["is", "not set"],
			"batch_no": ["is", "not set"],
		},
		fields=["name", "price_list_rate", "uom", "valid_from", "valid_upto"],
		order_by="valid_from desc, name",
	)
	today = getdate(nowdate())
	eligible = [
		p
		for p in prices
		if (not p.uom or p.uom == stock_uom)
		and (not p.valid_from or getdate(p.valid_from) <= today)
		and (not p.valid_upto or getdate(p.valid_upto) >= today)
	]
	if not stock_uom or not eligible or eligible[0].price_list_rate is None:
		raise ValueError(f"A current Standard Selling price in stock UOM is required for {item}")
	rate = finite_number(eligible[0].price_list_rate, minimum=0, field="selling rate")
	return rate * finite_number(quantity, minimum=0, field="component quantity")


def price_result(result, template=None):
	from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
		_compute_template_tape_neon_pricing,
	)

	computed, resolved = result["computed"], result["resolved_items"]
	if computed.get("ordering_mode") == "BULK_REEL":
		computed["total_price_msrp"] = round(
			sum(selling_amount(row["item_code"], row["qty"]) for row in result["components"]), 2
		)
		computed["price_basis"] = "Standard Selling bulk-stock quantities plus selected accessories"
		return result
	if result.get("components"):
		light_rows = [row for row in result["components"] if row["role"] == "light engine"]
		if template:
			length = sum(s["manufacturable_length_mm"] for s in computed["segments"])
			total = _compute_template_tape_neon_pricing(
				template, result["selections"], length, 0, result["product_category"] == "LED Neon"
			)["total_price_msrp"]
		else:
			total = sum(selling_amount(row["item_code"], row["qty"]) for row in light_rows)
		total += sum(
			selling_amount(row["item_code"], row["qty"])
			for row in result["components"]
			if row["role"] != "light engine"
		)
		computed["total_price_msrp"] = round(total, 2)
		return result
	segments = computed.get("segments") or []
	length = (
		sum(s["manufacturable_length_mm"] for s in segments)
		if segments
		else computed.get("manufacturable_length_mm", 0)
	)
	leads = (
		sum(
			float(s.get("start_lead_length_inches") or 0) + float(s.get("end_feed_length_inches") or 0)
			for s in segments
		)
		if segments
		else float(computed.get("lead_length_inches") or 0)
	)
	if not length or length <= 0:
		raise ValueError("A positive manufactured length is required before saving a build")
	if template:
		selections = {**result.get("selections", {}), "_leader_cable_item": resolved.get("leader_cable_item")}
		pricing = _compute_template_tape_neon_pricing(
			template, selections, length, leads, result["product_category"] == "LED Neon"
		)
		total = pricing["total_price_msrp"]
	else:
		total = selling_amount(resolved["tape_item"], stock_quantity(resolved["tape_item"], length, "mm"))
		if leads:
			total += selling_amount(
				resolved["leader_cable_item"], stock_quantity(resolved["leader_cable_item"], leads)
			)
	power = resolved.get("driver_plan") or {}
	for driver in power.get("drivers", []):
		total += selling_amount(driver["driver_item"], driver["qty"])
	computed["total_price_msrp"] = round(total, 2)
	return result
