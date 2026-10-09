# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Desk CSV import for reviewed field wire (WP-1.4, D7).

One CSV row becomes one sellable Item (Item Group "Field Wire", stock UOM Foot or Spool) and one
``ilL-Spec-Wire``. Start from ``tools/seed_imports/field_wire_TEMPLATE.csv``. The riser's EXAMPLE seed
is never imported: rows whose source reference says "example" are refused.

The import is all-or-nothing. A dry run (the default) reports what would happen; a real run writes
nothing unless every row is valid, and rolls back if any write fails.
"""

import csv
import io

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design import wire
from illumenate_lighting.illumenate_lighting.system_design.access import require_capability
from illumenate_lighting.illumenate_lighting.system_design.api import endpoint
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

SPEC_DOCTYPE = "ilL-Spec-Wire"
ITEM_GROUP = "Field Wire"
MAX_ROWS = 500

COLUMNS = (
	"item_code",
	"item_name",
	"wire_name",
	"category",
	"applications",
	"conductors",
	"listing",
	"rated_v",
	"temp_rating_c",
	"plenum",
	"riser",
	"wet",
	"direct_burial",
	"sunlight_resistant",
	"shielded",
	"impedance_ohm",
	"resistance_ohm_per_kft",
	"ampacity_a",
	"ampacity_basis",
	"od_in",
	"riser_label",
	"sales_uom_mode",
	"spool_length_ft",
	"is_verified",
	"source_reference",
	"is_active",
)
REQUIRED = (
	"item_code",
	"wire_name",
	"category",
	"applications",
	"conductors",
	"listing",
	"rated_v",
	"temp_rating_c",
	"riser_label",
	"source_reference",
)
CHECKS = (
	"plenum",
	"riser",
	"wet",
	"direct_burial",
	"sunlight_resistant",
	"shielded",
	"is_verified",
	"is_active",
)
NUMBERS = ("rated_v", "impedance_ohm", "resistance_ohm_per_kft", "ampacity_a", "od_in", "spool_length_ft")
TRUE = {"1", "y", "yes", "true", "x"}
FALSE = {"", "0", "n", "no", "false"}
ITEM_FIELDS = ["name", "is_sales_item", "disabled", "has_variants", "stock_uom"]


def _check(value, field, problems, default=0):
	text = str(value or "").strip().lower()
	if text == "":
		return default
	if text in TRUE:
		return 1
	if text in FALSE:
		return 0
	problems.append(f"{field} must be yes/no or 1/0")
	return default


def _number(value, field, problems):
	text = str(value or "").strip()
	if text == "":
		return None
	try:
		return float(text)
	except ValueError:
		problems.append(f"{field} must be a number")
		return None


def parse_csv(text):
	"""Parse the CSV text into rows of ``{row, item_code, item_name, spec, problems}``.

	Raises ``DesignError("INVALID")`` for a file that cannot be read at all.
	"""
	if not isinstance(text, str) or not text.strip():
		raise DesignError("INVALID", _("The CSV file is empty"))
	reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
	headers = [h.strip() for h in reader.fieldnames or []]
	missing = [c for c in REQUIRED if c not in headers]
	if missing:
		raise DesignError("INVALID", _("The CSV is missing columns: {0}").format(", ".join(missing)))
	rows, seen = [], {}
	for number, raw in enumerate(reader, start=2):
		values = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k}
		if not any(values.values()):
			continue
		if len(rows) >= MAX_ROWS:
			raise DesignError("INVALID", _("Import at most {0} wire rows at a time").format(MAX_ROWS))
		problems = [f"{c} is required" for c in REQUIRED if not values.get(c)]
		spec = {
			"item": values.get("item_code"),
			"wire_name": values.get("wire_name"),
			"category": wire.category_label(values.get("category")) or values.get("category"),
			"applications": ",".join(wire.split_applications(values.get("applications"))[0])
			or values.get("applications"),
			"listing": values.get("listing"),
			"temp_rating_c": values.get("temp_rating_c"),
			"ampacity_basis": values.get("ampacity_basis") or None,
			"riser_label": values.get("riser_label"),
			"sales_uom_mode": values.get("sales_uom_mode") or "Per Foot",
			"source_reference": values.get("source_reference"),
		}
		for field in NUMBERS:
			spec[field] = _number(values.get(field), field, problems)
		for field in CHECKS:
			spec[field] = _check(values.get(field), field, problems, default=1 if field == "is_active" else 0)
		if spec["sales_uom_mode"] != "Per Spool":
			spec["spool_length_ft"] = None
		conductors, conductor_problems = wire.parse_conductors(values.get("conductors"))
		spec["conductors"] = conductors
		if values.get("conductors"):
			problems += conductor_problems or wire.conductor_problems(conductors)
		problems += wire.spec_problems({**spec, "applications": values.get("applications")})
		code = values.get("item_code")
		if code in seen:
			problems.append(f"item_code {code} is repeated (first on row {seen[code]})")
		elif code:
			seen[code] = number
		rows.append(
			{
				"row": number,
				"item_code": code,
				"item_name": values.get("item_name") or values.get("wire_name"),
				"spec": spec,
				"problems": problems,
			}
		)
	if not rows:
		raise DesignError("INVALID", _("The CSV has no wire rows"))
	return rows


def uom_for(mode):
	return wire.SPOOL_UOM if mode == "Per Spool" else "Foot"


def plan_rows(rows):
	"""Add ``item_action`` / ``spec_action`` and Item problems to each parsed row."""
	for row in rows:
		code, mode = row["item_code"], row["spec"]["sales_uom_mode"]
		item = frappe.db.get_value("Item", code, ITEM_FIELDS, as_dict=True) if code else None
		if item:
			problems = wire.item_problems({**item, "is_sales_item": 1}, mode)
			row["item_action"] = "existing" if item.is_sales_item else "make sellable"
		else:
			problems = []
			row["item_action"] = "create"
		row["problems"] += problems
		row["spec_action"] = "update" if code and frappe.db.exists(SPEC_DOCTYPE, code) else "create"
	return rows


def ensure_wire_masters():
	"""Create the Field Wire Item Group and the Foot / Spool UOMs when missing (idempotent)."""
	# A site that has not run ERPNext setup has no Item Group tree yet; the import reports that later.
	if not frappe.db.exists("Item Group", ITEM_GROUP) and frappe.db.exists("Item Group", "All Item Groups"):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": ITEM_GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	for uom, whole in (("Foot", 0), (wire.SPOOL_UOM, 1)):
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": whole}).insert(
				ignore_permissions=True
			)


def _write_item(row):
	if row["item_action"] == "create":
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": row["item_code"],
				"item_name": row["item_name"],
				"item_group": ITEM_GROUP,
				"stock_uom": uom_for(row["spec"]["sales_uom_mode"]),
				"is_stock_item": 1,
				"is_sales_item": 1,
				"description": row["spec"]["wire_name"],
			}
		).insert(ignore_permissions=True)
	elif row["item_action"] == "make sellable":
		item = frappe.get_doc("Item", row["item_code"])
		item.is_sales_item = 1
		item.save(ignore_permissions=True)


def _write_spec(row):
	values = dict(row["spec"])
	conductors = values.pop("conductors")
	if row["spec_action"] == "update":
		doc = frappe.get_doc(SPEC_DOCTYPE, row["item_code"])
		doc.update(values)
		doc.set("conductors", [])
	else:
		doc = frappe.get_doc({"doctype": SPEC_DOCTYPE, **values})
	for conductor in conductors:
		doc.append("conductors", conductor)
	if row["spec_action"] == "update":
		doc.save(ignore_permissions=True)
	else:
		doc.insert(ignore_permissions=True)


def import_wire_csv(text, dry_run=True):
	"""Parse, check and (unless ``dry_run``) write every row. Returns the per-row report."""
	rows = plan_rows(parse_csv(text))
	invalid = sum(1 for row in rows if row["problems"])
	report = {
		"dry_run": bool(dry_run),
		"written": False,
		"invalid": invalid,
		"rows": [
			{
				"row": row["row"],
				"item_code": row["item_code"],
				"item_action": row["item_action"],
				"spec_action": row["spec_action"],
				"problems": row["problems"],
			}
			for row in rows
		],
	}
	if dry_run or invalid:
		return report
	frappe.db.savepoint("field_wire_import")
	try:
		ensure_wire_masters()
		for row in rows:
			_write_item(row)
			_write_spec(row)
	except Exception:
		frappe.db.rollback(save_point="field_wire_import")
		raise
	report["written"] = True
	return report


@frappe.whitelist(methods=["POST"])
@endpoint
def import_field_wire(csv_text=None, dry_run=1):
	"""Desk: import reviewed field wire. Catalog staff only."""
	require_capability("catalog")
	return import_wire_csv(csv_text, dry_run=str(dry_run).strip().lower() not in {"0", "false", "no"})
