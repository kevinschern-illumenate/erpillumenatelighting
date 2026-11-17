"""driver_catalog bulk loading returns exactly what the per-row lookup did — plan item 1.7."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

DRIVERS = {
	"DRV-A": dict(item="ITEM-A", cost=10, voltage_output="24V", output_type="Constant Voltage", output_protocol="PWM",
		max_wattage=96, max_wattage_per_output=96, usable_load_factor=0.8, outputs_count=1,
		independent_outputs_count=None, protocols=["0-10V", "DALI"]),
	"DRV-B": dict(item="ITEM-B", cost=20, voltage_output="24V", output_type="Constant Voltage", output_protocol="PWM",
		max_wattage=192, max_wattage_per_output=96, usable_load_factor=0.8, outputs_count=2,
		independent_outputs_count=2, protocols=["TRIAC", ""]),
	"DRV-DISABLED": dict(item="ITEM-OFF", cost=5, voltage_output="24V", output_type="Constant Voltage",
		output_protocol="PWM", max_wattage=60, max_wattage_per_output=60, usable_load_factor=0.8, outputs_count=1,
		independent_outputs_count=1, protocols=["ELV"]),
	"DRV-NOITEM": dict(item=None, cost=1, voltage_output="24V", output_type="Constant Voltage", output_protocol="PWM",
		max_wattage=60, max_wattage_per_output=60, usable_load_factor=0.8, outputs_count=1,
		independent_outputs_count=1, protocols=["MLV"]),
	"DRV-12V": dict(item="ITEM-12", cost=7, voltage_output="12V", output_type="Constant Voltage", output_protocol="PWM",
		max_wattage=60, max_wattage_per_output=60, usable_load_factor=0.8, outputs_count=1,
		independent_outputs_count=1, protocols=["0-10V"]),
	"DRV-TW": dict(item="ITEM-TW", cost=9, voltage_output="24V", output_type="Constant Voltage", output_protocol="PWM",
		max_wattage=96, max_wattage_per_output=48, usable_load_factor=0.8, outputs_count=2,
		independent_outputs_count=0, protocols=["DALI"]),
	"DRV-A-DUP": dict(item="ITEM-A", cost=11, voltage_output="24V", output_type="Constant Voltage",
		output_protocol="PWM", max_wattage=96, max_wattage_per_output=96, usable_load_factor=0.8, outputs_count=1,
		independent_outputs_count=1, protocols=["DALI"]),
}
DISABLED = {"ITEM-OFF": 1}


def _doc(name):
	spec = DRIVERS.get(name)
	if spec is None:
		raise LookupError(f"ilL-Spec-Driver {name} not found")
	data = {k: v for k, v in spec.items() if k != "protocols"}
	data["name"] = name
	data["input_protocols"] = [Record(protocol=p) for p in spec["protocols"]]
	return Record(data)


def _get_all(doctype, filters=None, fields=None, **kwargs):
	names = (filters or {}).get("name", ["in", []])[1] if doctype != "ilL-Child-Driver-Input-Protocol" else None
	if doctype == "ilL-Spec-Driver":
		return [Record({f: _doc(n).get(f) for f in fields}) for n in names if n in DRIVERS]
	if doctype == "ilL-Child-Driver-Input-Protocol":
		parents = filters["parent"][1]
		return [Record(parent=n, protocol=p) for n in parents if n in DRIVERS for p in DRIVERS[n]["protocols"]]
	if doctype == "Item":
		return [Record(name=n, disabled=DISABLED.get(n, 0)) for n in names]
	raise AssertionError(doctype)


def legacy_protocols(rows):
	protocols = set()
	for row in rows:
		driver = _doc(row.driver_spec)
		if driver.item and not DISABLED.get(driver.item):
			protocols.update(p.protocol for p in driver.input_protocols or [] if p.protocol)
	return {"protocols": sorted(protocols)}


class DriverCatalogBulk(unittest.TestCase):
	def setUp(self):
		self._ctx = load_service(ROOT + ".api.driver_catalog")
		self.catalog, self.frappe = self._ctx.__enter__()
		self.addCleanup(self._ctx.__exit__, None, None, None)
		self.frappe.get_doc = MagicMock(side_effect=lambda doctype, name: _doc(name))
		self.frappe.db.get_value = MagicMock(side_effect=self._get_value)
		self.calls = []

	def _get_value(self, doctype, name, field):
		if doctype == "Item":
			self.calls.append(name)
			return DISABLED.get(name, 0)
		return 1  # template is_active

	def bulk(self):
		self.frappe.get_all = MagicMock(side_effect=_get_all)

	def test_input_protocols_match_the_per_row_lookup_with_three_queries(self):
		rows = [Record(driver_spec=n) for n in ("DRV-A", "DRV-B", "DRV-DISABLED", "DRV-NOITEM", "DRV-A")]
		self.frappe.get_all = MagicMock(
			side_effect=lambda doctype, **kw: rows if doctype == "ilL-Rel-Driver-Eligibility" else _get_all(doctype, **kw)
		)
		result = self.catalog.input_protocols("ilL-Fixture-Template", "TPL")
		self.assertEqual(result, legacy_protocols(rows))
		self.assertEqual(result, {"protocols": ["0-10V", "DALI", "TRIAC"]})
		self.assertEqual(self.frappe.get_all.call_count, 4)
		self.frappe.get_doc.assert_not_called()
		self.assertEqual(self.calls, [])

	def test_collect_matches_expected_output(self):
		self.bulk()
		rows = [Record(driver_spec=n, priority=i) for i, n in enumerate(
			("DRV-A", "DRV-B", "DRV-DISABLED", "DRV-NOITEM", "DRV-12V"))]
		result, revisions = self.catalog._collect(rows, "24V", None, None)
		self.assertEqual([r["item_code"] for r in result], ["ITEM-A", "ITEM-B"])
		self.assertEqual(result[1], {"item_code": "ITEM-B", "outputs_count": 2, "priority": 1, "cost": 20,
			"max_wattage": 192, "max_wattage_per_output": 96, "usable_load_factor": 0.8})
		self.assertEqual(revisions["ITEM-A"]["outputs_count"], 1)
		self.assertEqual(revisions["ITEM-A"]["name"], "DRV-A")
		filtered, _ = self.catalog._collect(rows, "24V", None, "TRIAC")
		self.assertEqual([r["item_code"] for r in filtered], ["ITEM-B"])
		self.frappe.get_doc.assert_not_called()

	def test_ambiguity_and_channel_rules_are_unchanged(self):
		self.bulk()
		dup = [Record(driver_spec="DRV-A"), Record(driver_spec="DRV-A-DUP")]
		with self.assertRaisesRegex(ValueError, "one electrical specification"):
			self.catalog._collect(dup, "24V", None, None)
		self.assertEqual(len(self.catalog._collect(dup, "24V", None, None, skip_ambiguous=True)[0]), 1)
		tw = [Record(driver_spec="DRV-TW")]
		with self.assertRaisesRegex(ValueError, "color/control channels"):
			self.catalog._collect(tw, "24V", None, None)
		self.assertEqual(self.catalog._collect(tw, "24V", None, None, skip_ambiguous=True)[0], [])

	def test_missing_spec_still_raises_through_get_doc(self):
		self.bulk()
		with self.assertRaises(LookupError):
			self.catalog._collect([Record(driver_spec="GONE")], "24V", None, None)
		self.frappe.get_doc.assert_called_once_with("ilL-Spec-Driver", "GONE")

	def test_empty_rows_make_no_queries(self):
		self.bulk()
		self.assertEqual(self.catalog._collect([], "24V", None, None), ([], {}))
		self.frappe.get_all.assert_not_called()



if __name__ == "__main__":
	unittest.main()
