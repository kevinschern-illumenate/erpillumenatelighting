"""Explicit, checksum-guarded copy rehearsal; never deletes a public source.

Bench-only. Reference changes and public/CDN removal are separate reviewed steps.
Issued packet manifests and published drawing evidence are never rewritten.
"""

import hashlib
import json

import frappe

from illumenate_lighting.illumenate_lighting.api.build_artifacts import atomic_build

PARENTS = ("ilL-Document-Request", "ilL-Project-Fixture-Schedule", "Issue", "ilL-Export-Job")
REFERENCES = (
	("ilL-Child-Fixture-Schedule-Line", "spec_sheet"),
	("ilL-Request-Deliverable", "file"),
	("ilL-Export-Job", "output_file"),
)


def inspect_file(name):
	frappe.only_for("System Manager")
	doc = frappe.get_doc("File", name)
	if (
		doc.is_private
		or not str(doc.file_url).startswith("/files/")
		or doc.attached_to_doctype not in PARENTS
	):
		frappe.throw("Choose a legacy public project/request file from the inventory")
	if not doc.attached_to_name or not frappe.db.exists(doc.attached_to_doctype, doc.attached_to_name):
		frappe.throw("Resolve the missing attachment owner before copying")
	content = doc.get_content()
	if not isinstance(content, bytes):
		content = content.encode()
	references = []
	for doctype, field in REFERENCES:
		if not frappe.get_meta(doctype).has_field(field):
			continue
		fields = ["name", "parent"] if frappe.get_meta(doctype).istable else ["name"]
		for row in frappe.get_all(doctype, filters={field: doc.file_url}, fields=fields):
			references.append({"doctype": doctype, "field": field, **dict(row)})
	aliases = frappe.get_all(
		"File", filters={"file_url": doc.file_url}, fields=["name", "attached_to_doctype", "attached_to_name"]
	)
	return (
		doc,
		content,
		{
			"source_file": name,
			"source_url": doc.file_url,
			"sha256": hashlib.sha256(content).hexdigest(),
			"bytes": len(content),
			"references": references,
			"file_aliases": aliases,
			"automatic_reference_rewrite": False,
			"required_checks": [
				"Search rich text, JSON snapshots and external CMS/CDN references",
				"Verify each intended and denied actor against the private copy",
				"Retain issued packet/drawing evidence",
				"Retire public origin and purge CDN only after complete reference review",
			],
		},
	)


def dry_run(file_names):
	frappe.only_for("System Manager")
	names = json.loads(file_names) if isinstance(file_names, str) else file_names
	if (
		not isinstance(names, list)
		or not 1 <= len(names) <= 50
		or any(not isinstance(name, str) for name in names)
	):
		raise ValueError("Choose 1-50 File record names from the inventory")
	return {"mode": "dry_run", "files": [inspect_file(name)[2] for name in dict.fromkeys(names)]}


@atomic_build
def copy_private(file_name, expected_sha256):
	frappe.only_for("System Manager")
	frappe.db.sql("select name from `tabFile` where name=%s for update", file_name)
	doc, content, report = inspect_file(file_name)
	if report["sha256"] != expected_sha256:
		frappe.throw("Source bytes changed after inventory; inspect the current revision")
	# Deterministic name plus parent scope makes interrupted retries inspectable.
	copy_name = f"legacy-{doc.name}-{doc.file_name}"
	existing = frappe.db.get_value(
		"File",
		{
			"file_name": copy_name,
			"is_private": 1,
			"attached_to_doctype": doc.attached_to_doctype,
			"attached_to_name": doc.attached_to_name,
		},
		"name",
	)
	private = (
		frappe.get_doc("File", existing)
		if existing
		else frappe.get_doc(
			{
				"doctype": "File",
				"file_name": copy_name,
				"content": content,
				"is_private": 1,
				"owner": "Administrator",
				"attached_to_doctype": doc.attached_to_doctype,
				"attached_to_name": doc.attached_to_name,
			}
		).insert(ignore_permissions=True)
	)
	if not private.is_private or not str(private.file_url).startswith("/private/files/"):
		frappe.throw("Storage did not create a private copy")
	if hashlib.sha256(private.get_content()).hexdigest() != expected_sha256:
		frappe.throw("Private copy checksum differs from the inventory")
	return {
		**report,
		"mode": "copied",
		"private_file": private.name,
		"private_url": private.file_url,
		"source_retained": True,
		"reference_rewrite_required": True,
		"access_verified": False,
	}
