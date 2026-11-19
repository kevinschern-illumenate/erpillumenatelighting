"""Gallery publication service (docs/WEBFLOW_GALLERY_SYNC.md sections 5.2, 6, 6a), stubbed Frappe.

The pure readiness and projection modules run for real, so hashes move exactly as they would on a site.
"""

import copy
import json
import os
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.gallery_publication"
CONTROLLER = ROOT + ".doctype.ill_webflow_gallery.ill_webflow_gallery"
GALLERY = "ilL-Webflow-Gallery"
STATE = "ilL-Gallery-Publication"
JOB = "ilL-Gallery-Publish-Job"
NOW = datetime(2026, 11, 18, 12, 0)
ITEM_A, ITEM_B, ITEM_G = "a" * 24, "b" * 24, "c" * 24
CONFIG = {
	"brand_code": "staging2",
	"is_active": True,
	"sync_enabled": True,
	"webflow_site_id": "site",
	"collections": {"Galleries": "galleries"},
	"erpnext_base_url": "https://erp.example.com",
}

# load_service reads module files relative to the working directory: run from the repository root.
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_previous_cwd = None


def setUpModule():
	global _previous_cwd
	_previous_cwd = os.getcwd()
	os.chdir(REPO)


def tearDownModule():
	os.chdir(_previous_cwd)


class Doc(Record):
	"""A saved record: attribute writes land in the dict, as `doc.get` reads them on a real Document."""

	def __setattr__(self, key, value):
		self[key] = value

	def as_dict(self):
		return dict(self)


def ready_gallery(**overrides):
	gallery = {
		"name": "G1",
		"gallery_title": "Hotel Lobby",
		"slug": "hotel-lobby",
		"is_active": 1,
		"gallery_images": [
			{"image": "/files/hero.jpg", "alt_text": "Hero"},
			{"image": "/files/second.jpg", "alt_text": "Second"},
		],
		"gallery_type": "Lobby",
		"applications": [],
		"services_provided": [],
		"products_used": [{"product": "rainier-sf", "series": "Rainier", "note": "White finish"}],
		"credits": [{"credit_type": "Integrator", "credit_name": "Acme", "website": "https://acme.example"}],
		"videos": "",
		"seo_description": "A lobby.",
		"about": "Warm light.",
		"completion_date": "2026-01-01",
		"target_brands": [{"brand": "staging2", "enabled": 1}],
	}
	gallery.update(overrides)
	return gallery


def matches(record, filters):
	"""Frappe-style filters: a value, ["in", values] or ["!=", value]."""
	for key, wanted in filters.items():
		value = record.get(key)
		if isinstance(wanted, list | tuple):
			op, operand = wanted
			if (op == "in" and value not in operand) or (op == "!=" and value == operand):
				return False
		elif value != wanted:
			return False
	return True


