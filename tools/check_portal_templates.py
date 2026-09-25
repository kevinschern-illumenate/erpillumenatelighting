"""Local Jinja rendering and embedded-JS syntax checks; no Frappe/browser claims."""

import html
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/b2b-test-python"))

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, StrictUndefined

environment = Environment(
	loader=ChoiceLoader(
		[
			DictLoader(
				{
					"templates/web.html": "<!doctype html><html><body>{% block page_content %}{% endblock %}{% block script %}{% endblock %}</body></html>"
				}
			),
			FileSystemLoader(ROOT / "illumenate_lighting"),
			FileSystemLoader(ROOT),
		]
	),
	autoescape=True,
	undefined=StrictUndefined,
	extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"],
)
environment.globals.update(
	{
		"_": lambda value: value,
		"frappe": SimpleNamespace(
			format_value=lambda value, options: f"{options.get('options', '')} {value:,.2f}",
			utils=SimpleNamespace(
				sanitize_html=lambda value: html.escape(value), format_date=lambda value: str(value)
			),
		),
	}
)
parsed = 0
for path in (ROOT / "illumenate_lighting/templates").rglob("*.html"):
	environment.parse(path.read_text(encoding="utf8"))
	parsed += 1

offer = {
	"name": "OFFER-00001",
	"quotation": "Q-00001",
	"state": "ISSUED",
	"valid_until": "2026-10-01",
	"snapshot_hash": "a" * 64,
	"pdf_url": "/private/files/offer.pdf",
	"sales_order": None,
	"response_note": None,
	"unavailable_reason": None,
	"can_respond": True,
	"snapshot": {
		"currency": "USD",
		"grand_total": 240.0,
		"terms": "<script>unsafe()</script>",
		"taxes": [],
		"exclusions": [{"designation": "L2", "reason": "Other manufacturer specification"}],
		"items": [
			{
				"item_code": "SKU1",
				"item_name": "Fixture <img src=x onerror=unsafe()>",
				"ill_fixture_type": "L1",
				"additional_notes": "Buyer note",
				"qty": 2,
				"uom": "Nos",
				"rate": 120.0,
				"amount": 240.0,
			}
		],
	},
}
detail = environment.get_template("templates/pages/quote_detail.html")
rendered = detail.render(offer=offer)
assert '<form id="offer-response"' in rendered
assert "&lt;img" in rendered and "<img src=x" not in rendered
assert "<script>unsafe()" not in rendered
offer["can_respond"] = False
assert '<form id="offer-response"' not in detail.render(offer=offer)
listing = environment.get_template("templates/pages/quotes.html")
assert "OFFER-00001" in listing.render(
	offers=[offer], next_cursor="OFFER-00001", requests=[], requests_page=1, more_requests=False
)
assert "No issued quotations" in listing.render(
	offers=[], next_cursor=None, requests=[], requests_page=1, more_requests=False
)

from html.parser import HTMLParser


class Scripts(HTMLParser):
	def __init__(self):
		super().__init__()
		self.in_script = False
		self.sources = []

	def handle_starttag(self, tag, attrs):
		if tag == "script":
			self.in_script = True
			self.sources.append("")

	def handle_endtag(self, tag):
		if tag == "script":
			self.in_script = False

	def handle_data(self, data):
		if self.in_script:
			self.sources[-1] += data


parser = Scripts()
parser.feed(rendered)
account_context = {
	"user_profile": {
		key: "Value <img src=x onerror=alert(1)>"
		for key in ("first_name", "last_name", "full_name", "email", "phone", "job_title")
	},
	"customer": None,
	"portal_settings": {
		key: True
		for key in (
			"notify_orders",
			"notify_quotes",
			"notify_drawings",
			"notify_shipping",
			"notify_marketing",
		)
	},
}
account_context["user_profile"]["user_image"] = None
account_html = environment.get_template("templates/pages/account.html").render(**account_context)
assert "<img src=x onerror=alert(1)>" not in account_html
parser.feed(account_html)
parser.feed(environment.get_template("templates/pages/accept_invitation.html").render())
parser.feed(environment.get_template("templates/pages/products_catalog.html").render())


# Render the commercial branches as actual HTML, including dictionary child rows.
class View(dict):
	def __getattr__(self, key):
		return self.get(key)


