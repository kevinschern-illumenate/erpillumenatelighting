"""Starter CAD run styles: configuration presets with short drawing codes (CAD plan WP 1.2).

Reads a CSV with the columns in ``COLUMNS`` (see ``cad_starter_presets.example.csv``) and saves one
``ilL-Configuration-Preset`` per row for its ``user``, through the same validation the portal uses
(``portal.presets.prepare``/``save``: label, family, template offered to that user, price-free
request, sharing rules, drawing code format and uniqueness). Rows are also re-checked with
``presets.revalidate``: a starter style whose options the template no longer offers is refused, not
silently trimmed. A row with the label of an existing preset of that user replaces it.

Dry run by default: every row is checked and what would happen is printed; nothing is written. With
``dry_run=False`` all rows are saved in one transaction, or none when any row fails.

From the bench directory (``frappe-bench``)::

    bench --site SITE console
    >>> import runpy
    >>> seed = runpy.run_path("apps/illumenate_lighting/tools/seed_imports/cad_starter_presets.py")
    >>> seed["run"]("/path/to/presets.csv")                  # dry run
    >>> seed["run"]("/path/to/presets.csv", dry_run=False)   # save

or, from ``frappe-bench/sites``::

    ../env/bin/python ../apps/illumenate_lighting/tools/seed_imports/cad_starter_presets.py \\
        --site SITE /path/to/presets.csv [--commit]

The presets kill switch (``site_flags.presets_enabled``) is not consulted: seeding prepares the library
before the feature is switched on.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

COLUMNS = (
	"customer",
	"user",
	"label",
	"family",
	"template",
	"selections_json",
	"cad_code",
	"shared_with_company",
)
EXAMPLE = Path(__file__).resolve().parent / "cad_starter_presets.example.csv"


def read_rows(path):
	"""``[(line number, row)]`` from the CSV at ``path``; refuses a file without the expected columns."""
	with open(path, newline="", encoding="utf-8-sig") as handle:
		reader = csv.DictReader(handle)
		missing = [column for column in COLUMNS if column not in (reader.fieldnames or [])]
		if missing:
			raise ValueError(f"{path}: missing column(s) {', '.join(missing)}")
		return [
			(index, {key: (value or "").strip() for key, value in row.items() if key})
			for index, row in enumerate(reader, start=2)
			if any((value or "").strip() for value in row.values() if isinstance(value, str))
		]


def request_for(row):
	"""The configurator request a row describes (``selections_json`` is a JSON object or empty)."""
	text = row.get("selections_json") or "{}"
	try:
		selections = json.loads(text)
	except ValueError as error:
		raise ValueError(f"selections_json is not valid JSON ({error})") from None
	if not isinstance(selections, dict):
		raise ValueError("selections_json must be a JSON object")
	return {"family": row.get("family"), "template": row.get("template"), "selections": selections}


def _message(error):
	return str(error) or error.__class__.__name__


def _check(row, presets, actor, frappe):
	"""Validate one row as its user would save it: ``(name it replaces, values)`` or an error."""
	user = row.get("user")
	if not user or not frappe.db.exists("User", user):
		raise ValueError(f"user {user or '(blank)'} does not exist")
	if actor.is_guest:
		raise ValueError(f"user {user} is disabled")
	expected = row.get("customer") or None
	owner = actor.customer if actor.customer and not actor.is_internal else None
	if expected != owner:
		raise ValueError(f"user {user} belongs to company {owner or '(none)'}, not {expected or '(none)'}")
	request = request_for(row)
	name, values = presets.prepare(
		actor,
		row.get("label"),
		request,
		shared_with_company=row.get("shared_with_company") or "0",
		cad_code=row.get("cad_code") or None,
	)
	checked, problems = presets.revalidate(json.loads(values["request_json"]))
	if checked is None or problems:
		raise ValueError("; ".join(str(problem) for problem in problems) or "the preset cannot be used")
	return name, values, request


def run(path, dry_run=True, out=None):
	"""Seed the presets in the CSV at ``path`` (inside a connected Frappe site).

	Returns ``{"created": n, "replaced": n, "errors": [(line, message)], "dry_run": bool}``. Nothing is
	written on a dry run, or when any row fails.
	"""
	import frappe

	from illumenate_lighting.illumenate_lighting.portal import presets
	from illumenate_lighting.illumenate_lighting.portal.access import Actor

	out = out or sys.stdout
	rows = read_rows(path)
	result = {"created": 0, "replaced": 0, "errors": [], "dry_run": bool(dry_run)}
	seen_labels = {}
	seen_codes = {}
	session_user = frappe.session.user
	try:
		for line, row in rows:
			try:
				# template_problem and the rollout check answer for the signed-in user: be that user.
				frappe.set_user(row.get("user") or "Guest")
				actor = Actor(row.get("user"))
				name, values, request = _check(row, presets, actor, frappe)
				label_key = (actor.user, values["label"])
				if label_key in seen_labels:
					raise ValueError(f"same user and label as line {seen_labels[label_key]}")
				seen_labels[label_key] = line
				code = values.get("cad_code")
				if code:
					scope = values["customer"] or f"user:{actor.user}"
					code_key = (scope, code)
					if code_key in seen_codes:
						raise ValueError(f"drawing code {code} is also on line {seen_codes[code_key]}")
					seen_codes[code_key] = line
				action = "replace" if name else "create"
				verb = f"would {action}" if dry_run else ("replaced" if name else "created")
				if not dry_run:
					presets.save(
						actor,
						row.get("label"),
						request,
						shared_with_company=row.get("shared_with_company") or "0",
						cad_code=row.get("cad_code") or None,
					)
				result["replaced" if name else "created"] += 1
				shared = " shared" if values["shared_with_company"] else ""
				print(
					f"line {line}: {verb}{shared} preset {values['label']!r} for {actor.user}"
					f" ({values['family']} {values['template'] or '-'}, code {code or '-'})",
					file=out,
				)
			except Exception as error:
				result["errors"].append((line, _message(error)))
				print(f"line {line}: ERROR {_message(error)}", file=out)
	finally:
		frappe.set_user(session_user)
	if dry_run:
		frappe.db.rollback()
		print(
			f"Dry run: {len(rows)} row(s) checked, {len(result['errors'])} error(s); nothing saved.", file=out
		)
	elif result["errors"]:
		frappe.db.rollback()
		result["created"] = result["replaced"] = 0
		print(f"{len(result['errors'])} row(s) failed; nothing saved.", file=out)
	else:
		frappe.db.commit()
		print(f"Saved: {result['created']} created, {result['replaced']} replaced.", file=out)
	return result


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("csv", nargs="?", default=str(EXAMPLE), help="the presets CSV")
	parser.add_argument("--site", required=True, help="the site to seed (run from frappe-bench/sites)")
	parser.add_argument("--sites-path", default=".", help="the sites folder (default: current folder)")
	parser.add_argument("--commit", action="store_true", help="save the presets (default: dry run)")
	args = parser.parse_args(argv)
	import frappe

	frappe.init(site=args.site, sites_path=args.sites_path)
	frappe.connect()
	try:
		result = run(args.csv, dry_run=not args.commit)
	finally:
		frappe.destroy()
	return 1 if result["errors"] else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
