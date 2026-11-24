"""Hardening plan 0.6: Webflow sync brand selection, revision-aware progress and worker claims."""

import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


def _module(name, **attrs):
	module = types.ModuleType(name)
	module.__dict__.update(attrs)
	return module


def _dependencies(run_as=None):
	requests = _module("requests", RequestException=Exception, post=MagicMock())
	requests.exceptions = types.SimpleNamespace(Timeout=TimeoutError, HTTPError=RuntimeError)
	publication = _module(
		ROOT + ".api.publication",
		claim=MagicMock(return_value={"jobs": []}),
		inspect=MagicMock(),
		request=MagicMock(),
	)
	photometrics = _module(ROOT + ".photometrics", published=MagicMock())
	approvals = _module(ROOT + ".webflow_approvals", assert_no_pending=MagicMock(), pending=MagicMock(return_value=None))
	auto_push = _module(ROOT + ".webflow_auto_push", SKIP_FLAG="webflow_auto_push_skip", clear=MagicMock())
	modules = [
		requests,
		approvals,
		auto_push,
		_module("frappe.handler", upload_file=MagicMock()),
		publication,
		_module(ROOT + ".api.unit_conversion", format_length_inches=MagicMock()),
		_module(ROOT + ".api.webflow_attributes", ATTRIBUTE_DOCTYPES={}),
		_module(
			ROOT + ".api.webflow_brand",
			DEFAULT_ERPNEXT_BASE_URL="https://erp.example",
			get_base_url=MagicMock(),
			get_default_brand=lambda: "illumenate",
			include_configurator=MagicMock(),
			resolve_brand=MagicMock(),
		),
		_module(
			ROOT + ".doctype.ill_spec_profile.ill_spec_profile", compute_profile_dimensions=MagicMock()
		),
		photometrics,
		_module(ROOT + ".web_listing_source", Listing=MagicMock()),
		# The Sync to Webflow buttons' role check (Phase 7): a publisher here; refused in
		# test_webflow_sync_access.
		_module(ROOT + ".portal.staff", allowed=MagicMock(return_value=True), require=MagicMock()),
		_module(ROOT + ".template_link", require_template_access=MagicMock()),
	]
	if run_as:
		modules.append(_module(ROOT + ".portal.service_users", run_as=run_as))
	return {module.__name__: module for module in modules}


def _configure_n8n(test, module, frappe):
	"""Webhook URLs and the shared secret come from site config (spec sheet Phase 0, Z1).

	n8n_config may already be imported by an earlier test against another frappe stub, so it
	reads this test's frappe while the test runs.
	"""
	n8n_frappe = patch.object(module.n8n_config, "frappe", frappe)
	n8n_frappe.start()
	test.addCleanup(n8n_frappe.stop)
	frappe.conf["n8n_spec_webhook_url"] = "https://n8n.example/webhook/spec"
	frappe.conf["n8n_sync_webhook_url"] = "https://n8n.example/webhook/sync"
	frappe.conf["n8n_sync_secret"] = "secret"


class Product(Record):
	def get(self, key, default=None):
		return super().get(key, default)


def _product(*brands):
	return Product(
		name="demo",
		product_slug="demo-slug",
		flags=Record(),
		target_brands=[Record(brand=code, enabled=enabled) for code, enabled in brands],
	)


class WebflowSyncBrands(unittest.TestCase):
	def load(self, **kwargs):
		context = load_service(ROOT + ".api.webflow_export_v2", _dependencies(**kwargs))
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_cached_value = MagicMock(return_value="System User")
		frappe.enqueue = MagicMock()
		frappe._dict = Record
		frappe.conf["ERP-Sync-Secret-2026"] = "secret"
		_configure_n8n(self, module, frappe)
		return module, frappe

	def test_the_old_product_spec_endpoint_is_gone(self):
		# request_spec_sheet posted {product, product_slug, brand} to the spec webhook, which since
		# Phase 3 takes a template; it had no callers and no webflow_sync_scope check (final review).
		module, _frappe = self.load()
		self.assertFalse(hasattr(module, "request_spec_sheet"))

	def test_products_without_target_rows_use_the_default_brand(self):
		module, _frappe = self.load()
		self.assertEqual(module._sync_target_brands(_product()), ["illumenate"])
		self.assertEqual(module._sync_target_brands(_product(("a", 1), ("b", 0), ("c", 1))), ["a", "c"])


