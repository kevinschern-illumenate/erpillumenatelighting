"""The server-side fill of generated spec sheets (api/spec_sheet_fill.py).

``generated_sheet`` builds a small PDF shaped like the generator's output (pdf-lib): footer text
fields with a widget per page, radio groups whose /Opt lists the codes and whose widget states
are indexes, display boxes, and highlight boxes in the Subject.
"""

import io
import json
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
	ArrayObject,
	DecodedStreamObject,
	DictionaryObject,
	FloatObject,
	NameObject,
	NumberObject,
	TextStringObject,
)

from illumenate_lighting.illumenate_lighting.api import spec_sheet_fill

RADIO = 1 << 15
MARK = b"0 0.4 0.2 rg 2 2 5 5 re f"


def _stream(writer, data, bbox):
	stream = DecodedStreamObject()
	stream.set_data(data)
	stream.update(
		{
			NameObject("/Type"): NameObject("/XObject"),
			NameObject("/Subtype"): NameObject("/Form"),
			NameObject("/BBox"): ArrayObject([FloatObject(v) for v in bbox]),
		}
	)
	return writer._add_object(stream)


def _rect(*values):
	return ArrayObject([FloatObject(v) for v in values])


def generated_sheet(pages=2, steps=None, subject=None, text_steps=()):
	"""A two-page sheet: footer fields on every page, the builder on page 1."""
	steps = steps or {"0": ["KIT-RA01"], "1": ["WH", "WL", "WX"], "2": ["MC", "MG"]}
	writer = PdfWriter()
	for _ in range(pages):
		writer.add_blank_page(width=612, height=792)
	font = writer._add_object(
		DictionaryObject(
			{
				NameObject("/Type"): NameObject("/Font"),
				NameObject("/Subtype"): NameObject("/Type1"),
				NameObject("/BaseFont"): NameObject("/Helvetica"),
			}
		)
	)
	fields = ArrayObject()

	def annotate(page, widget):
		page = writer.pages[page]
		if "/Annots" not in page:
			page[NameObject("/Annots")] = ArrayObject()
		page["/Annots"].append(widget.indirect_reference)

	def text_field(name, rect, every_page=False):
		field = DictionaryObject(
			{
				NameObject("/FT"): NameObject("/Tx"),
				NameObject("/T"): TextStringObject(name),
				NameObject("/DA"): TextStringObject("/Helv 10 Tf 0 g"),
			}
		)
		field_ref = writer._add_object(field)
		kids = ArrayObject()
		for page in range(pages if every_page else 1):
			widget = DictionaryObject(
				{
					NameObject("/Type"): NameObject("/Annot"),
					NameObject("/Subtype"): NameObject("/Widget"),
					NameObject("/Rect"): _rect(*rect),
					NameObject("/Parent"): field_ref,
					NameObject("/P"): writer.pages[page].indirect_reference,
				}
			)
			writer._add_object(widget)
			annotate(page, widget)
			kids.append(widget.indirect_reference)
		field[NameObject("/Kids")] = kids
		fields.append(field_ref)

	for index, name in enumerate(("project_name", "fixture_type", "project_location")):
		text_field(name, (40 + index * 180, 46, 200 + index * 180, 60), every_page=True)
	for step, options in steps.items():
		x = 40 + int(step) * 100
		if step in text_steps:
			text_field(f"step_{step}", (x, 300, x + 60, 312))
			continue
		field = DictionaryObject(
			{
				NameObject("/FT"): NameObject("/Btn"),
				NameObject("/Ff"): NumberObject(RADIO),
				NameObject("/T"): TextStringObject(f"step_{step}"),
				NameObject("/Opt"): ArrayObject([TextStringObject(o) for o in options]),
			}
		)
		if step == "0":
			field[NameObject("/V")] = NameObject("/0")
		field_ref = writer._add_object(field)
		kids = ArrayObject()
		for index in range(len(options)):
			on = _stream(writer, MARK, (0, 0, 9, 9))
			off = _stream(writer, b"", (0, 0, 9, 9))
			widget = DictionaryObject(
				{
					NameObject("/Type"): NameObject("/Annot"),
					NameObject("/Subtype"): NameObject("/Widget"),
					NameObject("/Rect"): _rect(x, 280 - index * 12, x + 9, 289 - index * 12),
					NameObject("/Parent"): field_ref,
					NameObject("/P"): writer.pages[0].indirect_reference,
					NameObject("/AS"): NameObject("/0" if step == "0" and index == 0 else "/Off"),
					NameObject("/AP"): DictionaryObject(
						{
							NameObject("/N"): DictionaryObject(
								{NameObject(f"/{index}"): on, NameObject("/Off"): off}
							)
						}
					),
				}
			)
			writer._add_object(widget)
			annotate(0, widget)
			kids.append(widget.indirect_reference)
		field[NameObject("/Kids")] = kids
		fields.append(field_ref)
		if step != "0":
			text_field(f"display_step_{step}", (x, 295, x + 60, 307))
	writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
		{
			NameObject("/Fields"): fields,
			NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
			NameObject("/DR"): DictionaryObject(
				{NameObject("/Font"): DictionaryObject({NameObject("/Helv"): font})}
			),
		}
	)
	if subject is not None:
		writer.add_metadata({"/Subject": json.dumps(subject)})
	output = io.BytesIO()
	writer.write(output)
	return output.getvalue()


