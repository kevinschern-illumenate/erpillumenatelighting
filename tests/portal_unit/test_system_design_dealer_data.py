"""Dealer-entered design data on third-party schedule lines (System Designer D8, WP-1.6)."""

import types
import unittest
from unittest.mock import MagicMock

from test_product_finder_content import FakeDocument
from test_services import ROOT, Record, load_service

DEALER_DATA = ROOT + ".system_design.dealer_data"


class Rules(unittest.TestCase):
	def clean(self, protocols=("0-10V",), **values):
		with load_service(DEALER_DATA) as (module, frappe):
			frappe.db.exists.side_effect = lambda doctype, name: name in protocols
			return module.clean({field: values.get(field) for field in module.FIELDS})

	def test_blank_is_allowed(self):
		self.assertEqual(set(self.clean().values()), {None})

	def test_watts_range(self):
		for watts in (0, -1, 2000.5, "lots"):
			with self.subTest(watts=watts), self.assertRaises(ValueError):
				self.clean(watts_each=watts)
		self.assertEqual(self.clean(watts_each="2000")["watts_each"], 2000.0)
		self.assertEqual(self.clean(watts_each=0.5)["watts_each"], 0.5)

	def test_voltage_set_and_class(self):
		for volts in (12, 24, 48, 120, 208, 240, 277):
			self.assertEqual(self.clean(input_voltage_v=str(volts))["input_voltage_v"], volts)
		with self.assertRaises(ValueError):
			self.clean(input_voltage_v=36)
		self.assertEqual(self.clean(input_voltage_v=24)["voltage_class"], "Low Voltage")
		self.assertEqual(self.clean(input_voltage_v=277)["voltage_class"], "Line Voltage")
		self.assertEqual(self.clean(voltage_class="Line Voltage")["voltage_class"], "Line Voltage")
		with self.assertRaisesRegex(ValueError, "24 V is Low Voltage"):
			self.clean(input_voltage_v=24, voltage_class="Line Voltage")
		with self.assertRaises(ValueError):
			self.clean(voltage_class="Medium")

	def test_constant_current_needs_milliamps(self):
		with self.assertRaisesRegex(ValueError, "mA"):
			self.clean(third_party_drive="CC")
		with self.assertRaisesRegex(ValueError, "mA"):
			self.clean(third_party_drive="CC", third_party_ma=0)
		self.assertEqual(self.clean(third_party_drive="CC", third_party_ma="350")["third_party_ma"], 350.0)
		self.assertIsNone(self.clean(third_party_drive="CV", third_party_ma="350")["third_party_ma"])
		with self.assertRaises(ValueError):
			self.clean(third_party_drive="PWM")

	def test_dimming_must_exist(self):
		self.assertEqual(self.clean(third_party_dimming="0-10V")["third_party_dimming"], "0-10V")
		with self.assertRaises(ValueError):
			self.clean(third_party_dimming="Made Up")


class PortalLines(unittest.TestCase):
	def deps(self):
		return {
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda c: False),
			ROOT
			+ ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule": types.SimpleNamespace(
				has_permission=lambda *a: True
			),
			ROOT + ".portal.files": types.SimpleNamespace(finalize_spec=MagicMock()),
		}

	def add(self, **changes):
		with load_service(ROOT + ".api.portal", self.deps()) as (api, frappe):
			line = FakeDocument(idx=1)
			schedule = Record(
				name="S", status="DRAFT", is_locked=0, lines=[line], append=lambda *a: line, save=MagicMock()
			)
			frappe.get_doc.return_value = schedule
			frappe.db.exists.return_value = True
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			frappe.db.rollback = MagicMock()
			frappe.utils.strip_html = lambda value: value
			result = api.add_schedule_line(
				"S", {"line_id": "T1", "qty": 2, "manufacturer_type": "OTHER", **changes}
			)
			return result, line, schedule

	def update(self, line, **changes):
		with load_service(ROOT + ".api.portal", self.deps()) as (api, frappe):
			schedule = Record(name="S", status="DRAFT", is_locked=0, lines=[line], save=MagicMock())
			frappe.get_doc.return_value = schedule
			frappe.db.exists.return_value = True
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			frappe.db.rollback = MagicMock()
			frappe.utils.strip_html = lambda value: value
			return api.update_schedule_line("S", 0, changes), schedule

	def test_dealer_enters_third_party_data(self):
		result, line, schedule = self.add(
			watts_each="12", input_voltage_v="24", third_party_drive="CC", third_party_ma="700"
		)
		self.assertTrue(result["success"], result)
		self.assertEqual(
			(
				line.watts_each,
				line.input_voltage_v,
				line.voltage_class,
				line.third_party_drive,
				line.third_party_ma,
			),
			(12.0, 24.0, "Low Voltage", "CC", 700.0),
		)
		schedule.save.assert_called_once()

	def test_invalid_data_is_refused_before_saving(self):
		result, _line, schedule = self.add(watts_each="2500")
		self.assertFalse(result["success"])
		self.assertIn("2000", result["error"])
		schedule.save.assert_not_called()

	def test_partial_edit_is_validated_with_stored_values(self):
		line = FakeDocument(
			idx=1, manufacturer_type="OTHER", spec_sheet=None, third_party_drive="CC", third_party_ma=350.0
		)
		result, schedule = self.update(line, third_party_ma="")
		self.assertFalse(result["success"])
		schedule.save.assert_not_called()
		result, _ = self.update(line, watts_each="8")
		self.assertTrue(result["success"], result)
		self.assertEqual((line.watts_each, line.third_party_ma), (8.0, 350.0))

	def test_write_back_markers_are_not_dealer_editable(self):
		line = FakeDocument(idx=1, manufacturer_type="OTHER", spec_sheet=None, design_line_key="K1")
		result, _ = self.update(line, design_line_key="HACK", design_line_role="Wire", system_design="D")
		self.assertTrue(result["success"], result)
		self.assertEqual(line.design_line_key, "K1")
		self.assertNotIn("design_line_role", line)

	def test_illumenate_lines_ignore_dealer_data(self):
		line = FakeDocument(idx=1, manufacturer_type="ILLUMENATE")
		result, _ = self.update(line, watts_each="9999")
		self.assertTrue(result["success"], result)
		self.assertNotIn("watts_each", line)


if __name__ == "__main__":
	unittest.main()
