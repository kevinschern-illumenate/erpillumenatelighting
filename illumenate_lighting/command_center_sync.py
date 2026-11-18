"""Push the Command Center page and gateway into the site on every migrate.

The Command Center is a Web Page (``illumenate-command-center``) plus a Server Script
(``ilL Command Center Gateway``). Both live in the database, so a normal app deploy never
touched them. This hook copies the source files kept in the app into those records after
``bench migrate`` (which Frappe Cloud runs on every deploy), so merging to GitHub is enough.

Source files (edit these, not the records in the desk):
    illumenate_lighting/command_center/page/cc.js     -> Web Page JavaScript
    illumenate_lighting/command_center/page/cc.css    -> Web Page CSS
    illumenate_lighting/command_center/ss/cc_gateway.py -> Server Script (API ill_cc_gateway)

Behaviour
    * Only writes when the content actually changed.
    * Before overwriting the page's JS/CSS it attaches the previous version to the Web Page
      as a private file (cc.backup-<timestamp>.js/.css), so a bad deploy can be undone by hand.
      The backup is best-effort (System Settings may not allow .js/.css uploads): if it fails
      the page is still updated, and Web Page's Version history keeps the old values anyway.
    * Finds the page by name, or by its route (/command-center) if it was renamed.
    * Gives the Command Center roles access to the meeting agenda doctypes (ilL-Meeting-Agenda,
      ilL-Meeting-Agenda-Item): Viewer reads, Editor reads and writes. Like the roles, a grant is
      only added when that role has no rule on the doctype yet, so desk changes are kept.
    * Creates the Command Center roles if missing. People are given a role only at the moment
      the role is first created; after that the desk (User -> Roles) is the only authority,
      so removing someone in the desk is never undone by a later deploy.
    * Never raises: any problem is written to the Error Log and the migrate carries on.
    * Prints one "Command Center sync: ..." line per step, so the deploy log shows the outcome.
"""

import os

import frappe

WEB_PAGE = "illumenate-command-center"
WEB_PAGE_ROUTE = "command-center"
SERVER_SCRIPT = "ilL Command Center Gateway"
API_METHOD = "ill_cc_gateway"

# role -> people to seed when the role is first created (matched by the part before "@")
ROLES = {
	"Command Center Viewer": [],
	"Command Center Editor": ["kevins", "jay", "ryanb", "reigine"],
	"Command Center Finance": ["charlotte", "jay", "kevins"],
}

# meeting agenda doctypes (this app) -> role -> permissions; System Manager comes from the doctype JSON
AGENDA_DOCTYPES = ("ilL-Meeting-Agenda", "ilL-Meeting-Agenda-Item")
AGENDA_PERMS = {
	"Command Center Viewer": {"read", "select", "report", "print"},
	"Command Center Editor": {"read", "select", "report", "print", "write", "create", "delete"},
}
PTYPES = ("read", "select", "write", "create", "delete", "report", "print", "export", "share", "email")

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "command_center")


def _read(*parts):
	with open(os.path.join(SRC, *parts), encoding="utf-8") as f:
		return f.read().replace("\r\n", "\n")


def sync():
	"""after_migrate hook."""
	for step in (_sync_roles, _sync_agenda_permissions, _sync_server_script, _sync_web_page):
		# Every after_migrate hook shares one transaction, so on failure undo only this step,
		# not uncommitted work from the hooks that ran before it.
		frappe.db.savepoint("command_center_sync")
		try:
			result = step()
			frappe.db.commit()
			print(f"Command Center sync: {result}")
		except Exception as e:
			frappe.db.rollback(save_point="command_center_sync")
			frappe.log_error(title=f"Command Center sync failed: {step.__name__}")
			print(f"Command Center sync: {step.__name__} FAILED ({e!r}); see Error Log")


def _find_user(prefix):
	return frappe.db.get_value("User", {"name": ["like", prefix + "@%"], "enabled": 1}, "name")


