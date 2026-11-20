"""Kevin's Desk Phase 3: the Gmail client's limits, thread state and labels, mailboxes, ranking, warm job."""

import ast
import types
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from test_services import Record, load_service

from illumenate_lighting.kevins_desk import gmail, ranking, schedule

REPO = Path(__file__).resolve().parents[2]
PKG = "illumenate_lighting.kevins_desk"
OWNER = "kevins@illumenate.example"
OURS = {"illumenate.example"}
ME = {"sales@illumenate.example", OWNER}
NOW = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
TEAM = {"jay@illumenate.example": {"key": "jay", "name": "Jay", "owns": "sales calls"}}
DIRECTORY = {
	"emails": {"buyer@acme.example": ["Customer", "Acme"], "pm@gmail.com": ["Lead", "LEAD-9"]},
	"domains": {"acme.example": ["Customer", "Acme"], "tapeco.example": ["Supplier", "Tape Co"]},
}
LABEL_IDS = {"@Action": "L1", "@Waiting": "L2", "@Quote": "L3"}


def msg(
	sender, days_ago, to="kevins@illumenate.example", subject="Hello", labels=("INBOX",), extra=None, mid="m"
):
	headers = [
		{"name": "From", "value": sender},
		{"name": "To", "value": to},
		{"name": "Subject", "value": subject},
		{"name": "Message-ID", "value": f"<{mid}@mail>"},
	]
	headers += [{"name": k, "value": v} for k, v in (extra or {}).items()]
	at = NOW - timedelta(days=days_ago)
	return {
		"id": mid,
		"internalDate": str(int(at.timestamp() * 1000)),
		"labelIds": list(labels),
		"snippet": f"snippet {mid}",
		"payload": {"headers": headers},
	}


def thread(tid, *messages):
	return {"id": tid, "messages": list(messages)}


class FakeSession:
	"""Records Gmail calls; answers labels, thread lists and threads from canned data."""

	def __init__(self, threads=(), labels=None, profile="sales@illumenate.example"):
		self.headers, self.calls = {}, []
		self.threads = {t["id"]: t for t in threads}
		self.labels = [{"name": n, "id": i} for n, i in (labels if labels is not None else LABEL_IDS).items()]
		self.profile = profile

	def request(self, method, url, timeout=None, params=None, json=None):
		path = url.replace(gmail.API, "")
		self.calls.append((method, path, params, json))
		body = {}
		if path == "/labels" and method == "GET":
			body = {"labels": self.labels}
		elif path == "/labels":
			made = {"name": json["name"], "id": "NEW-" + json["name"]}
			self.labels.append(made)
			body = made
		elif path == "/profile":
			body = {"emailAddress": self.profile}
		elif path == "/threads":
			body = {"threads": [{"id": t} for t in self.threads]}
		elif path.startswith("/threads/") and path.endswith("/modify"):
			body = {}
		elif path.startswith("/threads/"):
			if path.split("/")[2] not in self.threads:
				return types.SimpleNamespace(status_code=404, content=b"x", json=lambda: {}, text="not found")
			body = self.threads[path.split("/")[2]]
		return types.SimpleNamespace(status_code=200, content=b"x", json=lambda: body, text="")

	def modifies(self):
		return {p.split("/")[2]: j for m, p, _, j in self.calls if p.endswith("/modify")}


