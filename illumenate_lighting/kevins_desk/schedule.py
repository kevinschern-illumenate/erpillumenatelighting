"""Kevin's daily schedule, day themes and hats (Pacific time).

One source of truth: the page receives ``payload()`` as JSON and works out the NOW bar in the browser,
and later phases (brief, snooze to a block, week view) read the same blocks from here.

Change a block's hat or time here, nowhere else. No Frappe import, so it is unit-tested directly.
"""

TIME_ZONE = "America/Los_Angeles"

# Hats in display order: key -> label
HATS = {
	"sales": "Sales & Customer",
	"ops": "Operations",
	"product": "Product & Engineering",
	"apps": "Applications & Design",
	"systems": "Systems",
	"growth": "Growth & Leadership",
}

# Deep-work theme per ISO weekday (Mon=1 .. Fri=5): hat key + what the afternoon is for
THEMES = {
	1: ("growth", "Growth & Leadership"),
	2: ("product", "Product & Engineering"),
	3: ("apps", "Applications & Design"),
	4: ("systems", "Systems (ERPNext, CAD toolkit, configurator)"),
	5: ("growth", "Growth & Leadership"),
}

THEME = "theme"  # placeholder hat: the block takes the day's deep-work theme

# (start, end, kind, title, hat). Lunch has no hat.
BASE_DAY = (
	("07:30", "08:00", "triage", "Triage & plan", "sales"),
	("08:00", "10:00", "customer", "Customer block 1", "sales"),
	("10:00", "10:15", "huddle", "Team huddle", "growth"),
	("10:15", "12:00", "ops", "Ops block", "ops"),
	("12:00", "12:30", "lunch", "Lunch", None),
	("12:30", "13:00", "inbox", "Inbox sweep 2", "sales"),
	("13:00", "15:30", "deep", "Deep work", THEME),
	("15:30", "16:30", "customer", "Customer block 2", "sales"),
	("16:30", "17:00", "shutdown", "Shutdown", "growth"),
)

# Per-weekday replacements: weekday -> {kind of the block replaced: [blocks that replace it]}
OVERRIDES = {
	# Monday 10:00 is a 45-minute team kickoff; the ops block starts after it.
	1: {
		"huddle": [("10:00", "10:45", "kickoff", "Team kickoff", "growth")],
		"ops": [("10:45", "12:00", "ops", "Ops block", "ops")],
	},
	# Friday 3:00 is the weekly review, inside the deep-work slot.
	5: {
		"deep": [
			("13:00", "15:00", "deep", "Deep work", THEME),
			("15:00", "15:30", "review", "Weekly review", "growth"),
		],
	},
}


def minutes(hhmm):
	hours, mins = hhmm.split(":")
	return int(hours) * 60 + int(mins)


def label(hhmm):
	"""'13:00' -> '1:00'"""
	hours, mins = (int(x) for x in hhmm.split(":"))
	return f"{(hours - 1) % 12 + 1}:{mins:02d}"


def day(weekday):
	"""Blocks for an ISO weekday (Mon=1). Weekends have none."""
	if weekday not in THEMES:
		return []
	theme_hat, theme_label = THEMES[weekday]
	swaps = OVERRIDES.get(weekday, {})
	rows = []
	for block in BASE_DAY:
		rows.extend(swaps.get(block[2], [block]))
	out = []
	for start, end, kind, title, hat in rows:
		if hat == THEME:
			hat, title = theme_hat, f"{title}: {theme_label}"
		out.append(
			{
				"start": minutes(start),
				"end": minutes(end),
				"label": f"{label(start)}\u2013{label(end)}",  # en dash
				"kind": kind,
				"title": title,
				"hat": hat,
			}
		)
	return out


def payload():
	"""Everything the page needs to draw the NOW bar and the schedule."""
	return {
		"tz": TIME_ZONE,
		"hats": [{"key": key, "label": text} for key, text in HATS.items()],
		"themes": {str(wd): {"hat": hat, "label": text} for wd, (hat, text) in THEMES.items()},
		"days": {str(wd): day(wd) for wd in range(1, 8)},
	}
