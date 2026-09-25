import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class Outbox(unittest.TestCase):
	def test_former_purchasing_contact_with_order_access_is_no_longer_a_recipient(self):
		orders = types.SimpleNamespace(load_accessible_sales_order=MagicMock(return_value=True))
		notifications = types.SimpleNamespace(
			order_recipients=MagicMock(return_value={"new-contact@example.com"})
		)
		with load_service(
			ROOT + ".portal.outbox",
			{ROOT + ".portal.orders": orders, ROOT + ".portal.notifications": notifications},
		) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(name="SO1")
			event = Record(reference_type="Sales Order", reference_name="SO1")
			self.assertFalse(module.reference_access(event, "former-contact@example.com"))
			self.assertTrue(module.reference_access(event, "new-contact@example.com"))

	def delivery(self):
		return Record(
			name="DEL1",
			recipient="buyer@example.com",
			event="EVENT1",
			state="PENDING",
			attempts=0,
			email_queue=None,
		)

	def test_email_setup_failure_persists_and_rolls_back_only_queue(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			frappe.get_doc.side_effect = [self.delivery(), Record(subject="Update", message="Open portal")]
			frappe.sendmail = MagicMock(side_effect=RuntimeError("No outgoing account"))
			frappe.log_error, frappe.get_traceback = MagicMock(), MagicMock()
			with patch.object(module, "eligibility", return_value=("PENDING", "Ready")):
				module.dispatch_one("DEL1")
			frappe.db.rollback.assert_called_once_with(save_point="portal_email_queue")
			self.assertEqual(frappe.db.set_value.call_args.args[2]["state"], "FAILED")

	def test_queue_creation_is_delayed_and_tracks_native_id(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			frappe.get_doc.side_effect = [self.delivery(), Record(subject="Update", message="Open portal")]
			frappe.sendmail = MagicMock(return_value=Record(name="EMAIL1"))
			with patch.object(module, "eligibility", return_value=("PENDING", "Ready")):
				module.dispatch_one("DEL1")
			self.assertFalse(frappe.sendmail.call_args.kwargs["now"])
			self.assertTrue(frappe.sendmail.call_args.kwargs["delayed"])
			self.assertEqual(frappe.db.set_value.call_args.args[2]["email_queue"], "EMAIL1")

	def test_duplicate_dispatch_reconciles_without_second_email(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			delivery = self.delivery()
			delivery["email_queue"] = "EMAIL1"
			frappe.get_doc.return_value = delivery
			frappe.sendmail = MagicMock()
			with patch.object(module, "reconcile") as reconcile:
				module.dispatch_one("DEL1")
				reconcile.assert_called_once_with(delivery)
			frappe.sendmail.assert_not_called()

	def test_opt_out_and_lost_access_checked_again_at_send(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			frappe.get_doc.side_effect = [self.delivery(), Record(), self.delivery(), Record()]
			queue = Record(reference_doctype=module.DELIVERY, reference_name="DEL1", db_set=MagicMock())
			for state in ("SUPPRESSED", "SKIPPED"):
				with patch.object(
					module, "eligibility", return_value=(state, "Access or preference changed")
				):
					self.assertFalse(module.before_send(queue))
				self.assertEqual(frappe.db.set_value.call_args.args[2]["state"], state)

	def test_native_sent_recipient_required_for_delivery_claim(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			delivery = self.delivery()
			delivery["email_queue"] = "EMAIL1"
			queue = Record(
				status="Not Sent", recipients=[Record(recipient="buyer@example.com", status="Not Sent")]
			)
			frappe.get_doc.return_value = queue
			module.reconcile(delivery)
			self.assertEqual(frappe.db.set_value.call_args.args[2]["state"], "QUEUED")
			queue.recipients[0]["status"] = "Sent"
			module.reconcile(delivery)
			self.assertEqual(frappe.db.set_value.call_args.args[2]["state"], "DELIVERED")

	def test_preference_off_has_explicit_suppressed_state(self):
		notifications = types.ModuleType(ROOT + ".portal.notifications")
		notifications.PREFERENCE_DEFAULTS = {"notify_orders": True}
		notifications.wants_notification = MagicMock(return_value=False)
		with load_service(ROOT + ".portal.outbox", {notifications.__name__: notifications}) as (
			module,
			_frappe,
		):
			state, _reason = module.eligibility(Record(preference="notify_orders"), "buyer@example.com")
			self.assertEqual(state, "SUPPRESSED")

	def test_unrelated_email_preserves_native_behavior(self):
		with load_service(ROOT + ".portal.outbox") as (module, frappe):
			self.assertTrue(module.before_send(Record(reference_doctype="Quotation")))
			frappe.get_doc.assert_not_called()