class GmailClientLimits(unittest.TestCase):
	def test_the_client_has_no_way_to_send_trash_delete_or_archive(self):
		src = (REPO / "illumenate_lighting/kevins_desk/gmail.py").read_text(encoding="utf-8")
		strings = [
			n.value
			for n in ast.walk(ast.parse(src))
			if isinstance(n, ast.Constant) and isinstance(n.value, str)
		]
		for word in ("/send", "trash", "/delete", "batchDelete", "batchModify", "/messages/", "/drafts/send"):
			self.assertFalse(
				[s for s in strings if word in s and not s.startswith(("A deliberately", "Add/remove"))], word
			)
		self.assertNotIn('"DELETE"', src)
		self.assertNotIn('"PUT"', src)

	def test_only_the_desks_own_labels_can_change(self):
		gm = gmail.Gmail({"Authorization": "Bearer t"}, session=FakeSession())
		gm.ensure_labels()
		for bad in ("INBOX", "UNREAD", "TRASH", "SPAM", "STARRED", "Label_123"):
			with self.subTest(bad=bad):
				with self.assertRaises(gmail.GmailError):
					gm.modify_thread("t1", remove=[bad])
				with self.assertRaises(gmail.GmailError):
					gm.modify_thread("t1", add=[bad])
		gm.modify_thread("t1", add=["@Action"], remove=["@Waiting"])
		self.assertEqual(gm.session.modifies(), {"t1": {"addLabelIds": ["L1"], "removeLabelIds": ["L2"]}})

	def test_missing_labels_are_created(self):
		gm = gmail.Gmail({}, session=FakeSession(labels={"@Action": "L1"}))
		self.assertEqual(
			gm.ensure_labels(), {"@Action": "L1", "@Waiting": "NEW-@Waiting", "@Quote": "NEW-@Quote"}
		)

	def test_threads_reads_metadata_only_and_skips_failures(self):
		s = FakeSession(threads=[thread("a", msg("x@acme.example", 1))])
		gm = gmail.Gmail({}, session=s)
		got = gm.threads(["a", "a", "missing"])
		self.assertEqual([t["id"] for t in got], ["a"])
		params = next(p for m, path, p, _ in s.calls if path == "/threads/a")
		self.assertEqual(params["format"], "metadata")


@contextmanager
def mail_module(rows=(), statuses=None):
	mb = types.ModuleType(PKG + ".mailboxes")
	mb.rows = MagicMock(return_value=list(rows))
	mb.status = MagicMock(
		side_effect=lambda row, owner: dict(row, **(statuses or {}).get(row["mailbox"], {}))
	)
	pipe = types.ModuleType(PKG + ".pipeline")
	pipe.desk_url = lambda dt, name: f"/desk/{dt.lower().replace(' ', '-')}/{name}"
	extras = {
		PKG + ".mailboxes": mb,
		PKG + ".pipeline": pipe,
		PKG + ".gmail": gmail,
		PKG + ".ranking": ranking,
	}
	with load_service(PKG + ".mail", extras) as (mail, frappe):
		frappe.log_error = MagicMock()
		yield mail, frappe, mb


