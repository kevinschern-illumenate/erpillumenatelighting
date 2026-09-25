"""Packet queue deduplication, permissions and worker failure boundaries."""

import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class PacketJobs(unittest.TestCase):
	def test_queued_request_has_worker_payload_not_framework_job_name(self):
		exports = types.SimpleNamespace(
			_check_schedule_access=lambda _: (True, None), _create_export_job=MagicMock(return_value="JOB")
		)
		with load_service(ROOT + ".portal.packet_jobs", {ROOT + ".api.exports": exports}) as (module, frappe):
			frappe.enqueue = MagicMock()
			frappe.db.get_value.side_effect = ["revision", None]
			result = module.request("S", include_cover="false")
			self.assertTrue(result["queued"])
			args = frappe.enqueue.call_args.kwargs
			self.assertEqual(args["packet_job"], "JOB")
			self.assertNotIn("job_name", args)
			self.assertTrue(args["enqueue_after_commit"])
			self.assertIn("false", frappe.db.set_value.call_args.args[2]["packet_options"])
			frappe.db.get_value.side_effect = ["revision", "JOB"]
			module.request("S", include_cover=False)
			self.assertEqual(exports._create_export_job.call_count, 1)

	def test_revoked_actor_cannot_poll_or_retry(self):
		with load_service(ROOT + ".portal.packet_jobs") as (module, frappe):
			frappe.get_doc.return_value = Record(schedule="S", status="FAILED", export_type="SPEC_SUBMITTAL")
			with patch.object(module, "_access", side_effect=PermissionError("revoked")):
				for function in (module.status, module.retry):
					with self.assertRaises(PermissionError):
						function("JOB")

	def test_worker_rejects_changed_source_and_duplicate_execution(self):
		packets = types.SimpleNamespace(generate=MagicMock())
		with load_service(ROOT + ".portal.packet_jobs", {ROOT + ".portal.packets": packets}) as (
			module,
			frappe,
		):
			job = Record(
				name="JOB",
				export_type="SPEC_SUBMITTAL",
				status="QUEUED",
				schedule="S",
				source_revision="old",
				requested_by="buyer",
			)
			frappe.get_doc.return_value = job
			frappe.set_user = MagicMock()
			frappe.db.get_value.side_effect = [1, "new", "RUNNING"]
			with patch.object(module, "_access"):
				module.run("JOB")
			packets.generate.assert_not_called()
			self.assertEqual(frappe.db.set_value.call_args.args[2]["status"], "FAILED")
			job["status"] = "RUNNING"
			module.run("JOB")
			packets.generate.assert_not_called()

	def test_late_worker_cannot_publish_after_recovery(self):
		with load_service(ROOT + ".portal.packet_jobs") as (module, frappe):
			frappe.db.get_value.return_value = "FAILED"
			with self.assertRaises(module.InterruptedPacket):
				module.checkpoint("JOB", 95, "Finalizing")
			frappe.db.set_value.assert_not_called()
			frappe.db.commit.assert_not_called()
