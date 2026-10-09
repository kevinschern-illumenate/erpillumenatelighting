"""Riser deliverable checks before a generated file is stored (System Designer WP-3.7)."""

import io
import unittest
import zipfile

from test_services import ROOT, Record, load_service

DELIVERABLES = ROOT + ".system_design.deliverables"
SVG = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'


def archive(members):
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w") as target:
		for name, data in members.items():
			target.writestr(name, data)
	return buffer.getvalue()


class ValidateDeliverable(unittest.TestCase):
	def code(self, module, kind, content):
		try:
			module.validate_deliverable(kind, content)
		except module.DesignError as e:
			return e.code
		return None

	def test_accepts_the_files_the_designer_writes(self):
		with load_service(DELIVERABLES) as (module, _frappe):
			self.assertEqual(module.validate_deliverable("Riser SVG", SVG), "image/svg+xml")
			logo = b'<svg><image href="data:image/png;base64,iVBORw0KGgo=" x="1"/></svg>'
			self.assertEqual(module.validate_deliverable("Riser SVG", logo), "image/svg+xml")
			dxf = archive(
				{
					"E-1.dxf": "999\r\nilLumenate System Designer\r\n0\r\nSECTION\r\n",
					"fonts/Arimo-Regular.ttf": "x",
				}
			)
			self.assertEqual(module.validate_deliverable("Riser DXF ZIP", dxf), "application/zip")
			# The client diagram is checked as the riser file of the same format.
			self.assertEqual(module.validate_deliverable("Presentation SVG", SVG), "image/svg+xml")

	def test_refuses_active_or_mislabelled_content(self):
		with load_service(DELIVERABLES) as (module, _frappe):
			for content in (
				b"<svg><script>alert(1)</script></svg>",
				b'<svg onload="alert(1)"></svg>',
				b'<svg><a href="https://example.com">x</a></svg>',
				b'<!DOCTYPE svg [<!ENTITY x "y">]><svg/>',
				b"<html><svg/></html>",
				b"",
			):
				self.assertEqual(self.code(module, "Riser SVG", content), "INVALID", content)
				self.assertEqual(self.code(module, "Presentation SVG", content), "INVALID", content)
			for members in (
				{"E-1.dxf": "0\r\nSECTION", "run.exe": "MZ"},
				{"../E-1.dxf": "0\r\nSECTION"},
				{"fonts/Arimo-Regular.ttf": "x"},
				{"E-1.dxf": "<html>"},
			):
				self.assertEqual(self.code(module, "Riser DXF ZIP", archive(members)), "INVALID", members)
			self.assertEqual(self.code(module, "Riser DXF ZIP", b"not a zip"), "INVALID")
			self.assertEqual(self.code(module, "Presentation PNG", SVG), "INVALID")

	def test_file_names_follow_the_product_name(self):
		record = Record(fixture_schedule="ILL-SCHED-2026-00001", revision="B")
		with load_service(DELIVERABLES) as (module, _frappe):
			self.assertEqual(
				module.deliverable_filename(record, "Riser PDF", "Tabloid"),
				"ilLumenate-System-Designer_ILL-SCHED-2026-00001_revB_Tabloid.pdf",
			)
			self.assertEqual(
				module.deliverable_filename(record, "Riser DXF ZIP", ""),
				"ilLumenate-System-Designer_ILL-SCHED-2026-00001_revB.zip",
			)
			self.assertEqual(
				module.deliverable_filename(record, "Presentation PDF", "Tabloid"),
				"ilLumenate-System-Designer_ILL-SCHED-2026-00001_revB_Client_Tabloid.pdf",
			)


if __name__ == "__main__":
	unittest.main()
