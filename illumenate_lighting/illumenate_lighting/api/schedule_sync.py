# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Two-way scope sync between a Fixture Schedule and its draft Quotations / Sales Orders.

The schedule is the scope the dealer sees in the portal; a draft Quotation or
Sales Order linked to it (``ill_fixture_schedule``) is its priced projection.
While both are drafts:

* saving the transaction pushes the rows the user added, removed or edited onto
  the schedule (``on_transaction_validate``), and
* saving the schedule pushes the lines that were added, removed or changed onto
  every other draft transaction linked to it (``on_schedule_update``).

Only scope travels: which lines exist, their product, quantity, Fixture Type,
Section / Room and notes. Rate, discount and taxes stay on the transaction and
are never rewritten. Sync stops when either side leaves draft: a submitted
transaction, or a schedule that is locked or past READY, is never touched.

Both directions diff against the document as it was before this save, so a
mismatch that predates the sync is left alone rather than "fixed" silently.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"
TRANSACTION_DOCTYPES = ("Quotation", "Sales Order")
CONFIGURED_LINKS = ("configured_group", "configured_fixture", "configured_tape_neon", "configured_led_sheet")
# A change to any of these makes the line a different product, so its rows are rebuilt.
PRODUCT_FIELDS = (*CONFIGURED_LINKS, "manufacturer_type", "product_type", "accessory_item", "variant_selections")
LABEL_FIELDS = ("line_id", "location", "notes")
LINE_PRODUCT_TYPES = ("Linear Fixture", "Linear Fixtures", "LED Tape", "COB Tape", "LED Neon", "LED Sheet", "Extrusion Kit")
POWER_OWNER_FIELD = "power_supply_for_line"
# Set on a document whose save is itself a sync write and must not sync onward.
SKIP_FLAG = "ill_skip_schedule_sync"
# Set on a schedule saved by a transaction: (doctype, name) of that transaction,
# which already holds the change and is skipped when the schedule pushes it on.
SOURCE_FLAG = "ill_schedule_sync_source"
SAVEPOINT = "ill_schedule_sync"


# ═══════════════════════════════════════════════════════════════════════
# PLANNING (pure: rows and lines in, changes out)
# ═══════════════════════════════════════════════════════════════════════


def _same(a, b) -> bool:
	return (a or None) == (b or None)


def _whole(value) -> int | None:
	number = flt(value)
	return int(number) if number > 0 and number == int(number) else None


def stock_qty(row) -> int | None:
	"""A row's quantity in stock UOM, when it is a whole number (schedule lines are)."""
	return _whole(flt(row.get("qty")) * flt(row.get("conversion_factor") or 1))


def rows_by_line(rows) -> dict[str, list]:
	grouped: dict[str, list] = {}
	for row in rows or []:
		key = row.get("ill_schedule_line_id")
		if key:
			grouped.setdefault(key, []).append(row)
	return grouped


def single_row_line(line) -> bool:
	"""Lines the converter writes as exactly one row at the line's quantity."""
	if line.get(POWER_OWNER_FIELD):
		return False  # A supply follows its fixture line's quantity.
	if line.get("manufacturer_type") == "ACCESSORY":
		return True
	return line.get("manufacturer_type") == "ILLUMENATE" and any(line.get(field) for field in CONFIGURED_LINKS)


def plan_transaction_changes(line_names, before_rows, rows, *, newly_linked: bool) -> dict:
	"""What one transaction save changes on its schedule.

	``add``: rows new to this save (every row, when the schedule was just
	linked) that point at no schedule line. ``remove``: lines whose last row this
	save removed. ``update``: ``(row, before_row)`` for lines that had and still
	have exactly that one row.
	"""
	line_names = set(line_names)
	before_names = {row.get("name") for row in before_rows or []}
	add = []
	for row in rows or []:
		if not row.get("item_code") or row.get("ill_is_power_supply_line") or row.get("is_alternative"):
			continue  # Supplies follow their fixture line; alternatives are not scope.
		if row.get("ill_schedule_line_id") in line_names:
			continue
		if newly_linked or row.get("__islocal") or row.get("name") not in before_names:
			add.append(row)

	current = rows_by_line(rows)
	previous = rows_by_line(before_rows)
	remove = [name for name in previous if name in line_names and name not in current]
	update = [
		(now[0], previous[name][0])
		for name, now in current.items()
		if name in line_names
		and len(now) == 1
		and len(previous.get(name) or []) == 1
		and now[0].get("name") == previous[name][0].get("name")
	]
	return {"add": add, "remove": remove, "update": update}


