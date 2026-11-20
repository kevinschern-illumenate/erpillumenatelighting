# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Plain formatting rules for customer and supplier emails. No Frappe imports.

Email templates print what these return, so dates, money and wording look the same
in every email no matter which screen (Desk composer, Notification, Helpdesk, CRM,
RFQ) rendered it, and a missing value is always "" rather than "None".
"""

from datetime import date, datetime
from html import escape

CURRENCY_SYMBOLS = {"USD": "$", "CAD": "CA$", "EUR": "€", "GBP": "£", "AUD": "A$", "MXN": "MX$"}

# Sales Order "Hold Reason" values are staff shorthand; customers read these instead.
HOLD_MESSAGES = {
	"Hold for Release": (
		"Your order is built to be ready, and we're holding it until you tell us to release it. "
		"Reply to this email when you'd like it to ship."
	),
	"Hold for Confirmation": (
		"We need you to confirm a few details before we can move your order forward. "
		"Reply to this email and we'll walk through them with you."
	),
	"Hold for Ship": (
		"Your order is ready, and we're holding it until we have your go-ahead to ship. "
		"Reply with the date that works for you and any delivery details."
	),
}
HOLD_FALLBACK = "Your order is on hold until we hear from you. Reply to this email and we'll sort it out."

# When the order leaves our warehouse: the production board's estimate, then the likely ship
# date, then the order's Delivery Date (the board's own fallback). The staff-confirmed
# delivery date is a different thing, the delivery promise made to the buyer before
# approval and locked after submit, so it is shown on its own (see ``delivery_promise``).
SHIP_DATE_FIELDS = ("ill_estimated_ship_date", "ill_likely_ship_date", "delivery_date")
SHIP_DATE_LABEL = "Estimated ship date"
PROMISE_LABEL = "Confirmed delivery date"


def as_date(value):
	"""A date from a date, datetime or 'YYYY-MM-DD...' string; None when blank or unreadable."""
	if not value:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	try:
		return date.fromisoformat(str(value).strip()[:10])
	except ValueError:
		return None


def fmt_date(value):
	"""'November 18, 2026'; '' when blank."""
	d = as_date(value)
	return f"{d:%B} {d.day}, {d.year}" if d else ""


def fmt_short_date(value):
	"""'Nov 18, 2026'; '' when blank."""
	d = as_date(value)
	return f"{d:%b} {d.day}, {d.year}" if d else ""


def days_between(start, end):
	"""Whole days from ``start`` to ``end`` (negative when ``end`` is earlier); None if either is blank."""
	a, b = as_date(start), as_date(end)
	return (b - a).days if a and b else None


def to_number(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def fmt_money(value, currency="USD"):
	"""'$1,234.50' for USD, '1,234.50 SEK' for currencies without a known symbol."""
	amount = round(to_number(value), 2)
	sign = "-" if amount < 0 else ""
	digits = f"{abs(amount):,.2f}"
	currency = (currency or "USD").upper()
	symbol = CURRENCY_SYMBOLS.get(currency)
	return f"{sign}{symbol}{digits}" if symbol else f"{sign}{digits} {currency}"


def fmt_qty(value):
	"""'12' for whole numbers, '12.5' otherwise."""
	number = to_number(value)
	return str(int(number)) if number == int(number) else f"{number:g}"


def clean(value):
	"""A trimmed string; '' for None/blank."""
	if value is None:
		return ""
	return str(value).strip()


def first_word(value):
	text = clean(value)
	return text.split()[0] if text else ""


def unique(values):
	"""Drop blanks and repeats, keep first-seen order."""
	seen, out = set(), []
	for value in values:
		if value and value not in seen:
			seen.add(value)
			out.append(value)
	return out


def text_to_html(value):
	"""Escape a Small Text value and keep its line breaks."""
	text = clean(value)
	return escape(text).replace("\n", "<br>") if text else ""


def ship_date(order):
	"""(formatted date, label) for a Sales Order dict, using SHIP_DATE_FIELDS precedence."""
	for field in SHIP_DATE_FIELDS:
		value = order.get(field)
		if as_date(value):
			return fmt_date(value), SHIP_DATE_LABEL
	return "", ""


def delivery_promise(order):
	"""(formatted date, label) for the staff-confirmed delivery date; ("", "") when not confirmed."""
	value = order.get("ill_confirmed_delivery_date")
	return (fmt_date(value), PROMISE_LABEL) if as_date(value) else ("", "")


def hold_message(reason):
	"""Customer wording for a Sales Order Hold Reason; '' when not on hold."""
	reason = clean(reason)
	if not reason:
		return ""
	return HOLD_MESSAGES.get(reason, HOLD_FALLBACK)


def overdue_stage(days_overdue):
	"""'' (not overdue), 'first' (1-14 days), 'second' (15-29) or 'final' (30+): sets the overdue email's tone."""
	if days_overdue is None or days_overdue <= 0:
		return ""
	if days_overdue < 15:
		return "first"
	if days_overdue < 30:
		return "second"
	return "final"


