"""Support Issue read model: current parent access, pagination and reply loop."""

import html
import re

import frappe

from illumenate_lighting.illumenate_lighting.portal.access import get_actor
from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination, is_staff


def description_text(value):
	"""Issue descriptions are HTML (Text Editor); show them as plain text with paragraph breaks."""
	text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", value or "")
	return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def _user_customer(user):
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import _get_user_customer

	return _get_user_customer(user)


def _dealer_customer(actor):
	"""The company whose support tickets ``actor`` sees: a Dealer's own company (FLOW-7)."""
	return actor.customer if actor.is_dealer and actor.customer and not actor.is_internal else None


def _has_project_field():
	return frappe.get_meta("Issue").has_field("ill_project")


def company_members(customer):
	"""Users whose company resolves to ``customer``, by the rule ``access.get_actor`` uses."""
	contacts = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
		pluck="parent",
	)
	if not contacts:
		return []
	rows = frappe.get_all("Contact", filters={"name": ["in", sorted(set(contacts))]}, fields=["user", "email_id"])
	candidates = {row.get("user") or row.get("email_id") for row in rows} - {None, ""}
	return sorted(user for user in candidates if _user_customer(user) == customer)


def is_company_ticket(doc, customer):
	"""Raised by a member of ``customer``, or about one of its orders or projects."""
	if doc.raised_by and _user_customer(doc.raised_by) == customer:
		return True
	order = doc.get("ill_portal_order")
	if order and frappe.db.get_value("Sales Order", order, "customer") == customer:
		return True
	project = doc.get("ill_project")
	return bool(project and frappe.db.get_value("ilL-Project", project, "owner_customer") == customer)


def can_read(doc, user=None):
	user = user or frappe.session.user
	if user == "Guest" or (user != "Administrator" and not frappe.db.get_value("User", user, "enabled")):
		return False
	if is_staff(doc, user):
		return True
	if doc.raised_by != user:
		# Dealers see their company's tickets; everyone else only the tickets they raised.
		customer = _dealer_customer(get_actor(user))
		if not customer or not is_company_ticket(doc, customer):
			return False
	if doc.get("ill_portal_order"):
		from illumenate_lighting.illumenate_lighting.portal.orders import load_accessible_sales_order

		return bool(load_accessible_sales_order(doc.ill_portal_order, user))
	return True


def validate_owner(doc, method=None):
	old = doc.get_doc_before_save()
	owner = doc.get("ill_support_owner")
	if owner and (not old or old.get("ill_support_owner") != owner) and not is_staff(doc, owner):
		frappe.throw("Choose an enabled support System User with native Issue access")


def _conditions(user):
	"""SQL over `tabIssue` matching the tickets ``user`` sees; mirrors :func:`can_read`."""
	actor = get_actor(user)
	params = {"user": user}
	if actor.is_internal:
		return ["raised_by = %(user)s"], params
	customer = _dealer_customer(actor)
	if not customer:
		return ["raised_by = %(user)s", "coalesce(ill_portal_order, '') = ''"], params
	company_orders = "select name from `tabSales Order` where customer=%(customer)s"
	params["customer"] = customer
	params["members"] = tuple(sorted({user, *company_members(customer)}))
	scope = ["raised_by IN %(members)s", f"ill_portal_order IN ({company_orders})"]
	if _has_project_field():
		scope.append("ill_project IN (select name from `tabilL-Project` where owner_customer=%(customer)s)")
	return [
		"(" + " OR ".join(scope) + ")",
		f"(coalesce(ill_portal_order, '') = '' OR ill_portal_order IN ({company_orders}))",
	], params


def _with_raisers(rows, user):
	"""Name who raised each ticket that the viewer did not raise themselves."""
	others = sorted({row.get("raised_by") for row in rows} - {user, None, ""})
	names = (
		dict(frappe.get_all("User", filters={"name": ["in", others]}, fields=["name", "full_name"], as_list=True))
		if others
		else {}
	)
	for row in rows:
		raised_by = row.get("raised_by")
		row["raised_by_me"] = raised_by == user
		row["raised_by_name"] = None if raised_by == user else (names.get(raised_by) or raised_by)
	return rows


@frappe.whitelist()
def list_tickets(page=1, page_size=20, status=None):
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in", frappe.PermissionError)
	page, page_size = _pagination(page, page_size)
	conditions, params = _conditions(frappe.session.user)
	if status == "open":
		conditions.append("status not in ('Closed', 'Resolved')")
	elif status == "closed":
		conditions.append("status in ('Closed', 'Resolved')")
	elif status not in (None, "", "all"):
		frappe.throw("Choose open, closed or all support requests")
	where = " AND ".join(conditions)
	total = frappe.db.sql(f"select count(*) from `tabIssue` where {where}", params)[0][0]
	params.update({"offset": (page - 1) * page_size, "limit": page_size})
	rows = frappe.db.sql(
		f"select name, subject, status, creation, ill_next_action_by, raised_by from `tabIssue` where {where} order by creation desc, name desc limit %(limit)s offset %(offset)s",
		params,
		as_dict=True,
	)
	return {
		"tickets": _with_raisers(rows, frappe.session.user),
		"total": total,
		"page": page,
		"page_size": page_size,
		"company": bool(_dealer_customer(get_actor(frappe.session.user))),
	}


@frappe.whitelist()
def detail(name):
	if not frappe.db.exists("Issue", name):
		frappe.throw("Support request unavailable", frappe.PermissionError)
	doc = frappe.get_doc("Issue", name)
	if not can_read(doc):
		frappe.throw("Support request unavailable", frappe.PermissionError)
	from illumenate_lighting.illumenate_lighting.portal.files import list_files

	return {
		"name": doc.name,
		"subject": doc.subject,
		"status": doc.status,
		"description": doc.description,
		"description_text": description_text(doc.description),
		"creation": doc.creation,
		"order": doc.get("ill_portal_order"),
		"next_action_by": doc.get("ill_next_action_by") or "Staff",
		"files": list_files("Issue", name),
		**_with_raisers([{"raised_by": doc.raised_by}], frappe.session.user)[0],
	}
