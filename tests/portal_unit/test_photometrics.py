"""Templates copy beam angle, charts, cone of light and the TM-30 chart from linked records."""

import unittest
from unittest.mock import MagicMock

from test_services import ROOT, load_service

FIXTURE = "ilL-Fixture-Template"


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class Doc(Row):
	def get(self, key, default=None):
		value = super().get(key, default)
		return (
			[row if isinstance(row, Row) else Row(row) for row in value] if isinstance(value, list) else value
		)

	def set(self, key, value):
		self[key] = value

	def append(self, key, row):
		self.setdefault(key, []).append(Row(row))


def meta(*fields):
	return MagicMock(has_field=lambda field: field in fields)


TEMPLATE_FIELDS = (
	"photometry",
	"beam_angle",
	"photometric_image",
	"polar_chart_image",
	"photometric_data",
	"tm30_chart_image",
	"colorimetry",
)
CONE = [
	{"mounting_height": "4 ft", "light_level": "11 fc", "beam_diameter": "13.9 ft", "display_order": 2},
	{"mounting_height": "2 ft", "light_level": "45 fc", "beam_diameter": "6.9 ft", "display_order": 1},
]


def photometry(**values):
	return Doc(
		doctype="ilL-Spec-Photometry",
		name="PH-1",
		beam_angle=120,
		photometric_image="/files/photo.png",
		polar_chart_image="/files/polar.png",
		photometric_data=CONE,
		**values,
	)


class ApplyToTemplate(unittest.TestCase):
	def run_apply(self, template, record=None, tm30=None):
		with load_service(ROOT + ".photometrics") as (module, frappe):
			frappe.get_meta = MagicMock(return_value=meta(*TEMPLATE_FIELDS))
			frappe.get_doc.return_value = record or photometry()
			frappe.db.get_value.return_value = tm30
			module.apply_to_template(template)
			return frappe

	def test_linked_photometry_overwrites_the_template_copies(self):
		template = Doc(doctype=FIXTURE, photometry="PH-1", beam_angle=90, photometric_data=[])
		self.run_apply(template)
		self.assertEqual(template.beam_angle, 120)
		self.assertEqual(template.polar_chart_image, "/files/polar.png")
		self.assertEqual([row["mounting_height"] for row in template.photometric_data], ["2 ft", "4 ft"])

	def test_unchanged_cone_rows_are_kept_as_they_are(self):
		rows = [
			Row(row, name=f"row-{i}") for i, row in enumerate(sorted(CONE, key=lambda r: r["display_order"]))
		]
		template = Doc(doctype=FIXTURE, photometry="PH-1", photometric_data=rows)
		self.run_apply(template)
		self.assertEqual([row.name for row in template.photometric_data], ["row-0", "row-1"])

	def test_without_a_link_the_template_keeps_its_own_values(self):
		template = Doc(doctype=FIXTURE, beam_angle=90, photometric_image="/files/own.png")
		frappe = self.run_apply(template)
		self.assertEqual(template.beam_angle, 90)
		self.assertEqual(template.photometric_image, "/files/own.png")
		frappe.get_doc.assert_not_called()

	def test_first_colorimetry_row_is_featured_and_supplies_the_tm30_chart(self):
		template = Doc(doctype=FIXTURE, colorimetry=[Row(colorimetry="C-2700"), Row(colorimetry="C-4000")])
		frappe = self.run_apply(template, tm30="/files/tm30-2700.png")
		self.assertEqual(template.colorimetry[0].is_featured, 1)
		self.assertFalse(template.colorimetry[1].get("is_featured"))
		self.assertEqual(template.tm30_chart_image, "/files/tm30-2700.png")
		self.assertEqual(frappe.db.get_value.call_args.args[:2], ("ilL-Spec-Colorimetry", "C-2700"))

	def test_marked_row_wins_over_the_first(self):
		template = Doc(
			doctype=FIXTURE,
			colorimetry=[Row(colorimetry="C-2700"), Row(colorimetry="C-4000", is_featured=1)],
		)
		frappe = self.run_apply(template, tm30="/files/tm30-4000.png")
		self.assertEqual(frappe.db.get_value.call_args.args[1], "C-4000")
		self.assertFalse(template.colorimetry[0].get("is_featured"))

	def test_two_featured_rows_or_a_repeated_record_are_refused(self):
		for rows in (
			[Row(colorimetry="C-2700", is_featured=1), Row(colorimetry="C-4000", is_featured=1)],
			[Row(colorimetry="C-2700"), Row(colorimetry="C-2700")],
		):
			with self.subTest(rows=rows), self.assertRaises(Exception):
				self.run_apply(Doc(doctype=FIXTURE, colorimetry=rows))

	def test_no_colorimetry_leaves_the_tm30_chart_editable(self):
		template = Doc(doctype=FIXTURE, colorimetry=[], tm30_chart_image="/files/own.png")
		self.run_apply(template)
		self.assertEqual(template.tm30_chart_image, "/files/own.png")


