"""The Light Source row of a fixture template's Components (owner, 2026-11-13)."""

import unittest
from types import SimpleNamespace

from test_services import ROOT, load_service


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class Template:
	doctype = "ilL-Fixture-Template"

	def __init__(self, **values):
		self.values = values

	def get(self, key):
		return self.values.get(key)

	def set(self, key, rows):
		self.values[key] = [row if isinstance(row, Row) else Row(row) for row in rows]


TABLES = {
	"ilL-Rel-Tape Offering": ["SPEC-A", "SPEC-A", None],
	"ilL-Child-Tape-Neon-Allowed-Spec": ["led-hd-sw", "lil-sw-led"],
	"ilL-Child-Webflow-Brand-Target": ["led-hd-sw"],
}


class LightSource(unittest.TestCase):
	def module(self, tables=TABLES, names=None):
		context = load_service(ROOT + ".template_light_source")
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.calls = []
		templates = names or {
			"led-hd-sw": "High Density Static White LED Tape",
			"lil-sw-led": "Lil Static White LED Tape",
		}

		def get_all(doctype, filters=None, pluck=None, fields=None):
			self.calls.append((doctype, filters))
			if doctype == "ilL-Tape-Neon-Template":
				return [{"name": n, "template_name": templates[n]} for n in filters["name"][1]]
			return list(tables.get(doctype, []))

		frappe.get_all = get_all
		return module

	def template(self, components=None):
		return Template(
			target_brands=[SimpleNamespace(get={"brand": "illumenate", "enabled": 1}.get)],
			allowed_tape_offerings=[Row(tape_offering="O1"), Row(tape_offering="O2")],
			kit_components=components or [],
		)

	def test_the_tape_template_for_the_fixtures_brand_names_the_light_source(self):
		module = self.module()
		self.assertEqual(module.names(self.template()), ["High Density Static White LED Tape"])
		brand_call = next(c for c in self.calls if c[0] == "ilL-Child-Webflow-Brand-Target")
		self.assertEqual(brand_call[1]["brand"], ["in", ["illumenate"]])

	def test_without_a_same_brand_template_every_template_counts(self):
		module = self.module(tables={**TABLES, "ilL-Child-Webflow-Brand-Target": []})
		self.assertEqual(
			module.names(self.template()),
			["High Density Static White LED Tape", "Lil Static White LED Tape"],
		)

	def test_the_light_source_row_comes_first_and_is_rebuilt(self):
		module = self.module()
		template = self.template(
			[
				Row(component_type="Profile", component_item="PRF-1", idx=1),
				Row(component_type="Light Source", component_description="Old name", idx=2),
				Row(component_type="Lens", component_item="LNS-1", idx=3),
			]
		)
		module.refresh(template)
		rows = template.get("kit_components")
		self.assertEqual(
			[
				(r.component_type, r.get("component_item"), r.get("component_description"), r.idx)
				for r in rows
			],
			[
				("Light Source", None, "High Density Static White LED Tape", 1),
				("Profile", "PRF-1", None, 2),
				("Lens", "LNS-1", None, 3),
			],
		)
		self.assertEqual(rows[0].webflow_title, "High Density Static White LED Tape")

	def test_no_offerings_no_light_source(self):
		module = self.module()
		template = Template(allowed_tape_offerings=[], kit_components=[Row(component_type="Light Source")])
		module.refresh(template)
		self.assertEqual(template.get("kit_components"), [])

	def test_other_templates_are_left_alone(self):
		module = self.module()
		template = self.template([Row(component_type="Light Source")])
		template.doctype = "ilL-Extrusion-Kit-Template"
		module.refresh(template)
		self.assertEqual(len(template.get("kit_components")), 1)


if __name__ == "__main__":
	unittest.main()
