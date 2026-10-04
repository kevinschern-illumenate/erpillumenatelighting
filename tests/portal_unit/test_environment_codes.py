"""Environment Rating codes (Dry 20, Damp 54, Wet 67, Wet+ 68) reach every record that copies them."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.led_sheet_math import match_sheet_specs

CODES = {"Dry": "20", "Damp": "54", "Wet": "67", "Wet+": "68"}


class Row(Record):
	__setattr__ = dict.__setitem__


def stub(name, **attributes):
	module = types.ModuleType(name)
	module.__dict__.update(attributes)
	return module


class SheetPanels(unittest.TestCase):
	"""LED Sheet panels are chosen by the option code appearing in the panel spec's Item code."""

	def names(self, specs, environment, offered=("54", "67", "68")):
		choices = {"Environment Rating": {"value": environment, "code": CODES[environment]}}
		return [s["name"] for s in match_sheet_specs(specs, choices, {"Environment Rating": list(offered)})]

	def test_each_rating_selects_its_ip_coded_panel(self):
		specs = [
			{"name": f"SW-{code}", "item": f"LED-SNF-SW-{code}-10W-SHEET", "cct": None}
			for code in ("54", "67", "68")
		]
		self.assertEqual(self.names(specs, "Damp"), ["SW-54"])
		self.assertEqual(self.names(specs, "Wet"), ["SW-67"])
		self.assertEqual(self.names(specs, "Wet+"), ["SW-68"])

	def test_panels_still_coded_o_resolve_until_ip_variants_exist(self):
		old = [{"name": "SW-O", "item": "LED-SNF-SW-O-10W-SHEET", "cct": None}]
		self.assertEqual(self.names(old, "Wet", offered=("67",)), ["SW-O"])
		# Once an IP-coded panel is allowed, the rating narrows to it.
		mixed = [*old, {"name": "SW-67", "item": "LED-SNF-SW-67-10W-SHEET", "cct": None}]
		self.assertEqual(self.names(mixed, "Wet", offered=("67",)), ["SW-67"])


class SheetTemplates(unittest.TestCase):
	def test_environment_rows_take_the_rating_code_and_other_rows_keep_theirs(self):
		with load_service(ROOT + ".api.environment_codes") as (codes, frappe):
			frappe.db.get_value.side_effect = lambda doctype, name, field: CODES.get(name)
			template = Record(
				allowed_options=[
					Row(option_type="Environment Rating", attribute_link="Wet", option_code="O"),
					Row(option_type="Environment Rating", attribute_link="Wet+", option_code=""),
					Row(option_type="CCT", attribute_link="3000K", option_code="30K"),
				]
			)
			self.assertTrue(codes.sync_sheet_template(template))
			self.assertEqual([r.option_code for r in template.allowed_options], ["67", "68", "30K"])
			self.assertFalse(codes.sync_sheet_template(template))


RATING_CODES = {
	**{("ilL-Attribute-Environment Rating", name): code for name, code in CODES.items()},
	**{("ilL-Attribute-IP Rating", f"IP{code}"): code for code in ("54", "67", "68")},
}


def lookup(doctype, name, field=None, as_dict=False):
	if doctype == "Item":
		return Record(stock_uom="Nos", disabled=0, item_name=name, ill_cable_assembly_length_mm=None)
	if isinstance(name, dict):
		return "TPL" if doctype == "ilL-Tape-Neon-Template" else 2.0
	return RATING_CODES.get((doctype, name))


