"""Disabled Items are never offered, priced or built.

ERPNext's ``Item.disabled`` is the one switch: a spec, map row, offering or
variant whose Item is disabled is treated as if it did not exist, and a build
that would still consume a disabled Item is refused.
"""

import frappe


def _value(row, field):
	return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


def disabled_items(item_codes) -> set[str]:
	"""The disabled Items among *item_codes*."""
	codes = sorted({code for code in item_codes if code})
	if not codes:
		return set()
	return set(frappe.db.get_all("Item", filters={"name": ["in", codes], "disabled": 1}, pluck="name") or [])


def enabled_rows(rows, field: str = "item") -> list:
	"""*rows* without those whose *field* Item is disabled; rows with no Item are kept."""
	rows = list(rows or [])
	off = disabled_items(_value(row, field) for row in rows)
	return [row for row in rows if _value(row, field) not in off] if off else rows


def disabled_tape_offerings(offerings) -> set[str]:
	"""The tape offerings among *offerings* whose tape spec's Item is disabled."""
	names = sorted({name for name in offerings if name})
	if not names:
		return set()
	rows = frappe.db.sql(
		"""select o.name from `tabilL-Rel-Tape Offering` o
		join `tabilL-Spec-LED Tape` s on s.name = o.tape_spec
		join `tabItem` i on i.name = s.item
		where i.disabled = 1 and o.name in %(names)s""",
		{"names": names},
	)
	return {row[0] for row in rows or []}


def enabled_tape_specs(spec_names) -> list[str]:
	"""*spec_names* (LED Tape/Neon specs) without those whose Item is disabled, order kept."""
	names = [name for name in spec_names or [] if name]
	if not names:
		return []
	rows = frappe.db.sql(
		"""select s.name from `tabilL-Spec-LED Tape` s
		join `tabItem` i on i.name = s.item
		where i.disabled = 1 and s.name in %(names)s""",
		{"names": sorted(set(names))},
	)
	off = {row[0] for row in rows or []}
	return [name for name in names if name not in off]


def allowed_tape_offering_rows(template) -> list:
	"""A Fixture Template's allowed tape offering rows whose tape Item is enabled."""
	rows = list(getattr(template, "allowed_tape_offerings", None) or [])
	off = disabled_tape_offerings(_value(row, "tape_offering") for row in rows)
	return [row for row in rows if _value(row, "tape_offering") not in off] if off else rows


def assert_enabled(item_codes, what: str = "this configuration") -> None:
	"""Refuse *what* when any of *item_codes* is a disabled Item."""
	off = disabled_items(item_codes)
	if off:
		raise ValueError(
			f"{', '.join(sorted(off))} {'is a disabled Item' if len(off) == 1 else 'are disabled Items'} "
			f"and cannot be used in {what}. Choose different options or re-enable the Item."
		)
