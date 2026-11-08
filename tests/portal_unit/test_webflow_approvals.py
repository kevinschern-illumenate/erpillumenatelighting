"""Sync rebuild step 2 (plan 4.19): approvals before a Webflow restore or archive, notifications
for approvals and failures, and ``published_on`` after a successful sync of a published page."""

import html
import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


def _module(name, **attrs):
	module = types.ModuleType(name)
	module.__dict__.update(attrs)
	return module


class Doc(Record):
	"""A document double: ``flags``, ``get_doc_before_save``, ``set`` and ``save``."""

	def __init__(self, *args, before=None, **kwargs):
		super().__init__(*args, **kwargs)
		self["flags"] = Record()
		self["_before"] = before
		self["save"] = MagicMock()

	def get(self, key, default=None):
		return super().get(key, default)

	def get_doc_before_save(self):
		return self["_before"]

	def set(self, key, value):
		self[key] = value

	def update(self, values=None, **kwargs):
		super().update(values or {}, **kwargs)


# --- Rules ----------------------------------------------------------------------------------


class ApprovalRules(unittest.TestCase):
	def load(self, extras=None):
		context = load_service(ROOT + ".webflow_approvals", extras)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module, frappe

	def test_restore_from_archived_needs_approval(self):
		# Discontinued puts the page back up too (owner, 2026-11-06).
		module, _frappe = self.load()
		for target in ("Webflow Draft", "Published", "Discontinued"):
			for published in (True, False):
				self.assertEqual(module.status_action("Archived", target, published), "Restore")
		self.assertIsNone(module.status_action("Archived", "Archived", True))

	def test_archive_needs_approval_only_when_ever_published(self):
		module, _frappe = self.load()
		for start in ("Webflow Draft", "Published", "Discontinued"):
			self.assertEqual(module.status_action(start, "Archived", True), "Archive")
			self.assertIsNone(module.status_action(start, "Archived", False))
		self.assertIsNone(module.status_action("Webflow Draft", "Published", True))
		self.assertIsNone(module.status_action("Published", "Discontinued", True))

	def test_template_archive_follows_the_same_rule(self):
		module, _frappe = self.load()
		self.assertEqual(module.template_action("Active + Live", "Archived", True), "Archive")
		self.assertIsNone(module.template_action("Active + Live", "Archived", False))
		self.assertIsNone(module.template_action("Archived", "Archived", True))
		self.assertIsNone(module.template_action("Archived", "Active + Live", True))
		self.assertIsNone(module.template_action("Active", "Discontinued", True))

	def test_ever_published_is_any_publication_date(self):
		module, _frappe = self.load()
		self.assertFalse(module.is_ever_published([]))
		self.assertFalse(module.is_ever_published([{"published_on": None}]))
		self.assertTrue(module.is_ever_published([{"published_on": None}, {"published_on": "2026-11-01"}]))

	def test_a_newer_change_updates_or_cancels_the_pending_approval(self):
		module, _frappe = self.load()
		restore = {"from_status": "Archived", "to_status": "Published", "template_doctype": None}
		# Archived -> Published (pending), then Published -> Webflow Draft: still a restore.
		self.assertEqual(
			module.plan(restore, "product", "Published", "Webflow Draft", True),
			("upsert", {"action": "Restore", "from_status": "Archived", "to_status": "Webflow Draft"}),
		)
		# Back to Archived cancels it.
		self.assertEqual(module.plan(restore, "product", "Published", "Archived", True), ("delete", None))
		archive = {"from_status": "Published", "to_status": "Archived", "template_doctype": None}
		self.assertEqual(module.plan(archive, "product", "Archived", "Published", True), ("delete", None))
		# A change that needs nothing leaves a pending approval from the other source alone.
		template = {
			"from_status": "Active + Live",
			"to_status": "Archived",
			"template_doctype": "ilL-Fixture-Template",
		}
		self.assertEqual(module.plan(template, "product", "Webflow Draft", "Published", True), ("keep", None))
		# A product change that needs approval replaces the template's.
		self.assertEqual(
			module.plan(template, "product", "Published", "Archived", True),
			("upsert", {"action": "Archive", "from_status": "Published", "to_status": "Archived"}),
		)
		self.assertEqual(module.plan(None, "product", "Published", "Archived", False), ("keep", None))

	def test_summary_names_the_public_site(self):
		module, _frappe = self.load()
		site = module.site_label(
			{"webflow_site_url": "https://staging-illumenate.webflow.io/", "brand_code": "x"}
		)
		self.assertEqual(site, "staging-illumenate.webflow.io")
		self.assertEqual(module.site_label({"brand_label": "206 Lighting"}), "206 Lighting")
		self.assertEqual(
			module.describe("Restore", "kit-ra01", "Published", [site]),
			"Restore kit-ra01 to Published on staging-illumenate.webflow.io",
		)
		self.assertEqual(
			module.describe("Archive", "kit-ra01", "Archived", [site], "FT-1"),
			"Archive kit-ra01 on staging-illumenate.webflow.io (template FT-1 set to Archived)",
		)


