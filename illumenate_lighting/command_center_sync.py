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
    * Creates the Command Center roles if missing. People are given a role only at the moment
      the role is first created; after that the desk (User -> Roles) is the only authority,
      so removing someone in the desk is never undone by a later deploy.
    * Never raises: any problem is written to the Error Log and the migrate carries on.
"""

import os

import frappe

WEB_PAGE = "illumenate-command-center"
SERVER_SCRIPT = "ilL Command Center Gateway"
API_METHOD = "ill_cc_gateway"

# role -> people to seed when the role is first created (matched by the part before "@")
ROLES = {
	"Command Center Viewer": [],
	"Command Center Editor": ["kevins", "jay", "ryanb", "reigine"],
	"Command Center Finance": ["charlotte", "jay", "kevins"],
}

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "command_center")


def _read(*parts):
	with open(os.path.join(SRC, *parts), encoding="utf-8") as f:
		return f.read().replace("\r\n", "\n")


def sync():
	"""after_migrate hook."""
	for step in (_sync_roles, _sync_server_script, _sync_web_page):
		# Every after_migrate hook shares one transaction, so on failure undo only this step,
		# not uncommitted work from the hooks that ran before it.
		frappe.db.savepoint("command_center_sync")
		try:
			step()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback(save_point="command_center_sync")
			frappe.log_error(title=f"Command Center sync failed: {step.__name__}")


def _find_user(prefix):
	return frappe.db.get_value("User", {"name": ["like", prefix + "@%"], "enabled": 1}, "name")


def _sync_roles():
	for role, people in ROLES.items():
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)
		for prefix in people:
			user = _find_user(prefix)
			if user:
				frappe.get_doc("User", user).add_roles(role)


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
			return
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
	else:
		doc.save(ignore_permissions=True)


def _backup(ext, content):
	if not (content or "").strip():
		return
	frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"cc.backup-{frappe.utils.now_datetime().strftime('%Y%m%d-%H%M%S')}.{ext}",
			"attached_to_doctype": "Web Page",
			"attached_to_name": WEB_PAGE,
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)


def _sync_web_page():
	if not frappe.db.exists("Web Page", WEB_PAGE):
		# the page (and its HTML) is set up by hand once; nothing to update until it exists
		return
	js, css = _read("page", "cc.js"), _read("page", "cc.css")
	doc = frappe.get_doc("Web Page", WEB_PAGE)
	changed = False
	if (doc.javascript or "").replace("\r\n", "\n") != js:
		_backup("js", doc.javascript)
		doc.javascript = js
		changed = True
	if (doc.css or "").replace("\r\n", "\n") != css:
		_backup("css", doc.css)
		doc.css = css
		changed = True
	if changed:
		doc.save(ignore_permissions=True)
		from frappe.website.utils import clear_cache

		clear_cache()
