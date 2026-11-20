"""Kevin's Desk: the owner-only gate (404 for everyone else), the page context and the schedule."""

import unittest
from contextlib import contextmanager
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_services import Record, load_service

from illumenate_lighting.kevins_desk import schedule

REPO = Path(__file__).resolve().parents[2]
ACCESS = "illumenate_lighting.kevins_desk.access"
PAGE = "illumenate_lighting.templates.pages.kevins_desk"
OWNER = "kevins@example.com"
SLUG = "A" * 10 + "b-_" + "9" * 19  # 32 URL-safe characters
PageMissing = type("PageDoesNotExistError", (Exception,), {})


@contextmanager
def desk(user=OWNER, conf=None, users=None):
	"""The page and the gate with one Frappe double. conf: ilL-Desk-Settings; users: name -> User row."""
	conf = {"enabled": 1, "desk_owner": OWNER, "slug": SLUG} if conf is None else conf
	users = {OWNER: {"enabled": 1, "user_type": "System User"}} if users is None else users
	with load_service(ACCESS) as (access, frappe):
		with load_service(PAGE, {ACCESS: access, "illumenate_lighting.kevins_desk.schedule": schedule}) as (
			page,
			page_frappe,
		):
			for f in (frappe, page_frappe):
				f.PageDoesNotExistError = PageMissing
				f.session.user = user
				f.form_dict = Record()
				f.sessions = SimpleNamespace(get_csrf_token=MagicMock(return_value="csrf-1"))
			frappe.db.get_singles_dict.return_value = conf

			def get_value(doctype, name, fields, as_dict=False):
				row = users.get(name)
				if fields == "first_name":
					return "Kevin" if row else None
				return dict(row) if row else None

			frappe.db.get_value.side_effect = get_value
			page_frappe.db = frappe.db
			with patch.object(page, "access", access):
				yield page, access, frappe


def open_page(page, frappe, slug=SLUG):
	frappe.form_dict = Record(slug=slug)
	with patch.object(page, "frappe", frappe):
		return page.get_context(Record())


class DeskGate(unittest.TestCase):
	def test_everyone_but_the_owner_with_the_right_link_gets_404(self):
		cases = {
			"guest": {"user": "Guest"},
			"another staff member": {
				"user": "jay@example.com",
				"users": {"jay@example.com": {"enabled": 1, "user_type": "System User"}},
			},
			"administrator": {"user": "Administrator"},
			"desk turned off": {"conf": {"enabled": 0, "desk_owner": OWNER, "slug": SLUG}},
			"no owner set": {"conf": {"enabled": 1, "slug": SLUG}},
			"settings not migrated": {"conf": {}},
			"owner disabled": {"users": {OWNER: {"enabled": 0, "user_type": "System User"}}},
			"owner became a website user": {"users": {OWNER: {"enabled": 1, "user_type": "Website User"}}},
		}
		for label, kwargs in cases.items():
			with self.subTest(label), desk(**kwargs) as (page, access, frappe):
				with self.assertRaises(PageMissing):
					open_page(page, frappe)
				with self.assertRaises(LookupError):  # frappe.DoesNotExistError: a 404 from endpoints
					access.require_owner()

	def test_wrong_short_or_missing_slug_is_404_even_for_the_owner(self):
		for slug in (None, "", SLUG[:-1], SLUG + "x", SLUG.lower(), ["list"], "../" + SLUG):
			with self.subTest(slug=slug), desk() as (page, _, frappe):
				with self.assertRaises(PageMissing):
					open_page(page, frappe, slug)
		weak = {"enabled": 1, "desk_owner": OWNER, "slug": "short"}
		with desk(conf=weak) as (page, _, frappe), self.assertRaises(PageMissing):
			open_page(page, frappe, "short")

	def test_a_guest_never_gets_a_login_redirect(self):
		with desk(user="Guest") as (page, _, frappe):
			frappe.Redirect = type("Redirect", (Exception,), {})
			with self.assertRaises(PageMissing):
				open_page(page, frappe)

	def test_owner_with_the_link_gets_the_page(self):
		with desk() as (page, access, frappe):
			context = open_page(page, frappe)
			self.assertEqual(access.require_owner()["desk_owner"], OWNER)
		self.assertEqual(context["desk"]["user"], OWNER)
		self.assertEqual(context["desk"]["first_name"], "Kevin")
		self.assertEqual(context["no_cache"], 1)
		self.assertEqual(context["sitemap"], 0)
		self.assertEqual(context["desk"]["schedule"], schedule.payload())
		self.assertIn("#cc {", context["cc_css"])  # the Command Center's own stylesheet
		self.assertIn("KDCore", context["kd_js"])

	def test_page_module_opts_out_of_cache_and_sitemap(self):
		with desk() as (page, _, _f):
			self.assertEqual((page.no_cache, page.sitemap), (1, 0))

	def test_inlined_assets_cannot_close_their_own_tag(self):
		with desk() as (page, _, _f):
			for key in page.SOURCES:
				self.assertTrue(page.asset(key))
			bad = REPO / "tests/portal_unit/fixtures/_kd_bad.js"
			bad.write_text("x = '</SCRIPT>'", encoding="utf-8")
			try:
				with patch.dict(page.SOURCES, {"kd_js": bad}), self.assertRaises(ValueError):
					page._cache.clear()
					page.asset("kd_js")
			finally:
				bad.unlink()
				page._cache.clear()


