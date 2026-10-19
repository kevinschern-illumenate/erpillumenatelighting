# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Dealer-scoped project parties instead of portal-created Customers (DESK-9).

Dealers name the end client, architect, lighting designer and general
contractor on a project. Those used to be ERPNext Customers, so two dealers
could not both use "Acme GC" and the Desk Customer list filled with parties
that never buy. An ``ilL-Project-Party`` belongs to one dealer company
(``owner_customer``); names are unique per company and role only.

A party becomes a real Customer only when Sales promotes it
(:func:`promote_to_customer`), because ilLumenate quotes or bills it directly.

The project's ``customer`` field stays a Customer link: schedules copy it, and
Desk quotations, exports and the Webflow and Desk configurators read it as a
Customer. A portal project's end client is ``end_client_party``; its
``customer`` is the dealer company until the party is promoted.
"""

import frappe
from frappe import _

DOCTYPE = "ilL-Project-Party"
PROJECT = "ilL-Project"

END_CLIENT = "End Client"
ROLE_FIELDS = {
	"end_client_party": END_CLIENT,
	"architect": "Architect",
	"lighting_designer": "Lighting Designer",
	"general_contractor": "General Contractor",
}
ROLES = tuple(ROLE_FIELDS.values())
TEAM_FIELDS = ("architect", "lighting_designer", "general_contractor")
CONTACT_FIELDS = ("contact_person", "email", "phone", "website", "address", "notes")
DENY = "1=0"


def clean_name(value) -> str:
	"""Trim and collapse whitespace so "Acme  GC " and "Acme GC" are one party."""
	return " ".join(str(value or "").split())[:140]


# ---------------------------------------------------------------------------
# Who may do what
# ---------------------------------------------------------------------------


def _is_staff(user) -> bool:
	"""Desk staff with sales access (and System Managers) manage every company's parties."""
	from illumenate_lighting.illumenate_lighting.portal.project_owner import can_set_owner_company

	return bool(can_set_owner_company(user))


def _unrestricted(user) -> bool:
	if user == "Administrator":
		return True
	return frappe.db.get_value("User", user, "user_type") == "System User"


def query_conditions(user=None) -> str:
	"""List scope: Desk users are limited by their role permissions; website users see their company's."""
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	user = user or frappe.session.user
	if user == "Guest":
		return DENY
	if _unrestricted(user):
		return ""
	actor = get_actor(user)
	if actor.is_guest or not actor.customer:
		return DENY
	return f"`tab{DOCTYPE}`.owner_customer = {frappe.db.escape(actor.customer)}"


def has_permission(doc, ptype="read", user=None) -> bool:
	"""Website users read their company's parties; only its dealers change them; nobody else."""
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	user = user or frappe.session.user
	if user == "Guest":
		return False
	if _unrestricted(user):
		return True
	actor = get_actor(user)
	if actor.is_guest or not actor.customer or doc.get("owner_customer") != actor.customer:
		return False
	if ptype == "read":
		return True
	return bool(actor.is_dealer and ptype in ("write", "create"))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def labels(names) -> dict:
	"""``{party: party_name}`` for the given party names, in one query."""
	names = sorted({name for name in names if name})
	if not names:
		return {}
	rows = frappe.get_all(DOCTYPE, filters={"name": ["in", names]}, fields=["name", "party_name"])
	return {row.name: row.party_name or row.name for row in rows}


def label(name):
	if not name:
		return None
	return frappe.db.get_value(DOCTYPE, name, "party_name") or name


def project_labels(project) -> dict:
	"""``{field: party_name}`` for each party a project names (end client and team)."""
	values = {field: project.get(field) for field in ROLE_FIELDS if project.get(field)}
	names = labels(values.values())
	return {field: names.get(value, value) for field, value in values.items()}


def end_client_label(project):
	"""The end client's display name: the party when set, else the Customer's name."""
	party = project.get("end_client_party")
	if party:
		return label(party)
	customer = project.get("customer")
	if not customer:
		return None
	return frappe.db.get_value("Customer", customer, "customer_name") or customer


def options(owner_customer) -> dict:
	"""``{field: [{"value", "label"}]}`` of the company's enabled parties, for each project role field."""
	choices = {field: [] for field in ROLE_FIELDS}
	if not owner_customer:
		return choices
	rows = frappe.get_all(
		DOCTYPE,
		filters={"owner_customer": owner_customer, "disabled": 0},
		fields=["name", "party_name", "role"],
		order_by="party_name asc",
	)
	fields = {role: field for field, role in ROLE_FIELDS.items()}
	for row in rows:
		field = fields.get(row.role)
		if field:
			choices[field].append({"value": row.name, "label": row.party_name or row.name})
	return choices


def picker_company(project=None, owner_customer=None, user=None):
	"""Which company's parties a project form may list for ``user``.

	Staff list the company they name (or the project's); everyone else lists
	their own company's, and only for a project of their own company.
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	user = user or frappe.session.user
	project_owner = project.get("owner_customer") if project else None
	if _is_staff(user):
		return project_owner or owner_customer or None
	actor = get_actor(user)
	if actor.is_guest or not actor.customer:
		return None
	if project is not None and project_owner != actor.customer:
		return None
	return actor.customer


def picker_options(project=None, owner_customer=None, user=None) -> dict:
	"""Options for the project form's party selects, keeping the project's current choices listed."""
	choices = options(picker_company(project, owner_customer, user))
	if project is not None:
		current = project_labels(project)
		for field, value in ((field, project.get(field)) for field in ROLE_FIELDS):
			if value and not any(option["value"] == value for option in choices[field]):
				choices[field].append({"value": value, "label": current.get(field, value)})
	return choices


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def find(owner_customer, role, party_name):
	"""The company's existing party with this name and role (database collation ignores case)."""
	return frappe.db.get_value(
		DOCTYPE, {"owner_customer": owner_customer, "role": role, "party_name": party_name}, "name"
	)


