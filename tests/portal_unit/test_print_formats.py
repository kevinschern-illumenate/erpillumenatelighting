"""The ilL print formats: helpers (printing.py), the shared template and every format.

Templates render in an environment like Frappe's: sandboxed, DebugUndefined (a missing
value prints as literal "{{ ... }}"), the app's template loader, and the ill_print_*
helpers registered as globals. Lookups are stubbed to return nothing, which is also
what a print sees for a document with few links filled in.
"""

import importlib.util
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jinja2 import ChoiceLoader, DebugUndefined, FileSystemLoader, PrefixLoader
from jinja2.sandbox import SandboxedEnvironment

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "illumenate_lighting"
MODULE = APP / "illumenate_lighting"
FORMATS = MODULE / "print_format"


def load_printing():
	frappe = types.ModuleType("frappe")
	frappe.db = MagicMock()
	frappe.db.get_value.return_value = None
	frappe.db.exists.return_value = False
	frappe.get_all = MagicMock(return_value=[])
	frappe.get_doc = MagicMock()
	frappe.get_meta = MagicMock()
	frappe.log_error = MagicMock()
	frappe.defaults = types.SimpleNamespace(get_user_default=lambda key: "ilLumenate Lighting")
	utils = types.ModuleType("frappe.utils")
	utils.get_url = lambda: "https://example.test"
	html_utils = types.ModuleType("frappe.utils.html_utils")
	html_utils.sanitize_html = lambda text: text
	frappe.utils = utils
	spec = importlib.util.spec_from_file_location("isolated_printing", MODULE / "printing.py")
	module = importlib.util.module_from_spec(spec)
	with patch.dict(
		sys.modules, {"frappe": frappe, "frappe.utils": utils, "frappe.utils.html_utils": html_utils}
	):
		spec.loader.exec_module(module)
	return module, frappe


PRINTING, FRAPPE = load_printing()


class Doc:
	"""A Document stand-in: attribute access, .get(), None for unset fields."""

	def __init__(self, **values):
		self.__dict__.update(values)

	def __getattr__(self, key):
		if key.startswith("__"):
			raise AttributeError(key)
		return None

	def get(self, key, default=None):
		value = self.__dict__.get(key)
		return default if value is None else value


def environment():
	env = SandboxedEnvironment(
		undefined=DebugUndefined,
		loader=ChoiceLoader(
			[PrefixLoader({"illumenate_lighting": FileSystemLoader(str(APP))}), FileSystemLoader(str(APP))]
		),
	)
	for name in dir(PRINTING):
		if name.startswith("ill_print"):
			env.globals[name] = getattr(PRINTING, name)
	env.globals["ill_invoice_payments"] = lambda doc: []
	env.globals["ill_sanitize_html"] = lambda text: text or ""
	env.globals["_"] = lambda text: text
	env.globals["frappe"] = Doc(
		utils=Doc(
			fmt_money=lambda value, currency=None, **kw: f"$ {float(value or 0):,.2f}",
			format_date=lambda value, *a: str(value),
			formatdate=lambda value, *a: str(value),
			date_diff=lambda a, b: 0,
			today=lambda: "2026-11-18",
		),
		db=Doc(get_value=lambda *a, **kw: None),
	)
	return env


def render(folder, doc):
	source = (FORMATS / folder / f"{folder}.html").read_text(encoding="utf-8")
	return environment().from_string(source).render(doc=doc)


TAPE = (
	"Configured LED Tape: ILL-CTN-00297\nPart Number: LED-HD-SW-I-27K-200-3M-WH-216.3-J(8E3F)\nCCT: 2700K\n"
	'Output Level: 200 lm/ft\nLength: 216.3" / 5494mm (requested: 219.0" / 5562mm)\nTotal Watts: 30.65W\n'
	"Environment: Dry\nPCB Mounting: N/A\nPCB Finish: N/A\nFeed Type: N/A\n\nBuild Description:\n"
	'LED Tape: LED-HD-SW-I-27K | Environment: Dry | CCT: 2700K | Lead Length: 24.0"'
)


