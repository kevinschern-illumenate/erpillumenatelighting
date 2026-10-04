"""A disabled Item is never offered, priced or built."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

DISABLED = {"PROFILE-OLD", "TAPE-OLD", "PANEL-OLD", "DRIVER-OLD", "LENS-OLD", "CLIP-OLD"}


def document_module():
	module = types.ModuleType("frappe.model.document")
	module.Document = object
	return module


def wire(frappe):
	"""Answer the Item and joined-spec lookups from DISABLED."""
	frappe.db.get_all.side_effect = lambda doctype, filters=None, pluck=None, **kwargs: [
		code for code in filters["name"][1] if code in DISABLED
	]

	def sql(query, values):
		if "tabilL-Rel-Tape Offering" in query:
			return [(name,) for name in values["names"] if name.startswith("OLD-")]
		return [(name,) for name in values["names"] if name in DISABLED]

	frappe.db.sql.side_effect = sql


class Helpers(unittest.TestCase):
	def test_rows_and_names_lose_disabled_items_and_keep_order(self):
		with load_service(ROOT + ".api.item_availability") as (availability, frappe):
			wire(frappe)
			rows = [Record(item="TAPE-OLD"), Record(item="TAPE-NEW"), Record(item=None)]
			self.assertEqual(availability.enabled_rows(rows), rows[1:])
			self.assertEqual(
				availability.enabled_tape_specs(["TAPE-NEW", "TAPE-OLD", "TAPE-2"]), ["TAPE-NEW", "TAPE-2"]
			)
			template = Record(
				allowed_tape_offerings=[Record(tape_offering="OLD-30K"), Record(tape_offering="NEW-30K")]
			)
			self.assertEqual(
				availability.allowed_tape_offering_rows(template), template.allowed_tape_offerings[1:]
			)
			with self.assertRaisesRegex(
				ValueError, "LENS-OLD is a disabled Item and cannot be used in this fixture"
			):
				availability.assert_enabled(["LENS-OLD", "LENS-NEW"], "this fixture")
			availability.assert_enabled(["LENS-NEW", None])

	def test_nothing_is_queried_when_there_is_nothing_to_check(self):
		with load_service(ROOT + ".api.item_availability") as (availability, frappe):
			self.assertEqual(availability.enabled_rows([Record(item=None)]), [Record(item=None)])
			self.assertEqual(availability.enabled_tape_specs([]), [])
			frappe.db.get_all.assert_not_called()
			frappe.db.sql.assert_not_called()


class Configurators(unittest.TestCase):
	def test_a_tape_template_never_resolves_to_a_disabled_spec(self):
		rollout = types.SimpleNamespace(require_configuration=lambda family: None)
		with load_service(ROOT + ".api.tape_neon_configurator", {ROOT + ".portal.rollout": rollout}) as (
			service,
			frappe,
		):
			wire(frappe)
			frappe.db.get_value.return_value = Record(is_free_cutting=0, default_tape_spec="TAPE-OLD")
			frappe.get_all.return_value = [
				Record(tape_spec="TAPE-OLD", environment_rating="Dry", is_default=1),
				Record(tape_spec="TAPE-NEW", environment_rating="Dry", is_default=0),
			]
			context = service._get_template_spec_context("TPL", environment_rating="Dry")
		self.assertEqual(context["spec_names"], ["TAPE-NEW"])
		self.assertEqual(context["env_spec_names"], ["TAPE-NEW"])

	def test_a_sheet_template_never_offers_a_disabled_panel(self):
		panels = {
			"OLD": Record(is_active=1, item="PANEL-OLD", cct=None),
			"NEW": Record(is_active=1, item="PANEL-NEW", cct=None),
		}
		with load_service(ROOT + ".api.led_sheet_configurator") as (service, frappe):
			wire(frappe)
			frappe.get_doc.side_effect = lambda doctype, name: panels[name]
			template = Record(
				name="SHEET",
				allowed_specs=[Record(spec="OLD", is_active=1), Record(spec="NEW", is_active=1)],
				allowed_options=[],
			)
			self.assertEqual(service.resolve_sheet_spec(template, {}), "NEW")
			frappe.throw = MagicMock(side_effect=ValueError)
			with self.assertRaises(ValueError):
				service.resolve_sheet_spec(template, {}, "OLD")

	def test_a_driver_variant_with_a_disabled_item_cannot_be_configured(self):
		extras = {"frappe.model.document": document_module()}
		with load_service(ROOT + ".api.driver_controller_configurator", extras) as (service, frappe):
			wire(frappe)
			template = Record(
				variants=[Record(item="DRIVER-OLD", is_active=1), Record(item="DRIVER-NEW", is_active=1)]
			)
			matches = service._matching_variants(template, [], {}, {}, partial=True)
		self.assertEqual([v.item for v in matches], ["DRIVER-NEW"])

	def test_a_disabled_lens_is_not_compatible_with_any_profile(self):
		with load_service(ROOT + ".utils") as (utils, frappe):
			wire(frappe)
			frappe.get_all.side_effect = [
				[Record(name="REL")],
				[
					Record(lens_spec="L1", lens_item="LENS-OLD", lens_appearance="Frosted", is_default=1),
					Record(lens_spec="L2", lens_item="LENS-NEW", lens_appearance="Frosted", is_default=0),
				],
			]
			lenses = utils.get_compatible_lenses_for_profile("PROFILE", "Frosted")
		self.assertEqual([lens.lens_item for lens in lenses], ["LENS-NEW"])


class Builds(unittest.TestCase):
	def test_a_linear_fixture_built_from_a_disabled_item_is_refused(self):
		class Fixture(Record):
			__setattr__ = dict.__setitem__

			def _renumber_user_segments(self):
				pass

			def before_save(self):
				pass

			def _generate_part_number(self):
				return "ILL-SH01-SW-20"

		material = types.SimpleNamespace(
			build_fixture_bom_items=lambda doc: [{"item_code": "PROFILE-OLD", "qty": 1, "stock_uom": "Nos"}]
		)
		with load_service(ROOT + ".api.linear_build", {ROOT + ".api.manufacturing_generator": material}) as (
			engine,
			frappe,
		):
			wire(frappe)
			frappe.db.get_value.return_value = Record(stock_uom="Foot", disabled=0)
			fixture = Fixture(
				leader_item="WIRE",
				is_multi_segment=0,
				segments=[Record(segment_index=1, start_leader_len_mm=300, start_leader_item="WIRE")],
				runs=[Record(run_index=1, leader_item="WIRE", leader_len_mm=300)],
				flags=Record(),
			)
			with self.assertRaisesRegex(ValueError, "PROFILE-OLD is a disabled Item"):
				engine.finish(fixture, {}, {}, {}, True, None, in_memory=True)


class Schedules(unittest.TestCase):
	def schedule(self, before_lines, lines):
		with load_service(
			ROOT + ".doctype.ill_project_fixture_schedule.ill_project_fixture_schedule",
			{"frappe.model.document": document_module()},
		) as (module, frappe):
			wire(frappe)
			schedule = module.ilLProjectFixtureSchedule()
			schedule.get = lambda field: {"lines": lines}.get(field)
			before = Record(lines=before_lines) if before_lines is not None else None
			schedule.get_doc_before_save = lambda: before
			schedule._reject_newly_added_disabled_items()

	def test_a_line_cannot_take_on_a_disabled_item(self):
		with self.assertRaisesRegex(ValueError, "CLIP-OLD is a disabled Item"):
			self.schedule([], [Record(name="row1", accessory_item="CLIP-OLD")])
		with self.assertRaisesRegex(ValueError, "CLIP-OLD"):
			self.schedule(
				[Record(name="row1", accessory_item="CLIP-NEW")],
				[Record(name="row1", accessory_item="CLIP-OLD")],
			)

	def test_a_schedule_already_carrying_a_now_disabled_item_can_still_be_edited(self):
		line = Record(name="row1", accessory_item="CLIP-OLD")
		self.schedule([line], [line, Record(name="row2", accessory_item="CLIP-NEW")])


if __name__ == "__main__":
	unittest.main()
