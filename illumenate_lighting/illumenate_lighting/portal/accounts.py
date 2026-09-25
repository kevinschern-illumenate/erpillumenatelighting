"""Company-scoped account maintenance and expiring invitations; no delegated staff roles."""

import hashlib
import json
import secrets

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build
from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint
from illumenate_lighting.illumenate_lighting.portal.access import get_actor
from illumenate_lighting.illumenate_lighting.portal.staff import allowed

INTAKE = "ilL-Account-Request"
INVITE = "ilL-Portal-Invitation"
ADDRESS_FIELDS = (
	"address_title",
	"address_type",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"country",
	"pincode",
	"phone",
	"email_id",
)
CONTACT_FIELDS = ("first_name", "last_name", "designation", "phone", "email_id", "company_name")
REQUEST_TYPES = (
	"Dealer application",
	"Company linkage",
	"Profile change",
	"Account closure",
	"Address change",
	"Contact change",
)


def _login():
	if frappe.session.user == "Guest" or not frappe.db.get_value("User", frappe.session.user, "enabled"):
		frappe.throw("Please sign in with an active account", frappe.PermissionError)


def company(user=None):
	actor = get_actor(user)
	if (
		actor.is_guest
		or not actor.is_dealer
		or not actor.customer
		or not frappe.db.get_value("User", actor.user, "enabled")
	):
		frappe.throw("A dealer linked to this company is required", frappe.PermissionError)
	return actor.customer


def linked_to(doc, customer):
	return any(row.link_doctype == "Customer" and row.link_name == customer for row in doc.get("links") or [])


def require_owned(doc, customer, *, exclusive=False):
	if not linked_to(doc, customer) or (
		exclusive
		and any(row.link_doctype != "Customer" or row.link_name != customer for row in doc.get("links") or [])
	):
		frappe.throw(
			"This contact or address is outside the approved customer context", frappe.PermissionError
		)
	if doc.get("disabled") or doc.get("ill_portal_archived"):
		raise ValueError("This contact or address has been archived")
	return doc


def selections(customer):
	"""Caller must first authorize the commercial customer (also used by direct PO intake)."""
	result = {}
	for doctype, fields in (("Address", ADDRESS_FIELDS), ("Contact", CONTACT_FIELDS)):
		names = frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": doctype, "link_doctype": "Customer", "link_name": customer},
			pluck="parent",
			distinct=True,
		)
		rows = (
			frappe.get_all(
				doctype,
				filters={
					"name": ["in", names],
					"disabled" if doctype == "Address" else "ill_portal_archived": 0,
				},
				fields=["name", "modified", *fields, *(["user"] if doctype == "Contact" else [])],
				order_by="modified desc",
			)
			if names
			else []
		)
		result[doctype.lower()] = rows
	return result


@frappe.whitelist()
def overview():
	_login()
	actor = get_actor()
	result = {
		"success": True,
		"customer": actor.customer,
		"can_manage": bool(actor.is_dealer and actor.customer),
		"requests": frappe.get_all(
			INTAKE,
			filters={"requested_by": actor.user},
			fields=["name", "request_type", "state", "staff_note", "creation"],
			order_by="creation desc",
			limit=50,
		),
	}
	if result["can_manage"]:
		result.update(selections(actor.customer))
		result["invitations"] = frappe.get_all(
			INVITE,
			filters={"customer": actor.customer, "project": ["is", "not set"]},
			fields=["name", "email", "state", "expires_on", "accepted_on"],
			order_by="creation desc",
			limit=100,
		)
		members = {row.user for row in result["contact"] if row.user}
		result["members"] = (
			frappe.get_all(
				"User",
				filters={"name": ["in", list(members)]},
				fields=["name", "full_name", "enabled", "user_type"],
			)
			if members
			else []
		)
		result["purchasing_contact"] = frappe.db.get_value(
			"Customer", actor.customer, "ill_purchasing_contact"
		)
	return result


