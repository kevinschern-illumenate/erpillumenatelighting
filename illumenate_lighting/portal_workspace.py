"""Preserve site workspace edits before Frappe imports the exported workspace."""

import copy
import hashlib
import json
from pathlib import Path

import frappe

WORKSPACE = "ilLumenate Lighting"


def merge_workspace(site, shipped):
	"""Retain site rows/blocks and add shipped destinations by stable identity."""
	result = copy.deepcopy(site)
	keys = {
		"shortcuts": ("type", "link_to", "label"),
		"links": ("type", "link_to", "label"),
		"number_cards": ("number_card_name",),
		"charts": ("chart_name",),
		"quick_lists": ("document_type", "label"),
		"custom_blocks": ("custom_block_name",),
	}
	for field, identity in keys.items():
		rows = result.setdefault(field, [])
		seen = {tuple(row.get(key) for key in identity) for row in rows}
		for row in shipped.get(field) or []:
			key = tuple(row.get(key) for key in identity)
			if key not in seen:
				rows.append(copy.deepcopy(row))
				seen.add(key)
		for row in rows:
			for metadata in ("name", "parent", "parenttype", "parentfield", "idx", "creation", "modified"):
				row.pop(metadata, None)
	blocks = json.loads(site.get("content") or "[]")
	seen = {block.get("id") for block in blocks}
	for block in json.loads(shipped.get("content") or "[]"):
		if block.get("id") not in seen:
			blocks.append(block)
			seen.add(block.get("id"))
	result["content"] = json.dumps(blocks)
	return result


def _directory():
	return Path(frappe.get_site_path("private", "backups", "ill-workspace"))


def before_migrate():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return
	data = frappe.as_json(frappe.get_doc("Workspace", WORKSPACE).as_dict())
	directory = _directory()
	directory.mkdir(parents=True, exist_ok=True)
	if (directory / "pending.json").exists():
		# A failed migration may already have imported shipped workspace data.
		# Keep the original site snapshot until its merge succeeds.
		return
	name = hashlib.sha256(data.encode()).hexdigest() + ".json"
	(directory / name).write_text(data, encoding="utf-8")
	(directory / "pending.json").write_text(json.dumps({"backup": name}), encoding="utf-8")


def after_migrate():
	directory = _directory()
	pending = directory / "pending.json"
	if not pending.exists():
		return
	name = json.loads(pending.read_text(encoding="utf-8"))["backup"]
	if Path(name).name != name or not name.endswith(".json"):
		frappe.throw("Workspace backup path is invalid")
	site = json.loads((directory / name).read_text(encoding="utf-8"))
	shipped = json.loads(
		Path(
			frappe.get_app_path(
				"illumenate_lighting",
				"illumenate_lighting",
				"workspace",
				"illumenate_lighting",
				"illumenate_lighting.json",
			)
		).read_text(encoding="utf-8")
	)
	merged = merge_workspace(site, shipped)
	doc = frappe.get_doc("Workspace", WORKSPACE)
	for field in (
		"content",
		"shortcuts",
		"links",
		"number_cards",
		"charts",
		"quick_lists",
		"custom_blocks",
		"roles",
		"label",
		"title",
		"icon",
		"indicator_color",
		"is_hidden",
		"hide_custom",
		"parent_page",
		"sequence_id",
		"public",
		"for_user",
	):
		if field in merged and doc.meta.has_field(field):
			doc.set(field, merged[field])
	doc.save(ignore_permissions=True)
	# Keep immutable backups; a receipt distinguishes applied from pending data.
	(directory / "last-merge.json").write_text(
		json.dumps({"backup": name, "applied_on": str(frappe.utils.now())}), encoding="utf-8"
	)
	pending.unlink()
