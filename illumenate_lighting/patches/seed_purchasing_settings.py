# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Seed ilL-Purchasing-Settings once (insert-if-missing; never overwrites staff edits).

* Company and warehouse: the ones Draft MR used before, when they exist on the site.
* Default lead times by item group: extrusions 10 days, tape / neon / sheet 35, power
  and controls 28 (the old Command Center API's category defaults), matched to existing
  Item Group names. Groups already in the table are left alone.
* Cost type defaults (decisions D2/D3): freight-in, duty, tariffs, MPF/HMF, brokerage,
  insurance and drayage are landed (capitalized); storage/demurrage, sales/use tax and
  other are expensed. Accounts are filled only when a matching account exists.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.purchasing import COST_TYPES, FALLBACK_COSTS, SETTINGS

COMPANY = "ilLumenate Lighting"
WAREHOUSE = "Stores - ilL"
# item group name keyword -> lead time (days)
GROUP_LEADS = (
	(("extrusion",), 10),
	(("tape", "neon", "sheet"), 35),
	(("power", "control", "driver"), 28),
)
# cost type -> account name stem (company abbreviation suffix added)
ACCOUNTS = {
	"Freight": "Freight In",
	"Drayage / delivery": "Freight In",
	"Duty": "Duties & Tariffs",
	"Tariff (additional)": "Duties & Tariffs",
	"MPF / HMF": "Duties & Tariffs",
	"Brokerage": "Customs Brokerage",
	"Insurance": "Inbound Insurance",
}


def _account(stem):
	return frappe.db.get_value("Account", {"account_name": stem, "is_group": 0}, "name")


def execute():
	if not frappe.db.exists("DocType", SETTINGS):
		return
	doc = frappe.get_single(SETTINGS)
	if not doc.company and frappe.db.exists("Company", COMPANY):
		doc.company = COMPANY
	if not doc.default_warehouse and frappe.db.exists("Warehouse", WAREHOUSE):
		doc.default_warehouse = WAREHOUSE
	have = {r.item_group for r in doc.get("default_lead_times") or []}
	groups = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name", limit_page_length=0)
	groups += frappe.get_all("Item Group", filters={"is_group": 1}, pluck="name", limit_page_length=0)
	for name in groups:
		if name in have:
			continue
		lowered = name.lower()
		for words, days in GROUP_LEADS:
			if any(w in lowered for w in words):
				doc.append("default_lead_times", {"item_group": name, "lead_time_days": days})
				have.add(name)
				break
	types = {r.cost_type for r in doc.get("cost_type_defaults") or []}
	for cost_type in COST_TYPES:
		if cost_type in types:
			continue
		rule = FALLBACK_COSTS[cost_type]
		stem = ACCOUNTS.get(cost_type)
		doc.append(
			"cost_type_defaults",
			{
				"cost_type": cost_type,
				"include_in_landed_cost": rule["include_in_landed_cost"],
				"allocation": rule["allocation"],
				"estimate_pct_of_value": rule["estimate_pct_of_value"],
				"expense_account": _account(stem) if stem else None,
			},
		)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save()
