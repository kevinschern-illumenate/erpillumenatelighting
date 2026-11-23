"""Kevin's Desk Phase 2: owner-only endpoints, the cache, the gateway adapter and the pipeline widgets."""

import ast
import types
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from test_services import load_service

from illumenate_lighting.kevins_desk import schedule

REPO = Path(__file__).resolve().parents[2]
PKG = "illumenate_lighting.kevins_desk"
OWNER = "kevins@example.com"
TODAY = date(2026, 11, 20)  # a Friday


def utils_module():
	"""frappe.utils with real date maths (the shared double's getdate returns strings)."""
	u = types.ModuleType("frappe.utils")

	def getdate(value=None):
		if isinstance(value, datetime):
			return value.date()
		if isinstance(value, date):
			return value
		return date.fromisoformat(str(value or TODAY)[:10])

	u.getdate = getdate
	u.add_days = lambda d, n: getdate(d) + timedelta(days=n)
	u.nowdate = lambda: str(TODAY)
	u.cint = lambda v: int(v or 0)
	u.now_datetime = lambda: datetime(2026, 11, 20, 10, 42, 5)
	return u


def gateway_columns():
	"""ALLOWED from the gateway source: doctype -> its list columns (what its list action can filter on)."""
	tree = ast.parse(
		(REPO / "illumenate_lighting/command_center/ss/cc_gateway.py").read_text(encoding="utf-8")
	)
	for node in ast.walk(tree):
		if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "ALLOWED":
			return {dt: cols for dt, (_, cols) in ast.literal_eval(node.value).items()}
	raise AssertionError("ALLOWED not found in cc_gateway.py")


class FakeGateway:
	"""Answers the gateway's list/overview actions and records every call."""

	def __init__(self, rows=None, columns=None, fail=()):
		self.calls, self.rows, self.fail = [], rows or {}, set(fail)
		self.columns = columns or gateway_columns()

	def __call__(self, action, **params):
		self.calls.append((action, params))
		if action == "overview":
			return {
				"today": str(TODAY),
				"signals": [
					{
						"id": "so_late",
						"label": "Open orders past delivery date",
						"dt": "Sales Order",
						"count": 2,
						"tone": "bad",
						"status": "",
					},
					{
						"id": "wo_draft",
						"label": "Work orders still in Draft",
						"dt": "Work Order",
						"count": 0,
						"tone": "warn",
						"status": "Draft",
					},
				],
			}
		dt = params["dt"]
		if dt in self.fail:
			raise ValueError("gateway said no")
		rows = self.rows.get(dt, [])
		return {
			"rows": rows,
			"total": len(rows) + (5 if dt == "Quotation" else 0),
			"columns": [{"fieldname": c} for c in self.columns.get(dt, [])],
		}

	def filters(self, dt):
		return [p["filters"] for a, p in self.calls if a == "list" and p["dt"] == dt]


@contextmanager
def pipeline(gw=None, todos=()):
	gw = gw or FakeGateway()
	cc = types.ModuleType(PKG + ".cc")
	cc.gateway = gw
	with load_service(PKG + ".pipeline", {PKG + ".cc": cc, "frappe.utils": utils_module()}) as (pipe, frappe):
		frappe.get_list = MagicMock(return_value=[dict(t) for t in todos])
		frappe.log_error = MagicMock()
		yield pipe, frappe, gw


