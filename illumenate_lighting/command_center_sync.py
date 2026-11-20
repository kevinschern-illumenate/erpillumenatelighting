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
    * Gives the Command Center roles access to the app doctypes in GRANTS (meeting agenda, inbound
      shipments, purchasing settings): Viewer reads, Editor reads and writes. Like the roles, a grant is
      only added when that role has no rule on the doctype yet, so desk changes are kept.
    * Creates the Command Center roles if missing. People are given a role only at the moment
      the role is first created; after that the desk (User -> Roles) is the only authority,
      so removing someone in the desk is never undone by a later deploy.
    * Keeps the page out of search engines without changing who can open it: a Website Route
      Meta for the route carries <meta name="robots" content="noindex, nofollow">, and Website
      Settings > Robots Txt disallows the route, which is also what drops it from /sitemap.xml.
      Both are separate steps, so a problem there never blocks the JS/CSS update.
    * Never raises: any problem is written to the Error Log and the migrate carries on.
    * Prints one "Command Center sync: ..." line per step, so the deploy log shows the outcome.
"""

import os

import frappe

WEB_PAGE = "illumenate-command-center"
WEB_PAGE_ROUTE = "command-center"
SERVER_SCRIPT = "ilL Command Center Gateway"
API_METHOD = "ill_cc_gateway"
# the page is for signed-in staff: keep it out of search engines (see _sync_noindex_meta)
ROBOTS_META = "noindex, nofollow"

# role -> people to seed when the role is first created (matched by the part before "@")
ROLES = {
	"Command Center Viewer": [],
	"Command Center Editor": ["kevins", "jay", "ryanb", "reigine"],
	"Command Center Finance": ["charlotte", "jay", "kevins"],
}

# App doctypes the Command Center roles need -> role -> permissions. The doctype JSON carries the
# ERPNext roles (System Manager, Purchase Manager, ...); these are the Command Center grants on top.
VIEW_PERMS = {"read", "select", "report", "print"}
GRANTS = {
	# weekly meeting agenda (v6)
	"ilL-Meeting-Agenda": {
		"Command Center Viewer": VIEW_PERMS,
		"Command Center Editor": VIEW_PERMS | {"write", "create", "delete"},
	},
	"ilL-Meeting-Agenda-Item": {
		"Command Center Viewer": VIEW_PERMS,
		"Command Center Editor": VIEW_PERMS | {"write", "create", "delete"},
	},
	# purchasing (v8): inbound shipments are edited from the Purchasing page; settings are read-only here
	"ilL-Inbound-Shipment": {
		"Command Center Viewer": VIEW_PERMS,
		"Command Center Editor": VIEW_PERMS | {"write", "create"},
	},
	"ilL-Purchasing-Settings": {"Command Center Viewer": {"read", "print"}},
}
# kept for anything that imported the v6 names
AGENDA_DOCTYPES = ("ilL-Meeting-Agenda", "ilL-Meeting-Agenda-Item")
AGENDA_PERMS = GRANTS["ilL-Meeting-Agenda"]
PTYPES = ("read", "select", "write", "create", "delete", "report", "print", "export", "share", "email")

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "command_center")


def _read(*parts):
	with open(os.path.join(SRC, *parts), encoding="utf-8") as f:
		return f.read().replace("\r\n", "\n")


def sync():
	"""after_migrate hook."""
	for step in (
		_sync_roles,
		_sync_permissions,
		_sync_server_script,
		_sync_web_page,
		_sync_noindex_meta,
		_sync_sitemap_exclusion,
	):
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


def _sync_permissions():
	"""Grant once per (doctype, role); after that the desk's Role Permissions Manager is the authority."""
	from frappe.permissions import add_permission, update_permission_property

	added = []
	for doctype, grants in GRANTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role, perms in grants.items():
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
		return "doctype permissions unchanged"
	frappe.clear_cache()
	return "doctype permissions added: " + "; ".join(added)


# the v6 name, kept so anything calling it directly still works
_sync_agenda_permissions = _sync_permissions


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


