"""The Part Number Builder's Dry/Wet section follows Environment Rating codes when they are re-assigned."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

CODES = {"Dry": "20", "Damp": "54", "Wet": "67"}


class Row(Record):
	__setattr__ = dict.__setitem__


class Template(Record):
	__setattr__ = dict.__setitem__

	def append(self, field, value):
		self.setdefault(field, []).append(Row(value))

	def remove(self, row):
		self["part_number_builder"].remove(row)


def template(environments, rows):
	return Template(
		allowed_options=[
			Record(option_type="Environment Rating", environment_rating=name, is_active=1)
			for name in environments
		],
		part_number_builder=[
			Row(
				section_name=section,
				section_order=order,
				option_code=code,
				option_label=label,
				option_order=i,
			)
			for i, (section, order, code, label) in enumerate(rows, start=1)
		],
	)


def section(doc, name="Dry/Wet"):
	return [(r.option_label, r.option_code) for r in doc.part_number_builder if r.section_name == name]


class EnvironmentSection(unittest.TestCase):
	def sync(self, doc):
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		path = ROOT + ".doctype.ill_fixture_template.ill_fixture_template"
		with load_service(path, {"frappe.model.document": document}) as (module, frappe):
			frappe.get_cached_doc = lambda doctype, name: Record(code=CODES[name], label=name)
			frappe.get_all.return_value = list(CODES.values())
			return module.sync_environment_section(doc)

	def test_io_codes_become_ip_codes_and_new_ratings_are_added(self):
		doc = template(
			["Dry", "Wet", "Damp"],
			[("Series", 1, "SH01", "St. Helens"), ("Dry/Wet", 2, "I", "Dry"), ("Dry/Wet", 2, "O", "Wet")],
		)
		self.assertTrue(self.sync(doc))
		self.assertEqual(section(doc), [("Dry", "20"), ("Wet", "67"), ("Damp", "54")])
		self.assertEqual(section(doc, "Series"), [("St. Helens", "SH01")])
		orders = [r.option_order for r in doc.part_number_builder if r.section_name == "Dry/Wet"]
		self.assertEqual(orders, [2, 3, 4])  # appended after the section's existing options

	def test_rows_for_codes_no_rating_uses_are_dropped_and_manual_rows_kept(self):
		doc = template(
			["Dry", "Wet"],
			[
				("Dry/Wet", 2, "I", "Indoor"),
				("Dry/Wet", 2, "O", "Outdoor"),
				("Dry/Wet", 2, "20", "Dry location"),
			],
		)
		self.assertTrue(self.sync(doc))
		self.assertEqual(section(doc), [("Dry location", "20"), ("Wet", "67")])

	def test_a_current_section_is_left_alone(self):
		doc = template(["Dry", "Wet"], [("Dry/Wet", 2, "20", "Dry"), ("Dry/Wet", 2, "67", "Wet")])
		self.assertFalse(self.sync(doc))
		self.assertEqual(section(doc), [("Dry", "20"), ("Wet", "67")])


class ExistingSites(unittest.TestCase):
	def test_patch_saves_each_template_whose_section_changed_once(self):
		docs = {name: MagicMock(name=name) for name in ("FT-A", "FT-B", "FT-C")}
		changed = {"FT-A": True, "FT-B": False}

		def sync(doc):
			if doc is docs["FT-C"]:
				raise ValueError("broken template")
			return changed[next(name for name, value in docs.items() if value is doc)]

		helper = types.ModuleType("ill_fixture_template")
		helper.sync_environment_section = sync
		module_path = ROOT + ".doctype.ill_fixture_template.ill_fixture_template"
		with load_service(
			"illumenate_lighting.patches.sync_environment_codes_in_part_number_builder", {module_path: helper}
		) as (patch, frappe):
			frappe.get_all.return_value = ["FT-B", "FT-A", "FT-A", "FT-C"]
			frappe.get_doc.side_effect = lambda doctype, name: docs[name]
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			patch.execute()
		docs["FT-A"].save.assert_called_once_with(ignore_permissions=True)
		docs["FT-B"].save.assert_not_called()
		frappe.log_error.assert_called_once()
		frappe.db.commit.assert_called_once()


if __name__ == "__main__":
	unittest.main()
