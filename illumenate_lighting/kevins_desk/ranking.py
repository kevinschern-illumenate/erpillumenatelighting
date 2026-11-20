"""Rank everything on the desk by Kevin's priority stack, then group it by hat. Pure Python, no Frappe.

Priority stack, highest first:
    1 Customer blocked or order at risk   2 New sales   3 Converting sales   4 Tickets
    5 Unblocking the team   6 Projects   7 Admin

Within a level: things Kevin owes before threads he is waiting on, then late first, then due today,
then oldest first. Groups (one per hat) are ordered by their most urgent item, so the hat that needs
Kevin most comes first.
"""

import re

STACK = {
	1: "Customer blocked · order at risk",
	2: "New sales",
	3: "Converting sales",
	4: "Tickets",
	5: "Unblocking the team",
	6: "Projects",
	7: "Admin",
}

# Topic of a thread or ToDo from its subject and snippet; the first that matches wins.
TOPICS = (
	(
		"risk",
		re.compile(
			r"\b(urgent|asap|emergency|not working|stopped working|isn'?t working|fail(?:ed|ure|ing)?|"
			r"flicker\w*|defect\w*|damaged|broken|wrong|missing|late|delay(?:ed|s)?|where is|"
			r"back ?order\w*|on hold|cancel\w*|complain\w*|escalat\w*)\b",
			re.I,
		),
	),
	(
		"quote",
		re.compile(
			r"\b(quote|quotes|quoted|quotation|rfq|rfp|pricing|price|prices|proposal|bid|budget\w*|"
			r"estimate|take-?off|specs?|specification|submittal|dealer|distributor|lead time|"
			r"availability|samples?)\b",
			re.I,
		),
	),
	(
		"order",
		re.compile(
			r"(\bpurchase order\b|\bp\.?o\.?\s*#|\bpo\s*\d|\border confirmation\b|\bdeposit\b|\binvoice\b|"
			r"\bpayment\b|\bship date\b|\btracking\b|\bshipped\b|\bdelivery\b|\brelease\b)",
			re.I,
		),
	),
	(
		"support",
		re.compile(
			r"\b(warranty|rma|return|install(?:ation|ing)?|troubleshoot\w*|support|dimm(?:ing|er)|driver)\b",
			re.I,
		),
	),
)

# ToDo linked record -> (stack, hat)
REF_STACK = {
	"Quotation": (2, "sales"),
	"Lead": (2, "sales"),
	"Opportunity": (2, "sales"),
	"ilL-Quote-Request": (2, "sales"),
	"Customer": (2, "sales"),
	"Sales Order": (3, "ops"),
	"Purchase Order": (3, "ops"),
	"Material Request": (3, "ops"),
	"Work Order": (3, "ops"),
	"Delivery Note": (3, "ops"),
	"ilL-Order-Intake": (3, "ops"),
	"HD Ticket": (4, "sales"),
	"Issue": (4, "sales"),
	"Project": (6, "product"),
	"Task": (6, "product"),
	"ilL-Project": (6, "apps"),
}
TOPIC_STACK = {"risk": (1, "sales"), "quote": (2, "sales"), "order": (3, "ops"), "support": (4, "sales")}
FLAG_RANK = {"late": 0, "today": 1}


def topic(*texts):
	text = " ".join(t for t in texts if t)
	for name, pattern in TOPICS:
		if pattern.search(text):
			return name
	return None


def thread_stack(thread):
	"""(stack, hat, topic) for a Gmail thread. thread["who"] is team / customer / supplier / lead / unknown."""
	t = topic(thread.get("title"), thread.get("snippet"))
	who = thread.get("who")
	if t == "risk":
		return 1, ("ops" if who == "supplier" else "sales"), t
	if who == "team":
		return 5, "growth", t
	if who == "supplier":
		return 3, "ops", t
	if t in TOPIC_STACK:
		return (*TOPIC_STACK[t], t)
	return 2, "sales", t  # a customer, dealer or new sender writing in: treat as new sales


def todo_stack(todo, team):
	ref = todo.get("ref") or {}
	if ref.get("dt") in REF_STACK:
		return REF_STACK[ref["dt"]]
	if (todo.get("assigned_by") or "").lower() in team:
		return 5, "growth"
	t = topic(todo.get("title"))
	return TOPIC_STACK.get(t, (7, None))


def sort_key(item):
	waiting = 1 if item.get("kind") == "waiting" else 0
	return (
		item["stack"],
		waiting,
		FLAG_RANK.get(item.get("flag"), 2),
		item.get("date") or "9999-12-31",
		item["id"],
	)


def merge(pipeline, mail, team, hats):
	"""One ranked list from the pipeline widgets, the owner's ToDos and Gmail threads, plus hat groups.

	pipeline: pipeline.build() output; mail: mail.build() output (or None); team: team.resolve();
	hats: schedule.HATS. Returns {"groups": [{hat, label, items}], "top": first 10 ranked items,
	"counts": {stack: n}, "total": n}. Every item carries its overall "rank".
	"""
	items, seen = [], set()
	for w in (pipeline or {}).get("widgets") or []:
		for it in w.get("items") or []:
			if it["id"] not in seen:
				seen.add(it["id"])
				items.append(dict(it, source="erpnext"))
	for todo in (pipeline or {}).get("todos") or []:
		stack, hat = todo_stack(todo, team)
		items.append(dict(todo, stack=stack, hat=hat, source="todo"))
	for thread in (mail or {}).get("threads") or []:
		items.append(dict(thread, source="gmail"))
	items.sort(key=sort_key)
	groups, by_hat = [], {}
	for rank, it in enumerate(items, 1):
		it["rank"] = rank
		key = it.get("hat") or "none"
		if key not in by_hat:
			by_hat[key] = {"hat": key, "label": hats.get(key, "No hat · admin"), "items": []}
			groups.append(by_hat[key])
		by_hat[key]["items"].append(it)
	counts = {}
	for it in items:
		counts[it["stack"]] = counts.get(it["stack"], 0) + 1
	return {"groups": groups, "top": items[:10], "counts": counts, "total": len(items)}
