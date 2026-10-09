# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Copy earlier decision notes into their portal conversations.

Order review notes, withdrawals, order change outcomes and offer responses used
to live only in their own fields, apart from the conversation. Each note becomes
a conversation message dated when it was recorded, so existing threads read in
order. Re-running posts nothing twice.
"""

import frappe

from illumenate_lighting.illumenate_lighting.portal.conversations import MESSAGE, post

NOTED = ("REVIEW", "REQUEST_INFORMATION", "PROPOSE_CHANGES", "REJECT", "WITHDRAWN")


def _post(doc, body, key, actor, recorded_on):
	name = post(doc, body, key=f"backfill:{key}", actor=actor, notify=False)
	if name and recorded_on:
		frappe.db.set_value(MESSAGE, name, "creation", recorded_on, update_modified=False)


def execute():
	for name in frappe.get_all("ilL-Order-Intake", pluck="name"):
		intake = frappe.get_doc("ilL-Order-Intake", name)
		for row in intake.decisions or []:
			if row.action in NOTED and row.note:
				_post(intake, row.note, row.name, row.actor, row.recorded_on)
	for change in frappe.get_all(
		"ilL-Order-Change",
		filters={"staff_note": ["is", "set"]},
		fields=["name", "staff_note", "decided_by", "decided_on"],
	):
		if change.decided_by:
			doc = frappe.get_doc("ilL-Order-Change", change.name)
			_post(doc, change.staff_note, change.name, change.decided_by, change.decided_on)
	for offer in frappe.get_all(
		"ilL-Quote-Offer",
		filters={"response_note": ["is", "set"]},
		fields=[
			"name",
			"state",
			"quote_request",
			"sales_order",
			"response_note",
			"responded_by",
			"responded_on",
		],
	):
		if offer.state == "ACCEPTED" and offer.sales_order:
			intake = frappe.db.get_value("ilL-Order-Intake", {"sales_order": offer.sales_order}, "name")
			parent = frappe.get_doc("ilL-Order-Intake", intake) if intake else None
			body = f"Accepted offer {offer.name}: {offer.response_note}"
		else:
			parent = frappe.get_doc("ilL-Quote-Request", offer.quote_request) if offer.quote_request else None
			label = "Declined" if offer.state == "DECLINED" else "Requested a revision of"
			body = f"{label} offer {offer.name}: {offer.response_note}"
		if parent and offer.responded_by:
			_post(parent, body, offer.name, offer.responded_by, offer.responded_on)