# --- Recording, approve and reject ---------------------------------------------------------


class ApprovalRecords(unittest.TestCase):
	def load(self, pending=None, published=True):
		self.notify = _module(ROOT + ".webflow_notify", approval_requested=MagicMock())
		self.export = _module(
			ROOT + ".api.webflow_export_v2", trigger_sync_v2=MagicMock(return_value={"jobs": ["J1"]})
		)
		brand = _module(
			ROOT + ".api.webflow_brand",
			get_default_brand=lambda: "illumenate",
			resolve_brand=lambda code, allow_inactive=False: {"webflow_site_url": "https://site.example"},
		)
		extras = {m.__name__: m for m in (self.notify, self.export, brand)}
		context = load_service(ROOT + ".webflow_approvals", extras)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.delete_doc = MagicMock()
		frappe.log_error = MagicMock()
		frappe.get_roles.return_value = ["System Manager"]
		frappe.db.get_value.return_value = pending

		def get_all(doctype, **kwargs):
			if doctype == module.PUBLICATION:
				return [Record(published_on="2026-11-01")] if published else []
			return []

		frappe.get_all = MagicMock(side_effect=get_all)
		self.inserted = []

		def get_doc(arg, name=None):
			if isinstance(arg, dict):
				doc = Doc(arg, name="WFA-00001")
				doc["insert"] = MagicMock(side_effect=lambda **kw: self.inserted.append(doc) or doc)
				return doc
			return self.docs[(arg, name)]

		frappe.get_doc = MagicMock(side_effect=get_doc)
		self.docs = {}
		return module, frappe

	def product(self, old, new, **flags):
		doc = Doc(name="kit-ra01", webflow_status=new, before=Record(webflow_status=old))
		doc["flags"].update(flags)
		return doc

	def test_never_published_product_archives_at_once(self):
		module, _frappe = self.load(published=False)
		module.on_product_update(self.product("Published", "Archived"))
		self.assertEqual(self.inserted, [])
		self.notify.approval_requested.assert_not_called()

	def test_archiving_an_ever_published_product_waits_and_notifies(self):
		module, _frappe = self.load()
		module.on_product_update(self.product("Published", "Archived"))
		(doc,) = self.inserted
		self.assertEqual(
			(doc.action, doc.state, doc.from_status, doc.to_status),
			("Archive", "Pending", "Published", "Archived"),
		)
		self.assertEqual(doc.summary, "Archive kit-ra01 on site.example")
		self.assertEqual(doc.requested_by, "buyer@example.com")
		self.notify.approval_requested.assert_called_once_with(doc)

	def test_restore_waits_even_when_never_published(self):
		module, _frappe = self.load(published=False)
		module.on_product_update(self.product("Archived", "Published"))
		self.assertEqual(self.inserted[0].action, "Restore")
		self.assertEqual(self.inserted[0].summary, "Restore kit-ra01 to Published on site.example")

	def test_a_newer_change_updates_the_pending_row(self):
		pending = Record(name="WFA-00001", product="kit-ra01", from_status="Archived", to_status="Published")
		module, _frappe = self.load(pending=pending)
		existing = Doc(pending)
		self.docs[(module.APPROVAL, "WFA-00001")] = existing
		module.on_product_update(self.product("Published", "Webflow Draft"))
		self.assertEqual(self.inserted, [])
		self.assertEqual(existing.to_status, "Webflow Draft")
		self.assertEqual(existing.from_status, "Archived")
		existing.save.assert_called_once()

	def test_changing_back_cancels_the_pending_row(self):
		pending = Record(name="WFA-00001", product="kit-ra01", from_status="Archived", to_status="Published")
		module, frappe = self.load(pending=pending)
		module.on_product_update(self.product("Published", "Archived"))
		frappe.delete_doc.assert_called_once_with(
			module.APPROVAL, "WFA-00001", ignore_permissions=True, force=True
		)
		self.notify.approval_requested.assert_not_called()

	def test_a_decision_write_back_asks_for_no_approval(self):
		module, frappe = self.load()
		module.on_product_update(self.product("Archived", "Published", webflow_approval_write=True))
		frappe.db.get_value.assert_not_called()
		self.assertEqual(self.inserted, [])

	def approval(self, module, frappe, state="Pending", **values):
		doc = Doc(
			{
				"name": "WFA-00001",
				"product": "kit-ra01",
				"action": "Restore",
				"state": state,
				"from_status": "Archived",
				"to_status": "Published",
				"template_doctype": None,
				"template_name": None,
				**values,
			}
		)
		self.docs[(module.APPROVAL, "WFA-00001")] = doc
		frappe.db.exists.return_value = True
		return doc

	def test_approve_sends_through_the_normal_sync_once(self):
		module, frappe = self.load()
		doc = self.approval(module, frappe)
		result = module.approve("WFA-00001")
		self.assertEqual((doc.state, doc.decided_by), ("Approved", "buyer@example.com"))
		self.export.trigger_sync_v2.assert_called_once_with("kit-ra01")
		self.assertEqual(result["sync"], {"jobs": ["J1"]})
		again = module.approve("WFA-00001")
		self.assertTrue(again["already"])
		self.export.trigger_sync_v2.assert_called_once()
		with self.assertRaisesRegex(ValueError, "already approved"):
			module.reject("WFA-00001")

	def test_approve_keeps_the_decision_when_the_sync_cannot_start(self):
		module, frappe = self.load()
		doc = self.approval(module, frappe)
		self.export.trigger_sync_v2.side_effect = ValueError("not ready")
		result = module.approve("WFA-00001")
		self.assertEqual(doc.state, "Approved")
		self.assertEqual(result["sync_error"], "not ready")
		frappe.db.rollback.assert_called_once_with(save_point="webflow_approval_sync")

	def test_reject_puts_the_webflow_status_back_without_a_new_approval(self):
		module, frappe = self.load()
		doc = self.approval(module, frappe)
		product = Doc(name="kit-ra01", webflow_status="Published")
		self.docs[(module.PRODUCT, "kit-ra01")] = product
		result = module.reject("WFA-00001")
		self.assertEqual(product.webflow_status, "Archived")
		self.assertTrue(product.flags.webflow_approval_write)
		product.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual((doc.state, result["restored"]), ("Rejected", True))
		self.export.trigger_sync_v2.assert_not_called()
		self.assertTrue(module.reject("WFA-00001")["already"])
		product.save.assert_called_once()

	def test_reject_puts_a_template_status_back(self):
		module, frappe = self.load()
		self.approval(
			module,
			frappe,
			action="Archive",
			template_doctype="ilL-Fixture-Template",
			template_name="FT-1",
		)
		doc = self.docs[(module.APPROVAL, "WFA-00001")]
		doc.update(from_status="Active + Live", to_status="Archived")
		template = Doc(name="FT-1", product_status="Archived")
		self.docs[("ilL-Fixture-Template", "FT-1")] = template
		module.reject("WFA-00001")
		self.assertEqual(template.product_status, "Active + Live")
		self.assertTrue(template.flags.webflow_approval_write)

	def test_reject_leaves_a_status_changed_since(self):
		module, frappe = self.load()
		self.approval(module, frappe)
		product = Doc(name="kit-ra01", webflow_status="Webflow Draft")
		self.docs[(module.PRODUCT, "kit-ra01")] = product
		self.assertFalse(module.reject("WFA-00001")["restored"])
		product.save.assert_not_called()

	def test_only_system_managers_or_product_editors_decide(self):
		module, frappe = self.load()
		self.approval(module, frappe)
		frappe.get_roles.return_value = ["ilL Catalog Viewer"]
		frappe.has_permission.return_value = False
		with self.assertRaises(PermissionError):
			module.approve("WFA-00001")
		frappe.has_permission.return_value = True
		self.assertEqual(module.approve("WFA-00001")["state"], "Approved")

	def test_pushes_are_refused_while_pending(self):
		pending = Record(
			name="WFA-00001", product="kit-ra01", summary="Restore kit-ra01 to Published on site.example"
		)
		module, frappe = self.load(pending=pending)
		with self.assertRaisesRegex(ValueError, "WFA-00001 is waiting for kit-ra01 \\(Restore kit-ra01"):
			module.assert_no_pending("kit-ra01")
		frappe.db.get_value.return_value = None
		module.assert_no_pending("kit-ra01")


