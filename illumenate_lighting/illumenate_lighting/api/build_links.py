"""Keep a configured row's build links on the Item the row orders.

A Quotation / Sales Order row names its configured build twice: ERPNext's
``item_code`` (which brings the Item's name, description and default BOM) and
this app's ``ill_*`` build links. Picking another configured Item in the grid
changes only the first, so the row would quote one build and pin another, and
submitting the order stops on the pinned-build check in manufacturing_order.
Before every save and submit, a row whose Item belongs to a different build
takes that build's links.
"""

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.api.build_artifacts import BUILD_ITEMS

# Build doctype → the row field that links it.
ROW_LINKS = {
	"ilL-Configured-Fixture": "ill_configured_fixture",
	"ilL-Configured-Tape-Neon": "ill_configured_tape_neon",
}
# Inputs of the previous build. Cleared so a reopen rebuilds them from the new build.
STALE_INPUTS = ("ill_configurator_request", "ill_bom_override_json")


def item_build(item_code):
	"""``(doctype, name)`` of the immutable build an Item belongs to, or ``None``."""
	if not item_code:
		return None
	for doctype, (item_field, prefix) in BUILD_ITEMS.items():
		# Legacy builds use the build ID itself as their Item code.
		if item_code.startswith(prefix) and frappe.db.exists(doctype, item_code):
			return doctype, item_code
		name = frappe.db.get_value("Item", item_code, item_field)
		if name:
			return doctype, name
	return None


def row_build(row):
	"""``(doctype, name)`` of the build a row links, or ``None``."""
	for doctype, field in ROW_LINKS.items():
		if row.get(field):
			return doctype, row.get(field)
	return None


def build_values(doc):
	"""Row build fields for one configured build, as ``_apply_artifact_to_row`` writes them."""
	from illumenate_lighting.illumenate_lighting.api.configured_product_builder import (
		_fixture_configuration_snapshot,
		_serialize_json,
		_tape_neon_configuration_snapshot,
	)

	if doc.doctype == "ilL-Configured-Fixture":
		values = {
			"ill_product_type": "Linear Fixture",
			"ill_configured_fixture": doc.name,
			"ill_configured_tape_neon": None,
			"ill_template_code": doc.get("fixture_template"),
			"ill_requested_length_mm": doc.get("requested_overall_length_mm"),
			"ill_mfg_length_mm": doc.get("manufacturable_overall_length_mm"),
			"ill_runs_count": doc.get("runs_count"),
			"ill_finish": doc.get("finish"),
			"ill_lens": doc.get("lens_appearance"),
			"ill_configuration_json": _serialize_json(_fixture_configuration_snapshot(doc)),
		}
	else:
		values = {
			"ill_product_type": doc.get("product_category"),
			"ill_configured_fixture": None,
			"ill_configured_tape_neon": doc.name,
			"ill_template_code": doc.get("tape_neon_template"),
			"ill_requested_length_mm": doc.get("requested_length_mm"),
			"ill_mfg_length_mm": doc.get("manufacturable_length_mm"),
			"ill_runs_count": doc.get("total_segments"),
			"ill_finish": doc.get("finish") or doc.get("pcb_finish"),
			"ill_lens": None,
			"ill_configuration_json": _serialize_json(_tape_neon_configuration_snapshot(doc)),
		}
	values.update(
		{
			"ill_configured_product_doctype": doc.doctype,
			"ill_configured_product": doc.name,
			"ill_configured_item": doc.get("configured_item"),
			"ill_bom": doc.get("bom"),
			"ill_total_watts": doc.get("total_watts"),
			"ill_engine_version": doc.get("engine_version"),
			**{field: None for field in STALE_INPUTS},
		}
	)
	return values


def _set(row, fieldname, value):
	try:
		if not row.meta.has_field(fieldname):
			return
	except AttributeError:
		pass
	row.set(fieldname, value)


def follow_items(doc, method=None):
	"""Quotation / Sales Order ``validate``: point each configured row at its Item's own build."""
	if doc.docstatus == 2:
		return
	moved = []
	for row in doc.get("items") or []:
		if row.get("ill_is_power_supply_line") or row.get("ill_configured_group"):
			continue
		linked = row_build(row)
		if linked is None:
			continue
		own = item_build(row.item_code)
		if own is None or own == linked:
			continue  # An Item that names no build (a legacy fixture) keeps the row as it is.
		build = frappe.get_doc(*own)
		for field, value in build_values(build).items():
			_set(row, field, value)
		if doc.doctype == "Sales Order" and build.get("bom"):
			_set(row, "bom_no", build.bom)
		moved.append(str(row.idx))
	if moved:
		frappe.msgprint(
			_("Row(s) {0}: the configured build now matches the Item ordered on the row.").format(
				", ".join(moved)
			),
			indicator="blue",
			alert=True,
		)
	return moved
