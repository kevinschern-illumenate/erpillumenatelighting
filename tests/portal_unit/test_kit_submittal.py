"""Configured Extrusion Kit lines fill their template's spec submittal from the stored build."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BUILD = {
	"part_number": "ILL-KIT-A-WH-FR-CL-FL-WH",
	"selections": {"kit_template": "KIT-A", "finish": "White", "endcap_style": "Flat"},
	"resolved_items": {
		"profile_spec": "PROFILE-SPEC",
		"solid_endcap_spec": "SOLID-SPEC",
		"mounting_spec": "CLIP-SPEC",
	},
}


def mapping(field, doctype, source, **extra):
	return {"pdf_field_name": field, "source_doctype": doctype, "source_field": source, **extra}


class KitSubmittal(unittest.TestCase):
	def generate(self, mappings, line=None):
		saved = MagicMock(return_value=Record(file_url="/private/files/kit.pdf"))
		stubs = {
			ROOT + ".api.exports": types.SimpleNamespace(_save_file_ignore_permissions=saved),
			ROOT + ".api.configuration_contract": types.SimpleNamespace(fingerprint=lambda value: "hash"),
		}
		records = {
			("ilL-Extrusion-Kit-Template", "KIT-A"): Record(
				doctype="ilL-Extrusion-Kit-Template",
				name="KIT-A",
				spec_submittal_template="/files/kit.pdf",
				beam_angle=120,
				series=None,
				webflow_product=None,
			),
			("ilL-Spec-Profile", "PROFILE-SPEC"): Record(width_mm=17.5),
			("ilL-Spec-Accessory", "SOLID-SPEC"): Record(item="CAP-SOLID"),
			("ilL-Spec-Accessory", "CLIP-SPEC"): Record(item="CLIP"),
			("ilL-Attribute-Finish", "White"): Record(finish_name="White", code="WH"),
		}
		line = line or Record(
			product_type="Extrusion Kit",
			kit_template="KIT-A",
			line_id="K1",
			ill_item_code=BUILD["part_number"],
			variant_selections=json.dumps(BUILD),
		)
		with load_service(ROOT + ".api.spec_submittal", stubs) as (service, frappe):
			frappe.get_doc.side_effect = lambda doctype, name: records[(doctype, name)]
			frappe.db.exists.side_effect = lambda doctype, name: (doctype, name) in records
			frappe.db.get_value.return_value = None
			frappe.get_all.return_value = mappings
			frappe.log_error = MagicMock()
			filled = {}

			def fill(template, values, **kwargs):
				filled.update(values, _template=template)
				return b"%PDF"

			service._fill_pdf_form_fields = fill
			result = service.generate_filled_kit_submittal(
				"KIT-A", _schedule_context=(Record(name="S"), Record(project_name="Lobby"), line)
			)
			return result, filled, saved

	def test_fields_come_from_the_template_resolved_specs_selections_and_line(self):
		result, filled, saved = self.generate(
			[
				mapping("beam", "ilL-Extrusion-Kit-Template", "beam_angle", suffix="°"),
				mapping("width", "ilL-Spec-Profile", "width_mm"),
				mapping("cap", "ilL-Spec-Accessory", "item", kit_component="Solid Endcap"),
				mapping("clip", "ilL-Spec-Accessory", "item", kit_component="Mounting"),
				mapping("finish", "ilL-Attribute-Finish", "code"),
				mapping("project", "ilL-Project", "project_name"),
				mapping("type", "ilL-Child-Fixture-Schedule-Line", "line_id"),
				mapping("part", "ilL-Child-Fixture-Schedule-Line", "line_id", webflow_field="part_number"),
			]
		)
		self.assertTrue(result["success"], result)
		self.assertEqual(filled["_template"], "/files/kit.pdf")
		self.assertEqual(filled["beam"], "120°")
		self.assertEqual(filled["width"], "17.5")
		self.assertEqual(filled["cap"], "CAP-SOLID")
		self.assertEqual(filled["clip"], "CLIP")
		self.assertEqual(filled["finish"], "WH")
		self.assertEqual(filled["project"], "Lobby")
		self.assertEqual(filled["type"], "K1")
		self.assertEqual(filled["part"], BUILD["part_number"])
		self.assertEqual(saved.call_args.args[2:4], ("ilL-Extrusion-Kit-Template", "KIT-A"))

	def test_unconfigured_kit_line_is_refused(self):
		line = Record(product_type="Extrusion Kit", kit_template="KIT-A", variant_selections=None)
		result, _filled, saved = self.generate(
			[mapping("beam", "ilL-Extrusion-Kit-Template", "beam_angle")], line
		)
		self.assertFalse(result["success"])
		self.assertIn("Configure this extrusion kit", result["message"])
		saved.assert_not_called()


if __name__ == "__main__":
	unittest.main()