class ThreadState(unittest.TestCase):
	def read(self, t):
		with mail_module() as (mail, _, _mb):
			return mail.read_thread(t, ME, OURS, NOW)

	def test_customer_wrote_last_in_the_inbox_needs_a_reply(self):
		info = self.read(
			thread(
				"t",
				msg("Kevin <kevins@illumenate.example>", 5, labels=("SENT",), mid="a"),
				msg('"Bo Byer" <Buyer@Acme.example>', 1, mid="b"),
			)
		)
		self.assertEqual(
			(info["state"], info["counterpart"], info["counterpart_name"]),
			("reply", "buyer@acme.example", "Bo Byer"),
		)
		self.assertEqual((info["message_id"], info["rfc_message_id"]), ("b", "<b@mail>"))
		self.assertFalse(info["automated"])

	def test_customer_wrote_last_but_archived_is_handled(self):
		self.assertEqual(self.read(thread("t", msg("buyer@acme.example", 1, labels=())))["state"], "none")

	def test_we_wrote_last_three_or_more_days_ago_is_waiting(self):
		info = self.read(
			thread(
				"t",
				msg("buyer@acme.example", 9, mid="a"),
				msg("kevins@illumenate.example", 4, to="buyer@acme.example", labels=("SENT",), mid="b"),
			)
		)
		self.assertEqual((info["state"], info["counterpart"]), ("waiting", "buyer@acme.example"))
		self.assertEqual(
			self.read(thread("t", msg("kevins@illumenate.example", 1, to="buyer@acme.example")))["state"],
			"recent",
		)

	def test_a_thread_we_started_waits_on_who_we_wrote_to(self):
		info = self.read(
			thread("t", msg("kevins@illumenate.example", 5, to="Jay <jay@illumenate.example>, pm@gmail.com"))
		)
		self.assertEqual((info["state"], info["counterpart"]), ("waiting", "pm@gmail.com"))

	def test_a_colleague_answering_a_customer_counts_as_us(self):
		info = self.read(
			thread(
				"t",
				msg("buyer@acme.example", 6, mid="a"),
				msg("jay@illumenate.example", 4, to="buyer@acme.example", mid="b"),
			)
		)
		self.assertEqual((info["state"], info["counterpart"]), ("waiting", "buyer@acme.example"))

	def test_a_colleague_asking_internally_needs_our_reply(self):
		info = self.read(thread("t", msg("Jay <jay@illumenate.example>", 0.5, to="sales@illumenate.example")))
		self.assertEqual((info["state"], info["counterpart"]), ("reply", "jay@illumenate.example"))

	def test_automated_mail_is_recognised(self):
		cases = {
			"list header": msg("news@acme.example", 1, extra={"List-Unsubscribe": "<mailto:x>"}),
			"bulk": msg("buyer@acme.example", 1, extra={"Precedence": "bulk"}),
			"auto-submitted": msg("buyer@acme.example", 1, extra={"Auto-Submitted": "auto-replied"}),
			"no-reply sender": msg("no-reply@vendor.example", 1),
			"notifications sender": msg("notifications@vendor.example", 1),
			"skipped domain": msg("builds@mail.github.com", 1),
			"google": msg("calendar-notification@google.com", 1),
		}
		for label, m in cases.items():
			with self.subTest(label):
				self.assertTrue(self.read(thread("t", m))["automated"])
		self.assertFalse(self.read(thread("t", msg("Auto Parts <sales@autoparts.example>", 1)))["automated"])


