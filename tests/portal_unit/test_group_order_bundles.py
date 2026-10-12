"""Readable group part numbers and ordering a multi-run group as a bundle of built runs."""

import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.portal.production import production_coverage


class Line(Record):
	pass


def schedule(lines, before=None, project="P-1"):
	return Record(
		ill_project=project,
		lines=lines,
		get_doc_before_save=lambda: Record(lines=before) if before is not None else None,
	)


class GroupPartNumber(unittest.TestCase):
	def test_prefix_slugifies_and_omits_blank_segments(self):
		with load_service(ROOT + ".api.group_part_number") as (module, _):
			self.assertEqual(
				module.prefix("ILL-SH01-SW", "Smith Residence", "a1", "Lobby / North"),
				"ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-NORTH",
			)
			self.assertEqual(module.prefix("LED-HD-SW", "Smith", "", None), "LED-HD-SW-SMITH")
			self.assertEqual(module.segment("x" * 50), "X" * 30)

	def test_suffix_is_four_uppercase_letters_redrawn_only_on_collision(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			frappe.db.exists.side_effect = [True, False, False]
			code = module.generate("ILL-SH01-SW-SMITH")
			base, _, suffix = code.rpartition("-")
			self.assertEqual(base, "ILL-SH01-SW-SMITH")
			self.assertEqual(len(suffix), 4)
			self.assertTrue(suffix.isalpha() and suffix.isupper())
			self.assertEqual(frappe.db.exists.call_count, 3)

	def test_assign_keeps_numbers_until_naming_inputs_or_group_change(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			frappe.db.exists.return_value = False
			frappe.db.get_value.side_effect = lambda doctype, name, field: (
				"Smith Residence" if doctype == "ilL-Project" else "ILL-SH01-SW"
			)
			kept = Line(name="L1", configured_group="G", line_id="A1", location="Lobby",
				group_part_number="ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-ABCD")
			moved = Line(name="L2", configured_group="G", line_id="A1", location="Hall",
				group_part_number="ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-WXYZ")
			copied = Line(name="L3", configured_group="G", line_id="A1", location="Lobby",
				group_part_number="ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-ABCD")
			regrouped = Line(name="L4", configured_group="G2", line_id="A1", location="Lobby",
				group_part_number="ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-QRST")
			plain = Line(name="L5", configured_fixture="F", group_part_number="STALE")
			before = [Record(name=f"L{i}", configured_group="G") for i in range(1, 5)]
			module.assign(schedule([kept, moved, copied, regrouped, plain], before))
			self.assertEqual(kept.group_part_number, "ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-ABCD")
			self.assertEqual(kept.ill_item_code, kept.group_part_number)
			self.assertTrue(moved.group_part_number.startswith("ILL-SH01-SW-SMITH-RESIDENCE-A1-HALL-"))
			self.assertNotEqual(copied.group_part_number, kept.group_part_number)
			self.assertTrue(copied.group_part_number.startswith("ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-"))
			self.assertNotEqual(regrouped.group_part_number, "ILL-SH01-SW-SMITH-RESIDENCE-A1-LOBBY-QRST")
			self.assertIsNone(plain.group_part_number)


def _order_service(extra=None):
	with load_service(ROOT + ".api.build_artifacts") as (artifacts, _):
		pass
	return {ROOT + ".api.build_artifacts": artifacts, **(extra or {})}


class GroupOrderBundle(unittest.TestCase):
	def build(self, include=True, separate=False):
		return {
			"request": {
				"family": "Linear Fixture",
				"template": "ILL-SH01-SW",
				"power": {"include_power_supply": include, "separate_supply_line": separate},
			},
			"members": [
				{"member_key": key, "geometry": {}, "build": {"components": [
					{"item_code": "PROFILE", "stock_uom": "Foot", "qty": qty}]}}
				for key, qty in (("M1", 20), ("M2", 5), ("M3", 20))
			],
			"power_plan": {"drivers": [{"driver_item": "PS-96", "qty": 2}], "requirements": [1, 2, 3]},
			"total_watts": 180,
		}

	def test_bundle_holds_runs_and_only_group_supplied_drivers(self):
		with load_service(ROOT + ".api.fixture_group_order", _order_service()) as (module, _):
			members = [{"item_code": "RUN-20"}, {"item_code": "RUN-5"}, {"item_code": "RUN-20"}]
			self.assertEqual(
				module.bundle_rows(members, self.build()),
				[{"item_code": "RUN-20", "qty": 2}, {"item_code": "RUN-5", "qty": 1},
					{"item_code": "PS-96", "qty": 2}],
			)
			self.assertEqual(len(module.bundle_rows(members, self.build(separate=True))), 2)
			self.assertEqual(len(module.bundle_rows(members, self.build(include=False))), 2)

	def test_order_bundle_is_non_stock_company_branded_and_packs_built_runs(self):
		build = self.build()
		bom_module = types.SimpleNamespace(
			snapshot=lambda _doc: build,
			current_estimate=lambda _doc: 1234.5,
			description=lambda _build, _labels=None: "Linear Fixture multi-run group",
			run_noun=lambda _family, count=1: "runs",
		)
		generator = types.SimpleNamespace(
			_create_item_price_at_msrp=MagicMock(),
			_ensure_brand_exists=MagicMock(),
			_ensure_default_uom_exists=MagicMock(),
			_ensure_item_group_exists=MagicMock(),
		)
		display = types.SimpleNamespace(run_labels=lambda _line: {})
		extras = _order_service({
			ROOT + ".api.fixture_group_bom": bom_module,
			ROOT + ".api.manufacturing_generator": generator,
			ROOT + ".portal.group_display": display,
		})
		with load_service(ROOT + ".api.fixture_group_order", extras) as (module, frappe):
			group = Record(name="HASH", family="Linear Fixture", template="ILL-SH01-SW", engine_version="g1")
			inserted = []

			def get_doc(value, name=None):
				if isinstance(value, dict):
					doc = MagicMock()
					doc.insert.side_effect = lambda **_: inserted.append(value)
					return doc
				return group

			frappe.get_doc.side_effect = get_doc
			frappe.db.exists.return_value = False
			runs = iter([{"item_code": "RUN-20"}, {"item_code": "RUN-5"}, {"item_code": "RUN-20"}])
			line = Line(name="L1", configured_group="HASH", group_part_number="ILL-SH01-SW-SMITH-A1-LOBBY-ABCD")
			target = Record(company="ilLumenate Lighting")
			with patch.object(module, "build_member", side_effect=lambda *_: next(runs)):
				artifact = module.ensure_order_bundle(Record(), line, target)
			item, bundle = inserted
			self.assertEqual(item["item_code"], "ILL-SH01-SW-SMITH-A1-LOBBY-ABCD")
			self.assertEqual(item["is_stock_item"], 0)
			self.assertEqual(item["brand"], "ilLumenate Lighting")
			self.assertEqual(item["ill_configured_group"], "HASH")
			self.assertEqual(bundle["doctype"], "Product Bundle")
			self.assertEqual(bundle["new_item_code"], item["item_code"])
			self.assertEqual([r["item_code"] for r in bundle["items"]], ["RUN-20", "RUN-5", "PS-96"])
			generator._create_item_price_at_msrp.assert_called_once_with(item["item_code"], 1234.5, [])
			self.assertEqual(artifact["item_code"], item["item_code"])
			self.assertIsNone(artifact["bom"])
			self.assertEqual(artifact["configured_group"], "HASH")

	def test_run_must_keep_the_materials_its_group_pinned(self):
		saved = Record(doctype="ilL-Configured-Fixture", name="CF")
		portal = types.SimpleNamespace(persist_artifact=MagicMock(return_value={
			"source_doctype": "ilL-Configured-Fixture", "source_name": "CF", "item_code": "RUN", "bom": "BOM-RUN"}))
		configurator = types.SimpleNamespace(member_payload=MagicMock(return_value={}))
		extras = _order_service({
			ROOT + ".portal.configuration": portal,
			ROOT + ".api.fixture_group_configurator": configurator,
		})
		with load_service(ROOT + ".api.fixture_group_order", extras) as (module, frappe):
			frappe.get_doc.return_value = saved
			member = {"geometry": {}, "build": {"components": [{"item_code": "P", "stock_uom": "Foot", "qty": 20}]}}
			request = {"family": "Linear Fixture"}
			with patch.object(module, "member_snapshot", return_value=member["build"]):
				self.assertEqual(module.build_member(request, member, "Run 1")["item_code"], "RUN")
			configurator.member_payload.assert_called_with(request, {}, standalone=True)
			drifted = {"components": [{"item_code": "P", "stock_uom": "Foot", "qty": 21}]}
			with patch.object(module, "member_snapshot", return_value=drifted):
				with self.assertRaisesRegex(ValueError, "Run 1 no longer builds"):
					module.build_member(request, member, "Run 1")


class BundleProduction(unittest.TestCase):
	def test_one_work_order_per_run_for_unplanned_demand(self):
		with load_service(ROOT + ".api.build_artifacts") as (artifacts, _):
			with load_service(ROOT + ".api.manufacturing_order", {ROOT + ".api.build_artifacts": artifacts}) as (
				module,
				frappe,
			):
				order = Record(name="SO", company="Company")
				row = Record(name="ROW", item_code="ILL-SH01-SW-P-A1-L-ABCD", qty=2, conversion_factor=1,
					ill_configured_group="HASH")
				members = [
					("ilL-Configured-Fixture", Record(name="CF1", configured_item="RUN-20", bom="B20"), 2.0),
					("ilL-Configured-Fixture", Record(name="CF2", configured_item="RUN-5", bom="B5"), 1.0),
				]
				frappe.get_all.return_value = [
					Record(name="WO1", production_item="RUN-20", bom_no="B20", qty=4, status="Draft")
				]
				frappe.get_meta = MagicMock()
				frappe.get_meta.return_value.has_field.return_value = True
				created = []
				work = MagicMock()
				work.name = "WO2"
				frappe.get_doc.side_effect = lambda value, *a: created.append(value) or work if isinstance(
					value, dict) else Record(item="X")
				group_order = types.SimpleNamespace(
					bundle_members=lambda _code: members,
					MEMBER_SOURCES=(("ilL-Configured-Fixture", "linear_build", "ill_configured_fixture"),),
					member_snapshot=lambda _doctype, _doc: {"components": []},
				)
				with (
					patch.dict("sys.modules", {ROOT + ".api.fixture_group_order": group_order}),
					patch.object(module, "assert_bom"),
				):
					result = module.create_for_line(order, row)
				self.assertTrue(result["created"]["work_order"])
				self.assertEqual(len(created), 1)
				data = created[0]
				self.assertEqual(data["production_item"], "RUN-5")
				self.assertEqual(data["qty"], 2)
				self.assertEqual(data["bom_no"], "B5")
				self.assertEqual(data["product_bundle_item"], row.item_code)
				self.assertEqual(data["ill_configured_fixture"], "CF2")
				self.assertEqual(data["ill_configured_group"], "HASH")

	def test_bundle_line_is_complete_only_when_every_run_is_built(self):
		lines = [dict(name="G", item_code="GRP", qty=2, ill_configured_group="HASH")]
		bundles = {"G": {"RUN-20": 2.0, "RUN-5": 1.0}}
		work = [
			{"name": "W1", "sales_order_item": "G", "production_item": "RUN-20", "qty": 4, "produced_qty": 4},
			{"name": "W2", "sales_order_item": "G", "production_item": "RUN-5", "qty": 2, "produced_qty": 1},
		]
		coverage = production_coverage(lines, work, bundles)
		self.assertEqual(coverage["lines"][0]["planned_stock_qty"], 2)
		self.assertEqual(coverage["lines"][0]["produced_qty"], 1)
		self.assertFalse(coverage["complete"])
		work[1]["produced_qty"] = 2
		self.assertTrue(production_coverage(lines, work, bundles)["complete"])


class BundleDrawingScope(unittest.TestCase):
	def test_schedule_drawing_covers_the_lines_own_group_bundle(self):
		with load_service(ROOT + ".portal.drawing_impact") as (service, frappe):
			line = Line(name="LINE", qty=1, configured_group="HASH", line_id="A1", location="Lobby",
				group_part_number="ILL-SH01-SW-P-A1-LOBBY-ABCD")
			item = Line(ill_schedule_line_id="LINE", qty=1, ill_configured_group="HASH",
				item_code="ILL-SH01-SW-P-A1-LOBBY-ABCD", ill_fixture_type="A1", ill_section_label="Lobby",
				conversion_factor=1)
			frappe.get_doc.return_value = Record(name="HASH", configured_item="ILL-GRP-HASH", bom="GB")
			frappe.db.get_value.return_value = "HASH"
			order, sched = Record(items=[item]), Record(lines=[line])
			self.assertTrue(service.order_matches_schedule(order, sched))
			frappe.db.get_value.return_value = "OTHER"
			self.assertFalse(service.order_matches_schedule(order, sched))
			frappe.db.get_value.return_value = "HASH"
			item["item_code"] = "SOMETHING-ELSE"
			self.assertFalse(service.order_matches_schedule(order, sched))


if __name__ == "__main__":
	unittest.main()
