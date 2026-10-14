"""REL-10 small correctness fixes."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

REPO = Path(__file__).resolve().parents[2]


class ActorPerRequest(unittest.TestCase):
	def service(self):
		identity = types.SimpleNamespace(
			_is_internal_user=MagicMock(return_value=False),
			_is_dealer_user=MagicMock(return_value=True),
			_get_user_customer=MagicMock(return_value="CUST-1"),
		)
		package = types.ModuleType("ill_project_package")
		package.ill_project = identity
		deps = {ROOT + ".doctype.ill_project": package, ROOT + ".doctype.ill_project.ill_project": identity}
		return load_service(ROOT + ".portal.access", deps), identity

	def test_one_web_request_resolves_each_user_once(self):
		context, identity = self.service()
		with context as (module, frappe):
			frappe.db.get_value.return_value = 1
			frappe.local.request = types.SimpleNamespace(method="GET")
			first = module.get_actor("dealer@acme.test")
			self.assertIs(module.get_actor("dealer@acme.test"), first)
			self.assertEqual(identity._get_user_customer.call_count, 1)
			module.forget_actor("dealer@acme.test")
			self.assertIsNot(module.get_actor("dealer@acme.test"), first)

	def test_jobs_and_consoles_never_cache(self):
		context, _identity = self.service()
		with context as (module, frappe):
			frappe.db.get_value.return_value = 1
			self.assertIsNot(module.get_actor("dealer@acme.test"), module.get_actor("dealer@acme.test"))


class SupportDescriptions(unittest.TestCase):
	def test_html_description_reads_as_text(self):
		with load_service(
			ROOT + ".portal.support",
			{
				ROOT + ".portal.access": types.SimpleNamespace(get_actor=MagicMock()),
				ROOT + ".portal.conversations": types.SimpleNamespace(
					_pagination=MagicMock(), is_staff=MagicMock()
				),
			},
		) as (module, _frappe):
			text = module.description_text(
				"<p><strong>Category:</strong> Order</p><p>Line one &amp; two\nthree &lt;b&gt;</p>"
			)
			self.assertEqual(text, "Category: Order\nLine one & two\nthree <b>")


class HardCodedSalesEmail(unittest.TestCase):
	def test_templates_and_notifications_use_the_shared_constant(self):
		for path in (
			"illumenate_lighting/templates/pages/schedule.html",
			"illumenate_lighting/illumenate_lighting/portal/notifications.py",
		):
			with self.subTest(path=path):
				self.assertNotIn("sales@illumenate.lighting", (REPO / path).read_text(encoding="utf-8"))


class ProjectLineCounts(unittest.TestCase):
	def test_counts_come_from_one_grouped_query(self):
		source = (REPO / "illumenate_lighting/templates/pages/project.py").read_text(encoding="utf-8")
		self.assertIn("GROUP BY parent", source)
		self.assertNotIn('frappe.db.count(\n\t\t\t"ilL-Child-Fixture-Schedule-Line"', source)


if __name__ == "__main__":
	unittest.main()
