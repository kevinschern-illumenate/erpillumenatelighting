"""Product authoring metadata, derived from the app's checked-in DocTypes.

No Frappe runtime is needed. Rebuild the browser snapshot with
``python -m tools.fixture_builder.catalog_schema`` after changing a DocType.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DOCTYPE_ROOT = Path(__file__).resolve().parents[1] / "doctype"
NON_VALUE = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}
PRODUCTS = {
	"fixture": {"label": "Linear fixtures", "template": "ilL-Fixture-Template", "spec": "ilL-Spec-Profile"},
	"tape": {"label": "LED tape", "template": "ilL-Tape-Neon-Template", "spec": "ilL-Spec-LED Tape"},
	"neon": {"label": "LED neon", "template": "ilL-Tape-Neon-Template", "spec": "ilL-Spec-LED Tape"},
	"led-sheet": {"label": "LED sheets", "template": "ilL-LED-Sheet-Template", "spec": "ilL-Spec-LED-Sheet"},
	"extrusion-kit": {
		"label": "Extrusion kits",
		"template": "ilL-Extrusion-Kit-Template",
		"spec": "ilL-Spec-Profile",
	},
	"driver": {"label": "Drivers", "template": "ilL-Driver-Template", "spec": "ilL-Spec-Driver"},
	"controller": {
		"label": "Controllers",
		"template": "ilL-Controller-Template",
		"spec": "ilL-Spec-Controller",
	},
}


def _field(name, label, kind="Data", **kwargs):
	return {"fieldname": name, "label": label, "fieldtype": kind, **kwargs}


def standard_doctypes():
	"""ERPNext v15 master-data fields used by this app, not transactional data.

	Custom product DocTypes are loaded live below. This small standard master
	contract is deliberately explicit; site-specific customizations are not guessed.
	"""
	return {
		"Item": {
			"autoname": "field:item_code",
			"fields": [
				_field("item_code", "Item Code", reqd=1),
				_field("item_name", "Item Name"),
				_field("item_group", "Item Group", "Link", options="Item Group", reqd=1),
				_field("stock_uom", "Default Unit of Measure", "Link", options="UOM", reqd=1),
				_field("is_stock_item", "Maintain Stock", "Check", default="1"),
				_field("disabled", "Disabled", "Check", default="0"),
				_field("is_sales_item", "Is Sales Item", "Check", default="1"),
				_field("is_purchase_item", "Is Purchase Item", "Check", default="1"),
				_field("description", "Description", "Text Editor"),
				_field("brand", "Brand", "Link", options="Brand"),
				_field("warranty_period", "Warranty Period (in days)", "Int"),
				_field("image", "Image", "Attach Image"),
				_field("has_variants", "Has Variants", "Check", default="0"),
				_field("variant_of", "Variant Of", "Link", options="Item"),
				_field(
					"variant_based_on", "Variant Based On", "Select", options="Item Attribute\nManufacturer"
				),
				_field("attributes", "Variant Attributes", "Table", options="Item Variant Attribute"),
				_field("supplier_items", "Supplier Items", "Table", options="Item Supplier"),
			],
		},
		"Item Variant Attribute": {
			"istable": 1,
			"fields": [
				_field("attribute", "Attribute", "Link", options="Item Attribute", reqd=1),
				_field("attribute_value", "Attribute Value"),
			],
		},
		"Item Supplier": {
			"istable": 1,
			"fields": [
				_field("supplier", "Supplier", "Link", options="Supplier", reqd=1),
				_field("supplier_part_no", "Supplier Part Number"),
				# Site custom field shown on the ilL Purchase Order print format.
				_field("custom_supplier_description", "Supplier Description", "Small Text"),
			],
		},
		"Item Attribute": {
			"autoname": "field:attribute_name",
			"fields": [
				_field("attribute_name", "Attribute Name", reqd=1),
				_field(
					"item_attribute_values", "Item Attribute Values", "Table", options="Item Attribute Value"
				),
			],
		},
		"Item Attribute Value": {
			"istable": 1,
			"fields": [
				_field("attribute_value", "Attribute Value", reqd=1),
				_field("abbr", "Abbreviation", reqd=1),
			],
		},
		"Item Group": {
			"autoname": "field:item_group_name",
			"fields": [
				_field("item_group_name", "Item Group Name", reqd=1),
				_field("parent_item_group", "Parent Item Group", "Link", options="Item Group"),
				_field("is_group", "Is Group", "Check", default="0"),
			],
		},
		"UOM": {
			"autoname": "field:uom_name",
			"fields": [
				_field("uom_name", "UOM Name", reqd=1),
				_field("must_be_whole_number", "Must be Whole Number", "Check"),
			],
		},
		"Brand": {"autoname": "field:brand", "fields": [_field("brand", "Brand", reqd=1)]},
		"Item Price": {
			"fields": [
				_field("item_code", "Item Code", "Link", options="Item", reqd=1),
				_field("price_list", "Price List", "Link", options="Price List", reqd=1),
				_field("price_list_rate", "Rate", "Currency", reqd=1),
				_field("currency", "Currency", "Link", options="Currency"),
				_field("uom", "UOM", "Link", options="UOM"),
			]
		},
	}


def build_schema():
	all_docs = {}
	for path in sorted(DOCTYPE_ROOT.glob("*/*.json")):
		doc = json.loads(path.read_text(encoding="utf-8"))
		all_docs[doc["name"]] = doc
	selected = {
		name
		for name, doc in all_docs.items()
		if not doc.get("istable")
		and (
			name.startswith(("ilL-Attribute-", "ilL-Spec-", "ilL-Rel-"))
			or name.endswith(("-Template", "-Submittal-Mapping"))
			or name in {"ilL-Webflow-Product", "ilL-Webflow-Category"}
		)
	}
	# Include every child of the authorable records, including certifications,
	# feed lengths, part-number builders, protocol lists, and Webflow content.
	pending = list(selected)
	while pending:
		for field in all_docs[pending.pop()]["fields"]:
			if field["fieldtype"] in ("Table", "Table MultiSelect"):
				child = field["options"]
				if child not in selected:
					selected.add(child)
					pending.append(child)
	doctypes = standard_doctypes()
	keys = ("fieldname", "label", "fieldtype", "options", "reqd", "default", "description", "read_only")
	for name in sorted(selected):
		doc = all_docs[name]
		doctypes[name] = {
			"autoname": doc.get("autoname", ""),
			"istable": doc.get("istable", 0),
			"fields": [
				{k: field[k] for k in keys if k in field}
				for field in doc["fields"]
				if field["fieldtype"] not in NON_VALUE
			],
		}
	return {"schema_version": 2, "products": PRODUCTS, "doctypes": doctypes}


@lru_cache(maxsize=1)
def cached_schema():
	"""Return the process-wide authoring schema. Callers must not mutate it."""
	return build_schema()
