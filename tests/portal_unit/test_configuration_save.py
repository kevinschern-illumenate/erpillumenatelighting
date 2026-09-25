"""Real save orchestration with explicit permission, engine and database boundaries."""

import json
import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class Doc(Record):
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value

	def reload(self):
		return self

	def save(self, **kwargs):
		self.modified = "revision-2"

	def append(self, field, values):
		row = Doc(name="child-new", **values)
		self[field].append(row)
		return row


@contextmanager
def service():
	policy = types.ModuleType(ROOT + ".portal.access")
	policy.can_edit_schedule = MagicMock(return_value=True)
	policy.can_read_schedule = MagicMock(return_value=True)
	with (
		load_service(ROOT + ".api.build_artifacts") as (atomic, _),
		load_service(
			ROOT + ".portal.configuration",
			{ROOT + ".portal.access": policy, ROOT + ".api.build_artifacts": atomic},
		) as (module, frappe),
	):
		atomic.frappe = frappe
		schedule = Doc(
			name="S1",
			modified="revision-1",
			status="DRAFT",
			is_locked=0,
			lines=[Doc(name="child-a", line_key="stable-a", qty=2, notes="Buyer note")],
		)
		stored = {}

		def get_doc(doctype, name=None):
			if isinstance(doctype, str):
				return schedule
			doc = Doc(**doctype, flags=Doc())

			def insert(**kwargs):
				stored[doc.request_key] = doc
				return doc

			doc.insert = insert
			return doc

		frappe.get_doc.side_effect = get_doc
		frappe.db.get_value.side_effect = lambda dt, filters, *a, **k: stored.get(filters.get("request_key"))
		with (
			patch.object(module, "normalized_payload", return_value={}),
			patch.object(
				module, "persist_artifact", return_value={"item_code": "BUILD", "bom": "BOM1"}
			) as build,
			patch.object(
				module,
				"apply_artifact",
				side_effect=lambda schedule, line, *a: (
					line or schedule.append("lines", {"line_key": "stable-new"})
				),
			),
		):
			yield module, frappe, policy, schedule, stored, build


def args(**extra):
	return dict(
		schedule_name="S1",
		family="LED Sheet",
		selections={"template": "SHEET"},
		idempotency_key="attempt-1234",
		expected_modified="revision-1",
		**extra,
	)


class ConfigurationSave(unittest.TestCase):
	def test_retry_reuses_receipt_even_after_schedule_revision_changes(self):
		with service() as (module, _frappe, _policy, schedule, stored, build):
			first = module.save(**args())
			second = module.save(**args())
			self.assertEqual(first["line_key"], second["line_key"])
			self.assertTrue(second["already_existed"])
			self.assertEqual(len(schedule.lines), 2)
			self.assertEqual(len(stored), 1)
			build.assert_called_once()

	def test_same_key_different_body_fails_before_engine(self):
		with service() as (module, _frappe, _policy, _schedule, _stored, build):
			module.save(**args())
			with self.assertRaisesRegex(ValueError, "different content"):
				module.save(**args(metadata={"qty": 3}))
			build.assert_called_once()

	def test_current_permission_is_rechecked_even_for_a_receipt(self):
		with service() as (module, _frappe, policy, _schedule, _stored, build):
			module.save(**args())
			policy.can_edit_schedule.side_effect = [True, False]
			with self.assertRaises(PermissionError):
				module.save(**args())
			build.assert_called_once()

	def test_stale_schedule_fails_before_creating_artifacts(self):
		with service() as (module, _frappe, _policy, schedule, _stored, build):
			schedule.modified = "someone-else-saved"
			with self.assertRaisesRegex(ValueError, "schedule changed"):
				module.save(**args(line_key="stable-a"))
			build.assert_not_called()

	def test_failed_artifact_rolls_back_without_receipt(self):
		with service() as (module, frappe, _policy, _schedule, stored, build):
			build.side_effect = ValueError("BOM failed")
			with self.assertRaisesRegex(ValueError, "BOM failed"):
				module.save(**args())
			frappe.db.rollback.assert_called_once_with(save_point="build_save")
			self.assertFalse(stored)

	def test_stable_line_resolution_ignores_reorder_and_rejects_fractional_ordinal(self):
		with service() as (module, _frappe, _policy, schedule, _stored, _build):
			original = schedule.lines[0]
			schedule.lines.insert(0, Doc(name="child-b", line_key="stable-b"))
			self.assertIs(module.resolve_line(schedule, "stable-a"), original)
			for value in [0.5, "nan", -1, 9]:
				with self.assertRaises(ValueError):
					module.resolve_line(schedule, line_idx=value)

	def test_apply_replaces_family_links_and_preserves_customer_context(self):
		with load_service(ROOT + ".api.build_artifacts") as (atomic, _):
			policy = types.ModuleType(ROOT + ".portal.access")
			policy.can_edit_schedule = policy.can_read_schedule = lambda doc: True
			sheet = types.ModuleType(ROOT + ".api.led_sheet_configurator")
			sheet.remove_sheet_accessories_for_line = MagicMock()
			with load_service(
				ROOT + ".portal.configuration",
				{
					ROOT + ".api.build_artifacts": atomic,
					ROOT + ".portal.access": policy,
					ROOT + ".api.led_sheet_configurator": sheet,
				},
			) as (module, _):
				line = Doc(
					name="C1",
					line_key="stable",
					configured_led_sheet="OLD",
					qty=3,
					notes="Keep",
					location="Lobby",
				)
				schedule = Doc(lines=[line])
				module.apply_artifact(
					schedule,
					line,
					"LED Tape",
					{
						"configured_tape_neon": "NEW",
						"item_code": "ITEM",
						"bom": "BOM",
						"template_code": "TAPE",
					},
					{},
				)
				self.assertEqual((line.qty, line.notes, line.location), (3, "Keep", "Lobby"))
				self.assertIsNone(line.configured_led_sheet)
				self.assertEqual((line.configured_tape_neon, line.ill_bom), ("NEW", "BOM"))
				sheet.remove_sheet_accessories_for_line.assert_called_once_with(schedule, line)
