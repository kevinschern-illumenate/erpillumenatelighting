# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Compatible power supplies on the template (owner, 2026-11-05; plan 4.17 item 10).

The fixture, tape/neon and LED sheet templates hold ``compatible_power_supplies``: one row per
driver in ilL-Rel-Driver-Eligibility for the template that is both Active and Allowed, sorted
by the driver's max wattage (low to high), then part number. Each row links back to its
eligibility row (``eligibility``). Rebuilt on every template save and by Apply Calculations;
nothing here reads the Webflow Product.

The Webflow Product turns these rows into calculated "Recommended With" compatible products:
each driver's ilL-Driver-Template (the one whose Variants include it) names the power supply's
Webflow Product (``power_supply_products``).
"""

import frappe

FIELD = "compatible_power_supplies"
DOCTYPES = ("ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template")
ELIGIBILITY = "ilL-Rel-Driver-Eligibility"
DRIVER = "ilL-Spec-Driver"
DRIVER_TEMPLATE = "ilL-Driver-Template"
DRIVER_FIELDS = (
	"name",
	"input_voltage_min",
	"input_voltage_max",
	"input_voltage_type",
	"voltage_output",
	"max_wattage",
	"location_rating",
	"outputs_count",
)


def _text(value):
	return "" if value is None else str(value).strip()


def voltage_frequency(v_min, v_max, v_type):
	"""Pure: "120 - 277VAC", or one value with its type when only one is set."""
	v_min, v_max, v_type = _text(v_min), _text(v_max), _text(v_type)
	if v_min and v_max:
		return f"{v_min} - {v_max}{v_type}"
	return f"{v_min or v_max}{v_type}" if (v_min or v_max) else ""


def power_supply_row(driver, protocols, eligibility):
	"""Pure: the table row for one driver (``driver`` is a dict of DRIVER_FIELDS)."""
	wattage = driver.get("max_wattage")
	return {
		"part_number": driver["name"],
		"input_protocol": ", ".join(protocols),
		"voltagefrequency": voltage_frequency(
			driver.get("input_voltage_min"), driver.get("input_voltage_max"), driver.get("input_voltage_type")
		),
		"output_voltage": _text(driver.get("voltage_output")),
		"max_wattage": f"{float(wattage):g}W" if wattage else "",
		"output_count": _text(driver.get("outputs_count")),
		"location_rating": _text(driver.get("location_rating")),
		"eligibility": eligibility,
	}


def sort_key(driver):
	"""Pure: max wattage low to high (drivers without one last), then part number."""
	wattage = driver.get("max_wattage")
	return (wattage is None or wattage == "", float(wattage or 0), driver["name"])


def rows_for(doctype, name):
	"""The template's power supply rows, read from Driver Eligibility and the driver specs."""
	if doctype not in DOCTYPES or not name:
		return []
	eligible = frappe.get_all(
		ELIGIBILITY,
		filters={"template_type": doctype, "fixture_template": name, "is_active": 1, "is_allowed": 1},
		fields=["name", "driver_spec"],
		order_by="name asc",
	)
	eligibility = {}
	for row in eligible:
		eligibility.setdefault(row["driver_spec"], row["name"])
	if not eligibility:
		return []
	drivers = frappe.get_all(DRIVER, filters={"name": ["in", list(eligibility)]}, fields=list(DRIVER_FIELDS))
	protocols = {}
	for row in frappe.get_all(
		"ilL-Child-Driver-Input-Protocol",
		filters={"parenttype": DRIVER, "parent": ["in", list(eligibility)]},
		fields=["parent", "protocol"],
		order_by="idx asc",
	):
		if row["protocol"]:
			protocols.setdefault(row["parent"], []).append(row["protocol"])
	codes = sorted({code for values in protocols.values() for code in values})
	labels = (
		{
			row["name"]: row["label"] or row["name"]
			for row in frappe.get_all(
				"ilL-Attribute-Dimming Protocol", filters={"name": ["in", codes]}, fields=["name", "label"]
			)
		}
		if codes
		else {}
	)
	return [
		power_supply_row(
			driver,
			[labels.get(code, code) for code in protocols.get(driver["name"], [])],
			eligibility[driver["name"]],
		)
		for driver in sorted(drivers, key=sort_key)
	]


def refresh(template):
	"""Rebuild the template's power supply table. Called from template_listing.refresh_template."""
	meta = getattr(template, "meta", None)
	if template.doctype not in DOCTYPES or (meta is not None and not meta.has_field(FIELD)):
		return
	template.set(FIELD, rows_for(template.doctype, template.name))


def power_supply_products(part_numbers):
	"""Pure on its inputs' order: the power supply Webflow Products for these drivers.

	Returns (products, missing): ``products`` in the order of the first driver that maps to
	each, and ``missing`` the drivers whose ilL-Driver-Template is not found or has no Webflow
	Product.
	"""
	part_numbers = [number for number in part_numbers if number]
	if not part_numbers:
		return [], []
	template_of = {}
	for row in frappe.get_all(
		"ilL-Child-Driver-Template-Variant",
		filters={"parenttype": DRIVER_TEMPLATE, "driver_spec": ["in", part_numbers]},
		fields=["parent", "driver_spec"],
		order_by="idx asc",
	):
		template_of.setdefault(row["driver_spec"], row["parent"])
	product_of = (
		{
			row["name"]: row["webflow_product"]
			for row in frappe.get_all(
				DRIVER_TEMPLATE,
				filters={"name": ["in", sorted(set(template_of.values()))]},
				fields=["name", "webflow_product"],
			)
		}
		if template_of
		else {}
	)
	products, missing = [], []
	for number in part_numbers:
		product = product_of.get(template_of.get(number))
		if not product:
			missing.append(number)
		elif product not in products:
			products.append(product)
	return products, missing


def power_supply_product_names():
	"""Every Webflow Product that a driver template links to (the power supply products)."""
	return set(
		frappe.get_all(DRIVER_TEMPLATE, filters={"webflow_product": ["is", "set"]}, pluck="webflow_product")
	)
