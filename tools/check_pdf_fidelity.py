"""Render actual PDF filler/merger output against a synthetic two-page master.

This is local visual evidence, not approval of installed family PDF mappings.
Uses the bundled test runtime's reportlab/pypdfium2 and explicit Frappe doubles.
"""

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pypdfium2
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/portal_unit"))
from test_services import ROOT as PACKAGE
from test_services import Record, load_service


def main():
	output = ROOT / ".tools/portal-pdf-qa"
	output.mkdir(parents=True, exist_ok=True)
	stream = io.BytesIO()
	canvas = Canvas(stream, pagesize=(612, 792))
	canvas.setTitle("Synthetic engineering specification - local fidelity fixture")
	canvas.setFont("Helvetica-Bold", 18)
	canvas.drawString(50, 735, "Engineering specification")
	canvas.setFont("Helvetica", 11)
	canvas.drawString(50, 698, "Synthetic master: member identity and dimensions")
	for name, label, y in (("designation", "Fixture / member", 628), ("length", "Manufactured length", 548)):
		canvas.drawString(50, y + 31, label)
		canvas.acroForm.textfield(name=name, x=50, y=y, width=510, height=28, fontSize=11)
	canvas.drawString(50, 480, "Included power")
	canvas.acroForm.checkbox(name="power", x=150, y=475, checked=False, buttonStyle="check")
	canvas.showPage()
	canvas.setFont("Helvetica-Bold", 18)
	canvas.drawString(50, 735, "Cable and feed notes")
	canvas.acroForm.textfield(
		name="notes", x=50, y=595, width=510, height=85, fontSize=10, fieldFlags="multiline"
	)
	canvas.save()
	content = stream.getvalue()
	with load_service(PACKAGE + ".api.spec_submittal") as (pdf, frappe):
		frappe.log_error = lambda *args, **kwargs: None
		with patch.object(pdf, "_get_file_doc_by_url", return_value=Record(get_content=lambda: content)):
			first = pdf._fill_pdf_form_fields(
				"/files/master.pdf",
				{
					"designation": "L1 / M1 - Long west elevation",
					"length": "6096 mm (20 ft)",
					"power": "/Yes",
					"notes": "Independent feed. Leader: 1828.8 mm (6 ft).\nSupply 1, output 1. Preserve this cable cut.",
				},
			)
			second = pdf._fill_pdf_form_fields(
				"/files/master.pdf",
				{
					"designation": "L1 / M2 - Short return",
					"length": "1524 mm (5 ft)",
					"power": "/Off",
					"notes": "Independent feed. Leader: 914.4 mm (3 ft).\nExternal power requirements remain visible.",
				},
			)
			assert first and second, "Filled output was not produced"
			merged = pdf._merge_pdfs([first, second])
			assert merged, "Merge failed"
			assert pdf._fill_pdf_form_fields("/files/master.pdf", {"missing_field": "No"}) is None
	(output / "filled-members.pdf").write_bytes(merged)
	reader = PdfReader(io.BytesIO(merged))
	assert len(reader.pages) == 4
	assert "Long west" in reader.pages[0].extract_text()
	assert "Short return" in reader.pages[2].extract_text()
	assert "1828.8" in reader.pages[1].extract_text()
	assert "914.4" in reader.pages[3].extract_text()
	with pypdfium2.PdfDocument(merged) as document:
		for index in range(len(document)):
			page = document[index]
			bitmap = page.render(scale=1.25)
			bitmap.to_pil().save(output / f"page-{index + 1}.png")
			bitmap.close()
			page.close()
	print(
		"Actual filler and merger: 4 distinct pages; missing mapped field blocked; raster previews in "
		+ str(output)
	)


if __name__ == "__main__":
	main()