@contextmanager
def endpoints(user=OWNER, owner=True):
	"""api.py with every desk module stubbed; returns (api, stubs, cache, store)."""
	access = types.ModuleType(PKG + ".access")

	def require_owner():
		if not owner or user != OWNER:
			raise LookupError("404")
		return {"desk_owner": OWNER, "slug": "S" * 32}

	access.require_owner = MagicMock(side_effect=require_owner)
	pipe = types.ModuleType(PKG + ".pipeline")
	pipe.build = MagicMock(return_value={"widgets": [], "todos": []})
	pipe.signals = MagicMock(return_value={"signals": []})
	mail = types.ModuleType(PKG + ".mail")
	mail.build = MagicMock(
		return_value={"mailboxes": [{"mailbox": "sales@example.com", "state": "connected"}], "threads": []}
	)
	mailboxes = types.ModuleType(PKG + ".mailboxes")
	mailboxes.connect = MagicMock(return_value="https://accounts.google.com/o/oauth2/v2/auth?x=1")
	mailboxes.rows = MagicMock(return_value=[{"mailbox": "sales@example.com"}])
	done = types.ModuleType(PKG + ".done")

	def parse(item):
		kind, _, rest = (item or "").partition(":")
		if kind == "ToDo":
			return ("todo", rest)
		if kind == "gmail":
			box, _, thread_id = rest.rpartition(":")
			return ("gmail", box, thread_id)
		raise LookupError("404")

	done.parse = MagicMock(side_effect=parse)
	done.close_todo = MagicMock()
	done.hide_thread = MagicMock()
	done.marks = MagicMock(return_value={("sales@example.com", "t0"): "m0"})
	ranking = types.ModuleType(PKG + ".ranking")
	ranking.merge = MagicMock(return_value={"groups": [], "top": [], "counts": {}, "total": 0})
	team = types.ModuleType(PKG + ".team")
	team.resolve = MagicMock(return_value={"jay@example.com": {"name": "Jay"}})
	stubs = types.SimpleNamespace(
		access=access, pipeline=pipe, mail=mail, mailboxes=mailboxes, ranking=ranking, team=team, done=done
	)
	extras = {PKG + "." + k: v for k, v in vars(stubs).items()}
	extras["frappe.utils"] = utils_module()
	with load_service(PKG + ".api", extras) as (api, frappe):
		frappe.session.user = user
		store = {}
		cache = MagicMock()
		cache.get_value.side_effect = store.get
		cache.set_value.side_effect = lambda k, v, expires_in_sec=None: store.__setitem__(k, v)
		cache.delete_value.side_effect = lambda k: store.pop(k, None)
		frappe.cache = MagicMock(return_value=cache)
		yield api, stubs, cache, store


