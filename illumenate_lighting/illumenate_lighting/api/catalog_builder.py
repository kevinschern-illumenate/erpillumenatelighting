"""Catalog Builder data, served only to authorized catalog staff."""

import hashlib
import json
import time
from collections import defaultdict
from contextlib import suppress
from datetime import timedelta

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.catalog_authoring.catalog import (
	_record_errors,
	identity,
	links,
	prepare_catalog,
	with_defaults,
)
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


MAX_RECORDS = 500
CHECK_VALID_MINUTES = 30
SAVEPOINT = "ill_catalog_row"
LOCK = "ill_catalog_builder_import"
AUDIT = "ilL-Catalog-Import"


@frappe.whitelist(methods=["POST"])
def check(catalog=None):
	return _run(catalog, "Check")


@frappe.whitelist(methods=["POST"])
def import_catalog(catalog=None, expected_hash=None):
	return _run(catalog, "Import", expected_hash)


@frappe.whitelist(methods=["GET"])
def history(limit=20):
	require("catalog")
	limit = max(1, min(frappe.utils.cint(limit), 100))
	manager = frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()
	return frappe.get_all(
		AUDIT,
		filters={} if manager else {"user": frappe.session.user},
		limit_page_length=limit,
		order_by="creation desc",
		fields=[
			"name",
			"mode",
			"status",
			"series_name",
			"product_type",
			"record_count",
			"created_count",
			"error_count",
			"skipped_count",
			"warning_count",
			"creation",
		],
	)


