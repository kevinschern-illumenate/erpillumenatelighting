"""Kevin's Desk at /kd/<slug>: private daily operating page (see illumenate_lighting/kevins_desk).

Anyone but the desk owner, including a guest, gets the site's 404 page (never a login prompt).
The page's CSS and JS are inlined into this gated response instead of being served from /assets,
so nothing about the desk is public. Styles are the Command Center's own cc.css plus kd.css.
"""

from pathlib import Path

import frappe

from illumenate_lighting.kevins_desk import access, schedule

no_cache = 1
sitemap = 0

APP = Path(__file__).resolve().parents[2]
SOURCES = {
	"cc_css": APP / "command_center/page/cc.css",
	"kd_css": APP / "kevins_desk/page/kd.css",
	"kd_js": APP / "kevins_desk/page/kd.js",
}
CLOSERS = {"cc_css": "</style", "kd_css": "</style", "kd_js": "</script"}
_cache = {}


def asset(key):
	"""Read an inlined asset once per file version; refuse one that would close its own tag."""
	path = SOURCES[key]
	stamp = path.stat().st_mtime_ns
	hit = _cache.get(key)
	if hit and hit[0] == stamp:
		return hit[1]
	text = path.read_text(encoding="utf-8")
	if CLOSERS[key] in text.lower():
		raise ValueError(f"{path.name} contains {CLOSERS[key]}; it cannot be inlined")
	_cache[key] = (stamp, text)
	return text


def get_context(context):
	conf = access.page_gate(frappe.form_dict.get("slug"))
	user = conf.get("desk_owner")
	context.update(
		{
			"title": "Kevin's Desk",
			"no_cache": 1,
			"sitemap": 0,
			"cc_css": asset("cc_css"),
			"kd_css": asset("kd_css"),
			"kd_js": asset("kd_js"),
			"desk": {
				"user": user,
				"first_name": (frappe.db.get_value("User", user, "first_name") or "").strip(),
				"schedule": schedule.payload(),
				"command_center": "/command-center",
				"api": {
					"today": "/api/method/illumenate_lighting.kevins_desk.api.today",
					"signals": "/api/method/illumenate_lighting.kevins_desk.api.signals",
					"connect": "/api/method/illumenate_lighting.kevins_desk.api.connect_mailbox",
				},
			},
			"csrf_token": frappe.sessions.get_csrf_token(),
		}
	)
	return context
