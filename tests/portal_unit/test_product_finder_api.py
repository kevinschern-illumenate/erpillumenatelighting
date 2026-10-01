"""Authentication, switches, verbs, and delegation for every portal endpoint."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BASE = ROOT + ".portal.product_finder"


class API(unittest.TestCase):
	def context(self):
		self.sessions = types.SimpleNamespace(
			**{
				name: MagicMock()
				for name in (
					"require_user",
					"start",
					"get_owned",
					"decoded",
					"stamp",
					"save_answers",
					"validate_answers",
					"complete",
					"claim",
				)
			}
		)
		self.access = MagicMock()
		self.editor = MagicMock(return_value=False)
		return load_service(
			ROOT + ".api.product_finder",
			{
				BASE + ".sessions": self.sessions,
				BASE + ".definition": types.SimpleNamespace(
					load_definition=MagicMock(return_value={"questions": []}), current_version=lambda: 2
				),
				BASE + ".desk": types.SimpleNamespace(can_edit_content=self.editor),
				ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=self.access),
				BASE + ".facts": types.SimpleNamespace(
					load=lambda: [
						{"name": "P", "title": "Product", "slug": "p", "image": None, "family": "Driver"}
					]
				),
				BASE + ".matcher": types.SimpleNamespace(evaluate=MagicMock(return_value={"options": {}})),
				BASE + ".server_definition": types.SimpleNamespace(
					load=MagicMock(return_value={"questions": []})
				),
				BASE + ".verification": types.SimpleNamespace(request=MagicMock(return_value="V")),
			},
		)

	def test_every_endpoint_checks_access_and_write_verbs(self):
		cases = {
			"get_definition": {},
			"start": {},
			"get_session": {"token": "T"},
			"save_answers": {"token": "T", "answers": {}},
			"evaluate": {"answers": {}, "question_id": "q"},
			"complete": {"token": "T"},
			"claim": {"token": "T"},
			"dismiss_banner": {},
			"request_verification": {"token": "T"},
		}
		with self.context() as (api, frappe):
			frappe.db.get_single_value.return_value = 0
			for endpoint, args in cases.items():
				with self.subTest(endpoint=endpoint), self.assertRaises(PermissionError):
					getattr(api, endpoint)(**args)
				self.assertEqual(
					getattr(api, endpoint).whitelist_options["methods"],
					["GET"] if endpoint in ("get_definition", "get_session") else ["POST"],
				)
			self.assertEqual(self.sessions.require_user.call_count, len(cases))
			self.assertEqual(self.access.call_count, len(cases))

	def test_preview_requires_staff_and_applies_to_session_mutations(self):
		with self.context() as (api, frappe):
			frappe.db.get_single_value.return_value = 0
			with self.assertRaises(PermissionError):
				api.start(preview=1)
			self.editor.return_value = True
			self.sessions.start.return_value = "T"
			self.assertEqual(api.start({"q": "draft"}, preview=1), {"token": "T"})
			self.sessions.start.assert_called_with({"q": "draft"}, include_inactive=True)
			api.save_answers("T", {}, preview=1)
			self.sessions.save_answers.assert_called_with("T", {}, include_inactive=True)

	def test_endpoint_shapes_and_guest_failure(self):
		with self.context() as (api, frappe):
			frappe.db.get_single_value.return_value = 1
			frappe.defaults = types.SimpleNamespace(set_user_default=MagicMock())
			self.sessions.complete.return_value = {"matches": [{"name": "P"}]}
			self.assertEqual(api.complete("T")["top"][0]["title"], "Product")
			self.sessions.get_owned.return_value = Record(
				quiz_answers="{}", status="Active", definition_version=1
			)
			self.assertTrue(api.get_session("T")["stale"])
			self.assertEqual(api.evaluate({}, "q"), {"options": {}})
			self.assertEqual(api.request_verification("T"), {"request": "V"})
			self.assertEqual(api.dismiss_banner(), {"dismissed": True})
			self.sessions.require_user.side_effect = PermissionError("Guest")
			with self.assertRaises(PermissionError):
				api.get_definition()


class FinderManagerCatalogAccess(unittest.TestCase):
	def test_finder_only_staff_can_read_catalog_for_preview(self):
		identity = types.SimpleNamespace(
			_is_internal_user=lambda user: False,
			_is_dealer_user=lambda user: False,
			_get_user_customer=lambda user: None,
		)
		deps = {
			ROOT + ".doctype.ill_project.ill_project": identity,
			ROOT + ".portal.staff": types.SimpleNamespace(
				allowed=lambda capability, user=None: capability == "finder"
			),
		}
		with load_service(ROOT + ".portal.access", deps) as (access, frappe):
			frappe.db.get_value.return_value = True
			self.assertTrue(access.can_view_catalog("finder-manager"))
			self.assertFalse(access.can_view_catalog("Guest"))