class Ingest(unittest.TestCase):
	def run_ingest(self, threads):
		s = FakeSession(threads=threads)
		with mail_module() as (mail, _, _mb):
			items, changed = mail.ingest(
				gmail.Gmail({}, session=s), "sales@illumenate.example", ME, OURS, TEAM, DIRECTORY, NOW
			)
		return items, changed, s

	def test_labels_follow_the_thread_state_and_only_ours_change(self):
		threads = [
			thread("reply", msg("buyer@acme.example", 3, subject="Re: lobby", labels=("INBOX", "L2"))),
			thread("quote", msg("new@studio.example", 0.2, subject="RFQ for 40 coves")),
			thread(
				"waiting", msg("kevins@illumenate.example", 5, to="buyer@acme.example", labels=("SENT", "L1"))
			),
			thread(
				"recent", msg("kevins@illumenate.example", 1, to="buyer@acme.example", labels=("SENT", "L1"))
			),
			thread("auto", msg("news@acme.example", 1, labels=("INBOX", "L1"), extra={"List-Id": "x"})),
			thread("done", msg("buyer@acme.example", 2, labels=("L1", "L3"))),
		]
		items, changed, s = self.run_ingest(threads)
		self.assertEqual(
			s.modifies(),
			{
				"reply": {"addLabelIds": ["L1"], "removeLabelIds": ["L2"]},
				"quote": {"addLabelIds": ["L1", "L3"], "removeLabelIds": []},
				"waiting": {"addLabelIds": ["L2"], "removeLabelIds": ["L1"]},
				"recent": {"addLabelIds": [], "removeLabelIds": ["L1"]},
				"auto": {"addLabelIds": [], "removeLabelIds": ["L1"]},
				"done": {"addLabelIds": [], "removeLabelIds": ["L1"]},  # @Quote is never removed
			},
		)
		self.assertEqual(changed, 6)
		self.assertEqual(sorted(i["name"] for i in items), ["quote", "reply", "waiting"])
		self.assertFalse(
			[c for c in s.calls if c[0] == "POST" and not c[1].endswith("/modify")]
		)  # labels existed

	def test_items_carry_who_stack_link_and_threading_ids(self):
		items, _, _s = self.run_ingest(
			[
				thread("reply", msg("buyer@acme.example", 3, subject="Lobby coves", mid="m9")),
				thread("tape", msg("orders@tapeco.example", 1, subject="Your order shipped")),
				thread(
					"jay",
					msg(
						"jay@illumenate.example",
						0.5,
						to="sales@illumenate.example",
						subject="Can you review?",
					),
				),
				thread("late", msg("pm@gmail.com", 0.5, subject="Coves arrived damaged")),
			]
		)
		got = {i["name"]: i for i in items}
		r = got["reply"]
		self.assertEqual(
			(r["who"], r["party"], r["party_link"]["url"], r["stack"], r["hat"], r["flag"]),
			("customer", "Acme", "/desk/customer/Acme", 2, "sales", "late"),
		)
		self.assertEqual(
			(r["message_id"], r["rfc_message_id"], r["status"]), ("m9", "<m9@mail>", "Needs reply")
		)
		self.assertEqual(
			r["url"], "https://mail.google.com/mail/?authuser=sales@illumenate.example#all/reply"
		)
		self.assertEqual(
			(got["tape"]["who"], got["tape"]["stack"], got["tape"]["hat"]), ("supplier", 3, "ops")
		)
		self.assertEqual((got["jay"]["who"], got["jay"]["party"], got["jay"]["stack"]), ("team", "Jay", 5))
		self.assertEqual(
			(got["late"]["who"], got["late"]["stack"], got["late"]["topic"]), ("lead", 1, "risk")
		)


class MailBuild(unittest.TestCase):
	def test_mailbox_states_are_reported_without_tokens(self):
		rows = [
			{"mailbox": "kevins@illumenate.example", "label": "kevins@"},
			{"mailbox": "sales@illumenate.example", "label": "sales@"},
			{"mailbox": "info@illumenate.example", "label": "info@"},
		]
		statuses = {
			"kevins@illumenate.example": {
				"state": "not_set_up",
				"redirect_uri": "https://x/cb/kevins-desk-kevins",
			},
			"sales@illumenate.example": {
				"state": "connected",
				"auth_header": {"Authorization": "Bearer SECRET"},
			},
			"info@illumenate.example": {
				"state": "connected",
				"auth_header": {"Authorization": "Bearer SECRET2"},
			},
		}
		sessions = {
			"Bearer SECRET": FakeSession(threads=[thread("t", msg("buyer@acme.example", 1))]),
			"Bearer SECRET2": FakeSession(profile="kevins@illumenate.example"),
		}
		with mail_module(rows, statuses) as (mail, _frappe, _mb):
			mail.Gmail = lambda header: gmail.Gmail(header, session=sessions[header["Authorization"]])
			mail.load_directory = MagicMock(return_value=DIRECTORY)
			out = mail.build(OWNER, TEAM, NOW)
		states = {m["mailbox"]: m for m in out["mailboxes"]}
		self.assertEqual(states["kevins@illumenate.example"]["state"], "not_set_up")
		self.assertEqual(states["sales@illumenate.example"]["state"], "connected")
		self.assertEqual(states["sales@illumenate.example"]["threads"], 1)
		self.assertEqual(states["info@illumenate.example"]["state"], "wrong_account")
		self.assertNotIn("SECRET", repr(out))
		self.assertEqual([t["mailbox"] for t in out["threads"]], ["sales@illumenate.example"])

	def test_one_failing_mailbox_does_not_stop_the_others(self):
		rows = [
			{"mailbox": "sales@illumenate.example", "label": "sales@"},
			{"mailbox": "kevins@illumenate.example", "label": "k"},
		]
		statuses = {
			r["mailbox"]: {"state": "connected", "auth_header": {"Authorization": "Bearer " + r["label"]}}
			for r in rows
		}
		with mail_module(rows, statuses) as (mail, frappe, _mb):
			ok = FakeSession(
				threads=[thread("t", msg("buyer@acme.example", 1))], profile="kevins@illumenate.example"
			)

			def make(header):
				if header["Authorization"] == "Bearer sales@":
					raise gmail.GmailError("HTTP 401")
				return gmail.Gmail(header, session=ok)

			mail.Gmail = make
			mail.load_directory = MagicMock(return_value=DIRECTORY)
			out = mail.build(OWNER, TEAM, NOW)
		self.assertEqual([m["state"] for m in out["mailboxes"]], ["error", "connected"])
		self.assertEqual(len(out["threads"]), 1)
		frappe.log_error.assert_called_once()

	def test_who_matches_team_customers_by_email_or_domain_but_not_generic_domains(self):
		with mail_module() as (mail, _, _mb):
			self.assertEqual(mail.who("jay@illumenate.example", TEAM, DIRECTORY, OURS), ("team", None))
			self.assertEqual(mail.who("info@illumenate.example", TEAM, DIRECTORY, OURS), ("internal", None))
			self.assertEqual(mail.who("anyone@acme.example", TEAM, DIRECTORY, OURS)[0], "customer")
			self.assertEqual(mail.who("pm@gmail.com", TEAM, DIRECTORY, OURS)[0], "lead")
			self.assertEqual(mail.who("someone@gmail.com", TEAM, DIRECTORY, OURS), ("unknown", None))


