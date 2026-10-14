"""Move project end clients and teams from Customers to dealer-scoped project parties (DESK-9).

Architect, lighting designer and general contractor now link ``ilL-Project-Party``.
For each project naming a Customer there, create (or reuse) a party of the
project's owner company with that Customer's name and repoint the field.

The end client stays in ``customer`` (schedules, quotes and exports read it as a
Customer). When that Customer was created by a website user (a dealer's
portal-created end client), the project also gets an End Client party.

Customers are never changed or deleted; each party records the Customer it came
from (``source_customer``) so staff can disable the portal-created ones later. A
team Customer created by staff is a real Customer, so its party links it
(``customer``) as already promoted.

Idempotent: fields that already name a party, and projects that already have an
end-client party, are skipped; parties are reused by company, role and name.
"""

import frappe

from illumenate_lighting.illumenate_lighting.portal.project_parties import (
	DOCTYPE,
	END_CLIENT,
	PROJECT,
	ROLE_FIELDS,
	TEAM_FIELDS,
	clean_name,
	find,
)


def execute():
	stats = migrate()
	frappe.db.commit()
	if stats["skipped"]:
		frappe.log_error(
			title="DESK-9: project parties not migrated",
			message="\n".join(stats["skipped"]),
		)


def migrate():
	cache = {"users": {}, "customers": {}, "companies": {}}
	stats = {"parties": 0, "projects": 0, "skipped": []}
	rows = frappe.get_all(
		PROJECT,
		fields=["name", "owner", "owner_customer", "customer", "end_client_party", *TEAM_FIELDS],
		order_by="creation asc",
	)
	for project in rows:
		values = {}
		for field in TEAM_FIELDS:
			value = project.get(field)
			if not value or frappe.db.exists(DOCTYPE, value):
				continue
			party = _party_for(project, value, ROLE_FIELDS[field], cache, stats, end_client=False)
			if party:
				values[field] = party
		customer = project.get("customer")
		if (
			customer
			and not project.get("end_client_party")
			and customer != project.get("owner_customer")
			and _customer(customer, cache)
			and _is_website_user(_customer(customer, cache).owner, cache)
		):
			party = _party_for(project, customer, END_CLIENT, cache, stats, end_client=True)
			if party:
				values["end_client_party"] = party
		if values:
			frappe.db.set_value(PROJECT, project.name, values, update_modified=False)
			stats["projects"] += 1
	return stats


def _party_for(project, customer_name, role, cache, stats, end_client):
	customer = _customer(customer_name, cache)
	if not customer:
		stats["skipped"].append(f"{project.name}: {role} {customer_name} is not a Customer")
		return None
	company = (
		project.get("owner_customer")
		or (_company(customer.owner, cache) if _is_website_user(customer.owner, cache) else None)
		or _company(project.get("owner"), cache)
	)
	if not company:
		stats["skipped"].append(f"{project.name}: no dealer company for {role} {customer_name}")
		return None
	party_name = clean_name(customer.customer_name or customer.name)
	existing = find(company, role, party_name)
	if existing:
		return existing
	staff_customer = not end_client and not _is_website_user(customer.owner, cache)
	party = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"party_name": party_name,
			"role": role,
			"owner_customer": company,
			"source_customer": customer.name,
			"customer": customer.name if staff_customer else None,
			"website": customer.get("website"),
		}
	)
	party.insert(ignore_permissions=True)
	stats["parties"] += 1
	return party.name


def _customer(name, cache):
	if name not in cache["customers"]:
		cache["customers"][name] = frappe.db.get_value(
			"Customer", name, ["name", "customer_name", "owner", "website"], as_dict=True
		)
	return cache["customers"][name]


def _is_website_user(user, cache):
	if not user or user in ("Administrator", "Guest"):
		return False
	if user not in cache["users"]:
		cache["users"][user] = frappe.db.get_value("User", user, "user_type")
	return cache["users"][user] == "Website User"


def _company(user, cache):
	if not user or user in ("Administrator", "Guest"):
		return None
	if user not in cache["companies"]:
		from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import _get_user_customer

		cache["companies"][user] = _get_user_customer(user)
	return cache["companies"][user]
