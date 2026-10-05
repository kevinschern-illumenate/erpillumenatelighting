"""Local rehearsal with isolated synthetic catalogs; never production acceptance.

All seeded records and committed imports are removed explicitly. The fixtures use
normal document validation and the service uses a Catalog Publisher's permissions.
"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.api import catalog_builder as service
from illumenate_lighting.illumenate_lighting.catalog_authoring.catalog import identity
from illumenate_lighting.illumenate_lighting.catalog_authoring.schema import cached_schema


class CatalogRehearsalFixture:
	def __init__(self):
		self.schema = cached_schema()
		self.prefix = "ZZTEST-CB5-" + frappe.generate_hash(length=8)
		self.seeds = []
		self.created = []
		self.user = self.prefix.lower() + "@example.invalid"
		self.examples = json.loads(
			(
				Path(__file__).resolve().parents[3] / "tools/yaml_builder_ui/src/catalog-examples.json"
			).read_text()
		)
		self.seed(
			"User",
			email=self.user,
			first_name="Catalog rehearsal",
			send_welcome_email=0,
			user_type="System User",
			roles=[{"role": "ilL Catalog Publisher"}],
		)

	def seed(self, doctype, **values):
		doc = frappe.get_doc({"doctype": doctype, **values}).insert()
		self.seeds.append((doctype, doc.name))
		return doc.name

	def catalog(self, family):
		frappe.set_user("Administrator")
		source = self.examples[family]
		prefix = f"{self.prefix}-{family[:2]}"
		names = {}
		for doctype, values in source["external_links"].items():
			for value in values:
				name = f"{prefix}-{value}"
				code = self.prefix[-8:] + str(len(self.seeds))
				if doctype == "UOM":
					# Configurators recognize physical unit names; an arbitrary prefixed
					# unit is not equivalent to Meter or Nos. Never change an existing UOM.
					actual = frappe.db.exists(doctype, value) or self.seed(
						doctype, uom_name=value, must_be_whole_number=int(value == "Nos")
					)
				elif doctype == "Item Group":
					actual = self.seed(
						doctype,
						item_group_name=name,
						is_group=0,
						parent_item_group=frappe.db.get_value("Item Group", {"is_group": 1}, "name"),
					)
				elif doctype == "ilL-Spec-Driver":
					item = self.seed(
						"Item",
						item_code=name,
						item_name=name,
						item_group=names["Item Group", "Products"],
						stock_uom=names["UOM", "Nos"],
					)
					actual = self.seed(
						doctype,
						item=item,
						outputs_count=1,
						independent_outputs_count=1,
						max_wattage=96,
						max_wattage_per_output=96,
						usable_load_factor=0.8,
						voltage_output=names["ilL-Attribute-Output Voltage", "24V DC"],
						output_protocol=names["ilL-Attribute-Dimming Protocol", "PWM"],
					)
				else:
					meta = self.schema["doctypes"][doctype]
					field = (
						meta["autoname"].removeprefix("field:") if meta["autoname"] != "prompt" else "name"
					)
					row = {"code": code, field: name}
					for required in meta["fields"]:
						if required.get("reqd") and required["fieldtype"] == "Data":
							row.setdefault(required["fieldname"], code)
					row.update(
						{
							"ilL-Attribute-CCT": {"kelvin": 3000, "is_active": 1},
							"ilL-Attribute-Dimming Protocol": {
								"protocol": "DMX512" if value == "DMX" else value
							},
							"ilL-Attribute-LED Package": {"spectrum_type": "Static White"},
							"ilL-Attribute-Output Level": {"value": 400},
							"ilL-Attribute-SDCM": {"sdcm": int(self.prefix[-6:], 36) % 10000000},
							"ilL-Attribute-Output Voltage": {"dc_voltage": "24V"},
						}.get(doctype, {})
					)
					actual = self.seed(doctype, **row)
				names[doctype, value] = actual

		for doctype, rows in source["records"].items():
			for row in rows:
				old = identity(doctype, row, self.schema)
				if old:
					names[doctype, old] = f"{prefix}-{old}"

		def rename(doctype, row):
			row = deepcopy(row)
			meta = self.schema["doctypes"][doctype]
			if any(field["fieldname"] == "is_active" for field in meta["fields"]):
				row["is_active"] = 1
			autoname = meta.get("autoname", "")
			if autoname.startswith("field:"):
				key = autoname[6:]
				row[key] = names.get((doctype, str(row.get(key))), row.get(key))
			elif autoname == "prompt":
				row["name"] = names.get((doctype, row.get("name")), row.get("name"))
			for field in meta["fields"]:
				key, kind = field["fieldname"], field["fieldtype"]
				if kind in {"Table", "Table MultiSelect"}:
					if key in row:
						row[key] = [rename(field["options"], child) for child in row[key]]
				elif kind in {"Link", "Dynamic Link"} and key in row:
					target = field["options"] if kind == "Link" else row.get(field["options"])
					row[key] = names.get((target, str(row[key])), row[key])
			if doctype == "ilL-Attribute-Series":
				row["code"] = prefix
			if doctype == "ilL-Spec-Profile":
				row["variant_code"] = frappe.db.get_value(
					"ilL-Attribute-Finish", names["ilL-Attribute-Finish", "White"], "code"
				)
			if (
				doctype == "Item"
				and family in {"fixture", "tape", "neon"}
				and row["item_code"].endswith("DEMO-LEADER")
			):
				row["stock_uom"] = names["UOM", "Meter"]
			for key in ("family", "profile_family", "default_profile_family"):
				if row.get(key) == "DEMO":
					row[key] = prefix
			if doctype == "ilL-Webflow-Product":
				row["product_slug"] = prefix.lower()
			return row

		# Format names depend on renamed link fields, including other format names.
		for _ in range(sum(map(len, source["records"].values()))):
			changed = False
			for doctype, rows in source["records"].items():
				if not self.schema["doctypes"][doctype]["autoname"].startswith("format:"):
					continue
				for row in rows:
					key = doctype, identity(doctype, row, self.schema)
					name = identity(doctype, rename(doctype, row), self.schema)
					changed |= names[key] != name
					names[key] = name
			if not changed:
				break
		catalog = {
			**source,
			"series_name": prefix,
			"records": {dt: [rename(dt, row) for row in rows] for dt, rows in source["records"].items()},
			"external_links": {
				dt: [names[dt, name] for name in values] for dt, values in source["external_links"].items()
			},
		}
		if family == "led-sheet":
			price_list = frappe.db.exists("Price List", "Standard Selling") or self.seed(
				"Price List", price_list_name="Standard Selling", selling=1, currency="USD"
			)
			currency = frappe.db.get_value("Price List", price_list, "currency")
			catalog["external_links"].update({"Price List": [price_list], "Currency": [currency]})
			catalog["records"]["Item Price"] = [
				{
					"item_code": row["item_code"],
					"price_list": price_list,
					"currency": currency,
					"uom": row["stock_uom"],
					"price_list_rate": 2,
				}
				for row in catalog["records"]["Item"]
				if row["item_code"].endswith(("LEADER", "JUMPER"))
			]
		# The Check endpoint rolls back the caller's transaction; fixtures must be durable first.
		frappe.db.commit()  # nosemgrep
		frappe.set_user(self.user)
		return catalog

	def run(self, catalog, digest=None):
		result = service.check(catalog) if digest is None else service.import_catalog(catalog, digest)
		self.created.extend((row["doctype"], row["name"]) for row in result["results"] if row["name"])
		return result

	def cleanup(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in frappe.get_all(service.AUDIT, filters={"user": self.user}, pluck="name"):
			frappe.delete_doc(service.AUDIT, name, force=True)
		for doctype, name in reversed(self.seeds + self.created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=True)
		# Service commits require durable cleanup of this fixture's exact records.
		frappe.db.commit()  # nosemgrep
		frappe.clear_cache(user=self.user)


class TestCatalogRehearsal(IntegrationTestCase):
	def test_48_record_fixture_catalog(self):
		fixtures, catalogs = [], []
		try:
			for _ in range(2):
				frappe.set_user("Administrator")
				fixture = CatalogRehearsalFixture()
				fixtures.append(fixture)
				catalogs.append(fixture.catalog("fixture"))
			catalog = deepcopy(catalogs[0])
			for doctype, rows in catalogs[1]["records"].items():
				catalog["records"].setdefault(doctype, []).extend(rows)
			for doctype, names in catalogs[1]["external_links"].items():
				catalog["external_links"][doctype] = sorted(
					set(catalog["external_links"].get(doctype, []) + names)
				)
			checked = fixture.run(catalog)
			self.assertEqual(checked["status"], "Passed", checked)
			imported = fixture.run(catalog, checked["catalog_hash"])
			self.assertEqual(imported["status"], "Imported", imported)
			self.assertEqual(imported["summary"]["created"], 48)
			print(
				"Catalog rehearsal (48 records): Check",
				checked["summary"]["duration_ms"],
				"ms; Import",
				imported["summary"]["duration_ms"],
				"ms",
			)
		finally:
			for fixture in reversed(fixtures):
				fixture.cleanup()

	def test_final_batch_failure_leaves_no_earlier_records(self):
		from illumenate_lighting.illumenate_lighting.doctype.ill_rel_kit_endcap_map.ill_rel_kit_endcap_map import (
			ilLRelKitEndcapMap,
		)

		frappe.set_user("Administrator")
		fixture = CatalogRehearsalFixture()
		try:
			catalog = fixture.catalog("extrusion-kit")
			checked = fixture.run(catalog)
			self.assertEqual(checked["status"], "Passed", checked)

			def changed_site_validation(doc):
				if doc.endcap_type == "Feed-Through":
					frappe.throw("Final batch rehearsal failure")

			with patch.object(ilLRelKitEndcapMap, "validate", changed_site_validation, create=True):
				result = fixture.run(catalog, checked["catalog_hash"])
			self.assertEqual(result["status"], "Rolled Back", result)
			self.assertEqual(result["results"][-1]["status"], "error")
			self.assertTrue(all(row["status"] == "created" for row in result["results"][:-1]))
			self.assertEqual(result["summary"]["created"], 0)
			for row in checked["results"]:
				self.assertFalse(frappe.db.exists(row["doctype"], row["name"]), row)
		finally:
			fixture.cleanup()

	def test_501_records_are_refused_before_any_catalog_insert(self):
		frappe.set_user("Administrator")
		fixture = CatalogRehearsalFixture()
		try:
			catalog = fixture.catalog("extrusion-kit")
			catalog["records"] = {"Brand": [{"brand": f"{fixture.prefix}-{i}"} for i in range(501)]}
			result = fixture.run(catalog)
			self.assertEqual((result["status"], result["stage"]), ("Refused", "shape"))
			self.assertEqual(result["summary"]["records"], 501)
			self.assertFalse(result["results"])
			self.assertFalse(frappe.db.exists("Brand", {"name": ["like", fixture.prefix + "%"]}))
		finally:
			fixture.cleanup()

	def test_every_family_checks_imports_and_opens_as_catalog_publisher(self):
		for family in cached_schema()["products"]:
			with self.subTest(family=family):
				frappe.set_user("Administrator")
				fixture = CatalogRehearsalFixture()
				try:
					catalog = fixture.catalog(family)
					checked = fixture.run(catalog)
					self.assertEqual(checked["status"], "Passed", checked)
					for row in checked["results"]:
						self.assertFalse(frappe.db.exists(row["doctype"], row["name"]), row)
					imported = fixture.run(catalog, checked["catalog_hash"])
					self.assertEqual(imported["status"], "Imported", imported)
					for row in imported["results"]:
						doc = frappe.get_doc(row["doctype"], row["name"])
						doc.check_permission("read")
					self.assertEqual(
						imported["summary"]["created"], sum(map(len, catalog["records"].values()))
					)
					resolved = resolve_catalog(catalog)
					self.assertTrue(resolved.get("is_valid", resolved.get("success")), resolved)
				finally:
					fixture.cleanup()


def resolve_catalog(catalog):
	"""Exercise imported records through the real configurator, without saving a build."""
	from illumenate_lighting.illumenate_lighting.api import (
		configurator_engine,
		driver_controller_configurator,
		extrusion_kit_configurator,
		led_sheet_configurator,
		tape_neon_configurator,
	)

	family, records = catalog["product_type"], catalog["records"]
	template_type = cached_schema()["products"][family]["template"]
	template = records[template_type][0]["template_code"]
	external = catalog["external_links"]
	if family in {"driver", "controller"}:
		validate = getattr(driver_controller_configurator, f"validate_{family}_configuration")
		return validate(
			records["ilL-Webflow-Product"][0]["product_slug"], json.dumps({"wattage": "96", "channels": "4"})
		)
	if family == "extrusion-kit":
		return extrusion_kit_configurator.validate_kit_configuration(
			json.dumps(
				{
					"kit_template": template,
					"finish": external["ilL-Attribute-Finish"][0],
					"lens_appearance": external["ilL-Attribute-Lens Appearance"][0],
					"mounting_method": external["ilL-Attribute-Mounting Method"][0],
					"endcap_style": external["ilL-Attribute-Endcap Style"][0],
					"endcap_color": external["ilL-Attribute-Endcap Color"][0],
				}
			)
		)
	if family == "led-sheet":
		return led_sheet_configurator.validate_sheet_configuration(
			template, coverage_width_ft=1, coverage_height_ft=1, include_power_supply=0
		)
	if family in {"tape", "neon"}:
		return tape_neon_configurator.validate_tape_neon_template_config(
			template,
			json.dumps(
				{
					"cct": external["ilL-Attribute-CCT"][0],
					"output_level": external["ilL-Attribute-Output Level"][0],
					"environment_rating": external["ilL-Attribute-Environment Rating"][0],
					"include_power_supply": False,
					"tape_length_value": 12,
					"tape_length_unit": "in",
				}
			),
			segments_json=json.dumps(
				[{"ip_rating": "IP67", "fixture_length_value": 12, "fixture_length_unit": "in"}]
			)
			if family == "neon"
			else None,
			_skip_record_creation=True,
		)
	return configurator_engine.validate_and_quote(
		fixture_template_code=template,
		finish_code=external["ilL-Attribute-Finish"][0],
		lens_appearance_code=external["ilL-Attribute-Lens Appearance"][0],
		mounting_method_code=external["ilL-Attribute-Mounting Method"][0],
		endcap_style_start_code=external["ilL-Attribute-Endcap Style"][0],
		endcap_style_end_code=external["ilL-Attribute-Endcap Style"][0],
		endcap_color_code=external["ilL-Attribute-Endcap Color"][0],
		power_feed_type_code=external["ilL-Attribute-Power Feed Type"][0],
		environment_rating_code=external["ilL-Attribute-Environment Rating"][0],
		tape_offering_id=records["ilL-Fixture-Template"][0]["allowed_tape_offerings"][0]["tape_offering"],
		requested_overall_length_mm=1000,
		include_power_supply=False,
		_skip_record_creation=True,
	)
