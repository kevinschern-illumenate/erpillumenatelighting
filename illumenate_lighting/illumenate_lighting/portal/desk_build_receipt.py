"""Durable Desk retries, including builds for unsaved ERP parent documents."""

import inspect
import json
from functools import wraps

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json, fingerprint


def idempotent(function):
	signature = inspect.signature(function)

	@wraps(function)
	def wrapped(*args, **kwargs):
		from illumenate_lighting.illumenate_lighting.portal.configuration import (
			resolve_line,
			schedule_context,
		)

		bound = signature.bind(*args, **kwargs)
		bound.apply_defaults()
		values = bound.arguments
		parent, name = values["parent_doctype"], values.get("parent_name")
		user = frappe.session.user
		if parent not in {"Quotation", "Sales Order"} or user == "Guest":
			frappe.throw("Choose a supported ERP parent", frappe.PermissionError)
		if frappe.db.get_value("User", user, "user_type") != "System User":
			frappe.throw("Desk builds require an enabled staff user", frappe.PermissionError)
		# Serialize same-user attempts, including unsaved document-only builds.
		frappe.db.sql("select name from `tabUser` where name=%s for update", user)
		if not frappe.db.get_value("User", user, "enabled"):
			frappe.throw("User is disabled", frappe.PermissionError)
		if not frappe.has_permission(parent, "write" if name else "create", doc=name):
			frappe.throw("Parent document is unavailable", frappe.PermissionError)
		schedule = (
			schedule_context(values["schedule"], write=True, lock=True) if values.get("schedule") else None
		)
		if name:
			frappe.db.sql(f"select name from `tab{parent}` where name=%s for update", name)
			doc = frappe.get_doc(parent, name)
			if doc.docstatus != 0:
				frappe.throw("Create a draft amendment before changing a submitted document")
		key = values.get("idempotency_key")
		if not isinstance(key, str) or not 8 <= len(key) <= 128:
			frappe.throw("Reload the configurator to obtain a save request key")
		request_key = fingerprint({"surface": "Desk", "actor": user, "key": key})
		request_hash = fingerprint(dict(values))
		receipt = frappe.db.get_value(
			"ilL-Configuration-Receipt",
			{"request_key": request_key},
			["request_hash", "response_json"],
			as_dict=True,
		)
		if receipt:
			if receipt.request_hash != request_hash:
				frappe.throw("This save key was used for different configuration content")
			return {**json.loads(receipt.response_json), "already_existed": True}
		if name and "expected_parent_modified" in values:
			if not values["expected_parent_modified"] or str(doc.modified) != str(
				values["expected_parent_modified"]
			):
				frappe.throw("The parent document changed. Reload before applying the configuration.")
		if schedule:
			if not values.get("expected_modified") or str(schedule.modified) != str(
				values["expected_modified"]
			):
				frappe.throw("The schedule changed; return to line selection and reload it")
			line = resolve_line(schedule, values.get("line_key"), values.get("line_idx"))
			values["line_idx"] = schedule.lines.index(line) if line else None
		result = function(**values)
		if not result.get("success"):
			return result
		result["save_receipt"] = request_key
		if "row_values" in result:
			result["row_values"]["ill_configuration_save_key"] = request_key
		result["already_existed"] = False
		record = frappe.get_doc(
			{
				"doctype": "ilL-Configuration-Receipt",
				"schedule": values.get("schedule"),
				"actor": user,
				"request_key": request_key,
				"request_hash": request_hash,
				"response_json": canonical_json(json.loads(frappe.as_json(result))),
			}
		)
		record.flags.configuration_service_write = True
		record.insert(ignore_permissions=True)
		return result

	return wrapped
