"""Saving, revising and loading ilL-System-Design records (System Designer WP-2.4).

Uses the WP-2.2 design fixtures and the WP-2.3 open-design records; the installed-site suite
(``system_design/test_designs.py``) covers the doctype, the permission hook and the database lock.
"""

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

DESIGNS = ROOT + ".system_design.designs"
EXPANSION = ROOT + ".system_design.expansion"
RECONCILE = ROOT + ".system_design.reconcile"
FIXTURES = Path(__file__).resolve().parents[2] / "tools/system_designer/packages/core-schemas/fixtures"
DESIGN = json.loads((FIXTURES / "designs/valid/runs-and-site.json").read_text(encoding="utf-8"))
RECORDS = json.loads((FIXTURES / "open-design/erp-records.json").read_text(encoding="utf-8"))
MODIFIED = datetime(2026, 10, 9, 12, 0, 0)


def schedule_payload():
	with load_service(EXPANSION) as (module, _frappe):
		records = copy.deepcopy(RECORDS)
		engine = records["context"]["engine"]
		lines = [module.serialize_line(line, idx, engine) for idx, line in enumerate(records["lines"], 1)]
		builds = {}
		for doc in records["docs"]:
			builds.setdefault(doc["doctype"], {})[doc["name"]] = module.BUILDERS[doc["doctype"]](
				doc, records["context"]
			)
		return lines, builds


LINES, BUILDS = schedule_payload()


class FakeDesign(Record):
	"""Enough of a Frappe document for ``save_design`` and ``create_revision``."""

	def __init__(self, **values):
		super().__init__(**values)
		self.flags = Record()
		self.saved = []

	def __setattr__(self, key, value):
		self[key] = value

	def is_new(self):
		return not self.get("name")

	def insert(self):
		self["name"] = self.get("name") or "SYSD-2026-00002"
		self["modified"] = MODIFIED
		self.saved.append("insert")

	def save(self):
		self["modified"] = MODIFIED
		self.saved.append("save")

	def db_set(self, key, value):
		self[key] = value

	def add_comment(self, kind, text):
		self.setdefault("notes", []).append((kind, text))


def settings(**changes):
	values = {
		"review_gate_enabled": 0,
		"review_gate_watts": 1500,
		"review_gate_dmx": 1,
		"review_gate_phase_dimming": 1,
		"vd_target_class2_pct": 3,
		"vd_target_line_pct": 3,
		"vd_target_landscape_pct": 5,
	}
	return Record(**{**values, **changes})


class Revisions(unittest.TestCase):
	def test_letters_follow_spreadsheet_columns(self):
		with load_service(DESIGNS) as (module, _frappe):
			pairs = {"A": "B", "Y": "Z", "Z": "AA", "AZ": "BA", "ZZ": "AAA", "": "A"}
			for current, expected in pairs.items():
				self.assertEqual(module.next_revision(current), expected)
			with self.assertRaises(ValueError):
				module.next_revision("A1")


class Parsing(unittest.TestCase):
	def test_size_limit_and_json(self):
		with load_service(DESIGNS) as (module, _frappe):
			self.assertEqual(module.parse_design(DESIGN), DESIGN)
			self.assertEqual(module.parse_design(json.dumps(DESIGN)), DESIGN)
			with self.assertRaises(module.DesignError) as caught:
				module.parse_design("{not json")
			self.assertEqual(caught.exception.code, "INVALID")
			big = json.dumps({"views": {"riser": "x" * module.MAX_DESIGN_BYTES}})
			with self.assertRaises(module.DesignError) as caught:
				module.parse_design(big)
			self.assertIn("5 MB", caught.exception.message)


class Fingerprints(unittest.TestCase):
	def test_stable_and_sensitive_to_h84_fields(self):
		with load_service(RECONCILE) as (module, _frappe):
			first = module.fingerprints(LINES, BUILDS)
			self.assertNotIn("wire1", {key.lower() for key in first})
			self.assertEqual(len(first), len([line for line in LINES if line["kind"] != "writeback"]))
			self.assertEqual(module.fingerprints(copy.deepcopy(LINES), BUILDS), first)
			lines = copy.deepcopy(LINES)
			lines[0]["qty"] += 1
			lines[0]["location"] = "Somewhere else"
			changed = module.fingerprints(lines, BUILDS)
			self.assertNotEqual(changed[lines[0]["key"]], first[lines[0]["key"]])
			self.assertEqual(
				{k: v for k, v in changed.items() if k != lines[0]["key"]},
				{k: v for k, v in first.items() if k != lines[0]["key"]},
			)
			builds = copy.deepcopy(BUILDS)
			ref = LINES[0]["configured"]
			builds[ref["doctype"]][ref["name"]]["configHash"] = "different"
			self.assertNotEqual(module.fingerprints(LINES, builds)[LINES[0]["key"]], first[LINES[0]["key"]])