def line_updates(line, row, before_row) -> dict:
	"""Line fields one edited row changes on its one-row schedule line."""
	if line.get(POWER_OWNER_FIELD):
		return {}  # Fixture Type, Location and quantity follow the fixture line.

	def edited(field):
		return not _same(row.get(field), before_row.get(field))

	changes = {}
	if edited("ill_section_label"):
		changes["location"] = row.get("ill_section_label") or None
	if edited("ill_fixture_type") and row.get("ill_fixture_type"):
		changes["line_id"] = row.get("ill_fixture_type")
	if edited("additional_notes"):
		changes["notes"] = row.get("additional_notes") or ""
	if single_row_line(line) and (edited("qty") or edited("conversion_factor")):
		qty = stock_qty(row)
		if qty:
			changes["qty"] = qty
	if line.get("manufacturer_type") == "ACCESSORY" and edited("item_code") and row.get("item_code"):
		changes["accessory_item"] = row.get("item_code")
	return {key: value for key, value in changes.items() if not _same(line.get(key), value)}


def plan_schedule_changes(before_lines, lines) -> dict:
	"""What one schedule save changes on its draft transactions.

	``added`` / ``removed`` lines; ``rebuilt`` lines that became another product;
	``scaled`` lines whose quantity changed (name → new / old ratio); and
	``relabelled`` lines whose Fixture Type, Location or notes changed.
	"""
	before = {line.get("name"): line for line in before_lines or [] if line.get("name")}
	after = {line.get("name"): line for line in lines or [] if line.get("name")}
	plan = {
		"added": [name for name in after if name not in before],
		"removed": [name for name in before if name not in after],
		"rebuilt": [],
		"scaled": {},
		"relabelled": [],
	}
	for name, line in after.items():
		old = before.get(name)
		if old is None:
			continue
		if any(not _same(line.get(field), old.get(field)) for field in PRODUCT_FIELDS):
			plan["rebuilt"].append(name)
			continue
		if flt(old.get("qty")) > 0 and flt(line.get("qty")) != flt(old.get("qty")):
			plan["scaled"][name] = flt(line.get("qty")) / flt(old.get("qty"))
		if any(not _same(line.get(field), old.get(field)) for field in LABEL_FIELDS):
			plan["relabelled"].append(name)
	return plan


def has_changes(plan: dict) -> bool:
	return any(plan.values())


def place_new_rows(line_order, items, first_new: int) -> list:
	"""Move the rows appended from ``first_new`` on next to their schedule neighbours.

	A new line's rows go after the rows of the nearest line above it in the
	schedule, else before the nearest line below it, else at the end.
	"""
	rank = {name: index for index, name in enumerate(line_order)}
	result = list(items[:first_new])
	for row in items[first_new:]:
		own = rank.get(row.get("ill_schedule_line_id"))
		position = len(result)
		if own is not None:
			ranks = [rank.get(other.get("ill_schedule_line_id")) for other in result]
			above = [index for index, other in enumerate(ranks) if other is not None and other <= own]
			below = [index for index, other in enumerate(ranks) if other is not None and other > own]
			if above:
				position = above[-1] + 1
			elif below:
				position = below[0]
		result.insert(position, row)
	for index, row in enumerate(result, 1):
		row.idx = index
	return result


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════


def schedule_is_open(schedule) -> bool:
	from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
		EDITABLE_STATUSES,
	)

	return not cint(schedule.get("is_locked")) and schedule.get("status") in EDITABLE_STATUSES


def _skip_globally() -> bool:
	flags = frappe.flags
	return bool(flags.get("in_import") or flags.get("in_migrate") or flags.get("in_install") or flags.get("in_patch"))


def _set(row, fieldname: str, value) -> None:
	try:
		if not row.meta.has_field(fieldname):
			return
	except AttributeError:
		pass
	row.set(fieldname, value)


def _sellable_stock_item(item_code):
	"""The Item a schedule ACCESSORY line can carry, or ``None``.

	Mirrors what the schedule → transaction converter accepts, so a line created
	here always converts back. Freight, services and other non-stock rows stay
	on the transaction only.
	"""
	item = frappe.db.get_value(
		"Item",
		item_code,
		["item_name", "is_stock_item", "is_sales_item", "disabled", "has_variants"],
		as_dict=True,
	)
	if not item or not item.is_stock_item or not item.is_sales_item or item.disabled or item.has_variants:
		return None
	return item