order_view = View(
	name="SO-001",
	customer_name="Buyer <script>bad()</script>",
	docstatus=1,
	status="Partially shipped",
	erp_status="To Deliver",
	is_request=False,
	is_cancelled=False,
	transaction_date="2026-09-25",
	requested_date="2026-10-20",
	confirmed_date=None,
	po_no="PO1",
	grand_total=100,
	total=100,
	currency="USD",
	per_delivered=50,
	per_billed=0,
	production=None,
	progress_percent=50,
	total_qty=2,
	portal_status="partially_shipped",
	portal_status_class="info",
	portal_status_label="Partially shipped",
	revision_hash="revision",
)
intake_view = View(
	name="OI1",
	state="CHANGES_PROPOSED",
	can_acknowledge=True,
	can_withdraw=True,
	original=View(items=[], grand_total=90, currency="USD", terms="Original terms"),
	current=View(grand_total=100, currency="USD", terms="Current terms"),
	revision_hash="revision",
)
order_html = environment.get_template("templates/pages/order_detail.html").render(
	order=order_view,
	intake=intake_view,
	intake_files=[],
	change_requests=[],
	items=[
		View(
			item_code="ITEM",
			item_name="Light",
			qty=2,
			rate=50,
			amount=100,
			produced_qty=1,
			delivered_qty=1,
			planning_path="manufacturing",
			open_qty=1,
			uom="Nos",
		)
	],
	deliveries=[
		View(
			name="DN1",
			posting_date="2026-09-25",
			is_return=True,
			items=[View(item_name="Light", qty=-1, uom="Nos", line="ROW1")],
		)
	],
	invoices=[
		View(
			name="INV1",
			posting_date="2026-09-25",
			status="Unpaid",
			due_date=None,
			grand_total=100,
			outstanding_amount=100,
			currency="USD",
			is_return=False,
		)
	],
	actions=View(can_request_change=True, can_reorder=True, downloads=[]),
	schedule=None,
	timeline=[],
	download_url="/download",
	progress_percent=50,
)
assert "&lt;script&gt;" in order_html and "<script>bad()" not in order_html
assert "Not confirmed" in order_html and "Outstanding" in order_html and "ROW1" in order_html
parser.feed(order_html)
orders_html = environment.get_template("templates/pages/orders.html").render(
	orders=[order_view], page=2, has_more=True, search="PO1", filter="shipping"
)
assert "Newer orders" in orders_html and "Older orders" in orders_html
quote_request_html = environment.get_template("templates/pages/quote_request_detail.html").render(
	request=View(
		name="QR1",
		schedule="S1",
		requested_by="buyer",
		state="REQUESTED",
		due_date=None,
		files=[],
		snapshot=View(requested_date=None, contact="Buyer", notes="Need <script>bad()</script>", lines=[]),
	)
)
assert "<script>bad()" not in quote_request_html

render_dir = ROOT / "tests/portal_ui/rendered"
render_dir.mkdir(exist_ok=True)
configurator = environment.get_template("templates/pages/configure.html")
for category in ("Linear Fixture", "LED Tape", "LED Neon", "LED Sheet"):
	context = dict(
		product_category=category,
		is_led_sheet=category == "LED Sheet",
		is_tape_neon=category in {"LED Tape", "LED Neon"},
		is_tape=category == "LED Tape",
		is_neon=category == "LED Neon",
		has_templates=True,
		templates=[],
		led_sheet_templates=[],
		selected_template=None,
		has_quiz_handoff=False,
		quiz_handoff_json="{}",
		schedule=None,
		schedule_name="",
		project_name="",
		line_idx=None,
		can_save=False,
		show_pricing=True,
		is_system_manager=True,
		configurator_mode="coordinator",
		title="Configure " + category,
		existing_configured_sheet=None,
		product_slug="",
	)
	for mode in ["coordinator", "wizard"] if category == "Linear Fixture" else ["coordinator"]:
		context["configurator_mode"] = mode
		output = configurator.render(**context)
		parser.feed(output)
		(render_dir / (category.replace(" ", "-") + "-" + mode + ".html")).write_text(output, encoding="utf8")
with tempfile.TemporaryDirectory(prefix="portal-template-", dir=ROOT / ".tools") as directory:
	for index, source in enumerate(parser.sources):
		path = Path(directory) / f"script-{index}.js"
		path.write_text(source, encoding="utf8")
		subprocess.run(["node", "--check", str(path)], check=True)
print(
	f"Parsed {parsed} Jinja templates; rendered quotes and five configurator modes; checked {len(parser.sources)} embedded scripts"
)

shipment = SimpleNamespace(
	name="DN-QA",
	posting_date="2026-09-25",
	is_return=0,
	docstatus=1,
	customer_name="Test buyer",
	shipping_address="1 Test Way",
	items=[
		SimpleNamespace(
			ill_section_label="Lobby",
			ill_fixture_type="L1",
			item_name="Group",
			item_code="GROUP",
			description="Three independent members",
			additional_notes="Install <left>\nKeep leads distinct",
			qty=2,
			uom="Nos",
			against_sales_order="SO-QA",
		)
	],
)
delivery_print = environment.get_template("templates/print_formats/delivery_note.html").render(doc=shipment)
assert delivery_print.count("Install &lt;left&gt;") == 1
assert (
	delivery_print.index("L1")
	< delivery_print.index("Three independent members")
	< delivery_print.index("Install &lt;left&gt;")
)
assert "Lobby" in delivery_print and "SO-QA" in delivery_print
print("Rendered unpriced Delivery Note with designation, room and escaped notes")