class WebflowSyncProgress(unittest.TestCase):
	def load(self, states, failed=()):
		context = load_service(ROOT + ".api.webflow_export_v2", _dependencies())
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_cached_value = MagicMock(return_value="System User")
		frappe._dict = Record
		frappe.get_doc.return_value = _product(("illumenate", 1), ("lighting_206", 1))

		def get_all(doctype, **kwargs):
			if doctype == "ilL-Child-Webflow-Sync-State":
				return [Record(row) for row in states]
			return [Record(row) for row in failed if row["brand"] == kwargs["filters"]["brand"]]

		frappe.get_all = MagicMock(side_effect=get_all)
		return module, frappe

	def test_an_earlier_synced_status_is_still_pending(self):
		module, _frappe = self.load(
			[
				{"brand": "illumenate", "sync_status": "Synced", "last_synced_at": datetime(2026, 11, 1)},
				{"brand": "lighting_206", "sync_status": "Synced", "last_synced_at": datetime(2026, 11, 3, 10, 5)},
			]
		)
		result = module.get_sync_progress("demo", since="2026-11-03 10:00:00")
		self.assertFalse(result["complete"])
		self.assertEqual([row["state"] for row in result["brands"]], ["pending", "complete"])

	def test_every_target_brand_must_finish_after_the_baseline(self):
		module, _frappe = self.load(
			[
				{"brand": "illumenate", "sync_status": "Synced", "last_synced_at": datetime(2026, 11, 3, 10, 1)},
				{"brand": "lighting_206", "sync_status": "Pending", "last_synced_at": datetime(2026, 11, 3, 10, 2)},
			]
		)
		result = module.get_sync_progress("demo", since="2026-11-03 10:00:00")
		self.assertTrue(result["complete"])
		self.assertEqual(result["brands"][1]["state"], "superseded")
		self.assertFalse(result["failed"])
		self.assertIn("server_time", result)

	def test_a_job_that_failed_after_the_baseline_fails_the_run(self):
		module, frappe = self.load(
			[], failed=[{"brand": "lighting_206", "name": "JOB-1", "last_error": "Publication failed (500)"}]
		)
		result = module.get_sync_progress("demo", since="2026-11-03 10:00:00")
		self.assertTrue(result["failed"])
		self.assertEqual(result["brands"][1]["error"], "Publication failed (500)")
		filters = frappe.get_all.call_args_list[-1].kwargs["filters"]
		self.assertEqual(filters["modified"][0], ">")

	def test_without_a_baseline_nothing_is_complete(self):
		module, frappe = self.load(
			[{"brand": "illumenate", "sync_status": "Synced", "last_synced_at": datetime(2026, 11, 3)}]
		)
		result = module.get_sync_progress("demo")
		self.assertFalse(result["complete"])
		self.assertEqual(frappe.get_all.call_count, 1)

	def test_progress_requires_read_access(self):
		module, frappe = self.load([])
		frappe.has_permission.return_value = False
		with self.assertRaises(PermissionError):
			module.get_sync_progress("demo")
		self.assertEqual(frappe.has_permission.call_args.args[1], "read")


