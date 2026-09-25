"""Pinned linear-fixture materials, physical cables and build identity."""

import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	cable_stock_quantity,
	canonical_json,
	fingerprint,
	finite_number,
	parse_bool,
)

ENGINE_VERSION = "linear-2"


def validate_material_additions(original, overrides, item_lookup):
	"""A BOM edit may add materials; removing engineered cuts requires reconfiguration."""
	from illumenate_lighting.illumenate_lighting.api.build_artifacts import quantities

	rows = []
	for row in overrides:
		item = item_lookup(row["item_code"])
		qty = finite_number(row["qty"], minimum=0, field="material quantity")
		if not item or item.disabled or qty <= 0:
			raise ValueError("Material additions require active Items and positive quantities")
		if any(row.get(key) and row[key] != item.stock_uom for key in ("uom", "stock_uom")):
			raise ValueError("Enter engineering material additions in the Item stock UOM")
		rows.append(
			{"item_code": row["item_code"], "qty": qty, "uom": item.stock_uom, "stock_uom": item.stock_uom}
		)
	required, proposed = quantities(original), quantities(rows)
	if any(proposed.get(key, 0) + 1e-6 < qty for key, qty in required.items()):
		raise ValueError("Reconfigure geometry or power before removing required build materials")
	return [
		{"item_code": item, "qty": qty, "uom": uom, "stock_uom": uom}
		for (item, uom), qty in sorted(proposed.items())
	]


def material_variant(doc, overrides):
	from illumenate_lighting.illumenate_lighting.api.build_artifacts import quantities
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount
	from illumenate_lighting.illumenate_lighting.portal.staff import require

	require("engineering")
	build = snapshot(doc)
	components = validate_material_additions(
		build["components"],
		overrides,
		lambda item: frappe.db.get_value("Item", item, ["stock_uom", "disabled"], as_dict=True),
	)
	if quantities(components) == quantities(build["components"]):
		return doc
	original = quantities(build["components"])
	extra_price = sum(
		selling_amount(row["item_code"], row["qty"] - original.get((row["item_code"], row["stock_uom"]), 0))
		for row in components
		if row["qty"] > original.get((row["item_code"], row["stock_uom"]), 0)
	)
	build.setdefault("engineering_base_components", build["components"])
	build["components"] = components
	build["engineering_material_additions"] = True
	identity = fingerprint(build)
	frappe.db.sql("select name from `tabilL-Fixture-Template` where name=%s for update", doc.fixture_template)
	existing = frappe.db.get_value(doc.doctype, {"config_hash": identity}, "name")
	if existing:
		return frappe.get_doc(doc.doctype, existing)
	metadata = {
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"parent",
		"parenttype",
		"parentfield",
	}

	def clean(value):
		if isinstance(value, dict):
			return {
				key: clean(item)
				for key, item in value.items()
				if key not in metadata and not key.startswith("_")
			}
		if isinstance(value, list):
			return [clean(item) for item in value]
		return value

	data = clean(doc.as_dict())
	data.update(
		config_hash=identity,
		name="ILL-CF-" + identity,
		build_snapshot_json=canonical_json(build),
		component_manifest_json=canonical_json(components),
		parent_configured_fixture=doc.name,
		variant_origin="Quotation Tool",
		variant_suffix=identity[:8].upper(),
		configured_item=None,
		bom=None,
		work_order=None,
		spec_submittal=None,
	)
	base_price = current_estimate(doc)
	data["pricing_snapshot"] = [
		{
			"msrp_unit": float(base_price) + extra_price,
			"tier_unit": float(base_price) + extra_price,
			"timestamp": frappe.utils.now(),
			"adder_breakdown_json": canonical_json(
				[{"component": "engineering additions", "amount": extra_price}]
			),
		}
	]
	variant = frappe.get_doc(data)
	variant.flags.linear_engine_write = True
	variant.insert(ignore_permissions=True)
	return variant


def cable_manifest(fixture):
	"""Each run feed and each outgoing jumper/end leader occurs exactly once."""
	cuts = []
	segments = fixture.segments or []
	first = segments[0] if segments else None
	for i, run in enumerate(fixture.runs or []):
		length = run.get("leader_len_mm")
		item = run.get("leader_item") or fixture.leader_item
		if i == 0 and first and first.get("start_leader_len_mm"):
			length = first.start_leader_len_mm
			item = first.get("start_leader_item") or item
		cuts.append(
			{
				"key": f"feed-{run.run_index}",
				"role": "leader" if i == 0 else "additional feed",
				"item_code": item,
				"length_mm": length,
				"run_index": run.run_index,
			}
		)
	for segment in segments:
		if segment.get("end_jumper_len_mm"):
			cuts.append(
				{
					"key": f"end-{segment.segment_index}",
					"role": "jumper" if fixture.is_multi_segment else "end leader",
					"item_code": segment.get("end_jumper_item"),
					"length_mm": segment.end_jumper_len_mm,
				}
			)
	if not cuts:
		raise ValueError("No physical leader/feed plan is available for this fixture")
	for cut in cuts:
		length = finite_number(cut["length_mm"], minimum=0, field="physical cable length")
		if length <= 0 or not cut["item_code"]:
			raise ValueError("Every fixture feed needs a resolved cable Item and positive physical length")
		item = frappe.db.get_value(
			"Item", cut["item_code"], ["stock_uom", "disabled", "ill_cable_assembly_length_mm"], as_dict=True
		)
		if not item or item.disabled:
			raise ValueError("A physical cable Item is missing or disabled")
		cut["stock_uom"] = item.stock_uom
		cut["qty"] = cable_stock_quantity(
			length, "mm", item.stock_uom, assembly_length_mm=item.ill_cable_assembly_length_mm or None
		)
	return cuts


