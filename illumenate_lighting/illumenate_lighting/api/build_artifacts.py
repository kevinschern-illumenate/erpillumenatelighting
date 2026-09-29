"""Shared immutable material verification for configured ERP BOMs."""

import math
from functools import wraps

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import finite_number

# Immutable builds with readable Item codes: the Item field that links back to
# the build, and the prefix of the content-addressed build ID.
BUILD_ITEMS = {
	"ilL-Configured-Fixture": ("custom_ill_configured_fixture", "ILL-CF-"),
	"ilL-Configured-Tape-Neon": ("custom_ill_configured_tape_neon", "ILL-TN-"),
}
ITEM_CODE_MAX_LENGTH = 140


def build_id(configured):
	"""Content-addressed identity of an immutable build (its historical Item code)."""
	build_hash = configured.config_hash or ""
	if len(build_hash) != 64 or any(char not in "0123456789abcdef" for char in build_hash):
		raise ValueError("A versioned configured product requires a complete build hash")
	return BUILD_ITEMS[configured.doctype][1] + build_hash


def item_belongs_to_build(item_code, configured):
	"""An Item is a build's own when its code is the build ID or it links back to the build."""
	if not item_code:
		return False
	if item_code == build_id(configured):
		return True
	link_field = BUILD_ITEMS[configured.doctype][0]
	return frappe.db.get_value("Item", item_code, link_field) == configured.name


def build_item_code(configured, part_number):
	"""The Item code for a build: its part number, kept unique per build.

	A part number omits some engineering inputs, so different builds can share
	one while each still needs its own Item and BOM. The first build takes the
	plain part number, a later one appends part of its build hash, and the build
	ID is the last resort. An existing Item is only ever returned for its own build.
	"""
	identity = build_id(configured)
	# A build keeps the Item it already has, including a legacy build-ID code.
	if frappe.db.exists("Item", identity):
		return identity
	own = frappe.db.get_value("Item", {BUILD_ITEMS[configured.doctype][0]: configured.name}, "name")
	if own:
		return own
	base = (part_number or "").strip()
	suffixed = [f"{base}-{configured.config_hash[:size].upper()}" for size in (6, 12)]
	for code in ([base, *suffixed] if base else []):
		if len(code) > ITEM_CODE_MAX_LENGTH or "<" in code or ">" in code:
			continue
		if not frappe.db.exists("Item", code):
			return code
	return identity


def atomic_build(function):
	@wraps(function)
	def wrapped(*args, **kwargs):
		point = "build_" + function.__name__
		frappe.db.savepoint(point)
		try:
			result = function(*args, **kwargs)
			if isinstance(result, dict) and (
				result.get("success") is False or result.get("is_valid") is False
			):
				frappe.db.rollback(save_point=point)
			return result
		except Exception:
			frappe.db.rollback(save_point=point)
			raise

	return wrapped


def quantities(rows):
	totals = {}
	for row in rows:
		key = row.get("item_code"), row.get("stock_uom") or row.get("uom")
		qty = row.get("stock_qty") if row.get("stock_qty") is not None else row.get("qty")
		totals[key] = totals.get(key, 0) + finite_number(qty, minimum=0, field="BOM component quantity")
	return totals


def assert_bom(item_code, components, bom):
	expected, actual = quantities(components), quantities(bom.items)
	if (
		bom.item != item_code
		or bom.docstatus != 1
		or not bom.is_active
		or float(bom.quantity) != 1
		or expected.keys() != actual.keys()
		or any(not math.isclose(qty, actual[key], rel_tol=0, abs_tol=1e-6) for key, qty in expected.items())
	):
		raise ValueError("BOM no longer matches the pinned build; engineering review is required")


@atomic_build
def ensure_bom(configured, item_code, components):
	tables = {
		"ilL-Configured-Group",
		"ilL-Configured-Fixture",
		"ilL-Configured-Tape-Neon",
		"ilL-Configured-LED-Sheet",
	}
	if configured.doctype not in tables:
		raise ValueError("Unsupported configured build type")
	frappe.db.sql(f"select name from `tab{configured.doctype}` where name=%s for update", configured.name)
	if not components:
		raise ValueError("A configured build must include physical materials")
	for row in components:
		item = frappe.db.get_value("Item", row["item_code"], ["stock_uom", "disabled"], as_dict=True)
		if not item or item.disabled or item.stock_uom != row["stock_uom"]:
			raise ValueError(
				"A build component is disabled or its stock UOM changed; engineering review is required"
			)
	name = frappe.db.get_value(configured.doctype, configured.name, "bom") or frappe.db.get_value(
		"BOM", {"item": item_code, "docstatus": 1, "is_active": 1}, "name"
	)
	if name:
		bom = frappe.get_doc("BOM", name)
		created = False
	else:
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": item_code,
				"quantity": 1,
				"is_active": 1,
				"is_default": 1,
				"with_operations": 0,
				"items": components,
				"remarks": f"Pinned build {configured.name}; SHA-256 {configured.config_hash}",
			}
		)
		bom.insert(ignore_permissions=True)
		bom.flags.ignore_permissions = True
		bom.submit()
		created = True
	assert_bom(item_code, components, bom)
	return {"success": True, "bom_name": bom.name, "created": created, "skipped": not created, "messages": []}
