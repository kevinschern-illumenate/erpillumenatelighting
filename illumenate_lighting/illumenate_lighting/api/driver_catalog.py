"""One schema adapter for driver eligibility and independent power outputs."""

import frappe
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.api.configuration_contract import finite_number


def independent_outputs(driver):
	physical = finite_number(driver.get("outputs_count"), minimum=1, field="driver outputs")
	count = driver.get("independent_outputs_count") or (1 if physical == 1 else 0)
	count = finite_number(count, minimum=0, field="independent power outputs")
	if not count.is_integer() or not physical.is_integer() or not 1 <= count <= physical:
		raise ValueError(
			f"Driver {driver.get('name')}: declare its independent power output count; color/control channels cannot be treated as independent feeds"
		)
	return int(count)


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=600, seconds=60)
def input_protocols(template_type, template):
	"""Public choices from approved associations; never expose driver costs."""
	if template_type not in {"ilL-Fixture-Template", "ilL-Tape-Neon-Template", "ilL-LED-Sheet-Template"}:
		raise ValueError("Unsupported template family")
	if not frappe.db.get_value(template_type, template, "is_active"):
		raise ValueError("Template is unavailable")
	rows = frappe.get_all(
		"ilL-Rel-Driver-Eligibility",
		filters={
			"template_type": template_type,
			"fixture_template": template,
			"is_allowed": 1,
			"is_active": 1,
		},
		fields=["driver_spec"],
		limit_page_length=201,
	)
	if len(rows) > 200:
		raise ValueError("Too many driver associations; ask engineering to review this template")
	protocols = set()
	drivers, disabled = _load_drivers([row.driver_spec for row in rows])
	for row in rows:
		driver = drivers[row.driver_spec]
		if driver.item and not disabled.get(driver.item):
			protocols.update(p.protocol for p in driver.input_protocols or [] if p.protocol)
	return {"protocols": sorted(protocols)}


DRIVER_FIELDS = (
	"name",
	"item",
	"cost",
	"voltage_output",
	"output_type",
	"output_protocol",
	"max_wattage",
	"max_wattage_per_output",
	"usable_load_factor",
	"outputs_count",
	"independent_outputs_count",
)


def _load_drivers(names):
	"""Bulk-load driver specs, their input protocols and Item.disabled flags.

	Returns ``(drivers_by_name, disabled_by_item)``. Each driver is a
	``frappe._dict`` with the fields the catalog reads plus ``input_protocols``.
	A missing spec falls back to ``frappe.get_doc`` so it raises exactly as the
	per-row lookup did.
	"""
	unique = list(dict.fromkeys(name for name in names if name))
	drivers = {}
	if unique:
		for driver in frappe.get_all(
			"ilL-Spec-Driver",
			filters={"name": ["in", unique]},
			fields=list(DRIVER_FIELDS),
			limit_page_length=0,
		):
			driver["input_protocols"] = []
			drivers[driver.name] = driver
		for protocol in frappe.get_all(
			"ilL-Child-Driver-Input-Protocol",
			filters={"parenttype": "ilL-Spec-Driver", "parentfield": "input_protocols", "parent": ["in", unique]},
			fields=["parent", "protocol"],
			order_by="idx asc",
			limit_page_length=0,
		):
			if protocol.parent in drivers:
				drivers[protocol.parent]["input_protocols"].append(protocol)
	for name in names:
		if name not in drivers:
			drivers[name] = frappe.get_doc("ilL-Spec-Driver", name)
	items = list(dict.fromkeys(driver.item for driver in drivers.values() if driver.item))
	disabled = {}
	if items:
		disabled = {
			row.name: row.disabled
			for row in frappe.get_all(
				"Item", filters={"name": ["in", items]}, fields=["name", "disabled"], limit_page_length=0
			)
		}
	return drivers, disabled


def candidates(template_type, template, voltage, output_protocol=None, input_protocol=None):
	if not voltage:
		raise ValueError("A light-engine voltage is required for supply selection")
	rows = frappe.get_all(
		"ilL-Rel-Driver-Eligibility",
		filters={
			"template_type": template_type,
			"fixture_template": template,
			"is_allowed": 1,
			"is_active": 1,
		},
		fields=["driver_spec", "priority"],
	)
	return _collect(rows, voltage, output_protocol, input_protocol)


def catalog_candidates(voltage, output_protocol=None, input_protocol=None):
	"""Every active constant-voltage supply at this voltage, for templates with no approved match."""
	if not voltage:
		raise ValueError("A light-engine voltage is required for supply selection")
	rows = frappe.get_all(
		"ilL-Spec-Driver",
		filters={"voltage_output": voltage, "output_type": "Constant Voltage"},
		fields=["name as driver_spec"],
		order_by="name asc",
	)
	return _collect(rows, voltage, output_protocol, input_protocol, skip_ambiguous=True)


def _collect(rows, voltage, output_protocol, input_protocol, skip_ambiguous=False):
	result, revisions = [], {}
	drivers, disabled = _load_drivers([row.driver_spec for row in rows])
	for row in rows:
		driver = drivers[row.driver_spec]
		if (
			driver.voltage_output != voltage
			or driver.output_type != "Constant Voltage"
			or (output_protocol and driver.output_protocol != output_protocol)
			or (input_protocol and input_protocol not in {p.protocol for p in driver.input_protocols or []})
		):
			continue
		if not driver.item or disabled.get(driver.item):
			continue
		if driver.item in revisions:
			if skip_ambiguous:
				continue
			raise ValueError("Each eligible driver Item must resolve to one electrical specification")
		try:
			outputs = independent_outputs(driver)
		except ValueError:
			if skip_ambiguous:
				continue
			raise
		revisions[driver.item] = {
			key: driver.get(key)
			for key in (
				"name",
				"voltage_output",
				"output_type",
				"output_protocol",
				"max_wattage",
				"max_wattage_per_output",
				"usable_load_factor",
				"independent_outputs_count",
			)
		}
		revisions[driver.item]["outputs_count"] = outputs
		result.append(
			{
				"item_code": driver.item,
				"outputs_count": outputs,
				"priority": row.get("priority") or 0,
				"cost": driver.cost or 0,
				**{
					key: driver.get(key)
					for key in ("max_wattage", "max_wattage_per_output", "usable_load_factor")
				},
			}
		)
	return result, revisions