def _new_request(
	request_type,
	data,
	*,
	customer=None,
	reference_type=None,
	reference_name=None,
	expected_modified=None,
	idempotency_key=None,
):
	body = {
		"type": request_type,
		"data": data,
		"customer": customer,
		"reference_type": reference_type,
		"reference_name": reference_name,
		"expected_modified": str(expected_modified or ""),
	}
	digest = fingerprint(body)
	key = fingerprint({"actor": frappe.session.user, "key": idempotency_key or digest})
	frappe.db.sql("select name from `tabUser` where name=%s for update", frappe.session.user)
	old = frappe.db.get_value(INTAKE, {"request_key": key}, ["name", "request_hash", "state"], as_dict=True)
	if old:
		if old.request_hash != digest:
			raise ValueError("This request key already represents different content")
		return {"success": True, "request": old.name, "state": old.state}
	doc = frappe.get_doc(
		{
			"doctype": INTAKE,
			"request_type": request_type,
			"requested_by": frappe.session.user,
			"customer": customer,
			"reference_type": reference_type,
			"reference_name": reference_name,
			"expected_modified": str(expected_modified or ""),
			"proposed_json": canonical_json(data),
			"request_key": key,
			"request_hash": digest,
			"state": "Pending",
		}
	)
	doc.flags.account_service = True
	doc.insert(ignore_permissions=True)
	return {"success": True, "request": doc.name, "state": doc.state}


@frappe.whitelist(methods=["POST"])
@atomic_build
def request_change(request_type, note, idempotency_key=None):
	_login()
	if (
		request_type not in REQUEST_TYPES[:4]
		or not isinstance(note, str)
		or not note.strip()
		or len(note) > 8000
	):
		raise ValueError("Choose an account request type and describe the requested change")
	return _new_request(
		request_type, {"note": note.strip()}, customer=get_actor().customer, idempotency_key=idempotency_key
	)


def _clean(doctype, values):
	values = json.loads(values) if isinstance(values, str) else values
	fields = ADDRESS_FIELDS if doctype == "Address" else CONTACT_FIELDS
	if not isinstance(values, dict) or set(values) - set(fields):
		raise ValueError("Only the displayed address or contact fields can be changed")
	data = {key: str(value or "").strip() for key, value in values.items()}
	if any(len(value) > 240 for value in data.values()):
		raise ValueError("Address and contact fields are limited to 240 characters")
	if data.get("email_id") and not frappe.utils.validate_email_address(data["email_id"]):
		raise ValueError("Enter a valid email address")
	return data


def _apply_contact(doc, data):
	if (
		data.get("email_id")
		and frappe.db.exists("User", data["email_id"])
		and doc.get("user") != data["email_id"]
	):
		raise ValueError("Use an invitation or staff identity reconciliation to associate a portal account")
	for field, value in data.items():
		if field in ("email_id", "phone"):
			child, child_field, primary = (
				("email_ids", "email_id", "is_primary")
				if field == "email_id"
				else ("phone_nos", "phone", "is_primary_phone")
			)
			doc.set(child, [{child_field: value, primary: 1}] if value else [])
		else:
			doc.set(field, value)


@frappe.whitelist(methods=["POST"])
@atomic_build
def save_record(doctype, values, name=None, expected_modified=None):
	customer = company()
	if doctype not in ("Address", "Contact"):
		raise ValueError("Choose Address or Contact")
	data = _clean(doctype, values)
	if name:
		frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name)
		doc = require_owned(frappe.get_doc(doctype, name), customer, exclusive=True)
		if str(doc.modified) != str(expected_modified):
			raise ValueError("This record changed. Reload before requesting a change.")
		return _new_request(
			doctype + " change",
			data,
			customer=customer,
			reference_type=doctype,
			reference_name=name,
			expected_modified=expected_modified,
		)
	doc = frappe.new_doc(doctype)
	if doctype == "Contact":
		if not data.get("first_name"):
			raise ValueError("First name is required")
		# A contact email alone must never establish a new User/company identity.
		if data.get("email_id") and frappe.db.exists("User", data["email_id"]):
			raise ValueError("Use a scoped invitation to link an existing portal user")
		_apply_contact(doc, data)
		doc.ill_portal_contact_only = 1
	else:
		doc.update(data)
	doc.append("links", {"link_doctype": "Customer", "link_name": customer})
	doc.insert(ignore_permissions=True)
	return {"success": True, "name": doc.name, "modified": str(doc.modified)}


