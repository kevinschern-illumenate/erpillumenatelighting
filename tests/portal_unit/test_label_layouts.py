"""Label layouts (templates/labels): each renders from a sample context, prints what it must,
leaves blanks out and sits on a page exactly the roll's size.

Rendered the way api/labels.render_html does it, with templates loaded under "templates/".
"""

import types
import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, PrefixLoader, StrictUndefined
from test_services import ROOT, load_service

TEMPLATES = Path(__file__).resolve().parents[2] / "illumenate_lighting" / "templates"
SMALL = types.SimpleNamespace(width_in=2.5, height_in=1.5)
LARGE = types.SimpleNamespace(width_in=4, height_in=6)

WORK_ORDER = {
	"doc_label": "WORK ORDER",
	"wo": "MFG-WO-2026-00412",
	"so": "SAL-ORD-2026-00188",
	"customer": "Riverside Hospitality Group",
	"po": "PO-77821",
	"part_number": "ILL-LN-24-27-L1-SA-120IN",
	"item_name": "Linear 24V 2700K",
	"length": "10' 3\"",
	"fixture_type": "L1",
	"section": "Level 2 Lobby",
	"ship_by": "12/04/26",
	"project": "Riverside Hotel",
	"build_qty": "12",
	"pull": [{"item": "PROFILE-A", "qty": "3 Nos"}],
	"pull_more": 0,
	"qr_payload": "https://erp.test/app/work-order/MFG-WO-2026-00412",
	"subcomponent": "",
	"unit_text": "",
}