def _page_route():
	"""The Command Center's live route without slashes (follows a renamed route), or None."""
	name = _find_web_page()
	if not name:
		return None
	return (frappe.db.get_value("Web Page", name, "route") or "").strip("/") or None


def _sync_noindex_meta():
	"""Make the page render <meta name="robots" content="noindex, nofollow">.

	Web Page has no meta tag table of its own (only meta_title/description/image); its
	"Set Meta Tags" button opens a Website Route Meta named after the route, whose rows Frappe
	renders on that route. Only the robots row is managed here; other rows are left alone.
	"""
	route = _page_route()
	if not route:
		return "noindex meta skipped (Web Page not found)"
	if frappe.db.exists("Website Route Meta", route):
		doc = frappe.get_doc("Website Route Meta", route)
	else:
		doc = frappe.new_doc("Website Route Meta")
		doc.name = route  # "Prompt" naming: the name is the route
	rows = [t for t in doc.meta_tags if (t.key or "").strip().lower() == "robots"]
	if rows and all(t.key == "robots" and t.value == ROBOTS_META for t in rows):
		return f"noindex meta unchanged (/{route})"
	for t in rows:
		t.key, t.value = "robots", ROBOTS_META
	if not rows:
		doc.append("meta_tags", {"key": "robots", "value": ROBOTS_META})
	if doc.is_new():
		doc.insert(ignore_permissions=True)
		action = "added"
	else:
		doc.save(ignore_permissions=True)
		action = "updated"
	from frappe.website.utils import clear_cache

	clear_cache()
	return f"noindex meta {action} (Website Route Meta {route!r}: robots = {ROBOTS_META!r})"


def _robots_with_disallow(robots_txt, path):
	"""Return robots_txt with ``Disallow: <path>`` for every crawler, or None if it already is.

	Uses the same parser Frappe's sitemap uses (urllib.robotparser), which honours only the
	first ``User-agent: *`` group and stops at the first matching rule, so the line goes at the
	top of that group (ahead of any ``Allow: /``), or a new group is appended if there is none.
	"""
	from urllib import robotparser

	def blocked(text):
		rp = robotparser.RobotFileParser()
		rp.parse(text.splitlines())
		return not rp.can_fetch("*", path)

	if blocked(robots_txt):
		return None
	lines = robots_txt.rstrip().splitlines() if robots_txt.strip() else []
	rule = f"Disallow: {path}"

	def field(line):
		key, _, value = line.split("#", 1)[0].partition(":")
		return key.strip().lower(), value.strip()

	for i, line in enumerate(lines):
		if field(line) == ("user-agent", "*"):
			j = i + 1
			while j < len(lines) and field(lines[j])[0] == "user-agent":
				j += 1  # keep a multi-agent group together
			lines.insert(j, rule)
			break
	else:
		if lines:
			lines.append("")
		lines += ["User-agent: *", rule]
	text = "\n".join(lines) + "\n"
	if not blocked(text):
		raise ValueError(f"robots.txt still allows {path} after adding {rule!r}")
	return text


def _sync_sitemap_exclusion():
	"""Keep the page out of /sitemap.xml.

	Frappe v16 lists every published, guest-viewable Web Page in the sitemap; the only per-route
	opt-out (short of unpublishing, which would take the page down) is a robots.txt rule:
	frappe/www/sitemap.py skips routes that Website Settings > Robots Txt disallows for "*".
	Existing robots.txt content is kept; the rule is added only if the route is not blocked yet.
	"""
	route = _page_route()
	if not route:
		return "sitemap exclusion skipped (Web Page not found)"
	current = frappe.db.get_single_value("Website Settings", "robots_txt") or ""
	updated = _robots_with_disallow(current, f"/{route}")
	if updated is None:
		return f"sitemap exclusion unchanged (robots.txt already disallows /{route})"
	frappe.db.set_single_value("Website Settings", "robots_txt", updated)
	from frappe.website.utils import clear_cache

	clear_cache()  # also drops the cached sitemap route list (get_public_pages_from_doctypes)
	return f"sitemap exclusion added (robots.txt: Disallow: /{route})"