class MountingAccessories(unittest.TestCase):
	"""Wet accessories serve IP67 and IP68 neon; Wet+ (IP68) accessories serve IP68 only."""

	def test_which_accessory_ratings_serve_which_products(self):
		with load_service(ROOT + ".api.environment_codes") as (codes, frappe):
			frappe.db.get_value.side_effect = lookup
			for row, product, expected in (
				("Wet", {"ip": ["IP67"]}, True),
				("Wet", {"ip": ["IP68"]}, True),
				("Wet", {"environment": "Wet+"}, True),
				("Wet", {"ip": ["IP54"]}, False),
				("Wet", {"environment": "Damp"}, False),
				("Wet+", {"ip": ["IP68"]}, True),
				("Wet+", {"environment": "Wet+"}, True),
				("Wet+", {"ip": ["IP67"]}, False),
				("Wet+", {"environment": "Wet"}, False),
				("Dry", {"ip": ["IP67"]}, False),
				("Damp", {"environment": "Damp"}, True),
				("", {"ip": ["IP67"]}, True),
			):
				with self.subTest(row=row, product=product):
					environments = codes.configuration_environments(
						product.get("environment"), product.get("ip", ())
					)
					self.assertIs(codes.accessory_serves(row, environments), expected)

	def test_ip_ratings_arrive_as_a_list_json_or_comma_separated(self):
		with load_service(ROOT + ".api.environment_codes") as (codes, frappe):
			frappe.db.get_value.side_effect = lookup
			expected = [("IP67", 67), ("IP68", 68)]
			for value in (["IP67", "IP68", "IP67"], '["IP67", "IP68"]', "IP67, IP68"):
				self.assertEqual(codes.configuration_environments(None, value), expected)

	def neon(self, maps):
		with load_service(ROOT + ".api.tape_neon_build") as (engine, frappe):
			frappe.db.get_value.side_effect = lookup
			frappe.get_all.return_value = [Record(environment_rating=row) for row in maps]
			result = {
				"selections": {"mounting_accessory_item": "CLIP", "mounting_accessory_qty": 4},
				"computed": {"segments": [{"ip_rating": "IP67"}, {"ip_rating": "IP68"}]},
			}
			return engine.mounting_component(result, "NEON-TPL")

	def test_a_wet_clip_is_approved_for_neon_with_ip67_and_ip68_segments(self):
		self.assertEqual(self.neon(["Wet"])["qty"], 4)

	def test_a_wet_plus_clip_needs_every_segment_to_be_ip68(self):
		with self.assertRaisesRegex(ValueError, "not approved"):
			self.neon(["Wet+"])
		self.assertEqual(self.neon(["Wet+", "Wet"])["qty"], 4)
		with self.assertRaisesRegex(ValueError, "not approved"):
			self.neon(["Dry"])

	def test_the_neon_picker_offers_only_accessories_the_build_approves(self):
		rows = [
			Record(
				accessory_item=item,
				environment_rating=rating,
				mounting_method=item,
				qty_rule_type="PER_SEGMENT",
			)
			for item, rating in (
				("WET-CLIP", "Wet"),
				("WETPLUS-CLIP", "Wet+"),
				("DRY-CLIP", "Dry"),
				("ANY-CLIP", ""),
			)
		]
		with load_service(ROOT + ".api.tape_neon_configurator") as (service, frappe):
			frappe.db.get_value.side_effect = lookup
			frappe.get_all.return_value = rows
			offered = service.get_mounting_accessories("NEON", ip_ratings='["IP67", "IP68"]', segments=2)
			ip68 = service.get_mounting_accessories("NEON", ip_ratings="IP68", segments=2)
			everything = service.get_mounting_accessories("NEON", segments=2)
		items = lambda response: [a["accessory_item"] for a in response["accessories"]]  # noqa: E731
		self.assertEqual(items(offered), ["WET-CLIP", "ANY-CLIP"])
		self.assertEqual(items(ip68), ["WET-CLIP", "WETPLUS-CLIP", "ANY-CLIP"])
		self.assertEqual(len(items(everything)), 4)  # No environment known: unchanged.


class SpecSheetIpRating(unittest.TestCase):
	"""A Webflow tape/neon spec sheet turns the environment into the IP rating its code names."""

	def resolve(self, ip_ratings=("IP20", "IP54", "IP67", "IP68"), **selections):
		environments = {code: name for name, code in CODES.items()}

		def get_value(doctype, name, field=None, *args, **kwargs):
			if isinstance(name, dict):
				code = name.get("code")
				if doctype == "ilL-Attribute-Environment Rating":
					return environments.get(code)
				return f"IP{code}" if f"IP{code}" in ip_ratings else None
			return CODES.get(name) if doctype == "ilL-Attribute-Environment Rating" else None

		with load_service(ROOT + ".api.spec_sheet_generator") as (generator, frappe):
			frappe.db.get_value.side_effect = get_value
			frappe.db.exists.side_effect = lambda doctype, name=None: name in CODES or name in ip_ratings
			return generator._resolve_ip_rating_from_selection(Record(allowed_options=[]), selections)

	def test_each_rating_maps_to_the_ip_rating_of_its_code(self):
		self.assertEqual(self.resolve(environment_rating="Dry"), "IP20")
		self.assertEqual(self.resolve(environment_rating="Damp"), "IP54")
		self.assertEqual(self.resolve(environment_rating="Wet"), "IP67")
		self.assertEqual(self.resolve(environment_rating="Wet+"), "IP68")
		self.assertEqual(self.resolve(environment_rating_code="68"), "IP68")
		# An explicit IP selection still wins.
		self.assertEqual(self.resolve(environment_rating="Wet+", ip_rating="IP67"), "IP67")

	def test_a_wet_plus_request_never_settles_for_ip67_while_ip68_exists(self):
		self.assertEqual(self.resolve(ip_ratings=("IP67", "IP68"), environment_rating="Wet+"), "IP68")


