"""Is Discontinued follows the status table (plan 4.3 rows 10 to 17, 4.8, D48)."""

import unittest

from test_services import ROOT, load_service


class Discontinued(unittest.TestCase):
	def test_the_status_table(self):
		with load_service(ROOT + ".webflow_state") as (module, _frappe):
			cases = [
				# (webflow status, template status, published before, expected)
				("Discontinued", "Active + Live", True, True),  # row 10
				("Discontinued", "Active", False, True),
				("Published", "Active + Live", True, False),  # row 9
				("Webflow Draft", "Internal Only", True, True),  # row 12
				("Webflow Draft", "Internal Only", False, False),  # row 13
				("Published", "Discontinued", True, True),  # row 14
				("Published", "Discontinued", False, False),  # row 15
				("Archived", "Active + Live", True, True),  # row 11, owner 2026-11-02
				("Archived", "Active + Live", False, False),
				("Discontinued", "Archived", True, False),  # row 16
				("Webflow Draft", None, False, False),
			]
			for status, template, published, expected in cases:
				with self.subTest(status=status, template=template, published=published):
					self.assertEqual(module.discontinued(status, template, published), expected)


class EffectiveStatus(unittest.TestCase):
	"""What a push uses (owner, 2026-11-08: plan 4.3 table, product field left alone)."""

	def test_the_template_overrides_the_product_only_when_it_must(self):
		with load_service(ROOT + ".webflow_state") as (module, _frappe):
			cases = [
				# (template status, webflow status, published, expected status, rule)
				(None, "Published", False, "Published", None),  # unlinked
				("Active + Live", "Published", True, "Published", None),
				("Active + Live", "Webflow Draft", False, "Webflow Draft", None),
				("Active + Live", "Archived", True, "Archived", None),
				("Internal Only", "Published", True, "Discontinued", "stays_up"),  # row 12
				("Discontinued", "Discontinued", True, "Discontinued", "stays_up"),  # row 14
				("Discontinued", "Webflow Draft", True, "Webflow Draft", None),  # hidden stays hidden
				("Draft", "Published", True, "Webflow Draft", "hidden"),  # row 3
				("Active", "Published", True, "Webflow Draft", "hidden"),  # D61
				("Draft", "Published", False, None, "never_published"),  # row 2
				("Active", "Webflow Draft", False, None, "never_published"),  # D60
				("Internal Only", "Published", False, None, "never_published"),  # row 13
				("Archived", "Published", True, None, "archived_template"),  # to be decided
				("Discontinued", "Archived", True, "Archived", None),
			]
			for template, status, published, expected, rule in cases:
				with self.subTest(template=template, status=status, published=published):
					self.assertEqual(module.effective_status(template, status, published), (expected, rule))

	def test_the_product_line_explains_an_override(self):
		with load_service(ROOT + ".webflow_state") as (module, frappe):
			frappe._ = lambda text: text
			module._ = frappe._
			self.assertIsNone(module.describe_effective("Active + Live", "Published", "Published", None))
			self.assertEqual(
				module.describe_effective("Internal Only", "Published", "Discontinued", "stays_up"),
				"Shown on Webflow as Discontinued, because the template is Internal Only (Webflow Status here: Published).",
			)
			self.assertIn(
				"never published", module.describe_effective("Draft", "Published", None, "never_published")
			)


class TemplateStatusChange(unittest.TestCase):
	def load(self, old, new, stage="Published", published=True):
		import sys
		import types
		from unittest.mock import MagicMock

		from test_services import Record

		notify = types.ModuleType(ROOT + ".webflow_notify")
		notify.notify = MagicMock()
		context = load_service(ROOT + ".webflow_state", {notify.__name__: notify})
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		package = sys.modules.get(ROOT)
		if package is not None:
			before = getattr(package, "webflow_notify", None)
			package.webflow_notify = notify
			self.addCleanup(setattr, package, "webflow_notify", before)
		frappe._ = lambda text: text
		module._ = frappe._
		module.linked_product = MagicMock(return_value="kit-ra02")
		module.ever_published = MagicMock(return_value=published)
		frappe.db.get_value = MagicMock(return_value=stage)
		frappe.db.set_value = MagicMock()
		frappe.msgprint = MagicMock()
		template = Record(name="KIT-RA02", doctype="ilL-Extrusion-Kit-Template", product_status=new)
		template["get_doc_before_save"] = lambda: Record(product_status=old)
		module.on_template_update(template)
		return notify.notify, frappe

	def test_hiding_a_published_page_notifies(self):
		for new in ("Draft", "Active"):
			with self.subTest(new=new):
				notify, frappe = self.load("Active + Live", new)
				notify.assert_called_once()
				self.assertIn("hidden", notify.call_args.args[0])
				frappe.db.set_value.assert_not_called()

	def test_back_to_live_from_discontinued_resets_to_webflow_draft(self):
		for old in ("Discontinued", "Archived"):
			with self.subTest(old=old):
				notify, frappe = self.load(old, "Active + Live")
				frappe.db.set_value.assert_called_once_with(
					"ilL-Webflow-Product", "kit-ra02", "webflow_status", "Webflow Draft"
				)
				notify.assert_not_called()

	def test_internal_only_back_to_live_resumes(self):
		notify, frappe = self.load("Internal Only", "Active + Live")
		frappe.db.set_value.assert_not_called()
		notify.assert_not_called()

	def test_never_published_or_hidden_pages_do_nothing(self):
		notify, _frappe = self.load("Active + Live", "Draft", published=False)
		notify.assert_not_called()
		notify, _frappe = self.load("Active + Live", "Draft", stage="Webflow Draft")
		notify.assert_not_called()


if __name__ == "__main__":
	unittest.main()