def create(data, user=None) -> dict:
	"""Create a party for the user's company, or return the one it already has by that name and role.

	Dealers always create for their own company. Staff name the company
	(``owner_customer``), normally the project's owner company.
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor

	user = user or frappe.session.user
	data = data or {}
	staff = _is_staff(user)
	actor = get_actor(user)
	if staff or actor.is_internal:
		owner_customer = clean_name(data.get("owner_customer")) or actor.customer
		if not owner_customer:
			frappe.throw(_("Choose the dealer company first."))
		if not frappe.db.exists("Customer", owner_customer):
			frappe.throw(_("Company {0} does not exist.").format(owner_customer))
	elif actor.is_dealer and actor.customer:
		owner_customer = actor.customer
	else:
		frappe.throw(_("Only dealers can add companies or people to a project."), frappe.PermissionError)

	party_name = clean_name(data.get("party_name"))
	if not party_name:
		frappe.throw(_("Name is required."))
	role = data.get("role")
	if role not in ROLES:
		frappe.throw(_("Choose a role: {0}.").format(", ".join(ROLES)))

	existing = find(owner_customer, role, party_name)
	if existing:
		return {"party": existing, "label": label(existing), "role": role, "existing": True}

	party = frappe.new_doc(DOCTYPE)
	party.update(
		{
			"party_name": party_name,
			"role": role,
			"owner_customer": owner_customer,
			**{field: str(data.get(field) or "").strip() or None for field in CONTACT_FIELDS},
		}
	)
	# The role gate and company scope are checked above, for dealers and staff alike.
	party.insert(ignore_permissions=True)
	return {"party": party.name, "label": party.party_name, "role": role, "existing": False}


def validate_party(party_name: str, owner_customer, role, party=None):
	"""Raise unless ``party_name`` names a ``role`` party of ``owner_customer``."""
	party = party or frappe.db.get_value(
		DOCTYPE, party_name, ["name", "party_name", "role", "owner_customer"], as_dict=True
	)
	if not party:
		frappe.throw(_("{0} is not a known project party.").format(party_name))
	if party.role != role:
		frappe.throw(_("{0} is not a {1}.").format(party.party_name, _(role)))
	if owner_customer and party.owner_customer != owner_customer:
		frappe.throw(_("{0} belongs to another company.").format(party.party_name), frappe.PermissionError)
	return party


def validate_project(project):
	"""Each changed party field names a party of the right role from the project's owner company.

	Unchanged values are left alone, so moving a project to another company
	does not block saving it with the previous company's parties.
	"""
	previous = None if project.is_new() else project.get_doc_before_save()
	for field, role in ROLE_FIELDS.items():
		value = project.get(field)
		if not value or (previous is not None and previous.get(field) == value):
			continue
		validate_party(value, project.get("owner_customer"), role)


def project_customer(project_data, owner_customer):
	"""The Customer a new project bills and syncs to its schedules when the form names no Customer.

	A promoted end client is that Customer; otherwise the owner (dealer) company.
	"""
	party = project_data.get("end_client_party")
	if party:
		promoted = frappe.db.get_value(DOCTYPE, party, "customer")
		if promoted:
			return promoted
	return owner_customer


# ---------------------------------------------------------------------------
# Promotion (Desk)
# ---------------------------------------------------------------------------


def _new_customer(party):
	customer = frappe.new_doc("Customer")
	customer.customer_name = party.party_name
	customer.customer_type = "Company"
	customer.customer_group = (
		frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
	)
	customer.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
	if party.get("website"):
		customer.website = party.website
	customer.insert()
	return customer.name


@frappe.whitelist(methods=["POST"])
def promote_to_customer(party: str, customer: str | None = None) -> dict:
	"""Link a party to a Customer, creating one, because Sales quotes or bills it directly.

	``customer`` links an existing Customer instead. A new Customer whose name is
	already taken is refused rather than silently linked to a different company.
	Projects that name this party as end client and still bill the owner company
	switch their Customer to the promoted one.
	"""
	from illumenate_lighting.illumenate_lighting.portal.staff import require

	require("sales")
	doc = frappe.get_doc(DOCTYPE, party)
	if doc.customer and not customer:
		return {"customer": doc.customer, "created": False, "projects": []}
	created = False
	if customer:
		if not frappe.db.exists("Customer", customer):
			frappe.throw(_("Customer {0} does not exist.").format(customer))
	else:
		if frappe.db.exists("Customer", {"customer_name": doc.party_name}):
			frappe.throw(
				_("A Customer named {0} already exists. Choose it to link this party to it.").format(
					doc.party_name
				)
			)
		customer = _new_customer(doc)
		created = True
	doc.db_set("customer", customer)

	projects = []
	if doc.role == END_CLIENT:
		for row in frappe.get_all(
			PROJECT, filters={"end_client_party": doc.name}, fields=["name", "customer", "owner_customer"]
		):
			if not row.customer or row.customer == row.owner_customer:
				frappe.db.set_value(PROJECT, row.name, "customer", customer)
				projects.append(row.name)
	return {"customer": customer, "created": created, "projects": projects}