class WebflowSlugs(unittest.TestCase):
	def test_wet_plus_does_not_take_the_wet_slug(self):
		with load_service(ROOT + ".api.webflow_attributes") as (attributes, _frappe):
			self.assertEqual(attributes.slugify("Wet"), "wet")
			self.assertEqual(attributes.slugify("Wet+"), "wet-plus")
			self.assertEqual(attributes.slugify("RGB+W"), "rgb-plus-w")
			self.assertEqual(attributes.slugify("Dry Location"), "dry-location")


class Propagation(unittest.TestCase):
	def test_a_changed_code_reaches_the_templates_that_offer_the_rating(self):
		docs = {name: MagicMock(name=name) for name in ("SHEET-A", "SHEET-B", "FT-A", "FT-BROKEN")}
		builder = MagicMock(side_effect=lambda doc: doc is docs["FT-A"])
		fixture_template = stub("ill_fixture_template", sync_environment_section=builder)
		path = ROOT + ".doctype.ill_fixture_template.ill_fixture_template"
		with load_service(ROOT + ".api.environment_codes", {path: fixture_template}) as (codes, frappe):
			rows = {
				"ilL-Child-LED-Sheet-Allowed-Option": ["SHEET-A", "SHEET-B", "SHEET-A"],
				"ilL-Child-Template-Allowed-Option": ["FT-A", "FT-BROKEN", "FT-NO-BUILDER"],
				"ilL-Child-PN-Builder-Row": ["FT-A", "FT-BROKEN"],
			}
			frappe.get_all.side_effect = lambda doctype, **kwargs: rows[doctype]
			frappe.get_doc.side_effect = lambda doctype, name: docs[name]
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			codes.sync_sheet_template = lambda doc: doc is docs["SHEET-A"]
			docs["FT-BROKEN"].save.side_effect = ValueError("locked")
			builder.side_effect = lambda doc: doc in (docs["FT-A"], docs["FT-BROKEN"])

			failed = codes.propagate("Wet")

			filters = {c.args[0]: c.kwargs["filters"] for c in frappe.get_all.call_args_list}
		self.assertEqual(filters["ilL-Child-LED-Sheet-Allowed-Option"]["attribute_link"], "Wet")
		self.assertEqual(filters["ilL-Child-Template-Allowed-Option"]["environment_rating"], "Wet")
		docs["SHEET-A"].save.assert_called_once_with(ignore_permissions=True)
		docs["SHEET-B"].save.assert_not_called()
		docs["FT-A"].save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(failed, ["ilL-Fixture-Template FT-BROKEN"])

	def test_only_a_code_change_propagates(self):
		propagate = MagicMock(return_value=[])
		extras = {
			"frappe.model.document": stub("frappe.model.document", Document=object),
			ROOT + ".api.environment_codes": stub("environment_codes", propagate=propagate),
		}
		path = ROOT + ".doctype.ill_attribute_environment_rating.ill_attribute_environment_rating"
		with load_service(path, extras) as (module, _frappe):
			rating = module.ilLAttributeEnvironmentRating()
			rating.name = "Wet+"
			rating.has_value_changed = lambda field: False
			rating.on_change()
			propagate.assert_not_called()
			rating.has_value_changed = lambda field: field == "code"
			rating.on_change()
		propagate.assert_called_once_with("Wet+")

	def test_existing_sites_sync_their_sheet_templates_on_migrate(self):
		patches = Path("illumenate_lighting/patches.txt").read_text().split("[post_model_sync]", 1)[1]
		self.assertIn(
			"illumenate_lighting.patches.sync_environment_codes_on_led_sheet_templates", patches.splitlines()
		)


if __name__ == "__main__":
	unittest.main()