def line(**values):
	base = dict(
		name="row1",
		idx=1,
		item_code="LED-HD-SW",
		item_name="LED Tape - 2700K",
		qty=792.0,
		uom="Inch",
		stock_uom="Inch",
		rate=0.51,
		amount=403.92,
		price_list_rate=0.85,
		discount_percentage=40.0,
		description=TAPE,
		ill_section_label="Kitchen",
		ill_fixture_type="A1",
	)
	base.update(values)
	return Doc(**base)


def sales_doc(**values):
	base = dict(
		name="DOC-0001",
		doctype="Quotation",
		docstatus=1,
		status="Open",
		company="ilLumenate Lighting",
		currency="USD",
		customer="Dealer Co",
		customer_name="Dealer Co",
		party_name="Dealer Co",
		transaction_date="2026-11-01",
		posting_date="2026-11-01",
		valid_till="2026-12-01",
		due_date="2026-12-01",
		items=[
			line(),
			line(
				name="row2",
				idx=2,
				item_code="PS-24V",
				item_name="Power Supply 24V",
				qty=2,
				uom="Ea",
				rate=72.0,
				amount=144.0,
				price_list_rate=120.0,
				description="",
				ill_section_label="",
				ill_fixture_type="",
			),
		],
		taxes=[Doc(description="FedEx Ground", charge_type="Actual", tax_amount=30.0)],
		total=547.92,
		grand_total=577.92,
		outstanding_amount=577.92,
		address_display="1 Main St<br>Tacoma, WA 98406<br>",
		contact_display="Pat Buyer",
		contact_email="pat@example.com",
		payment_schedule=[],
	)
	base.update(values)
	return Doc(**base)


