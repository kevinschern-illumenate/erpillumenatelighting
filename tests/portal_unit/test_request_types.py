"""Desk request types drive the portal form, and their mandatory fields are enforced (DESK-7)."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

PHOTOMETRIC = Record(
	name="Photometric Layout",
	custom_fields=[
		Record(
			field_key="ceiling_height", label="Ceiling height", fieldtype="Float", mandatory=1, sort_order=2
		),
		Record(field_key="dimmed", label="Dimmed", fieldtype="Check", mandatory=1, sort_order=1),
		Record(field_key="notes", label="Notes", fieldtype="Data", mandatory=0, sort_order=3),
	],
)


def service():
	return load_service(ROOT + ".api.document_requests")


def prepare(frappe, inserted):
	frappe.session = Record(user="dealer@acme.test")
	frappe.db.get_value.return_value = "Photometric Layout"
	frappe.db.exists.return_value = True
	frappe.get_doc.return_value = PHOTOMETRIC
	doc = Record(custom_field_values=[], flags=Record())
	doc.append = lambda field, row: doc.custom_field_values.append(Record(row)) or doc.custom_field_values[-1]
	doc.insert = lambda **kw: inserted.append(doc)
	frappe.new_doc = MagicMock(return_value=doc)
	return doc


class MandatoryFields(unittest.TestCase):
	def test_a_missing_mandatory_value_is_refused(self):
		with service() as (module, frappe):
			inserted = []
			prepare(frappe, inserted)
			for values in ({}, {"ceiling_height": "  "}, {"ceiling_height": None}):
				with self.subTest(values=values), self.assertRaisesRegex(ValueError, "Ceiling height"):
					module.create_portal_document_request(
						request_type="Photometric Layout", description="Layout", custom_fields=values
					)
			self.assertEqual(inserted, [])

	def test_zero_and_unticked_checks_are_answers(self):
		with service() as (module, frappe):
			inserted = []
			doc = prepare(frappe, inserted)
			module.create_portal_document_request(
				request_type="Photometric Layout",
				description="Layout",
				custom_fields={"ceiling_height": 0, "dimmed": 0},
			)
			self.assertEqual(len(inserted), 1)
			self.assertEqual([row.field_key for row in doc.custom_field_values], ["ceiling_height", "dimmed"])

	def test_legacy_drawing_requests_without_fields_still_work(self):
		with service() as (module, frappe):
			inserted = []
			prepare(frappe, inserted)
			module.create_portal_document_request(request_type="Photometric Layout", description="Layout")
			self.assertEqual(len(inserted), 1)


class FormDefinition(unittest.TestCase):
	def test_types_arrive_with_their_fields_in_order(self):
		with service() as (module, frappe):
			frappe.get_all.return_value = [
				Record(
					name="Photometric Layout",
					type_name="Photometric Layout",
					portal_label="Photometric",
					show_due_date_field=1,
				)
			]
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = PHOTOMETRIC
			(only,) = module.portal_request_types()
			self.assertEqual(only["label"], "Photometric")
			self.assertEqual([f["field_key"] for f in only["fields"]], ["dimmed", "ceiling_height", "notes"])
			self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["is_active"], 1)


if __name__ == "__main__":
	unittest.main()
