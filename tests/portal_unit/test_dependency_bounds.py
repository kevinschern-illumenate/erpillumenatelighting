"""Readiness dependency bounds (owner, 2026-11-19): 3,000 records, one summary line past them."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from test_services import ROOT, load_service

MODULE = ROOT + ".api.product_readiness"


class Field(SimpleNamespace):
	pass


class Meta:
	def __init__(self, name, fields):
		self.name = name
		self.fields = fields

	def has_field(self, fieldname):
		return any(field.fieldname == fieldname for field in self.fields)


class Doc(dict):
	def __init__(self, doctype, name, links=()):
		super().__init__(name=name, **{f"link_{i}": target for i, target in enumerate(links)})
		self.doctype = doctype
		self.name = name
		self.meta = Meta(
			doctype,
			[
				Field(fieldname=f"link_{i}", fieldtype="Link", options="ilL-Attribute-X")
				for i in range(len(links))
			],
		)

	def as_dict(self):
		return dict(self)


class DependencyBounds(unittest.TestCase):
	def manifest(self, links, limit):
		with load_service(MODULE) as (readiness, frappe):
			docs = {name: Doc("ilL-Attribute-X", name) for name in links}
			frappe.as_json = lambda value: __import__("json").dumps(value, default=str)
			frappe.db.exists = MagicMock(return_value=True)
			frappe.get_doc = MagicMock(side_effect=lambda _doctype, name: docs[name])
			readiness.related_dependencies = lambda doc: []
			readiness.unpublished_fields = lambda doctype: ()
			readiness.MAX_DEPENDENCIES = limit
			return readiness.dependency_manifest(Doc("ilL-Spec-Root", "ROOT", links))

	def test_the_limit_is_3000(self):
		with load_service(MODULE) as (readiness, _frappe):
			self.assertEqual(readiness.MAX_DEPENDENCIES, 3000)

	def test_records_past_the_limit_give_one_summary_line(self):
		records, issues = self.manifest([f"A{i}" for i in range(10)], limit=4)
		self.assertEqual(len(records), 4)
		dependency_issues = [issue for issue in issues if issue["field"] == "dependencies"]
		self.assertEqual(len(dependency_issues), 1)
		self.assertEqual(dependency_issues[0]["record"], "ROOT")
		self.assertTrue(dependency_issues[0]["message"].startswith("7 linked records were not checked"))

	def test_a_graph_within_the_limit_has_no_dependency_issue(self):
		records, issues = self.manifest([f"A{i}" for i in range(10)], limit=3000)
		self.assertEqual(len(records), 11)
		self.assertEqual([issue for issue in issues if issue["field"] == "dependencies"], [])


if __name__ == "__main__":
	unittest.main()
