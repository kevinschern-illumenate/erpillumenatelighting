"""One schema adapter for driver eligibility and independent power outputs."""

import frappe

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
	for row in rows:
		driver = frappe.get_doc("ilL-Spec-Driver", row.driver_spec)
		if driver.item and not frappe.db.get_value("Item", driver.item, "disabled"):
			protocols.update(p.protocol for p in driver.input_protocols or [] if p.protocol)
	return {"protocols": sorted(protocols)}


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
	result, revisions = [], {}
	for row in rows:
		driver = frappe.get_doc("ilL-Spec-Driver", row.driver_spec)
		if (
			driver.voltage_output != voltage
			or driver.output_type != "Constant Voltage"
			or (output_protocol and driver.output_protocol != output_protocol)
			or (input_protocol and input_protocol not in {p.protocol for p in driver.input_protocols or []})
		):
			continue
		if not driver.item or frappe.db.get_value("Item", driver.item, "disabled"):
			continue
		if driver.item in revisions:
			raise ValueError("Each eligible driver Item must resolve to one electrical specification")
		outputs = independent_outputs(driver)
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
				"priority": row.priority or 0,
				"cost": driver.cost or 0,
				**{
					key: driver.get(key)
					for key in ("max_wattage", "max_wattage_per_output", "usable_load_factor")
				},
			}
		)
	return result, revisions
