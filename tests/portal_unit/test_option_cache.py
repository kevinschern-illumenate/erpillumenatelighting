"""Configurator option projections are cached per catalog revision (plan 6.5)."""

import re
import types
import unittest
from pathlib import Path
from typing import ClassVar

from test_services import ROOT, Record, load_service


class FakeCache:
	def __init__(self):
		self.values = {}
		self.writes = 0

	def get_value(self, key):
		return self.values.get(key)

	def set_value(self, key, value, expires_in_sec=None):
		self.writes += 1
		self.values[key] = value

	def delete_value(self, key):
		self.values.pop(key, None)


def boundaries(state):
	return {
		ROOT + ".portal.site_flags": types.SimpleNamespace(option_projection_cache_enabled=lambda: state["enabled"]),
		ROOT + ".portal.product_finder.facts": types.SimpleNamespace(catalog_stamp=lambda: state["stamp"]),
	}


class OptionCache(unittest.TestCase):
	def run_cache(self, test, enabled=True):
		state = {"enabled": enabled, "stamp": "2026-11-01:0"}
		with load_service(ROOT + ".api.option_cache", boundaries(state)) as (cache_module, frappe):
			cache = FakeCache()
			frappe.cache = lambda: cache
			test(cache_module, frappe, cache, state)

	def test_a_projection_is_built_once_per_revision_and_handed_out_as_a_copy(self):
		def test(module, frappe, cache, state):
			builds = []

			def build():
				builds.append(1)
				return {"success": True, "options": {"ccts": [{"value": "3000K"}]}}

			first = module.cached_projection("tape_neon_init", "TPL", build)
			first["options"]["ccts"].clear()
			second = module.cached_projection("tape_neon_init", "TPL", build)
			self.assertEqual(len(builds), 1)
			self.assertEqual(second["options"]["ccts"], [{"value": "3000K"}], "a caller's edit never reaches the cache")
			module.cached_projection("tape_neon_init", "OTHER", build)
			self.assertEqual(len(builds), 2, "keyed per template")
			state["stamp"] = "2026-11-02:0"
			module.cached_projection("tape_neon_init", "TPL", build)
			self.assertEqual(len(builds), 3, "a catalog save starts a new revision")

		self.run_cache(test)

	def test_mapping_saves_and_site_flag_changes_start_a_new_revision(self):
		def test(module, frappe, cache, state):
			before = module.catalog_revision()
			module.invalidate(Record(doctype="ilL-Rel-Kit-Lens-Map"), "on_update")
			after_mapping = module.catalog_revision()
			self.assertNotEqual(before, after_mapping)
			frappe.conf["ill_portal_hero_image_first"] = False
			self.assertNotEqual(after_mapping, module.catalog_revision())
			frappe.conf["db_password"] = "secret"
			self.assertNotIn("secret", module.catalog_revision(), "only ill_* keys, and only as a hash")

		self.run_cache(test)

	def test_failures_are_never_cached(self):
		def test(module, frappe, cache, state):
			module.cached_projection("kit_init", "KIT", lambda: {"success": False, "error": "Kit template is not active"})
			self.assertEqual(cache.writes, 0)

		self.run_cache(test)

	def test_kill_switch_and_blank_template_read_live(self):
		def test(module, frappe, cache, state):
			builds = []
			for _ in range(2):
				module.cached_projection("kit_init", "KIT", lambda: builds.append(1) or {"success": True})
			self.assertEqual(len(builds), 2)
			self.assertEqual(cache.writes, 0)

		self.run_cache(test, enabled=False)

		def blank(module, frappe, cache, state):
			module.cached_projection("kit_init", "", lambda: {"success": True})
			self.assertEqual(cache.writes, 0)

		self.run_cache(blank)

	def test_hooks_invalidate_on_every_mapping_doctype(self):
		with load_service(ROOT + ".api.option_cache", boundaries({"enabled": True, "stamp": ""})) as (module, _frappe):
			mapping = module.MAPPING_DOCTYPES
		hooks = Path("illumenate_lighting/hooks.py").read_text()
		match = re.search(r"for _option_doctype in \(([^)]*)\):", hooks)
		self.assertIsNotNone(match)
		self.assertEqual(tuple(re.findall(r'"([^"]+)"', match.group(1))), mapping)
		self.assertIn("api.option_cache.invalidate", hooks)
		self.assertIn("product_finder.facts.invalidate", hooks, "templates/specs/attributes/publication keep their stamp hooks")

	def test_site_flag_is_on_unless_a_site_turns_it_off(self):
		with load_service(ROOT + ".portal.site_flags") as (flags, frappe):
			self.assertTrue(flags.option_projection_cache_enabled())
			frappe.conf["ill_option_projection_cache"] = 0
			self.assertFalse(flags.option_projection_cache_enabled())