class DeskTemplate(unittest.TestCase):
	def test_template_is_noindex_and_loads_nothing_from_assets(self):
		html = (REPO / "illumenate_lighting/templates/pages/kevins_desk.html").read_text(encoding="utf-8")
		self.assertIn('<meta name="robots" content="noindex', html)
		self.assertNotIn("/assets/", html)
		self.assertNotIn("<link", html)

	def test_route_and_patch_are_registered(self):
		hooks = (REPO / "illumenate_lighting/hooks.py").read_text(encoding="utf-8")
		self.assertIn('{"from_route": "/kd/<slug>", "to_route": "kevins_desk"}', hooks)
		patches = (REPO / "illumenate_lighting/patches.txt").read_text(encoding="utf-8")
		self.assertIn("illumenate_lighting.patches.seed_desk_settings", patches.split("[post_model_sync]")[1])


class DeskSchedule(unittest.TestCase):
	def test_weekdays_run_730_to_5_without_gaps_or_overlaps(self):
		for wd in range(1, 6):
			with self.subTest(weekday=wd):
				blocks = schedule.day(wd)
				self.assertEqual(blocks[0]["start"], 7 * 60 + 30)
				self.assertEqual(blocks[-1]["end"], 17 * 60)
				for a, b in pairwise(blocks):
					self.assertEqual(a["end"], b["start"], (a, b))
				self.assertTrue(all(b["hat"] in schedule.HATS for b in blocks if b["kind"] != "lunch"))
				self.assertEqual(next(b for b in blocks if b["kind"] == "lunch")["hat"], None)

	def test_weekends_are_empty(self):
		self.assertEqual((schedule.day(6), schedule.day(7)), ([], []))

	def test_deep_work_follows_the_day_theme(self):
		expected = {1: "growth", 2: "product", 3: "apps", 4: "systems", 5: "growth"}
		for wd, hat in expected.items():
			deep = [b for b in schedule.day(wd) if b["kind"] == "deep"]
			self.assertEqual([b["hat"] for b in deep], [hat])
			self.assertEqual(deep[0]["start"], 13 * 60)
		self.assertEqual(
			schedule.day(4)[6]["title"], "Deep work: Systems (ERPNext, CAD toolkit, configurator)"
		)

	def test_monday_kickoff_and_friday_review(self):
		mon = {b["kind"]: b for b in schedule.day(1)}
		self.assertEqual((mon["kickoff"]["start"], mon["kickoff"]["end"]), (600, 645))
		self.assertEqual(mon["ops"]["start"], 645)
		self.assertNotIn("huddle", mon)
		fri = {b["kind"]: b for b in schedule.day(5)}
		self.assertEqual((fri["deep"]["end"], fri["review"]["start"], fri["review"]["end"]), (900, 900, 930))
		self.assertEqual(fri["review"]["label"], "3:00\u20133:30")
		tue = [b["kind"] for b in schedule.day(2)]
		self.assertEqual(
			tue, ["triage", "customer", "huddle", "ops", "lunch", "inbox", "deep", "customer", "shutdown"]
		)

	def test_payload_is_json_ready(self):
		import json

		data = json.loads(json.dumps(schedule.payload()))
		self.assertEqual(data["tz"], "America/Los_Angeles")
		self.assertEqual(len(data["hats"]), 6)
		self.assertEqual(set(data["days"]), {str(d) for d in range(1, 8)})


if __name__ == "__main__":
	unittest.main()
