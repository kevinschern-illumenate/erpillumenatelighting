import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.publication_contract import callback_disposition, retry_at


class RevisionFence(unittest.TestCase):
	def disposition(self, **kwargs):
		job = {"state": "RUNNING", "lease_token": "secret", "revision_hash": "v1", "payload_hash": "p1"}
		return callback_disposition(
			job,
			**{
				"token": "secret",
				"revision_hash": "v1",
				"payload_hash": "p1",
				"current_hash": "v1",
				**kwargs,
			},
		)

	def test_old_callback_cannot_clear_new_revision(self):
		self.assertEqual(self.disposition(current_hash="v2"), "superseded")

	def test_token_revision_and_payload_must_all_match(self):
		for field in ("token", "revision_hash", "payload_hash"):
			with self.subTest(field=field), self.assertRaises(ValueError):
				self.disposition(**{field: "wrong"})
		self.assertEqual(self.disposition(), "current")

	def test_retries_back_off_and_stop(self):
		now = datetime(2026, 9, 25)
		self.assertEqual(retry_at(1, now), now + timedelta(seconds=30))
		self.assertEqual(retry_at(4, now), now + timedelta(seconds=240))
		self.assertEqual(retry_at(2, now, 120), now + timedelta(seconds=120))
		self.assertEqual(retry_at(7, now, 99999), now + timedelta(hours=1))
		self.assertIsNone(retry_at(8, now))


class StaffCapabilities(unittest.TestCase):
	def test_role_and_system_user_both_required(self):
		with load_service(ROOT + ".portal.staff") as (module, frappe):
			frappe.get_roles.return_value = ["ilL Catalog Publisher"]
			frappe.db.get_value.return_value = "Website User"
			self.assertFalse(module.allowed("catalog"))
			frappe.db.get_value.return_value = "System User"
			self.assertTrue(module.allowed("catalog"))
			self.assertFalse(module.allowed("integration"))


class PublicationCallbacks(unittest.TestCase):
	def dependencies(self):
		readiness = types.ModuleType(ROOT + ".api.product_readiness")
		readiness.content_record = lambda value: value
		readiness.evaluate = MagicMock()
		brand = types.ModuleType(ROOT + ".api.webflow_brand")
		brand.get_default_brand = lambda: "a"
		brand.resolve_brand = MagicMock()
		staff = types.ModuleType(ROOT + ".portal.staff")
		staff.require = MagicMock()
		staff.require_catalog_reader = MagicMock()
		return {module.__name__: module for module in (readiness, brand, staff)}

	def documents(self, operation="STAGE", current="v1"):
		job = Record(
			name="J1",
			state="RUNNING",
			lease_token="secret",
			revision_hash="v1",
			payload_hash="p1",
			operation=operation,
			attempts=1,
		)
		job["as_dict"] = lambda: job
		state = Record(current_hash=current, live_hash="last-good", name="STATE", remote_item_id="a" * 24)
		return job, state

	def test_staging_does_not_claim_live_publication(self):
		with load_service(ROOT + ".api.publication", self.dependencies()) as (module, _frappe):
			job, state = self.documents()
			with (
				patch.object(module, "_job_locked", return_value=(job, None, state, None)),
				patch.object(module, "_refresh"),
				patch.object(module, "_save"),
			):
				module.acknowledge("J1", "secret", "v1", "p1", "a" * 24)
			self.assertEqual(state.state, "STAGED")
			self.assertEqual(state.staged_hash, "v1")
			self.assertEqual(state.live_hash, "last-good")

	def test_stale_success_preserves_new_pending_state_and_live_hash(self):
		with load_service(ROOT + ".api.publication", self.dependencies()) as (module, _frappe):
			job, state = self.documents(current="v2")
			state["state"] = "NEEDS_REVIEW"
			with (
				patch.object(module, "_job_locked", return_value=(job, None, state, None)),
				patch.object(module, "_refresh"),
				patch.object(module, "_save"),
			):
				module.acknowledge("J1", "secret", "v1", "p1", "a" * 24)
			self.assertEqual(job.state, "SUPERSEDED")
			self.assertEqual(state.state, "NEEDS_REVIEW")
			self.assertEqual(state.live_hash, "last-good")

	def test_remote_identity_conflict_is_rejected(self):
		with load_service(ROOT + ".api.publication", self.dependencies()) as (module, _frappe):
			job, state = self.documents()
			with (
				patch.object(module, "_job_locked", return_value=(job, None, state, None)),
				patch.object(module, "_refresh"),
				patch.object(module, "_save") as save,
				self.assertRaisesRegex(ValueError, "identity conflict"),
			):
				module.acknowledge("J1", "secret", "v1", "p1", "b" * 24)
			save.assert_not_called()