@contextmanager
def mailboxes_module(rows=({"mailbox": "sales@illumenate.example", "enabled": 1, "label": "sales@"},)):
	access = types.ModuleType(PKG + ".access")
	access.SETTINGS = "ilL-Desk-Settings"
	with load_service(PKG + ".mailboxes", {PKG + ".access": access}) as (mb, frappe):
		frappe.get_single = MagicMock(return_value=Record(mailboxes=[Record(r) for r in rows]))
		mb.get_url = lambda path: "https://site.example" + path
		yield mb, frappe


class Mailboxes(unittest.TestCase):
	def test_app_names_and_redirect_uris_are_fixed(self):
		with mailboxes_module() as (mb, _):
			self.assertEqual(mb.app_name("Sales@illumenate.example"), "kevins-desk-sales")
			self.assertEqual(mb.app_name("ryan.b@x.example"), "kevins-desk-ryan-b")
			self.assertEqual(
				mb.redirect_uri("kevins-desk-sales"),
				"https://site.example/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/kevins-desk-sales",
			)

	def test_only_configured_mailboxes_can_be_connected(self):
		with mailboxes_module() as (mb, frappe):
			for bad in ("", None, "ceo@illumenate.example"):
				with self.subTest(bad=bad), self.assertRaises(LookupError):
					mb.connect(bad, OWNER, "/kd/x")
			frappe.get_doc.assert_not_called()

	def test_a_new_mailbox_app_copies_the_template_and_asks_for_offline_access(self):
		with mailboxes_module() as (mb, frappe):
			frappe.db.exists.side_effect = lambda dt, name=None: name == "tmpl"
			frappe.db.get_single_value.return_value = "tmpl"
			template = MagicMock(client_id="cid", scopes=[Record(scope="https://mail.google.com/")])
			template.get = lambda f: {
				"client_id": "cid",
				"token_uri": "https://oauth2.googleapis.com/token",
			}.get(f)
			template.get_password.return_value = "secret"
			new = MagicMock()
			new.is_new.return_value = True
			new.append = MagicMock()
			frappe.new_doc = MagicMock(return_value=new)
			frappe.get_doc.side_effect = lambda dt, name=None: template
			self.assertEqual(mb.ensure_app("sales@illumenate.example"), "kevins-desk-sales")
		appended = [c.args for c in new.append.call_args_list]
		self.assertIn(("scopes", {"scope": "https://mail.google.com/"}), appended)
		self.assertIn(("query_parameters", {"key": "access_type", "value": "offline"}), appended)
		self.assertIn(("query_parameters", {"key": "prompt", "value": "consent"}), appended)
		self.assertIn(
			("query_parameters", {"key": "login_hint", "value": "sales@illumenate.example"}), appended
		)
		self.assertEqual(new.client_secret, "secret")
		new.insert.assert_called_once_with(ignore_permissions=True, set_name="kevins-desk-sales")

	def test_status_hides_nothing_but_never_says_connected_without_a_token(self):
		row = {"mailbox": "sales@illumenate.example", "label": "sales@"}
		with mailboxes_module() as (mb, frappe):
			frappe.db.exists.return_value = False
			self.assertEqual(mb.status(row, OWNER)["state"], "not_set_up")
			frappe.db.exists.return_value = True
			app = MagicMock()
			frappe.get_doc.return_value = app
			app.get_active_token.return_value = None  # refresh failed / revoked
			self.assertEqual(mb.status(row, OWNER)["state"], "not_connected")
			token = MagicMock()
			token.get_password.return_value = "at"
			token.get_auth_header.return_value = {"Authorization": "Bearer at"}
			app.get_active_token.return_value = token
			st = mb.status(row, OWNER)
		self.assertEqual((st["state"], st["auth_header"]), ("connected", {"Authorization": "Bearer at"}))
		app.get_active_token.assert_called_with(OWNER)