class RefreshTemplates(unittest.TestCase):
	def test_photometry_change_resaves_every_linking_template(self):
		with load_service(ROOT + ".photometrics") as (module, frappe):
			frappe.get_meta = MagicMock(return_value=meta("photometry"))
			frappe.get_all.side_effect = lambda doctype, **kw: ["T-1"] if doctype == FIXTURE else []
			template = MagicMock()
			frappe.get_doc.return_value = template
			self.assertEqual(module.refresh_templates(Doc(doctype="ilL-Spec-Photometry", name="PH-1")), [])
			template.save.assert_called_once()
			self.assertEqual(frappe.get_all.call_args_list[0].kwargs["filters"], {"photometry": "PH-1"})

	def test_colorimetry_finds_templates_through_their_rows(self):
		with load_service(ROOT + ".photometrics") as (module, frappe):
			frappe.get_all.return_value = [
				Row(parenttype=FIXTURE, parent="T-1"),
				Row(parenttype="ilL-LED-Sheet-Template", parent="S-1"),
			]
			pairs = module.linked_templates("ilL-Spec-Colorimetry", "C-2700")
			self.assertEqual(pairs, [(FIXTURE, "T-1"), ("ilL-LED-Sheet-Template", "S-1")])
			self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["colorimetry"], "C-2700")

	def test_a_template_that_fails_validation_is_reported_not_raised(self):
		with load_service(ROOT + ".photometrics") as (module, frappe):
			frappe.get_meta = MagicMock(return_value=meta("photometry"))
			frappe.get_all.side_effect = lambda doctype, **kw: ["T-1"] if doctype == FIXTURE else []
			frappe.get_doc.return_value.save.side_effect = ValueError("invalid template")
			frappe.log_error = MagicMock()
			failed = module.refresh_templates(Doc(doctype="ilL-Spec-Photometry", name="PH-1"))
			self.assertEqual(failed, ["T-1"])
			self.assertIn("T-1", frappe.msgprint.call_args.args[0])


if __name__ == "__main__":
	unittest.main()


class Migration(unittest.TestCase):
	PATCH = "illumenate_lighting.patches.migrate_photometrics_to_spec_records"

	def test_template_values_move_into_a_record_named_after_it(self):
		with load_service(self.PATCH) as (module, frappe):
			frappe.db.exists.return_value = False
			record = MagicMock(name="record")
			record.name = "ILL-EL01"
			frappe.get_doc.return_value = record
			template = Doc(doctype=FIXTURE, name="ILL-EL01", template_name="Elevate", beam_angle=120)
			self.assertEqual(module.migrate_photometry(template, meta(*TEMPLATE_FIELDS)), [])
			values = frappe.get_doc.call_args.args[0]
			self.assertEqual(values["photometry_code"], "ILL-EL01")
			self.assertEqual(values["beam_angle"], 120)
			record.insert.assert_called_once()
			frappe.db.set_value.assert_called_once_with(
				FIXTURE, "ILL-EL01", "photometry", "ILL-EL01", update_modified=False
			)

	def test_templates_with_nothing_to_move_or_already_linked_are_skipped(self):
		with load_service(self.PATCH) as (module, frappe):
			for template in (
				Doc(doctype=FIXTURE, name="EMPTY", photometric_data=[]),
				Doc(doctype=FIXTURE, name="DONE", photometry="PH-1", beam_angle=120),
			):
				self.assertEqual(module.migrate_photometry(template, meta(*TEMPLATE_FIELDS)), [])
			frappe.get_doc.assert_not_called()

	def test_tm30_chart_becomes_the_featured_colorimetry_row(self):
		with load_service(self.PATCH) as (module, frappe):
			frappe.db.exists.return_value = False
			frappe.get_all.side_effect = [["PKG-SW"], ["2700K", "2700K"]]
			record = MagicMock()
			record.name = "TN-1"
			frappe.get_doc.return_value = record
			template = Doc(
				doctype="ilL-Tape-Neon-Template",
				name="TN-1",
				tm30_chart_image="/files/tm30.png",
				allowed_tape_specs=[{"tape_spec": "TAPE-1"}],
			)
			self.assertEqual(module.migrate_colorimetry(template, meta(*TEMPLATE_FIELDS)), [])
			created, row = (call.args[0] for call in frappe.get_doc.call_args_list)
			self.assertEqual((created["led_package"], created["cct"]), ("PKG-SW", "2700K"))
			self.assertEqual(created["tm30_chart_image"], "/files/tm30.png")
			self.assertEqual((row["parent"], row["is_featured"], row["colorimetry"]), ("TN-1", 1, "TN-1"))

	def test_unresolved_source_is_listed_for_review(self):
		with load_service(self.PATCH) as (module, frappe):
			frappe.db.exists.return_value = False
			frappe.get_all.side_effect = [["PKG-SW"], ["2700K", "4000K"]]
			frappe.get_doc.return_value.name = "TN-1"
			template = Doc(
				doctype="ilL-Tape-Neon-Template",
				name="TN-1",
				tm30_chart_image="/files/tm30.png",
				allowed_tape_specs=[{"tape_spec": "TAPE-1"}],
			)
			review = module.migrate_colorimetry(template, meta(*TEMPLATE_FIELDS))
			self.assertIn("set the LED package and CCT", review[0])

	def test_matching_beam_angle_only_records_are_flagged(self):
		with load_service(self.PATCH) as (module, frappe):
			frappe.get_all.return_value = [
				Row(name="A", beam_angle=120.0),
				Row(name="B", beam_angle=120.0),
				Row(name="C", beam_angle=120.0, polar_chart_image="/files/p.png"),
			]
			self.assertEqual(len(module.shared_beam_angles()), 1)
			self.assertIn("A, B", module.shared_beam_angles()[0])


