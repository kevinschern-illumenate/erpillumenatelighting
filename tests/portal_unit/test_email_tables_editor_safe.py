"""patches/email_tables_editor_safe.py: the site's template copies get the editor-safe tables."""

import unittest
from pathlib import Path

from test_services import Record, load_service

from illumenate_lighting.illumenate_lighting.email_templates import library

PATCH = "illumenate_lighting.patches.email_tables_editor_safe"
BEFORE = Path(__file__).parent / "fixtures" / "email_bodies_before_editor_safe"


def shipped_before(template):
	"""A template's copy on the site before this patch: the old body, with the card marker
	that automatic templates were seeded with."""
	text = (BEFORE / f"{template.slug}.html").read_text(encoding="utf-8")
	return f"{library.CARD_MARKER}\n{text}" if template.slug in library.automatic_slugs() else text


class EditorSafeTablesPatch(unittest.TestCase):
	def run_patch(self, templates, drafts=()):
		with load_service(PATCH) as (module, frappe):
			frappe.db.exists.side_effect = lambda doctype, name: name in templates
			frappe.db.get_value.side_effect = lambda doctype, name, field: templates.get(name)
			frappe.get_all.return_value = [Record(name=name, mfs_html=html) for name, html in drafts]
			return module, frappe, module.execute()

	def test_every_shipped_copy_becomes_todays_body_and_stays_there(self):
		with load_service(PATCH) as (module, _frappe):
			names = list(module.REPLACEMENTS)
		by_name = {t.name: t for t in library.TEMPLATES}
		self.assertEqual(len(names), 4)
		for name in names:
			with self.subTest(template=name):
				template = by_name[name]
				module, _frappe, _ = self.run_patch({})
				self.assertEqual(module.update(name, shipped_before(template)), template.body())
				self.assertEqual(module.update(name, template.body()), template.body())

	def test_updates_site_copies_and_rfq_drafts_but_not_edited_ones(self):
		by_name = {t.name: t for t in library.TEMPLATES}
		po, rfq = (
			by_name["ilL - Purchase Order - Send to supplier"],
			by_name["ilL - Request for Quotation - Request"],
		)
		edited = shipped_before(by_name["ilL - Sales Invoice - Invoice"]).replace(
			"{{ c.blocks.invoice_schedule }}\n", "{{ c.blocks.invoice_schedule }}<p>Our own words</p>\n"
		)
		templates = {
			po.name: shipped_before(po),
			rfq.name: shipped_before(rfq),
			"ilL - Sales Invoice - Invoice": edited,
		}
		_module, frappe, result = self.run_patch(
			templates, drafts=[("PUR-RFQ-1", shipped_before(rfq)), ("PUR-RFQ-2", "Custom message")]
		)
		self.assertEqual(sorted(result["templates"]), sorted([po.name, rfq.name]))
		self.assertEqual(result["drafts"], ["PUR-RFQ-1"])
		frappe.db.set_value.assert_any_call("Email Template", po.name, "response_html", po.body())
		frappe.db.set_value.assert_any_call(
			"Request for Quotation", "PUR-RFQ-1", "mfs_html", rfq.body(), update_modified=False
		)
		self.assertEqual(frappe.db.set_value.call_count, 3)

	def test_a_partly_edited_copy_is_left_whole(self):
		# One of a template's two snippets gone: changing only the other would leave an
		# unclosed {% if %}, so neither changes.
		po = next(t for t in library.TEMPLATES if t.slug == "po_send")
		text = shipped_before(po).replace("{{ c.blocks.purchase_schedule }}\n", "")
		with load_service(PATCH) as (module, _frappe):
			self.assertEqual(module.update(po.name, text), text)
			self.assertEqual(module.update(po.name, None), None)


if __name__ == "__main__":
	unittest.main()