class PublicationWorker(unittest.TestCase):
	def load(self):
		users = []

		@contextmanager
		def run_as(key):
			users.append(key)
			yield "worker@example.com"

		context = load_service(ROOT + ".api.webflow_export_v2", _dependencies(run_as=run_as))
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_cached_value = MagicMock(return_value="System User")
		frappe.enqueue = MagicMock()
		_configure_n8n(self, module, frappe)
		return module, frappe, users

	def test_requests_are_claimed_by_a_worker_not_the_requesting_user(self):
		module, frappe, _users = self.load()
		doc = _product(("illumenate", 1), ("lighting_206", 1))
		doc.save = MagicMock()
		frappe.get_doc.return_value = doc
		publication = __import__("sys").modules[ROOT + ".api.publication"]
		module.inspect.return_value = {"readiness": {"ready": True}, "current_hash": "h1"}
		module.request.side_effect = lambda product, brand, operation, digest: {"job": f"JOB-{brand}"}
		for trigger, operation in ((module.trigger_sync_v2, "STAGE"), (module.trigger_publish_v2, "PUBLISH")):
			frappe.enqueue.reset_mock()
			result = trigger("demo")
			self.assertEqual(result, {"status": "success", "jobs": ["JOB-illumenate", "JOB-lighting_206"]})
			self.assertEqual(module.request.call_args.args[2], operation)
			self.assertEqual(
				[call.kwargs["brand"] for call in frappe.enqueue.call_args_list], ["illumenate", "lighting_206"]
			)
			for call in frappe.enqueue.call_args_list:
				self.assertTrue(call.args[0].endswith(".claim_and_dispatch"))
				self.assertTrue(call.kwargs["enqueue_after_commit"])
			# The button's own save queues no automatic push (plan 4.19 Q2).
			self.assertTrue(doc.flags["webflow_auto_push_skip"])
		publication.claim.assert_not_called()
		# The sync sent the latest version: the brands' waiting automatic pushes are dropped.
		auto_push = __import__("sys").modules[ROOT + ".webflow_auto_push"]
		self.assertEqual(
			[call.args for call in auto_push.clear.call_args_list], [("demo", "illumenate"), ("demo", "lighting_206")]
		)

	def test_worker_claims_as_the_integration_user_and_dispatches_each_job(self):
		module, frappe, users = self.load()
		module.claim.return_value = {"jobs": [{"job": "J1"}, {"job": "J2"}]}
		self.assertEqual(module.claim_and_dispatch("illumenate", "https://n8n.example/hook"), ["J1", "J2"])
		self.assertEqual(users, ["publication"])
		module.claim.assert_called_once_with("illumenate", limit=5)
		self.assertEqual([call.kwargs["job_data"]["job"] for call in frappe.enqueue.call_args_list], ["J1", "J2"])


