"""Assembled vs ship-in-pieces linear fixtures (fixture_fulfillment)."""

import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.fixture_fulfillment"

ITEMS = {
	"TAPE": Record(stock_uom="Inch", disabled=0),
	"LEADER": Record(stock_uom="Inch", disabled=0),
	"JUMPER": Record(stock_uom="Inch", disabled=0),
	"PROFILE": Record(stock_uom="Ea", disabled=0),
	"LENS": Record(stock_uom="Ea", disabled=0),
	"EC-FT": Record(stock_uom="Ea", disabled=0),
	"EC-SOLID": Record(stock_uom="Ea", disabled=0),
	"CLIP": Record(stock_uom="Nos", disabled=0),
	"AX01-JOIN-S": Record(stock_uom="Ea", disabled=0),
	"AX01-JOIN-L": Record(stock_uom="Ea", disabled=0),
}


def fake_db(frappe, *, family="AX01", lens_type="Stick", stick=2000, joiners=("AX01-JOIN-L", "AX01-JOIN-S")):
	def get_value(doctype, name, field=None, as_dict=False, **kwargs):
		if doctype == "ilL-Fixture-Template":
			return 2500
		if doctype == "ilL-Spec-Profile":
			return {"stock_length_mm": stick, "family": family}[field]
		if doctype == "ilL-Spec-Lens":
			if as_dict:
				return Record(stock_type=lens_type, stock_length_mm=stick, continuous_max_length_mm=30000)
			return lens_type
		if doctype == "Item":
			item = ITEMS.get(name)
			if item is None:
				return None
			if as_dict:
				return item
			if field == "stock_uom":
				return item.stock_uom
			return item.get(field)
		return None

	frappe.db.get_value = MagicMock(side_effect=get_value)
	frappe.get_all = MagicMock(
		side_effect=lambda doctype, filters=None, **kw: (
			[Record(item=code) for code in joiners] if filters.get("profile_family") == family else []
		)
	)


def row(code, qty, uom="Ea"):
	return {"item_code": code, "qty": qty, "uom": uom, "stock_uom": uom}


def doc(runs, segments=(), tape_cut=0):
	return Record(
		fixture_template="AX01",
		profile_item="PROFILE",
		lens_item="LENS",
		runs=[Record(run_index=i, run_len_mm=mm) for i, mm in runs],
		segments=[Record(segment_index=i, tape_cut_len_mm=mm) for i, mm in segments],
		tape_cut_length_mm=tape_cut,
	)


class PureRules(unittest.TestCase):
	def setUp(self):
		self.ctx = load_service(MODULE)
		self.module, self.frappe = self.ctx.__enter__()

	def tearDown(self):
		self.ctx.__exit__(None, None, None)

	def test_every_segment_within_a_stick_is_assembled(self):
		m = self.module
		self.assertEqual(m.classify([2000, 1524, 1524], 2000), m.ASSEMBLED)
		self.assertEqual(m.classify([1524, 2001], 2000), m.SHIP_PIECES)
		self.assertEqual(m.classify([9000], 0), m.ASSEMBLED)

	def test_sticks_round_up(self):
		self.assertEqual(self.module.sticks_for(9742, 2000), 5)
		self.assertEqual(self.module.sticks_for(4000, 2000), 2)
		self.assertEqual(self.module.sticks_for(100, 2000), 1)

	def test_segment_lengths_sum_stick_pieces_per_user_segment(self):
		computed = {
			"user_segments": [
				{"user_segment_index": 1, "profile_cut_len_mm": 2000},
				{"user_segment_index": 1, "profile_cut_len_mm": 500},
				{"user_segment_index": 2, "profile_cut_len_mm": 1200},
			]
		}
		self.assertEqual(self.module.segment_lengths(computed), [2500, 1200])
		self.assertEqual(self.module.segment_lengths({"manufacturable_overall_length_mm": 3000}), [3000])

	def test_jumpers_belong_to_the_run_whose_tape_spans_them(self):
		runs = self.module.split_runs([(1, 3000), (2, 3000)], [(1500, "J1"), (4500, "J2"), (6000, "END")], 300)
		self.assertEqual([r["jumpers"] for r in runs], [["J1"], ["J2", "END"]])
		self.assertEqual([r["lead_mm"] for r in runs], [300, 300])

	def test_identical_runs_share_one_light_engine(self):
		engines = self.module.dedupe_engines(
			[
				{"run_index": 1, "components": [row("TAPE", 100, "Inch")]},
				{"run_index": 2, "components": [row("TAPE", 100, "Inch")]},
				{"run_index": 3, "components": [row("TAPE", 40, "Inch")]},
			]
		)
		self.assertEqual([(e["key"], e["qty"], e["runs"]) for e in engines], [("LE1", 2, [1, 2]), ("LE2", 1, [3])])

	def test_flag_off_or_unreadable_means_no_split(self):
		self.frappe.db.get_single_value = MagicMock(return_value=0)
		self.assertFalse(self.module.split_enabled())
		self.frappe.db.get_single_value = MagicMock(side_effect=Exception("no column"))
		self.assertFalse(self.module.split_enabled())
		self.frappe.db.get_single_value = MagicMock(return_value=1)
		self.assertTrue(self.module.split_enabled())

	def test_only_linear_3_builds_ship_in_pieces(self):
		block = json.dumps({"fulfillment": {"mode": "SHIP_PIECES"}})
		self.assertTrue(self.module.is_ship_pieces(Record(engine_version="linear-3", build_snapshot_json=block)))
		self.assertFalse(self.module.is_ship_pieces(Record(engine_version="linear-2", build_snapshot_json=block)))
		self.assertFalse(self.module.is_ship_pieces(Record(engine_version="linear-3", build_snapshot_json="{}")))


