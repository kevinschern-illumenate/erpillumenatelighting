"""Hardening plan 0.6: Webflow sync brand selection, revision-aware progress and worker claims."""

import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

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
	modules = [
		requests,
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
	]
	if run_as:
		modules.append(_module(ROOT + ".portal.service_users", run_as=run_as))
	return {module.__name__: module for module in modules}


def _configure_n8n(frappe):
	"""Webhook URLs and the shared secret come from site config (spec sheet Phase 0, Z1)."""
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
		_configure_n8n(frappe)
		return module, frappe

	def test_spec_sheet_defaults_to_the_first_enabled_target_brand(self):
		module, frappe = self.load()
		frappe.get_doc.return_value = _product(("lighting_206", 0), ("illumenate", 1))
		requests = __import__("sys").modules["requests"]
		requests.post.return_value = MagicMock(json=lambda: {"ok": True})
		self.assertEqual(module.request_spec_sheet("demo"), {"ok": True})
		self.assertEqual(requests.post.call_args.kwargs["json"]["brand"], "illumenate")
		self.assertEqual(requests.post.call_args.kwargs["json"]["product_slug"], "demo-slug")

	def test_spec_sheet_rejects_a_brand_the_product_does_not_target(self):
		module, frappe = self.load()
		frappe.get_doc.return_value = _product(("illumenate", 1))
		with self.assertRaisesRegex(ValueError, "not an enabled target brand"):
			module.request_spec_sheet("demo", "lighting_206")

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
		_configure_n8n(frappe)
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
		publication.claim.assert_not_called()

	def test_worker_claims_as_the_integration_user_and_dispatches_each_job(self):
		module, frappe, users = self.load()
		module.claim.return_value = {"jobs": [{"job": "J1"}, {"job": "J2"}]}
		self.assertEqual(module.claim_and_dispatch("illumenate", "https://n8n.example/hook"), ["J1", "J2"])
		self.assertEqual(users, ["publication"])
		module.claim.assert_called_once_with("illumenate", limit=5)
		self.assertEqual([call.kwargs["job_data"]["job"] for call in frappe.enqueue.call_args_list], ["J1", "J2"])


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
