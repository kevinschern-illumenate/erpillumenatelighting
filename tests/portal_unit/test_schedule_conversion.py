"""Schedule → Quotation / Sales Order rows keep each line's Fixture Type and Section / Room."""

import types
import unittest
from unittest.mock import patch

from test_services import ROOT, Record, load_service


class Row(Record):
	__setattr__ = dict.__setitem__
	meta = types.SimpleNamespace(has_field=lambda fieldname: True)

	def set(self, key, value):
		self[key] = value


class Target:
	doctype = "Sales Order"

	def __init__(self):
		self.items = []

	def append(self, field, values):
		row = Row(values)
		getattr(self, field).append(row)
		return row


def controller():
	document = types.ModuleType("frappe.model.document")
	document.Document = object
	return load_service(
		ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule",
		{"frappe.model.document": document},
	)


class TapeNeonConversion(unittest.TestCase):
	def test_configured_tape_and_neon_rows_carry_fixture_type_and_location(self):
		with controller() as (module, _frappe):
			schedule = module.ilLProjectFixtureSchedule.__new__(module.ilLProjectFixtureSchedule)
			lines = [
				Row(
					name="ROW-1",
					idx=1,
					line_id="T1",
					location="Lobby",
					notes="Cove",
					qty=2,
					manufacturer_type="ILLUMENATE",
					product_type=family,
					configured_tape_neon="CTN-1",
					variant_selections=None,
				)
				for family in ("LED Tape", "LED Neon")
			]
			target = Target()

			def append_row(_schedule, target_doc, line, *_args, **_kwargs):
				target_doc.append("items", {"item_code": "TAPE-PN", "qty": line.qty})
				return True

			for line in lines:
				schedule.lines = [line]
				with (
					patch.object(
						module.ilLProjectFixtureSchedule, "_append_configured_tape_neon_row", append_row
					),
					patch.dict(
						"sys.modules",
						{
							ROOT + ".api.manufacturing_generator": types.SimpleNamespace(
								_create_or_get_bom=None,
								_create_or_get_configured_item=None,
								_update_fixture_links=None,
							)
						},
					),
				):
					counts = schedule.append_quote_lines(target)
				self.assertEqual(counts["tape_neon"], 1, line.product_type)
				row = target.items[-1]
				self.assertEqual(
					(row["ill_fixture_type"], row["ill_section_label"], row["additional_notes"]),
					("T1", "Lobby", "Cove"),
					line.product_type,
				)
				self.assertEqual(row["ill_schedule_line_id"], "ROW-1")


if __name__ == "__main__":
	unittest.main()