class Layouts(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.ctx = load_service(ROOT + ".api.labels")
		cls.labels, cls.frappe = cls.ctx.__enter__()
		env = Environment(loader=PrefixLoader({"templates": FileSystemLoader(str(TEMPLATES))}))
		cls.env = env
		cls.frappe.render_template = lambda name, context: env.get_template(name).render(**context)
		cls.frappe.utils.nowdate = lambda: "2026-11-23"
		cls.labels._logo_src = lambda: "data:image/png;base64,AAAA"
		cls.labels._fonts = lambda: [("ilL Poppins", 400, "https://erp.test/assets/p.ttf")]

	@classmethod
	def tearDownClass(cls):
		cls.ctx.__exit__(None, None, None)

	def render(self, layout, context, stock=SMALL):
		return self.labels.render_html([(layout, context)], stock)

	def test_every_layout_file_exists_for_every_template_option(self):
		import json

		doctype = (
			TEMPLATES.parent
			/ "illumenate_lighting"
			/ "doctype"
			/ "ill_label_template"
			/ "ill_label_template.json"
		)
		options = next(f for f in json.loads(doctype.read_text())["fields"] if f["fieldname"] == "layout")[
			"options"
		].split("\n")
		for layout in options:
			self.assertTrue((TEMPLATES / "labels" / f"{layout}.html").exists(), layout)

	def test_page_is_the_roll_size_with_no_extra_page(self):
		html = self.labels.render_html([("work_order", WORK_ORDER), ("product", WORK_ORDER)], SMALL)
		self.assertIn("width: 63.5mm; height: 38.1mm;", html)
		self.assertEqual(html.count('class="lbl break"'), 1)  # the last label has no page break
		self.assertEqual(html.count('class="lbl"'), 1)
		self.assertIn('@font-face { font-family: "ilL Poppins"', html)
		packet = self.render("packet_4x6", WORK_ORDER, LARGE)
		self.assertIn("width: 101.6mm; height: 152.4mm;", packet)

	def test_work_order_label(self):
		html = self.render("work_order", WORK_ORDER)
		for text in (
			"WORK ORDER",
			"MFG-WO-2026-00412",
			"SO SAL-ORD-2026-00188 · L1 · Level 2 Lobby",
			"Ship by 12/04/26",
			"Build qty 12",
			"data:image/svg+xml",
		):
			self.assertIn(text, html)

	def test_product_label_and_blank_fields(self):
		context = {
			**WORK_ORDER,
			"doc_label": "SALES ORDER",
			"unit_text": "Unit 3 of 12",
			"po": "",
			"length": "",
			"section": "",
		}
		html = self.render("product", context)
		for text in (
			"SALES ORDER",
			">L1<",
			"ILL-LN-24-27-L1-SA-120IN",
			"SO SAL-ORD-2026-00188",
			"Unit 3 of 12",
		):
			self.assertIn(text, html)
		self.assertNotIn("PO ", html)
		self.assertNotIn("Length", html)
		for junk in ("None", "N/A", "{{"):
			self.assertNotIn(junk, html)

	def test_light_engine_and_kit_piece_use_the_product_layout(self):
		html = self.render(
			"light_engine",
			{**WORK_ORDER, "doc_label": "LIGHT ENGINE", "subcomponent": "Light engine LE1, runs 1-2"},
		)
		self.assertIn("LIGHT ENGINE", html)
		self.assertIn("Light engine LE1, runs 1-2", html)
		self.assertIn("KIT PIECE", self.render("kit_piece", {**WORK_ORDER, "doc_label": "KIT PIECE"}))

	def test_packet_checklist_and_pull_list_fit_their_budget(self):
		context = {
			**WORK_ORDER,
			"doc_label": "WORK ORDER PACKET",
			"checklist": ["Work order label", "Product labels x 12"],
			"pull": [{"item": f"PART-{i}", "qty": "1 Nos"} for i in range(10)],
			"pull_more": 2,
		}
		html = self.render("packet_4x6", context, LARGE)
		self.assertIn("WORK ORDER PACKET", html)
		self.assertIn("Product labels x 12", html)
		self.assertIn("PART-8", html)
		self.assertNotIn("PART-9<", html)
		self.assertIn("+ 3 more rows on the work order", html)
		self.assertIn("Printed 11/23/26", html)

	def test_reel_tag_and_shelf_labels_carry_their_barcodes(self):
		reel = self.render(
			"reel",
			{
				"doc_label": "REEL",
				"reel_id": "R-00041",
				"barcode": "R-00041",
				"item_code": "TAPE-1",
				"starting_length": "100'",
				"shelf": "B3",
				"lot": "",
				"received": "",
			},
		)
		self.assertIn("R-00041", reel)
		self.assertIn("Start 100'", reel)
		self.assertIn("Shelf B3", reel)
		self.assertNotIn("Lot ", reel)
		self.assertIn("Left:", reel)
		self.assertIn("data:image/svg+xml;base64,", reel)
		tag = self.render("reel_tag", {"doc_label": "REEL", "reel_id": "R-00042", "barcode": "R-00042"})
		self.assertIn("R-00042", tag)
		shelf = self.render(
			"location",
			{
				"doc_label": "SHELF",
				"location_code": "B3",
				"barcode": "LOC-B3",
				"warehouse": "Stores - ilL",
				"description": "",
			},
		)
		self.assertIn(">B3<", shelf)
		self.assertIn("Stores - ilL", shelf)

	def test_layouts_need_nothing_beyond_their_inputs(self):
		strict = Environment(
			loader=PrefixLoader({"templates": FileSystemLoader(str(TEMPLATES))}), undefined=StrictUndefined
		)
		keys = {
			"logo_src": "",
			"qr_src": "",
			"barcode_src": "",
			"printed_on": "",
			"checklist": [],
			"doc_label": "X",
			"unit_text": "",
		}
		helpers = {
			"fit": self.labels.fit_pt,
			"truncate": self.labels.truncate,
			"width_mm": 63.5,
			"height_mm": 38.1,
		}
		samples = {
			"work_order": WORK_ORDER,
			"product": WORK_ORDER,
			"packet_4x6": WORK_ORDER,
			"reel": {
				"reel_id": "R-1",
				"barcode": "R-1",
				"item_code": "",
				"item_name": "",
				"starting_length": "",
				"received": "",
				"lot": "",
				"shelf": "",
			},
			"reel_tag": {"reel_id": "R-1", "barcode": "R-1"},
			"location": {"location_code": "A1", "barcode": "LOC-A1", "warehouse": "", "description": ""},
			"_test": {"stock": "1.5 x 2.5"},
		}
		for layout, context in samples.items():
			strict.get_template(f"templates/labels/{layout}.html").render(c={**keys, **context}, **helpers)


if __name__ == "__main__":
	unittest.main()
