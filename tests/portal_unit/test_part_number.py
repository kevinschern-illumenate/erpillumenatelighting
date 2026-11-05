"""Plan 3.5: fixture part numbers decode to offered options, and anything unclear is reported."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

ATTRIBUTES = {
	"ilL-Attribute-Environment Rating": {"Dry": "D", "Wet": "W"},
	"ilL-Attribute-Lens Appearance": {"Frosted": "FR", "Clear": "CL"},
	"ilL-Attribute-Mounting Method": {"Clips": "CL", "Surface": "SM"},
	"ilL-Attribute-Finish": {"Anodized Silver": "SV", "White": "WH", "Old White": "WH"},
	"ilL-Attribute-Power Feed Type": {"Leader": "L", "Leader Plug": "LP"},
	"ilL-Attribute-LED Package": {"SMD 2835": "S", "COB": "C"},
	"ilL-Attribute-CCT": {"3000K": "30", "4000K": "40"},
}
OFFERINGS = [
	Record(name="TO-1", led_package="SMD 2835", cct="3000K", is_active=1),
	Record(name="TO-2", led_package="SMD 2835", cct="4000K", is_active=1),
	Record(name="TO-3", led_package="COB", cct="4000K", is_active=1),
]


def option(option_type, field, value, active=1):
	return Record(option_type=option_type, is_active=active, **{field: value})


def template(name, builder=None, finishes=("Anodized Silver",)):
	return Record(
		name=name,
		allowed_options=[
			option("Environment Rating", "environment_rating", "Dry"),
			option("Environment Rating", "environment_rating", "Wet"),
			option("Lens Appearance", "lens_appearance", "Frosted"),
			option("Mounting Method", "mounting_method", "Clips"),
			option("Mounting Method", "mounting_method", "Surface", active=0),
			option("Power Feed Type", "power_feed_type", "Leader"),
			option("Power Feed Type", "power_feed_type", "Leader Plug"),
			*[option("Finish", "finish", finish) for finish in finishes],
		],
		allowed_tape_offerings=[Record(tape_offering=row.name) for row in OFFERINGS],
		part_number_builder=builder or [],
	)


def get_all(templates):
	def lookup(doctype, filters=None, fields=None, **kwargs):
		filters = filters or {}
		if doctype == "ilL-Fixture-Template":
			return [Record(name=row.name, template_name=row.name.title(), default_profile_family=row.family) for row in templates]
		if doctype == "ilL-Rel-Tape Offering":
			return [row for row in OFFERINGS if row.name in filters["name"][1]]
		wanted = filters["name"][1]
		return [Record(name=name, code=code) for name, code in ATTRIBUTES[doctype].items() if name in wanted]

	return lookup


class PartNumber(unittest.TestCase):
	def module(self, templates, enabled=True, configurator=None):
		listing = types.ModuleType(ROOT + ".portal_listing")
		listing.template_filters = lambda **filters: {"product_status": ["in", ["Active"]], **filters}
		flags = types.ModuleType(ROOT + ".portal.site_flags")
		flags.part_number_decode_enabled = lambda: enabled
		access = types.ModuleType(ROOT + ".portal.configurator_access")
		access.require_configurator = configurator or (lambda schedule=None: None)
		context = load_service(
			ROOT + ".portal.part_number",
			{
				ROOT + ".portal_listing": listing,
				ROOT + ".portal.site_flags": flags,
				ROOT + ".portal.configurator_access": access,
			},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		docs = {row.name: row for row in templates}
		frappe.get_all = MagicMock(side_effect=get_all(templates))
		frappe.get_cached_doc = MagicMock(side_effect=lambda doctype, name: docs[name])
		return module, frappe

	def test_parse_reads_both_tails_and_hyphenated_series(self):
		module, _frappe = self.module([])
		parsed = module.parse(" ill-sh-01-s-d-30-o3-fr-cl-sv-48.0-l10-c ")
		self.assertEqual(
			(parsed["series"], parsed["led_package"], parsed["finish"], parsed["feed"], parsed["end"], parsed["joint"]),
			("SH-01", "S", "SV", "L10", "C", False),
		)
		self.assertEqual(parsed["length_inches"], 48.0)
		joint = module.parse("ILL-SH01-S-D-30-O3-FR-CL-SV-120.0-J(AB12)-V(2)")
		self.assertEqual((joint["joint"], joint["feed"], joint["variant"]), (True, None, True))

	def test_parse_refuses_other_text(self):
		module, _frappe = self.module([])
		for value in ("", "LS-48", "ILL-SH01-S-D-30-O3-FR-CL-SV-long-L10-C", "X" * 300, "ILL-SH01--D-30-O3-FR-CL-SV-48-L10-C"):
			with self.subTest(value=value), self.assertRaises(module.NotAPartNumber):
				module.parse(value)

	def test_decodes_every_offered_option(self):
		builder = [Record(section_name="Finish", option_code="SV", option_label="Silver")]
		module, _frappe = self.module([Record(template("FT-1", builder), family="SH01")])
		result = module.decode("ILL-SH01-S-W-40-O3-FR-CL-SV-48.0-LP6-C")
		self.assertEqual(result["status"], "decoded")
		self.assertEqual(result["template"], "FT-1")
		self.assertEqual(
			result["selections"],
			{
				"fixture_template_code": "FT-1",
				"environment_rating_code": "Wet",
				"lens_appearance_code": "Frosted",
				"mounting_method_code": "Clips",
				"finish_code": "Anodized Silver",
				"led_package_code": "SMD 2835",
				"cct_code": "4000K",
			},
		)
		finish = next(row for row in result["applied"] if row["field"] == "finish")
		self.assertEqual(finish["label"], "Silver")
		review = {row["field"]: row for row in result["review"]}
		self.assertEqual((review["feed"]["value"], review["feed"]["leader_ft"]), ("Leader Plug", 6.0))
		self.assertEqual(review["length"]["answer"], 48.0)
		self.assertEqual(review["output"]["answer"], "O3")
		self.assertEqual(
			[row["text"] for row in result["review"]],
			["Output O3", "Length 48 in", "Start feed Leader Plug, 6 ft leader", "Choose the feed direction"],
		)
		# Length, start feed, leader and end prefill the segment, so the dealer does not re-enter them.
		self.assertEqual(
			result["segments"],
			[
				{
					"segment_index": 1,
					"requested_length_mm": 1219.2,
					"start_power_feed_type": "Leader Plug",
					"start_leader_cable_length_mm": 1829,
					"end_type": "Endcap",
				}
			],
		)

	def test_jointed_part_numbers_leave_segments_to_the_dealer(self):
		module, _frappe = self.module([Record(template("FT-1", []), family="SH01")])
		result = module.decode("ILL-SH01-S-W-40-O3-FR-CL-SV-120.0-J(AB12)")
		self.assertEqual(result["segments"], [])
		self.assertIn("Jointed runs", [row["text"] for row in result["review"]])

	def test_unclear_codes_are_reported_not_guessed(self):
		builder = [Record(section_name="Mounting", option_code="CL"), Record(section_name="Lens", option_code="FR")]
		module, _frappe = self.module(
			[Record(template("FT-1", builder, finishes=("White", "Old White")), family="SH01")]
		)
		# SM is an inactive mounting, WH is two finishes, CL is not a lens, C/30 is not an offering.
		result = module.decode("ILL-SH01-C-D-30-XX-CL-SM-WH-24-L-C")
		self.assertEqual(result["status"], "partial")
		reasons = {row["field"]: row["reason"] for row in result["unmatched"]}
		self.assertEqual(reasons["finish"], "matches more than one option")
		self.assertEqual(reasons["lens"], "not in this product's part number guide")
		self.assertEqual(reasons["mounting"], "not in this product's part number guide")
		self.assertEqual(reasons["cct"], "no longer offered on this product")
		for key in ("finish_code", "lens_appearance_code", "mounting_method_code", "cct_code"):
			self.assertNotIn(key, result["selections"])
		self.assertEqual(result["selections"]["led_package_code"], "COB")
		self.assertNotIn("output", {row["field"] for row in result["review"]}, "XX means not specified")

	def test_unknown_series_and_equal_templates(self):
		module, _frappe = self.module([Record(template("FT-1"), family="SH01"), Record(template("FT-2"), family="SH01")])
		unknown = module.decode("ILL-ZZ9-S-D-30-O3-FR-CL-SV-48-L-C")
		self.assertEqual((unknown["status"], unknown["template"]), ("unknown", None))
		tie = module.decode("ILL-SH01-S-D-30-O3-FR-CL-SV-48-L-C")
		self.assertEqual((tie["status"], tie["template"], tie["selections"]), ("ambiguous", None, {}))
		self.assertEqual([row["value"] for row in tie["candidates"]], ["FT-1", "FT-2"])

	def test_best_matching_template_wins(self):
		module, _frappe = self.module(
			[Record(template("FT-1", finishes=("White",)), family="SH01"), Record(template("FT-2"), family="SH01")]
		)
		result = module.decode("ILL-SH01-S-D-30-O3-FR-CL-SV-48-L-C")
		self.assertEqual((result["status"], result["template"]), ("decoded", "FT-2"))

	def test_endpoint_guards(self):
		calls = []
		module, frappe = self.module([], configurator=lambda schedule=None: calls.append(schedule))
		frappe.session = Record(user="Guest")
		with self.assertRaises(PermissionError):
			module.decode_part_number("ILL-X")
		frappe.session = Record(user="dana@acme.test")
		self.assertEqual(module.decode_part_number("nope", schedule="S-1")["success"], False)
		self.assertEqual(calls, ["S-1"])
		module, frappe = self.module([], enabled=False)
		with self.assertRaises(ValueError):
			module.decode_part_number("ILL-X")
