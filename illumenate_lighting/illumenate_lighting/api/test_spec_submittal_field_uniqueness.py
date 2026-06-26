# Copyright (c) 2026, ilLumenate Lighting and Contributors
# See license.txt

"""
Unit tests for spec-submittal form-field isolation.

These verify that filled submittals are made independent of one another before
being merged into a packet, so that identically named AcroForm fields from
different fixtures do not collapse into a single shared value (the bug where
submittal data repeated across every fixture in the packet).

The tests stub out frappe so the module imports without the framework, and
skip automatically when pypdf is not installed.
"""

import sys
import unittest
from unittest.mock import MagicMock

# Stub out frappe and its sub-modules so the import succeeds without the framework
_frappe_mock = MagicMock()
sys.modules.setdefault("frappe", _frappe_mock)
sys.modules.setdefault("frappe.utils", MagicMock())
sys.modules.setdefault("frappe.utils.file_manager", MagicMock())

try:
	import pypdf  # noqa: F401

	HAS_PYPDF = True
except ImportError:  # pragma: no cover - pypdf is a declared dependency
	HAS_PYPDF = False

from illumenate_lighting.illumenate_lighting.api.spec_submittal import (  # noqa: E402
	_make_form_fields_unique,
	_remove_form_fields,
)


def _build_writer_with_fields():
	"""Build a minimal PdfWriter whose AcroForm has one parent and one child field."""
	from pypdf import PdfWriter
	from pypdf.generic import (
		ArrayObject,
		DictionaryObject,
		NameObject,
		TextStringObject,
	)

	writer = PdfWriter()

	parent_field = DictionaryObject()
	parent_field[NameObject("/T")] = TextStringObject("fixture_name")

	child_widget = DictionaryObject()
	child_widget[NameObject("/T")] = TextStringObject("kid")
	# Mark as a child of another field – must NOT be renamed directly.
	child_widget[NameObject("/Parent")] = DictionaryObject()

	acroform = DictionaryObject()
	acroform[NameObject("/Fields")] = ArrayObject([parent_field, child_widget])
	writer._root_object[NameObject("/AcroForm")] = acroform

	return writer, parent_field, child_widget


@unittest.skipUnless(HAS_PYPDF, "pypdf is required for these tests")
class TestMakeFormFieldsUnique(unittest.TestCase):
	def test_top_level_field_is_prefixed(self):
		"""A top-level field's name gets a unique prefix but keeps the original suffix."""
		writer, parent_field, _child = _build_writer_with_fields()

		_make_form_fields_unique(writer)

		new_name = str(parent_field["/T"])
		self.assertNotEqual(new_name, "fixture_name")
		self.assertTrue(new_name.endswith("fixture_name"), new_name)

	def test_child_field_is_not_renamed(self):
		"""Child widgets inherit their name from the parent and must be left untouched."""
		writer, _parent, child_widget = _build_writer_with_fields()

		_make_form_fields_unique(writer)

		self.assertEqual(str(child_widget["/T"]), "kid")

	def test_two_documents_get_distinct_prefixes(self):
		"""Two independently processed documents must not share field names."""
		writer_a, parent_a, _ = _build_writer_with_fields()
		writer_b, parent_b, _ = _build_writer_with_fields()

		_make_form_fields_unique(writer_a)
		_make_form_fields_unique(writer_b)

		self.assertNotEqual(str(parent_a["/T"]), str(parent_b["/T"]))

	def test_no_acroform_is_noop(self):
		"""Documents without an AcroForm are handled gracefully."""
		from pypdf import PdfWriter

		writer = PdfWriter()
		# Should not raise even though there is no /AcroForm.
		_make_form_fields_unique(writer)


@unittest.skipUnless(HAS_PYPDF, "pypdf is required for these tests")
class TestRemoveFormFields(unittest.TestCase):
	def _build_writer_with_widget_page(self):
		"""Build a PdfWriter with one page holding a widget annotation and a link."""
		from pypdf import PdfWriter
		from pypdf.generic import (
			ArrayObject,
			DictionaryObject,
			NameObject,
			TextStringObject,
		)

		writer = PdfWriter()
		page = writer.add_blank_page(width=200, height=200)

		widget = DictionaryObject()
		widget[NameObject("/Subtype")] = NameObject("/Widget")
		widget[NameObject("/T")] = TextStringObject("fixture_name")

		link = DictionaryObject()
		link[NameObject("/Subtype")] = NameObject("/Link")

		page[NameObject("/Annots")] = ArrayObject(
			[writer._add_object(widget), writer._add_object(link)]
		)

		acroform = DictionaryObject()
		acroform[NameObject("/Fields")] = ArrayObject([widget])
		writer._root_object[NameObject("/AcroForm")] = acroform

		return writer, page

	def test_widget_annotations_are_removed(self):
		"""Widget annotations (the form fields) are dropped after flattening."""
		writer, page = self._build_writer_with_widget_page()

		_remove_form_fields(writer)

		subtypes = [a.get_object().get("/Subtype") for a in page["/Annots"]]
		self.assertNotIn("/Widget", subtypes)

	def test_non_widget_annotations_are_preserved(self):
		"""Non-widget annotations such as links are left untouched."""
		writer, page = self._build_writer_with_widget_page()

		_remove_form_fields(writer)

		subtypes = [a.get_object().get("/Subtype") for a in page["/Annots"]]
		self.assertIn("/Link", subtypes)

	def test_acroform_is_removed(self):
		"""The now-empty AcroForm dictionary is removed from the document root."""
		writer, _page = self._build_writer_with_widget_page()

		_remove_form_fields(writer)

		self.assertNotIn("/AcroForm", writer._root_object)

	def test_no_annots_is_noop(self):
		"""Pages without annotations are handled gracefully."""
		from pypdf import PdfWriter

		writer = PdfWriter()
		writer.add_blank_page(width=200, height=200)
		# Should not raise even though there are no annotations or AcroForm.
		_remove_form_fields(writer)


if __name__ == "__main__":
	unittest.main()