def page_text(pdf):
	return [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]


def content(pdf, page=0):
	return PdfReader(io.BytesIO(pdf)).pages[page].get_contents().get_data()


class Inspect(unittest.TestCase):
	def test_lists_footer_fields_steps_and_codes(self):
		info = spec_sheet_fill.inspect(generated_sheet(subject=[{"code": "1:WH 1:WL"}]))
		self.assertTrue(info["has_form"])
		self.assertEqual(info["steps"]["1"], ["WH", "WL", "WX"])
		self.assertEqual(info["steps"]["0"], ["KIT-RA01"])
		self.assertIn("project_name", info["text_fields"])
		self.assertEqual(sorted(info["display_steps"]), ["1", "2"])
		self.assertEqual(info["highlight_style"], "steps")

	def test_old_row_label_highlights_and_plain_pdfs(self):
		self.assertEqual(
			spec_sheet_fill.inspect(generated_sheet(subject=[{"code": "Lenses"}]))["highlight_style"],
			"rows",
		)
		writer = PdfWriter()
		writer.add_blank_page(width=612, height=792)
		plain = io.BytesIO()
		writer.write(plain)
		info = spec_sheet_fill.inspect(plain.getvalue())
		self.assertFalse(info["has_form"])
		self.assertEqual(info["steps"], {})