class GalleryPublicationCase(unittest.TestCase):
	def setUp(self):
		self.gallery = ready_gallery()
		self.item_ids = {"rainier-sf": ITEM_A}
		self.jobs = {}
		self.conf = {"n8n_gallery_webhook_url": "https://n8n.example/webhook/gallery"}
		self.state = Doc(name="P1", gallery="G1", brand="staging2", state="NEEDS_REVIEW")
		self.notify = types.ModuleType(ROOT + ".webflow_notify")
		self.notify.notify = MagicMock(return_value=[])
		self.notify.success_push = MagicMock(return_value=True)
		self.staff = types.ModuleType(ROOT + ".portal.staff")
		self.staff.require = MagicMock()
		self.staff.require_catalog_reader = MagicMock()
		brand = types.ModuleType(ROOT + ".api.webflow_brand")
		brand.get_default_brand = lambda: "illumenate"
		brand.resolve_brand = MagicMock(return_value=CONFIG)
		self.deps = {m.__name__: m for m in (self.notify, self.staff, brand)}

	# Boundary doubles -------------------------------------------------------------------------

	def doc(self):
		return Record(name="G1", as_dict=lambda: copy.deepcopy(self.gallery))

	def get_value(self, doctype, filters=None, field=None, *args, **kwargs):
		if doctype == "ilL-Child-Webflow-Sync-State":
			# Spec 6a: the sync row's item ID counts whatever its sync status (saves set it Pending).
			if filters.get("brand") == "staging2" and "sync_status" not in filters:
				return self.item_ids.get(filters["parent"])
			return None
		if doctype == "ilL-Webflow-Product":
			return "Rainier [SF]"
		if doctype == JOB and isinstance(filters, dict):
			return next((name for name, job in self.jobs.items() if matches(job, filters)), None)
		return None

	def count(self, doctype, filters=None):
		return sum(1 for job in self.jobs.values() if matches(job, filters or {})) if doctype == JOB else 0

	def sql(self, query, *args, **kwargs):
		if "from `tabilL-Gallery-Publish-Job`" in query:
			return [Record(name=name) for name in self.jobs]
		return []

	def save(self, doc):
		if doc.get("doctype") == JOB and not doc.get("name"):
			doc["name"] = f"J{len(self.jobs) + 1}"
			self.jobs[doc["name"]] = doc
		return doc

	def job_locked(self, name):
		return self.jobs[name], self.doc(), self.state, CONFIG

	@contextmanager
	def service(self):
		with load_service(MODULE, self.deps) as (module, frappe):
			frappe.db.get_value.side_effect = self.get_value
			frappe.db.sql.side_effect = self.sql
			frappe.db.count.side_effect = self.count
			frappe.db.exists.return_value = None
			frappe.enqueue = MagicMock()
			frappe.log_error = MagicMock()
			frappe.conf = Record(**self.conf)
			frappe.get_all.side_effect = lambda doctype, **kw: (
				["Rainier"] if doctype == "ilL-Attribute-Series" else []
			)
			frappe.get_doc.side_effect = lambda value, *a: Doc(value) if isinstance(value, dict) else None
			with (
				patch.object(module, "now_datetime", return_value=NOW),
				patch.object(module, "_save", side_effect=self.save),
				patch.object(module, "_locked", side_effect=lambda g, b: (self.doc(), self.state, CONFIG)),
				patch.object(module, "_job_locked", side_effect=self.job_locked),
			):
				yield module, frappe

	# Flow helpers ---------------------------------------------------------------------------

	def current_hash(self, module):
		return module.inspect("G1", "staging2")["current_hash"]

	def stage(self, module, item=ITEM_G):
		revision = self.current_hash(module)
		job = module.request("G1", "staging2", "STAGE", revision)["job"]
		claimed = module.claim("staging2")["jobs"][0]
		module.acknowledge(job, claimed["token"], revision, claimed["payload_hash"], item)
		return revision

	def publish(self, module):
		revision = self.stage(module)
		job = module.request("G1", "staging2", "PUBLISH", revision)["job"]
		claimed = module.claim("staging2")["jobs"][0]
		module.acknowledge(job, claimed["token"], revision, claimed["payload_hash"], ITEM_G)
		return revision

	# Tests --------------------------------------------------------------------------------

	def test_request_requires_current_hash(self):
		with self.service() as (module, _frappe):
			self.current_hash(module)
			with self.assertRaisesRegex(ValueError, "changed"):
				module.request("G1", "staging2", "STAGE", "stale-hash")
			self.assertEqual(self.jobs, {})
			self.staff.require.assert_called_with("catalog")

	def test_request_blocks_when_not_ready(self):
		cases = {
			"no images": ready_gallery(gallery_images=[]),
			"brand not targeted": ready_gallery(target_brands=[{"brand": "illumenate", "enabled": 1}]),
			"target disabled": ready_gallery(target_brands=[{"brand": "staging2", "enabled": 0}]),
			"empty targets, not default brand": ready_gallery(target_brands=[]),
		}
		for label, gallery in cases.items():
			with self.subTest(label), self.service() as (module, _frappe):
				self.gallery = gallery
				result = module.inspect("G1", "staging2")
				self.assertFalse(result["readiness"]["ready"])
				with self.assertRaisesRegex(ValueError, "readiness"):
					module.request("G1", "staging2", "STAGE", result["current_hash"])
				self.assertEqual(self.jobs, {})
		with self.service() as (module, _frappe):
			self.gallery = cases["brand not targeted"]
			issues = module.inspect("G1", "staging2")["readiness"]["issues"]
			self.assertIn("target_brands", [issue["field"] for issue in issues])
			self.assertEqual([i["record"] for i in issues if i["field"] == "target_brands"], ["staging2"])

	def test_publish_requires_staged_approved_revision(self):
		with self.service() as (module, _frappe):
			revision = self.current_hash(module)
			with self.assertRaisesRegex(ValueError, "Stage this approved revision"):
				module.request("G1", "staging2", "PUBLISH", revision)
			self.assertEqual(self.jobs, {})
			self.stage(module)
			job = module.request("G1", "staging2", "PUBLISH", revision)["job"]
			self.assertEqual(self.jobs[job].operation, "PUBLISH")

	def test_request_is_idempotent(self):
		with self.service() as (module, _frappe):
			revision = self.current_hash(module)
			first = module.request("G1", "staging2", "STAGE", revision)
			second = module.request("G1", "staging2", "STAGE", revision)
			self.assertEqual(first["job"], second["job"])
			self.assertEqual(len(self.jobs), 1)
			job = self.jobs[first["job"]]
			self.assertEqual((job.gallery, job.brand, job.publication), ("G1", "staging2", "P1"))
			self.assertEqual(job.state, "QUEUED")
			self.assertEqual(self.state.state, "QUEUED")
			self.assertEqual(self.state.approved_hash, revision)

	def test_claim_supersedes_job_when_hash_changed(self):
		def reorder_hero(test):
			test.gallery["gallery_images"].reverse()

		def change_product_id(test):
			test.item_ids["rainier-sf"] = ITEM_B

		for label, change in (("hero reordered", reorder_hero), ("product ID changed", change_product_id)):
			with self.subTest(label):
				self.setUp()
				with self.service() as (module, _frappe):
					revision = self.current_hash(module)
					job = module.request("G1", "staging2", "STAGE", revision)["job"]
					change(self)
					self.assertEqual(module.claim("staging2"), {"jobs": []})
					self.assertEqual(self.jobs[job].state, "SUPERSEDED")
					self.assertEqual(self.state.state, "NEEDS_REVIEW")
					self.assertNotEqual(self.state.current_hash, revision)

	def test_claim_sets_lease_and_attempts(self):
		with self.service() as (module, _frappe):
			revision = self.current_hash(module)
			name = module.request("G1", "staging2", "STAGE", revision)["job"]
			claimed = module.claim("staging2")["jobs"]
			self.staff.require.assert_called_with("integration")
			self.assertEqual(len(claimed), 1)
			item = claimed[0]
			self.assertEqual(
				set(item),
				{"job", "token", "operation", "revision_hash", "payload_hash", "remote_item_id", "payload"},
			)
			job = self.jobs[name]
			self.assertEqual(job.state, "RUNNING")
			self.assertEqual(job.attempts, 1)
			self.assertEqual(job.lease_expires, NOW + timedelta(minutes=5))
			self.assertEqual(item["token"], job.lease_token)
			self.assertTrue(len(item["token"]) >= 32)
			self.assertEqual(
				(item["job"], item["operation"], item["revision_hash"]), (name, "STAGE", revision)
			)
			payload = item["payload"]
			self.assertEqual(payload["hero_image"]["url"], "https://erp.example.com/files/hero.jpg")
			self.assertEqual(payload["product_item_ids"], [ITEM_A])
			self.assertEqual(payload["erp_sync_id"], "G1")
			# A running job is not claimed twice while its lease holds.
			self.assertEqual(module.claim("staging2"), {"jobs": []})

	def test_acknowledge_stage_sets_staged_hash(self):
		with self.service() as (module, _frappe):
			revision = self.stage(module)
			self.assertEqual(self.state.staged_hash, revision)
			self.assertEqual(self.state.state, "STAGED")
			self.assertEqual(self.state.remote_item_id, ITEM_G)
			self.assertIsNone(self.state.get("live_hash"))
			self.assertEqual(self.jobs["J1"].state, "COMPLETE")
			args = self.notify.success_push.call_args.args
			self.assertEqual(args[3:], (GALLERY, "G1"))
			self.notify.notify.assert_not_called()

	def test_acknowledge_publish_sets_live_hash(self):
		with self.service() as (module, _frappe):
			revision = self.publish(module)
			self.assertEqual(self.state.live_hash, revision)
			self.assertEqual(self.state.staged_hash, revision)
			self.assertEqual(self.state.state, "LIVE")
			self.assertEqual(self.state.published_on, NOW)

	def test_retire_clears_hashes(self):
		with self.service() as (module, _frappe):
			live = self.publish(module)
			with self.assertRaisesRegex(ValueError, "Deactivate"):
				module.request("G1", "staging2", "RETIRE", live)
			self.gallery["is_active"] = 0
			revision = self.current_hash(module)
			job = module.request("G1", "staging2", "RETIRE", revision)["job"]
			claimed = module.claim("staging2")["jobs"][0]
			self.assertFalse(claimed["payload"]["active"])
			module.acknowledge(job, claimed["token"], revision, claimed["payload_hash"])
			self.assertIsNone(self.state.live_hash)
			self.assertIsNone(self.state.staged_hash)
			self.assertEqual(self.state.state, "RETIRED")
			self.assertEqual(self.state.remote_item_id, ITEM_G)

	def test_stale_callback_does_not_clear_new_revision(self):
		with self.service() as (module, _frappe):
			revision = self.current_hash(module)
			job = module.request("G1", "staging2", "STAGE", revision)["job"]
			claimed = module.claim("staging2")["jobs"][0]
			self.gallery["gallery_images"].reverse()
			result = module.acknowledge(job, claimed["token"], revision, claimed["payload_hash"], ITEM_G)
			self.assertEqual(result["state"], "SUPERSEDED")
			self.assertIsNone(self.state.get("staged_hash"))
			self.assertEqual(self.state.state, "NEEDS_REVIEW")
			self.assertNotEqual(self.state.current_hash, revision)

	def test_remote_identity_conflict_refused(self):
		with self.service() as (module, _frappe):
			self.state["remote_item_id"] = ITEM_A
			revision = self.current_hash(module)
			job = module.request("G1", "staging2", "STAGE", revision)["job"]
			claimed = module.claim("staging2")["jobs"][0]
			self.assertEqual(claimed["remote_item_id"], ITEM_A)
			with self.assertRaisesRegex(ValueError, "identity conflict"):
				module.acknowledge(job, claimed["token"], revision, claimed["payload_hash"], ITEM_B)
			self.assertEqual(self.state.remote_item_id, ITEM_A)
			self.assertIsNone(self.state.get("staged_hash"))
			self.assertEqual(self.jobs[job].state, "RUNNING")

	def test_temporary_failure_schedules_retry(self):
		for code, expected in (("429", NOW + timedelta(minutes=1)), ("400", None)):
			with self.subTest(code):
				self.setUp()
				with self.service() as (module, frappe):
					revision = self.current_hash(module)
					name = module.request("G1", "staging2", "STAGE", revision)["job"]
					claimed = module.claim("staging2")["jobs"][0]
					module.acknowledge(
						name,
						claimed["token"],
						revision,
						claimed["payload_hash"],
						outcome="error",
						error_code=code,
					)
					job = self.jobs[name]
					self.assertEqual(job.state, "FAILED")
					self.assertEqual(self.state.state, "FAILED")
					self.assertEqual(job.next_attempt_on, expected)
					self.assertIn(code, job.last_error)
					if expected:
						self.notify.notify.assert_not_called()
						frappe.get_all.side_effect = lambda doctype, **kw: (
							["staging2"] if doctype == JOB else []
						)
						self.assertEqual(module.retry_brands(now=expected), ["staging2"])
						filters = frappe.get_all.call_args.kwargs["filters"]
						self.assertEqual(filters, {"state": "FAILED", "next_attempt_on": ["<=", expected]})
					else:
						self.notify.notify.assert_called_once()
						call = self.notify.notify.call_args
						self.assertEqual(call.args[2:4], (GALLERY, "G1"))
						self.assertTrue(call.kwargs.get("once"))
						self.assertIn("G1", call.args[0])

	def test_expire_leases_marks_timeout(self):
		with self.service() as (module, frappe):
			revision = self.current_hash(module)
			name = module.request("G1", "staging2", "STAGE", revision)["job"]
			module.claim("staging2")
			frappe.get_all.side_effect = lambda doctype, **kw: (
				[n for n, j in self.jobs.items() if j.state == "RUNNING"] if doctype == JOB else []
			)
			self.assertEqual(module.expire_leases(now=NOW + timedelta(minutes=4)), [])
			self.assertEqual(module.expire_leases(now=NOW + timedelta(minutes=10)), [name])
			job = self.jobs[name]
			self.assertEqual(job.state, "FAILED")
			self.assertIsNone(job.lease_token)
			self.assertIn("timeout", job.last_error)
			self.assertEqual(job.next_attempt_on, NOW + timedelta(minutes=1))
			self.staff.require.assert_called_with("integration")

	def test_invalidate_sets_needs_review(self):
		with self.service() as (module, frappe):
			frappe.db.table_exists.side_effect = lambda doctype: doctype == STATE
			module.invalidate_gallery(Doc(name="G1", flags=Record()))
			query, gallery = frappe.db.sql.call_args.args
			self.assertIn("update `tabilL-Gallery-Publication` set state='NEEDS_REVIEW'", query)
			self.assertEqual(gallery, "G1")
			frappe.db.sql.reset_mock()
			frappe.db.table_exists.side_effect = lambda doctype: False
			module.invalidate_gallery(Doc(name="G1", flags=Record()))
			frappe.db.sql.assert_not_called()

	def test_tick_expires_leases_as_publication_user(self):
		users = types.ModuleType(ROOT + ".portal.service_users")
		seen = []

		@contextmanager
		def run_as(key):
			seen.append(key)
			yield key

		users.run_as = run_as
		self.deps[users.__name__] = users
		with self.service() as (module, frappe):
			with patch.object(module, "expire_leases", side_effect=lambda: seen.append("expired")) as expire:
				module.tick()
			expire.assert_called_once_with()
			self.assertEqual(seen, ["publication", "expired"])
			frappe.db.commit.assert_called_once()

	def test_a_new_request_supersedes_a_failed_job_still_waiting_to_retry(self):
		with self.service() as (module, frappe):
			stale = self.queue(module)
			self.jobs[stale].state = "FAILED"
			self.jobs[stale].next_attempt_on = NOW + timedelta(minutes=1)
			# A failed job with no retry left stays as it is.
			self.jobs["JDONE"] = Doc(
				doctype=JOB, name="JDONE", state="FAILED", next_attempt_on=None, publication="P1"
			)

			def waiting(doctype, **kwargs):
				if doctype == "ilL-Attribute-Series":
					return ["Rainier"]
				wanted = {k: v for k, v in kwargs["filters"].items() if k != "next_attempt_on"}
				return [n for n, job in self.jobs.items() if matches(job, wanted) and job.get("next_attempt_on")]

			frappe.get_all.side_effect = waiting
			frappe.get_doc.side_effect = lambda value, name=None: Doc(value) if isinstance(value, dict) else self.jobs[name]
			fresh = self.queue(module)
			self.assertNotEqual(fresh, stale)
			self.assertEqual(self.jobs[stale].state, "SUPERSEDED")
			self.assertIsNone(self.jobs[stale].next_attempt_on)
			self.assertEqual(self.jobs[fresh].state, "QUEUED")
			self.assertEqual(self.jobs["JDONE"].state, "FAILED")

	NUDGE = ROOT + ".api.gallery_publication.send_nudge"

	def fake_requests(self):
		"""The app's CI image may not ship `requests`: a stand-in the worker imports."""
		requests = types.ModuleType("requests")
		requests.RequestException = type("RequestException", (Exception,), {})
		requests.post = MagicMock()
		self.deps["requests"] = requests
		return requests

	def nudges(self, frappe):
		return [c.kwargs["brand"] for c in frappe.enqueue.call_args_list if c.args[0] == self.NUDGE]

	def test_request_nudges_n8n_after_commit_and_again_on_a_double_click(self):
		with self.service() as (module, frappe):
			self.queue(module)
			self.queue(module)
			self.assertEqual(self.nudges(frappe), ["staging2", "staging2"])
			for call in frappe.enqueue.call_args_list:
				self.assertTrue(call.kwargs["enqueue_after_commit"])

	def test_retry_nudges_n8n(self):
		with self.service() as (module, frappe):
			job = self.queue(module)
			self.jobs[job].state = "FAILED"
			frappe.enqueue.reset_mock()
			module.retry(job)
			self.assertEqual(self.nudges(frappe), ["staging2"])

	def test_no_webhook_configured_logs_and_leaves_the_job_queued(self):
		self.conf = {}
		with self.service() as (module, frappe):
			job = self.queue(module)
			self.assertEqual(self.jobs[job].state, "QUEUED")
			self.assertEqual(self.nudges(frappe), [])
			frappe.log_error.assert_called_once()

	def test_send_nudge_posts_the_brand_with_the_shared_secret(self):
		n8n = types.ModuleType(ROOT + ".api.n8n_config")
		n8n.webhook_url = lambda key: "https://n8n.example/webhook/gallery"
		n8n.auth_headers = lambda: {"STAGING-Sync-Secret": "s"}
		self.deps[n8n.__name__] = n8n
		requests = self.fake_requests()
		with self.service() as (module, frappe):
			module.send_nudge("staging2")
			post = requests.post
			post.assert_called_once_with(
				"https://n8n.example/webhook/gallery",
				json={"brand": "staging2"},
				headers={"STAGING-Sync-Secret": "s"},
				timeout=30,
			)

	def test_a_failed_nudge_is_logged_not_raised(self):
		n8n = types.ModuleType(ROOT + ".api.n8n_config")
		n8n.webhook_url = lambda key: "https://n8n.example/webhook/gallery"
		n8n.auth_headers = lambda: {"h": "s"}
		self.deps[n8n.__name__] = n8n
		requests = self.fake_requests()
		requests.post.side_effect = requests.RequestException("down")
		with self.service() as (module, frappe):
			module.send_nudge("staging2")
			frappe.log_error.assert_called_once()

	def test_tick_nudges_each_brand_with_a_due_retry(self):
		users = types.ModuleType(ROOT + ".portal.service_users")
		users.run_as = contextmanager(lambda key: (yield key))
		self.deps[users.__name__] = users
		with self.service() as (module, frappe):
			with (
				patch.object(module, "expire_leases"),
				patch.object(module, "retry_brands", return_value=["staging2", "illumenate"]),
			):
				module.tick()
			self.assertEqual(self.nudges(frappe), ["staging2", "illumenate"])
			with (
				patch.object(module, "expire_leases"),
				patch.object(module, "retry_brands", return_value=[]),
			):
				frappe.enqueue.reset_mock()
				module.tick()
			self.assertEqual(self.nudges(frappe), [])

	def test_slug_locks_after_stage(self):
		with self.service() as (module, _frappe):
			self.assertFalse(self.slug_locked())
			self.stage(module)
		self.assertTrue(self.state.staged_hash)
		self.assertTrue(self.slug_locked())

	def queue(self, module, operation="STAGE"):
		return module.request("G1", "staging2", operation, self.current_hash(module))["job"]

	def test_same_revision_while_queued_or_running_returns_the_same_job(self):
		with self.service() as (module, _frappe):
			first = self.queue(module)
			self.assertEqual(self.queue(module), first)
			module.claim("staging2")
			self.assertEqual(self.jobs[first].state, "RUNNING")
			self.assertEqual(self.queue(module), first)
			self.assertEqual(len(self.jobs), 1)

	def test_retire_then_reactivate_then_stage_creates_a_new_job(self):
		with self.service() as (module, _frappe):
			live = self.publish(module)
			self.gallery["is_active"] = 0
			revision = self.current_hash(module)
			retire = module.request("G1", "staging2", "RETIRE", revision)["job"]
			claimed = module.claim("staging2")["jobs"][0]
			module.acknowledge(retire, claimed["token"], revision, claimed["payload_hash"])
			self.assertEqual(self.state.state, "RETIRED")
			self.gallery["is_active"] = 1
			self.assertEqual(self.current_hash(module), live)
			stage = self.queue(module)
			self.assertNotIn(stage, ("J1", "J2", retire))
			self.assertEqual(self.jobs[stage].state, "QUEUED")
			self.assertEqual(self.jobs[stage].revision_hash, live)
			self.assertEqual(self.state.state, "QUEUED")
			keys = [job.request_key for job in self.jobs.values()]
			self.assertEqual(len(keys), len(set(keys)))

	def test_repeat_request_after_complete_makes_a_new_job(self):
		"""A -> B -> back to A (toggling featured) must be stageable again."""
		with self.service() as (module, _frappe):
			first = self.stage(module)
			self.gallery["featured"] = 1
			self.stage(module)
			self.gallery["featured"] = 0
			self.assertEqual(self.current_hash(module), first)
			again = self.queue(module)
			self.assertEqual(len(self.jobs), 3)
			self.assertEqual(self.jobs[again].state, "QUEUED")
			self.assertEqual(self.jobs["J1"].state, "COMPLETE")

	def test_repeat_request_after_superseded_makes_a_new_job(self):
		with self.service() as (module, _frappe):
			first = self.queue(module)
			self.gallery["featured"] = 1
			self.assertEqual(module.claim("staging2"), {"jobs": []})
			self.assertEqual(self.jobs[first].state, "SUPERSEDED")
			self.gallery["featured"] = 0
			again = self.queue(module)
			self.assertNotEqual(again, first)
			self.assertEqual(self.jobs[again].state, "QUEUED")
			self.assertNotEqual(self.jobs[again].request_key, self.jobs[first].request_key)

	def save_without_change(self, module):
		"""invalidate_gallery runs on every save; the hashes then decide on the next inspect."""
		self.state["state"] = "NEEDS_REVIEW"
		return module.inspect("G1", "staging2")

	def test_no_op_save_after_stage_restores_staged(self):
		with self.service() as (module, _frappe):
			revision = self.stage(module)
			# Adding a second brand target changes nothing sent to this brand.
			self.gallery["target_brands"].append({"brand": "illumenate", "enabled": 1})
			result = self.save_without_change(module)
			self.assertEqual(result["current_hash"], revision)
			self.assertEqual(result["state"], "STAGED")
			job = module.request("G1", "staging2", "PUBLISH", revision)["job"]
			self.assertEqual(self.jobs[job].operation, "PUBLISH")

	def test_no_op_save_after_publish_restores_live(self):
		with self.service() as (module, _frappe):
			self.publish(module)
			self.assertEqual(self.save_without_change(module)["state"], "LIVE")

	def test_real_change_after_stage_needs_review(self):
		with self.service() as (module, _frappe):
			self.stage(module)
			self.gallery["gallery_title"] = "Hotel Lobby, renewed"
			self.assertEqual(self.save_without_change(module)["state"], "NEEDS_REVIEW")

	def test_restore_never_overwrites_queued_failed_or_retired(self):
		for kept in ("QUEUED", "FAILED", "RETIRED"):
			self.setUp()
			with self.subTest(kept), self.service() as (module, _frappe):
				revision = self.stage(module)
				self.state["state"] = kept
				self.assertEqual(module.inspect("G1", "staging2")["state"], kept)
				self.assertEqual(self.state.staged_hash, revision)

	def test_gallery_failure_wording(self):
		cases = {
			"identity-conflict": "more than one Webflow item matches this gallery; reconcile it",
			"lookup-incomplete": "the Webflow collection has too many items to search; ask an administrator",
			"400": "Webflow rejected the data",
		}
		for code, reason in cases.items():
			with self.subTest(code):
				self.setUp()
				with self.service() as (module, _frappe):
					job = self.queue(module)
					claimed = module.claim("staging2")["jobs"][0]
					module.acknowledge(
						job, claimed["token"], claimed["revision_hash"], claimed["payload_hash"],
						outcome="error", error_code=code,
					)
					self.assertEqual(self.jobs[job].last_error, f"Publication failed ({code}: {reason})")
					self.assertNotIn("product", self.state.last_error)

	def test_series_only_row_hashes_and_stays_ready(self):
		"""Spec 5.1: a series-only row (the import's Custom rows) must not break the hash or readiness."""
		self.gallery["products_used"].append({"product": None, "series": "Custom"})
		with self.service() as (module, frappe):
			frappe.get_all.side_effect = lambda doctype, **kw: (
				["Rainier", "Custom"] if doctype == "ilL-Attribute-Series" else []
			)
			result = module.inspect("G1", "staging2")
			self.assertTrue(result["readiness"]["ready"], result["readiness"]["issues"])
			dependencies = json.loads(self.state.dependencies_json)
			self.assertEqual(dependencies["products"], {"rainier-sf": ITEM_A})
			self.assertEqual(dependencies["series"], ["Custom", "Rainier"])
			job = module.request("G1", "staging2", "STAGE", result["current_hash"])["job"]
			self.assertEqual(module.claim("staging2")["jobs"][0]["job"], job)

	def test_product_staged_through_publication_record_is_ready(self):
		"""A product staged by the publication process has no Synced row, only its publication record."""
		self.item_ids = {}
		original = self.get_value

		def get_value(doctype, filters=None, field=None, *args, **kwargs):
			if doctype == "ilL-Product-Publication" and field == "remote_item_id":
				return ITEM_A
			return original(doctype, filters, field, *args, **kwargs)

		self.get_value = get_value
		with self.service() as (module, _frappe):
			result = module.inspect("G1", "staging2")
			self.assertTrue(result["readiness"]["ready"], result["readiness"]["issues"])

	def slug_locked(self):
		"""Task 2's controller, against the publication record this service writes."""
		document = types.ModuleType("frappe.model.document")
		document.Document = object
		model = types.ModuleType("frappe.model")
		model.document = document
		with load_service(CONTROLLER, {"frappe.model": model, "frappe.model.document": document}) as (
			controller,
			frappe,
		):
			# Frappe's table_exists takes the doctype name and adds the "tab" prefix itself.
			frappe.db.table_exists.side_effect = lambda doctype: doctype == STATE
			frappe.db.exists.side_effect = lambda doctype, filters: (
				doctype == STATE
				and filters == {"gallery": self.state.gallery, "staged_hash": ["is", "set"]}
				and bool(self.state.get("staged_hash"))
			)
			gallery = controller.ilLWebflowGallery()
			gallery.is_new = lambda: False
			gallery.get_doc_before_save = lambda: Record(name="G1")
			return gallery._slug_locked()


