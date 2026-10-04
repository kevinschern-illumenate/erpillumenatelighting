"""Environment Rating codes that other records keep a copy of.

An Environment Rating's ``code`` is the order code its part numbers carry (Dry 20,
Damp 54, Wet 67, and later Wet+ 68). Two places store a copy:

- LED Sheet templates, on each Environment Rating option row (``option_code``),
  which the Sheet part number and panel matching read.
- Fixture Template Part Number Builders, in the Dry/Wet section exported to the
  spec-sheet ordering guide.

These helpers keep both copies equal to the rating.
"""

import json
import re

import frappe

ENVIRONMENT_RATING = "ilL-Attribute-Environment Rating"
IP_RATING = "ilL-Attribute-IP Rating"
SHEET_TEMPLATE = "ilL-LED-Sheet-Template"
FIXTURE_TEMPLATE = "ilL-Fixture-Template"

# A mounting accessory approved for Wet (IP67) also serves IP68 products (Wet+ or an
# IP68 neon segment). This is for accessories only: configurations never substitute
# one rating's tape, spec or part number for another's.
WET_IP = 67


def ip_number(doctype: str, name: str | None) -> int | None:
	"""The IP number a rating stands for: Wet → 67 (its code), IP68 → 68."""
	if not name:
		return None
	code = str(frappe.db.get_value(doctype, name, "code") or "").strip()
	if code.isdigit():
		return int(code)
	match = re.fullmatch(r"IP(\d+)", str(name).strip(), re.IGNORECASE)
	return int(match.group(1)) if match else None


def configuration_environments(environment_rating=None, ip_ratings=()) -> list[tuple[str, int | None]]:
	"""``(name, IP number)`` for a tape's Environment Rating and each neon segment's IP Rating."""
	if isinstance(ip_ratings, str):
		ip_ratings = json.loads(ip_ratings) if ip_ratings.strip().startswith("[") else ip_ratings.split(",")
	found = {}
	if environment_rating:
		found[environment_rating] = ip_number(ENVIRONMENT_RATING, environment_rating)
	for ip in ip_ratings or ():
		ip = (ip or "").strip()
		if ip and ip not in found:
			found[ip] = ip_number(IP_RATING, ip)
	return list(found.items())


def accessory_serves(row_environment: str | None, environments) -> bool:
	"""True when a mounting-accessory map row tagged *row_environment* serves every configuration environment.

	An untagged row serves anything. A tagged row serves its own rating and any rating
	with the same IP number; a Wet (IP67) or higher row also serves higher IP numbers.
	"""
	if not row_environment:
		return True
	row_number = ip_number(ENVIRONMENT_RATING, row_environment)
	for name, number in environments:
		if name == row_environment:
			continue
		if row_number is None or number is None:
			return False
		if not (row_number == number or WET_IP <= row_number <= number):
			return False
	return True


def sync_sheet_template(doc) -> bool:
	"""Give each Environment Rating option on an LED Sheet template its rating's current code."""
	changed = False
	for row in doc.get("allowed_options") or []:
		if row.option_type != "Environment Rating" or not row.attribute_link:
			continue
		code = frappe.db.get_value(ENVIRONMENT_RATING, row.attribute_link, "code")
		if code and row.option_code != code:
			row.option_code = code
			changed = True
	return changed


def propagate(environment_rating: str | None = None) -> list[str]:
	"""Re-sync the records that copy Environment Rating codes; return the ones that failed to save.

	With *environment_rating*, only templates that offer that rating are visited.
	"""
	from illumenate_lighting.illumenate_lighting.doctype.ill_fixture_template.ill_fixture_template import (
		sync_environment_section,
	)

	sheet_filters = {"parenttype": SHEET_TEMPLATE, "option_type": "Environment Rating"}
	fixture_filters = {"parenttype": FIXTURE_TEMPLATE, "option_type": "Environment Rating"}
	if environment_rating:
		sheet_filters["attribute_link"] = environment_rating
		fixture_filters["environment_rating"] = environment_rating
	sheets = set(frappe.get_all("ilL-Child-LED-Sheet-Allowed-Option", filters=sheet_filters, pluck="parent"))
	# Only builders that already have a Dry/Wet section; Populate fills empty ones.
	fixtures = set(
		frappe.get_all("ilL-Child-Template-Allowed-Option", filters=fixture_filters, pluck="parent")
	) & set(
		frappe.get_all(
			"ilL-Child-PN-Builder-Row",
			filters={"parenttype": FIXTURE_TEMPLATE, "section_name": "Dry/Wet"},
			pluck="parent",
		)
	)

	failed = []
	for doctype, names, sync in (
		(SHEET_TEMPLATE, sheets, sync_sheet_template),
		(FIXTURE_TEMPLATE, fixtures, sync_environment_section),
	):
		for name in sorted(names):
			try:
				doc = frappe.get_doc(doctype, name)
				if sync(doc):
					doc.save(ignore_permissions=True)
			except Exception:
				frappe.log_error(title="Environment Rating code sync", message=frappe.get_traceback())
				failed.append(f"{doctype} {name}")
	return failed