# Purchase order rows that match on all of these print as one line with the quantities
# added up (a configured fixture breaks into parts, so one part repeats once per fixture).
MERGE_KEY_FIELDS = (
	"item_code",
	"uom",
	"rate",
	"schedule_date",
	"supplier_part_no",
	"ill_supplier_description",
	"ill_section_label",
	"ill_fixture_type",
)
MERGE_SUM_FIELDS = ("qty", "stock_qty", "amount")
_LINE_FIELDS = (*MERGE_KEY_FIELDS, *MERGE_SUM_FIELDS, "item_name", "stock_uom")


def _merge_key_value(value):
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		return round(float(value), 6)
	return clean(value)


def merge_same_lines(rows):
	"""Rows that match on MERGE_KEY_FIELDS as one row each, quantities and amounts added up.

	Lines keep the position of their first row. Rows without an item code (section
	headers) are never merged. Returns plain dicts of the fields ``summarize_lines`` reads.
	"""
	merged, groups = [], {}
	for row in rows or []:
		values = {field: row.get(field) for field in _LINE_FIELDS}
		if not clean(values["item_code"]):
			merged.append(values)
			continue
		key = tuple(_merge_key_value(values[field]) for field in MERGE_KEY_FIELDS)
		target = groups.get(key)
		if target is None:
			groups[key] = values
			merged.append(values)
			continue
		for field in MERGE_SUM_FIELDS:
			target[field] = round(to_number(target[field]) + to_number(values[field]), 9)
	return merged


def summarize_lines(rows, limit=15, currency="USD", with_amounts=True, merge=False):
	"""Email-sized line summaries from transaction item rows.

	The label is how customers know their lines: fixture type and section/room first,
	the item name when the row was not configured. ``merge`` combines repeated lines
	(``merge_same_lines``). Returns (lines, how many more).
	"""
	if merge:
		rows = merge_same_lines(rows)
	lines = []
	for row in rows or []:
		fixture_type = clean(row.get("ill_fixture_type"))
		section = clean(row.get("ill_section_label"))
		item_name = clean(row.get("item_name")) or clean(row.get("item_code"))
		if fixture_type and section:
			label = f"{fixture_type} - {section}"
		else:
			label = fixture_type or section or item_name
		detail = item_name if (fixture_type or section) and item_name != label else ""
		lines.append(
			{
				"label": label,
				"detail": detail,
				"item_code": clean(row.get("item_code")),
				"supplier_part_no": clean(row.get("supplier_part_no")),
				"qty": fmt_qty(row.get("qty")),
				"uom": clean(row.get("uom")) or clean(row.get("stock_uom")),
				"rate": fmt_money(row.get("rate"), currency) if with_amounts else "",
				"amount": fmt_money(row.get("amount"), currency) if with_amounts else "",
				"required_by": fmt_short_date(row.get("schedule_date")),
			}
		)
	limit = max(int(limit or 0), 1)
	return lines[:limit], max(len(lines) - limit, 0)