def _sync_roles():
	created = []
	for role, people in ROLES.items():
		if frappe.db.exists("Role", role):
			continue
		created.append(role)
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)
		for prefix in people:
			user = _find_user(prefix)
			if user:
				frappe.get_doc("User", user).add_roles(role)
	return "roles created: " + ", ".join(created) if created else "roles unchanged"


def _sync_agenda_permissions():
	from frappe.permissions import add_permission, update_permission_property

	added = []
	for doctype in AGENDA_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for role, perms in AGENDA_PERMS.items():
			if not frappe.db.exists("Role", role):
				continue
			if frappe.db.exists(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			):
				continue
			add_permission(doctype, role, 0)
			for ptype in PTYPES:
				update_permission_property(doctype, role, 0, ptype, int(ptype in perms), validate=False)
			added.append(f"{role} on {doctype}")
	if not added:
		return "agenda permissions unchanged"
	frappe.clear_cache()
	return "agenda permissions added: " + "; ".join(added)


def _sync_server_script():
	script = _read("ss", "cc_gateway.py")
	if frappe.db.exists("Server Script", SERVER_SCRIPT):
		doc = frappe.get_doc("Server Script", SERVER_SCRIPT)
		if (
			(doc.script or "").replace("\r\n", "\n") == script
			and doc.script_type == "API"
			and doc.api_method == API_METHOD
			and not doc.allow_guest
			and not doc.disabled
		):
			return f"Server Script {SERVER_SCRIPT!r} unchanged"
	else:
		doc = frappe.new_doc("Server Script")
		doc.name = SERVER_SCRIPT  # Server Script names are "set by user" (Prompt)
	doc.script_type = "API"
	doc.api_method = API_METHOD
	doc.allow_guest = 0
	doc.disabled = 0
	doc.script = script
	if doc.is_new():
		doc.insert(ignore_permissions=True)
		return f"Server Script {SERVER_SCRIPT!r} created"
	doc.save(ignore_permissions=True)
	return f"Server Script {SERVER_SCRIPT!r} updated"


def _backup(page, ext, content):
	"""Attach the old JS/CSS to the page. Best-effort: never blocks the update."""
	if not (content or "").strip():
		return
	frappe.db.savepoint("command_center_backup")
	try:
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"cc.backup-{frappe.utils.now_datetime().strftime('%Y%m%d-%H%M%S')}.{ext}",
				"attached_to_doctype": "Web Page",
				"attached_to_name": page,
				"is_private": 1,
				"content": content,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.db.rollback(save_point="command_center_backup")
		frappe.log_error(title=f"Command Center sync: {ext} backup skipped (Version history still has it)")


def _find_web_page():
	if frappe.db.exists("Web Page", WEB_PAGE):
		return WEB_PAGE
	return frappe.db.get_value("Web Page", {"route": WEB_PAGE_ROUTE}, "name")


def _sync_web_page():
	name = _find_web_page()
	if not name:
		# the page (and its HTML) is set up by hand once; nothing to update until it exists
		frappe.log_error(
			title="Command Center sync: Web Page not found",
			message=f"No Web Page named {WEB_PAGE!r} or with route {WEB_PAGE_ROUTE!r}; page not updated.",
		)
		return f"Web Page not found (name {WEB_PAGE!r} / route {WEB_PAGE_ROUTE!r}); skipped"
	js, css = _read("page", "cc.js"), _read("page", "cc.css")
	doc = frappe.get_doc("Web Page", name)
	changed = []
	if (doc.javascript or "").replace("\r\n", "\n") != js:
		_backup(name, "js", doc.javascript)
		doc.javascript = js
		changed.append("javascript")
	if (doc.css or "").replace("\r\n", "\n") != css:
		_backup(name, "css", doc.css)
		doc.css = css
		changed.append("css")
	if not doc.insert_style:
		# Frappe only renders the css field when Insert Style is ticked
		doc.insert_style = 1
		changed.append("insert_style")
	if not changed:
		return f"Web Page {name!r} unchanged (route /{doc.route})"
	doc.save(ignore_permissions=True)
	from frappe.website.utils import clear_cache

	clear_cache()
	return f"Web Page {name!r} updated: {', '.join(changed)} (route /{doc.route})"