@frappe.whitelist(methods=["POST"])
@atomic_build
def archive_record(doctype, name, expected_modified):
	customer = company()
	if doctype not in ("Address", "Contact"):
		raise ValueError("Choose Address or Contact")
	frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", name)
	doc = require_owned(frappe.get_doc(doctype, name), customer, exclusive=True)
	if str(doc.modified) != str(expected_modified):
		raise ValueError("This record changed. Reload before requesting archival.")
	return _new_request(
		doctype + " change",
		{"archive": True},
		customer=customer,
		reference_type=doctype,
		reference_name=name,
		expected_modified=expected_modified,
	)


@frappe.whitelist(methods=["POST"])
@atomic_build
def set_purchasing_contact(contact):
	customer = company()
	require_owned(frappe.get_doc("Contact", contact), customer)
	frappe.db.set_value("Customer", customer, "ill_purchasing_contact", contact)
	return {"success": True}


def _invite_authority(customer, project=None, user=None):
	if not frappe.db.get_value("User", user or frappe.session.user, "enabled"):
		frappe.throw("The inviter's account is unavailable", frappe.PermissionError)
	if project:
		from illumenate_lighting.illumenate_lighting.portal.access import can_manage_project_collaborators

		if not can_manage_project_collaborators(frappe.get_doc("ilL-Project", project), user):
			frappe.throw("Project invitation access denied", frappe.PermissionError)
	elif company(user) != customer:
		frappe.throw("Company invitation access denied", frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
@atomic_build
def invite(email, first_name, last_name="", project=None, access_level="VIEW"):
	_login()
	customer = None if project else company()
	_invite_authority(customer, project)
	if access_level not in ("VIEW", "EDIT"):
		raise ValueError("Choose VIEW or EDIT project access")
	email = str(email or "").strip().lower()
	if not frappe.utils.validate_email_address(email) or not str(first_name or "").strip():
		raise ValueError("Valid email and first name are required")
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		if user.user_type != "Website User" or not user.enabled:
			frappe.throw("This account needs staff assistance", frappe.PermissionError)
		member = get_actor(email)
		if not project and member.customer and member.customer != customer:
			frappe.throw("This account is already linked to another company", frappe.PermissionError)
	token = secrets.token_urlsafe(32)
	doc = frappe.get_doc(
		{
			"doctype": INVITE,
			"customer": customer,
			"project": project,
			"access_level": access_level,
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"invited_by": frappe.session.user,
			"token_hash": hashlib.sha256(token.encode()).hexdigest(),
			"state": "Pending",
			"expires_on": frappe.utils.add_days(frappe.utils.now_datetime(), 7),
		}
	)
	doc.flags.account_service = True
	doc.insert(ignore_permissions=True)
	# The recipient uses the site's existing signup/password flow, then accepts as this email.
	return {
		"success": True,
		"invitation": doc.name,
		"invite_url": "/portal/accept-invitation#" + token,
		"email": email,
		"expires_on": str(doc.expires_on),
	}


@frappe.whitelist(methods=["POST"])
@atomic_build
def accept_invitation(token):
	_login()
	digest = hashlib.sha256(str(token or "").encode()).hexdigest()
	name = frappe.db.get_value(INVITE, {"token_hash": digest}, "name")
	if not name:
		raise ValueError("Invitation is invalid or unavailable")
	frappe.db.sql("select name from `tabilL-Portal-Invitation` where name=%s for update", name)
	doc = frappe.get_doc(INVITE, name)
	user = frappe.get_doc("User", frappe.session.user)
	if user.name.lower() != doc.email or user.user_type != "Website User" or not user.enabled:
		frappe.throw("Sign in with the invited email's website account", frappe.PermissionError)
	if doc.state != "Pending" or frappe.utils.get_datetime(doc.expires_on) <= frappe.utils.now_datetime():
		raise ValueError("Invitation was used, revoked or expired")
	_invite_authority(doc.customer, doc.project, doc.invited_by)
	frappe.db.sql("select name from `tabUser` where name=%s for update", user.name)
	if doc.project:
		frappe.db.sql("select name from `tabilL-Project` where name=%s for update", doc.project)
		project = frappe.get_doc("ilL-Project", doc.project)
		row = next((row for row in project.get("collaborators") or [] if row.user == user.name), None)
		if row:
			row.access_level, row.is_active = doc.access_level, 1
		else:
			project.append(
				"collaborators", {"user": user.name, "access_level": doc.access_level, "is_active": 1}
			)
		project.save(ignore_permissions=True)
	else:
		member = get_actor(user.name)
		if member.customer and member.customer != doc.customer:
			frappe.throw("Company membership changed; ask staff to review it", frappe.PermissionError)
		_link_member(user, doc.customer)
	frappe.db.set_value(
		INVITE, name, {"state": "Accepted", "accepted_on": frappe.utils.now(), "accepted_by": user.name}
	)
	return {"success": True, "project": doc.project, "customer": doc.customer}


def _link_member(user, customer):
	"""Reuse an existing identity contact; do not depend on arbitrary first-contact ordering."""
	names = frappe.get_all("Contact", or_filters={"user": user.name, "email_id": user.email}, pluck="name")
	contacts = [frappe.get_doc("Contact", name) for name in names]
	for contact in contacts:
		if contact.get("user") and contact.user != user.name:
			raise ValueError("Email is associated with another User; staff reconciliation is required")
		if any(
			row.link_doctype == "Customer" and row.link_name != customer for row in contact.get("links") or []
		):
			raise ValueError("A Contact is already linked to another company")
	contact = next((row for row in contacts if linked_to(row, customer)), contacts[0] if contacts else None)
	if contact:
		if contact.get("ill_portal_archived"):
			raise ValueError("Staff must review the archived identity contact")
		contact.user = user.name
		contact.ill_portal_contact_only = 0
		if not linked_to(contact, customer):
			contact.append("links", {"link_doctype": "Customer", "link_name": customer})
		contact.save(ignore_permissions=True)
	else:
		contact = frappe.new_doc("Contact")
		contact.update({"first_name": user.first_name, "last_name": user.last_name, "user": user.name})
		contact.append("email_ids", {"email_id": user.email, "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": customer})
		contact.insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def revoke_invitation(name):
	doc = frappe.get_doc(INVITE, name)
	_invite_authority(doc.customer, doc.project)
	frappe.db.sql("select name from `tabilL-Portal-Invitation` where name=%s for update", name)
	doc.reload()
	if doc.state != "Pending":
		raise ValueError("Only pending invitations can be revoked")
	frappe.db.set_value(INVITE, name, "state", "Revoked")
	return {"success": True}


@frappe.whitelist(methods=["POST"])
@atomic_build
def disable_member(user):
	customer = company()
	if user == frappe.session.user:
		raise ValueError("Use the account closure request for your own account")
	frappe.db.sql("select name from `tabUser` where name=%s for update", user)
	doc = frappe.get_doc("User", user)
	member = get_actor(user)
	if doc.user_type != "Website User" or member.is_dealer or member.customer != customer:
		frappe.throw("Staff must review this account's access", frappe.PermissionError)
	if not frappe.db.exists(
		INVITE, {"email": user, "customer": customer, "state": "Accepted", "project": ["is", "not set"]}
	):
		frappe.throw(
			"Only a member admitted through this company's invitation can be disabled here",
			frappe.PermissionError,
		)
	doc.enabled = 0
	doc.save(ignore_permissions=True)
	return {"success": True}


@frappe.whitelist(methods=["POST"])
@atomic_build
def review(name, decision, note, expected_modified, approved_customer=None):
	if not (allowed("sales") or allowed("support")):
		frappe.throw("Account review requires authorized staff", frappe.PermissionError)
	frappe.db.sql("select name from `tabilL-Account-Request` where name=%s for update", name)
	doc = frappe.get_doc(INTAKE, name)
	if doc.state not in ("Pending", "Information needed") or str(doc.modified) != str(expected_modified):
		raise ValueError("The account request changed. Reload it before review.")
	if (
		decision not in ("Approve", "Reject", "Request information", "Resolve profile request")
		or not str(note or "").strip()
	):
		raise ValueError("Choose a decision and explain the outcome")
	if decision == "Resolve profile request" and doc.request_type != "Profile change":
		raise ValueError("Account grants and linkage require the approval action")
	if decision == "Approve":
		_apply_request(doc, approved_customer)
	doc.state = {
		"Approve": "Approved",
		"Reject": "Rejected",
		"Request information": "Information needed",
		"Resolve profile request": "Resolved",
	}[decision]
	doc.staff_note, doc.reviewed_by, doc.reviewed_on = (
		str(note).strip(),
		frappe.session.user,
		frappe.utils.now(),
	)
	doc.flags.account_service = True
	doc.save(ignore_permissions=True)
	return {"success": True, "state": doc.state}


def _apply_request(request, approved_customer):
	data = json.loads(request.proposed_json)
	if request.request_type in ("Address change", "Contact change"):
		doctype = "Address" if request.request_type == "Address change" else "Contact"
		frappe.db.sql(f"select name from `tab{doctype}` where name=%s for update", request.reference_name)
		doc = require_owned(frappe.get_doc(doctype, request.reference_name), request.customer, exclusive=True)
		if str(doc.modified) != request.expected_modified:
			raise ValueError("The source changed after this request. Obtain a new request.")
		if data.get("archive"):
			if doctype == "Contact" and doc.user:
				raise ValueError(
					"Disable or transfer the linked account before archiving its identity contact"
				)
			doc.set("disabled" if doctype == "Address" else "ill_portal_archived", 1)
		elif doctype == "Contact":
			if doc.user and "email_id" in data and data["email_id"] != doc.email_id:
				raise ValueError("Change the User identity through the native account administration flow")
			_apply_contact(doc, _clean(doctype, data))
		else:
			doc.update(_clean(doctype, data))
		doc.save(ignore_permissions=True)
		return
	if request.request_type == "Profile change":
		raise ValueError(
			"Apply and verify the requested company/profile changes in the native records, then record the outcome as a resolved request"
		)
	if not allowed("sales") or not frappe.has_permission("User", "write", doc=request.requested_by):
		frappe.throw(
			"Account linkage, dealer grants and closure require native User administration permission",
			frappe.PermissionError,
		)
	user = frappe.get_doc("User", request.requested_by)
	if user.user_type != "Website User":
		raise ValueError("Portal intake cannot alter a staff account")
	if request.request_type == "Account closure":
		user.enabled = 0
		user.save(ignore_permissions=True)
		return
	if not approved_customer or not frappe.has_permission("Customer", "read", doc=approved_customer):
		raise ValueError("Select and verify the approved Customer in ERP")
	member = get_actor(user.name)
	if member.customer and member.customer != approved_customer:
		raise ValueError("Existing company linkage must be reconciled in native Contact records first")
	_link_member(user, approved_customer)
	if request.request_type == "Dealer application":
		if "Dealer" not in frappe.get_roles(user.name):
			user.append("roles", {"role": "Dealer"})
		user.save(ignore_permissions=True)
	request.customer = approved_customer


@frappe.whitelist(methods=["POST"])
@atomic_build
def reply(name, message):
	_login()
	frappe.db.sql("select name from `tabilL-Account-Request` where name=%s for update", name)
	doc = frappe.get_doc(INTAKE, name)
	if doc.requested_by != frappe.session.user or doc.state != "Information needed":
		frappe.throw("This account request is not awaiting your reply", frappe.PermissionError)
	if not str(message or "").strip() or len(message) > 8000:
		raise ValueError("Provide the requested information in up to 8000 characters")
	responses = json.loads(doc.responses_json or "[]")
	responses.append(
		{"actor": frappe.session.user, "message": message.strip(), "recorded_on": frappe.utils.now()}
	)
	doc.responses_json, doc.state = canonical_json(responses), "Pending"
	doc.flags.account_service = True
	doc.save(ignore_permissions=True)
	return {"success": True, "state": doc.state}


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	return ptype in ("read", "select", "report") and (
		allowed("sales", user) or allowed("support", user) or doc.requested_by == user
	)


def query_conditions(user=None):
	user = user or frappe.session.user
	if allowed("sales", user) or allowed("support", user):
		return ""
	return "`tabilL-Account-Request`.requested_by=" + frappe.db.escape(user)