class DeskEndpoints(unittest.TestCase):
	def test_every_endpoint_checks_the_owner_before_anything_else(self):
		tree = ast.parse((REPO / "illumenate_lighting/kevins_desk/api.py").read_text(encoding="utf-8"))
		endpoints_found = []
		for fn in tree.body:
			if not isinstance(fn, ast.FunctionDef) or not fn.decorator_list:
				continue
			endpoints_found.append(fn.name)
			first = next(
				s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
			)
			self.assertIn("access.require_owner()", ast.unparse(first), fn.name)
			self.assertIn("allow_guest=True", ast.unparse(fn.decorator_list[0]), fn.name)
		self.assertEqual(sorted(endpoints_found), ["connect_mailbox", "mark_done", "signals", "today"])

	def test_guest_and_other_users_get_404_and_nothing_is_read(self):
		for user in ("Guest", "jay@example.com"):
			with self.subTest(user=user), endpoints(user=user) as (api, stubs, cache, _):
				for call in (
					api.today,
					api.signals,
					lambda refresh=0: api.connect_mailbox("sales@example.com"),
					lambda refresh=0: api.mark_done("ToDo:T-1"),
					lambda refresh=0: api.mark_done("gmail:sales@example.com:t1", "m1", "Hi"),
				):
					with self.assertRaises(LookupError):
						call()
					with self.assertRaises(LookupError):
						call(refresh=1)
				for fn in (
					stubs.pipeline.build,
					stubs.pipeline.signals,
					stubs.mail.build,
					stubs.mailboxes.connect,
					stubs.team.resolve,
					stubs.done.parse,
					stubs.done.close_todo,
					stubs.done.hide_thread,
					stubs.done.marks,
				):
					fn.assert_not_called()
				cache.get_value.assert_not_called()

	def test_owner_reads_are_cached_per_user_and_refresh_rebuilds(self):
		with endpoints() as (api, stubs, _, store):
			first = api.today()
			second = api.today()
			third = api.today(refresh="1")
		self.assertEqual((first["cached"], second["cached"], third["cached"]), (False, True, False))
		self.assertEqual(stubs.pipeline.build.call_count, 2)
		self.assertEqual(stubs.mail.build.call_count, 2)
		stubs.pipeline.build.assert_called_with(OWNER)
		stubs.mail.build.assert_called_with(
			OWNER, {"jay@example.com": {"name": "Jay"}}, done={("sales@example.com", "t0"): "m0"}
		)
		self.assertEqual(first["built_at"], "2026-11-20T10:42:05")
		self.assertEqual(first["mailboxes"], [{"mailbox": "sales@example.com", "state": "connected"}])
		self.assertEqual(sorted(store), [f"kevins_desk:{OWNER}:mail", f"kevins_desk:{OWNER}:pipeline"])
		pipeline_arg, mail_arg, team_arg, hats = stubs.ranking.merge.call_args.args
		self.assertEqual(team_arg, {"jay@example.com": {"name": "Jay"}})
		self.assertEqual((pipeline_arg["widgets"], mail_arg["threads"]), ([], []))
		self.assertIn("sales", hats)

	def test_connect_returns_to_the_desk_and_drops_the_mail_cache(self):
		with endpoints() as (api, stubs, _, store):
			api.today()
			out = api.connect_mailbox("sales@example.com")
		self.assertEqual(out, {"authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?x=1"})
		stubs.mailboxes.connect.assert_called_once_with(
			"sales@example.com", OWNER, "/kd/" + "S" * 32 + "?mailbox=connected"
		)
		self.assertNotIn(f"kevins_desk:{OWNER}:mail", store)

	def test_connect_is_post_only_and_tightly_rate_limited(self):
		src = (REPO / "illumenate_lighting/kevins_desk/api.py").read_text(encoding="utf-8")
		tree = ast.parse(src)
		fn = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "connect_mailbox")
		self.assertIn("methods=['POST']", ast.unparse(fn.decorator_list[0]))
		self.assertEqual(ast.unparse(fn.decorator_list[1]), "rate_limit(limit=10, seconds=60)")

	def test_done_closes_a_todo_and_drops_it_from_the_cached_pipeline_only(self):
		with endpoints() as (api, stubs, _, store):
			stubs.pipeline.build.return_value = {
				"widgets": [],
				"todos": [{"id": "ToDo:T-1"}, {"id": "ToDo:T-2"}],
			}
			stubs.mail.build.return_value = {
				"mailboxes": [],
				"threads": [{"id": "gmail:sales@example.com:t1"}],
			}
			api.today()
			out = api.mark_done("ToDo:T-1")
		self.assertEqual(out, {"done": "ToDo:T-1"})
		stubs.done.close_todo.assert_called_once_with("T-1", OWNER)
		stubs.done.hide_thread.assert_not_called()
		self.assertEqual(store[f"kevins_desk:{OWNER}:pipeline"]["todos"], [{"id": "ToDo:T-2"}])
		self.assertEqual(len(store[f"kevins_desk:{OWNER}:mail"]["threads"]), 1)

	def test_done_hides_a_thread_of_the_desks_own_mailboxes_and_drops_it_from_the_mail_cache(self):
		with endpoints() as (api, stubs, _, store):
			stubs.mail.build.return_value = {
				"mailboxes": [],
				"threads": [{"id": "gmail:sales@example.com:t1"}, {"id": "gmail:sales@example.com:t2"}],
			}
			api.today()
			api.mark_done("gmail:sales@example.com:t1", "m9", "RFQ")
		stubs.done.hide_thread.assert_called_once_with(
			"sales@example.com", "t1", "m9", "RFQ", {"sales@example.com"}
		)
		stubs.done.close_todo.assert_not_called()
		self.assertEqual(
			store[f"kevins_desk:{OWNER}:mail"]["threads"], [{"id": "gmail:sales@example.com:t2"}]
		)

	def test_done_on_anything_else_is_not_found_and_without_a_cache_is_still_done(self):
		with endpoints() as (api, stubs, _, store):
			for bad in (None, "Sales Order:SO-1", "nonsense"):
				with self.assertRaises(LookupError):
					api.mark_done(bad)
			api.mark_done("ToDo:T-1")
		stubs.done.close_todo.assert_called_once_with("T-1", OWNER)
		self.assertEqual(store, {})

	def test_done_is_post_only_and_rate_limited(self):
		tree = ast.parse((REPO / "illumenate_lighting/kevins_desk/api.py").read_text(encoding="utf-8"))
		fn = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "mark_done")
		self.assertIn("methods=['POST']", ast.unparse(fn.decorator_list[0]))
		self.assertEqual(ast.unparse(fn.decorator_list[1]), "rate_limit(limit=60, seconds=60)")