class Ranking(unittest.TestCase):
	def test_topics(self):
		self.assertEqual(ranking.topic("Driver flicker at 10%"), "risk")
		self.assertEqual(ranking.topic("RFQ: lobby coves"), "quote")
		self.assertEqual(ranking.topic("PO #4471 attached"), "order")
		self.assertEqual(ranking.topic("Warranty question"), "support")
		self.assertIsNone(ranking.topic("Lunch Friday?"))
		self.assertIsNone(ranking.topic("New template ideas"))  # "late" inside a word is not risk

	def test_todo_stack(self):
		team = {"jay@x.example": {}}
		self.assertEqual(ranking.todo_stack({"ref": {"dt": "Quotation"}}, team), (2, "sales"))
		self.assertEqual(ranking.todo_stack({"ref": {"dt": "Sales Order"}}, team), (3, "ops"))
		self.assertEqual(
			ranking.todo_stack({"assigned_by": "Jay@x.example", "title": "x"}, team), (5, "growth")
		)
		self.assertEqual(
			ranking.todo_stack({"title": "Customer says coves arrived damaged"}, team), (1, "sales")
		)
		self.assertEqual(ranking.todo_stack({"title": "Renew domain"}, team), (7, None))

	def test_merge_ranks_by_stack_owed_before_waiting_then_late_then_oldest(self):
		def it(i, stack, hat, date, flag=None):
			return {"id": i, "stack": stack, "hat": hat, "date": date, "flag": flag, "title": i}

		pipeline = {
			"widgets": [
				{
					"items": [
						it("q-old", 2, "sales", "2026-11-01"),
						it("so-late", 1, "sales", "2026-11-18", "late"),
					]
				},
				{"items": [it("so-wk", 3, "ops", "2026-11-21"), it("q-old", 2, "sales", "2026-11-01")]},
			],
			"todos": [{"id": "td", "title": "Renew domain", "date": "2026-11-19", "flag": "late"}],
		}
		mail = {
			"threads": [
				dict(it("g-wait", 2, "sales", "2026-10-01", "late"), kind="waiting"),
				dict(it("g-new", 2, "sales", "2026-11-20", "late"), kind="reply"),
				it("g-team", 5, "growth", "2026-11-19"),
			]
		}
		out = ranking.merge(pipeline, mail, {}, schedule.HATS)
		order = [i["id"] for i in out["top"]]
		self.assertEqual(order, ["so-late", "g-new", "q-old", "g-wait", "so-wk", "g-team", "td"])
		self.assertEqual([g["hat"] for g in out["groups"]], ["sales", "ops", "growth", "none"])
		self.assertEqual(out["groups"][-1]["label"], "No hat · admin")
		self.assertEqual([i["rank"] for i in out["groups"][0]["items"]], [1, 2, 3, 4])
		self.assertEqual(out["counts"], {1: 1, 2: 3, 3: 1, 5: 1, 7: 1})
		self.assertEqual(out["total"], 7)
		self.assertEqual({i["source"] for i in out["top"]}, {"erpnext", "gmail", "todo"})