class Helpers(unittest.TestCase):
	def test_specs_drop_internal_reference_build_dump_and_na_values(self):
		info = PRINTING.ill_print_specs(line())
		self.assertEqual(info["part_number"], "LED-HD-SW-I-27K-200-3M-WH-216.3-J(8E3F)")
		self.assertEqual(
			info["specs"],
			[
				("CCT", "2700K"),
				("Output", "200 lm/ft"),
				("Length", '216.3" / 5494mm'),
				("Watts", "30.65W"),
				("Environment", "Dry"),
			],
		)
		self.assertEqual(info["notes"], [])

	def test_specs_keep_plain_lines_but_not_ones_repeating_the_item(self):
		item = line(
			item_name="Power Supply-24V-200W",
			description="Non-Dimming Power Supply · PS-NON · Power Supply-24V-200W\nKit KIT-RA03 - Profile - 2000mm",
		)
		self.assertEqual(PRINTING.ill_print_specs(item)["notes"], ["Kit KIT-RA03 - Profile - 2000mm"])

	def test_specs_read_html_descriptions_and_skip_pipe_summaries(self):
		item = line(
			description='<div class="ql-editor"><p>non-pnc | 154.3" | RGB | White</p><p>Finish: White</p></div>'
		)
		info = PRINTING.ill_print_specs(item)
		self.assertEqual(info["specs"], [("Finish", "White")])
		self.assertEqual(info["notes"], [])

	def test_sections_follow_header_rows_merge_case_and_total(self):
		items = [
			line(name="h", item_code="", qty=0, ill_section_label="Kitchen", amount=0),
			line(name="a", ill_section_label="", amount=10.0),
			line(name="b", ill_section_label="Bath", amount=5.0),
			line(name="c", ill_section_label="KITCHEN", amount=2.0),
		]
		sections = PRINTING.ill_print_sections(items)
		self.assertEqual([s["label"] for s in sections], ["Kitchen", "Bath"])
		self.assertEqual([i.name for i in sections[0]["items"]], ["a", "c"])
		self.assertEqual(sections[0]["subtotal"], 12.0)

	def test_msrp_is_list_rate_but_never_below_the_selling_rate(self):
		self.assertEqual(PRINTING.ill_print_msrp(line()), 0.85)
		self.assertEqual(PRINTING.ill_print_msrp(line(price_list_rate=0, rate_with_margin=0, rate=9.0)), 9.0)
		self.assertEqual(PRINTING.ill_print_msrp(line(price_list_rate=5.0, rate=7.5)), 7.5)

	def test_discount_and_pricing_columns(self):
		self.assertEqual(PRINTING.ill_print_discount(line()), 40.0)
		self.assertEqual(
			PRINTING.ill_print_discount(line(discount_percentage=0, price_list_rate=100, rate=55)), 45.0
		)
		self.assertFalse(
			PRINTING.ill_print_pricing([line(discount_percentage=0, price_list_rate=0.51)])["has_discount"]
		)

	def test_totals_skip_zero_charges_and_label_rates_once(self):
		doc = sales_doc(
			discount_amount=10.0,
			additional_discount_percentage=5,
			taxes=[
				Doc(description="Shipping", charge_type="Actual", tax_amount=0),
				Doc(description="WA Sales Tax", charge_type="On Net Total", rate=10.1, tax_amount=5.0),
				Doc(description="ST 6% @ 6.0", charge_type="On Net Total", rate=6.0, tax_amount=3.0),
			],
		)
		rows = PRINTING.ill_print_totals(doc)["rows"]
		self.assertEqual(
			[r[0] for r in rows], ["Subtotal", "Discount (5%)", "WA Sales Tax (10.1%)", "ST 6% @ 6.0"]
		)
		self.assertEqual(rows[1][1], -10.0)

	def test_terms_prefer_the_document_then_the_default_record(self):
		self.assertEqual(PRINTING.ill_print_terms(Doc(terms="<p>Own</p>")), "<p>Own</p>")
		FRAPPE.db.exists.return_value = True
		FRAPPE.db.get_value.return_value = "<p>One</p><p>Two two</p><p>Three</p>"
		try:
			columns = PRINTING.ill_print_terms_columns(Doc(terms="<p></p>"), "sales")
		finally:
			FRAPPE.db.exists.return_value = False
			FRAPPE.db.get_value.return_value = None
		self.assertEqual(columns, ["<p>One</p><p>Two two</p>", "<p>Three</p>"])

	def test_small_formatters(self):
		self.assertEqual(PRINTING.ill_print_qty(792.0, "Inch"), "792 in")
		self.assertEqual(PRINTING.ill_print_qty(1.5, "Foot"), "1.5 ft")
		self.assertEqual(PRINTING.ill_print_qty(20, "6.56ft Piece"), "20 6.56ft Piece")
		self.assertEqual(PRINTING.ill_print_warehouse("Finished Goods - ilL"), "Finished Goods")
		self.assertEqual(PRINTING.ill_print_note("Install <left>\nA: 1 | B: 2 | C: 3"), "Install <left>")
		self.assertEqual(
			PRINTING.ill_print_address("1 Main St<br>\nTacoma, WA<br>"), ["1 Main St", "Tacoma, WA"]
		)

	def test_helpers_never_raise(self):
		broken = Doc(items="not a list", description=object())
		self.assertEqual(PRINTING.ill_print_specs(broken)["specs"], [])
		self.assertEqual(PRINTING.ill_print_build(Doc(description=None))["cuts"]["rows"], [])
		self.assertEqual(PRINTING.ill_print_schedule(Doc(lines=None))["sections"], [])