def _line_from_row(row) -> dict | None:
	"""Schedule line values for a transaction row that has none, or ``None``."""
	qty = stock_qty(row)
	if not qty:
		return None
	values = {
		"qty": qty,
		"line_id": row.get("ill_fixture_type") or None,
		"location": row.get("ill_section_label") or None,
		"notes": row.get("additional_notes") or "",
		"configuration_status": "Configured",
	}
	links = {field: row.get("ill_" + field) for field in CONFIGURED_LINKS if row.get("ill_" + field)}
	if links:
		# A configured row added without a schedule (or before the link existed).
		product_type = row.get("ill_product_type")
		if not product_type and links.get("configured_group"):
			product_type = frappe.db.get_value("ilL-Configured-Group", links["configured_group"], "family")
		if not product_type and links.get("configured_fixture"):
			product_type = "Linear Fixture"
		if not product_type and links.get("configured_led_sheet"):
			product_type = "LED Sheet"
		if product_type not in LINE_PRODUCT_TYPES:
			return None
		values.update(links)
		values.update({
			"manufacturer_type": "ILLUMENATE",
			"product_type": product_type,
			"ill_item_code": row.item_code,
			"ill_bom": row.get("ill_bom") or None,
			"ill_configurator_request": row.get("ill_configurator_request") or None,
		})
		return values
	item = _sellable_stock_item(row.item_code)
	if not item:
		return None
	values.update({
		"manufacturer_type": "ACCESSORY",
		"accessory_item": row.item_code,
		"accessory_item_name": item.item_name,
	})
	return values


# ═══════════════════════════════════════════════════════════════════════
# TRANSACTION → SCHEDULE
# ═══════════════════════════════════════════════════════════════════════


def on_transaction_validate(doc, method=None):
	"""Quotation / Sales Order ``validate``: push this save's row changes onto the schedule."""
	if doc.flags.get(SKIP_FLAG) or cint(doc.docstatus) != 0 or _skip_globally():
		return
	name = doc.get("ill_fixture_schedule")
	if not name:
		return
	before = doc.get_doc_before_save()
	if before is None and doc.get("amended_from"):
		return  # An amendment re-copies rows already reconciled on the cancelled document.
	previous_link = before.get("ill_fixture_schedule") if before is not None else None
	if previous_link and previous_link != name:
		return  # Switched to another schedule version; its rows still name the old lines.
	if not frappe.db.exists(SCHEDULE_DOCTYPE, name):
		return
	schedule = frappe.get_doc(SCHEDULE_DOCTYPE, name)
	if not schedule_is_open(schedule):
		return

	plan = plan_transaction_changes(
		[line.name for line in schedule.lines],
		(before.get("items") if before is not None else None) or [],
		doc.get("items") or [],
		newly_linked=not previous_link,
	)
	if not has_changes(plan):
		return

	frappe.db.savepoint(SAVEPOINT)
	try:
		message = push_to_schedule(schedule, doc, plan)
	except Exception:  # Never block the transaction save on schedule bookkeeping.
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.log_error(
			title=f"Schedule sync: {doc.doctype} {doc.name} → {name} failed",
			message=frappe.get_traceback(),
		)
		frappe.msgprint(
			_("Saved, but Fixture Schedule {0} could not be updated to match. See Error Log.").format(name),
			indicator="orange",
			alert=True,
		)
		return
	if message:
		frappe.msgprint(message, indicator="blue", alert=True)


def push_to_schedule(schedule, doc, plan) -> str | None:
	"""Apply ``plan`` to ``schedule``, save it, and mirror its own follow-ups onto ``doc``."""
	from illumenate_lighting.illumenate_lighting.api.desk_configurator import _next_fixture_type

	lines = {line.name: line for line in schedule.lines}
	qty_before = {line.name: flt(line.qty) for line in schedule.lines}
	used = [row.get("ill_fixture_type") for row in doc.get("items") or [] if row.get("ill_fixture_type")]

	added, skipped = [], []
	for row in plan["add"]:
		values = _line_from_row(row)
		if values is None:
			skipped.append(row.get("item_name") or row.item_code)
			continue
		if not values.get("line_id"):
			values["line_id"] = _next_fixture_type(schedule, used)
		used.append(values["line_id"])
		added.append((row, schedule.append("lines", values)))

	removed = 0
	for name in plan["remove"]:
		line = lines[name]
		if not any(other is line for other in schedule.lines):
			continue  # Already dropped with the LED Sheet it belonged to.
		if line.get("configured_led_sheet"):
			from illumenate_lighting.illumenate_lighting.api.led_sheet_configurator import (
				remove_sheet_accessories_for_line,
			)

			remove_sheet_accessories_for_line(schedule, line)
		schedule.set("lines", [other for other in schedule.lines if other is not line])
		removed += 1

	updated, edited = 0, set()
	for row, before_row in plan["update"]:
		line = lines[row.ill_schedule_line_id]
		if not any(other is line for other in schedule.lines):
			continue
		changes = line_updates(line, row, before_row)
		if "accessory_item" in changes:
			item = _sellable_stock_item(changes["accessory_item"])
			if item:
				changes["accessory_item_name"] = item.item_name
			else:
				changes.pop("accessory_item")
		if changes:
			line.update(changes)
			updated += 1
			edited.add(line.name)

	if not (added or removed or updated):
		return _skipped_message(schedule, skipped)

	schedule.flags.ignore_permissions = True
	schedule.flags[SOURCE_FLAG] = (doc.doctype, doc.name)
	schedule.save()

	for row, line in added:
		_set(row, "ill_schedule_line_id", line.name)
		_set(row, "ill_fixture_type", line.line_id)

	# Mirror what the schedule did on its own: supplies and LED Sheet accessories
	# dropped with their line, and supply quantities that follow their fixture.
	remaining = {line.name: line for line in schedule.lines}
	items = doc.get("items") or []
	kept = [
		row
		for row in items
		if not (row.get("ill_schedule_line_id") in qty_before and row.get("ill_schedule_line_id") not in remaining)
	]
	if len(kept) != len(items):
		for index, row in enumerate(kept, 1):
			row.idx = index
		doc.set("items", kept)
	grouped = rows_by_line(doc.get("items"))
	for name, line in remaining.items():
		old = qty_before.get(name)
		if old and name not in edited and flt(line.qty) != old:
			for row in grouped.get(name, []):
				row.qty = flt(row.qty) * flt(line.qty) / old

	message = _("Fixture Schedule {0} updated: {1} line(s) added, {2} removed, {3} changed.").format(
		schedule.name, len(added), removed, updated
	)
	extra = _skipped_message(schedule, skipped)
	return f"{message} {extra}" if extra else message