class ProductItemIdCase(unittest.TestCase):
	"""Spec 6a: a product's Webflow item ID in a brand, from the three places the product flow keeps it."""

	def setUp(self):
		self.publications = {}
		self.sync_rows = {}
		self.own = {}
		self.calls = []

	@contextmanager
	def helper(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint

		brand = types.ModuleType(ROOT + ".api.webflow_brand")
		brand.get_default_brand = lambda: "illumenate"

		def get_value(doctype, filters=None, field=None, *args, **kwargs):
			self.calls.append((doctype, filters, field))
			if doctype == "ilL-Product-Publication":
				return next(
					(item for (product, code), item in self.publications.items()
					if filters == {"scope_key": fingerprint([product, code])} and field == "remote_item_id"),
					None,
				)
			if doctype == "ilL-Child-Webflow-Sync-State":
				self.assertNotIn("sync_status", filters)
				key = (filters["parent"], filters["brand"])
				self.assertEqual(filters["parenttype"], "ilL-Webflow-Product")
				return self.sync_rows.get(key) if field == "webflow_item_id" else None
			if doctype == "ilL-Webflow-Product":
				return self.own.get(filters) if field == "webflow_item_id" else None
			return None

		with load_service(ROOT + ".api.gallery_products", {brand.__name__: brand}) as (module, frappe):
			frappe.db.get_value.side_effect = get_value
			yield module

	def test_publication_record_resolves(self):
		self.publications[("P-1", "staging2")] = ITEM_A
		with self.helper() as module:
			self.assertEqual(module.product_item_id("P-1", "staging2"), ITEM_A)

	def test_sync_row_resolves_whatever_its_status(self):
		self.sync_rows[("P-1", "staging2")] = ITEM_B
		with self.helper() as module:
			self.assertEqual(module.product_item_id("P-1", "staging2"), ITEM_B)

	def test_own_field_resolves_for_default_brand_only(self):
		self.own["P-1"] = ITEM_G
		with self.helper() as module:
			self.assertEqual(module.product_item_id("P-1", "illumenate"), ITEM_G)
			self.assertIsNone(module.product_item_id("P-1", "staging2"))

	def test_precedence(self):
		self.publications[("P-1", "illumenate")] = ITEM_A
		self.sync_rows[("P-1", "illumenate")] = ITEM_B
		self.own["P-1"] = ITEM_G
		with self.helper() as module:
			self.assertEqual(module.product_item_id("P-1", "illumenate"), ITEM_A)
			del self.publications[("P-1", "illumenate")]
			self.assertEqual(module.product_item_id("P-1", "illumenate"), ITEM_B)
			del self.sync_rows[("P-1", "illumenate")]
			self.assertEqual(module.product_item_id("P-1", "illumenate"), ITEM_G)

	def test_none_found_gives_none(self):
		with self.helper() as module:
			self.assertIsNone(module.product_item_id("P-1", "staging2"))
			self.assertIsNone(module.product_item_id("P-1", "illumenate"))
			self.assertIsNone(module.product_item_id(None, "staging2"))


if __name__ == "__main__":
	unittest.main()