# --- The sync endpoints ---------------------------------------------------------------------


class SyncEndpoints(unittest.TestCase):
	def load(self):
		import test_webflow_sync

		deps = test_webflow_sync._dependencies()
		self.approvals = deps[ROOT + ".webflow_approvals"]
		context = load_service(ROOT + ".api.webflow_export_v2", deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.get_cached_value = MagicMock(return_value="System User")
		frappe.enqueue = MagicMock()
		test_webflow_sync._configure_n8n(self, module, frappe)
		return module, frappe

	def test_sync_and_publish_refuse_while_an_approval_is_pending(self):
		module, frappe = self.load()
		self.approvals.assert_no_pending.side_effect = ValueError("approval WFA-00001 is waiting")
		for trigger in (module.trigger_sync_v2, module.trigger_publish_v2):
			with self.assertRaisesRegex(ValueError, "WFA-00001"):
				trigger("kit-ra01")
		frappe.get_doc.assert_not_called()
		module.request.assert_not_called()
		frappe.enqueue.assert_not_called()

	def published_on(self, status, published_on=None):
		module, frappe = self.load()

		def get_value(doctype, filters, fields=None, **kwargs):
			if doctype == "ilL-Webflow-Product":
				return status
			return Record(name="PUB-1", published_on=published_on)

		frappe.db.get_value = MagicMock(side_effect=get_value)
		frappe.db.set_value = MagicMock()
		frappe.utils.now_datetime = lambda: "2026-11-22 10:00:00"
		return module, frappe

	def test_a_published_page_gets_its_first_published_on(self):
		for status in ("Published", "Discontinued"):
			module, frappe = self.published_on(status)
			self.assertTrue(module._mark_ever_published("kit-ra01", "illumenate"))
			frappe.db.set_value.assert_called_once_with(
				"ilL-Product-Publication",
				"PUB-1",
				"published_on",
				"2026-11-22 10:00:00",
				update_modified=False,
			)

	def test_drafts_and_already_published_pages_are_left_alone(self):
		for status, published_on in (
			("Webflow Draft", None),
			("Archived", None),
			("Published", "2026-11-01"),
		):
			module, frappe = self.published_on(status, published_on)
			self.assertFalse(module._mark_ever_published("kit-ra01", "illumenate"))
			frappe.db.set_value.assert_not_called()

	def test_only_a_completed_callback_marks_the_page_published(self):
		module, frappe = self.load()
		publication = __import__("sys").modules[ROOT + ".api.publication"]
		publication.acknowledge = MagicMock()
		frappe.db.get_value = MagicMock(return_value=Record(product="kit-ra01", brand="illumenate"))
		staff = _module(ROOT + ".portal.staff", require=MagicMock())
		with (
			patch.dict("sys.modules", {staff.__name__: staff}),
			patch.object(module, "_mark_ever_published") as mark,
			patch.object(module, "_update_product_sync_target"),
		):
			for state, calls in (("SUPERSEDED", 0), ("COMPLETE", 1)):
				mark.reset_mock()
				publication.acknowledge.return_value = {"state": state}
				module.mark_webflow_synced(
					"kit-ra01",
					"a" * 24,
					brand="illumenate",
					job="J1",
					token="t",
					revision_hash="r",
					payload_hash="p",
				)
				self.assertEqual(mark.call_count, calls)


# --- Notifications --------------------------------------------------------------------------


class Notifications(unittest.TestCase):
	def load(self, users=None, known=()):
		context = load_service(ROOT + ".webflow_notify")
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		if users is not None:
			frappe.conf["webflow_notify_users"] = users
		frappe.logger = MagicMock()
		frappe.log_error = MagicMock()
		frappe.publish_realtime = MagicMock()
		frappe.scrub = lambda value: value.lower().replace(" ", "_").replace("-", "_")
		frappe.utils.escape_html = html.escape
		frappe.get_all = MagicMock(return_value=[Record(name=user, email=user) for user in known])
		frappe.db.exists.return_value = False
		self.logs = []

		def get_doc(values):
			doc = Record(values)
			doc["insert"] = MagicMock(side_effect=lambda **kw: self.logs.append(doc))
			return doc

		frappe.get_doc = MagicMock(side_effect=get_doc)
		return module, frappe

	def test_recipients_accept_a_list_a_json_string_or_commas(self):
		module, _frappe = self.load()
		expected = ["owner@example.com", "kevin@example.com"]
		for value in (
			expected,
			json.dumps(expected),
			"owner@example.com, kevin@example.com",
			" owner@example.com;kevin@example.com ,OWNER@example.com",
			'"owner@example.com, kevin@example.com"',
		):
			with self.subTest(value=value):
				self.assertEqual(module.parse_users(value), expected)
		for value in (None, "", "  ", [], "[]", {"a": 1}):
			self.assertEqual(module.parse_users(value), [])

	def test_unset_notifies_nobody_and_warns_once(self):
		module, frappe = self.load()
		self.assertEqual(module.notify("s", "m", document_name="kit-ra01"), [])
		self.assertEqual(module.notify("s", "m", document_name="kit-ra01"), [])
		self.assertEqual(frappe.logger.return_value.warning.call_count, 1)
		self.assertEqual(self.logs, [])

	def test_each_enabled_recipient_gets_a_bell_email_and_browser_notification(self):
		module, frappe = self.load("owner@example.com, gone@example.com", known=["owner@example.com"])
		approval = Record(
			product="kit-ra01",
			action="Restore",
			summary="Restore kit-ra01 to Published on x",
			requested_by="a@b",
		)
		self.assertEqual(module.approval_requested(approval), ["owner@example.com"])
		(log,) = self.logs
		self.assertEqual(log["doctype"], "Notification Log")
		self.assertEqual(log["type"], "Mention")  # an Alert log is never emailed
		self.assertEqual((log["document_type"], log["document_name"]), ("ilL-Webflow-Product", "kit-ra01"))
		self.assertIn("Restore kit-ra01 to Published on x", log["email_content"])
		event, payload = frappe.publish_realtime.call_args.args
		self.assertEqual(event, "ill_webflow_alert")
		self.assertEqual(payload["route"], "/app/ill_webflow_product/kit-ra01".replace("_", "-"))
		self.assertEqual(frappe.publish_realtime.call_args.kwargs["user"], "owner@example.com")

	def test_a_failed_job_notifies_once_with_the_reason(self):
		module, frappe = self.load(["owner@example.com"], known=["owner@example.com"])
		job = Record(
			name="J1",
			product="kit-ra01",
			brand="illumenate",
			operation="STAGE",
			attempts=2,
			last_error="Publication failed (500)",
		)
		module.publication_failed(job)
		(log,) = self.logs
		self.assertIn("job J1", log["subject"])
		self.assertIn("Publication failed (500)", log["email_content"])
		frappe.db.exists.return_value = True
		module.publication_failed(job)
		self.assertEqual(len(self.logs), 1)

	def test_a_success_is_a_push_to_who_started_it_only(self):
		module, frappe = self.load(["owner@example.com"], known=["owner@example.com"])
		job = Record(
			product="kit-ra02",
			brand="illumenate",
			operation="STAGE",
			requested_by="webflow_auto_push",
			started_by="saver@example.com",
		)
		self.assertTrue(module.publication_succeeded(job))
		self.assertEqual(self.logs, [])  # no bell, no email
		event, payload = frappe.publish_realtime.call_args.args
		self.assertEqual(event, "ill_webflow_alert")
		self.assertEqual(payload["indicator"], "green")
		self.assertIn("Synced to Webflow: kit-ra02", payload["title"])
		self.assertEqual(frappe.publish_realtime.call_args.kwargs["user"], "saver@example.com")
		# Older jobs have no started_by: the requester gets it.
		job["started_by"] = None
		job["requested_by"] = "owner@example.com"
		job["operation"] = "PUBLISH"
		module.publication_succeeded(job)
		self.assertEqual(frappe.publish_realtime.call_args.kwargs["user"], "owner@example.com")
		self.assertIn("Published on Webflow", frappe.publish_realtime.call_args.args[1]["title"])

	def test_no_success_push_without_a_person(self):
		module, frappe = self.load()
		for user in (None, "", "Guest", "Administrator", "webflow_auto_push"):
			self.assertFalse(module.success_push(user, "t", "b"))
		frappe.publish_realtime.assert_not_called()

	def test_a_spec_sheet_push_names_the_template(self):
		module, frappe = self.load()
		module.spec_sheet_generated("owner@example.com", "ilL-Extrusion-Kit-Template", "KIT-RA02")
		payload = frappe.publish_realtime.call_args.args[1]
		self.assertEqual(payload["title"], "Spec sheet generated: KIT-RA02")
		self.assertEqual(payload["route"], "/app/ill-extrusion-kit-template/KIT-RA02")

	def test_a_notification_problem_never_raises(self):
		module, frappe = self.load(["owner@example.com"], known=["owner@example.com"])
		frappe.get_doc = MagicMock(side_effect=RuntimeError("smtp"))
		self.assertEqual(module.notify("s", "m", document_name="kit-ra01"), [])
		frappe.log_error.assert_called_once()


class PublicationFailures(unittest.TestCase):
	def load(self):
		import test_publication

		notify = _module(
			ROOT + ".webflow_notify", publication_failed=MagicMock(), publication_succeeded=MagicMock()
		)
		approvals = _module(ROOT + ".webflow_approvals", assert_no_pending=MagicMock(), pending=MagicMock())
		deps = test_publication.PublicationCallbacks.dependencies(None)
		deps.update({notify.__name__: notify, approvals.__name__: approvals})
		context = load_service(ROOT + ".api.publication", deps)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		self.notify, self.approvals = notify, approvals
		return module, frappe

	def acknowledge(self, module, outcome, error_code=None):
		import test_publication

		job, state = test_publication.PublicationCallbacks.documents(None)
		with (
			patch.object(module, "_job_locked", return_value=(job, None, state, None)),
			patch.object(module, "_refresh"),
			patch.object(module, "_save"),
		):
			module.acknowledge("J1", "secret", "v1", "p1", "a" * 24, outcome=outcome, error_code=error_code)
		return job

	def test_a_failed_job_notifies_and_a_successful_one_only_pushes(self):
		module, _frappe = self.load()
		done = self.acknowledge(module, "success")
		self.notify.publication_failed.assert_not_called()
		self.notify.publication_succeeded.assert_called_once_with(done)
		job = self.acknowledge(module, "error", "400")
		self.assertEqual(job.state, "FAILED")
		self.notify.publication_failed.assert_called_once_with(job)
		self.notify.publication_succeeded.assert_called_once()

	def test_a_publication_request_is_refused_while_pending(self):
		module, _frappe = self.load()
		self.approvals.assert_no_pending.side_effect = ValueError("approval WFA-00001 is waiting")
		with patch.object(module, "_locked") as locked, self.assertRaisesRegex(ValueError, "WFA-00001"):
			module.request("kit-ra01", "illumenate", "STAGE", "h1")
		locked.assert_not_called()


if __name__ == "__main__":
	unittest.main()