class SubmittalRecord(unittest.TestCase):
	def resolve(self, doctype, template, cct=None):
		with load_service(ROOT + ".photometrics") as (module, frappe):
			frappe.get_cached_doc = MagicMock(side_effect=lambda dt, name: (dt, name))
			return module.submittal_record(doctype, template, cct)

	def test_photometry_is_the_template_link(self):
		self.assertEqual(
			self.resolve("ilL-Spec-Photometry", Doc(photometry="PH-1")), ("ilL-Spec-Photometry", "PH-1")
		)
		self.assertIsNone(self.resolve("ilL-Spec-Photometry", Doc()))
		self.assertIsNone(self.resolve("ilL-Spec-Photometry", None))

	def test_colorimetry_follows_the_configured_cct_then_the_featured_row(self):
		template = Doc(
			colorimetry=[
				Row(colorimetry="C-2700", cct="2700K"),
				Row(colorimetry="C-4000", cct="4000K", is_featured=1),
			]
		)
		self.assertEqual(self.resolve("ilL-Spec-Colorimetry", template, "2700K")[1], "C-2700")
		self.assertEqual(self.resolve("ilL-Spec-Colorimetry", template, "3500K")[1], "C-4000")
		self.assertEqual(self.resolve("ilL-Spec-Colorimetry", template)[1], "C-4000")
		self.assertIsNone(self.resolve("ilL-Spec-Colorimetry", Doc(colorimetry=[])))


class Published(unittest.TestCase):
	def publish(self, template, records):
		with load_service(ROOT + ".photometrics") as (module, frappe):
			frappe.get_meta = MagicMock(return_value=meta(*TEMPLATE_FIELDS))
			frappe.db.get_value.side_effect = lambda doctype, name, fields, as_dict: (
				Row(records[name]) if name in records else None
			)
			return module.published(template)

	def test_cone_rows_and_charts_keep_their_payload_shape(self):
		data = self.publish(Doc(doctype=FIXTURE, photometric_image="/files/p.png", photometric_data=CONE), {})
		self.assertEqual(data["photometric_image"], "/files/p.png")
		self.assertEqual([row["mounting_height"] for row in data["photometric_data"]], ["2 ft", "4 ft"])
		self.assertEqual(
			list(data["photometric_data"][0]),
			["mounting_height", "light_level", "beam_diameter", "display_order"],
		)
		self.assertNotIn("colorimetry", data)

	def test_ies_file_comes_from_an_active_photometry_record(self):
		template = Doc(doctype=FIXTURE, photometry="PH-1")
		data = self.publish(
			template, {"PH-1": {"is_active": 1, "ies_file": "/files/a.ies", "ldt_file": None}}
		)
		self.assertEqual(data, {"ies_file": "/files/a.ies"})
		self.assertEqual(self.publish(template, {"PH-1": {"is_active": 0, "ies_file": "/files/a.ies"}}), {})

	def test_colorimetry_lists_measured_rows_per_cct(self):
		template = Doc(
			doctype=FIXTURE,
			colorimetry=[
				Row(colorimetry="C-2700", cct="2700K", is_featured=1),
				Row(colorimetry="C-3000", cct="3000K"),
				Row(colorimetry="C-4000", cct="4000K"),
				Row(colorimetry="C-OLD", cct="5000K"),
			],
		)
		data = self.publish(
			template,
			{
				"C-2700": {
					"is_active": 1,
					"cct": "2700K",
					"ra": 95.2,
					"r9": 60,
					"tm30_chart_image": "/files/t.png",
				},
				# A migrated chart with no measurements yet stays out of the payload.
				"C-3000": {"is_active": 1, "cct": "3000K", "ra": 0, "tm30_chart_image": "/files/t3.png"},
				"C-4000": {"is_active": 1, "cct": "4000K", "tm30_rf": 91},
				"C-OLD": {"is_active": 0, "cct": "5000K", "ra": 90},
			},
		)
		self.assertEqual(
			data["colorimetry"],
			[
				{"cct": "2700K", "is_featured": 1, "ra": 95.2, "r9": 60, "tm30_chart_image": "/files/t.png"},
				{"cct": "4000K", "is_featured": 0, "tm30_rf": 91},
			],
		)

	def test_no_template_publishes_nothing(self):
		self.assertEqual(self.publish(None, {}), {})
