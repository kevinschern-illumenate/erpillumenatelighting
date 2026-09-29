"""Seed and verify the CI upgrade rehearsal site the way production looks.

Run from the bench's sites directory with the bench Python:
	../env/bin/python upgrade_rehearsal.py seed|verify SITE

``seed`` runs on the previously deployed app revision, ``verify`` after the new
revision has migrated. A fresh install marks every patch as complete without
running it, so only this path executes new patches and migration hooks against
an existing site.
"""

import json
import sys
from pathlib import Path

import frappe

WORKSPACE = "ilLumenate Lighting"
BLOCK = {"id": "ill-rehearsal-block", "type": "paragraph", "data": {"text": "Site customization", "col": 12}}


def seed():
	# Production installed this app before ERPNext, so its patches and
	# after_migrate hook run before ERPNext's, HRMS's and CRM's.
	apps = frappe.get_installed_apps()
	order = ["frappe", "illumenate_lighting"] + [
		app for app in apps if app not in ("frappe", "illumenate_lighting")
	]
	frappe.db.set_global("installed_apps", json.dumps(order))

	# A site customization of the shipped workspace that must survive the upgrade.
	workspace = frappe.get_doc("Workspace", WORKSPACE)
	workspace.content = json.dumps([*json.loads(workspace.content or "[]"), BLOCK])
	workspace.save(ignore_permissions=True)

	# Revisions up to 786a521 left a pending snapshot under private/backups, where
	# it breaks every Frappe backup until a migration relocates it.
	legacy = Path(frappe.get_site_path("private", "backups", "ill-workspace"))
	legacy.mkdir(parents=True, exist_ok=True)
	(legacy / "snapshot.json").write_text(frappe.as_json(workspace.as_dict()), encoding="utf-8")
	(legacy / "pending.json").write_text(json.dumps({"backup": "snapshot.json"}), encoding="utf-8")


def verify():
	backups = Path(frappe.get_site_path("private", "backups"))
	stray = [path.name for path in backups.iterdir() if not path.is_file()] if backups.exists() else []
	assert not stray, f"Directories in private/backups break Frappe backups: {stray}"

	state = Path(frappe.get_site_path("private", "ill-workspace"))
	assert not (state / "pending.json").exists(), "The workspace merge did not complete"
	assert (state / "last-merge.json").is_file(), "The workspace merge left no receipt"

	content = json.loads(frappe.db.get_value("Workspace", WORKSPACE, "content") or "[]")
	assert any(block.get("id") == BLOCK["id"] for block in content), (
		"The site workspace customization was lost"
	)

	errors = frappe.get_all("Error Log", filters={"method": ["like", "ilL workspace%"]}, pluck="method")
	assert not errors, f"Workspace preservation logged errors: {errors}"
	print("Upgrade rehearsal verified: backups directory clean, workspace customization kept")


if __name__ == "__main__":
	action, site = sys.argv[1], sys.argv[2]
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	try:
		{"seed": seed, "verify": verify}[action]()
		frappe.db.commit()
	finally:
		frappe.destroy()