class SyncScope(unittest.TestCase):
	"""Site config ``webflow_sync_scope`` limits what reaches n8n (plan 2026-11-23 Task 1)."""

	load = PublicationWorker.load

	def setUp(self):
		self.module, self.frappe, _users = self.load()
		# n8n_config may keep this frappe stub after the test: never leave a scope behind.
		self.addCleanup(self.frappe.conf.pop, "webflow_sync_scope", None)
		self.frappe.conf["webflow_sync_scope"] = {"doctypes": ["ilL-Fixture-Template"], "brands": ["illumenate"]}
		self.module.inspect.return_value = {"readiness": {"ready": True}, "current_hash": "h1"}
		self.module.request.side_effect = lambda product, brand, operation, digest: {"job": f"JOB-{brand}"}
		self.frappe.msgprint = MagicMock()

	def product(self, **links):
		doc = _product(("illumenate", 1), ("lighting_206", 1))
		doc.update(links)
		doc.save = MagicMock()
		self.frappe.get_doc.return_value = doc
		return doc

	def test_stage_brands_refuses_out_of_scope_template(self):
		doc = self.product(tape_neon_template="TAPE-1")
		for trigger in (self.module.trigger_sync_v2, self.module.trigger_publish_v2):
			with self.subTest(trigger=trigger.__name__):
				with self.assertRaises(ValueError) as caught:
					trigger("demo")
				self.assertIn("ilL-Tape-Neon-Template is not enabled for spec generation", str(caught.exception))
		doc.save.assert_not_called()
		self.module.request.assert_not_called()
		self.frappe.enqueue.assert_not_called()

	def test_product_without_template_is_out_of_scope_when_doctypes_are_limited(self):
		self.product()
		with self.assertRaises(ValueError):
			self.module.stage_brands("demo")
		self.module.request.assert_not_called()

	def test_stage_brands_skips_out_of_scope_brand(self):
		self.product(fixture_template="FX-1")
		results = self.module.stage_brands("demo")
		self.assertEqual(results[0], {"brand": "illumenate", "job": "JOB-illumenate"})
		self.assertEqual(results[1]["brand"], "lighting_206")
		self.assertIn("Brand lighting_206 is not enabled for Webflow sync", results[1]["issues"][0]["message"])
		self.assertEqual([call.args[1] for call in self.module.request.call_args_list], ["illumenate"])

	def test_publish_skips_out_of_scope_brand(self):
		self.product(fixture_template="FX-1")
		self.assertEqual(self.module.trigger_publish_v2("demo"), {"status": "success", "jobs": ["JOB-illumenate"]})
		self.assertIn("lighting_206", self.frappe.msgprint.call_args.kwargs["msg"])

	def test_unset_scope_changes_nothing(self):
		del self.frappe.conf["webflow_sync_scope"]
		self.product(tape_neon_template="TAPE-1")
		self.assertEqual(
			self.module.trigger_sync_v2("demo"), {"status": "success", "jobs": ["JOB-illumenate", "JOB-lighting_206"]}
		)


class ServiceUsers(unittest.TestCase):
	def load(self):
		context = load_service(ROOT + ".portal.service_users")
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.set_user = MagicMock(side_effect=lambda user: frappe.session.__setitem__("user", user))
		return module, frappe

	def test_run_as_restores_the_caller_even_after_an_error(self):
		module, frappe = self.load()
		frappe.db.get_value.return_value = 1
		with self.assertRaises(RuntimeError), module.run_as("publication") as user:
			self.assertEqual(frappe.session.user, user)
			raise RuntimeError("boom")
		self.assertEqual(frappe.session.user, "buyer@example.com")

	def test_a_missing_or_disabled_user_is_refused(self):
		module, frappe = self.load()
		frappe.db.get_value.return_value = 0
		with self.assertRaises(PermissionError), module.run_as("publication"):
			pass
		frappe.set_user.assert_not_called()

	def test_site_config_can_point_at_an_existing_integration_user(self):
		module, frappe = self.load()
		frappe.conf["ill_service_users"] = {"publication": "n8n@example.com"}
		self.assertEqual(module.service_user("publication"), "n8n@example.com")

	def test_ensure_is_idempotent_and_only_adds_missing_roles(self):
		module, frappe = self.load()
		frappe.db.exists.return_value = True
		user = Record(roles=[Record(role="ilL Integration")])
		user["add_roles"] = MagicMock()
		frappe.get_doc.return_value = user
		module.ensure_service_user("publication")
		user.add_roles.assert_not_called()
		user["roles"] = [Record(role="Other")]
		module.ensure_service_user("publication")
		user.add_roles.assert_called_once_with("ilL Integration")

	def test_ensure_creates_a_system_user_without_a_welcome_email(self):
		module, frappe = self.load()
		frappe.db.exists.side_effect = lambda doctype, name: doctype == "Role"
		created = MagicMock()
		created.get.return_value = []
		frappe.get_doc.return_value = created
		module.ensure_service_user("publication")
		values = frappe.get_doc.call_args.args[0]
		self.assertEqual(values["user_type"], "System User")
		self.assertEqual(values["send_welcome_email"], 0)
		created.insert.assert_called_once_with(ignore_permissions=True)
		created.add_roles.assert_called_once_with("ilL Integration")


if __name__ == "__main__":
	unittest.main()