class GatewayAdapter(unittest.TestCase):
	def test_returns_the_gateway_message_and_restores_the_callers_response(self):
		safe_exec = types.ModuleType("frappe.utils.safe_exec")
		with load_service(PKG + ".cc", {"frappe.utils.safe_exec": safe_exec}) as (cc, frappe):
			frappe.local.response = {"message": "caller's"}

			def run(method, **kw):
				self.assertEqual(method, "ill_cc_gateway")
				self.assertNotIn(
					"message", frappe.local.response
				)  # a stale message is never mistaken for ours
				frappe.local.response["message"] = {"rows": [kw["dt"]], "action": kw["action"]}

			safe_exec.call_whitelisted_function = run
			self.assertEqual(cc.gateway("list", dt="Quotation"), {"rows": ["Quotation"], "action": "list"})
			self.assertEqual(frappe.local.response, {"message": "caller's"})

			def boom(method, **kw):
				raise ValueError("You don't have Command Center access.")

			safe_exec.call_whitelisted_function = boom
			with self.assertRaises(ValueError):
				cc.gateway("overview")
			self.assertEqual(frappe.local.response, {"message": "caller's"})


SO = [
	{
		"name": "SO-1",
		"customer": "Acme",
		"status": "To Deliver and Bill",
		"grand_total": 1200.4,
		"delivery_date": date(2026, 11, 18),
	},
	{
		"name": "SO-2",
		"customer": "Bolt",
		"status": "To Deliver",
		"grand_total": 50,
		"delivery_date": date(2026, 11, 20),
	},
	{
		"name": "SO-3",
		"customer": "Cove",
		"status": "To Deliver",
		"grand_total": 75,
		"delivery_date": date(2026, 11, 22),
	},
]
TODOS = [
	{"name": "T-up", "description": "<p>Plan Q1</p>", "date": date(2026, 11, 25), "priority": "Medium"},
	{"name": "T-none", "description": "No date here", "date": None, "priority": "Low"},
	{
		"name": "T-today",
		"description": "<p>Call Bob &amp; Sue</p><p>[email] Owners: kevins</p>"
		'<p><a href="https://mail.google.com/mail/u/0/#inbox/abc?x=1&amp;y=2">Email thread (kevins@ inbox): open in Gmail</a></p>',
		"date": date(2026, 11, 20),
		"priority": "High",
		"_user_tags": ",email,top3",
		"reference_type": "Quotation",
		"reference_name": "QTN 7",
	},
	{
		"name": "T-late",
		"description": "<div>Send drawings</div>",
		"date": date(2026, 11, 2),
		"priority": "High",
	},
]


