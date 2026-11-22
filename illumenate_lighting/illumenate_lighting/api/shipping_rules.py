# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Parcel checks, box splitting and tracker status rules for outbound shipping.

Plain Python with no Frappe imports, so the rules are unit tested directly. Units are
inches and pounds throughout. The conversion to ounces for EasyPost happens once, in
the n8n workflow (docs/SHIPPING_EASYPOST_INTEGRATION.md).
"""

import math

# FedEx published values. ilL-Shipping-Settings overrides each one; check them against
# the FedEx agreement. "girth" here means length + girth: longest side + 2 x the other two.
DEFAULT_THRESHOLDS = {
	"ah_length_in": 48.0,
	"ah_second_side_in": 30.0,
	"ah_weight_lb": 50.0,
	"ah_girth_in": 105.0,
	"oversize_length_in": 96.0,
	"oversize_girth_in": 130.0,
	"max_length_in": 108.0,
	"max_weight_lb": 150.0,
	"max_girth_in": 165.0,
}

# Weight UOM name (lower case) -> pounds per unit.
POUNDS_PER = {
	"lb": 1.0,
	"lbs": 1.0,
	"pound": 1.0,
	"pounds": 1.0,
	"kg": 2.20462,
	"kgs": 2.20462,
	"kilogram": 2.20462,
	"kilograms": 2.20462,
	"g": 0.00220462,
	"gram": 0.00220462,
	"grams": 0.00220462,
	"gm": 0.00220462,
	"oz": 0.0625,
	"ounce": 0.0625,
	"ounces": 0.0625,
}

# EasyPost tracker status -> box status shown on the Shipment Parcel row.
BOX_STATUS = {
	"pre_transit": "Pre-Transit",
	"in_transit": "In Transit",
	"out_for_delivery": "Out for Delivery",
	"available_for_pickup": "Available for Pickup",
	"delivered": "Delivered",
	"return_to_sender": "Returned",
	"failure": "Exception",
	"error": "Exception",
	"cancelled": "Cancelled",
	"unknown": "Unknown",
}
# EasyPost statuses that alert the shipping lead.
EXCEPTIONS = frozenset({"return_to_sender", "failure", "error"})
MOVING = frozenset({"Pre-Transit", "In Transit", "Out for Delivery", "Available for Pickup"})


def number(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def thresholds(settings=None):
	"""DEFAULT_THRESHOLDS with every positive value from settings laid over it."""
	settings = settings or {}
	return {key: number(settings.get(key)) or default for key, default in DEFAULT_THRESHOLDS.items()}


def sides(parcel):
	"""The three dimensions, longest first."""
	return sorted((number(parcel.get(k)) for k in ("length", "width", "height")), reverse=True)


def length_plus_girth(parcel):
	longest, second, third = sides(parcel)
	return longest + 2 * (second + third)


def _fmt(value):
	return f"{value:g}"


def parcel_findings(parcel, limits):
	"""``(errors, flags)`` for one box. Errors block submit; flags mean a surcharge."""
	errors, flags = [], []
	dims = sides(parcel)
	weight = number(parcel.get("weight"))
	if min(dims) <= 0:
		errors.append("needs a length, width and height above 0 (inches)")
	if weight <= 0:
		errors.append("needs a weight above 0 (pounds)")
	if errors:
		return errors, flags

	longest, second, _third = dims
	girth = length_plus_girth(parcel)
	if longest > limits["max_length_in"]:
		errors.append(
			f"is {_fmt(longest)} in long; the most FedEx Ground takes is {_fmt(limits['max_length_in'])} in"
		)
	if weight > limits["max_weight_lb"]:
		errors.append(
			f"weighs {_fmt(weight)} lb; the most FedEx Ground takes is {_fmt(limits['max_weight_lb'])} lb"
		)
	if girth > limits["max_girth_in"]:
		errors.append(
			f"is {_fmt(girth)} in length + girth; the most FedEx Ground takes is {_fmt(limits['max_girth_in'])} in"
		)
	if errors:
		return errors, flags

	if longest > limits["oversize_length_in"] or girth > limits["oversize_girth_in"]:
		flags.append(f"oversize ({_fmt(longest)} in long, {_fmt(girth)} in length + girth)")
	else:
		if longest > limits["ah_length_in"]:
			flags.append(f"additional handling: longest side {_fmt(longest)} in")
		if second > limits["ah_second_side_in"]:
			flags.append(f"additional handling: second side {_fmt(second)} in")
		if girth > limits["ah_girth_in"]:
			flags.append(f"additional handling: {_fmt(girth)} in length + girth")
	if weight > limits["ah_weight_lb"]:
		flags.append(f"additional handling: {_fmt(weight)} lb")
	return errors, flags


def check_parcels(parcels, limits):
	"""``{"errors": [...], "flags": [...], "special": [bool per box]}``, messages prefixed "Box n"."""
	result = {"errors": [], "flags": [], "special": []}
	if not parcels:
		result["errors"].append("Add at least one parcel.")
		return result
	for index, parcel in enumerate(parcels, start=1):
		errors, flags = parcel_findings(parcel, limits)
		result["errors"].extend(f"Box {index} {message}." for message in errors)
		result["flags"].extend(f"Box {index}: {message}." for message in flags)
		result["special"].append(bool(flags))
	return result


def expand_counts(parcels):
	"""One dict per physical box: a row with Count 3 becomes three rows with Count 1.

	Each box needs its own tracking number and label, so rows are split before labels are
	bought. Returns None when nothing needs splitting.
	"""
	if all(int(number(p.get("count")) or 1) <= 1 for p in parcels):
		return None
	boxes = []
	for parcel in parcels:
		box = {key: parcel.get(key) for key in ("length", "width", "height", "weight")}
		box["count"] = 1
		boxes.extend(dict(box) for _ in range(max(int(number(parcel.get("count")) or 1), 1)))
	return boxes


def to_pounds(weight, uom):
	"""Weight in pounds, or None when the UOM is not one we know."""
	factor = POUNDS_PER.get(str(uom or "").strip().lower().rstrip("."))
	if factor is None:
		return None
	return number(weight) * factor


def suggested_weight(lines):
	"""``(pounds, unknown_uoms)`` for Delivery Note lines.

	Each line gives ``total_weight`` (or ``weight_per_unit`` x ``stock_qty``) and
	``weight_uom``. Lines without a weight are skipped. Rounded up to 0.1 lb.
	"""
	total, unknown = 0.0, set()
	for line in lines:
		weight = number(line.get("total_weight")) or number(line.get("weight_per_unit")) * number(
			line.get("stock_qty") or line.get("qty")
		)
		if weight <= 0:
			continue
		pounds = to_pounds(weight, line.get("weight_uom") or "lb")
		if pounds is None:
			unknown.add(str(line.get("weight_uom")))
			continue
		total += pounds
	return math.ceil(total * 10 - 1e-9) / 10, sorted(unknown)


def box_status(easypost_status):
	status = str(easypost_status or "").strip().lower()
	return BOX_STATUS.get(status, status.replace("_", " ").title() or "Unknown")


def shipment_status(box_statuses, current=None):
	"""Native ``tracking_status`` for a Shipment from its boxes' statuses.

	Returned wins, Delivered needs every box delivered, a box on the move means In
	Progress, and anything else leaves the current value alone.
	"""
	statuses = list(box_statuses)
	if any(s == "Returned" for s in statuses):
		return "Returned"
	if statuses and all(s == "Delivered" for s in statuses):
		return "Delivered"
	if any(s in MOVING or s == "Delivered" for s in statuses):
		return "In Progress"
	return current
