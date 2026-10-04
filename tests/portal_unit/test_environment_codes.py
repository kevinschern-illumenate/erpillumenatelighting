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
