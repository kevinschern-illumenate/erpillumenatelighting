"""Design Catalog adapter (System Designer H7, WP-2.1).

The TEST records in ``packages/core-schemas/fixtures/catalog/erp-records.json`` build the committed
``payload.json``; the TypeScript suite parses that payload with the riser ``CatalogItemSchema`` and
``WireTypeSchema``. Regenerate after a deliberate mapping change with
``python3 -B tests/portal_unit/test_system_design_catalog.py --write``.
"""

import copy
import json
import random
import sys
import unittest
from pathlib import Path

from test_services import ROOT, load_service

CATALOG = ROOT + ".system_design.catalog"
FIXTURES = (
	Path(__file__).resolve().parents[2] / "tools/system_designer/packages/core-schemas/fixtures/catalog"
)
RECORDS = json.loads((FIXTURES / "erp-records.json").read_text(encoding="utf-8"))


def records():
	return copy.deepcopy(RECORDS)


class Mapping(unittest.TestCase):
	def setUp(self):
		self.context = load_service(CATALOG)
		self.module, _frappe = self.context.__enter__()
		self.payload = self.module.build_payload(records())
		self.items = {item["id"]: item for item in self.payload["items"]}
		self.wires = {wire["id"]: wire for wire in self.payload["wires"]}

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_committed_payload_matches_the_mapping(self):
		expected = json.loads((FIXTURES / "payload.json").read_text(encoding="utf-8"))
		self.assertEqual(json.loads(self.module.payload_json(self.payload)), expected)

	def test_tape_groups_and_conversions(self):
		base = self.items["tape:TEST-TAPE-24:4.4:50"]
		self.assertEqual(base["sku"], "TEST-TAPE-24 4.4 W/ft 50 mm cut")
		self.assertEqual(base["erpItemCode"], "TEST-TAPE-24")
		self.assertEqual(
			{
				key: base["specs"][key]
				for key in ("voltage", "drive", "wPerFtMax", "cutIntervalIn", "reelLengthFt")
			},
			{
				"voltage": 24,
				"drive": "CV",
				"wPerFtMax": 4.4,
				"cutIntervalIn": 1.9685,
				"reelLengthFt": 16.4042,
			},
		)
		self.assertEqual(base["specs"]["maxRunFtSingleFeed"], 16)
		self.assertEqual(base["specs"]["channelMap"], ["CH1"])
		high = self.items["tape:TEST-TAPE-24:6.2:100"]["specs"]
		self.assertEqual((high["wPerFtMax"], high["cutIntervalIn"]), (6.2, 3.937))
		rgb = self.items["tape:TEST-TAPE-RGB:6:free"]
		self.assertEqual(rgb["sku"], "TEST-TAPE-RGB")
		specs = rgb["specs"]
		self.assertTrue(specs["freeCutting"])
		self.assertNotIn("cutIntervalIn", specs)
		self.assertEqual(
			(specs["drive"], specs["powerBasis"], specs["channelMap"], specs["channelWPerFtMax"]),
			("CV-CC-IC", "max-operating", ["R", "G", "B"], [2, 2, 2]),
		)
		self.assertEqual(specs["maxRunFtSingleFeed"], 10)
		self.assertEqual(
			specs["pixel"], {"protocol": "WS2811", "pixelsPerFt": 18.288, "ampsPerPixelMax": 0.012}
		)

	def test_line_voltage_tape_is_incomplete_with_erp_fieldnames(self):
		item = self.items["tape:TEST-TAPE-120:3:1000"]
		self.assertEqual(item["specs"]["kind"], "incomplete")
		self.assertEqual(item["specs"]["intendedKind"], "tape")
		self.assertEqual(item["specs"]["missingFields"], ["input_voltage"])
		self.assertIn("120 V", item["specs"]["notes"][0])
		self.assertNotIn("voltage", item["specs"]["available"])

	def test_supplies_drivers_and_rank(self):
		psu = self.items["drv:TEST-PSU-96"]
		self.assertEqual((psu["category"], psu["specs"]["kind"]), ("psu", "psu"))
		self.assertEqual(psu["specs"]["outputs"], [{"name": "OUT1", "maxW": 96, "class2": True}])
		self.assertEqual(psu["specs"]["listings"], ["Class 2", "UL 8750"])
		self.assertEqual((psu["specs"]["maxInputA"], psu["specs"]["maxInputAAtV"]), (1.2, 120))
		self.assertEqual(psu["specs"]["usableLoadFactor"], 0.8)
		two = self.items["drv:TEST-PSU-60"]["specs"]
		self.assertEqual([o["name"] for o in two["outputs"]], ["OUT1", "OUT2"])
		self.assertEqual(two["dimming"], ["phase-forward"])
		cc = self.items["drv:TEST-CC-700"]
		self.assertEqual((cc["category"], cc["specs"]["outputType"]), ("driver", "CC"))
		self.assertEqual(
			(cc["specs"]["outputmA"], cc["specs"]["outputVMin"], cc["specs"]["outputVMax"]), (700, 20, 54)
		)
		self.assertNotIn("outputV", cc["specs"])
		# Same priority: the cheaper supply ranks first; lower priority comes after.
		ranks = {
			key: self.items[f"drv:{key}"].get("rank") for key in ("TEST-PSU-60", "TEST-PSU-96", "TEST-CC-700")
		}
		self.assertEqual(ranks, {"TEST-PSU-60": 1, "TEST-PSU-96": 2, "TEST-CC-700": 3})
		bad = self.items["drv:TEST-PSU-BAD"]
		self.assertNotIn("rank", bad)
		self.assertEqual(
			bad["specs"]["missingFields"], ["max_wattage_per_output", "efficiency", "input_protocols"]
		)
		self.assertIn("unmapped protocol: Mystery", bad["specs"]["notes"])

	def test_rank_reveals_order_not_cost(self):
		data = records()
		data["costs"]["TEST-PSU-60"] = 99
		items = {i["id"]: i for i in self.module.build_payload(data)["items"]}
		self.assertEqual(items["drv:TEST-PSU-96"]["rank"], 1)
		self.assertEqual(items["drv:TEST-PSU-60"]["rank"], 2)

	def test_controls(self):
		decoder = self.items["ctl:TEST-DEC-4"]
		self.assertEqual((decoder["category"], decoder["specs"]["kind"]), ("dmx-decoder", "decoder"))
		specs = decoder["specs"]
		self.assertEqual(
			(specs["powerType"], specs["maxATotal"], specs["dmxFootprint"], specs["protocolIn"]),
			("DC", 20, 4, ["DMX512"]),
		)
		self.assertNotIn("outputDimming", specs)
		self.assertNotIn("ports", specs)
		converter = self.items["ctl:TEST-CONV-4"]
		self.assertEqual(
			(converter["category"], converter["specs"]["kind"]), ("dmx-0-10v-converter", "controller")
		)
		self.assertEqual(
			converter["specs"]["ports"],
			[
				{"name": "DMX In", "direction": "in", "protocol": "DMX512"},
				{"name": "Out 1", "direction": "out", "protocol": "0-10V", "maxDevices": 10},
			],
		)
		self.assertEqual(converter["specs"]["ownPowerW"], 1.5)
		self.assertNotIn("ctl:TEST-DIM", self.items)
		self.assertNotIn("ctl:TEST-SENSOR", self.items)

	def test_wires(self):
		spool = self.wires["wire:TEST-WIRE-18-2"]
		self.assertEqual(
			{
				key: spool[key]
				for key in (
					"category",
					"applications",
					"ampacityBasis",
					"salesUom",
					"spoolLengthFt",
					"verify",
				)
			},
			{
				"category": "class2-power",
				"applications": ["class2-dc", "lv-branch"],
				"ampacityBasis": "402.5-fallback",
				"salesUom": "spool",
				"spoolLengthFt": 500,
				"verify": True,
			},
		)
		self.assertEqual(
			spool["conductors"],
			[
				{
					"count": 2,
					"awg": "18",
					"material": "Cu",
					"stranding": "stranded",
					"role": "power",
					"colors": ["Red", "Black"],
				}
			],
		)
		self.assertEqual(spool["source"], {"kind": "manufacturer", "reference": "Test datasheet rev A"})
		dmx = self.wires["wire:TEST-WIRE-DMX"]
		self.assertEqual(
			(dmx["ampacityBasis"], dmx["conductors"][0]["role"]), ("not-applicable", "data-pair")
		)
		self.assertNotIn("spoolLengthFt", dmx)
		self.assertNotIn("wire:TEST-WIRE-UNPRICED", self.wires)
		self.assertNotIn("costPerFt", spool)

	def test_no_cost_key_at_any_depth(self):
		data = records()
		for group in ("tapes", "drivers", "controllers", "wires"):
			for spec in data[group]:
				spec["cost"] = 12.5
				spec["valuation_rate"] = 10
		payload = self.module.build_payload(data)
		self.assertEqual(self.module.forbidden_keys(payload), set())
		self.assertNotIn("41.5", self.module.payload_json(payload))
		self.assertEqual(
			self.module.forbidden_keys({"a": [{"b": {"standard_rate": 1}}], "buying_price": 2}),
			{"standard_rate", "buying_price"},
		)

	def test_hash_is_stable_and_sensitive(self):
		first = self.module.payload_hash(self.payload)
		shuffled = records()
		for group in ("tapes", "drivers", "controllers", "wires"):
			random.Random(7).shuffle(shuffled[group])
		random.Random(3).shuffle(shuffled["offerings"]["TEST-TAPE-24"])
		self.assertEqual(self.module.payload_hash(self.module.build_payload(shuffled)), first)
		changed = records()
		changed["tapes"][0]["watts_per_foot"] = 4.5
		self.assertNotEqual(self.module.payload_hash(self.module.build_payload(changed)), first)
		self.assertEqual(self.module.unpack(self.module.pack(self.payload)), self.payload)
		self.assertEqual(self.module.pack(self.payload), self.module.pack(self.payload))
		self.assertEqual(
			self.module.summarize(self.payload),
			{"item_count": len(self.payload["items"]), "incomplete_count": 2, "wire_count": 2},
		)


