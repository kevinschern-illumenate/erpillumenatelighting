# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Desk APIs for pulling Fixture Schedule line items into a Quotation.

Mirrors the ERPNext "Get Items From" workflow: from a draft Quotation the
user picks a pre-existing ilL-Project-Fixture-Schedule (typically created in
the customer portal) and all of its line items — linear/configured fixtures,
configured LED tape & neon, extrusion kits, accessories / power supplies — are
appended to the quotation.

The heavy lifting lives on the schedule controller
(``ilLProjectFixtureSchedule.append_quote_lines``) so the line representation
stays in lock-step with ``create_sales_order``.
"""

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

SUPPORTED_PARENTS = {"Quotation", "Sales Order"}
SCHEDULE_DOCTYPE = "ilL-Project-Fixture-Schedule"


@frappe.whitelist()
def get_schedule_summary(fixture_schedule: str) -> dict[str, Any]:
	"""Return a per-type line breakdown for the import-preview dialog."""
	if not fixture_schedule:
		frappe.throw(_("Please select a Fixture Schedule."))
	if not frappe.db.exists(SCHEDULE_DOCTYPE, fixture_schedule):
		frappe.throw(_("Fixture Schedule {0} was not found.").format(fixture_schedule))

	schedule = frappe.get_doc(SCHEDULE_DOCTYPE, fixture_schedule)
	schedule.check_permission("read")

	summary = schedule.get_transaction_line_summary()
	return {
		"fixture_schedule": schedule.name,
		"schedule_name": schedule.schedule_name,
		"status": schedule.status,
		"customer": schedule.customer,
		"version": schedule.version,
		"total_lines": len(schedule.lines),
		"summary": summary,
	}


@frappe.whitelist()
def add_schedule_to_quotation(
	quotation: str,
	fixture_schedule: str,
	include_accessories: int | str = 1,
	include_other: int | str = 0,
) -> dict[str, Any]:
	"""Append all line items from ``fixture_schedule`` onto ``quotation``.

	The quotation must be an existing draft (docstatus 0) that the current
	user can write to. The schedule status is left untouched.
	"""
	return _add_schedule_to_transaction(
		"Quotation", quotation, fixture_schedule, include_accessories, include_other
	)


@frappe.whitelist()
def add_schedule_to_transaction(
	parent_doctype: str,
	parent_name: str,
	fixture_schedule: str,
	include_accessories: int | str = 1,
	include_other: int | str = 0,
) -> dict[str, Any]:
	"""Generic entry point — append schedule lines to a Quotation or Sales Order."""
	return _add_schedule_to_transaction(
		parent_doctype, parent_name, fixture_schedule, include_accessories, include_other
	)


def _add_schedule_to_transaction(
	parent_doctype: str,
	parent_name: str,
	fixture_schedule: str,
	include_accessories: int | str,
	include_other: int | str,
) -> dict[str, Any]:
	if parent_doctype not in SUPPORTED_PARENTS:
		frappe.throw(_("Schedule items can only be added to Quotations and Sales Orders."))
	if not parent_name:
		frappe.throw(_("Missing the target {0}.").format(parent_doctype))
	if not fixture_schedule:
		frappe.throw(_("Please select a Fixture Schedule."))
	if not frappe.db.exists(parent_doctype, parent_name):
		frappe.throw(_("{0} {1} was not found.").format(parent_doctype, parent_name))
	if not frappe.db.exists(SCHEDULE_DOCTYPE, fixture_schedule):
		frappe.throw(_("Fixture Schedule {0} was not found.").format(fixture_schedule))

	target_doc = frappe.get_doc(parent_doctype, parent_name)
	target_doc.check_permission("write")
	if cint(target_doc.docstatus) != 0:
		frappe.throw(_("Schedule items can only be added to a draft {0}.").format(parent_doctype))

	schedule = frappe.get_doc(SCHEDULE_DOCTYPE, fixture_schedule)
	schedule.check_permission("read")

	counts = schedule.append_quote_lines(
		target_doc,
		include_accessories=bool(cint(include_accessories)),
		include_other=bool(cint(include_other)),
	)

	if counts.get("rows_added"):
		target_doc.save()

	counts["parent_doctype"] = parent_doctype
	counts["parent_name"] = target_doc.name
	counts["fixture_schedule"] = schedule.name
	return counts