class Planning(unittest.TestCase):
	def setUp(self):
		self.ctx = load_service(MODULE)
		self.module, self.frappe = self.ctx.__enter__()

	def tearDown(self):
		self.ctx.__exit__(None, None, None)

	def components(self):
		return [
			row("TAPE", 9742 / 25.4, "Inch"),
			row("LEADER", 120, "Inch"),
			row("PROFILE", 1),
			row("LENS", 1),
			row("EC-FT", 2),
			row("EC-SOLID", 2),
			row("CLIP", 10, "Nos"),
		]

	def test_short_fixture_is_assembled_and_keeps_its_components(self):
		fake_db(self.frappe)
		components = self.components()
		block, result = self.module.plan(
			doc([(1, 1500)]),
			{"manufacturable_overall_length_mm": 1524},
			components,
			[{"role": "leader", "item_code": "LEADER", "length_mm": 3048, "key": "leader"}],
			"TAPE",
		)
		self.assertEqual(block["mode"], "ASSEMBLED")
		self.assertIs(result, components)

	def test_long_fixture_ships_a_kit_and_one_light_engine_per_run(self):
		fake_db(self.frappe)
		block, shipped = self.module.plan(
			doc([(1, 4871), (2, 4871)], tape_cut=9742),
			{"manufacturable_overall_length_mm": 9742},
			self.components(),
			[
				{"role": "leader", "item_code": "LEADER", "length_mm": 3048, "key": "leader"},
				{"role": "additional feed", "item_code": "LEADER", "length_mm": 3048, "key": "feed-2"},
			],
			"TAPE",
		)
		self.assertEqual(block["mode"], "SHIP_PIECES")
		self.assertEqual((block["sticks"], block["joints"], block["joiner_item"]), ([5], 4, "AX01-JOIN-S"))
		kit = {r["item_code"]: r["qty"] for r in block["kit"]}
		self.assertEqual(kit["PROFILE"], 5)
		self.assertEqual(kit["LENS"], 5)
		self.assertEqual(kit["AX01-JOIN-S"], 4)
		self.assertEqual((kit["EC-FT"], kit["EC-SOLID"], kit["CLIP"]), (2, 2, 10))
		self.assertNotIn("TAPE", kit)
		self.assertNotIn("LEADER", kit)
		# Both runs are identical: one light engine Item, quantity 2, each with its own leader.
		[engine] = block["light_engines"]
		self.assertEqual((engine["key"], engine["qty"], engine["runs"]), ("LE1", 2, [1, 2]))
		parts = {r["item_code"]: r["qty"] for r in engine["components"]}
		self.assertAlmostEqual(parts["TAPE"], 4871 / 25.4, places=4)
		self.assertAlmostEqual(parts["LEADER"], 120, places=4)
		# The sealed materials equal what ships: kit + every light engine.
		totals = {r["item_code"]: r["qty"] for r in shipped}
		self.assertAlmostEqual(totals["TAPE"], 9742 / 25.4, places=4)
		self.assertAlmostEqual(totals["LEADER"], 240, places=4)
		self.assertEqual(totals["PROFILE"], 5)

	def test_family_without_a_straight_joiner_is_butted(self):
		fake_db(self.frappe, family="SH01", joiners=())
		block, _ = self.module.plan(
			doc([(1, 3000)], tape_cut=3000),
			{"manufacturable_overall_length_mm": 3000},
			self.components(),
			[{"role": "leader", "item_code": "LEADER", "length_mm": 3048, "key": "leader"}],
			"TAPE",
		)
		self.assertEqual((block["joints"], block["joiner_item"]), (1, None))
		self.assertNotIn("AX01-JOIN-S", {r["item_code"] for r in block["kit"]})

	def test_continuous_lens_is_not_counted_in_sticks(self):
		fake_db(self.frappe, lens_type="Continuous Roll")
		block, _ = self.module.plan(
			doc([(1, 4000)], tape_cut=4000),
			{"manufacturable_overall_length_mm": 4000},
			self.components(),
			[{"role": "leader", "item_code": "LEADER", "length_mm": 3048, "key": "leader"}],
			"TAPE",
		)
		kit = {r["item_code"]: r["qty"] for r in block["kit"]}
		self.assertEqual((kit["PROFILE"], kit["LENS"]), (2, 1))

	def test_jumpers_go_into_the_light_engine_of_their_run(self):
		fake_db(self.frappe)
		fixture = doc([(1, 3000)], segments=[(1, 1500), (2, 1500)])
		block, _ = self.module.plan(
			fixture,
			{
				"user_segments": [
					{"user_segment_index": 1, "profile_cut_len_mm": 1524},
					{"user_segment_index": 2, "profile_cut_len_mm": 2540},
				]
			},
			self.components(),
			[
				{"role": "leader", "item_code": "LEADER", "length_mm": 3048, "key": "leader"},
				{"role": "jumper", "item_code": "JUMPER", "length_mm": 610, "key": "end-1"},
			],
			"TAPE",
		)
		[engine] = block["light_engines"]
		self.assertEqual(engine["jumpers_mm"], [610])
		self.assertIn("JUMPER", {r["item_code"] for r in engine["components"]})

	def test_bundle_lists_light_engines_then_kit(self):
		block = {
			"light_engines": [{"key": "LE1", "qty": 2}],
			"kit": [row("PROFILE", 5), row("CLIP", 10, "Nos")],
		}
		self.assertEqual(
			self.module.bundle_rows(block, {"LE1": "FX-1-LE1"}),
			[
				{"item_code": "FX-1-LE1", "qty": 2},
				{"item_code": "PROFILE", "qty": 5},
				{"item_code": "CLIP", "qty": 10},
			],
		)

	def test_a_changed_bundle_is_refused(self):
		self.frappe.get_all = MagicMock(return_value=[Record(item_code="PROFILE", qty=4)])
		with self.assertRaises(ValueError):
			self.module.assert_bundle("FX-1", [{"item_code": "PROFILE", "qty": 5}])
		self.frappe.get_all = MagicMock(return_value=[Record(item_code="PROFILE", qty=5)])
		self.module.assert_bundle("FX-1", [{"item_code": "PROFILE", "qty": 5}])


