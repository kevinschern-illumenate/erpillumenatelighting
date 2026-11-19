"""Offer COB Tape on the Product Finder's product-type question.

Sites seeded before COB Tape became its own family have a family question without it, so
neither the Finder quiz nor the /portal/configure chooser offered it. Add the shipped COB
Tape option right after LED Tape. A question that already has a COB Tape row, active or
not, is left alone, so a row staff turned off stays off. Saving the question bumps the
Finder content version, which refreshes cached definitions.
"""

import json
from pathlib import Path

import frappe

from illumenate_lighting.illumenate_lighting.portal.product_finder.content import QUESTION

SEED = Path(__file__).resolve().parents[1] / "illumenate_lighting/portal/product_finder/seed/content.json"
COB_TAPE, LED_TAPE = "COB Tape", "LED Tape"


def execute():
	if not frappe.db.table_exists(QUESTION):
		return
	option = seed_option()
	for name in frappe.get_all(QUESTION, filters={"question_type": "Family chooser"}, pluck="name"):
		doc = frappe.get_doc(QUESTION, name)
		if add_option(doc, option):
			doc.save(ignore_permissions=True)


def seed_option() -> dict:
	content = json.loads(SEED.read_text(encoding="utf-8"))
	for question in content["questions"]:
		for option in question.get("options") or []:
			if question.get("question_type") == "Family chooser" and option.get("value") == COB_TAPE:
				return dict(option)
	return {"value": COB_TAPE, "label": COB_TAPE, "is_active": 1}


def add_option(doc, option) -> bool:
	"""Insert ``option`` after the LED Tape row (or last) and renumber; False when already there."""
	rows = list(doc.get("options") or [])
	if any(row.get("value") == COB_TAPE for row in rows):
		return False
	row = doc.append("options", option)
	rows = [r for r in doc.get("options") if r is not row]
	after = next((i + 1 for i, r in enumerate(rows) if r.get("value") == LED_TAPE), len(rows))
	rows.insert(after, row)
	for idx, r in enumerate(rows, start=1):
		r.idx = idx
	doc.set("options", rows)
	return True
