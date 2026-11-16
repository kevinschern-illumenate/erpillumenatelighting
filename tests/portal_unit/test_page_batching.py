"""Plan 2.7: collaborator and resource pages read related rows in one query, not one per row."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from test_services import Record, load_service

COLLABORATORS = "illumenate_lighting.templates.pages.collaborators"
RESOURCES = "illumenate_lighting.templates.pages.resources"


class CollaboratorUsers(unittest.TestCase):
	def test_user_details_are_one_query_and_skip_missing_users(self):
		with load_service(COLLABORATORS) as (page, frappe):
			frappe.get_all.return_value = [
				Record(name="a@x.com", full_name="Ann <A>", email="a@x.com"),
				Record(name="b@x.com", full_name="Bob", email="bob@x.com"),
			]
			users = page._user_details(["b@x.com", "a@x.com", "gone@x.com", None, "a@x.com"])
			frappe.get_all.assert_called_once()
			args, kwargs = frappe.get_all.call_args
			self.assertEqual(args, ("User",))
			self.assertEqual(kwargs["filters"], {"name": ["in", ["a@x.com", "b@x.com", "gone@x.com"]]})
			self.assertEqual(users["b@x.com"].email, "bob@x.com")
			self.assertNotIn("gone@x.com", users)
			frappe.get_doc.assert_not_called()
			frappe.db.exists.assert_not_called()

	def test_no_collaborators_means_no_query(self):
		with load_service(COLLABORATORS) as (page, frappe):
			self.assertEqual(page._user_details([]), {})
			frappe.get_all.assert_not_called()

	def test_page_uses_the_batched_details(self):
		source = (Path(__file__).resolve().parents[2] / "illumenate_lighting/templates/pages/collaborators.py").read_text(
			encoding="utf8"
		)
		loop = source.split("collaborators = []", 1)[1].split("available_users", 1)[0]
		self.assertIn("_user_details(", loop)
		self.assertNotIn("get_doc(", loop)
		self.assertNotIn("db.exists(", loop)


class ResourceSpecSheets(unittest.TestCase):
	def test_thirty_products_cost_two_queries_and_keep_order(self):
		with load_service(RESOURCES) as (page, frappe):
			products = [
				Record(name=f"P-{i}", product_name=f"Product {i:02d}", product_slug=f"p-{i}", short_description=None)
				for i in range(30)
			]
			documents = [
				Record(parent="P-2", document_file="/files/p2-b.pdf", document_title="B", display_order=1),
				Record(parent="P-0", document_file="/files/p0.pdf", document_title="Zero", display_order=1),
				Record(parent="P-2", document_file="/files/p2-a.pdf", document_title="A", display_order=2),
			]
			frappe.db.exists.return_value = True
			frappe.get_all = MagicMock(side_effect=[products, documents])
			sheets = page._get_webflow_spec_sheets()
			self.assertEqual(frappe.get_all.call_count, 2)
			docs_call = frappe.get_all.call_args_list[1]
			self.assertEqual(docs_call.args, ("ilL-Child-Webflow-Document",))
			self.assertEqual(docs_call.kwargs["filters"]["parent"], ["in", [f"P-{i}" for i in range(30)]])
			self.assertEqual(docs_call.kwargs["filters"]["document_type"], "Spec Sheet")
			self.assertEqual([(s["product_name"], s["title"]) for s in sheets], [
				("Product 00", "Zero"),
				("Product 02", "B"),
				("Product 02", "A"),
			])
			self.assertEqual(sheets[0]["description"], "Product specification sheet")
			self.assertEqual(sheets[0]["url"], "/files/p0.pdf")

	def test_no_products_skips_the_documents_query(self):
		with load_service(RESOURCES) as (page, frappe):
			frappe.db.exists.return_value = True
			frappe.get_all = MagicMock(return_value=[])
			self.assertEqual(page._get_webflow_spec_sheets(), [])
			frappe.get_all.assert_called_once()


if __name__ == "__main__":
	unittest.main()
