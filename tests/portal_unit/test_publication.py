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
		payload, readiness, _export = self.refresh("Active", "Webflow Draft", published_on=None, is_active=1)
		self.assertFalse(payload["active"])
		# The reason is given (owner, 2026-11-20), not a readiness message.
		self.assertEqual(len(readiness["inactive_reasons"]), 1)

	def test_a_live_template_without_a_webflow_status_says_so(self):
		payload, readiness, _export = self.refresh("Active + Live", None, is_active=1)
		self.assertFalse(payload["active"])
		self.assertEqual(readiness["inactive_reasons"], ["the product's Webflow Status is not set"])

	def test_internal_only_keeps_a_published_page_up_without_the_readiness_issue(self):
		payload, readiness, _export = self.refresh("Internal Only", is_active=1)
		self.assertTrue(payload["active"])
		self.assertEqual(payload["webflow_state"]["effective_status"], "Discontinued")
		self.assertEqual(readiness["issues"], [])

	def test_a_live_template_leaves_the_hash_key_out(self):
		payload, _readiness, _export = self.refresh("Active + Live", is_active=1)
		self.assertNotIn("effective_webflow_status", payload)
		self.assertEqual(payload["webflow_state"]["effective_status"], "Published")


class PublicationScope(unittest.TestCase):
	"""webflow_sync_scope at the job queue (final review, plan 2026-11-23): jobs queued from any
	button (Publication dialog, wizard, retry, legacy trigger) never reach n8n out of scope."""

	def setUp(self):
		context = load_service(ROOT + ".api.publication", PublicationCallbacks.dependencies(self))
		self.module, self.frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		# The n8n_config publication holds (it may predate this test's frappe stub).
		for target, attr, value in (
			(self.module.n8n_config, "frappe", self.frappe),
			(self.module.webflow_approvals, "pending", MagicMock(return_value=None)),
			(self.module.webflow_approvals, "assert_no_pending", MagicMock()),
			(self.module, "now_datetime", lambda: datetime(2026, 11, 23, 12, 0)),
		):
			patcher = patch.object(target, attr, value)
			patcher.start()
			self.addCleanup(patcher.stop)
		# n8n_config may keep this frappe stub after the test: never leave a scope behind.
		self.addCleanup(self.frappe.conf.pop, "webflow_sync_scope", None)
		self.frappe.conf["webflow_sync_scope"] = {
			"doctypes": ["ilL-Fixture-Template"],
			"brands": ["illumenate"],
		}
		self.state = Record(name="STATE", current_hash="v1", approved_hash="v1", remote_item_id=None)
		self.docs = {
			"KIT-JOB": Product(name="kit-ra01", kit_template="KIT-RA01"),
			"FX-JOB": Product(name="ill-ra01-sw", fixture_template="ILL-RA01-SW"),
		}
		self.jobs = {
			name: Record(
				name=name,
				product=doc.name,
				brand="illumenate",
				state="QUEUED",
				operation="STAGE",
				revision_hash="v1",
				payload_hash="p1",
				attempts=0,
				payload_json="{}",
			)
			for name, doc in self.docs.items()
		}

	def locked(self, name):
		return self.jobs[name], self.docs[name], self.state, {}

	def test_claim_skips_out_of_scope_job(self):
		self.frappe.db.sql = MagicMock(return_value=[Record(name="KIT-JOB"), Record(name="FX-JOB")])
		self.frappe.db.exists = MagicMock(return_value=False)
		with (
			patch.object(self.module, "_job_locked", side_effect=self.locked),
			patch.object(self.module, "_refresh", return_value=(None, {"ready": True})),
			patch.object(self.module, "_save"),
		):
			claimed = self.module.claim("illumenate", limit=1)["jobs"]
		# The older kit job is skipped and does not use up the limit; it stays queued, untouched.
		self.assertEqual([job["job"] for job in claimed], ["FX-JOB"])
		self.assertEqual(self.jobs["KIT-JOB"].state, "QUEUED")

	def test_request_refuses_out_of_scope_product(self):
		with (
			patch.object(self.module, "_locked", return_value=(self.docs["KIT-JOB"], self.state, {})),
			patch.object(self.module, "_refresh") as refresh,
			self.assertRaisesRegex(ValueError, "ilL-Extrusion-Kit-Template is not enabled"),
		):
			self.module.request("kit-ra01", "illumenate", "STAGE", "v1")
		refresh.assert_not_called()

	def test_request_refuses_out_of_scope_brand(self):
		with (
			patch.object(self.module, "_locked", return_value=(self.docs["FX-JOB"], self.state, {})),
			patch.object(self.module, "_refresh"),
			self.assertRaisesRegex(ValueError, "Brand lighting_206 is not enabled"),
		):
			self.module.request("ill-ra01-sw", "lighting_206", "STAGE", "v1")

	def test_retry_refuses_out_of_scope_product(self):
		self.jobs["KIT-JOB"]["state"] = "FAILED"
		with (
			patch.object(self.module, "_job_locked", side_effect=self.locked),
			patch.object(self.module, "_refresh"),
			patch.object(self.module, "_save") as save,
			self.assertRaisesRegex(ValueError, "ilL-Extrusion-Kit-Template is not enabled"),
		):
			self.module.retry("KIT-JOB")
		save.assert_not_called()


class Product(Record):
	def get(self, key, default=None):
		return super().get(key, default)
