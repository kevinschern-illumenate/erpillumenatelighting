"""Included power supplies as their own schedule lines.

When a dealer includes power for a Linear Fixture, LED Tape, COB Tape, LED Neon or LED
Sheet build (single or grouped), the supplies are not folded into the configured
Item. Every supply the power planner selects becomes an ACCESSORY line directly
under the fixture line, with the same Fixture Type and Location. Quantity
follows the fixture line: the supplies needed by one build times the number of
builds.

Linear, tape and neon geometry does not depend on the supplies, so those builds
are made as externally powered products. A Sheet's feeds are sized by its
drivers, so a Sheet keeps its full power plan and is only marked
``power_supply_separate``: the supplies stay out of its BOM and price.

A multi-run group keeps its power plan for every family and is marked
``separate_supply_line``: the supplies stay out of its BOM and price, while its
description and traveler still say which supply output feeds which run.
"""

import copy
import json
import uuid

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool

SPLIT_FAMILIES = ("Linear Fixture", "LED Tape", "COB Tape", "LED Neon", "LED Sheet")
SHEET = "LED Sheet"
# Schedule line fields that tie a power-supply line to its fixture line.
OWNER_FIELD = "power_supply_for_line"
PER_BUILD_FIELD = "power_supply_qty_per_build"


def _plan_drivers(plan, error=None):
	plan = plan or {}
	if plan.get("status") != "selected" or not plan.get("drivers"):
		raise ValueError(error or _("No compatible power supply could be selected for this configuration."))
	drivers = []
	for row in plan["drivers"]:
		item, qty = row.get("driver_item") or row.get("item_code"), row.get("qty")
		if not item or not qty:
			raise ValueError(_("The selected power supply plan is incomplete."))
		drivers.append({"driver_item": item, "qty": int(qty)})
	return drivers


def _error_text(result):
	messages = [m.get("text") for m in result.get("messages") or [] if m.get("severity") == "error"]
	return result.get("error") or "; ".join(m for m in messages if m) or None


def split_power(family, payload):
	"""Return ``(payload_to_build, drivers)`` for a normalized configuration payload.

	``drivers`` is ``[{"driver_item", "qty"}]`` per build when power is included
	for a family whose supplies become their own lines; the payload is then
	rewritten to build the fixture without supplies. Otherwise the payload is
	returned unchanged with no drivers.
	"""
	if family not in SPLIT_FAMILIES:
		return payload, []
	if payload.get("group_request"):
		from illumenate_lighting.illumenate_lighting.api.fixture_group_configurator import calculate

		request = payload["group_request"]
		request = copy.deepcopy(json.loads(request) if isinstance(request, str) else request)
		power = request.get("power") or {}
		if not parse_bool(power.get("include_power_supply"), default=True):
			return payload, []
		# Plan the group's shared supplies once; keep the plan (Sheet feeds are sized by it and
		# every traveler shows the run-to-output allocation) but move the supplies to their lines.
		build = {**request, "power": {**power, "separate_supply_line": True}}
		return {**payload, "group_request": build}, _plan_drivers(calculate(build)["build"]["power_plan"])

	if not parse_bool(payload.get("include_power_supply"), default=True):
		return payload, []
	from illumenate_lighting.illumenate_lighting.api.configured_product_builder import _dispatch_calculate

	if family == SHEET:
		build = {**payload, "power_supply_separate": 1}
		preview = _dispatch_calculate(
			family,
			build,
			parent_configured_fixture=None,
			parent_configured_tape_neon=None,
			tape_neon_template=None,
		)
		return build, _plan_drivers(preview.get("power_plan"), _error_text(preview))

	preview = _dispatch_calculate(
		family,
		{**payload, "include_power_supply": True},
		parent_configured_fixture=None,
		parent_configured_tape_neon=None,
		tape_neon_template=payload.get("tape_neon_template"),
	)
	plan = (preview.get("resolved_items") or {}).get("driver_plan")
	drivers = _plan_drivers(plan, _error_text(preview))
	build = {**payload, "include_power_supply": False}
	if isinstance(payload.get("selections"), dict):
		# Tape/neon builds also keep their selections; they must agree.
		build["selections"] = {**payload["selections"], "include_power_supply": False}
	return build, drivers


def _item_name(item_code):
	return frappe.db.get_value("Item", item_code, "item_name") or item_code


def is_power_line(line):
	return bool(line.get(OWNER_FIELD))


def set_power_lines(schedule, owner, drivers):
	"""Replace the power-supply lines of ``owner`` with ``drivers`` (per build).

	Call after the owner line holds its new configuration and before saving;
	``reconcile`` (run on every schedule save) places them under the owner and
	keeps quantity, Fixture Type and Location in step with it.
	"""
	if not owner.get("line_key"):
		owner.line_key = uuid.uuid4().hex
	key = owner.line_key
	schedule.lines[:] = [line for line in schedule.lines if line.get(OWNER_FIELD) != key]
	for driver in drivers or []:
		line = schedule.append("lines", {})
		line.line_key = uuid.uuid4().hex
		line.manufacturer_type = "ACCESSORY"
		line.configuration_status = "Configured"
		line.accessory_item = driver["driver_item"]
		line.accessory_item_name = _item_name(driver["driver_item"])
		line.set(OWNER_FIELD, key)
		line.set(PER_BUILD_FIELD, int(driver["qty"]))
		line.notes = _("Power supply for {0}").format(owner.get("line_id") or _("the line above"))
	reconcile(schedule)


def clear_power_lines(schedule, owner):
	"""Drop the power-supply lines of ``owner`` (power excluded or line replaced)."""
	key = owner.get("line_key")
	if key:
		schedule.lines[:] = [line for line in schedule.lines if line.get(OWNER_FIELD) != key]


def _owns_power(line):
	return line.get("manufacturer_type") == "ILLUMENATE" and line.get("configuration_status") == "Configured"


def reconcile(schedule):
	"""Keep every power-supply line directly under, and in step with, its fixture line.

	Lines whose fixture line was deleted or is no longer a configured ilLumenate
	product are removed. The rest take the fixture line's Fixture Type and
	Location and its quantity times the supplies needed per build.
	"""
	lines = list(schedule.lines or [])
	owners = {line.line_key: line for line in lines if line.get("line_key") and not is_power_line(line)}
	children = {}
	for line in lines:
		if not is_power_line(line):
			continue
		owner = owners.get(line.get(OWNER_FIELD))
		if owner is None or not _owns_power(owner):
			continue
		per_build = int(line.get(PER_BUILD_FIELD) or 0) or 1
		line.qty = per_build * int(owner.get("qty") or 1)
		line.line_id = owner.get("line_id")
		line.location = owner.get("location")
		children.setdefault(owner.line_key, []).append(line)
	ordered = []
	for line in lines:
		if is_power_line(line):
			continue
		ordered.append(line)
		ordered.extend(children.get(line.get("line_key"), []))
	if len(ordered) != len(lines) or any(a is not b for a, b in zip(ordered, lines, strict=True)):
		schedule.lines[:] = ordered
	for index, line in enumerate(schedule.lines, 1):
		line.idx = index


def accessory_row_specs(drivers, qty):
	"""Transaction (Quotation / Sales Order) row specs for the split supplies."""
	return [
		{"item_code": driver["driver_item"], "qty": int(driver["qty"]) * int(qty or 1)}
		for driver in drivers or []
	]
