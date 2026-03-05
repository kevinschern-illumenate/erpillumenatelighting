# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Tests for QUOTED status transition flexibility in update_schedule_status().

Verifies that QUOTED allows transitions to both DRAFT and READY
for all users (privileged and non-privileged).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock


def _make_mock_schedule(status="QUOTED", is_locked=False):
	"""Return a mock schedule document."""
	mock = MagicMock()
	mock.status = status
	mock.is_locked = is_locked
	mock.name = "SCHED-001"
	return mock


class TestUpdateScheduleStatusQuotedTransitions(FrappeTestCase):
	"""Test QUOTED stage transition flexibility."""

	def _call_update(self, current_status, new_status, is_dealer=False, is_internal=False):
		"""Helper to call update_schedule_status with mocked permissions."""
		from illumenate_lighting.illumenate_lighting.api.portal import update_schedule_status

		mock_schedule = _make_mock_schedule(status=current_status)

		# The function does a local import from the doctype module, so we
		# patch at the source so the local import picks up our mocks.
		doctype_mod = "illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule"

		with patch.object(frappe.db, "exists", return_value=True), \
			patch.object(frappe, "get_doc", return_value=mock_schedule), \
			patch(
				f"{doctype_mod}.has_permission",
				return_value=True,
			), \
			patch(
				f"{doctype_mod}._is_dealer_user",
				return_value=is_dealer,
			), \
			patch(
				f"{doctype_mod}._is_internal_user",
				return_value=is_internal,
			):
			return update_schedule_status("SCHED-001", new_status)

	# ── Privileged user (dealer) transitions from QUOTED ─────────────────

	def test_quoted_to_draft_allowed_dealer(self):
		"""Privileged (dealer) user can move QUOTED -> DRAFT."""
		result = self._call_update("QUOTED", "DRAFT", is_dealer=True)
		self.assertTrue(result["success"])

	def test_quoted_to_ready_allowed_dealer(self):
		"""Privileged (dealer) user can move QUOTED -> READY."""
		result = self._call_update("QUOTED", "READY", is_dealer=True)
		self.assertTrue(result["success"])

	# ── Privileged user (internal) transitions from QUOTED ───────────────

	def test_quoted_to_draft_allowed_internal(self):
		"""Privileged (internal) user can move QUOTED -> DRAFT."""
		result = self._call_update("QUOTED", "DRAFT", is_internal=True)
		self.assertTrue(result["success"])

	def test_quoted_to_ready_allowed_internal(self):
		"""Privileged (internal) user can move QUOTED -> READY."""
		result = self._call_update("QUOTED", "READY", is_internal=True)
		self.assertTrue(result["success"])

	# ── Non-privileged user transitions from QUOTED ──────────────────────

	def test_quoted_to_draft_allowed_non_privileged(self):
		"""Non-privileged user can move QUOTED -> DRAFT."""
		result = self._call_update("QUOTED", "DRAFT", is_dealer=False, is_internal=False)
		self.assertTrue(result["success"])

	def test_quoted_to_ready_allowed_non_privileged(self):
		"""Non-privileged user can move QUOTED -> READY."""
		result = self._call_update("QUOTED", "READY", is_dealer=False, is_internal=False)
		self.assertTrue(result["success"])

	# ── Ensure other transitions still work as expected ──────────────────

	def test_draft_to_ready_allowed(self):
		"""DRAFT -> READY is always allowed."""
		result = self._call_update("DRAFT", "READY")
		self.assertTrue(result["success"])

	def test_ready_to_draft_allowed(self):
		"""READY -> DRAFT is always allowed."""
		result = self._call_update("READY", "DRAFT")
		self.assertTrue(result["success"])

	def test_ready_to_quoted_privileged_allowed(self):
		"""Privileged user can move READY -> QUOTED."""
		result = self._call_update("READY", "QUOTED", is_dealer=True)
		self.assertTrue(result["success"])

	def test_ready_to_quoted_non_privileged_blocked(self):
		"""Non-privileged user cannot move READY -> QUOTED."""
		result = self._call_update("READY", "QUOTED", is_dealer=False, is_internal=False)
		self.assertFalse(result["success"])
		self.assertIn("Cannot change status", result["error"])

	def test_draft_to_quoted_blocked(self):
		"""DRAFT -> QUOTED is not a valid transition."""
		result = self._call_update("DRAFT", "QUOTED")
		self.assertFalse(result["success"])
		self.assertIn("Cannot change status", result["error"])

	def test_same_status_noop(self):
		"""Setting same status returns success (no-op)."""
		result = self._call_update("QUOTED", "QUOTED")
		self.assertTrue(result["success"])
