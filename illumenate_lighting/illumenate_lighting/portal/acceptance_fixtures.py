"""Explicit, isolated-site fixtures for the Cloud actor/browser acceptance suite.

No HTTP endpoints, passwords in output, business-record deletion, or live emails.
"""

import io
import json
import os
import re
from pathlib import Path

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build

ACTORS = {
	"admin": ("System User", "System Manager", None),
	"dealer_a": ("Website User", "Dealer", "a"),
	"buyer_a": ("Website User", "Dealer", "a"),
	"dealer_b": ("Website User", "Dealer", "b"),
	"member_a": ("Website User", None, "a"),
	"viewer": ("Website User", None, None),
	"editor": ("Website User", None, None),
	"sales": ("System User", "ilL Sales Review", None),
	"approver": ("System User", "ilL Order Approver", None),
	"engineering": ("System User", "ilL Engineering", None),
	"catalog": ("System User", "ilL Catalog Publisher", None),
	"integration": ("System User", "ilL Integration", None),
	"operations": ("System User", "ilL Operations", None),
	"support": ("System User", "ilL Support", None),
}


def require_test_site():
	frappe.only_for("System Manager")
	if not frappe.conf.get("ill_portal_acceptance"):
		frappe.throw("Use an isolated test site with ill_portal_acceptance enabled")


@atomic_build
def seed(run_id):
	"""Passwords come only from B2B_E2E_<ACTOR>_PASSWORD process secrets."""
	require_test_site()
	if not re.fullmatch(r"[a-z0-9]{4,20}", str(run_id)):
		raise ValueError("Use a new 4-20 character lowercase alphanumeric run ID")
	prefix = "b2b-qa-" + run_id
	users = {actor: f"{prefix}-{actor}@example.invalid" for actor in ACTORS}
	if any(frappe.db.exists("User", email) for email in users.values()):
		raise ValueError("This run ID already exists. Retain its records and choose a new ID.")
	passwords = {actor: os.environ.get(f"B2B_E2E_{actor.upper()}_PASSWORD") for actor in ACTORS}
	if any(not value or len(value) < 16 for value in passwords.values()):
		raise ValueError(
			"Set a distinct strong password of at least 16 characters in every actor's process secret"
		)
	if len(set(passwords.values())) != len(passwords):
		raise ValueError("Use distinct actor passwords")
	customers = {}
	group = frappe.get_doc(
		{
			"doctype": "Customer Group",
			"customer_group_name": prefix,
			"parent_customer_group": "All Customer Groups",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	for company in ("a", "b"):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"{prefix}-{company}",
				"customer_type": "Company",
				"customer_group": group.name,
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)
		customers[company] = customer.name
	for actor, (user_type, role, company) in ACTORS.items():
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": users[actor],
				"first_name": f"QA {actor}",
				"enabled": 1,
				"user_type": user_type,
				"send_welcome_email": 0,
				"new_password": passwords[actor],
				"roles": [{"role": role}] if role else [],
			}
		).insert(ignore_permissions=True)
		if company:
			frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": f"QA {actor}",
					"user": user.name,
					"email_ids": [{"email_id": user.name, "is_primary": 1}],
					"links": [{"link_doctype": "Customer", "link_name": customers[company]}],
				}
			).insert(ignore_permissions=True)
	schedules, projects, files = {}, {}, {}
	from frappe.utils.file_manager import save_file
	from PIL import Image

	# Distinct synthetic bytes avoid a deduplicated path masking isolation.
	for company in ("a", "b"):
		stream = io.BytesIO()
		Image.new("RGB", (2, 2), "red" if company == "a" else "blue").save(stream, "PNG")
		project = frappe.get_doc(
			{
				"doctype": "ilL-Project",
				"project_name": f"{prefix}-{company}",
				"customer": customers[company],
				"owner_customer": customers[company],
				"is_private": 0,
				"owner": users["dealer_" + company],
				"collaborators": [
					{"user": users["viewer"], "access_level": "VIEW", "is_active": 1},
					{"user": users["editor"], "access_level": "EDIT", "is_active": 1},
				]
				if company == "a"
				else [],
			}
		).insert(ignore_permissions=True)
		schedule = frappe.get_doc(
			{
				"doctype": "ilL-Project-Fixture-Schedule",
				"schedule_name": f"{prefix}-{company}",
				"ill_project": project.name,
				"customer": customers[company],
				"owner": users["dealer_" + company],
				"status": "DRAFT",
				"inherits_project_privacy": 1,
				"lines": [
					{
						"line_id": "OTHER-1",
						"qty": 2,
						"manufacturer_type": "OTHER",
						"manufacturer_name": "QA Manufacturer",
						"fixture_model_number": "QA-1",
						"location": "Test room",
					}
				],
			}
		).insert(ignore_permissions=True)
		file = save_file(
			prefix + "-" + company + ".png", stream.getvalue(), schedule.doctype, schedule.name, is_private=1
		)
		projects[company], schedules[company], files[company] = project.name, schedule.name, file.file_url
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": prefix + "-" + company,
				"address_type": "Billing",
				"address_line1": "1 Test Way",
				"city": "Test City",
				"country": "United States",
				"pincode": "00000",
				"links": [{"link_doctype": "Customer", "link_name": customers[company]}],
			}
		).insert(ignore_permissions=True)
	manifest = {
		"schema_version": 1,
		"run_id": run_id,
		"site": frappe.local.site,
		"actors": users,
		"customers": customers,
		"projects": projects,
		"schedules": schedules,
		"private_files": files,
		"engineering_cases": [],
		"seeded_on": str(frappe.utils.now()),
	}
	directory = Path(frappe.get_site_path("private", "backups", "b2b-release"))
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / (prefix + "-fixtures.json")
	# Save only when the complete database transaction succeeds.
	frappe.db.after_commit.add(
		lambda: path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
	)
	return manifest