class Summary(unittest.TestCase):
	def test_flags_come_from_schedule_and_zones(self):
		with load_service(DESIGNS) as (module, _frappe):
			with patch.object(module.gate, "gate_enabled", return_value=False):
				summary = module.design_summary(DESIGN, LINES, BUILDS, settings())
			self.assertEqual(summary["total_connected_w"], 403.1)
			self.assertTrue(summary["uses_dmx"])
			self.assertTrue(summary["uses_phase_dimming"])
			self.assertFalse(summary["review_required"])
			self.assertEqual(summary["runs"], len(DESIGN["runs"]))
			design = copy.deepcopy(DESIGN)
			design["zones"] = [{"id": "z1", "name": "Z", "color": "#112233", "method": "DMX512"}]
			with patch.object(module.gate, "gate_enabled", return_value=True):
				summary = module.design_summary(design, [], {}, settings())
			self.assertTrue(summary["uses_dmx"])
			self.assertEqual([r["code"] for r in summary["review_reasons"]], ["DMX"])


class Concurrency(unittest.TestCase):
	def record(self, **changes):
		return FakeDesign(**{"name": "SYSD-2026-00001", "is_current": 1, "status": "Draft", **changes})

	def check(self, module, frappe, record, expected):
		frappe.db.get_value.return_value = MODIFIED
		module._locked_for_edit(record, expected)

	def test_matching_timestamp_passes_and_locks_the_row(self):
		with load_service(DESIGNS) as (module, frappe):
			self.check(module, frappe, self.record(), str(MODIFIED))
			self.assertTrue(frappe.db.get_value.call_args.kwargs["for_update"])

	def test_refusals(self):
		cases = [
			({}, "2026-10-09 11:59:59", "CONFLICT"),
			({}, None, "INVALID"),
			({}, "yesterday", "INVALID"),
			({"is_current": 0}, str(MODIFIED), "CONFLICT"),
			({"status": "In Review"}, str(MODIFIED), "LOCKED"),
			({"status": "Approved"}, str(MODIFIED), "LOCKED"),
		]
		with load_service(DESIGNS) as (module, frappe):
			for changes, expected, code in cases:
				with self.subTest(changes=changes, expected=expected):
					with self.assertRaises(module.DesignError) as caught:
						self.check(module, frappe, self.record(**changes), expected)
					self.assertEqual(caught.exception.code, code)
			self.check(module, frappe, self.record(status="Changes Requested"), str(MODIFIED))