class PipelineWidgets(unittest.TestCase):
	def test_filters_ask_the_gateway_for_the_brief(self):
		with pipeline() as (pipe, _, gw):
			pipe.build(OWNER, TODAY)
		self.assertEqual(
			gw.filters("Sales Order"),
			[
				{
					"status": ["in", ["To Deliver and Bill", "To Deliver"]],
					"delivery_date": ["<=", "2026-11-22"],
				}
			],
		)
		self.assertEqual(
			gw.filters("Purchase Order"),
			[{"status": ["in", ["To Receive and Bill", "To Receive"]], "ill_eta": ["<", "2026-11-20"]}],
		)
		self.assertEqual(
			gw.filters("Quotation"), [{"status": "Open", "transaction_date": ["<", "2026-11-17"]}]
		)
		self.assertEqual(gw.filters("HD Ticket"), [{"status": "Open"}])

	def test_every_filter_and_sort_field_is_a_gateway_column(self):
		# the gateway silently drops filters on columns it doesn't list, which would widen a widget
		allowed = gateway_columns()
		with pipeline() as (pipe, _, gw):
			pipe.build(OWNER, TODAY)
		self.assertTrue(gw.calls)
		for _, params in gw.calls:
			cols = allowed[params["dt"]]
			for field in params["filters"]:
				self.assertIn(field, cols, (params["dt"], field))
			self.assertIn(params["order_by"].split()[0], cols, params)

	def test_po_falls_back_to_required_by_when_the_site_has_no_eta(self):
		cols = gateway_columns()
		cols["Purchase Order"] = [c for c in cols["Purchase Order"] if c != "ill_eta"]
		with pipeline(FakeGateway(columns=cols)) as (pipe, _, gw):
			widgets = {w["key"]: w for w in pipe.build(OWNER, TODAY)["widgets"]}
		self.assertEqual([list(f)[1] for f in gw.filters("Purchase Order")], ["ill_eta", "schedule_date"])
		self.assertIsNone(widgets["po_late"]["error"])

	def test_sales_orders_split_into_at_risk_and_this_week(self):
		with pipeline(FakeGateway(rows={"Sales Order": SO})) as (pipe, _, _gw):
			data = pipe.build(OWNER, TODAY)
		widgets = {w["key"]: w for w in data["widgets"]}
		late, week = widgets["so_late"], widgets["so_week"]
		self.assertEqual([i["name"] for i in late["items"]], ["SO-1"])
		self.assertEqual(
			late["items"][0] | {},
			{
				"id": "Sales Order:SO-1",
				"dt": "Sales Order",
				"name": "SO-1",
				"title": "SO-1",
				"party": "Acme",
				"date": "2026-11-18",
				"amount": 1200.4,
				"status": "To Deliver and Bill",
				"flag": "late",
				"url": "/desk/sales-order/SO-1",
				"hat": "sales",
				"stack": 1,
			},
		)
		self.assertEqual(
			[(i["name"], i["flag"], i["stack"]) for i in week["items"]],
			[("SO-2", "today", 3), ("SO-3", None, 3)],
		)
		self.assertEqual([w["stack"] for w in data["widgets"]], sorted(w["stack"] for w in data["widgets"]))

	def test_links_go_to_the_desk_or_helpdesk_and_are_encoded(self):
		with pipeline() as (pipe, _, _gw):
			self.assertEqual(pipe.desk_url("HD Ticket", "12"), "/helpdesk/tickets/12")
			self.assertEqual(pipe.desk_url("Purchase Order", "PO/1 #2"), "/desk/purchase-order/PO%2F1%20%232")

	def test_quote_total_counts_beyond_the_shown_rows(self):
		quotes = [
			{
				"name": "QTN-1",
				"party_name": "Acme",
				"status": "Open",
				"grand_total": 9,
				"transaction_date": "2026-11-01",
			}
		]
		with pipeline(FakeGateway(rows={"Quotation": quotes})) as (pipe, _, _gw):
			w = {w["key"]: w for w in pipe.build(OWNER, TODAY)["widgets"]}["quotes_open"]
		self.assertEqual((len(w["items"]), w["total"], w["items"][0]["stack"]), (1, 6, 2))

	def test_one_failing_widget_does_not_blank_the_others(self):
		with pipeline(FakeGateway(rows={"Sales Order": SO}, fail={"Quotation", "Purchase Order"})) as (
			pipe,
			frappe,
			_gw,
		):
			data = pipe.build(OWNER, TODAY)
		widgets = {w["key"]: w for w in data["widgets"]}
		self.assertEqual(widgets["quotes_open"]["error"], "Couldn't load")
		self.assertEqual(widgets["po_late"]["error"], "Couldn't load")
		self.assertEqual(len(widgets["so_week"]["items"]), 2)
		self.assertEqual(frappe.log_error.call_count, 2)

	def test_todos_are_mine_bucketed_and_parsed(self):
		with pipeline(todos=TODOS) as (pipe, frappe, _gw):
			data = pipe.build(OWNER, TODAY)
		kwargs = frappe.get_list.call_args.kwargs
		self.assertEqual(frappe.get_list.call_args.args, ("ToDo",))
		self.assertEqual(kwargs["filters"], {"allocated_to": OWNER, "status": "Open"})
		todos = data["todos"]
		self.assertEqual(
			[(t["name"], t["bucket"]) for t in todos],
			[("T-late", "overdue"), ("T-today", "today"), ("T-up", "upcoming"), ("T-none", "undated")],
		)
		today = todos[1]
		self.assertEqual(today["title"], "Call Bob & Sue")
		self.assertEqual(today["gmail"], "https://mail.google.com/mail/u/0/#inbox/abc?x=1&y=2")
		self.assertEqual(today["tags"], ["email", "top3"])
		self.assertEqual(today["ref"], {"dt": "Quotation", "name": "QTN 7", "url": "/desk/quotation/QTN%207"})
		self.assertEqual((today["url"], today["flag"]), ("/desk/todo/T-today", "today"))
		self.assertEqual((todos[0]["title"], todos[0]["flag"]), ("Send drawings", "late"))
		self.assertIsNone(data["todos_error"])

	def test_todo_failure_is_reported_not_raised(self):
		with pipeline() as (pipe, frappe, _gw):
			frappe.get_list.side_effect = PermissionError("no")
			data = pipe.build(OWNER, TODAY)
		self.assertEqual((data["todos"], data["todos_error"]), ([], "Couldn't load"))

	def test_signals_keep_only_decisions_with_something_in_them(self):
		with pipeline() as (pipe, _, gw):
			data = pipe.signals()
		self.assertEqual(gw.calls, [("overview", {})])
		self.assertEqual([s["id"] for s in data["signals"]], ["so_late"])


if __name__ == "__main__":
	unittest.main()
