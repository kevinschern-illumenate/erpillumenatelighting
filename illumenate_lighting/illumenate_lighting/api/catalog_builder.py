"""Catalog Builder data, served only to authorized catalog staff."""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.catalog_authoring.reference import (
	SHORT_TYPES,
	SKIPPED_TYPES,
	SUMMARY_ONLY,
	TABLES,
	reference_record,
)
from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import cached_schema
from illumenate_lighting.illumenate_lighting.portal.staff import require

CACHE_KEY = "ill_catalog_builder_reference"
CACHE_SECONDS = 300
NOT_LISTED = {"Item Price"}
# Fetch long text, files and child rows only when a user copies a full record.
LIST_SKIPPED_TYPES = (
	SKIPPED_TYPES
	| TABLES
	| {
		"Text Editor",
		"Long Text",
		"Text",
		"Small Text",
		"HTML Editor",
		"Markdown Editor",
		"Code",
		"JSON",
		"Attach",
		"Attach Image",
	}
)


@frappe.whitelist(methods=["GET"])
def reference(refresh=0):
	require("catalog")
	if not frappe.utils.cint(refresh):
		cached = frappe.cache().get_value(CACHE_KEY, user=frappe.session.user)
		if cached is not None:
			return cached
	data = live_reference()
	frappe.cache().set_value(CACHE_KEY, data, user=frappe.session.user, expires_in_sec=CACHE_SECONDS)
	return data


def live_reference():
	"""List readable catalog records using both row and field permissions."""
	now = frappe.utils.now_datetime().isoformat(timespec="seconds")
	doctypes, skipped = {}, []
	for doctype, meta in cached_schema()["doctypes"].items():
		if meta.get("istable") or doctype in NOT_LISTED:
			continue
		if not frappe.db.exists("DocType", doctype) or not frappe.has_permission(doctype, "read"):
			skipped.append(doctype)
			continue
		live = frappe.get_meta(doctype)
		permitted = set(live.get_permitted_fieldnames(user=frappe.session.user))
		fields = [
			field["fieldname"]
			for field in meta["fields"]
			if field["fieldtype"] not in LIST_SKIPPED_TYPES
			and (doctype not in SUMMARY_ONLY or field["fieldtype"] in SHORT_TYPES)
			and live.has_field(field["fieldname"])
			and (frappe.session.user == "Administrator" or field["fieldname"] in permitted)
		]
		# get_all bypasses permissions, including User Permissions on linked records.
		rows = frappe.get_list(doctype, fields=["name", *fields], limit_page_length=0, order_by="name asc")
		doctypes[doctype] = {
			"source": "live",
			"exported_on": now,
			"records": {
				row["name"]: {
					key: value for key, value in row.items() if key != "name" and value not in (None, "", 0)
				}
				for row in rows
			},
		}
	return {
		"schema_version": 1,
		"exported_on": now,
		"source": "live",
		"doctypes": doctypes,
		"skipped": skipped,
	}


@frappe.whitelist(methods=["GET"])
def record(doctype, name):
	require("catalog")
	schema = cached_schema()
	meta = schema["doctypes"].get(doctype)
	if not meta or meta.get("istable") or doctype in NOT_LISTED:
		frappe.throw(_("Choose a catalog DocType"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	doc.apply_fieldlevel_read_permissions()
	return reference_record(doctype, doc.as_dict(), schema)
