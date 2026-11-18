"""Sync rebuild step 3 (plan 4.19 Q2-Q4): automatic pushes 2 minutes after the last save,
retries after 1, 5 and 15 minutes, failure notifications and the ``webflow_auto_push`` switch."""

import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api import publication_contract as contract

NOW = datetime(2026, 11, 22, 10, 40, 0)


def _module(name, **attrs):
	module = types.ModuleType(name)
	module.__dict__.update(attrs)
	return module


class Doc(Record):
	def get(self, key, default=None):
		return super().get(key, default)


def _product(status="Published", brands=(("illumenate", 1),), flags=None, item=None):
	return Doc(
		name="kit-ra01",
		webflow_status=status,
		webflow_item_id=item,
		flags=Record(flags or {}),
		target_brands=[Record(brand=code, enabled=enabled) for code, enabled in brands],
	)


class AutoPush(unittest.TestCase):
	"""``webflow_auto_push`` against a frappe double; the database is a dict of rows."""

	def load(self, *, switch=None, synced=("illumenate",), retrying=None, approval=None):
		self.users = []

		@contextmanager
		def run_as(key):
			self.users.append(key)
			yield f"{key}@example.com"

		self.export = _module(
			ROOT + ".api.webflow_export_v2",
			stage_brands=MagicMock(return_value=[{"brand": "illumenate", "job": "J9"}]),
			claim_and_dispatch=MagicMock(return_value=["J1"]),
		)
		self.notify = _module(ROOT + ".webflow_notify", auto_push_failed=MagicMock())
		self.approvals = _module(
			ROOT + ".webflow_approvals",
			FLAG="webflow_approval_write",
			pending=MagicMock(return_value=approval),
		)
		self.publication = _module(
			ROOT + ".api.publication",
			expire_leases=MagicMock(return_value=[]),
			retry_brands=MagicMock(return_value=[]),
		)
		n8n = _module(
			ROOT + ".api.n8n_config",
			sync_webhook_url=MagicMock(return_value="https://n8n.example/w2"),
			auth_headers=MagicMock(),
		)
		deps = {
			module.__name__: module
			for module in (
				self.export,
				self.notify,
				self.approvals,
				self.publication,
				n8n,
				_module(ROOT + ".portal.service_users", run_as=run_as),
				_module(ROOT + ".api.webflow_brand", get_default_brand=lambda: "illumenate"),
			)
		}
		context = load_service(ROOT + ".webflow_auto_push", deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.module, self.frappe = module, frappe
		frappe.utils.now_datetime = lambda: NOW
		frappe.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
		frappe.log_error = MagicMock()
		frappe.session = Record(user="editor@example.com")
		if switch is not None:
			frappe.conf["webflow_auto_push"] = switch
		self.rows = {}
		self.synced = set(synced)
		self.retrying = dict(retrying or {})
		self.product = Record(webflow_status="Published", webflow_item_id=None)
		self.targets = [Record(brand="illumenate", enabled=1)]
		frappe.get_all = MagicMock(side_effect=self.get_all)
		frappe.db.get_value = MagicMock(side_effect=self.get_value)
		frappe.db.set_value = MagicMock(side_effect=self.set_value)
		frappe.db.delete = MagicMock(side_effect=self.delete)
		frappe.get_doc = MagicMock(side_effect=self.new_doc)
		return module, frappe

	# --- database double ------------------------------------------------------------------

	def get_all(self, doctype, filters=None, fields=None, pluck=None, **kwargs):
		filters = filters or {}
		if doctype == "ilL-Product-Publication":
			return [Record(brand=brand) for brand in self.synced]
		if doctype == "ilL-Child-Webflow-Sync-State":
			return []
		if doctype == "ilL-Publish-Job":
			return [Record(name=job, brand=brand) for brand, job in self.retrying.items()]
		if doctype == "ilL-Child-Webflow-Brand-Target":
			return self.targets
		if doctype == "ilL-Webflow-Auto-Push":
			rows = [
				row for row in self.rows.values() if row["due_at"] <= filters.get("due_at", [None, NOW])[1]
			]
			rows.sort(key=lambda row: row["due_at"])
			return [row["name"] for row in rows] if pluck else rows
		raise AssertionError(doctype)

	def get_value(self, doctype, name, fields=None, as_dict=False, **kwargs):
		if doctype == "ilL-Webflow-Auto-Push":
			if isinstance(name, dict):
				row = next((row for row in self.rows.values() if row["scope_key"] == name["scope_key"]), None)
				return row and row["name"]
			row = self.rows.get(name)
			if not row:
				return None
			return row[fields] if isinstance(fields, str) else Record(row)
		if doctype == "ilL-Webflow-Product":
			return self.product
		raise AssertionError(doctype)

	def set_value(self, doctype, name, values, *args, **kwargs):
		self.rows[name].update(values)

	def delete(self, doctype, filters):
		for name, row in list(self.rows.items()):
			if all(row.get(key) == value for key, value in filters.items()):
				del self.rows[name]

	def new_doc(self, values):
		doc = Record(values)

		def insert(**kwargs):
			name = f"AP-{len(self.rows) + 1}"
			doc["name"] = name
			self.rows[name] = {key: value for key, value in doc.items() if key != "insert"}
			return doc

		doc["insert"] = insert
		return doc

	def row(self):
		(row,) = self.rows.values()
		return row

	# --- switch ----------------------------------------------------------------------------

	def test_the_switch_reads_text_from_the_frappe_cloud_editor(self):
		module, _frappe = self.load()
		for value in (1, True, "1", "true", "TRUE", " yes ", '"true"', "on"):
			self.assertTrue(module.parse_switch(value), value)
		for value in (None, "", 0, False, "0", "false", "no", "off", 2, "maybe"):
			self.assertFalse(module.parse_switch(value), value)

	def test_the_switch_is_off_by_default(self):
		module, _frappe = self.load()
		self.assertFalse(module.enabled())
		module.tick()
		self.publication.retry_brands.assert_called_once()  # retries still run
		self.export.stage_brands.assert_not_called()

	# --- queueing on save --------------------------------------------------------------------

	def test_a_save_queues_a_push_due_in_two_minutes(self):
		module, _frappe = self.load()
		module.on_product_update(_product())
		row = self.row()
		self.assertEqual((row["product"], row["brand"]), ("kit-ra01", "illumenate"))
		self.assertEqual(row["due_at"], NOW + timedelta(minutes=2))
		self.assertEqual(row["saved_by"], "editor@example.com")
		self.assertEqual(row["scope_key"], module.scope_key("kit-ra01", "illumenate"))

	def test_each_save_restarts_the_two_minutes_on_the_same_row(self):
		module, frappe = self.load()
		module.on_product_update(_product())
		later = NOW + timedelta(seconds=90)
		frappe.utils.now_datetime = lambda: later
		frappe.session = Record(user="second@example.com")
		module.on_product_update(_product())
		row = self.row()  # still one row
		self.assertEqual(row["due_at"], later + timedelta(minutes=2))
		self.assertEqual(row["saved_by"], "second@example.com")

	def test_never_synced_products_queue_nothing(self):
		module, _frappe = self.load(synced=())
		module.on_product_update(_product())
		self.assertEqual(self.rows, {})

	def test_the_legacy_item_id_counts_for_the_default_brand(self):
		module, _frappe = self.load(synced=())
		module.on_product_update(_product(item="a" * 24))
		self.assertEqual(self.row()["brand"], "illumenate")

	def test_only_enabled_target_brands_with_a_webflow_item_queue(self):
		module, _frappe = self.load(synced=("illumenate", "lighting_206"))
		module.on_product_update(_product(brands=(("illumenate", 1), ("lighting_206", 0), ("other", 1))))
		self.assertEqual([row["brand"] for row in self.rows.values()], ["illumenate"])

	def test_archived_products_queue_nothing_and_drop_a_waiting_push(self):
		module, _frappe = self.load()
		module.on_product_update(_product())
		module.on_product_update(_product(status="Archived"))
		self.assertEqual(self.rows, {})

	def test_a_push_or_a_callback_save_queues_nothing(self):
		module, _frappe = self.load()
		for flag in ("webflow_auto_push_skip", "_skip_webflow_sync", "webflow_approval_write"):
			module.on_product_update(_product(flags={flag: True}))
		self.assertEqual(self.rows, {})

	def test_a_save_replaces_a_failed_push_waiting_for_its_retry(self):
		# Even before the first sync succeeded: the save's push sends the latest version.
		module, _frappe = self.load(synced=(), retrying={"illumenate": "J7"})
		module.on_product_update(_product())
		self.assertEqual(self.row()["replaces_job"], "J7")

	# --- the tick ----------------------------------------------------------------------------

	def queue(self, module, due=NOW - timedelta(seconds=1), **extra):
		module.on_product_update(_product())
		self.row().update({"due_at": due, **extra})
		return self.row()["name"]

	def test_off_holds_the_push_and_on_releases_it(self):
		module, frappe = self.load()
		name = self.queue(module)
		self.assertEqual(module.process(name), "held")
		module.tick()
		self.assertIn(name, self.rows)  # held, not lost
		self.export.stage_brands.assert_not_called()
		frappe.conf["webflow_auto_push"] = "true"
		module.tick()
		self.export.stage_brands.assert_called_once_with("kit-ra01", ["illumenate"])
		self.assertEqual(self.users[-1], "webflow_auto_push")  # requested as the auto-push user
		self.assertEqual(self.rows, {})
		self.notify.auto_push_failed.assert_not_called()

	def test_a_push_that_is_not_due_waits(self):
		module, _frappe = self.load(switch="1")
		name = self.queue(module, due=NOW + timedelta(minutes=1))
		self.assertEqual(module.process(name), "wait")
		self.export.stage_brands.assert_not_called()

	def test_a_pending_approval_holds_the_push_without_noise(self):
		module, frappe = self.load(switch="1", approval=Record(name="WFA-00001"))
		name = self.queue(module)
		self.assertEqual(module.run_due(), {name: "approval"})
		self.assertIn(name, self.rows)
		self.export.stage_brands.assert_not_called()
		self.notify.auto_push_failed.assert_not_called()
		frappe.log_error.assert_not_called()

	def test_archived_or_never_synced_rows_are_dropped_at_the_tick(self):
		for change in ("archived", "unsynced", "untargeted", "deleted"):
			with self.subTest(change=change):
				module, _frappe = self.load(switch="1")
				name = self.queue(module)
				if change == "archived":
					self.product["webflow_status"] = "Archived"
				elif change == "unsynced":
					self.synced.clear()
				elif change == "untargeted":
					self.targets[0]["enabled"] = 0
				else:
					self.product = None
				self.assertEqual(module.process(name), "drop")
				self.assertEqual(self.rows, {})
				self.export.stage_brands.assert_not_called()

	def test_a_product_that_is_not_ready_notifies_at_once_and_never_raises(self):
		module, _frappe = self.load(switch="1")
		issues = [
			{"message": "Set the products collection ID", "record": "illumenate", "field": "collections"}
		]
		self.export.stage_brands.return_value = [{"brand": "illumenate", "issues": issues}]
		name = self.queue(module)
		self.assertEqual(module.run_due(), {name: "failed"})
		(call,) = self.notify.auto_push_failed.call_args_list
		self.assertEqual(call.args[:2], ("kit-ra01", "illumenate"))
		self.assertIn("Set the products collection ID", call.args[2])
		self.assertEqual(call.args[3], "editor@example.com")
		self.assertEqual(self.rows, {})

	def test_a_push_that_cannot_be_requested_notifies_at_once(self):
		module, frappe = self.load(switch="1")
		self.export.stage_brands.side_effect = ValueError("Set n8n_sync_webhook_url in site config")
		name = self.queue(module)
		self.assertEqual(module.run_due(), {name: "failed"})
		self.assertIn("n8n_sync_webhook_url", self.notify.auto_push_failed.call_args.args[2])
		frappe.db.rollback.assert_called_with(save_point="webflow_auto_push")
		self.assertEqual(self.rows, {})

	def test_at_most_ten_pushes_per_tick(self):
		module, _frappe = self.load(switch="1")
		for index in range(12):
			self.rows[f"AP-{index}"] = {
				"name": f"AP-{index}",
				"product": "kit-ra01",
				"brand": "illumenate",
				"scope_key": str(index),
				"due_at": NOW - timedelta(minutes=12 - index),
			}
		self.assertEqual(len(module.run_due()), 10)
		self.assertEqual(sorted(self.rows), ["AP-10", "AP-11"])

	def test_due_retries_are_claimed_and_sent_every_tick(self):
		module, _frappe = self.load()
		self.publication.retry_brands.return_value = ["illumenate"]
		self.assertEqual(module.run_retries(), ["J1"])
		self.publication.expire_leases.assert_called_once()
		self.assertEqual(self.users[0], "publication")
		self.export.claim_and_dispatch.assert_called_once_with("illumenate", "https://n8n.example/w2")


# --- Retries and notifications (publication) ------------------------------------------------


class Classification(unittest.TestCase):
	def test_temporary_and_permanent_failures(self):
		for code in ("429", "transport", "timeout", "connection", "500", "502", "503", "504", None):
			self.assertTrue(contract.is_temporary(code), code)
		for code in ("400", "401", "403", "404", "422", "identity-conflict", "readiness", "response-invalid"):
			self.assertFalse(contract.is_temporary(code), code)

	def test_retries_after_one_five_and_fifteen_minutes_then_stop(self):
		waits = [contract.next_retry("503", attempts, NOW) for attempts in (1, 2, 3, 4)]
		self.assertEqual(waits[:3], [NOW + timedelta(minutes=m) for m in (1, 5, 15)])
		self.assertIsNone(waits[3])
		self.assertIsNone(contract.next_retry("400", 1, NOW))

	def test_a_longer_retry_after_is_honoured_up_to_fifteen_minutes(self):
		self.assertEqual(contract.next_retry("429", 1, NOW, "120"), NOW + timedelta(minutes=2))
		self.assertEqual(contract.next_retry("429", 1, NOW, "99999"), NOW + timedelta(minutes=15))
		self.assertEqual(contract.next_retry("429", 2, NOW, "Wed, 21 Oct"), NOW + timedelta(minutes=5))


class PublicationRetries(unittest.TestCase):
	def load(self):
		import test_publication

		self.notify = _module(ROOT + ".webflow_notify", publication_failed=MagicMock())
		approvals = _module(
			ROOT + ".webflow_approvals", assert_no_pending=MagicMock(), pending=MagicMock(return_value=None)
		)
		deps = test_publication.PublicationCallbacks.dependencies(None)
		deps.update({self.notify.__name__: self.notify, approvals.__name__: approvals})
		context = load_service(ROOT + ".api.publication", deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.utils.now_datetime = lambda: NOW
		module.now_datetime = lambda: NOW
		return module, frappe

	def failed_job(self, module, attempts, code):
		import test_publication

		job, state = test_publication.PublicationCallbacks.documents(None)
		job["attempts"] = attempts
		with (
			patch.object(module, "_job_locked", return_value=(job, None, state, None)),
			patch.object(module, "_refresh"),
			patch.object(module, "_save"),
		):
			module.acknowledge("J1", "secret", "v1", "p1", "a" * 24, outcome="error", error_code=code)
		return job

	def test_temporary_failures_retry_three_times_then_notify_once(self):
		module, _frappe = self.load()
		jobs = [self.failed_job(module, attempts, "503") for attempts in (1, 2, 3, 4)]
		self.assertEqual(
			[job.next_attempt_on for job in jobs], [NOW + timedelta(minutes=m) for m in (1, 5, 15)] + [None]
		)
		self.assertIn("retry 1 of 3 at 10:41", jobs[0].last_error)
		self.assertIn("after 3 retries", jobs[3].last_error)
		self.notify.publication_failed.assert_called_once_with(jobs[3])

	def test_permanent_failures_notify_at_once_with_the_reason(self):
		module, _frappe = self.load()
		for code, reason in (("400", "Webflow rejected the data"), ("identity-conflict", "reconcile")):
			self.notify.publication_failed.reset_mock()
			job = self.failed_job(module, 1, code)
			self.assertIsNone(job.next_attempt_on)
			self.assertIn(reason, job.last_error)
			self.notify.publication_failed.assert_called_once_with(job)

	def test_a_lease_that_runs_out_is_a_timeout_that_retries(self):
		import test_publication

		module, frappe = self.load()
		job, state = test_publication.PublicationCallbacks.documents(None)
		job["lease_expires"] = NOW - timedelta(seconds=1)
		frappe.get_all = MagicMock(return_value=["J1"])
		with (
			patch.object(module, "_job_locked", return_value=(job, None, state, None)),
			patch.object(module, "_save"),
		):
			self.assertEqual(module.expire_leases(NOW), ["J1"])
		self.assertEqual(job.state, "FAILED")
		self.assertEqual(job.next_attempt_on, NOW + timedelta(minutes=1))
		self.assertIn("timeout", job.last_error)
		self.notify.publication_failed.assert_not_called()

	def claim(self, module, frappe, job, state, readiness=True):
		frappe.db.sql = MagicMock(return_value=[Record(name="J1")])
		ready = {"ready": readiness, "issues": []}
		with (
			patch.object(module, "_job_locked", return_value=(job, None, state, None)),
			patch.object(module, "_refresh", return_value=(None, ready)),
			patch.object(module, "_save"),
		):
			return module.claim("illumenate")

	def waiting_retry(self):
		job = Record(
			name="J1",
			product="kit-ra01",
			state="FAILED",
			revision_hash="v1",
			next_attempt_on=NOW - timedelta(seconds=1),
			attempts=1,
			operation="STAGE",
			payload_json="{}",
		)
		return job, Record(name="STATE", current_hash="v1", approved_hash="v1")

	def test_a_newer_save_supersedes_a_waiting_retry_without_notifying(self):
		module, frappe = self.load()
		job, state = self.waiting_retry()
		state["current_hash"] = "v2"  # the product was saved again
		self.assertEqual(self.claim(module, frappe, job, state), {"jobs": []})
		self.assertEqual(job.state, "SUPERSEDED")
		self.notify.publication_failed.assert_not_called()

	def test_a_due_retry_is_claimed_again(self):
		module, frappe = self.load()
		job, state = self.waiting_retry()
		frappe.db.exists = MagicMock(return_value=False)
		claimed = self.claim(module, frappe, job, state)
		self.assertEqual([row["job"] for row in claimed["jobs"]], ["J1"])
		self.assertEqual((job.state, job.attempts), ("RUNNING", 2))

	def test_a_retry_of_a_product_no_longer_ready_stops_and_notifies(self):
		module, frappe = self.load()
		job, state = self.waiting_retry()
		self.assertEqual(self.claim(module, frappe, job, state, readiness=False), {"jobs": []})
		self.assertIsNone(job.next_attempt_on)
		self.assertIn("readiness", job.last_error)
		self.notify.publication_failed.assert_called_once_with(job)


class DispatchFailures(unittest.TestCase):
	"""A call to n8n that fails is recorded on the job (it retries or notifies)."""

	def load(self):
		import test_webflow_sync

		deps = test_webflow_sync._dependencies()
		context = load_service(ROOT + ".api.webflow_export_v2", deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.log_error = MagicMock()
		test_webflow_sync._configure_n8n(self, module, frappe)
		self.requests = deps["requests"]
		return module, frappe

	def test_an_n8n_error_answer_is_recorded_with_its_status(self):
		module, _frappe = self.load()
		error = Exception("503")
		error.response = Record(status_code=503)
		self.requests.post.side_effect = error
		job_data = {"job": "J1", "token": "t", "revision_hash": "r", "payload_hash": "p"}
		with patch.object(module, "_record_dispatch_failure") as record:
			module.enqueue_n8n_webhook("https://n8n.example/w2", job_data)
		record.assert_called_once_with(job_data, "503")
		self.assertEqual(module._dispatch_error_code(Exception("refused")), "connection")

	def test_a_timeout_is_left_to_the_lease(self):
		module, _frappe = self.load()
		self.requests.post.side_effect = TimeoutError("read timed out")
		with patch.object(module, "_record_dispatch_failure") as record, self.assertRaises(TimeoutError):
			module.enqueue_n8n_webhook("https://n8n.example/w2", {"job": "J1"})
		record.assert_not_called()


class FailureNotification(unittest.TestCase):
	def test_an_automatic_push_failure_names_the_product_brand_and_reason(self):
		context = load_service(ROOT + ".webflow_notify")
		module, _frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		with patch.object(module, "notify", return_value=["owner@example.com"]) as notify:
			module.auto_push_failed(
				"kit-ra01", "illumenate", "Not ready: Set the products collection ID", "a@b"
			)
		subject, message, doctype, name = notify.call_args.args
		self.assertIn("kit-ra01 (illumenate)", subject)
		self.assertIn("Set the products collection ID", message)
		self.assertIn("a@b", message)
		self.assertEqual((doctype, name), ("ilL-Webflow-Product", "kit-ra01"))


if __name__ == "__main__":
	unittest.main()
