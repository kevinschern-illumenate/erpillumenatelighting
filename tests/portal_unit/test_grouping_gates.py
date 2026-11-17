"""Plan 6.8: code-verifiable grouping gates — canonical identity and cable ownership."""

import copy
import unittest

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.group_contract import normalize


def linear(*segments):
	return {
		"family": "Linear Fixture",
		"template": "ILL-SH01-SW",
		"shared": {"finish_code": "White"},
		"power": {"include_power_supply": True},
		"members": [{"label": "L1", "input": {"segments": list(segments)}}],
	}


def segment(**extra):
	return {
		"length_value": 10,
		"length_unit": "ft",
		"start_leader_cable_length_mm": 1828.8,
		"end_type": "Endcap",
		**extra,
	}


def tape(seg):
	return {
		"family": "LED Tape",
		"template": "TAPE-T",
		"shared": {"cct": "3000K"},
		"power": {"include_power_supply": False},
		"members": [{"input": {"segments": [seg]}}],
	}


class CanonicalIdentity(unittest.TestCase):
	def test_leader_and_jumper_dimensions_are_part_of_the_identity(self):
		base = fingerprint(normalize(linear(segment())))
		longer = fingerprint(normalize(linear(segment(start_leader_cable_length_mm=914.4))))
		self.assertNotEqual(base, longer)
		jumped = linear(segment(end_type="Jumper", end_jumper_cable_length_mm=304.8), segment())
		other = linear(segment(end_type="Jumper", end_jumper_cable_length_mm=609.6), segment())
		self.assertNotEqual(fingerprint(normalize(jumped)), fingerprint(normalize(other)))

	def test_an_endcap_ignores_a_stale_jumper_length(self):
		stale = linear(segment(end_jumper_cable_length_mm=999))
		self.assertEqual(normalize(stale), normalize(linear(segment())))
		self.assertEqual(normalize(stale)["members"][0]["segments"][0]["end_jumper_cable_length_mm"], 0)

	def test_tape_feet_inches_inches_and_millimetres_share_one_identity(self):
		forms = (
			{"tape_length_unit": "ft_in", "tape_length_feet": 5, "tape_length_inches": 6},
			{"tape_length_unit": "in", "tape_length_value": 66},
			{"tape_length_unit": "mm", "tape_length_value": 66 * 25.4},
			{"requested_length_mm": 66 * 25.4},
		)
		identities = {
			fingerprint(normalize(tape({**form, "start_lead_length_inches": 72, "end_type": "Endcap"})))
			for form in forms
		}
		self.assertEqual(len(identities), 1)
		normal = normalize(tape({**forms[1], "start_lead_length_inches": 72}))
		self.assertAlmostEqual(normal["members"][0]["segments"][0]["requested_length_mm"], 1676.4)
		self.assertAlmostEqual(normal["members"][0]["segments"][0]["start_lead_length_inches"], 72)

	def test_presentation_does_not_change_identity_but_the_template_does(self):
		first = linear(segment())
		second = copy.deepcopy(first)
		second.update(qty=4, view="desk")
		second["members"][0].update(label="Renamed", member_id="x")
		self.assertEqual(fingerprint(normalize(first)), fingerprint(normalize(second)))
		second["template"] = "ILL-SH02-SW"
		second["members"][0]["template"] = "ILL-SH02-SW"
		self.assertNotEqual(fingerprint(normalize(first)), fingerprint(normalize(second)))


class LinearCableOwnership(unittest.TestCase):
	def fixture(self, **extra):
		data = {
			"name": "PREVIEW",
			"leader_item": "WIRE",
			"is_multi_segment": 0,
			"segments": [Record(segment_index=1, start_leader_len_mm=609.6, start_leader_item="WIRE")],
			"runs": [Record(run_index=1, leader_item="WIRE", leader_len_mm=300)],
		}
		data.update(extra)
		return Record(**data)

	def test_single_fixture_end_feed_is_an_end_leader_not_a_jumper(self):
		fixture = self.fixture()
		fixture.segments[0]["end_jumper_len_mm"] = 304.8
		fixture.segments[0]["end_jumper_item"] = "WIRE"
		with load_service(ROOT + ".api.linear_build") as (engine, frappe):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			cuts = engine.cable_manifest(fixture)
		self.assertEqual([c["role"] for c in cuts], ["leader", "end leader"])
		self.assertEqual([c["key"] for c in cuts], ["feed-1", "end-1"])
		self.assertAlmostEqual(sum(c["qty"] for c in cuts), 3)

	def test_unresolved_disabled_or_absent_cables_fail_instead_of_dropping_a_row(self):
		with load_service(ROOT + ".api.linear_build") as (engine, frappe):
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=1)
			with self.assertRaisesRegex(ValueError, "missing or disabled"):
				engine.cable_manifest(self.fixture())
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			unresolved = self.fixture(leader_item=None)
			unresolved.segments[0]["start_leader_item"] = None
			unresolved.runs[0]["leader_item"] = None
			with self.assertRaisesRegex(ValueError, "resolved cable Item"):
				engine.cable_manifest(unresolved)
			with self.assertRaisesRegex(ValueError, "No physical leader"):
				engine.cable_manifest(self.fixture(segments=[], runs=[]))

	def test_bom_rows_merge_by_item_and_uom_only(self):
		with load_service(ROOT + ".api.linear_build") as (engine, _frappe):
			rows = engine.cable_bom_rows(
				[
					{"item_code": "WIRE", "stock_uom": "Foot", "qty": 2},
					{"item_code": "WIRE", "stock_uom": "Foot", "qty": 1},
					{"item_code": "WIRE-B", "stock_uom": "Nos", "qty": 1},
				]
			)
		self.assertEqual(
			rows,
			[
				{"item_code": "WIRE", "qty": 3, "uom": "Foot", "stock_uom": "Foot"},
				{"item_code": "WIRE-B", "qty": 1, "uom": "Nos", "stock_uom": "Nos"},
			],
		)


if __name__ == "__main__":
	unittest.main()