class Snapshots(unittest.TestCase):
	def test_unknown_hash_is_not_found(self):
		with load_service(CATALOG) as (module, frappe):
			frappe.db.get_value.return_value = None
			with self.assertRaises(module.DesignError) as caught:
				module.catalog_response("0" * 64)
			self.assertEqual(caught.exception.code, "NOT_FOUND")
			self.assertIsNone(module.get_snapshot("../etc"))

	def test_stored_snapshot_is_unpacked(self):
		with load_service(CATALOG) as (module, frappe):
			payload = module.build_payload(records())
			frappe.db.get_value.return_value = module.pack(payload)
			response = module.catalog_response("a" * 64)
			self.assertEqual(response["hash"], "a" * 64)
			self.assertEqual(response["items"], payload["items"])

	def test_invalidate_drops_only_the_current_pointer(self):
		with load_service(CATALOG) as (module, frappe):
			module.invalidate()
			frappe.cache().delete_value.assert_called_once_with(module.CURRENT_KEY)


def write_payload():
	with load_service(CATALOG) as (module, _frappe):
		payload = module.build_payload(records())
		(FIXTURES / "payload.json").write_text(
			json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
		)


if __name__ == "__main__":
	if "--write" in sys.argv:
		write_payload()
	else:
		unittest.main()
