"""Preserve site workspace edits before Frappe imports the exported workspace."""

import copy
import hashlib
import json
from pathlib import Path

import frappe

from illumenate_lighting.private_storage import private_state_directory

WORKSPACE = "ilLumenate Lighting"

# Blocks and cards of the pre-2026-10 layout. A site still holding any of them gets the
# shipped layout once, with its own blocks and cards kept after it, because merging by
# identity alone would interleave the old sections with the new ones.
RETIRED_BLOCKS = {
	"ill_dashboard_header",
	"ill_spacer_dashboard",
	"ill_portal_header",
	"ill_spacer_portal",
	"ill_catalog_systems_header",
	"ill_card_driver_controller",
	"ill_reports_header",
	"ill_spacer_reports",
	"ill_shortcuts_header",
	"ill_workflow_header",
	"ill_spacer_1",
	"ill_masters_header",
}
RETIRED_CARDS = {"Driver & Controller Catalog"}


def _cards(links):
	"""Split workspace links into (Card Break, [links]) groups; links before any card render nowhere."""
	groups = []
	for row in links or []:
		if row.get("type") == "Card Break":
			groups.append((row, []))
		elif groups:
			groups[-1][1].append(row)
	return groups


def _relayout(site, shipped):
	"""Take the shipped content and cards, then append the site's own blocks and cards."""
	result = copy.deepcopy(site)
	shipped_blocks = json.loads(shipped.get("content") or "[]")
	known = {block.get("id") for block in shipped_blocks} | RETIRED_BLOCKS
	own = [block for block in json.loads(site.get("content") or "[]") if block.get("id") not in known]
	result["content"] = json.dumps(shipped_blocks + own)
	shipped_links = shipped.get("links") or []
	known_cards = {row.get("label") for row, _ in _cards(shipped_links)} | RETIRED_CARDS
	links = copy.deepcopy(shipped_links)
	for card, rows in _cards(site.get("links")):
		if card.get("label") not in known_cards:
			links += copy.deepcopy([card, *rows])
	result["links"] = links
	return result


def merge_workspace(site, shipped):
	"""Retain site rows/blocks and add shipped destinations by stable identity."""
	site_ids = {block.get("id") for block in json.loads(site.get("content") or "[]")}
	if site_ids & RETIRED_BLOCKS:
		site = _relayout(site, shipped)
	result = copy.deepcopy(site)
	# v16 makes Workspace.type mandatory. Backups made on v15 (including a
	# pending snapshot from a failed upgrade) do not contain it. A normal save
	# of an existing document does not apply the new-document default.
	result["type"] = site.get("type") or shipped.get("type") or "Workspace"
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
	# A new shipped block goes after the shipped block before it, so a new section lands
	# where it ships instead of at the bottom; without a placed predecessor it is appended.
	anchor = None
	for block in json.loads(shipped.get("content") or "[]"):
		if block.get("id") not in seen:
			ids = [existing.get("id") for existing in blocks]
			position = ids.index(anchor) + 1 if anchor in ids else len(blocks)
			blocks.insert(position, block)
			seen.add(block.get("id"))
		anchor = block.get("id")
	result["content"] = json.dumps(blocks)
	return result


SAVEPOINT = "ill_workspace_restore"


def _directory():
	return private_state_directory(
		frappe.get_site_path("private"),
		"ill-workspace",
		log=lambda message: frappe.log_error(title="ilL workspace preservation", message=message),
	)


def _log_failure(stage):
	frappe.log_error(
		title=f"ilL workspace preservation: {stage} skipped",
		message=frappe.get_traceback(),
	)


def before_migrate():
	# Preserving workspace edits is best-effort and must never abort a migration.
	try:
		_snapshot_workspace()
	except Exception:
		_log_failure("before_migrate")


def after_migrate():
	# Roll back a partial workspace save and keep pending.json for the next migration.
	try:
		frappe.db.savepoint(SAVEPOINT)
		_restore_workspace()
	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		_log_failure("after_migrate")


def _snapshot_workspace():
	# Resolve first: this also moves a legacy directory out of private/backups.
	directory = _directory()
	if not frappe.db.exists("Workspace", WORKSPACE):
		return
	data = frappe.as_json(frappe.get_doc("Workspace", WORKSPACE).as_dict())
	directory.mkdir(parents=True, exist_ok=True)
	if (directory / "pending.json").exists():
		# A failed migration may already have imported shipped workspace data.
		# Keep the original site snapshot until its merge succeeds.
		return
	name = hashlib.sha256(data.encode()).hexdigest() + ".json"
	(directory / name).write_text(data, encoding="utf-8")
	(directory / "pending.json").write_text(json.dumps({"backup": name}), encoding="utf-8")


def _restore_workspace():
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
		"type",
		"link_type",
		"link_to",
		"external_link",
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

	# Other apps' after_migrate hooks still run in the same transaction. Keep
	# the original snapshot pending if a later hook fails and rolls this save
	# back; only mark it applied once Frappe commits the complete migration.
	def finish_merge():
		(directory / "last-merge.json").write_text(
			json.dumps({"backup": name, "applied_on": str(frappe.utils.now())}), encoding="utf-8"
		)
		pending.unlink(missing_ok=True)

	frappe.db.after_commit.add(finish_merge)
