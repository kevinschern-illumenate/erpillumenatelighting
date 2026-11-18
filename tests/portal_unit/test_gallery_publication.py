"""Gallery publication service (docs/WEBFLOW_GALLERY_SYNC.md sections 5.2, 6, 6a), stubbed Frappe.

The pure readiness and projection modules run for real, so hashes move exactly as they would on a site.
"""

import copy
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


class GalleryPublicationCase(unittest.TestCase):
	def setUp(self):
		self.gallery = ready_gallery()
		self.item_ids = {"rainier-sf": ITEM_A}
		self.jobs = {}
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
			if filters.get("brand") == "staging2" and filters.get("sync_status") == "Synced":
				return self.item_ids.get(filters["parent"])
			return None
		if doctype == "ilL-Webflow-Product":
			return "Rainier [SF]"
		if doctype == JOB and isinstance(filters, dict) and "request_key" in filters:
			return next(
				(name for name, job in self.jobs.items() if job.request_key == filters["request_key"]), None
			)
		return None

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
			frappe.db.exists.return_value = None
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

	def test_slug_locks_after_stage(self):
		with self.service() as (module, _frappe):
			self.assertFalse(self.slug_locked())
			self.stage(module)
		self.assertTrue(self.state.staged_hash)
		self.assertTrue(self.slug_locked())

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


if __name__ == "__main__":
	unittest.main()