def catalog_hash(catalog):
	text = json.dumps(catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run(catalog, mode, expected_hash=None):
	# Authorization is the only intentional raised error. All runs after it return receipts.
	require("catalog")
	started = time.monotonic()
	log = {"mode": mode, "user": frappe.session.user, "catalog_json": catalog, "record_count": 0}
	try:
		try:
			if isinstance(catalog, str):
				try:
					catalog = json.loads(catalog)
				except ValueError:
					response = _response(log, "Refused", "shape", errors=["Catalog must be valid JSON"])
				else:
					log["catalog_json"] = catalog
					response = _guarded(catalog, mode, expected_hash, log)
			else:
				response = _guarded(catalog, mode, expected_hash, log)
		except Exception:
			frappe.db.rollback()
			log["error_detail"] = frappe.get_traceback()
			response = _response(
				log,
				"Error",
				log.get("stage", "shape"),
				errors=["Unexpected server error. The run was rolled back; see the audit log."],
			)
		finally:
			frappe.local.message_log = []

		response["summary"]["duration_ms"] = int((time.monotonic() - started) * 1000)
		try:
			response["log"] = _write_log(log, response)
		except Exception:
			# Import is already committed. Never tell the caller to retry an imported catalog
			# merely because persisting its receipt failed. Other outcomes cannot authorize Import.
			with suppress(Exception):
				frappe.db.rollback()
			if response["status"] != "Imported":
				response.update(ok=False, status="Error")
			response["errors"].append(
				"The audit log could not be saved. "
				+ (
					"The catalog records were imported."
					if response["status"] == "Imported"
					else "Run Check again before importing."
				)
			)
			response["summary"]["errors"] += 1
		return response
	finally:
		# Hold the site lock through the durable audit receipt. Failed acquisition never releases it.
		if log.get("locked"):
			with suppress(Exception):
				frappe.db.sql("select release_lock(%s)", _lock_name())


def _guarded(catalog, mode, expected_hash, log):
	log["stage"] = "shape"
	if not isinstance(catalog, dict) or not isinstance(catalog.get("records"), dict):
		return _response(
			log, "Refused", "shape", errors=["records must map DocType names to lists of records"]
		)
	if any(not isinstance(rows, list) for rows in catalog["records"].values()):
		return _response(
			log, "Refused", "shape", errors=["records must map DocType names to lists of records"]
		)
	log["record_count"] = sum(len(rows) for rows in catalog["records"].values())
	if log["record_count"] > MAX_RECORDS:
		return _response(
			log,
			"Refused",
			"shape",
			errors=[f"Split the catalog: {log['record_count']} records, limit {MAX_RECORDS}"],
		)
	if not isinstance(catalog.get("product_type", ""), str) or not isinstance(
		catalog.get("series_name", ""), str
	):
		return _response(log, "Refused", "shape", errors=["product_type and series_name must be text"])
	log.update(
		catalog_hash=catalog_hash(catalog),
		product_type=catalog.get("product_type"),
		series_name=catalog.get("series_name"),
	)
	if mode == "Import":
		log["stage"] = "gate"
		passing = []
		if expected_hash == log["catalog_hash"]:
			passing = frappe.get_all(
				AUDIT,
				filters={
					"mode": "Check",
					"status": "Passed",
					"user": frappe.session.user,
					"catalog_hash": expected_hash,
					"creation": [">=", frappe.utils.now_datetime() - timedelta(minutes=CHECK_VALID_MINUTES)],
				},
				pluck="name",
				order_by="creation desc",
				limit_page_length=1,
			)
		if not passing:
			return _response(
				log, "Refused", "gate", errors=["Run Check again: the catalog changed or the check expired"]
			)
		log["check_log"] = passing[0]

	log["stage"] = "lock"
	if frappe.db.sql("select get_lock(%s, 0)", _lock_name())[0][0] != 1:
		return _response(
			log, "Refused", "lock", errors=["Another catalog check or import is running; try again shortly"]
		)
	log["locked"] = True
	log["stage"] = "validate"
	schema = cached_schema()
	try:
		reference = _existence_map(catalog, schema)
		missing = [
			f"Declared existing record not found in ERPNext: {doctype} {name}"
			for doctype, names in catalog.get("external_links", {}).items()
			for name in names
			if name not in reference.get(doctype, ())
		]
		if missing:
			return _response(log, "Failed", "validate", errors=missing)
		_records, batches, external = prepare_catalog(catalog, schema, reference)
	except ValueError as error:
		return _response(log, "Failed", "validate", errors=str(error).splitlines())

	log["stage"] = "permissions"
	errors = [
		f"You cannot create {doctype}"
		for doctype in dict(batches)
		if not frappe.has_permission(doctype, "create")
	]
	if errors:
		return _response(log, "Failed", "permissions", errors=errors, external=external)

	log["stage"] = "insert"
	results = _insert_batches(batches, schema, mode)
	failed = any(row["status"] in {"error", "skipped"} for row in results)
	if mode == "Check" or failed:
		frappe.db.rollback()
		status = ("Failed" if failed else "Passed") if mode == "Check" else "Rolled Back"
	else:
		# commit the complete import before its audit receipt.
		frappe.db.commit()  # nosemgrep
		status = "Imported"
	return _response(log, status, "insert", results=results, external=external)


def _lock_name():
	return f"{LOCK}:{frappe.local.site}"


def _existence_map(catalog, schema):
	"""Only fetch names needed by this run; existence is independent of read permissions."""
	external = catalog.get("external_links", {})
	if not isinstance(external, dict) or any(
		not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names)
		for names in external.values()
	):
		raise ValueError("external_links must map DocType names to lists of existing record names")
	wanted = defaultdict(set)
	for doctype, rows in catalog["records"].items():
		meta = schema["doctypes"].get(doctype)
		if not meta or meta.get("istable"):
			continue  # prepare_catalog reports invalid parent DocTypes.
		for index, row in enumerate(rows):
			if not isinstance(row, dict):
				continue
			row = with_defaults(doctype, row, schema)
			# Malformed child tables must reach normal CLI validation, not crash link traversal.
			if _record_errors(doctype, row, schema, f"{doctype}[{index}]"):
				continue
			if name := identity(doctype, row, schema):
				wanted[doctype].add(name)
			for target, value, _path in links(doctype, row, schema):
				if target:
					wanted[target].add(value)
	for doctype, names in external.items():
		wanted[doctype].update(names)
	reference = {}
	for doctype, names in wanted.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		found = reference[doctype] = set()
		names = sorted(names)
		for start in range(0, len(names), 500):
			found.update(
				frappe.get_all(
					doctype,
					filters={"name": ["in", names[start : start + 500]]},
					pluck="name",
					limit_page_length=0,
				)
			)
	return reference


