"""Plan 3.3: bulk edit, delete and move of schedule lines, all or nothing."""

import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


class FakeCache:
	def __init__(self):
		self.values = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.values[key] = value

	def get_value(self, key):
		return self.values.get(key)

	def delete_value(self, key):
		self.values.pop(key, None)


class Line(Record):
	__setattr__ = dict.__setitem__

	def as_dict(self):
		return dict(self)


class Schedule(Record):
	__setattr__ = dict.__setitem__

	def append(self, field, values):
		row = Line(values)
		self.setdefault(field, []).append(row)
		return row


def positive_int(value, default=1, minimum=1):
	try:
		return max(int(value), minimum)
	except (TypeError, ValueError):
		return default


class BulkUpdateLines(unittest.TestCase):
	def setUp(self):
		self.enabled = True
		self.undo_on = True
		self.cache = FakeCache()
		self.schedule = Schedule(
			name="S1",
			status="DRAFT",
			is_locked=0,
			modified="rev-1",
			lines=[
				Line(name="r1", idx=1, line_key="k1", line_id="A1", qty=1, manufacturer_type="ILLUMENATE"),
				Line(name="r2", idx=2, line_key="p1", line_id="PS", qty=2, power_supply_for_line="k1"),
				Line(name="r3", idx=3, line_key="k3", line_id="B1", qty=5, manufacturer_type="OTHER"),
				Line(name="r4", idx=4, line_key="k4", line_id="C1", qty=1, manufacturer_type="ILLUMENATE"),
			],
		)
		self.schedule.save = MagicMock()
		self.target = Schedule(name="S2", status="READY", is_locked=0, modified="rev-2", lines=[])
		self.target.save = MagicMock()
		self.calls = []
		self.clone = MagicMock()

		def schedule_context(name, write=False, lock=False):
			self.calls.append((name, write, lock))
			return {"S1": self.schedule, "S2": self.target}[name]

		def resolve_line(schedule, line_key=None, line_idx=None):
			matches = [line for line in schedule.lines if line_key in (line.line_key, line.name)]
			if len(matches) != 1:
				raise ValueError("The selected line changed or is unavailable; reload the schedule")
			return matches[0]

		def require_fresh(schedule, expected_modified=None):
			if expected_modified and str(expected_modified) != str(schedule.modified):
				raise ValueError("This schedule changed since you opened it. Reload to see the latest version.")

		self.extras = {
			ROOT + ".api.build_artifacts": types.SimpleNamespace(atomic_build=lambda function: function),
			ROOT + ".portal.site_flags": types.SimpleNamespace(
				line_copy_enabled=lambda: True,
				bulk_edit_enabled=lambda: self.enabled,
				undo_enabled=lambda: self.undo_on,
			),
			ROOT + ".portal.line_undo": types.SimpleNamespace(
				snapshot=lambda schedule, lines: [],
				previous_values=lambda lines, values: [],
				remember=lambda *args, **kwargs: None,
			),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				schedule_context=schedule_context, resolve_line=resolve_line
			),
			ROOT + ".portal.schedule_lines": types.SimpleNamespace(require_fresh=require_fresh),
			ROOT + ".portal.line_intent": types.SimpleNamespace(
				intent_values=lambda line, exclude: {
					**{k: v for k, v in line.as_dict().items() if k not in exclude},
					"configuration_status": "Pending",
				}
			),
			ROOT + ".portal.line_documents": types.SimpleNamespace(clone=self.clone),
			ROOT + ".utils": types.SimpleNamespace(parse_positive_int=positive_int),
			ROOT + ".system_design.dealer_data": types.SimpleNamespace(apply=lambda line, data: None),
			ROOT + ".portal.files": types.SimpleNamespace(finalize_spec=MagicMock()),
		}

	@contextmanager
	def module(self):
		with load_service(ROOT + ".portal.line_copy", self.extras) as (line_copy, _):
			with load_service(ROOT + ".portal.line_edit", self.extras) as (line_edit, _):
				extras = {
					**self.extras,
					ROOT + ".portal.line_copy": line_copy,
					ROOT + ".portal.line_edit": line_edit,
				}
				with load_service(ROOT + ".portal.line_undo", extras) as (line_undo, undo_frappe):
					undo_frappe.cache = lambda: self.cache
					self.line_undo, self.undo_frappe = line_undo, undo_frappe
					extras[ROOT + ".portal.line_undo"] = line_undo
					with load_service(ROOT + ".portal.bulk_lines", extras) as (module, frappe):
						yield module, frappe

	def run_bulk(self, keys, changes, expected_modified="rev-1"):
		with self.module() as (module, _frappe):
			return module.bulk_update_lines("S1", json.dumps(keys), json.dumps(changes), expected_modified)

	def ids(self, schedule=None):
		return [line.line_id for line in (schedule or self.schedule).lines]

	def test_fields_are_set_on_every_selected_line_through_the_row_validator(self):
		result = self.run_bulk(["k1", "k3"], {"qty": "4", "location": "  Lobby  ", "notes": "Paint\n"})
		self.assertEqual(self.calls, [("S1", True, True)])
		self.assertEqual((result["success"], result["count"], result["action"]), (True, 2, "update"))
		self.assertEqual(result["modified"], "rev-1")
		a1, ps, b1, c1 = self.schedule.lines
		self.assertEqual((a1.qty, a1.location, a1.notes), (4, "Lobby", "Paint\n"))
		self.assertEqual((b1.qty, b1.location), (4, "Lobby"))
		self.assertEqual((ps.qty, c1.qty), (2, 1), "unselected lines keep their values")
		self.assertNotIn("location", c1)
		self.schedule.save.assert_called_once_with(ignore_permissions=True)

	def test_line_id_can_be_set_and_location_cleared(self):
		self.schedule.lines[0]["location"] = "Old"
		self.run_bulk(["k1"], {"line_id": "T2", "location": None})
		self.assertEqual((self.schedule.lines[0].line_id, self.schedule.lines[0].location), ("T2", ""))

	def test_a_failing_line_saves_nothing_and_is_reported(self):
		calls = []

		def apply_line_data(schedule, line, data):
			calls.append(line.line_id)
			if line.line_id == "B1":
				raise ValueError("Upload the replacement specification and provide its File ID.")
			line.qty = data["qty"]

		self.extras[ROOT + ".portal.line_edit"] = types.SimpleNamespace(apply_line_data=apply_line_data)
		with load_service(ROOT + ".portal.line_copy", self.extras) as (line_copy, _):
			extras = {**self.extras, ROOT + ".portal.line_copy": line_copy}
			with load_service(ROOT + ".portal.bulk_lines", extras) as (module, _frappe):
				result = module.bulk_update_lines("S1", '["k1", "k3", "k4"]', '{"qty": 9}', "rev-1")
		self.assertEqual(calls, ["A1", "B1", "C1"], "every line is validated so all errors are reported")
		self.assertFalse(result["success"])
		self.assertEqual(
			result["errors"],
			[{"line_key": "k3", "line": "B1", "error": "Upload the replacement specification and provide its File ID."}],
		)
		self.schedule.save.assert_not_called()

	def test_unknown_lines_are_reported_without_changes(self):
		result = self.run_bulk(["k1", "gone", "also-gone"], {"qty": 3})
		self.assertFalse(result["success"])
		self.assertEqual([error["line_key"] for error in result["errors"]], ["gone", "also-gone"])
		self.assertIn("reload the schedule", result["errors"][0]["error"])
		self.assertEqual(self.schedule.lines[0].qty, 1)
		self.schedule.save.assert_not_called()

	def test_invalid_requests_are_refused(self):
		cases = [
			(["k1"], {"qty": 0}, "rev-1", "whole number"),
			(["k1"], {"qty": "2.5"}, "rev-1", "whole number"),
			(["k1"], {"qty": "x"}, "rev-1", "whole number"),
			(["k1"], {"line_id": "x" * 141}, "rev-1", "limited to 140"),
			(["k1"], {"line_id": ["x"]}, "rev-1", "Invalid value"),
			(["k1"], {"configured_fixture": "CF-9"}, "rev-1", "at least one field"),
			(["k1"], {"action": "explode"}, "rev-1", "Unsupported"),
			(["k1"], {"action": "move"}, "rev-1", "Choose a schedule"),
			(["k1"], {"action": "move", "target_schedule": "S1"}, "rev-1", "different schedule"),
			([], {"qty": 1}, "rev-1", "between 1 and 100"),
			(["k1"], {"qty": 2}, "rev-0", "changed since you opened it"),
		]
		for keys, changes, modified, message in cases:
			with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
				self.run_bulk(keys, changes, modified)
		self.schedule["is_locked"] = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.run_bulk(["k1"], {"qty": 2})
		self.schedule.update(is_locked=0, status="ORDERED")
		with self.assertRaisesRegex(ValueError, "Draft or Ready"):
			self.run_bulk(["k1"], {"qty": 2})
		self.assertEqual(self.schedule.lines[0].qty, 1)
		self.schedule.save.assert_not_called()

	def test_delete_removes_the_selected_lines_and_renumbers(self):
		result = self.run_bulk(["k3", "k1"], {"action": "delete"})
		self.assertEqual((result["success"], result["count"]), (True, 2))
		self.assertEqual(self.ids(), ["PS", "C1"], "like a single delete, an owner's supply line stays")
		self.assertEqual([line.idx for line in self.schedule.lines], [1, 2])
		self.schedule.save.assert_called_once_with(ignore_permissions=True)

	def test_move_copies_to_the_target_then_removes_from_this_schedule(self):
		result = self.run_bulk(
			["k1", "k4"], {"action": "move", "target_schedule": "S2", "target_modified": "rev-2"}
		)
		self.assertEqual(self.calls, [("S1", True, True), ("S2", True, True)])
		self.assertEqual(self.ids(self.target), ["A1", "PS", "C1"])
		self.assertTrue(all(line.configuration_status == "Pending" for line in self.target.lines))
		self.assertEqual(self.target.lines[1].power_supply_for_line, self.target.lines[0].line_key)
		self.assertEqual(self.ids(), ["B1"], "moved supply lines leave with their owner")
		self.assertEqual((result["target"], result["count"], len(result["line_keys"])), ("S2", 3, 2))
		self.target.save.assert_called_once_with(ignore_permissions=True)
		self.schedule.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(self.clone.call_count, 3)

	def test_move_refuses_a_locked_or_changed_target(self):
		with self.assertRaisesRegex(ValueError, "target schedule changed"):
			self.run_bulk(["k1"], {"action": "move", "target_schedule": "S2", "target_modified": "rev-1"})
		self.target["is_locked"] = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.run_bulk(["k1"], {"action": "move", "target_schedule": "S2"})
		self.assertEqual(self.target.lines, [])
		self.assertEqual(len(self.schedule.lines), 4)
		self.schedule.save.assert_not_called()

	def undo(self, token, user="buyer@example.com"):
		with self.module() as (_module, _frappe):
			self.undo_frappe.session = Record(user=user)
			return self.line_undo.undo_line_action(token)

	def test_delete_offers_an_undo_that_restores_rows_with_their_keys_and_places(self):
		original = [dict(line) for line in self.schedule.lines]
		result = self.run_bulk(["k3", "k1"], {"action": "delete"})
		self.assertEqual({key: result["undo"][key] for key in ("expires_in", "action", "count")}, {
			"expires_in": 10, "action": "delete", "count": 2
		})
		stored = json.loads(self.cache.values["ill_portal_line_undo:" + result["undo"]["token"]])
		self.assertEqual((stored["user"], stored["schedule"]), ("buyer@example.com", "S1"))
		self.assertNotIn("name", stored["rows"][0]["row"], "system fields are not kept")
		self.schedule.save.reset_mock()
		restored = self.undo(result["undo"]["token"])
		self.assertEqual((restored["success"], restored["action"], restored["count"]), (True, "delete", 2))
		self.assertEqual([line.line_key for line in self.schedule.lines], [row["line_key"] for row in original])
		self.assertEqual([line.idx for line in self.schedule.lines], [1, 2, 3, 4])
		self.assertEqual(self.schedule.lines[2].qty, 5)
		self.schedule.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(self.cache.values, {}, "a receipt is used once")
		with self.assertRaisesRegex(ValueError, "can no longer be undone"):
			self.undo(result["undo"]["token"])

	def test_undo_refuses_a_line_key_that_is_back_or_an_uneditable_schedule(self):
		token = self.run_bulk(["k3"], {"action": "delete"})["undo"]["token"]
		self.schedule.lines.append(Line(name="r9", idx=9, line_key="k3", line_id="B1"))
		with self.assertRaisesRegex(ValueError, "already in this schedule"):
			self.undo(token)
		self.schedule.lines.pop()
		self.schedule["is_locked"] = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.undo(token)
		self.schedule.update(is_locked=0, status="ORDERED")
		with self.assertRaisesRegex(ValueError, "Draft or Ready"):
			self.undo(token)
		self.assertEqual(self.ids(), ["A1", "PS", "C1"])
		self.assertEqual([call[0] for call in self.calls[-3:]], ["S1", "S1", "S1"])
		self.assertTrue(all(call[1:] == (True, True) for call in self.calls), "restore re-checks edit access")

	def test_undo_receipts_are_personal_expire_and_follow_the_kill_switch(self):
		token = self.run_bulk(["k3"], {"action": "delete"})["undo"]["token"]
		with self.assertRaisesRegex(ValueError, "can no longer be undone"):
			self.undo(token, user="someone@example.com")
		with self.assertRaisesRegex(ValueError, "can no longer be undone"):
			self.undo("forged-token")
		key = "ill_portal_line_undo:" + token
		receipt = json.loads(self.cache.values[key])
		self.cache.values[key] = json.dumps({**receipt, "expires": receipt["expires"] - 60})
		with self.assertRaisesRegex(ValueError, "can no longer be undone"):
			self.undo(token)
		self.cache.values[key] = json.dumps(receipt)
		self.undo_on = False
		with self.assertRaisesRegex(ValueError, "Undo is turned off"):
			self.undo(token)
		self.assertNotIn("undo", self.run_bulk(["k4"], {"action": "delete"}))
		with self.module() as (_module, _frappe):
			self.assertEqual(self.line_undo.undo_line_action.whitelist_options, {"methods": ["POST"]})
			self.undo_frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				self.line_undo.undo_line_action(token)

	def test_undo_of_a_move_restores_the_lines_and_withdraws_the_copies(self):
		self.target.lines.append(Line(name="t1", idx=1, line_key="other", line_id="Z9"))
		result = self.run_bulk(["k1"], {"action": "move", "target_schedule": "S2", "target_modified": "rev-2"})
		self.assertEqual(self.ids(self.target), ["Z9", "A1", "PS"])
		self.assertEqual(result["undo"]["count"], 2, "the owner's supply line moved too")
		copies = {line.line_key for line in self.target.lines[1:]}
		self.target.save.reset_mock()
		self.undo(result["undo"]["token"])
		self.assertEqual(self.ids(), ["A1", "PS", "B1", "C1"])
		self.assertEqual([line.line_key for line in self.schedule.lines][:2], ["k1", "p1"])
		self.assertEqual(self.ids(self.target), ["Z9"])
		self.target.save.assert_called_once_with(ignore_permissions=True)
		doctype, filters, field, value = self.undo_frappe.db.set_value.call_args.args
		self.assertEqual((doctype, field, value), ("ilL-Line-Document", "active", 0))
		self.assertEqual((filters["schedule"], filters["line_key"][0]), ("S2", "in"))
		self.assertEqual(set(filters["line_key"][1]), copies)

	def test_undo_of_a_move_refuses_when_the_copies_changed_or_the_target_locked(self):
		token = self.run_bulk(["k4"], {"action": "move", "target_schedule": "S2"})["undo"]["token"]
		self.target["is_locked"] = 1
		with self.assertRaisesRegex(ValueError, "locked"):
			self.undo(token)
		self.target["is_locked"] = 0
		self.target.lines.clear()
		with self.assertRaisesRegex(ValueError, "changed in the other schedule"):
			self.undo(token)

	def test_undo_of_a_bulk_edit_restores_the_previous_values(self):
		self.schedule.lines[0]["location"] = "Old"
		token = self.run_bulk(["k1", "k3"], {"qty": "4", "location": "Lobby"})["undo"]["token"]
		self.undo(token)
		a1, _ps, b1, _c1 = self.schedule.lines
		self.assertEqual((a1.qty, a1.location, b1.qty, b1.location), (1, "Old", 5, ""))
		token = self.run_bulk(["k1"], {"qty": "4"})["undo"]["token"]
		self.schedule.lines[0]["qty"] = 7
		with self.assertRaisesRegex(ValueError, "changed again"):
			self.undo(token)
		self.assertEqual(self.schedule.lines[0].qty, 7)

	def test_kill_switch_guest_and_post_only(self):
		self.enabled = False
		with self.assertRaisesRegex(ValueError, "turned off"):
			self.run_bulk(["k1"], {"qty": 2})
		self.enabled = True
		with self.module() as (module, frappe):
			self.assertEqual(module.bulk_update_lines.whitelist_options, {"methods": ["POST"]})
			frappe.session = Record(user="Guest")
			with self.assertRaises(PermissionError):
				module.bulk_update_lines("S1", '["k1"]', '{"qty": 2}')
		self.assertEqual(self.calls, [])


if __name__ == "__main__":
	unittest.main()
