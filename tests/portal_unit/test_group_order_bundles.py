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


HASH = "a1b2c3d4e5f6" + "0" * 52


def linear_member(part_number, *lengths_mm):
	return {"geometry": {"segments": [{"requested_length_mm": mm} for mm in lengths_mm]},
		"build": {"part_number": part_number}}


def tape_member(part_number, *lengths_mm):
	segments = [{"manufacturable_length_mm": mm, "manufacturable_length_in": round(mm / 25.4, 2)}
		for mm in lengths_mm]
	return {"geometry": {"segments": [{"requested_length_mm": mm} for mm in lengths_mm]},
		"build": {"part_number": part_number, "computed": {
			"manufacturable_length_mm": sum(lengths_mm), "segments": segments}}}


def sheet_member(part_number, width, height):
	return {"geometry": {"coverage_width_ft": width, "coverage_height_ft": height},
		"build": {"part_number": part_number}}


def group_build(family, members, template="TPL"):
	return {"request": {"family": family, "template": template}, "members": members}


def free(frappe, items=None):
	"""Item codes in ``items`` exist with the given owner group; nothing else is taken."""
	items = items or {}
	frappe.db.exists.side_effect = lambda doctype, name: doctype == "Item" and name in items
	frappe.db.get_value.side_effect = lambda doctype, name, field: items.get(name)