def _insert_batches(batches, schema, mode):
	failed, results = set(), []
	for batch, (doctype, rows) in enumerate(batches, 1):
		for row in rows:
			name = identity(doctype, row, schema)
			key = (doctype, name)
			result = {
				"batch": batch,
				"doctype": doctype,
				"catalog_name": name,
				"name": "",
				"status": "skipped",
				"message": "",
				"warnings": [],
			}
			results.append(result)
			blocked = [
				f"{target} {value}"
				for target, value, _ in links(doctype, row, schema)
				if (target, value) in failed
			]
			if blocked:
				failed.add(key)
				result["message"] = f"Depends on {blocked[0]}, which failed"
				continue
			frappe.local.message_log = []
			frappe.db.savepoint(SAVEPOINT)
			try:
				doc = frappe.get_doc({**row, "doctype": doctype})
				doc.insert()
			except Exception as error:
				frappe.db.rollback(save_point=SAVEPOINT)
				failed.add(key)
				result.update(status="error", message=_error_text(error))
			else:
				frappe.db.release_savepoint(SAVEPOINT)
				result.update(
					name=doc.name, status="created" if mode == "Import" else "checked", warnings=_messages()
				)
	return results


def _messages():
	messages = []
	for entry in getattr(frappe.local, "message_log", None) or []:
		if isinstance(entry, str):
			with suppress(ValueError):
				entry = json.loads(entry)
		text = entry.get("message", "") if isinstance(entry, dict) else str(entry)
		text = frappe.utils.strip_html_tags(str(text)).strip()
		if text and text not in messages:
			messages.append(text)
	return messages


def _error_text(error):
	messages = _messages()
	text = messages[-1] if messages else frappe.utils.strip_html_tags(str(error))
	if not (
		type(error).__module__.startswith("frappe.")
		or isinstance(error, (frappe.ValidationError, frappe.PermissionError))
	):
		text = f"{type(error).__name__}: {text}"
	return text[:1000]


def _response(log, status, stage, *, errors=(), results=(), external=()):
	results, errors = list(results), list(errors)
	return {
		"ok": status in {"Passed", "Imported"},
		"mode": log["mode"],
		"status": status,
		"stage": stage,
		"log": None,
		"catalog_hash": log.get("catalog_hash"),
		"errors": errors,
		"external": external,
		"results": results,
		"summary": {
			"records": log["record_count"],
			"created": sum(row["status"] == "created" for row in results) if status == "Imported" else 0,
			"checked": sum(row["status"] == "checked" for row in results),
			"errors": len(errors) + sum(row["status"] == "error" for row in results),
			"skipped": sum(row["status"] == "skipped" for row in results),
			"warnings": sum(len(row["warnings"]) for row in results),
			"duration_ms": 0,
		},
	}


def _write_log(log, response):
	payload = json.dumps(log["catalog_json"], indent=1, ensure_ascii=False, default=str)
	if response["stage"] == "shape" and response["status"] == "Refused":
		payload = payload.encode("utf-8")[: 100 * 1024].decode("utf-8", errors="ignore")
	summary = response["summary"]
	doc = frappe.get_doc(
		{
			"doctype": AUDIT,
			"mode": log["mode"],
			"user": log["user"],
			"status": response["status"],
			"product_type": (log.get("product_type") or "")[:140],
			"series_name": (log.get("series_name") or "")[:140],
			"catalog_hash": log.get("catalog_hash"),
			"check_log": log.get("check_log"),
			"catalog_json": payload,
			"results_json": json.dumps(response["results"], indent=1, ensure_ascii=False),
			"error_detail": log.get("error_detail"),
			"record_count": summary["records"],
			"created_count": summary["created"],
			"error_count": summary["errors"],
			"skipped_count": summary["skipped"],
			"warning_count": summary["warnings"],
			"duration_ms": summary["duration_ms"],
		}
	)
	doc.insert(ignore_permissions=True)  # Audit only; catalog records never bypass permissions.
	# the audit receipt survives dry-run and failed-import rollbacks.
	frappe.db.commit()  # nosemgrep
	return doc.name