class WarmJob(unittest.TestCase):
	@contextmanager
	def tasks(self, conf, owner_ok=True):
		access = types.ModuleType(PKG + ".access")
		access.config = MagicMock(return_value=conf)
		access.is_owner = MagicMock(return_value=owner_ok)
		api = types.ModuleType(PKG + ".api")
		api.build_today = MagicMock()
		api.cached = MagicMock()
		pipe = types.ModuleType(PKG + ".pipeline")
		pipe.signals = MagicMock()
		with load_service(
			PKG + ".tasks", {PKG + ".access": access, PKG + ".api": api, PKG + ".pipeline": pipe}
		) as (t, frappe):
			frappe.session.user = "Administrator"
			frappe.set_user = MagicMock(
				side_effect=lambda u: (
					setattr(frappe.session, "user", u) or frappe.session.__setitem__("user", u)
				)
			)
			frappe.log_error = MagicMock()
			yield t, frappe, api

	def test_rebuilds_as_the_owner_and_restores_the_user(self):
		with self.tasks({"enabled": 1, "desk_owner": OWNER}) as (t, frappe, api):
			api.build_today.side_effect = lambda owner, refresh: self.assertEqual(frappe.session.user, OWNER)
			t.warm()
			api.build_today.assert_called_once_with(OWNER, refresh=True)
			self.assertEqual(frappe.session.user, "Administrator")

	def test_does_nothing_when_off_or_owner_invalid(self):
		for conf, ok in (
			({"enabled": 0, "desk_owner": OWNER}, True),
			({"enabled": 1}, True),
			({"enabled": 1, "desk_owner": OWNER}, False),
		):
			with self.subTest(conf=conf, ok=ok), self.tasks(conf, ok) as (t, frappe, api):
				t.warm()
				api.build_today.assert_not_called()
				frappe.set_user.assert_not_called()

	def test_a_failure_is_logged_and_the_user_restored(self):
		with self.tasks({"enabled": 1, "desk_owner": OWNER}) as (t, frappe, api):
			api.build_today.side_effect = RuntimeError("gmail down")
			t.warm()
			frappe.log_error.assert_called_once()
			self.assertEqual(frappe.session.user, "Administrator")


class Hooks(unittest.TestCase):
	def test_warm_runs_every_ten_minutes_in_weekday_working_hours(self):
		hooks = (REPO / "illumenate_lighting/hooks.py").read_text(encoding="utf-8")
		self.assertIn('"*/10 6-17 * * 1-5": ["illumenate_lighting.kevins_desk.tasks.warm"]', hooks)
		patches = (
			(REPO / "illumenate_lighting/patches.txt")
			.read_text(encoding="utf-8")
			.split("[post_model_sync]")[1]
		)
		self.assertLess(patches.index("seed_desk_settings"), patches.index("seed_desk_mailboxes"))


if __name__ == "__main__":
	unittest.main()
