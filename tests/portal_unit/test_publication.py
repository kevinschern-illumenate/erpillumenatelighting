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


class EffectiveStatusGate(unittest.TestCase):
	"""The template's Product Status decides whether a linked product pushes (owner 2026-11-08)."""

	def refresh(self, template_status, webflow_status="Published", published_on="2026-11-01", is_active=0):
		deps = PublicationCallbacks.dependencies(None)
		with load_service(ROOT + ".api.publication", deps) as (module, _frappe):
			from test_services import Record

			readiness = {
				"ready": True,
				"issues": [{"field": "product_status", "message": "Internal Only templates stay off"}],
				"dependencies": [],
			}
			deps[ROOT + ".api.product_readiness"].evaluate.return_value = readiness
			state = Record(brand="illumenate", published_on=published_on, approved_hash=None)
			doc = Record(
				name="kit-ra02",
				product_slug="kit-ra02",
				is_active=is_active,
				webflow_status=webflow_status,
				product_category=None,
				target_brands=[],
			)
			export = types.ModuleType(ROOT + ".api.webflow_export_v2")
			export.get_webflow_products = MagicMock(return_value={"products": [{"name": "kit-ra02"}]})
			sync = types.ModuleType(ROOT + ".webflow_sync_payload")
			sync.template_section = MagicMock(return_value=None)
			import sys

			for extra in (export, sync):
				sys.modules[extra.__name__] = extra
				self.addCleanup(sys.modules.pop, extra.__name__, None)
			state_module = sys.modules[ROOT + ".webflow_state"] = __import__("importlib").import_module(
				ROOT + ".webflow_state"
			)
			with (
				patch.object(state_module, "template_status", return_value=template_status),
				patch.object(module, "Listing", side_effect=lambda value: value),
				patch.object(module, "_save"),
				patch.object(module, "_targeted", return_value=True),
				patch.object(module, "_strip_volatile_metadata", side_effect=lambda value: value),
			):
				payload, readiness = module._refresh(
					doc, state, {"is_active": True, "sync_enabled": True, "collections": {"Products": "c"}}
				)
			return payload, readiness, export.get_webflow_products

	def test_a_published_page_under_a_draft_template_pushes_hidden(self):
		payload, _readiness, export = self.refresh("Draft")
		self.assertTrue(payload["active"])
		self.assertEqual(payload["webflow_state"]["effective_status"], "Webflow Draft")
		self.assertEqual(payload["effective_webflow_status"], "Webflow Draft")
		export.assert_called_once()

	def test_never_published_under_a_plain_active_template_does_not_push(self):
		payload, _readiness, _export = self.refresh("Active", "Webflow Draft", published_on=None, is_active=1)
		self.assertFalse(payload["active"])

	def test_internal_only_keeps_a_published_page_up_without_the_readiness_issue(self):
		payload, readiness, _export = self.refresh("Internal Only", is_active=1)
		self.assertTrue(payload["active"])
		self.assertEqual(payload["webflow_state"]["effective_status"], "Discontinued")
		self.assertEqual(readiness["issues"], [])

	def test_a_live_template_leaves_the_hash_key_out(self):
		payload, _readiness, _export = self.refresh("Active + Live", is_active=1)
		self.assertNotIn("effective_webflow_status", payload)
		self.assertEqual(payload["webflow_state"]["effective_status"], "Published")
