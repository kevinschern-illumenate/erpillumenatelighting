"""Local Jinja rendering and embedded-JS syntax checks; no Frappe/browser claims."""

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/b2b-test-python"))

from jinja2 import (
	ChainableUndefined,
	ChoiceLoader,
	DictLoader,
	Environment,
	FileSystemLoader,
	StrictUndefined,
	nodes,
)
from markupsafe import Markup

environment = Environment(
	loader=ChoiceLoader(
		[
			DictLoader(
				{
					"templates/web.html": "<!doctype html><html><head>{% block head_include %}{% endblock %}</head><body>{% block page_content %}{% endblock %}{% block script %}{% endblock %}</body></html>"
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
		"ill_can_view_catalog": lambda: True,
		"ill_finder_enabled": lambda: True,
		"ill_sanitize_html": lambda value: html.escape(value or ""),
		"include_script": lambda path: Markup(f'<script src="/assets/illumenate_lighting/dist/js/{path}"></script>'),
		"frappe": SimpleNamespace(
			format_value=lambda value, options: f"{options.get('options', '')} {value:,.2f}",
			utils=SimpleNamespace(
				sanitize_html=lambda value: html.escape(value), format_date=lambda value: str(value)
			),
		),
	}
)
# Inline event handlers must never interpolate template values: the browser HTML-decodes the attribute
# before running it, so `| e` cannot stop a quote in a name from breaking out of a JS string.
INLINE_HANDLER = re.compile(r"""(?<![\w-])on[a-z]+\s*=\s*("[^"]*\{\{|'[^']*\{\{)""", re.IGNORECASE)


def inline_handler_violations(source):
	return [source.count("\n", 0, match.start()) + 1 for match in INLINE_HANDLER.finditer(source)]


assert inline_handler_violations("""<button onclick="go('{{ doc.name | e }}')">""") == [1]
assert inline_handler_violations("""<a\nonmouseover='x({{ i }})'>""") == [2]
assert not inline_handler_violations("""<div data-content="{{ x }}" data-project="{{ doc.name | e }}">""")
assert not inline_handler_violations("""<button onclick="go()">{{ _('Go') }}</button>""")

parsed = 0
handler_violations = []
# UI-2: page templates keep no long <style> blocks and no hard-coded colours. Print documents
# rendered to PDF on their own (no portal stylesheet) live in templates/print and are exempt.
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL)
HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
style_violations = []


def page_style_violations(name, source):
	found = []
	for block in STYLE_BLOCK.finditer(source):
		lines = block.group(1).strip("\n").count("\n") + 1
		if lines > 20:
			found.append(f"{name}:{source.count(chr(10), 0, block.start()) + 1}: <style> block of {lines} lines")
	for colour in HEX_COLOUR.finditer(source):
		found.append(f"{name}:{source.count(chr(10), 0, colour.start()) + 1}: hard-coded colour {colour.group(0)}")
	return found


assert page_style_violations("x", "<style>" + "a{}\n" * 21 + "</style>")
assert not page_style_violations("x", "<style>a{}\nb{}</style>")
assert page_style_violations("x", '<div style="color:#fff">')
assert not page_style_violations("x", '<a href="#addLineModal">')
# SEC-2: every template output is escaped (| e), JSON-encoded (| tojson), a number, a translation of a
# literal, a macro or sanitized HTML, or listed in tools/portal_raw_outputs.txt with why it is safe.
OUTPUT = re.compile(r"\{\{-?(.*?)-?\}\}", re.DOTALL)
MACRO = re.compile(r"\{%-?\s*macro\s+(\w+)")
ESCAPING_FILTERS = {"e", "escape", "forceescape", "tojson", "urlencode", "int", "float", "round", "length", "count", "abs"}
RAW_ALLOWLIST_FILE = ROOT / "tools/portal_raw_outputs.txt"
RAW_ALLOWLIST = {
	tuple(part.strip() for part in line.split("#", 1)[0].split(":", 1))
	for line in RAW_ALLOWLIST_FILE.read_text(encoding="utf8").splitlines()
	if line.split("#", 1)[0].strip()
}


def _constant(expr):
	if isinstance(expr, nodes.Const):
		return True
	if isinstance(expr, nodes.CondExpr):
		return _constant(expr.expr1) and (expr.expr2 is None or _constant(expr.expr2))
	return isinstance(expr, (nodes.Add, nodes.Sub, nodes.Mul, nodes.Div, nodes.FloorDiv, nodes.Mod, nodes.Compare))


def _escaped(expr, macros):
	if _constant(expr):
		return True
	if isinstance(expr, nodes.Filter):
		if expr.name in ESCAPING_FILTERS:
			return True
		inner = expr.node
		return (
			expr.name == "safe"
			and isinstance(inner, nodes.Call)
			and isinstance(inner.node, nodes.Name)
			and inner.node.name == "ill_sanitize_html"
		)
	if isinstance(expr, nodes.Call) and isinstance(expr.node, nodes.Name):
		name = expr.node.name
		if name in macros or name == "super":
			return True
		return name in ("_", "__") and all(isinstance(arg, nodes.Const) for arg in expr.args)
	return False


def unescaped_outputs(name, source):
	macros = set(MACRO.findall(source))
	found = []
	for match in OUTPUT.finditer(source):
		expression = match.group(1).strip()
		tree = environment.parse("{{ " + expression + " }}").body[0].nodes[0]
		if not _escaped(tree, macros) and (Path(name).as_posix(), expression) not in RAW_ALLOWLIST:
			found.append(f"{name}:{source.count(chr(10), 0, match.start()) + 1}: {{{{ {expression} }}}}")
	return found


assert unescaped_outputs("x", "<p>{{ doc.name }}</p><i>{{ _(doc.status) }}</i>") == [
	"x:1: {{ doc.name }}",
	"x:1: {{ _(doc.status) }}",
]
assert not unescaped_outputs(
	"x",
	"{% macro row(d) %}{% endmacro %}{{ doc.name | e }}{{ (a or b) | e }}{{ x | tojson }}{{ _('Hi') }}"
	"{{ row(doc) }}{{ page - 1 }}{{ 'a' if ok else 'b' }}{{ ill_sanitize_html(doc.notes) | safe }}",
)
assert unescaped_outputs("x", "{{ doc.notes | safe }}{{ a or b | e }}") == [
	"x:1: {{ doc.notes | safe }}",
	"x:1: {{ a or b | e }}",
]
# UI-7: every <label> names its control: for="<id>", a wrapped control, or an id that aria-labelledby
# points at (a caption for a group such as pills). Pill labels are clickable choices, not captions, and
# labels inside a <template> are cloned per segment, so ids would repeat; their controls carry aria-label.
LABEL = re.compile(r"<label\b([^>]*)>(.*?)</label>", re.DOTALL)
LABEL_CONTROL = re.compile(r"<(?:input|select|textarea)\b")
TEMPLATE_BLOCK = re.compile(r"<template\b.*?</template>", re.DOTALL)
label_violations = []


def unlabelled_labels(name, source):
	templates = [(block.start(), block.end()) for block in TEMPLATE_BLOCK.finditer(source)]
	labelledby = set(" ".join(re.findall(r"""aria-labelledby=["']([^"']+)""", source)).split())
	found = []
	for label in LABEL.finditer(source):
		attrs = label.group(1)
		label_id = re.search(r"""\bid=["']([^"']+)""", attrs)
		if (
			re.search(r"\bfor=", attrs)
			or LABEL_CONTROL.search(label.group(2))
			or (label_id and label_id.group(1) in labelledby)
			or "pill-option" in attrs
			or any(start <= label.start() < end for start, end in templates)
		):
			continue
		found.append(f"{name}:{source.count(chr(10), 0, label.start()) + 1}: <label{attrs}>")
	return found


assert unlabelled_labels("x", "<label>Name</label><input name='n'>") == ["x:1: <label>"]
assert not unlabelled_labels(
	"x",
	'<label for="n">Name</label><label><input type="checkbox"> Yes</label>'
	'<label id="t">Type</label><div role="radiogroup" aria-labelledby="t"></div>'
	"<template><label>Start</label></template>",
)
unescaped = []
for path in (ROOT / "illumenate_lighting/templates").rglob("*.html"):
	source = path.read_text(encoding="utf8")
	environment.parse(source)
	parsed += 1
	if path.parent.name in ("pages", "includes", "print"):
		unescaped += unescaped_outputs(path.relative_to(ROOT / "illumenate_lighting"), source)
	if path.parent.name in ("pages", "includes"):
		label_violations += unlabelled_labels(path.relative_to(ROOT), source)
	handler_violations += [f"{path.relative_to(ROOT)}:{line}" for line in inline_handler_violations(source)]
	if path.parent.name == "pages":
		style_violations += page_style_violations(path.relative_to(ROOT), source)
if style_violations:
	sys.exit(
		"Page styles belong in public/css/pages/_<page>.scss and colours in --ill-* tokens (UI-2):\n  "
		+ "\n  ".join(style_violations)
	)
if unescaped:
	sys.exit(
		"Escape template outputs with | e (| tojson in scripts), or list them in "
		"tools/portal_raw_outputs.txt with why they are safe (SEC-2):\n  " + "\n  ".join(unescaped)
	)
if label_violations:
	sys.exit(
		'Point each <label> at its control with for="<id>" (add the id), or wrap the control (UI-7):\n  '
		+ "\n  ".join(label_violations)
	)
if handler_violations:
	sys.exit(
		"Inline event handlers interpolate template values (use data attributes and a delegated listener):\n  "
		+ "\n  ".join(handler_violations)
	)

offer = {
	"name": "OFFER-00001",
	"quotation": "Q-00001",
	"state": "ISSUED",
	"valid_until": "2026-10-01",
	"snapshot_hash": "a" * 64,
	"pdf_url": "/private/files/offer.pdf",
	"sales_order": None,
	"quote_request": "QR-00001",
	"project_name": "Lobby <b>",
	"schedule_name": "Level 1",
	"status_label": "Awaiting your response",
	"status_class": "warning",
	"grand_total": 240.0,
	"currency": "USD",
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
assert 'data-parent-type="ilL-Quote-Request" data-parent-name="QR-00001"' in rendered
assert 'ill-status--warning">Awaiting your response' in rendered and "Next step" in rendered
assert 'href="/portal/quotes" aria-current="page"' in detail.render(offer=offer, path="portal/quotes/OFFER-00001")
offer["can_respond"] = False
assert '<form id="offer-response"' not in detail.render(offer=offer)
listing = environment.get_template("templates/pages/quotes.html")
assert "OFFER-00001" in listing.render(
	offers=[offer], next_cursor="OFFER-00001", requests=[], requests_page=1, more_requests=False
)
assert "No issued quotations" in listing.render(
	offers=[], next_cursor=None, requests=[], requests_page=1, more_requests=False
)
filtered = listing.render(
	offers=[offer],
	next_cursor="OFFER-00001",
	requests=[dict(name="QR-1", schedule="S1", schedule_name="Level 1", state="INFORMATION_NEEDED", status_label="Needs your reply", status_class="warning")],
	requests_page=1,
	more_requests=False,
	status="open",
	search="lobby",
	request_status="action",
)
assert "Lobby &lt;b&gt;" in filtered and "Needs your reply" in filtered and "status=open&amp;search=lobby" in filtered
assert "No quotes match" in listing.render(
	offers=[], next_cursor=None, requests=[], requests_page=1, more_requests=False, status="open", search="", request_status="open"
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
accept_page = environment.get_template("templates/pages/accept_invitation.html")
parser.feed(accept_page.render(signed_in_as=None, signup_enabled=False))
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
	lines=[
		View(item_code="ITEM", qty=3, uom="Nos", rate=50, amount=150, status="changed", changed=["qty", "amount"], was=View(qty=2, rate=50)),
		View(item_code="NEW", qty=1, uom="Nos", rate=10, amount=10, status="added", changed=[], was=None),
		View(item_code="OLD", qty=1, uom="Nos", rate=5, amount=5, status="removed", changed=[], was=None),
	],
	lines_changed=True,
	revision_hash="revision",
	next_step=View(buyer=True, text="Acknowledge <this> revision"),
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
assert "Next step" in order_html and "Acknowledge &lt;this&gt; revision" in order_html
parser.feed(order_html)
orders_html = environment.get_template("templates/pages/orders.html").render(
	orders=[order_view], page=2, has_more=True, search="PO1", filter="shipping"
)
assert "Newer orders" in orders_html and "Older orders" in orders_html
assert 'class="ill-record"' in orders_html and "No orders match" not in orders_html
quote_request_html = environment.get_template("templates/pages/quote_request_detail.html").render(
	request=View(
		name="QR1",
		schedule="S1",
		requested_by="buyer",
		state="INFORMATION_NEEDED",
		status_label="Needs your reply",
		status_class="warning",
		due_date=None,
		files=[],
		snapshot=View(requested_date=None, contact="Buyer", notes="Need <script>bad()</script>", lines=[]),
	)
)
assert "<script>bad()" not in quote_request_html
assert "Needs your reply" in quote_request_html and "ilLumenate needs more information" in quote_request_html

render_dir = ROOT / "tests/portal_ui/rendered"
render_dir.mkdir(exist_ok=True)
(render_dir / "quote-detail.html").write_text(rendered, encoding="utf8")
projects_page = environment.get_template("templates/pages/ill_projects.html")


def project_rows(can_edit):
	return [
		View(
			name=name,
			project_name=label,
			customer="Buyer",
			company_name="Acme <Lighting>",
			is_private=private,
			status=status,
			schedule_count=count,
			last_activity="2026-10-01",
			next_step={"label": step, "tone": "warning"},
			can_edit=can_edit,
		)
		for name, label, status, private, count, step in (
			("P-1');alert(1);//", "x');alert(2);//<b>", "ACTIVE", 0, 2, "Quote ready"),
			('P-2";alert(3);//', 'y");alert(4);//', "ARCHIVED", 1, 0, "Add a schedule"),
		)
	]


hostile_projects = projects_page.render(
	projects=project_rows(True), page=1, has_more=False, status_filter="all", sort="recent", search=""
)
assert "alert(2);//&lt;b&gt;" in hostile_projects and "onclick" not in hostile_projects
assert "Acme &lt;Lighting&gt;" in hostile_projects
parser.feed(hostile_projects)
(render_dir / "projects-hostile.html").write_text(hostile_projects, encoding="utf8")
readonly_projects = projects_page.render(
	projects=project_rows(False), page=2, has_more=True, status_filter="active", sort="name", search="x&y"
)
parser.feed(readonly_projects)
(render_dir / "projects-readonly.html").write_text(readonly_projects, encoding="utf8")
collaborators_page = environment.get_template("templates/pages/collaborators.html").render(
	frappe=SimpleNamespace(
		get_doc=lambda doctype, name: View(full_name="Olivia Owner"),
		utils=SimpleNamespace(format_date=lambda value: str(value)),
	),
	project=View(
		name="P-1",
		project_name="Lobby <refit>",
		customer="Acme",
		owner="owner@acme.test",
		is_private=1,
		modified="2026-10-14 01:00:00",
	),
	collaborators=[
		View(
			user="architect@studio.test",
			full_name='Ada "<b>"',
			email="architect@studio.test",
			access_level="VIEW",
			is_active=1,
			added_on="2026-09-01",
		),
		View(
			user="former@studio.test",
			full_name="Former",
			email="former@studio.test",
			access_level="EDIT",
			is_active=0,
			added_on=None,
		),
	],
	available_users=[
		View(value="teammate@acme.test", label="Tess Mate (teammate@acme.test)"),
	],
	invitations=[
		View(
			name="INV-1",
			email="pending@studio.test",
			first_name="Pat",
			last_name="<Pending>",
			access_level="EDIT",
			expires_label="10-21-2026",
		)
	],
	can_manage=True,
)
assert "<b>" not in collaborators_page and "update_project_collaborators" not in collaborators_page
parser.feed(collaborators_page)
(render_dir / "collaborators.html").write_text(collaborators_page, encoding="utf8")
drawing_types = [
	View(
		name="Shop Drawing",
		label="Shop <Drawing>",
		icon="fa-wrench",
		description="Fabrication detail",
		show_project_field=1,
		show_fixture_field=1,
		show_priority_field=1,
		show_due_date_field=0,
		default_priority="Normal",
		fields=[],
	),
	View(
		name="Photometric Layout",
		label="Photometric Layout",
		icon="fa-lightbulb-o",
		description="Point-by-point layout",
		show_project_field=0,
		show_fixture_field=0,
		show_priority_field=0,
		show_due_date_field=1,
		default_priority=None,
		fields=[
			View(field_key="ceiling_height", label="Ceiling height", fieldtype="Float", mandatory=1, help_text="In feet"),
			View(field_key="target", label="Target", fieldtype="Select", options="Office\nRetail", mandatory=0),
			View(field_key="dimmed", label="Dimmed", fieldtype="Check", mandatory=1),
		],
	),
]
drawings_page = environment.get_template("templates/pages/drawings.html").render(
	request_types=drawing_types,
	projects=[View(name="P-1", project_name="Lobby <Refit>")],
	pending_requests=[],
	completed_requests=[],
	all_requests=[],
	pending_count=0,
	page=2,
	has_more=True,
	drawing_type_icon=lambda value: "file",
)
assert "Shop &lt;Drawing&gt;" in drawings_page and "Lobby &lt;Refit&gt;" in drawings_page
assert 'data-value="shop_drawing"' not in drawings_page, "request types come from Desk"
assert 'href="?page=1#all"' in drawings_page and 'href="?page=3#all"' in drawings_page, "REL-8 pager"
assert 'id="requestProjectSearch"' in drawings_page
parser.feed(drawings_page)
(render_dir / "drawings.html").write_text(drawings_page, encoding="utf8")
overview = environment.get_template("templates/pages/portal.html")
overview_context = {
	"greeting": "Good morning",
	"user_name": "Dana <D>",
	"customer_name": "Acme & Co",
	"recent_projects": [View(name="P-1", project_name="Lobby <Refit>", customer="Acme", status="ACTIVE")],
	"recent_orders": [],
	"finder_banner": None,
	"path": "portal",
	"project_status_label": lambda status: status.title(),
	"project_status_class": lambda status: "success",
}
overview_actions = [
	{"kind": "offer", "title": "Respond to quote <Q-1>", "context": "Lobby <Refit>", "due_label": "Expires in 3 days", "link": "/portal/quotes/Q-1", "tone": "warning"},
	{"kind": "schedule", "title": "Configure 2 lines in Main", "context": None, "due_label": None, "link": "/portal/schedules/S-1", "tone": "info"},
]
for name, actions in (("overview", overview_actions), ("overview-empty", [])):
	overview_html = overview.render(action_items=actions, **overview_context)
	assert not actions or "Respond to quote &lt;Q-1&gt;" in overview_html, "action text is escaped"
	assert ("all caught up" in overview_html) == (not actions)
	assert 'aria-current="page">Overview' in overview_html
	parser.feed(overview_html)
	(render_dir / f"{name}.html").write_text(overview_html, encoding="utf8")
# The schedule page has a large context; render its FLOW-2 header with lenient undefineds.
schedule_page = environment.overlay(undefined=ChainableUndefined).get_template("templates/pages/schedule.html")
schedule_base = {
	"project": View(name="P-1", project_name="Proj"),
	"lines": [],
	"lines_json": [],
	"can_edit": True,
	"schedule_status_class": lambda status: "info",
	"schedule_status_label": lambda status: status.title(),
	"schedule_status_description": lambda status: status,
	"status_labels": {},
	"status_classes": {"DRAFT": "secondary"},
	"export_statuses": {"COMPLETED": {"label": "Completed", "css": "success"}},
	"open_offer": None,
	"system_design": None,
	"design_dimming_protocols": [],
}
steps = ["build", "ready", "quote_requested", "quoted", "order_requested", "ordered"]
schedule_variants = {
	"schedule-ready": dict(
		schedule=View(name="S-1", schedule_name="Lobby", status="READY", version=1, modified="2026-10-14", is_locked=0),
		progress_steps=[
			{"key": key, "label": key, "state": ("done" if i < 1 else "current" if i == 1 else "upcoming"), "problem": False}
			for i, key in enumerate(steps)
		],
		commercial=View(
			requests=[
				View(
					name="QR-1",
					link="/portal/quote-requests/QR-1",
					status_class="info",
					status_label="Received",
					assigned_name="Sam <S>",
					last_message="Can you confirm <b>finish</b>?",
				)
			],
			offers=[],
			order=None,
		),
		next_step={"primary": {"label": "Request quote", "action": "quote"}, "secondary": {"label": "Order directly", "action": "order"}},
		unconfigured_lines=[],
	),
	"schedule-draft": dict(
		schedule=View(name="S-1", schedule_name="Lobby", status="DRAFT", version=1, modified="2026-10-14", is_locked=0),
		progress_steps=[
			{"key": key, "label": key, "state": "current" if i == 0 else "upcoming", "problem": False}
			for i, key in enumerate(steps)
		],
		commercial=View(requests=[], offers=[], order=None),
		next_step={
			"primary": {"label": "Mark ready", "action": "ready", "disabled_reason": "Configure these lines first: A1, Row 2"},
			"secondary": None,
		},
		unconfigured_lines=[("A1", "key-1"), ("Row 2", "key-2")],
	),
}
for name, variant in schedule_variants.items():
	schedule_html = schedule_page.render(**schedule_base, **variant)
	assert "Sam &lt;S&gt;" in schedule_html or name != "schedule-ready"
	assert 'onclick="requestQuote()"' not in schedule_html and 'onclick="createSalesOrder()"' not in schedule_html
	(render_dir / f"{name}.html").write_text(schedule_html, encoding="utf8")
# FLOW-9: the project page lists the latest version of each schedule, earlier ones folded.
project_page = environment.overlay(undefined=ChainableUndefined).get_template("templates/pages/project.html")


def schedule_version(name, version, parent=None):
	return View(
		name=name,
		schedule_name="Main <x>",
		status="DRAFT",
		version=version,
		is_locked=int((version < 3 and parent is not None) or name == "S-1"),
		version_parent=parent,
		lines_count=3,
	)


project_versions = project_page.render(
	project=View(name="P-1", project_name="Lobby"),
	schedules=[1],
	schedule_families=[
		View(latest=schedule_version("S-3", 3, "S-1"), earlier=[schedule_version("S-2", 2, "S-1"), schedule_version("S-1", 1)]),
		View(latest=schedule_version("S-9", 1), earlier=[]),
	],
	can_edit=True,
	schedule_status_class=lambda status: "info",
	schedule_status_label=lambda status: status.title(),
	project_status_class=lambda status: "success",
	project_status_label=lambda status: (status or "").title(),
)
assert "Main &lt;x&gt;" in project_versions
(render_dir / "project-versions.html").write_text(project_versions, encoding="utf8")
# FLOW-8 / REL-5 / FLOW-5: the create form for a dealer, for sales staff and for a user without a company,
# and the edit modal; all share one set of fields and one pair of party/contact modals.
project_party_options = {
	"end_client_party": [{"value": "PTY-1", "label": "Hotel <One>"}],
	"architect": [{"value": "PTY-2", "label": "Studio <A>"}],
	"lighting_designer": [],
	"general_contractor": [],
}
project_new_base = dict(
	is_new=True,
	project=None,
	needs_company=False,
	can_set_owner_company=False,
	dealer_companies=[],
	allowed_customers=[
		{"value": "ACME", "label": "Acme <Lighting>"},
		{"value": "CLIENT", "label": "Client Co"},
	],
	user_customer="ACME",
	owner_company_label="Acme <Lighting>",
	can_create_parties=True,
	# DESK-9: the end client and team pick from the dealer company's project parties.
	party_options=project_party_options,
)
project_new_variants = {
	"project-new-dealer": {},
	"project-new-staff": dict(
		can_set_owner_company=True,
		dealer_companies=[{"value": "ACME", "label": "Acme <Lighting>"}],
		user_customer=None,
		owner_company_label=None,
		party_options={},
	),
	"project-new-no-company": dict(
		needs_company=True,
		allowed_customers=[],
		user_customer=None,
		owner_company_label=None,
		can_create_parties=False,
		party_options={},
	),
}
for name, variant in project_new_variants.items():
	project_new = project_page.render(**{**project_new_base, **variant})
	assert "<Lighting>" not in project_new and "<One>" not in project_new
	assert "Hotel &lt;One&gt;" in project_new or name != "project-new-dealer"
	parser.feed(project_new)
	(render_dir / f"{name}.html").write_text(project_new, encoding="utf8")
project_edit_base = dict(
	schedules=[],
	schedule_families=[],
	can_edit=True,
	owner_company_label="Acme <Lighting>",
	contact_details={"project_manager": View(first_name="Pat", last_name="<Lee>")},
	party_labels={"architect": "Studio <A>"},
	party_options=project_party_options,
	can_create_parties=True,
	schedule_status_class=lambda status: "info",
	schedule_status_label=lambda status: status.title(),
	project_status_class=lambda status: "success",
	project_status_label=lambda status: (status or "").title(),
)
# A legacy project whose end client is a Customer other than the owner company: read-only end client.
project_edit = project_page.render(
	project=View(
		name="P-1",
		project_name="Lobby <b>",
		customer="CLIENT",
		owner_customer="ACME",
		architect="PTY-2",
		project_manager="CONT-1",
		location="Main St <1>",
		is_private=0,
		status="ACTIVE",
	),
	customer_label="Client <Co>",
	end_client_editable=False,
	**project_edit_base,
)
assert "Client &lt;Co&gt;" in project_edit and "Pat &lt;Lee&gt;" in project_edit
assert "Studio &lt;A&gt;" in project_edit and "<Lee>" not in project_edit and "<A>" not in project_edit
parser.feed(project_edit)
(render_dir / "project-edit.html").write_text(project_edit, encoding="utf8")
# DESK-9: a portal project bills the dealer company; its end client is a party the dealer can change.
project_edit_party = project_page.render(
	project=View(
		name="P-2",
		project_name="Hotel",
		customer="ACME",
		end_client_party="PTY-1",
		owner_customer="ACME",
		is_private=0,
		status="ACTIVE",
	),
	customer_label="Hotel <One>",
	end_client_editable=True,
	**{**project_edit_base, "party_labels": {"end_client_party": "Hotel <One>"}},
)
assert "Hotel &lt;One&gt;" in project_edit_party and "<One>" not in project_edit_party
parser.feed(project_edit_party)
(render_dir / "project-edit-party.html").write_text(project_edit_party, encoding="utf8")
dealer_access = environment.get_template("templates/pages/request_dealer_access.html")
dealer_access_variants = {
	"guest": dict(
		signed_in=False, state="apply", is_guest=True, prefill={}, application=None, claim_token="CLAIM"
	),
	"signed-in": dict(
		signed_in=True,
		state="apply",
		is_guest=False,
		prefill={"company": "Studio <x>", "full_name": 'Dana "D"', "email": "dana@studio.test", "phone": ""},
		application=None,
		claim_token=None,
	),
	"pending": dict(
		signed_in=True,
		state="pending",
		is_guest=False,
		prefill={},
		application=View(name="AR-<1>", state="Information needed"),
		claim_token=None,
	),
	"approved": dict(
		signed_in=True, state="approved", is_guest=False, prefill={}, application=None, claim_token=None
	),
}
for name, variant in dealer_access_variants.items():
	dealer_access_html = dealer_access.render(**variant)
	assert "<x>" not in dealer_access_html and "AR-<1>" not in dealer_access_html
	parser.feed(dealer_access_html)
	(render_dir / f"dealer-access-{name}.html").write_text(dealer_access_html, encoding="utf8")
for name, signed_in_as in (("guest", None), ("signed-in", "Invitee@Studio.test")):
	accept_html = accept_page.render(signed_in_as=signed_in_as, signup_enabled=True)
	(render_dir / f"accept-invitation-{name}.html").write_text(accept_html, encoding="utf8")
configurator = environment.get_template("templates/pages/configure.html")
for category in ("Linear Fixture", "LED Tape", "COB Tape", "LED Neon", "LED Sheet", "Driver", "Controller", "Extrusion Kit"):
	context = dict(
		product_category=category,
		is_led_sheet=category == "LED Sheet",
		is_tape_neon=category in {"LED Tape", "COB Tape", "LED Neon"},
		is_tape=category in {"LED Tape", "COB Tape"},
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
		configurator_mode="coordinator",
		title="Configure " + category,
		existing_configured_sheet=None,
		product_slug="",
		show_stock_qty=True,
		finder="TOKEN",
		driver_templates=[
			View(name="DRV-A", template_name="Slim <Driver>", image="/files/drv.jpg", gallery_json='[{"image": "/files/drv.jpg"}]', description="Class 2"),
			View(name="DRV-B", template_name="Wet Driver", image=None, gallery_json="[]", description=""),
		],
	)
	for mode in ["coordinator", "wizard"] if category == "Linear Fixture" else ["coordinator"]:
		context["configurator_mode"] = mode
		output = configurator.render(**context)
		parser.feed(output)
		(render_dir / (category.replace(" ", "-") + "-" + mode + ".html")).write_text(output, encoding="utf8")
prefilled = configurator.render(
	**{
		**context,
		"product_category": "Linear Fixture",
		"is_led_sheet": False,
		"is_tape_neon": False,
		"is_tape": False,
		"is_neon": False,
		"configurator_mode": "coordinator",
		"has_quiz_handoff": True,
		"quiz_prefill": {
			"applied": [{"field": "moisture", "answer": "Damp", "value": "Damp"}],
			"unmatched": [{"field": "finish", "answer": "<b>Gold</b>"}],
		},
	}
)
assert "pre-filled below" in prefilled and "Not offered on this product" in prefilled
assert "&lt;b&gt;Gold&lt;/b&gt;" in prefilled
nothing = configurator.render(
	**{
		**context,
		"has_quiz_handoff": True,
		"quiz_prefill": {"applied": [], "unmatched": [{"field": "cct", "answer": "5000K"}]},
	}
)
assert "nothing was pre-filled" in nothing and "5000K" in nothing
finder = environment.get_template("templates/pages/product_finder.html").render(title="Product Finder", session_token="T", claim_token=None, preview=False, csrf_token="csrf")
designer_template = environment.get_template("templates/pages/system_design.html")
designer = designer_template.render(
	assets="/assets/illumenate_lighting/system_designer/designer",
	asset_version=7,
	schedule_name="SCH </script><b>",
	mount_options={"schedule": "SCH </script><b>", "csrfToken": "csrf", "apiBase": "/api/method/x"},
)
assert 'import "/assets/illumenate_lighting/system_designer/designer.js?v=7";' in designer
assert "IllSystemDesigner.mount" in designer and "</script><b>" not in designer
assert "/portal/schedules/SCH%20%3C/script%3E%3Cb%3E" in designer
assert "Back to schedule" not in designer_template.render(
	assets="a", asset_version=0, schedule_name=None, mount_options={"schedule": None}
)
assert 'ill-finder.js' in finder
parser.feed(finder)
catalog_builder = environment.get_template("templates/pages/catalog_builder.html").render(
	assets="/assets/illumenate_lighting/catalog_builder/catalog-builder",
	asset_version=123,
	mount_options={
		"csrfToken": "csrf",
		"referenceUrl": "/api/reference",
		"user": "</script><script>bad()</script>",
	},
)
assert "catalog-builder.css?v=123" in catalog_builder and "catalog-builder.js?v=123" in catalog_builder
assert "IllCatalogBuilder.mount(" in catalog_builder and "<script>bad()" not in catalog_builder
assert "</body>" in catalog_builder
parser.feed(catalog_builder)
banner = environment.get_template("templates/includes/product_finder_banner.html").render(finder_banner=View(image=None, headline="Find <light>", text="Choose", cta="Start", resume=View(url="/portal/product-finder?session=T", percent=50)))
assert "Resume (50% done)" in banner and "Find &lt;light&gt;" in banner
(render_dir / "finder-banner.html").write_text(banner, encoding="utf8")
chooser = configurator.render(show_type_chooser=True, chooser_options=[View(value="Linear Fixture",label="Linear",featured=True,href="/portal/configure?category=Linear+Fixture&schedule=S&draft=D&finder=T"),View(value="Driver",label="Driver",featured=False,href="/portal/configure?category=Driver&schedule=S&draft=D&finder=T")])
parser.feed(chooser)
(render_dir / "finder-chooser.html").write_text(chooser, encoding="utf8")
# FLOW-6: a schedule editor without catalog access configures without any price UI.
for category, mode in (
	("Linear Fixture", "coordinator"),
	("Linear Fixture", "wizard"),
	("LED Tape", "coordinator"),
	("LED Sheet", "coordinator"),
	("Driver", "coordinator"),
	("Extrusion Kit", "coordinator"),
):
	unpriced = configurator.render(
		**{
			**context,
			"product_category": category,
			"is_led_sheet": category == "LED Sheet",
			"is_tape_neon": category == "LED Tape",
			"is_tape": category == "LED Tape",
			"is_neon": False,
			"configurator_mode": mode,
			"show_pricing": False,
			"show_stock_qty": False,
			"config_schedule": "SCH </script><b>",
			"schedule_name": "SCH </script><b>",
			"can_save": True,
		}
	)
	assert "</script><b>" not in unpriced, category
	assert 'id="pricingResults"' not in unpriced and "Fixture Price Breakdown" not in unpriced, category
	assert "config_schedule" in unpriced, category
	parser.feed(unpriced)
	unpriced_name = "unpriced-" + category.replace(" ", "-") + "-" + mode + ".html"
	(render_dir / unpriced_name).write_text(unpriced, encoding="utf8")
# FLOW-7: a Dealer's company ticket list names who raised each colleague's ticket.
support_page = environment.get_template("templates/pages/ill_support.html")
company_tickets = [
	View(name="ISS-1", subject="Mine", status="Open", creation="2026-10-01", raised_by_name=None),
	View(name="ISS-2", subject="Pat's <order>", status="Open", creation="2026-10-02", raised_by_name="Pat <Buyer>"),
]
support_html = support_page.render(
	tickets=company_tickets,
	ticket_page=View(total=2, page=1, page_size=20, company=True),
	recent_orders=[],
	recent_projects=[],
)
assert "Raised by Pat &lt;Buyer&gt;" in support_html and support_html.count("Raised by") == 1
assert "Pat's <order>" not in support_html
parser.feed(support_html)
(render_dir / "support-company.html").write_text(support_html, encoding="utf8")
# .tools/ is git-ignored, so a clean checkout (CI) does not have it yet.
(ROOT / ".tools").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="portal-template-", dir=ROOT / ".tools") as directory:
	for index, source in enumerate(parser.sources):
		path = Path(directory) / f"script-{index}.js"
		path.write_text(source, encoding="utf8")
		subprocess.run(["node", "--check", str(path)], check=True)
print(
	f"Parsed {parsed} Jinja templates; rendered quotes and nine configurator modes; checked {len(parser.sources)} embedded scripts"
)

class PrintDoc(SimpleNamespace):
	"""A Frappe Document as print formats see it: every field exists, empty or not."""

	def __getattr__(self, key):
		return None

	def get(self, key, default=None):
		return getattr(self, key, default)

	def get_formatted(self, key):
		return str(getattr(self, key))


shipment = PrintDoc(
	name="DN-QA",
	posting_date="2026-09-25",
	is_return=0,
	docstatus=1,
	customer_name="Test buyer",
	shipping_address="1 Test Way",
	vehicle_no="1Z999",
	total_qty=2,
	items=[
		PrintDoc(
			idx=1,
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
delivery_print = environment.get_template("illumenate_lighting/print_format/ill_delivery_note/ill_delivery_note.html").render(doc=shipment)
assert delivery_print.count("Install &lt;left&gt;") == 1
assert (
	delivery_print.index("L1")
	< delivery_print.index("Three independent members")
	< delivery_print.index("Install &lt;left&gt;")
)
assert "Lobby" in delivery_print and "SO-QA" in delivery_print and "1Z999" in delivery_print
assert "Rate" not in delivery_print
print("Rendered unpriced Delivery Note with designation, room and escaped notes")

# UI-6: the configurator ships only to the pages that use it.
WEB_JS = ROOT / "illumenate_lighting/public/js"
assert "configurator/" not in (WEB_JS / "illumenate_web.bundle.js").read_text(encoding="utf8")
for configurator_page in ("configure", "configure_tape", "schedule"):
	source = (ROOT / f"illumenate_lighting/templates/pages/{configurator_page}.html").read_text(encoding="utf8")
	assert 'include_script("illumenate_configurator.bundle.js")' in source, configurator_page
configurator_bundle = (WEB_JS / "illumenate_configurator.bundle.js").read_text(encoding="utf8")
for script in WEB_JS.glob("configurator/*.js"):
	assert f'"./configurator/{script.name}"' in configurator_bundle, script.name
print("Checked the configurator bundle split")
# UI-6: fonts and icons are self-hosted woff2, with the two body weights preloaded.
PUBLIC = ROOT / "illumenate_lighting/public"
hooks_source = (ROOT / "illumenate_lighting/hooks.py").read_text(encoding="utf8")
portal_css = (PUBLIC / "css/portal.css").read_text(encoding="utf8")
assert "cdnjs" not in hooks_source and "fonts.googleapis" not in portal_css
font_urls = re.findall(r"url\('/assets/illumenate_lighting/(fonts/[^']+)'\)", portal_css)
assert font_urls and all(url.endswith(".woff2") and (PUBLIC / url).exists() for url in font_urls), font_urls
for stylesheet in re.findall(r'"/assets/illumenate_lighting/(vendor/fontawesome/css/[^"]+)"', hooks_source):
	assert (PUBLIC / stylesheet).exists(), stylesheet
portal_shell = environment.get_template("templates/portal_base.html").render()
for weight in ("Regular", "SemiBold"):
	assert f'href="/assets/illumenate_lighting/fonts/Poppins-{weight}.woff2" as="font"' in portal_shell
print("Checked self-hosted fonts and icons")
