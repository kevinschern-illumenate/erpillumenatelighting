"""Private, read-only migration evidence for fresh and upgraded Cloud sites.

Invoke with bench execute; these functions are deliberately not HTTP endpoints.
"""

import importlib
import json
import re
import subprocess
from pathlib import Path

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

HEADERS = {
	"Sales Order": ("docstatus", "customer", "company", "currency", "grand_total", "terms", "amended_from"),
	"Quotation": (
		"docstatus",
		"quotation_to",
		"party_name",
		"currency",
		"grand_total",
		"terms",
		"valid_till",
	),
	"BOM": ("docstatus", "item", "quantity", "is_active", "is_default", "with_operations"),
	"ilL-Configured-Fixture": ("config_hash", "configured_item", "bom", "build_snapshot_json"),
	"ilL-Configured-Tape-Neon": ("config_hash", "configured_item", "bom", "build_snapshot_json"),
	"ilL-Configured-LED-Sheet": ("config_hash", "configured_item", "bom", "build_snapshot_json"),
	"ilL-Configured-Group": ("config_hash", "configured_item", "bom", "build_snapshot_json"),
	"ilL-Quote-Offer": ("state", "snapshot_hash", "snapshot_json", "pdf_sha256", "quotation", "sales_order"),
	"ilL-Order-Intake": (
		"state",
		"request_hash",
		"approved_snapshot",
		"acknowledgment_sha256",
		"sales_order",
	),
}
LINE_FIELDS = (
	"name",
	"idx",
	"item_code",
	"qty",
	"uom",
	"stock_uom",
	"stock_qty",
	"conversion_factor",
	"rate",
	"amount",
	"description",
	"ill_fixture_schedule",
	"ill_schedule_line_id",
	"ill_fixture_type",
	"ill_section_label",
	"additional_notes",
	"ill_configurator_request",
	"ill_bom",
	"ill_configured_fixture",
	"ill_configured_tape_neon",
	"ill_configured_led_sheet",
	"ill_configured_group",
	"ill_configuration_json",
)


def document_digest(doc):
	data = {key: doc.get(key) for key in HEADERS[doc.doctype]}
	if doc.doctype in ("Sales Order", "Quotation", "BOM"):
		data["items"] = [{key: row.get(key) for key in LINE_FIELDS} for row in doc.get("items") or []]
	if doc.doctype == "BOM":
		data["operations"] = [
			{key: row.get(key) for key in ("operation", "workstation", "time_in_mins", "hour_rate")}
			for row in doc.get("operations") or []
		]
	return fingerprint(json.loads(frappe.as_json(data)))


def compare(before, after):
	"""New rows are reported separately; historical mutation is never hidden."""
	changes, missing, added = [], [], []
	for doctype in sorted(set(before["records"]) | set(after["records"])):
		old, new = before["records"].get(doctype, {}), after["records"].get(doctype, {})
		changes.extend(
			{"doctype": doctype, "name": name} for name in old.keys() & new.keys() if old[name] != new[name]
		)
		missing.extend({"doctype": doctype, "name": name} for name in old.keys() - new.keys())
		added.extend({"doctype": doctype, "name": name} for name in new.keys() - old.keys())
	return {
		"historical_records_unchanged": not changes and not missing,
		"changed": changes,
		"missing": missing,
		"added": added,
	}


def collect():
	frappe.only_for("System Manager")
	records = {}
	for doctype in HEADERS:
		if not frappe.db.exists("DocType", doctype):
			continue
		records[doctype] = {}
		cursor = ""
		while True:
			filters = {"name": [">", cursor]}
			if doctype in ("Sales Order", "Quotation", "BOM"):
				filters["docstatus"] = ["in", [1, 2]]
			names = frappe.get_all(
				doctype, filters=filters, pluck="name", order_by="name asc", limit_page_length=250
			)
			for name in names:
				records[doctype][name] = document_digest(frappe.get_doc(doctype, name))
			if len(names) < 250:
				break
			cursor = names[-1]
	versions, commits = {}, {}
	for app in frappe.get_installed_apps():
		module = importlib.import_module(app)
		versions[app] = getattr(module, "__version__", "unavailable")
		try:
			commits[app] = subprocess.check_output(
				["git", "rev-parse", "HEAD"],
				cwd=Path(module.__file__).resolve().parent,
				text=True,
				stderr=subprocess.DEVNULL,
				timeout=10,
			).strip()
		except (OSError, subprocess.SubprocessError):
			commits[app] = "unavailable"
	assets = Path(frappe.get_site_path("..", "assets", "assets.json"))
	return {
		"schema_version": 1,
		"site": frappe.local.site,
		"captured_on": str(frappe.utils.now()),
		"app_versions": versions,
		"app_commits": commits,
		"active_hooks_hash": fingerprint(json.loads(frappe.as_json(frappe.get_hooks()))),
		"asset_manifest_hash": fingerprint(json.loads(assets.read_text(encoding="utf-8")))
		if assets.is_file()
		else None,
		"records": records,
		"group_rollout_enabled": bool(frappe.conf.get("ill_portal_fixture_groups")),
		"enabled_families": frappe.conf.get("ill_portal_enabled_families"),
		"pilot_users": frappe.conf.get("ill_portal_pilot_users"),
		"role_permissions": frappe.get_all(
			"Custom DocPerm",
			fields=["parent", "role", "read", "write", "create", "submit", "cancel", "amend", "delete"],
		),
		"custom_fields": frappe.get_all(
			"Custom Field",
			filters={"fieldname": ["like", "ill_%"]},
			fields=["dt", "fieldname", "fieldtype", "options", "read_only", "allow_on_submit"],
		),
	}


def capture(label):
	frappe.only_for("System Manager")
	if not isinstance(label, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", label):
		raise ValueError("Use a short checkpoint label containing letters, digits, hyphens or underscores")
	directory = Path(frappe.get_site_path("private", "backups", "b2b-release"))
	directory.mkdir(parents=True, exist_ok=True)
	path = directory / (label + ".json")
	evidence = collect()
	with path.open("x", encoding="utf-8") as stream:
		json.dump(evidence, stream, default=str, sort_keys=True)
	return {
		"private_checkpoint": str(path),
		"records_only": "Hashes and record IDs; no password or financial payload copied",
	}


def compare_checkpoints(before_label, after_label):
	frappe.only_for("System Manager")
	if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", label) for label in (before_label, after_label)):
		raise ValueError("Invalid checkpoint label")
	directory = Path(frappe.get_site_path("private", "backups", "b2b-release"))
	return compare(
		*(
			json.loads((directory / (label + ".json")).read_text(encoding="utf-8"))
			for label in (before_label, after_label)
		)
	)
