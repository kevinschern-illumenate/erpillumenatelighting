"""Support Issue read model: current parent access, pagination and reply loop."""

import frappe

from illumenate_lighting.illumenate_lighting.portal.access import get_actor
from illumenate_lighting.illumenate_lighting.portal.conversations import _pagination, is_staff


def can_read(doc, user=None):
	user = user or frappe.session.user
	if user == "Guest" or (user != "Administrator" and not frappe.db.get_value("User", user, "enabled")):
		return False
	if is_staff(doc, user):
		return True
	if doc.raised_by != user:
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
	actor = get_actor(user)
	params = {"user": user}
	conditions = ["raised_by = %(user)s"]
	if actor.is_internal:
		return conditions, params
	if actor.is_dealer and actor.customer:
		conditions.append(
			"(coalesce(ill_portal_order, '') = '' OR ill_portal_order IN (select name from `tabSales Order` where customer=%(customer)s))"
		)
		params["customer"] = actor.customer
	else:
		conditions.append("coalesce(ill_portal_order, '') = ''")
	return conditions, params


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
		f"select name, subject, status, creation, ill_next_action_by from `tabIssue` where {where} order by creation desc, name desc limit %(limit)s offset %(offset)s",
		params,
		as_dict=True,
	)
	return {"tickets": rows, "total": total, "page": page, "page_size": page_size}


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
		"creation": doc.creation,
		"order": doc.get("ill_portal_order"),
		"next_action_by": doc.get("ill_next_action_by") or "Staff",
		"files": list_files("Issue", name),
	}
