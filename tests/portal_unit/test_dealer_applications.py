"""FLOW-5: visitors and signed-in users without a company apply for dealer access."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".portal.dealer_applications"
VALID = {"company": " Studio Lux ", "full_name": "Dana Doe", "email": "Dana@Studio.test", "territory": "PNW"}


class DealerApplications(unittest.TestCase):
	def service(self, user="Guest", dealer=False, customer=None):
		self.rate_limits = []

		def rate_limit(**options):
			self.rate_limits.append(options)
			return lambda function: function

		self.staff = types.SimpleNamespace(
			assign=MagicMock(),
			body=MagicMock(side_effect=lambda doc, summary, note: f"{summary}|{note}"),
			notify_staff=MagicMock(return_value=["sam@illumenate.test"]),
			_guarded=lambda work, title: work(),
		)
		self.access = types.SimpleNamespace(
			can_view_catalog=MagicMock(return_value=dealer),
			get_actor=MagicMock(return_value=Record(customer=customer)),
		)
		context = load_service(
			MODULE,
			{
				"frappe.rate_limiter": types.SimpleNamespace(rate_limit=rate_limit),
				ROOT + ".portal.staff_notifications": self.staff,
				ROOT + ".portal.access": self.access,
			},
		)
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		frappe.session.user = user
		frappe.utils.validate_email_address = lambda value: "@" in value and " " not in value
		self.inserted = []
		frappe.get_all.return_value = []
		frappe.db.get_value.return_value = None

		def get_doc(values):
			doc = Record(values, name="AR-1", flags=Record())
			doc.insert = lambda **options: self.inserted.append((doc, options))
			return doc

		frappe.get_doc.side_effect = get_doc
		return module, frappe

	def test_guest_endpoint_is_post_only_and_rate_limited(self):
		module, _frappe = self.service()
		self.assertEqual(module.apply.whitelist_options, {"allow_guest": True, "methods": ["POST"]})
		self.assertEqual(self.rate_limits, [{"limit": 5, "seconds": 3600}])

	def test_filled_honeypot_succeeds_silently_without_creating_anything(self):
		module, frappe = self.service()
		result = module.apply(**VALID, fax_number="555-0100")
		self.assertEqual(result, {"success": True, "state": "Pending"})
		frappe.get_doc.assert_not_called()
		self.staff.notify_staff.assert_not_called()
		# A real guest application gets exactly the same reply.
		self.assertEqual(module.apply(**VALID), result)

	def test_fields_are_validated_and_trimmed(self):
		module, _frappe = self.service()
		data, errors = module.clean({"email": "nope", "message": "x" * 4001})
		self.assertEqual(set(errors), {"company", "full_name", "email", "message"})
		self.assertIn("valid email", errors["email"])
		result = module.apply(company="Studio", full_name="  ", email="dana@studio.test")
		self.assertFalse(result["success"])
		self.assertEqual(set(result["errors"]), {"full_name"})
		self.assertEqual(self.inserted, [])
		data, errors = module.clean(VALID)
		self.assertEqual(errors, {})
		self.assertEqual(
			data,
			{
				"company": "Studio Lux",
				"full_name": "Dana Doe",
				"email": "dana@studio.test",
				"territory": "PNW",
			},
		)

	def test_guest_application_is_anonymous_and_rings_the_accounts_team(self):
		module, _frappe = self.service()
		module.apply(**VALID, website="https://studio.test", message="We spec hospitality")
		((doc, options),) = self.inserted
		self.assertEqual(options, {"ignore_permissions": True})
		self.assertEqual(doc["doctype"], "ilL-Account-Request")
		self.assertEqual(doc["request_type"], "Dealer application")
		self.assertEqual(doc["state"], "Pending")
		self.assertIsNone(doc["requested_by"], "never the shared Guest account")
		self.assertTrue(doc.flags.account_service)
		self.assertEqual(json.loads(doc["proposed_json"])["company"], "Studio Lux")
		self.staff.assign.assert_called_once_with(doc, "accounts")
		capability, notified, subject, message = self.staff.notify_staff.call_args.args
		self.assertEqual((capability, notified), ("accounts", doc))
		self.assertEqual(subject, "New dealer application AR-1 from Dana Doe at Studio Lux")
		self.assertIn("Website: https://studio.test", message)
		self.assertIn("company invitation", message)

	def test_resubmitting_the_same_details_returns_the_first_application(self):
		module, frappe = self.service()
		frappe.db.get_value.return_value = Record(name="AR-0", state="Pending")
		self.assertEqual(module.apply(**VALID), {"success": True, "state": "Pending"})
		self.assertEqual(self.inserted, [])
		self.staff.notify_staff.assert_not_called()

	def test_signed_in_application_is_owned_by_the_user(self):
		module, _frappe = self.service(user="dana@studio.test")
		result = module.apply(**VALID)
		((doc, _options),) = self.inserted
		self.assertEqual(doc["requested_by"], "dana@studio.test")
		self.assertEqual(result, {"success": True, "request": "AR-1", "state": "Pending"})
		self.assertNotIn("company invitation", self.staff.notify_staff.call_args.args[3])

	def test_signed_in_user_with_an_open_application_gets_it_back(self):
		module, frappe = self.service(user="dana@studio.test")
		frappe.get_all.return_value = [Record(name="AR-0", state="Information needed")]
		self.assertEqual(
			module.apply(**VALID), {"success": True, "request": "AR-0", "state": "Information needed"}
		)
		self.assertEqual(self.inserted, [])
		self.assertEqual(frappe.get_all.call_args.kwargs["filters"]["requested_by"], "dana@studio.test")

	def test_dealers_do_not_apply_again(self):
		module, _frappe = self.service(user="dealer@acme.test", dealer=True)
		self.assertFalse(module.apply(**VALID)["success"])
		self.assertEqual(self.inserted, [])

	def test_page_state(self):
		module, _frappe = self.service()
		self.assertEqual(module.page_state()["state"], "apply")
		self.assertTrue(module.page_state()["is_guest"])
		module, _frappe = self.service(user="dealer@acme.test", dealer=True)
		self.assertEqual(module.page_state()["state"], "approved")
		module, frappe = self.service(user="dana@studio.test")
		frappe.get_all.return_value = [Record(name="AR-0", state="Pending")]
		self.assertEqual(module.page_state()["state"], "pending")
		module, frappe = self.service(user="dana@studio.test", customer="CUST-1")
		frappe.db.get_value.side_effect = lambda doctype, name, fields, **kw: (
			Record(full_name="Dana Doe", email="dana@studio.test", mobile_no=None, phone="555")
			if doctype == "User"
			else "Studio Lux"
		)
		state = module.page_state()
		self.assertEqual(state["state"], "apply")
		self.assertEqual(
			state["prefill"],
			{"full_name": "Dana Doe", "email": "dana@studio.test", "phone": "555", "company": "Studio Lux"},
		)


if __name__ == "__main__":
	unittest.main()