def cable_bom_rows(cuts):
	totals = {}
	for cut in cuts:
		key = (cut["item_code"], cut["stock_uom"])
		totals[key] = totals.get(key, 0) + cut["qty"]
	return [
		{"item_code": item, "qty": qty, "uom": uom, "stock_uom": uom}
		for (item, uom), qty in sorted(totals.items())
	]


def snapshot(doc):
	result = json.loads(doc.get("build_snapshot_json") or "{}")
	if doc.get("build_schema_version") != 2 or fingerprint(result) != doc.config_hash:
		raise ValueError("Linear fixture build snapshot does not match its identity")
	return result


def current_estimate(doc):
	"""Price pinned physical work today; never rewrite the saved build or an offer."""
	from illumenate_lighting.illumenate_lighting.api.build_artifacts import quantities
	from illumenate_lighting.illumenate_lighting.api.configurator_engine import _calculate_pricing
	from illumenate_lighting.illumenate_lighting.api.tape_neon_pricing import selling_amount

	build = snapshot(doc)
	resolved = build["resolved_items"]
	for row in build["components"]:
		item = frappe.db.get_value("Item", row["item_code"], ["stock_uom", "disabled"], as_dict=True)
		if not item or item.disabled or item.stock_uom != row["stock_uom"]:
			raise ValueError("A pinned linear component is inactive or its stock UOM has changed")
	price = _calculate_pricing(
		doc.fixture_template,
		resolved,
		build["computed"],
		doc.finish,
		doc.lens_appearance,
		doc.mounting_method,
		doc.endcap_style_start,
		doc.endcap_style_end,
		doc.power_feed_type,
		doc.environment_rating,
		doc.tape_offering,
		1,
		driver_plan=resolved.get("driver_plan"),
	)["msrp_unit"]
	if build.get("engineering_material_additions"):
		original = quantities(build["engineering_base_components"])
		price += sum(
			selling_amount(
				row["item_code"], row["qty"] - original.get((row["item_code"], row["stock_uom"]), 0)
			)
			for row in build["components"]
			if row["qty"] > original.get((row["item_code"], row["stock_uom"]), 0)
		)
	return round(price, 2)


def finish(doc, inputs, computed, resolved, include_power, override, *, in_memory=False):
	"""Seal a fully populated engine document, then deduplicate without rewriting geometry."""
	from illumenate_lighting.illumenate_lighting.api.engineering_sources import capture
	from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import build_fixture_bom_items

	doc._renumber_user_segments()
	doc.before_save()  # Populate display/SKU attributes once, before the v2 immutable boundary.
	doc.display_part_number = doc._generate_part_number()
	doc.build_schema_version = 2
	doc.engine_version = ENGINE_VERSION
	cables = cable_manifest(doc)
	doc.cable_manifest_json = canonical_json(cables)
	components = build_fixture_bom_items(doc)
	value = {
		"engine_version": ENGINE_VERSION,
		"inputs": {
			**inputs,
			"include_power_supply": parse_bool(include_power),
			"override_max_run_ft": override,
			"dimming_protocol": (resolved.get("driver_plan") or {}).get("requested_protocol"),
		},
		"computed": computed,
		"resolved_items": resolved,
		"components": components,
		"cables": cables,
		"engineering_sources": capture(
			tape_offering=doc.tape_offering,
			tape_spec=frappe.db.get_value("ilL-Rel-Tape Offering", doc.tape_offering, "tape_spec")
			if doc.tape_offering
			else None,
			profile=doc.profile_item,
			lens=frappe.db.get_value("ilL-Attribute-Lens Appearance", doc.lens_appearance, "lens_spec")
			if doc.lens_appearance
			else None,
			driver=doc.drivers[0].driver_item if doc.drivers else None,
		),
	}
	doc.config_hash = fingerprint(value)
	doc.build_snapshot_json = canonical_json(value)
	doc.component_manifest_json = canonical_json(components)
	doc.power_plan_json = canonical_json(resolved.get("driver_plan") or {})
	doc.name = "ILL-CF-" + doc.config_hash
	if in_memory:
		return doc
	frappe.db.sql("select name from `tabilL-Fixture-Template` where name=%s for update", doc.fixture_template)
	existing = frappe.db.get_value("ilL-Configured-Fixture", {"config_hash": doc.config_hash}, "name")
	if existing:
		saved = frappe.get_doc("ilL-Configured-Fixture", existing)
		snapshot(saved)
		return saved.name
	doc.flags.linear_engine_write = True
	doc.insert(ignore_permissions=True)
	return doc.name