def _skipped_message(schedule, skipped) -> str | None:
	if not skipped:
		return None
	return _("Kept on this document only (not a stock product line): {0}.").format(", ".join(skipped))


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULE → TRANSACTIONS
# ═══════════════════════════════════════════════════════════════════════


def on_schedule_update(doc, method=None):
	"""Fixture Schedule ``on_update``: push this save's line changes onto its draft transactions."""
	if doc.flags.get(SKIP_FLAG) or _skip_globally() or not schedule_is_open(doc):
		return
	before = doc.get_doc_before_save()
	if before is None:
		return
	plan = plan_schedule_changes(before.get("lines") or [], doc.get("lines") or [])
	if not has_changes(plan):
		return
	source = tuple(doc.flags.get(SOURCE_FLAG) or ())
	for doctype in TRANSACTION_DOCTYPES:
		for name in frappe.get_all(doctype, filters={"ill_fixture_schedule": doc.name, "docstatus": 0}, pluck="name"):
			if (doctype, name) == source:
				continue
			frappe.db.savepoint(SAVEPOINT)
			try:
				push_to_transaction(doc, frappe.get_doc(doctype, name), plan)
			except Exception:  # One stale draft must not block the schedule save.
				frappe.db.rollback(save_point=SAVEPOINT)
				frappe.log_error(
					title=f"Schedule sync: {doc.name} → {doctype} {name} failed",
					message=frappe.get_traceback(),
				)


def push_to_transaction(schedule, target, plan) -> bool:
	"""Bring one draft transaction in line with ``plan``; save it when anything changed."""
	if cint(target.docstatus) != 0:
		return False
	lines = {line.name: line for line in schedule.lines}
	drop = set(plan["removed"]) | set(plan["rebuilt"])
	items = target.get("items") or []
	kept = [row for row in items if row.get("ill_schedule_line_id") not in drop]
	changed = len(kept) != len(items)
	if changed:
		for index, row in enumerate(kept, 1):
			row.idx = index
		target.set("items", kept)

	grouped = rows_by_line(target.get("items"))
	for name, ratio in plan["scaled"].items():
		for row in grouped.get(name, []):
			row.qty = flt(row.qty) * ratio
			changed = True
	for name in plan["relabelled"]:
		line = lines.get(name)
		if line is None:
			continue
		section, notes = schedule._schedule_line_group_fields(line)
		for row in grouped.get(name, []):
			_set(row, "ill_section_label", section)
			_set(row, "ill_fixture_type", line.line_id or None)
			_set(row, "additional_notes", notes)
			changed = True

	wanted = {name for name in (*plan["added"], *plan["rebuilt"]) if name in lines}
	if wanted:
		first_new = len(target.get("items") or [])
		counts = schedule.append_quote_lines(
			target,
			include_accessories=True,
			include_other=False,
			tape_neon_mode="configured_item",
			only_lines=wanted,
		)
		if counts.get("rows_added"):
			changed = True
			target.set("items", place_new_rows([line.name for line in schedule.lines], target.get("items"), first_new))

	if not changed:
		return False
	target.flags[SKIP_FLAG] = True
	target.flags.ignore_permissions = True
	target.save()
	target.add_comment("Info", _("Updated to match Fixture Schedule {0}.").format(schedule.name))
	return True