SAMPLES = {
	"ill_quotation": lambda: sales_doc(),
	"ill_quotation_msrp": lambda: sales_doc(),
	"ill_sales_order": lambda: sales_doc(
		doctype="Sales Order", status="On Hold", po_no="PO-77", advance_paid=100.0
	),
	"ill_sales_order_msrp": lambda: sales_doc(doctype="Sales Order", status="To Deliver and Bill"),
	"ill_sales_invoice": lambda: sales_doc(doctype="Sales Invoice", outstanding_amount=0, status="Paid"),
	"ill_delivery_note": lambda: sales_doc(
		doctype="Delivery Note",
		vehicle_no="1Z999",
		packed_items=[
			Doc(parent_detail_docname="row1", item_code="CH-1", item_name="Profile", qty=3, uom="Ea")
		],
	),
	"ill_packing_list": lambda: Doc(
		name="PS-1",
		docstatus=1,
		delivery_note="DN-1",
		from_case_no=1,
		to_case_no=2,
		items=[line(stock_uom="Ea")],
	),
	"ill_pick_list": lambda: Doc(
		name="PL-1",
		docstatus=1,
		purpose="Delivery",
		customer_name="Dealer Co",
		locations=[line(warehouse="Stores - ilL", sales_order="SO-1", picked_qty=0)],
	),
	"ill_payment_receipt": lambda: Doc(
		name="PE-1",
		docstatus=1,
		payment_type="Receive",
		party_name="Dealer Co",
		received_amount=577.92,
		paid_to_account_currency="USD",
		reference_no="QBO-2112",
		posting_date="2026-11-02",
		references=[
			Doc(
				reference_doctype="Sales Invoice",
				reference_name="SINV-1",
				total_amount=577.92,
				allocated_amount=577.92,
			)
		],
	),
	"ill_purchase_order": lambda: sales_doc(
		doctype="Purchase Order", supplier="Vendor Co", supplier_name="Vendor Co", ill_vendor_order_no="ACK-5"
	),
	"ill_request_for_quotation": lambda: Doc(
		name="RFQ-1",
		docstatus=1,
		transaction_date="2026-11-01",
		suppliers=[Doc(supplier="Vendor Co", supplier_name="Vendor Co", email_id="v@example.com")],
		items=[line()],
		message_for_supplier="Please quote.",
	),
	"ill_receiving_report": lambda: Doc(
		name="PR-1",
		docstatus=1,
		supplier_name="Vendor Co",
		posting_date="2026-11-01",
		total_qty=10,
		items=[line(purchase_order="PO-1", received_qty=10, qty=8, rejected_qty=2, warehouse="Stores - ilL")],
	),
	"ill_purchase_invoice": lambda: sales_doc(
		doctype="Purchase Invoice",
		supplier_name="Vendor Co",
		bill_no="INV-9",
		remarks="Against Supplier Invoice INV-9",
	),
	"ill_material_request": lambda: Doc(
		name="MR-1",
		docstatus=1,
		status="Pending",
		material_request_type="Manufacture",
		items=[line(warehouse="Stores - ilL", sales_order="SO-1", actual_qty=0)],
	),
	"ill_work_order_traveler": lambda: Doc(
		name="WO-1",
		docstatus=1,
		status="In Process",
		production_item="LED-HD-SW",
		item_name="LED Tape",
		qty=1,
		stock_uom="Ea",
		description=TAPE,
		sales_order=None,
		required_items=[
			Doc(
				item_code="TAPE",
				item_name="Tape reel",
				required_qty=216,
				stock_uom="Inch",
				source_warehouse="Stores - ilL",
			)
		],
	),
	"ill_fixture_schedule": lambda: Doc(
		name="SCHED-1",
		schedule_name="Main Schedule",
		version=2,
		status="DRAFT",
		lines=[
			Doc(
				line_id="A1",
				qty=4,
				location="Kitchen",
				manufacturer_type="OTHER",
				manufacturer_name="Acme",
				fixture_model_number="DL-4",
				watts_each=9.0,
				notes="Trim to match",
			)
		],
	),
}


