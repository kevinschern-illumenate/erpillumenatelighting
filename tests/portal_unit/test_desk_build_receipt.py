"""Actual retry boundary with fake ERP persistence; SQL races still require Bench."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_configuration_save import Doc
from test_services import ROOT, Record, load_service


class DeskReceipt(unittest.TestCase):
	def test_unsaved_parent_retry_is_durable_and_rechecks_access(self):
		adapter = types.SimpleNamespace(resolve_line=MagicMock(), schedule_context=MagicMock())
		with load_service(ROOT + ".portal.desk_build_receipt", {ROOT + ".portal.configuration": adapter}) as (
			service,
			frappe,
		):
			stored = {}

			def lookup(dt, key, field, **kwargs):
				if dt == "User":
					return "System User" if field == "user_type" else 1
				return stored.get(key["request_key"])

			frappe.db.get_value.side_effect = lookup

			def create(data):
				doc = Doc(**data, flags=Doc())
				doc.insert = lambda **kwargs: stored.setdefault(doc.request_key, doc)
				return doc

			frappe.get_doc.side_effect = create
			calls = []

			@service.idempotent
			def build(
				parent_doctype, parent_name=None, schedule=None, idempotency_key="test-save-123", qty=1
			):
				calls.append(qty)
				return {"success": True, "row_values": {"item_code": "BUILD", "qty": qty}}

			first = build("Quotation")
			second = build("Quotation")
			self.assertEqual(calls, [1])
			self.assertEqual(first["save_receipt"], second["save_receipt"])
			self.assertTrue(second["already_existed"])
			with self.assertRaisesRegex(ValueError, "different configuration"):
				build("Quotation", qty=2)
			frappe.has_permission.return_value = False
			with self.assertRaises(PermissionError):
				build("Quotation")
			self.assertEqual(calls, [1])

	def test_failed_build_has_no_receipt_and_stale_schedule_never_builds(self):
		schedule = Doc(name="S", modified="new", lines=[])
		adapter = types.SimpleNamespace(
			resolve_line=MagicMock(return_value=None), schedule_context=MagicMock(return_value=schedule)
		)
		with load_service(ROOT + ".portal.desk_build_receipt", {ROOT + ".portal.configuration": adapter}) as (
			service,
			frappe,
		):
			frappe.db.get_value.side_effect = lambda dt, key, field, **kwargs: (
				("System User" if field == "user_type" else 1) if dt == "User" else None
			)
			calls = []

			@service.idempotent
			def build(
				parent_doctype,
				schedule="S",
				expected_modified="old",
				line_key=None,
				line_idx=None,
				idempotency_key="test-save-123",
			):
				calls.append(True)
				return {"success": False, "error": "Missing BOM"}

			with self.assertRaisesRegex(ValueError, "schedule changed"):
				build("Quotation")
			self.assertFalse(calls)
			self.assertFalse(build("Quotation", expected_modified="new")["success"])
			frappe.get_doc.assert_not_called()

	def test_reopen_returns_exact_saved_inputs_only_after_parent_access(self):
		line = Doc(
			name="L",
			line_key="stable",
			ill_configurator_request=json.dumps(
				{
					"family": "LED Tape",
					"selections": {
						"include_power_supply": False,
						"ordering_mode": "BULK_REEL",
						"tape_length_value": 50,
						"tape_length_unit": "ft",
					},
				}
			),
		)
		adapter = types.SimpleNamespace(
			FAMILIES={},
			resolve_line=MagicMock(return_value=line),
			schedule_context=MagicMock(return_value=Record(modified="r1")),
		)
		with load_service(
			ROOT + ".portal.configuration_reopen", {ROOT + ".portal.configuration": adapter}
		) as (service, frappe):
			result = service.load("S", line_key="stable")
			self.assertEqual(result["request"]["selections"]["include_power_supply"], False)
			self.assertEqual(result["request"]["selections"]["tape_length_value"], 50)
			frappe.get_doc.assert_not_called()
			adapter.schedule_context.side_effect = PermissionError("Revoked")
			with self.assertRaises(PermissionError):
				service.load("S", line_key="stable")