class Saving(unittest.TestCase):
	def setUp(self):
		self.context = load_service(DESIGNS)
		self.module, self.frappe = self.context.__enter__()
		self.schedule = Record(
			name="SCH-FIXTURE", version=2, schedule_name="Kitchen", ill_project="PRJ-1", customer="CUST-1"
		)
		module = self.module
		self.patches = [
			patch.object(module.access, "require_edit", return_value=self.schedule),
			patch.object(module, "require_designer"),
			patch.object(module, "settings", return_value=settings()),
			patch.object(module.expansion, "expand_schedule", return_value=(LINES, BUILDS, {})),
			patch.object(module.gate, "gate_enabled", return_value=False),
		]
		for item in self.patches:
			item.start()
		self.frappe.db.exists.return_value = True

	def tearDown(self):
		for item in self.patches:
			item.stop()
		self.context.__exit__(None, None, None)

	def test_first_save_creates_revision_a(self):
		record = FakeDesign()
		self.frappe.new_doc = MagicMock(return_value=record)
		with patch.object(self.module, "current_design", return_value=None):
			result = self.module.save_design("SCH-FIXTURE", json.dumps(DESIGN))
		self.assertEqual(record.saved, ["insert"])
		self.assertEqual((record.revision, record.status, record.is_current), ("A", "Draft", 1))
		self.assertEqual((record.fixture_schedule, record.schedule_version), ("SCH-FIXTURE", 2))
		self.assertEqual(record.title, "Kitchen design")
		self.assertEqual(record.build_hash, self.module.build_hash(DESIGN))
		self.assertEqual(json.loads(record.design_json), json.loads(self.module.canonical_json(DESIGN)))
		self.assertEqual(record.catalog_snapshot, DESIGN["catalogSnapshotHash"])
		self.assertEqual(len(json.loads(record.line_fingerprint_json)), 9)
		self.assertEqual(
			result,
			{
				"name": "SYSD-2026-00002",
				"revision": "A",
				"modified": str(MODIFIED),
				"build_hash": record.build_hash,
				"summary": json.loads(record.result_summary_json),
			},
		)

	def test_second_new_design_is_a_conflict(self):
		with patch.object(self.module, "current_design", return_value=FakeDesign(name="SYSD-2026-00001")):
			with self.assertRaises(self.module.DesignError) as caught:
				self.module.save_design("SCH-FIXTURE", DESIGN)
		self.assertEqual(caught.exception.code, "CONFLICT")

	def test_update_checks_owner_schedule_and_timestamp(self):
		record = FakeDesign(
			name="SYSD-2026-00001", is_current=1, status="Draft", revision="A", schedule_version=2
		)
		self.frappe.db.get_value.return_value = MODIFIED
		with patch.object(self.module.access, "require_design", return_value=record) as require:
			self.module.save_design("SCH-FIXTURE", DESIGN, "SYSD-2026-00001", str(MODIFIED))
		require.assert_called_once_with("SYSD-2026-00001", "SCH-FIXTURE")
		self.assertEqual(record.saved, ["save"])

	def test_schedule_mismatches(self):
		other = copy.deepcopy(DESIGN)
		other["schedule"]["version"] = 1
		with self.assertRaises(self.module.DesignError) as caught:
			self.module.save_design("SCH-FIXTURE", other)
		self.assertEqual(caught.exception.code, "CONFLICT")
		other["schedule"] = {"name": "SCH-OTHER", "version": 2}
		with self.assertRaises(self.module.DesignError) as caught:
			self.module.save_design("SCH-FIXTURE", other)
		self.assertEqual(caught.exception.code, "INVALID")
		self.frappe.db.exists.return_value = False
		with self.assertRaises(self.module.DesignError) as caught:
			self.module.save_design("SCH-FIXTURE", DESIGN)
		self.assertIn("catalog", caught.exception.message)

	def test_invalid_design_is_refused(self):
		broken = copy.deepcopy(DESIGN)
		broken["schemaVersion"] = 2
		with self.assertRaises(self.module.DesignError) as caught:
			self.module.save_design("SCH-FIXTURE", broken)
		self.assertEqual(caught.exception.code, "INVALID")


class Revising(unittest.TestCase):
	def test_copy_resets_review_and_children(self):
		with load_service(DESIGNS) as (module, frappe):
			old = FakeDesign(
				name="SYSD-2026-00001",
				revision="B",
				status="Approved",
				is_current=1,
				fixture_schedule="SCH-FIXTURE",
				approved_by="ae@example.com",
				comments=[{"body": "x"}],
			)
			copy_record = FakeDesign(**{k: v for k, v in old.items() if k != "name"})
			frappe.copy_doc = MagicMock(return_value=copy_record)
			frappe.db.get_value.return_value = 1
			with (
				patch.object(module.access, "require_design", return_value=old),
				patch.object(module.access, "require_edit"),
				patch.object(module, "require_designer"),
			):
				result = module.create_revision("SYSD-2026-00001", "  Moved the cabinet  ")
			self.assertEqual(result, {"name": "SYSD-2026-00002", "revision": "C"})
			self.assertEqual(old.is_current, 0)
			self.assertEqual(
				(
					copy_record.status,
					copy_record.revision_parent,
					copy_record.approved_by,
					copy_record.comments,
				),
				("Draft", "SYSD-2026-00001", None, []),
			)
			self.assertEqual(copy_record.notes, [("Comment", "Moved the cabinet")])

	def test_only_the_current_revision_can_be_revised(self):
		with load_service(DESIGNS) as (module, frappe):
			old = FakeDesign(name="SYSD-2026-00001", revision="A", fixture_schedule="S")
			frappe.db.get_value.return_value = 0
			with (
				patch.object(module.access, "require_design", return_value=old),
				patch.object(module.access, "require_edit"),
				patch.object(module, "require_designer"),
			):
				with self.assertRaises(module.DesignError) as caught:
					module.create_revision("SYSD-2026-00001")
			self.assertEqual(caught.exception.code, "CONFLICT")


if __name__ == "__main__":
	unittest.main()
