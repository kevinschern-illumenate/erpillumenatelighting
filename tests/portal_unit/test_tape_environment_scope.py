"""Environment Ratings are IP ratings (Dry 20 / Damp 54 / Wet 67): a tape request never borrows another rating's spec."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

DRY = Record(tape_spec="ILL-SH01-SW-20", environment_rating="Dry", is_default=1)
WET = Record(tape_spec="ILL-SH01-SW-67", environment_rating="Wet", is_default=0)
ANY = Record(tape_spec="ILL-SH01-SW-ANY", environment_rating=None, is_default=0)


class EnvironmentScope(unittest.TestCase):
	def service(self, rows):
		rollout = types.SimpleNamespace(require_configuration=lambda family: None)
		context = load_service(ROOT + ".api.tape_neon_configurator", {ROOT + ".portal.rollout": rollout})
		service, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.logger = MagicMock()
		meta = Record(is_free_cutting=0, default_tape_spec=DRY.tape_spec)
		frappe.db.get_value.side_effect = lambda doctype, *args, **kwargs: (
			meta if doctype == "ilL-Tape-Neon-Template" else "Static White"
		)
		specs = [Record(name=r.tape_spec, item=r.tape_spec, led_package="SW") for r in rows]
		frappe.get_all.side_effect = lambda doctype, *args, **kwargs: {
			"ilL-Child-Tape-Neon-Allowed-Spec": rows,
			"ilL-Spec-LED Tape": specs,
		}.get(doctype, [])
		return service

	def scope(self, rows, environment):
		context = self.service(rows)._get_template_spec_context("TPL", environment_rating=environment)
		return context["env_spec_names"]

	def test_each_environment_resolves_only_its_own_and_untagged_specs(self):
		rows = [DRY, WET, ANY]
		self.assertEqual(self.scope(rows, "Dry"), [DRY.tape_spec, ANY.tape_spec])
		self.assertEqual(self.scope(rows, "Wet"), [WET.tape_spec, ANY.tape_spec])
		self.assertEqual(self.scope(rows, "Damp"), [ANY.tape_spec])
		self.assertEqual(self.scope(rows, None), [DRY.tape_spec, WET.tape_spec, ANY.tape_spec])

	def test_an_environment_without_a_spec_is_refused_instead_of_given_another_environments_tape(self):
		self.assertEqual(self.scope([DRY, WET], "Damp"), [])
		result = self.service([DRY, WET]).validate_tape_configuration(
			{"cct": "3000K", "output_level": "Standard", "environment_rating": "Damp"},
			tape_neon_template="TPL",
		)
		self.assertFalse(result["is_valid"])
		self.assertIn("has no tape spec for environment 'Damp'", result["error"])


if __name__ == "__main__":
	unittest.main()