class Fill(unittest.TestCase):
	def fill(self, sheet=None, **kwargs):
		kwargs.setdefault(
			"text",
			{"project_name": "Seattle Library", "fixture_type": "L2", "project_location": "Reading Room"},
		)
		kwargs.setdefault("steps", {"1": "wl", "2": "MG"})
		return spec_sheet_fill.fill(sheet or generated_sheet(), **kwargs)

	def test_footer_values_print_on_every_page(self):
		result = self.fill()
		for text in page_text(result["pdf"]):
			self.assertIn("Seattle Library", text)
			self.assertIn("L2", text)
			self.assertIn("Reading Room", text)

	def test_radios_are_selected_by_code_and_drawn_with_their_display_boxes(self):
		result = self.fill()
		self.assertEqual(result["selected"], {"1": "WL", "2": "MG"})
		self.assertEqual(result["unmatched"], {})
		data = content(result["pdf"])
		# The series (preselected) and the two chosen options are drawn, nothing else.
		self.assertEqual(data.count(b" Do Q"), 3)
		self.assertIn(b"q 1.000000 0 0 1.000000 140.0000 268.0000 cm /IllFill2 Do Q", data)
		self.assertEqual(data.count(b"q\n"), data.count(b"\nQ\n"))
		text = page_text(result["pdf"])[0]
		self.assertIn("WL", text)
		self.assertIn("MG", text)

	def test_the_result_has_no_form_left(self):
		reader = PdfReader(io.BytesIO(self.fill()["pdf"]))
		self.assertNotIn("/AcroForm", reader.trailer["/Root"])
		for page in reader.pages:
			for annot in page.get("/Annots") or []:
				self.assertNotEqual(annot.get_object().get("/Subtype"), "/Widget")
		self.assertEqual(len(reader.pages), 2)

	def test_copies_merged_into_one_packet_keep_their_own_values(self):
		first = self.fill(text={"project_name": "P", "fixture_type": "A1", "project_location": "Lobby"})
		second = self.fill(text={"project_name": "P", "fixture_type": "B7", "project_location": "Hall"})
		writer = PdfWriter()
		for pdf in (first["pdf"], second["pdf"]):
			writer.append(PdfReader(io.BytesIO(pdf)))
		merged = io.BytesIO()
		writer.write(merged)
		pages = page_text(merged.getvalue())
		self.assertIn("A1", pages[0])
		self.assertIn("Lobby", pages[1])
		self.assertIn("B7", pages[2])
		self.assertIn("Hall", pages[3])
		self.assertNotIn("B7", pages[0])

	def test_unknown_codes_and_missing_steps_are_reported_not_guessed(self):
		result = self.fill(steps={"1": "ZZ", "9": "E"})
		self.assertEqual(result["unmatched"], {"1": "ZZ"})
		self.assertEqual(result["missing_steps"], ["9"])
		self.assertEqual(content(result["pdf"]).count(b" Do Q"), 1)

	def test_a_free_text_step_takes_its_value(self):
		sheet = generated_sheet(steps={"0": ["ILL-SH03-SW"], "7": []}, text_steps=("7",))
		result = self.fill(sheet, steps={"7": "216.0"})
		self.assertEqual(result["selected"], {"7": "216.0"})
		self.assertIn("216.0", page_text(result["pdf"])[0])

	def test_highlights_follow_the_selected_step_codes_only(self):
		subject = [
			{"code": "1:WH 1:WL", "pageIndex": 0, "x": 27, "y": 600, "width": 50, "height": 9},
			{"code": "1:WX", "pageIndex": 0, "x": 27, "y": 580, "width": 50, "height": 9},
			{"code": "2:mg", "pageIndex": 1, "x": 27, "y": 560, "width": 50, "height": 9, "isRow": True},
		]
		result = self.fill(generated_sheet(subject=subject))
		self.assertEqual(result["highlights"], 2)
		self.assertIn(b"/IllHighlight gs", content(result["pdf"], 0))
		self.assertIn(b"25.000 598.500 54.000 12.000 re f", content(result["pdf"], 0))
		self.assertNotIn(b"578.500", content(result["pdf"], 0))
		self.assertIn(b"27.000 559.500 50.000 10.000 re f", content(result["pdf"], 1))
		self.assertEqual(PdfReader(io.BytesIO(result["pdf"])).metadata.get("/Subject"), "")

	def test_a_sheet_without_a_form_comes_back_unchanged(self):
		writer = PdfWriter()
		writer.add_blank_page(width=612, height=792)
		plain = io.BytesIO()
		writer.write(plain)
		result = spec_sheet_fill.fill(plain.getvalue(), text={"project_name": "P"}, steps={"1": "WH"})
		self.assertFalse(result["has_form"])
		self.assertEqual(result["pdf"], plain.getvalue())

	def test_title_names_the_line(self):
		result = self.fill(title="L2 · KIT-RA01-WL-MG")
		self.assertEqual(PdfReader(io.BytesIO(result["pdf"])).metadata.title, "L2 · KIT-RA01-WL-MG")


if __name__ == "__main__":
	unittest.main()