class LightEngineWorkOrders(unittest.TestCase):
	def test_one_work_order_per_light_engine_for_unplanned_demand(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, _):
			with load_service(ROOT + ".api.manufacturing_order", {ROOT + ".api.build_artifacts": artifacts}) as (
				module,
				frappe,
			):
				order = Record(name="SO", company="Company")
				row = Record(name="ROW", item_code="FX-1", qty=3, conversion_factor=1)
				fixture = Record(name="CF1", doctype="ilL-Configured-Fixture")
				engines = [
					({"key": "LE1", "qty": 2, "runs": [1, 2]}, "FX-1-LE1", "B1"),
					({"key": "LE2", "qty": 1, "runs": [3]}, "FX-1-LE2", "B2"),
				]
				fulfillment = types.SimpleNamespace(
					light_engines=lambda _doc: engines,
					traveler_lines=lambda _doc, engine=None: [engine["key"] if engine else "kit"],
				)
				frappe.get_all.return_value = [
					Record(name="WO1", production_item="FX-1-LE1", bom_no="B1", qty=6, status="Draft")
				]
				frappe.get_meta.return_value.has_field.return_value = True
				created = []
				work = MagicMock()
				work.name = "WO2"
				frappe.get_doc.side_effect = lambda value, *a: created.append(value) or work
				with patch.dict("sys.modules", {ROOT + ".api.fixture_fulfillment": fulfillment}):
					result = module._create_for_light_engines(order, row, fixture, {"components": []})
				self.assertEqual(result["work_orders"], ["WO1", "WO2"])
				[data] = created
				self.assertEqual((data["production_item"], data["bom_no"], data["qty"]), ("FX-1-LE2", "B2", 3))
				self.assertEqual(data["product_bundle_item"], "FX-1")
				self.assertEqual(data["ill_configured_fixture"], "CF1")
				self.assertIn("kit", data["remarks"])

	def test_production_that_differs_is_refused(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, _):
			with load_service(ROOT + ".api.manufacturing_order", {ROOT + ".api.build_artifacts": artifacts}) as (
				module,
				frappe,
			):
				fulfillment = types.SimpleNamespace(
					light_engines=lambda _doc: [({"key": "LE1", "qty": 1}, "FX-1-LE1", "B1")],
					traveler_lines=lambda _doc, engine=None: [],
				)
				frappe.get_all.return_value = [
					Record(name="WO1", production_item="FX-1-LE1", bom_no="OLD", qty=1, status="Draft")
				]
				with patch.dict("sys.modules", {ROOT + ".api.fixture_fulfillment": fulfillment}):
					with self.assertRaisesRegex(ValueError, "Manufacturing must reconcile"):
						module._create_for_light_engines(
							Record(name="SO", company="C"),
							Record(name="ROW", item_code="FX-1", qty=1, conversion_factor=1),
							Record(name="CF1"),
							{"components": []},
						)


if __name__ == "__main__":
	unittest.main()