class BulkLoads(unittest.TestCase):
	ATTRS: ClassVar[dict] = {
		"3000K": Record(name="3000K", code="30", kelvin=3000),
		"2700K": Record(name="2700K", code="27", kelvin=2700),
	}

	def attribute_rows(self, frappe):
		def get_all(doctype, filters=None, fields=None, **kwargs):
			return [self.ATTRS[name] for name in filters["name"][1] if name in self.ATTRS]

		frappe.get_all.side_effect = get_all

	def test_tape_attribute_options_read_once_and_keep_shape_and_order(self):
		with load_service(ROOT + ".api.tape_neon_configurator") as (service, frappe):
			self.attribute_rows(frappe)
			offerings = [Record(cct="3000K"), Record(cct="2700K"), Record(cct="9999K"), Record(cct=None)]
			collected = service._collect_attribute_options(offerings, "cct", "ilL-Attribute-CCT", ["name", "code", "kelvin"])
			resolved = service._resolve_attribute_list("ilL-Attribute-CCT", {"3000K", "2700K", ""}, ["name", "code", "kelvin"])
			self.assertEqual(frappe.get_all.call_count, 2)
			frappe.db.get_value.assert_not_called()
		expected = [
			{"value": "2700K", "label": "2700K", "code": "27", "kelvin": 2700},
			{"value": "3000K", "label": "3000K", "code": "30", "kelvin": 3000},
		]
		self.assertEqual(collected, expected)
		self.assertEqual(resolved, expected)

	def test_tape_template_init_is_served_from_the_projection_cache(self):
		calls = []

		def cached_projection(kind, template, build):
			calls.append((kind, template))
			return {"success": True, "cached": True}

		extras = {ROOT + ".api.option_cache": types.SimpleNamespace(cached_projection=cached_projection)}
		with load_service(ROOT + ".api.tape_neon_configurator", extras) as (service, _frappe):
			self.assertEqual(service.get_tape_neon_template_init("TN-1"), {"success": True, "cached": True})
			self.assertEqual(service.get_tape_neon_template_init(""), {"success": False, "error": "template_code is required"})
		self.assertEqual(calls, [("tape_neon_init", "TN-1")])

	def test_kit_options_and_lens_cascade_use_bulk_reads(self):
		class Template(Record):
			def get_allowed_values(self, option_type):
				return {"Finish": ["White", "Black"], "Lens Appearance": ["Frosted", "Clear", "Opal"], "Mounting Method": []}[option_type]

			def get_default_value(self, option_type):
				return None

		attrs = {
			"White": Record(name="White", code="WH"),
			"Black": Record(name="Black", code="BK"),
			"Frosted": Record(name="Frosted", code="FR"),
			"Clear": Record(name="Clear", code="CL"),
		}
		maps = [
			Record(name="M1", lens_item="LENS-FR", lens_appearance="Frosted"),
			Record(name="M2", lens_item="LENS-CL", lens_appearance="Clear"),
			Record(name="M3", lens_item="LENS-OPAL-OLD", lens_appearance="Opal"),
		]
		mounting = types.SimpleNamespace(methods_without_accessory=lambda methods: set(), needs_accessory=lambda method: True)
		extras = {ROOT + ".api.mounting_accessory": mounting}
		with load_service(ROOT + ".api.extrusion_kit_configurator", extras) as (service, frappe):
			frappe.db.get_all.side_effect = lambda doctype, filters=None, pluck=None, **kwargs: [
				code for code in filters["name"][1] if code.endswith("-OLD")
			]
			frappe.db.sql.side_effect = lambda query, values: [(n,) for n in values["names"] if n.endswith("-OLD")]

			def get_all(doctype, filters=None, fields=None, **kwargs):
				if doctype == "ilL-Rel-Kit-Lens-Map":
					return [m for m in maps if m.lens_appearance in filters["lens_appearance"][1]]
				if doctype == "ilL-Rel-Kit-Profile-Map":
					return []
				if isinstance(filters, dict) and "name" in filters:
					return [attrs[n] for n in filters["name"][1] if n in attrs]
				return []

			frappe.get_all.side_effect = get_all
			template = Template(
				name="KIT", template_code="K", template_name="Kit", series=None, profile_stock_length_mm=0,
				lens_stock_length_mm=0, solid_endcap_qty=0, feed_through_endcap_qty=0, mounting_accessory_qty=0,
				base_price_msrp=0, default_profile_spec=None, default_lens_spec=None, spec_sheet=None, image="/k.png",
			)
			service.kit_template_image = lambda t: t.image
			service.kit_spec_sheet_data = lambda t: []
			frappe.get_all.reset_mock()
			init = service._build_init_response(template)
			self.assertEqual([o["value"] for o in init["options"]["finish"]], ["Black", "White"], "sorted by label as before")
			self.assertEqual(init["options"]["lens_appearance"][0], {"value": "Clear", "label": "Clear", "code": "CL"})
			frappe.db.get_value.assert_not_called()

			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = template
			frappe.get_all.reset_mock()
			cascade = service.get_kit_cascading_options("KIT", finish="White")
			lens_calls = [c for c in frappe.get_all.call_args_list if c.args[0] in ("ilL-Rel-Kit-Lens-Map", "ilL-Attribute-Lens Appearance")]
			self.assertEqual(len(lens_calls), 2, "one map query and one attribute query, not two per lens")
		self.assertEqual(
			[o["value"] for o in cascade["available_lens_appearances"]], ["Frosted", "Clear"],
			"template order kept; a lens whose only map uses a disabled Item is dropped",
		)

	def test_sheet_templates_read_their_specs_in_one_query_in_row_order(self):
		gallery = types.SimpleNamespace(_fetch_webflow_gallery=lambda products: {})
		cache = types.SimpleNamespace(cached_projection=lambda kind, template, build: build())
		extras = {
			"illumenate_lighting.templates.pages.configure": gallery,
			ROOT + ".api.option_cache": cache,
		}
		specs = {
			"S-B": Record(name="S-B", item="PANEL-B"),
			"S-A": Record(name="S-A", item="PANEL-A"),
		}
		with load_service(ROOT + ".api.portal", extras) as (module, frappe):
			frappe.db.get_all.side_effect = lambda *args, **kwargs: []
			frappe.db.sql.side_effect = lambda *args, **kwargs: []

			def get_all(doctype, filters=None, fields=None, **kwargs):
				if doctype == "ilL-LED-Sheet-Template":
					return [Record(name="SHEET", template_name="Sheet", image=None, webflow_product=None)]
				return [specs[n] for n in filters["name"][1] if n in specs]

			frappe.get_all.side_effect = get_all
			frappe.get_doc.return_value = Record(
				allowed_specs=[
					Record(spec="S-B", is_active=1), Record(spec="S-OFF", is_active=0),
					Record(spec="S-GONE", is_active=1), Record(spec="S-A", is_active=1),
				],
				allowed_options=[],
			)
			result = module._cached_led_sheet_templates()
			spec_calls = [c for c in frappe.get_all.call_args_list if c.args[0] == "ilL-Spec-LED-Sheet"]
			self.assertEqual(len(spec_calls), 1)
			self.assertFalse([c for c in frappe.db.get_value.call_args_list if c.args and c.args[0] == "ilL-Spec-LED-Sheet"])
		self.assertEqual([s.name for s in result["templates"][0]["allowed_specs"]], ["S-B", "S-A"])


if __name__ == "__main__":
	unittest.main()