class Formats(unittest.TestCase):
	def test_every_format_folder_has_a_matching_record_and_sample(self):
		folders = sorted(p.name for p in FORMATS.iterdir() if p.is_dir() and not p.name.startswith("__"))
		self.assertEqual(folders, sorted(SAMPLES))
		for folder in folders:
			record = json.loads((FORMATS / folder / f"{folder}.json").read_text(encoding="utf-8"))
			self.assertEqual(record["module"], "ilLumenate Lighting", folder)
			self.assertEqual(record["custom_format"], 1, folder)
			self.assertEqual(record["name"].lower().replace(" - ", "_").replace(" ", "_"), folder, folder)

	def test_every_format_renders_completely_in_the_sandbox(self):
		for folder, sample in SAMPLES.items():
			with self.subTest(folder=folder):
				html = render(folder, sample())
				self.assertNotIn("{{", html)
				self.assertNotIn("{%", html)
				self.assertIn('class="ill-doc"', html)
				self.assertIn("ill-title", html)

	def test_templates_follow_the_sandbox_rules(self):
		for path in [*FORMATS.glob("*/*.html"), APP / "templates/print/ill_print.html"]:
			source = path.read_text(encoding="utf-8")
			with self.subTest(path=path.name):
				self.assertNotRegex(source, r"set\s+_\s*=")
				self.assertNotIn("frappe.get_doc", source)
				# An inline "x if y" with no else prints DebugUndefined text in Frappe.
				for expression in re.findall(r"\{\{(.*?)\}\}", source, re.S):
					if re.search(r"\sif\s", expression):
						self.assertRegex(expression, r"\selse\s", expression.strip()[:80])

	def test_dealer_formats_show_discounts_and_msrp_formats_do_not(self):
		dealer = render("ill_quotation", sales_doc())
		self.assertIn(">Disc<", dealer)
		self.assertIn("$ 0.51", dealer)
		retail = render("ill_quotation_msrp", sales_doc())
		self.assertNotIn(">Disc<", retail)
		self.assertNotIn("$ 0.51", retail)
		self.assertNotIn("FedEx", retail)
		self.assertIn("$ 0.85", retail)
		self.assertIn("Total (MSRP)", retail)

	def test_shipping_and_shop_documents_carry_no_prices(self):
		for folder in (
			"ill_delivery_note",
			"ill_packing_list",
			"ill_pick_list",
			"ill_receiving_report",
			"ill_material_request",
			"ill_work_order_traveler",
			"ill_fixture_schedule",
		):
			with self.subTest(folder=folder):
				self.assertNotIn("$ ", render(folder, SAMPLES[folder]()))

	def test_delivery_note_lists_tracking_order_and_kit_contents(self):
		html = render("ill_delivery_note", SAMPLES["ill_delivery_note"]())
		self.assertIn("Packing Slip", html)
		self.assertIn("1Z999", html)
		self.assertIn("Includes 3 ea", html)

	def test_internal_build_text_stays_off_customer_documents(self):
		html = render("ill_quotation", sales_doc())
		self.assertNotIn("ILL-CTN-00297", html)
		self.assertNotIn("Build Description", html)
		self.assertIn("LED-HD-SW-I-27K-200-3M-WH-216.3-J(8E3F)", html)

	def test_work_order_traveler_keeps_the_build_description(self):
		html = render("ill_work_order_traveler", SAMPLES["ill_work_order_traveler"]())
		self.assertIn("Lead Length: 24.0", html)


class Seeds(unittest.TestCase):
	def test_terms_records_and_default_formats_line_up(self):
		spec = importlib.util.spec_from_file_location("isolated_terms", MODULE / "print_terms.py")
		terms = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(terms)
		self.assertEqual(set(terms.RECORDS), set(PRINTING.TERMS.values()))
		source = (APP / "patches/seed_print_terms.py").read_text(encoding="utf-8")
		names = {json.loads(p.read_text(encoding="utf-8"))["name"] for p in FORMATS.glob("*/*.json")}
		for name in re.findall(r'": "(ilL [^"]+)"', source):
			self.assertIn(name, names)
		self.assertIn("illumenate_lighting.patches.seed_print_terms", (APP / "patches.txt").read_text())

	def test_print_helpers_are_registered_as_jinja_methods(self):
		hooks = (APP / "hooks.py").read_text(encoding="utf-8")
		for name in dir(PRINTING):
			if name.startswith("ill_print_"):
				self.assertIn(f"illumenate_lighting.illumenate_lighting.printing.{name}", hooks, name)


if __name__ == "__main__":
	unittest.main()