class GroupPartNumber(unittest.TestCase):
	LINEAR = "ILL-SH01-HD-DR-30-HO-FR-SM-WH"

	def test_run_prefix_strips_the_length_and_feed_segments_of_every_family(self):
		with load_service(ROOT + ".api.group_part_number") as (module, _):
			cases = [
				("Linear Fixture", linear_member(self.LINEAR + "-120.0-E10-C", 3048), self.LINEAR),
				("Linear Fixture", linear_member(self.LINEAR + "-144.0-L6-R4", 3657.6), self.LINEAR),
				("Linear Fixture", linear_member(self.LINEAR + "-144.0-J(1A2B)", 2438.4, 1219.2), self.LINEAR),
				("LED Tape", tape_member("TAPE-27-HO-120-E10-C", 3048), "TAPE-27-HO"),
				# A feed segment with no type code must not be read as the length.
				("LED Tape", tape_member("TAPE-27-HO-120-10-C", 3048), "TAPE-27-HO"),
				("LED Tape", tape_member("TAPE-120-C", 3048), "TAPE"),
				("LED Neon", tape_member("NEON-27-96.5-J(FFFF)", 1219.2, 1231.9), "NEON-27"),
				("LED Sheet", sheet_member("LS01-DR-30-HO-AD-WH", 4, 6), "LS01-DR-30-HO-AD-WH"),
			]
			for family, member, prefix in cases:
				self.assertEqual(module.run_prefix(family, member), prefix, member["build"]["part_number"])
			self.assertIsNone(module.run_prefix("LED Tape", {"geometry": {}, "build": {}}))

	def test_total_length_sums_every_run_in_the_familys_format(self):
		with load_service(ROOT + ".api.group_part_number") as (module, _):
			linear = [linear_member("", 2438.4), linear_member("", 609.6, 609.6)]
			self.assertEqual(module.total_length("Linear Fixture", linear), "144.0")
			tape = [tape_member("", 3048), tape_member("", 1270)]
			self.assertEqual(module.total_length("LED Tape", tape), "170")
			self.assertEqual(module.total_length("LED Neon", [tape_member("", 1257.3)]), "49.5")
			sheets = [sheet_member("", 4, 6), sheet_member("", 2.5, 5)]
			self.assertEqual(module.total_length("LED Sheet", sheets), "36.5SF")

	def test_group_number_is_prefix_total_length_and_hash_code(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			free(frappe)
			build = group_build("Linear Fixture", [
				linear_member(self.LINEAR + "-96.0-E10-C", 2438.4),
				linear_member(self.LINEAR + "-48.0-E2-C", 1219.2),
			])
			group = Record(name="G", config_hash=HASH)
			self.assertEqual(module.for_group(group, build), self.LINEAR + "-144.0-GRP(A1B2)")
			sheet = group_build("LED Sheet", [sheet_member("LS01-DR-30-HO-AD-WH", 4, 6)] * 2)
			self.assertEqual(module.for_group(group, sheet), "LS01-DR-30-HO-AD-WH-48SF-GRP(A1B2)")

	def test_one_run_group_matches_the_standalone_part_number_with_a_group_tail(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			free(frappe)
			group = Record(name="G", config_hash=HASH)
			for family, member, standalone_tail in (
				("Linear Fixture", linear_member(self.LINEAR + "-120.0-E10-C", 3048), "-E10-C"),
				("LED Tape", tape_member("TAPE-27-HO-120-E10-C", 3048), "-E10-C"),
				("LED Neon", tape_member("NEON-27-48-J(AAAA)", 609.6, 609.6), "-J(AAAA)"),
			):
				standalone = member["build"]["part_number"]
				expected = standalone[: -len(standalone_tail)] + "-GRP(A1B2)"
				self.assertEqual(module.for_group(group, group_build(family, [member])), expected)

	def test_code_grows_only_when_another_group_holds_it(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			build = group_build("LED Tape", [tape_member("TAPE-120-C", 3048)])
			group = Record(name="G", config_hash=HASH)
			free(frappe, {"TAPE-120-GRP(A1B2)": "OTHER"})
			self.assertEqual(module.for_group(group, build), "TAPE-120-GRP(A1B2C)")
			free(frappe, {"TAPE-120-GRP(A1B2)": "G"})
			self.assertEqual(module.for_group(group, build), "TAPE-120-GRP(A1B2)")
			self.assertEqual(module.for_group(group, build, accept=lambda code: False), "TAPE-120-GRP(A1B2C)")

	def test_a_run_without_a_part_number_falls_back_to_the_template(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			free(frappe)
			build = group_build("LED Tape", [tape_member("", 3048)], template="Shelf Tape")
			self.assertEqual(module.for_group(Record(name="G", config_hash=HASH), build),
				"SHELF-TAPE-120-GRP(A1B2)")

	def test_assign_keeps_quoted_numbers_and_numbers_new_or_changed_groups(self):
		with load_service(ROOT + ".api.group_part_number") as (module, frappe):
			free(frappe, {"OLD-FORMAT-ABCD": "G", "G2-NUMBER": "G2"})
			numbers = {"G": "NEW-G-GRP(A1B2)", "G2": "NEW-G2-GRP(C3D4)"}
			frappe.get_doc.side_effect = lambda doctype, name: Record(name=name)
			legacy = Line(name="L1", configured_group="G", group_part_number="OLD-FORMAT-ABCD")
			copied = Line(name="L2", configured_group="G", group_part_number="OLD-FORMAT-ABCD")
			fresh = Line(name="L3", configured_group="G")
			regrouped = Line(name="L4", configured_group="G2", group_part_number="OLD-FORMAT-ABCD")
			desk = Line(name="L5", configured_group="G2", group_part_number="G2-NUMBER")
			plain = Line(name="L6", configured_fixture="F", group_part_number="STALE")
			before = [Record(name="L1", configured_group="G"), Record(name="L4", configured_group="G"),
				Record(name="L5", configured_group="G")]
			with patch.object(module, "for_group", side_effect=lambda group: numbers[group.name]) as made:
				module.assign(schedule([legacy, copied, fresh, regrouped, desk, plain], before))
			self.assertEqual(legacy.ill_item_code, "OLD-FORMAT-ABCD")
			self.assertEqual(copied.ill_item_code, "OLD-FORMAT-ABCD")
			self.assertEqual(fresh.group_part_number, "NEW-G-GRP(A1B2)")
			self.assertEqual(fresh.ill_item_code, "NEW-G-GRP(A1B2)")
			self.assertEqual(regrouped.group_part_number, "NEW-G2-GRP(C3D4)")
			# A line moved to a group whose bundle already carries its number keeps it.
			self.assertEqual(desk.ill_item_code, "G2-NUMBER")
			self.assertIsNone(plain.group_part_number)
			self.assertEqual(made.call_count, 2)


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
			group_item_prefix=lambda _group: "Shelf Light",
			run_noun=lambda _family, count=1: "runs",
		)
		generator = types.SimpleNamespace(
			_create_item_price_at_msrp=MagicMock(),
			_ensure_brand_exists=MagicMock(),
			_ensure_default_uom_exists=MagicMock(),
			_ensure_item_group_exists=MagicMock(),
		)
		extras = _order_service({
			ROOT + ".api.fixture_group_bom": bom_module,
			ROOT + ".api.manufacturing_generator": generator,
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
				artifact = module.ensure_order_bundle("HASH", {}, target, line=line)
			item, bundle = inserted
			self.assertEqual(item["item_code"], "ILL-SH01-SW-SMITH-A1-LOBBY-ABCD")
			self.assertEqual(item["item_name"], "Shelf Light multi-run group (3 runs)")
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

	def test_part_number_without_a_schedule_line_is_the_groups_own(self):
		numbering = types.SimpleNamespace(for_group=MagicMock(return_value="ILL-X-144.0-GRP(A1B2)"))
		extras = _order_service({ROOT + ".api.group_part_number": numbering})
		with load_service(ROOT + ".api.fixture_group_order", extras) as (module, frappe):
			group = Record(name="HASH")
			frappe.db.exists.return_value = False
			self.assertEqual(module._part_number(group, {}, [], None), "ILL-X-144.0-GRP(A1B2)")
			# A line keeps a quoted number (any format) while it is this group's bundle.
			line = Line(name="L1", doctype="Line", group_part_number="OLD-ABCD")
			frappe.db.exists.side_effect = lambda doctype, name: doctype == "Item"
			frappe.db.get_value.return_value = "HASH"
			with patch.object(module, "_bundle_matches", return_value=True):
				self.assertEqual(module._part_number(group, {}, [], line), "OLD-ABCD")
			# Another group's Item: the line takes the group's own number.
			frappe.db.get_value.return_value = "OTHER"
			self.assertEqual(module._part_number(group, {}, [], line), "ILL-X-144.0-GRP(A1B2)")
			self.assertEqual(line.group_part_number, "ILL-X-144.0-GRP(A1B2)")
			frappe.db.set_value.assert_called_once()

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
