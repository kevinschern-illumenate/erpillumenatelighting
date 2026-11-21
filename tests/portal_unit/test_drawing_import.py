"""Draw-to-quote plan 2.1-2.6: importing an AutoCAD ``ilq/2`` package into a schedule."""

import base64
import copy
import json
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

PACKAGES = Path(__file__).resolve().parents[2] / "tools/system_designer/fixtures/cad/packages"


def package(name="job-20-runs.json"):
	return json.loads((PACKAGES / "valid" / name).read_text(encoding="utf-8"))


def encode(value):
	return base64.b64encode(json.dumps(value).encode()).decode()


CONTROL_SPECS = {
	"DMXC-TW-BK-WALL": ("DMX Controller", [("DMX512", "DMX512"), ("BLE Mesh", "Bluetooth Mesh")]),
	"DMXD-PWM-5C-SF": ("DMX Decoder", [("DMX512", "DMX512"), ("PWM", "PWM")]),
}


class Line(Record):
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value


class Schedule(Record):
	__setattr__ = dict.__setitem__

	def append(self, field, values):
		row = Line(values)
		self.setdefault(field, []).append(row)
		return row


class DrawingImport(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.schedule = Schedule(name="S1", status="DRAFT", is_locked=0, modified="m-0", version=1, lines=[])
		self.schedule.save = MagicMock(side_effect=self._bump)
		self.versions = []
		self.schedule.create_new_version = MagicMock(side_effect=self._version)
		self.calls = []
		self.saves = []
		self.missing = {}
		self.problems = {}
		self.records = []
		self.counter = 0

		def schedule_context(name, write=False, lock=False):
			return self.versions[-1] if self.versions and name == self.versions[-1].name else self.schedule

		def calculate(family, selections, product_slug=None, template=None, segments=None):
			self.calls.append({"family": family, "template": template, "selections": selections, "segments": segments})
			if family == "Linear Fixture":
				total = sum(item["requested_length_mm"] for item in selections["segments"])
				return {
					"success": True,
					"validation": {
						"is_valid": True,
						"part_number": f"ILL-{template}",
						"computed": {
							"manufacturable_overall_length_mm": total - 10,
							"runs_count": 1,
							"total_watts": 20.0,
							"assembly_mode": "ASSEMBLED",
							"segments": [{"profile_cut_len_mm": total - 10}],
						},
						"msrp": 999,
					},
					"input_hash": "h",
				}
			missing = self.missing.get(template)
			if missing and not all(selections.get(key) for key in missing):
				return {"success": False, "validation": {"is_valid": False, "missing_fields": missing}}
			total_in = sum(item["tape_length_value"] for item in segments)
			mm = total_in * 25.4
			snapped = (mm // 50) * 50
			runs = 2 if total_in > 231 else 1
			return {
				"success": True,
				"validation": {
					"is_valid": True,
					"part_number": f"TAPE-{template}",
					"computed": {
						"manufacturable_length_mm": snapped,
						"runs_count": runs,
						"runs": [{"run_len_mm": snapped / runs}] * runs,
						"max_run_ft_effective": 19.32,
						"total_watts": round(snapped / 304.8 * 4.4, 2),
						"segments": [{"manufacturable_length_mm": (item["tape_length_value"] * 25.4 // 50) * 50} for item in segments],
					},
					"pricing": {"msrp_unit": 10},
				},
				"input_hash": "h",
			}

		def save(schedule_name, family, selections, idempotency_key, expected_modified, line_key=None, line_idx=None, metadata=None, product_slug=None, template=None, segments=None, finder=None):
			doc = schedule_context(schedule_name)
			if str(expected_modified) != str(doc.modified):
				raise ValueError("The schedule changed; reload it before saving this configuration")
			self.saves.append({"family": family, "line_key": line_key, "metadata": metadata, "key": idempotency_key, "template": template})
			line = next((item for item in doc.lines if item.get("line_key") == line_key), None) if line_key else None
			if line is None:
				self.counter += 1
				line = doc.append("lines", {"line_key": f"LK{self.counter}"})
			request = {"family": family, "template": template, "selections": selections, "segments": json.loads(segments) if isinstance(segments, str) else segments}
			line.update(
				line_id=metadata["line_id"],
				location=metadata["location"],
				qty=metadata["qty"],
				manufacturer_type="ILLUMENATE",
				configured_tape_neon=f"CTN-{line['line_key']}" if family != "Linear Fixture" else None,
				configured_fixture=f"CF-{line['line_key']}" if family == "Linear Fixture" else None,
				ill_item_code=f"PN-{line['line_key']}",
				ill_configurator_request=json.dumps(request),
			)
			if family == "LED Tape" and not line_key:
				doc.append("lines", {"line_key": f"PS-{line['line_key']}", "power_supply_for_line": line["line_key"], "manufacturer_type": "ACCESSORY"})
			doc.save()
			return {"success": True, "line_key": line["line_key"], "modified": doc.modified}

		def kit_save(schedule_name, selections, idempotency_key, expected_modified, line_key=None, line_idx=None, metadata=None, finder=None):
			doc = schedule_context(schedule_name)
			self.saves.append({"family": "Extrusion Kit", "line_key": line_key, "metadata": metadata, "key": idempotency_key})
			line = next((item for item in doc.lines if item.get("line_key") == line_key), None) if line_key else None
			if line is None:
				self.counter += 1
				line = doc.append("lines", {"line_key": f"LK{self.counter}"})
			line.update(line_id=metadata["line_id"], location=metadata["location"], qty=metadata["qty"], kit_template=selections["kit_template"], ill_item_code="KIT-" + selections["kit_template"])
			doc.save()
			return {"success": True, "line_key": line["line_key"], "modified": doc.modified}

		def append_line(schedule, line_data, is_sales_staff):
			row = schedule.append("lines", {})
			row.update({key: value for key, value in line_data.items() if value is not None})
			return None

		def template_problem(family, template):
			return self.problems.get(template)

		def record_doc(values):
			doc = Record(values)
			doc.flags = Record()
			doc.name = f"CADI-{len(self.records) + 1:05d}"
			doc.insert = MagicMock()
			doc.save = MagicMock()
			doc.db_set = MagicMock()
			doc.__class__ = type("Doc", (Record,), {"__setattr__": dict.__setitem__})
			self.records.append(doc)
			return doc

		self.extras = {
			ROOT + ".api.build_artifacts": types.SimpleNamespace(atomic_build=lambda function: function),
			ROOT + ".portal.configuration": types.SimpleNamespace(schedule_context=schedule_context, calculate=calculate, save=save),
			ROOT + ".portal.kit_configuration": types.SimpleNamespace(save=kit_save),
			ROOT + ".api.extrusion_kit_configurator": types.SimpleNamespace(
				validate_kit_configuration=lambda selections: {"is_valid": True, "part_number": "KIT-" + selections["kit_template"]}
			),
			ROOT + ".portal.presets": types.SimpleNamespace(
				FAMILY_DOCTYPES={"LED Tape": 1, "COB Tape": 1, "LED Neon": 1, "Linear Fixture": 1, "Extrusion Kit": 1},
				template_problem=template_problem,
			),
			ROOT + ".system_design.cad_access": types.SimpleNamespace(enabled_for=lambda user=None: self.enabled),
			ROOT + ".portal.staff": types.SimpleNamespace(allowed=lambda role: False),
			ROOT + ".portal.schedule_lines": types.SimpleNamespace(require_fresh=self._require_fresh),
			ROOT + ".portal.line_add": types.SimpleNamespace(append_line=append_line),
			ROOT + ".system_design.telemetry": types.SimpleNamespace(record=MagicMock()),
			ROOT + ".system_design.catalog": types.SimpleNamespace(
				SNAPSHOT_DOCTYPE="ilL-Design-Catalog-Snapshot", current_snapshot_hash=lambda: "0" * 63 + "1"
			),
			ROOT + ".system_design.dealer_data": types.SimpleNamespace(apply=lambda line, data: line.update(watts_each=data.get("watts_each"))),
			ROOT + ".api.portal": types.SimpleNamespace(
				orderable_item_problem=lambda code, staff=False: None if code in CONTROL_SPECS else "This Item is not active",
				is_power_supply_group=lambda group: False,
			),
			ROOT + ".system_design.readiness": types.SimpleNamespace(
				controller_category=lambda kind, dimming=None: {"DMX Decoder": "dmx-decoder", "DMX Controller": "dmx-controller"}.get(kind)
			),
			ROOT + ".portal.access": types.SimpleNamespace(get_actor=lambda user=None: self.actor),
			ROOT + ".portal.site_flags": types.SimpleNamespace(cad_min_versions=lambda: self.min_versions),
			ROOT + ".system_design.cad_catalog": types.SimpleNamespace(
				cad_catalog=lambda user=None: self.catalog,
				TAPE_OPTIONS={"Finish": ("finish", "finish", "Finish")},
				template_options=lambda rows: [{"key": "finish", "values": [row["finish"] for row in rows]}],
			),
		}
		self.catalog = None
		self.actor = types.SimpleNamespace(is_internal=False, customer="Dealer Co")
		self.min_versions = {}
		self.record_doc = record_doc

	def _bump(self, *args, **kwargs):
		doc = self.versions[-1] if self.versions else self.schedule
		number = int(str(doc.modified).split("-")[1]) + 1
		doc.modified = f"m-{number}"

	def _version(self, version_notes=None):
		new = Schedule(name="S1-v2", status="DRAFT", is_locked=0, modified="m-0", version=2, lines=copy.deepcopy(self.schedule.lines))
		for line in new.lines:
			line.__class__ = Line
		new.save = MagicMock(side_effect=self._bump)
		self.versions.append(new)
		return new.name

	def _require_fresh(self, schedule, expected_modified=None):
		if expected_modified and str(expected_modified) != str(schedule.modified):
			raise ValueError("This schedule changed since you opened it.")

	@contextmanager
	def module(self):
		with load_service(ROOT + ".portal.drawing_import", self.extras) as (module, frappe):
			frappe.db.get_value.side_effect = self._get_value
			frappe.get_all.side_effect = self._get_all
			frappe.get_doc.side_effect = self.record_doc
			frappe.utils.date_diff = lambda a, b: 0
			self.frappe = frappe
			yield module

	def _get_value(self, doctype, name, field=None, *args, **kwargs):
		if doctype == "ilL-Spec-Controller":
			spec = CONTROL_SPECS.get(name["item"])
			return Record(name=name["item"], controller_type=spec[0], output_dimming=None) if spec else None
		if doctype == "Item" and name in CONTROL_SPECS:
			return Record(item_name=f"{name} control", item_group="Controls")
		if doctype == "ilL-Extrusion-Kit-Template":
			return 2000
		if doctype == "ilL-Design-Catalog-Snapshot":
			return "2026-11-20 09:00:00"
		if field == "config_hash":
			return "cfg-" + name
		return None

	def _get_all(self, doctype, **kwargs):
		if doctype == "ilL-Child-Controller-Port":
			spec = CONTROL_SPECS.get(kwargs["filters"]["parent"])
			return [Record(port_name=name, protocol=protocol) for name, protocol in spec[1]]
		return []

	def preview(self, value=None, **kwargs):
		with self.module() as module:
			return module.preview_drawing_import("S1", "job.ilq.json", encode(value or package()), **kwargs)

	def commit(self, value=None, **kwargs):
		with self.module() as module:
			kwargs.setdefault("expected_modified", (self.versions[-1] if self.versions else self.schedule).modified)
			return module.commit_drawing_import("S1", "job.ilq.json", encode(value or package()), **kwargs)

	# --- Preview -----------------------------------------------------------------------------

	def test_preview_plans_every_run_and_strips_prices(self):
		result = self.preview()
		self.assertTrue(result["success"])
		self.assertEqual(result["counts"]["ok"], 24)  # 20 runs, one other line, three controls
		self.assertEqual(result["counts"]["error"], 0)
		self.assertEqual(result["counts"]["add"], 24)
		self.assertNotIn("msrp", json.dumps(result))
		self.assertNotIn("pricing", json.dumps(result))
		self.schedule.save.assert_not_called()
		self.assertEqual(result["site"], {"rooms": 4, "cabinets": 2, "wire_paths": 22, "psus": 3})

	def test_tape_segments_are_inches_with_jumpers_and_feeds(self):
		self.preview()
		call = next(item for item in self.calls if item["template"] == "led-hd-sw" and len(item["segments"]) == 2)
		first, second = call["segments"]
		self.assertEqual(first["tape_length_value"], 48.25)
		self.assertEqual(first["tape_length_unit"], "in")
		self.assertEqual(first["start_feed_direction"], "End")
		self.assertEqual(first["start_lead_length_inches"], 60)
		self.assertEqual((first["end_type"], first["end_feed_length_inches"]), ("Jumper", 12))
		self.assertEqual(second["end_type"], "Endcap")
		self.assertNotIn("start_feed_direction", second)

	def test_linear_segments_are_millimetres_with_preset_defaults(self):
		self.preview()
		call = next(item for item in self.calls if item["family"] == "Linear Fixture")
		segment = call["selections"]["segments"][0]
		self.assertEqual(segment["requested_length_mm"], 3658)
		self.assertEqual(segment["start_power_feed_type"], "Wire Leads")
		self.assertEqual(segment["start_leader_cable_length_mm"], 1524)  # 60 in from CAD
		self.assertEqual(segment["end_type"], "Endcap")
		self.assertEqual(call["selections"]["fixture_template_code"], "ILL-RA01-SW")
		self.assertIsNone(call["segments"])

	def test_kit_runs_are_a_kit_line_plus_a_tape_build(self):
		result = self.preview()
		row = next(item for item in result["rows"] if item["id"] == "L5-02")
		parts = {entry["part"]: entry for entry in row["parts"]}
		self.assertEqual(parts["kit"]["qty"], 2)  # 120 in over 2000 mm sticks
		self.assertEqual(parts["kit"]["cad_run_id"], "L5-02.K")
		self.assertEqual(parts["tape"]["family"], "LED Tape")
		self.assertEqual(parts["tape"]["cad_run_id"], "L5-02")

	def test_server_lengths_and_splits_are_reported(self):
		result = self.preview()
		row = next(item for item in result["rows"] if item["id"] == "L1-02")
		self.assertEqual(row["drawn_length_in"], 132.5)
		self.assertEqual(row["server_length_in"], 131.89)
		self.assertTrue(any("cut to the nearest increment" in text for text in row["messages"]))
		long_run = next(item for item in result["rows"] if item["id"] == "L7-01")
		self.assertTrue(any("Splits into 2 runs" in text for text in long_run["messages"]))

	def test_open_option_needs_a_choice_then_the_choice_fixes_it(self):
		self.missing["non-pnc-sw"] = ["finish"]
		result = self.preview()
		row = next(item for item in result["rows"] if item["id"] == "L3-01")
		self.assertEqual(row["status"], "needs_choice")
		self.assertEqual(row["parts"][0]["missing"], ["finish"])
		result = self.preview(choices=json.dumps({"L3-01": {"finish": "White", "unit_price": 5}}))
		row = next(item for item in result["rows"] if item["id"] == "L3-01")
		self.assertEqual(row["status"], "ok")
		call = [item for item in self.calls if item["template"] == "non-pnc-sw"][-1]
		self.assertEqual(call["selections"]["finish"], "White")
		self.assertNotIn("unit_price", call["selections"])

	def test_template_no_longer_offered_is_an_error_row(self):
		self.problems["cob-sd-sw"] = "cob-sd-sw is no longer offered"
		result = self.preview()
		rows = [item for item in result["rows"] if item["template"] == "cob-sd-sw"]
		self.assertEqual({item["status"] for item in rows}, {"error"})
		self.assertEqual(result["counts"]["error"], 4)

	def test_price_keys_in_a_style_are_dropped(self):
		value = package("minimal.json")
		value["runs"][0]["style"]["selections"]["msrp_adder"] = 4
		result = self.preview(value)
		self.assertIn("msrp_adder", " ".join(result["rows"][0]["messages"]))
		self.assertNotIn("msrp_adder", self.calls[0]["selections"])

	def test_invalid_packages_and_files_are_refused(self):
		with self.module() as module:
			with self.assertRaisesRegex(ValueError, ".ilq.json"):
				module.preview_drawing_import("S1", "job.dwg", encode(package()))
			with self.assertRaisesRegex(ValueError, "not a valid drawing package"):
				module.preview_drawing_import("S1", "job.json", encode({"schema": "ilq/1"}))

	def test_dxf_uploads_go_through_dxf_ingest_with_their_options(self):
		seen = {}

		class DxfError(ValueError):
			pass

		def package_from_dxf(data, filename, options, report=None):
			seen.update(data=data, filename=filename, options=options)
			if report is not None:
				report["layers"] = [{"layer": "ILM-TAPE-led-hd-sw", "runs": 1}]
			return package("minimal.json")

		self.extras[ROOT + ".portal.dxf_ingest"] = types.SimpleNamespace(DxfError=DxfError, package_from_dxf=package_from_dxf)
		with self.module() as module:
			result = module.preview_drawing_import(
				"S1", "plan.dxf", base64.b64encode(b"0\nSECTION").decode(), options=json.dumps({"types": {"ILM-TAPE-x": "T1"}})
			)
		self.assertTrue(result["success"])
		self.assertEqual(seen["options"], {"types": {"ILM-TAPE-x": "T1"}})
		self.assertEqual(seen["data"], b"0\nSECTION")

	def test_flag_off_or_not_in_pilot_refuses(self):
		self.enabled = False
		with self.assertRaises(PermissionError):
			self.preview()

	def test_catalog_warning_when_the_drawing_used_an_unknown_snapshot(self):
		value = package("minimal.json")
		value["catalog"]["snapshot_hash"] = "f" * 64
		with self.module() as module:
			self.frappe.db.get_value.side_effect = lambda doctype, name, field=None, *a, **k: None if doctype == "ilL-Design-Catalog-Snapshot" else self._get_value(doctype, name, field)
			result = module.preview_drawing_import("S1", "min.json", encode(value))
		self.assertTrue(any("not one this server built" in text for text in result["warnings"]))

	# --- Commit ------------------------------------------------------------------------------

	def test_commit_adds_configured_lines_with_cad_ids_and_a_receipt(self):
		result = self.commit()
		self.assertTrue(result["success"], result)
		ids = {line.get("cad_run_id") for line in self.schedule.lines if line.get("cad_run_id")}
		self.assertIn("L1-01", ids)
		self.assertIn("L5-01.K", ids)
		self.assertIn("OTHER.X1", ids)
		self.assertEqual(len(self.saves), 22)  # 20 builds + 2 kits
		receipt = result["receipt"]
		self.assertEqual(receipt["schema"], "ilq-receipt/1")
		run = next(item for item in receipt["runs"] if item["id"] == "L1-01")
		self.assertTrue(run["line_key"].startswith("LK"))
		self.assertEqual(run["configured_doctype"], "ilL-Configured-Tape-Neon")
		self.assertEqual(run["config_hash"], "cfg-CTN-" + run["line_key"])
		self.assertEqual(run["part_number"], "PN-" + run["line_key"])
		kit = next(item for item in receipt["runs"] if item["id"] == "L5-01")
		self.assertEqual({part["part"] for part in kit["parts"]}, {"tape", "kit"})
		other = next(line for line in self.schedule.lines if line.get("cad_run_id") == "OTHER.X1")
		self.assertEqual((other["manufacturer_type"], other["qty"], other["watts_each"]), ("OTHER", 4, 12))
		record = self.records[-1]
		self.assertEqual(record["runs_added"], 24)
		self.assertTrue(record.flags.cad_import_service_write)
		site = json.loads(record["site_json"])
		self.assertEqual(site["schema"], "cad-site/1")
		line = site["lines"][run["line_key"]]
		self.assertEqual((line["room"], line["cabinet"], line["homeRunLengthFt"]), ("Kitchen", "CAB-1", 11.46))
		cabinet = next(item for item in site["cabinets"] if item["id"] == "CAB-1")
		self.assertEqual(cabinet["feedLengthFt"], 45)

	def test_controls_become_accessory_lines_and_seed_the_design(self):
		result = self.commit()
		self.assertTrue(result["success"], result)
		decoder = next(line for line in self.schedule.lines if line.get("cad_run_id") == "DEC-01")
		self.assertEqual((decoder["manufacturer_type"], decoder["accessory_item"], decoder["qty"]), ("ACCESSORY", "DMXD-PWM-5C-SF", 1))
		self.assertEqual(decoder["location"], "CAB-1")
		wall = next(line for line in self.schedule.lines if line.get("cad_run_id") == "CTL-01")
		self.assertEqual(wall["location"], "Living")
		self.assertEqual(result["receipt"]["controls"]["DEC-01"], decoder["line_key"])
		site = json.loads(self.records[-1]["site_json"])
		seed = site["controls"]["DEC-01"]
		self.assertEqual(seed["catalogId"], "ctl:DMXD-PWM-5C-SF")
		self.assertEqual(seed["category"], "dmx-decoder")
		self.assertEqual(seed["dmx"], {"universe": 1, "start_address": 1})
		self.assertEqual((seed["cabinet"], seed["controlFrom"], seed["lineKey"]), ("CAB-1", "CTL-01", decoder["line_key"]))
		zone = site["zones"][0]
		self.assertEqual((zone["method"], zone["control"]), ("DMX512", {"id": "CTL-01", "port": "DMX512"}))
		self.assertEqual(len(zone["lines"]), 3)

	def test_control_changes_update_in_place_and_removed_controls_need_confirmation(self):
		self.commit()
		key = next(line["line_key"] for line in self.schedule.lines if line.get("cad_run_id") == "DEC-02")
		value = package()
		value["controls"][2]["item_code"] = "DMXC-TW-BK-WALL"
		self.commit(value)
		changed = next(line for line in self.schedule.lines if line.get("cad_run_id") == "DEC-02")
		self.assertEqual((changed["line_key"], changed["accessory_item"]), (key, "DMXC-TW-BK-WALL"))
		value["controls"] = value["controls"][:2]
		result = self.commit(value)
		self.assertTrue(result["confirm_removals_required"])
		self.assertEqual([row["id"] for row in result["removals"]], ["DEC-02"])

	def test_unknown_control_or_port_is_an_error(self):
		value = package()
		value["controls"][0]["item_code"] = "NOT-A-CONTROL"
		result = self.preview(value)
		row = next(item for item in result["other_lines"] if item["id"] == "CTL-01")
		self.assertEqual(row["status"], "error")
		value = package()
		value["zones"][0]["control"]["port"] = "DMX OUT"
		result = self.preview(value)
		zone = next(item for item in result["other_lines"] if item["id"] == "ZN-1")
		self.assertIn("has no output DMX OUT", zone["messages"][0])
		self.assertFalse(self.commit(value)["success"])

	def test_idempotency_keys_are_stable_per_package_and_run(self):
		self.commit()
		keys = [item["key"] for item in self.saves]
		self.assertEqual(len(keys), len(set(keys)))
		self.assertTrue(all(len(key) == 64 for key in keys))

	def test_unchanged_reimport_saves_nothing_and_changed_run_updates_in_place(self):
		self.commit()
		first = {line["cad_run_id"]: line["line_key"] for line in self.schedule.lines if line.get("cad_run_id")}
		self.saves.clear()
		self.commit()
		self.assertEqual(self.saves, [])
		value = package()
		value["drawing"]["rev"] = 2
		value["runs"][0]["segments"][0]["path_length_in"] = 100
		self.saves.clear()
		result = self.commit(value)
		self.assertTrue(result["success"], result)
		tape = [item for item in self.saves if item["family"] != "Extrusion Kit"]
		self.assertEqual(len(tape), 1)
		self.assertEqual(tape[0]["line_key"], first["L1-01"])

	def test_removed_run_needs_confirmation_and_takes_its_supply_line(self):
		self.commit()
		value = package()
		value["runs"] = [run for run in value["runs"] if run["id"] != "L1-01"]
		value["psus"] = [{**psu, "runs": [run for run in psu["runs"] if run != "L1-01"]} for psu in value["psus"]]
		value["wire_paths"] = [wire for wire in value["wire_paths"] if "L1-01" not in (wire["from"], wire["to"])]
		value["zones"] = [{**zone, "runs": [run for run in zone["runs"] if run != "L1-01"]} for zone in value["zones"]]
		key = next(line["line_key"] for line in self.schedule.lines if line.get("cad_run_id") == "L1-01")
		result = self.commit(value)
		self.assertFalse(result["success"])
		self.assertTrue(result["confirm_removals_required"])
		self.assertEqual(result["removals"][0]["id"], "L1-01")
		result = self.commit(value, confirm_removals="1")
		self.assertTrue(result["success"], result)
		keys = {line.get("line_key") for line in self.schedule.lines}
		self.assertNotIn(key, keys)
		self.assertFalse(any(line.get("power_supply_for_line") == key for line in self.schedule.lines))
		self.assertEqual(result["receipt"]["removed"], ["L1-01"])

	def test_other_line_reimport_keeps_its_line_key(self):
		self.commit()
		before = next(line for line in self.schedule.lines if line.get("cad_run_id") == "OTHER.X1")
		before.line_key = "OTHER-KEY"
		value = package()
		value["other_lines"][0]["qty"] = 6
		self.commit(value)
		after = [line for line in self.schedule.lines if line.get("cad_run_id") == "OTHER.X1"]
		self.assertEqual(len(after), 1)
		self.assertEqual((after[0]["line_key"], after[0]["qty"]), ("OTHER-KEY", 6))

	def test_errors_or_open_choices_refuse_the_whole_commit(self):
		self.problems["led-hd-sw"] = "led-hd-sw is no longer offered"
		result = self.commit()
		self.assertFalse(result["success"])
		self.assertEqual(self.saves, [])
		self.schedule.save.assert_not_called()

	def test_toolkit_errors_block_the_commit(self):
		value = package()
		value["check"]["errors"] = 2
		result = self.commit(value)
		self.assertFalse(result["success"])
		self.assertIn("ILCHECK", result["error"])

	def test_locked_schedule_imports_into_a_new_version_only_when_asked(self):
		self.schedule.status = "QUOTED"
		result = self.commit()
		self.assertFalse(result["success"])
		self.assertTrue(result["new_version_required"])
		self.schedule.create_new_version.assert_not_called()
		result = self.commit(new_version="1", expected_modified=self.schedule.modified)
		self.assertTrue(result["success"], result)
		self.assertEqual(result["schedule"], "S1-v2")
		self.assertEqual(self.schedule.lines, [])  # v1 untouched

	def test_plan_pdf_is_kept_and_added_to_the_current_design(self):
		uploads = []
		design = Record(name="SYSD-1")
		self.extras[ROOT + ".portal.file_validation"] = types.SimpleNamespace(
			validate_content=lambda name, data: {"mime_type": "application/pdf"} if data.startswith(b"%PDF") else (_ for _ in ()).throw(ValueError("not a PDF"))
		)
		self.extras[ROOT + ".system_design.designs"] = types.SimpleNamespace(current_design=lambda doc: design)
		self.extras[ROOT + ".system_design.deliverables"] = types.SimpleNamespace(
			upload_deliverable=lambda *args, **kwargs: uploads.append((args, kwargs)) or {"file_url": "/private/files/plan.pdf"}
		)
		self.extras[ROOT + ".system_design.errors"] = types.SimpleNamespace(DesignError=type("DesignError", (Exception,), {}))
		pdf = base64.b64encode(b"%PDF-1.7 plan").decode()
		result = self.commit(plan_pdf=pdf)
		self.assertTrue(result["success"], result)
		args, kwargs = uploads[0]
		self.assertEqual(args[:3], ("SYSD-1", "Plan PDF", "rev1"))
		self.assertEqual(kwargs["content"], b"%PDF-1.7 plan")
		self.assertEqual(self.records[1]["attached_to_field"], "plan_pdf")
		self.records[0].db_set.assert_called_once()
		with self.assertRaisesRegex(ValueError, "not a PDF"):
			self.commit(plan_pdf=base64.b64encode(b"GIF89a").decode())

	def test_stale_expected_modified_is_refused(self):
		with self.assertRaisesRegex(ValueError, "changed"):
			self.commit(expected_modified="m-99")


	# --- Phase 1: source, scale, versions, choices, on-behalf (implementation plan WP 1.1-1.10) -------

	def sheeted(self, statuses):
		value = package("minimal.json")
		value["source"] = {"tool": "autocad", "version": "0.5.0", "input": "ilq"}
		value["sheets"] = [{"id": f"P{index}", "scale": {"status": status}} for index, status in enumerate(statuses, 1)]
		run = value["runs"][0]
		run["sheet"] = f"P{len(statuses)}"
		return value

	def test_preview_reports_source_sheets_and_scale(self):
		result = self.preview(self.sheeted(["verified", "declared"]))
		self.assertEqual(result["source"]["tool"], "autocad")
		self.assertEqual(result["scale"], {"status": "declared"})
		self.assertEqual([sheet["used"] for sheet in result["sheets"]], [False, True])
		self.assertTrue(any("not calibrated" in text for text in result["warnings"]))
		self.assertNotIn("Scale not verified", json.dumps(result["rows"]))
		result = self.preview(self.sheeted(["unverified"]))
		self.assertEqual(result["scale"], {"status": "unverified"})
		self.assertIn("Scale not verified", result["rows"][0]["messages"])

	def test_old_packages_get_a_derived_source_and_declared_scale(self):
		result = self.preview(package("minimal.json"))
		self.assertEqual(result["source"]["tool"], "autocad")
		self.assertEqual(result["scale"]["status"], "declared")
		self.assertEqual(self.preview()["scale"]["status"], "verified")  # job-20-runs ran ILSCALE

	def test_preview_is_recorded_for_telemetry(self):
		with self.module() as module:
			module.preview_drawing_import("S1", "job.ilq.json", encode(package()))
		record = self.extras[ROOT + ".system_design.telemetry"].record
		event, schedule = record.call_args.args[:2]
		self.assertEqual((event, schedule), ("cad_preview", "S1"))
		self.assertEqual(record.call_args.kwargs["details"]["source_tool"], "autocad")

	def test_unreadable_files_are_recorded_then_refused(self):
		record = self.extras[ROOT + ".system_design.telemetry"].record
		with self.module() as module, self.assertRaises(Exception):
			module.preview_drawing_import("S1", "job.ilq.json", base64.b64encode(b"{").decode())
		self.assertEqual(record.call_args.args[0], "cad_preview_failed")

	def test_old_toolkit_versions_are_blocked_when_a_minimum_is_set(self):
		self.min_versions = {"autocad": "0.5.0"}
		result = self.preview()  # job-20-runs was written by 0.3.0
		self.assertTrue(any("0.5.0 or later" in text for text in result["blocking"]))
		self.assertFalse(self.commit()["success"])
		self.assertEqual(self.preview(self.sheeted(["verified"]))["blocking"], [])

	def test_choice_groups_collect_runs_waiting_on_the_same_keys(self):
		self.missing["led-hd-sw"] = ["finish"]

		def get_all(doctype, **kwargs):
			if doctype == "ilL-Tape-Neon-Template":
				return [Record(name="TPL-HD", template_code="led-hd-sw")]
			if doctype == "ilL-Child-Tape-Neon-Allowed-Option":
				return [Record(parent="TPL-HD", finish="White"), Record(parent="TPL-HD", finish="Black")]
			return self._get_all(doctype, **kwargs)

		with self.module() as module:
			self.frappe.get_all.side_effect = get_all
			result = module.preview_drawing_import("S1", "job.ilq.json", encode(package()))
		group = next(item for item in result["choice_groups"] if item["template"] == "led-hd-sw")
		self.assertEqual(group["keys"], [{"key": "finish", "values": ["White", "Black"]}])
		waiting = [row["id"] for row in result["rows"] if row["status"] == "needs_choice" and row["template"] == "led-hd-sw"]
		self.assertEqual(sorted(group["runs"]), sorted(waiting))
		self.assertGreater(len(group["runs"]), 1)

	def test_commit_records_source_scale_choices_and_on_behalf(self):
		self.actor = types.SimpleNamespace(is_internal=True, customer=None)
		self.schedule.customer = "Dealer Co"
		self.missing["led-hd-sw"] = ["cct"]
		choices = {row: {"cct": "2700K"} for row in ("L1-01",)}
		result = self.commit(choices=json.dumps({run["id"]: {"cct": "2700K"} for run in package()["runs"]}))
		self.assertTrue(result["success"], result)
		record = self.records[-1]
		self.assertEqual((record["source_tool"], record["source_input"]), ("autocad", "ilq"))
		self.assertEqual(record["scale_status"], "verified")
		self.assertEqual((record["on_behalf"], record["on_behalf_customer"]), (1, "Dealer Co"))
		self.assertEqual(json.loads(record["choices_json"])["L1-01"], choices["L1-01"])
		details = self.extras[ROOT + ".system_design.telemetry"].record.call_args.kwargs["details"]
		self.assertTrue(details["on_behalf"])

	def test_dealers_importing_their_own_schedule_are_not_on_behalf(self):
		self.schedule.customer = "Dealer Co"
		self.assertTrue(self.commit()["success"])
		self.assertEqual(self.records[-1]["on_behalf"], 0)

	def test_unverified_scale_blocks_a_quote_until_confirmed(self):
		rows = [Record(name="CADI-00001", scale_status="unverified", scale_confirmed_by=None, ignored_count=0)]
		with self.module() as module:
			self.frappe.get_all.side_effect = lambda doctype, **kwargs: rows
			self.assertIn("CADI-00001", module.quote_blockers("S1")[0])
			rows[0]["scale_confirmed_by"] = "ae@illumenate.lighting"
			self.assertEqual(module.quote_blockers("S1"), [])
			rows[0].update(scale_status="declared", scale_confirmed_by=None)
			self.assertEqual(module.quote_blockers("S1"), [])
			rows.clear()
			self.assertEqual(module.quote_blockers("S1"), [])

	def test_scale_confirmation_needs_an_engineer_and_a_note(self):
		staff = types.SimpleNamespace(require=MagicMock(side_effect=PermissionError("staff only")))
		self.extras[ROOT + ".portal.staff"] = staff
		with self.module() as module:
			with self.assertRaises(PermissionError):
				module.confirm_drawing_scale("CADI-00001", "measured the 12 ft wall")
			staff.require.side_effect = None
			with self.assertRaisesRegex(ValueError, "at least 3"):
				module.confirm_drawing_scale("CADI-00001", "ok")
			result = module.confirm_drawing_scale("CADI-00001", "measured the 12 ft wall")
			self.assertTrue(result["success"])
			name, values = self.frappe.db.set_value.call_args.args[1:3]
			self.assertEqual(name, "CADI-00001")
			self.assertEqual(values["scale_note"], "measured the 12 ft wall")
		staff.require.assert_called_with("design_review")


	def test_server_checks_turn_toolkit_errors_into_error_rows(self):
		self.catalog = json.loads((PACKAGES.parent / "catalog.sample.json").read_text(encoding="utf-8"))
		value = package("minimal.json")
		value["runs"][0]["style"] = {"family": "LED Neon", "template": "non-pnc-sw", "selections": {"cct": "2700K", "output_level": "200 lm/ft"}}
		value["runs"][0]["segments"][0]["min_arc_radius_in"] = 1.0
		result = self.preview(value)
		row = result["rows"][0]
		self.assertEqual(row["status"], "error")
		self.assertTrue(any("minimum" in text for text in row["messages"]), row["messages"])
		self.assertFalse(self.commit(value)["success"])
		value["check"]["overrides"] = [{"code": "BEND_RADIUS", "ref": value["runs"][0]["id"], "note": "engineer approved the cove"}]
		self.assertEqual(self.preview(value)["rows"][0]["status"], "ok")


class PureHelpers(unittest.TestCase):
	def setUp(self):
		self.context = load_service(ROOT + ".portal.drawing_import")
		self.module, _frappe = self.context.__enter__()

	def tearDown(self):
		self.context.__exit__(None, None, None)

	def test_scale_summary_takes_the_worst_sheet_with_runs(self):
		value = package("minimal.json")
		self.assertEqual(self.module.scale_summary(value)["status"], "declared")
		value["drawing"]["scale_verified"] = True
		self.assertEqual(self.module.scale_summary(value)["status"], "verified")
		value["sheets"] = [{"id": "A", "scale": {"status": "unverified"}}, {"id": "B", "scale": {"status": "verified"}}]
		self.assertEqual(self.module.scale_summary(value)["status"], "unverified")
		value["runs"][0]["sheet"] = "B"
		self.assertEqual(self.module.scale_summary(value)["status"], "verified")

	def test_version_check(self):
		value = {"source": {"tool": "autocad", "version": "0.4.5"}}
		self.assertEqual(self.module.version_check(value, {}), ([], []))
		blocking, _warnings = self.module.version_check(value, {"autocad": "0.5.0"})
		self.assertEqual(len(blocking), 1)
		self.assertEqual(self.module.version_check(value, {"autocad": "0.4.5"}), ([], []))
		self.assertEqual(self.module.version_check(value, {"bluebeam": "9"}), ([], []))
		_blocking, warnings = self.module.version_check({"source": {"tool": "dxf", "version": "dxf-1"}}, {"dxf": "1"})
		self.assertEqual(len(warnings), 1)
		self.assertEqual(self.module.version_tuple("0.10.2"), (0, 10, 2))
		self.assertGreater(self.module.version_tuple("0.10.0"), self.module.version_tuple("0.9.9"))

	def test_diff_receipts(self):
		older = {"runs": [{"id": "A", "part_number": "P1", "server_length_in": 10}, {"id": "B", "part_number": "P2"}]}
		newer = {"runs": [{"id": "A", "part_number": "P1", "server_length_in": 12}, {"id": "C", "part_number": "P3"}]}
		diff = self.module.diff_receipts(older, newer)
		self.assertEqual([run["id"] for run in diff["added"]], ["C"])
		self.assertEqual([run["id"] for run in diff["removed"]], ["B"])
		self.assertEqual(diff["changed"], [{"id": "A", "changes": {"server_length_in": {"from": 10, "to": 12}}}])

	def test_kit_quantity_covers_the_run_with_whole_sticks(self):
		self.assertEqual(self.module.kit_quantity(78.74, 2000), 1)
		self.assertEqual(self.module.kit_quantity(78.75, 2000), 2)
		self.assertIsNone(self.module.kit_quantity(10, 0))

	def test_site_seed_uses_the_longest_low_voltage_path(self):
		value = package()
		seed = self.module.site_seed(value, {"L1-01": "K1"}, "CADI-1")
		self.assertEqual(seed["lines"]["K1"]["homeRunLengthFt"], 11.46)
		self.assertEqual(seed["rooms"][2], {"id": "Z-Bath", "name": "Primary Bath", "level": "L2", "envChoice": "damp"})
		self.assertEqual(set(seed["lines"]), {"K1"})


if __name__ == "__main__":
	unittest.main()
