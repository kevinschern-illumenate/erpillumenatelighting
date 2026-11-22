"""Compare probe lengths with AutoCAD toolkit ground truth (draw-to-quote spike, WP 2.6).

Usage::

	python3 -m tools.bluebeam_spike.compare_lengths report.json truth.ilq.json [--markdown]
		[--subtypes /PolyLine,/Line] [--assume-unit ft] [--tolerance-pct 1.0] [--out result.json]

``report.json`` is the output of ``probe_pdf``; ``truth.ilq.json`` is the ``ilq/2`` package the
toolkit exported for the same drawing. A run's truth length is the sum of its
``segments[].path_length_in``.

Matching. Measured markups (by default /PolyLine and /Line, i.e. Polylength and Length; Area
polygons are rooms, not runs) are matched to runs by a run id found, in this order, in the
markup's ``extra_keys`` values (Bluebeam custom columns), /Contents, /Subj, then /T. An id
matches as a whole token (not preceded or followed by a letter or digit); when several ids
match, the longest wins, and a tie is ambiguous and left unmatched by id. Several markups with
the same run id are summed (a run drawn as more than one Polylength). Markups without an id are
then matched by order (page, then annotation order) to the runs no markup named, in package
order. Each run reports how it was matched.

Statistics are over matched runs with a non-zero truth length: signed error
``computed - truth`` in inches and in % of truth, mean signed %, mean |%|, max |%|, and p95 |%|
(nearest-rank: the ceil(0.95 n)-th smallest value).
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

from tools.bluebeam_spike.probe_pdf import unit_to_inches

DEFAULT_SUBTYPES = ("/PolyLine", "/Line")
ID_SOURCES = ("extra_keys", "Contents", "Subj", "T")


def truth_runs(package):
	"""``[{"id", "truth_in"}]`` from an ``ilq/2`` package, in package order."""
	if package.get("schema") != "ilq/2":
		raise ValueError(f"expected an ilq/2 package, got schema {package.get('schema')!r}")
	runs = []
	for run in package.get("runs") or []:
		segments = run.get("segments") or []
		runs.append({"id": str(run["id"]), "truth_in": sum(float(s["path_length_in"]) for s in segments)})
	return runs


def _strings(value):
	if isinstance(value, str):
		yield value
	elif isinstance(value, dict):
		for item in value.values():
			yield from _strings(item)
	elif isinstance(value, list):
		for item in value:
			yield from _strings(item)


def _token(run_id):
	return re.compile(rf"(?<![A-Za-z0-9]){re.escape(run_id)}(?![A-Za-z0-9])", re.IGNORECASE)


def find_run_id(markup, run_ids, patterns=None):
	"""Return ``(run_id, source)`` or ``(None, reason)`` for one probe annotation."""
	patterns = patterns or {run_id: _token(run_id) for run_id in run_ids}
	for source in ID_SOURCES:
		texts = list(_strings(markup.get(source)))
		if not texts:
			continue
		found = sorted(
			{run_id for run_id, pattern in patterns.items() if any(pattern.search(t) for t in texts)},
			key=len,
			reverse=True,
		)
		if not found:
			continue
		if len(found) > 1 and len(found[0]) == len(found[1]):
			return None, f"ambiguous in {source}: {', '.join(found)}"
		return found[0], source
	return None, None


def markup_length_in(markup, assume_unit=None):
	if markup.get("computed_length_in") is not None:
		return float(markup["computed_length_in"])
	if markup.get("computed_length") is not None and assume_unit:
		factor = unit_to_inches(assume_unit)
		if factor is None:
			raise ValueError(f"unknown unit {assume_unit!r}")
		return float(markup["computed_length"]) * factor
	return None


def percentile_nearest_rank(values, pct):
	if not values:
		return None
	ordered = sorted(values)
	rank = max(1, math.ceil(pct / 100 * len(ordered)))
	return ordered[rank - 1]


def compare(report, package, *, subtypes=DEFAULT_SUBTYPES, assume_unit=None, tolerance_pct=1.0):
	runs = truth_runs(package)
	run_ids = [run["id"] for run in runs]
	patterns = {run_id: _token(run_id) for run_id in run_ids}
	measured, unmeasured, notes = [], [], []
	for page in report.get("pages") or []:
		for annot in page.get("annotations") or []:
			if annot.get("Subtype") not in subtypes:
				continue
			ref = {"page": page.get("page"), "index": annot.get("index"), "NM": annot.get("NM")}
			length = markup_length_in(annot, assume_unit)
			if length is None:
				unmeasured.append({**ref, "reason": annot.get("length_note") or "no length in inches"})
				continue
			run_id, source = find_run_id(annot, run_ids, patterns)
			if run_id is None and source:
				notes.append(f"page {ref['page']} annot {ref['index']}: {source}")
			measured.append(
				{**ref, "length_in": length, "run_id": run_id, "id_source": source if run_id else None}
			)

	by_run = {run_id: [] for run_id in run_ids}
	for markup in measured:
		if markup["run_id"]:
			by_run[markup["run_id"]].append(markup)
	method = {run_id: "id" for run_id, items in by_run.items() if items}
	leftover_markups = [m for m in measured if not m["run_id"]]
	leftover_runs = [run_id for run_id in run_ids if not by_run[run_id]]
	for run_id, markup in zip(leftover_runs, leftover_markups, strict=False):
		markup["run_id"] = run_id
		by_run[run_id].append(markup)
		method[run_id] = "order"
	unmatched = leftover_markups[len(leftover_runs) :]

	rows = []
	for run in runs:
		items = by_run[run["id"]]
		computed = round(sum(m["length_in"] for m in items), 6) if items else None
		row = {
			"run_id": run["id"],
			"truth_in": round(run["truth_in"], 6),
			"computed_in": computed,
			"error_in": None,
			"error_pct": None,
			"method": method.get(run["id"]),
			"markups": [{"page": m["page"], "index": m["index"], "NM": m["NM"]} for m in items],
		}
		if computed is not None:
			row["error_in"] = round(computed - run["truth_in"], 6)
			if run["truth_in"]:
				row["error_pct"] = round(row["error_in"] / run["truth_in"] * 100, 6)
		rows.append(row)
	return {
		"runs": rows,
		"summary": summarise(rows, tolerance_pct),
		"unmatched_markups": [{k: m[k] for k in ("page", "index", "NM", "length_in")} for m in unmatched],
		"unmeasured_markups": unmeasured,
		"notes": notes,
	}


def summarise(rows, tolerance_pct=1.0):
	scored = [row for row in rows if row["error_pct"] is not None]
	pct = [row["error_pct"] for row in scored]
	abs_pct = [abs(value) for value in pct]
	abs_in = [abs(row["error_in"]) for row in scored]

	def mean(values):
		return round(sum(values) / len(values), 6) if values else None

	return {
		"runs": len(rows),
		"matched": sum(1 for row in rows if row["computed_in"] is not None),
		"matched_by_id": sum(1 for row in rows if row["method"] == "id"),
		"matched_by_order": sum(1 for row in rows if row["method"] == "order"),
		"scored": len(scored),
		"mean_error_pct": mean(pct),
		"mean_abs_error_pct": mean(abs_pct),
		"max_abs_error_pct": round(max(abs_pct), 6) if abs_pct else None,
		"p95_abs_error_pct": percentile_nearest_rank(abs_pct, 95),
		"mean_abs_error_in": mean(abs_in),
		"max_abs_error_in": round(max(abs_in), 6) if abs_in else None,
		"tolerance_pct": tolerance_pct,
		"within_tolerance": sum(1 for value in abs_pct if value <= tolerance_pct),
	}


def _fmt(value, digits=2):
	return "-" if value is None else f"{value:.{digits}f}"


def to_markdown(result):
	lines = [
		"| Run | Truth (in) | Computed (in) | Error (in) | Error % | Matched by |",
		"|---|---:|---:|---:|---:|---|",
	]
	for row in result["runs"]:
		lines.append(
			f"| {row['run_id']} | {_fmt(row['truth_in'])} | {_fmt(row['computed_in'])} | "
			f"{_fmt(row['error_in'])} | {_fmt(row['error_pct'], 3)} | {row['method'] or 'unmatched'} |"
		)
	s = result["summary"]
	lines += [
		"",
		f"Runs {s['runs']}, matched {s['matched']} (id {s['matched_by_id']}, order {s['matched_by_order']}); "
		f"mean error {_fmt(s['mean_error_pct'], 3)} %, mean |error| {_fmt(s['mean_abs_error_pct'], 3)} %, "
		f"max |error| {_fmt(s['max_abs_error_pct'], 3)} %, p95 |error| {_fmt(s['p95_abs_error_pct'], 3)} %; "
		f"{s['within_tolerance']}/{s['scored']} within {s['tolerance_pct']} %. "
		f"Unmatched markups: {len(result['unmatched_markups'])}; "
		f"unmeasured: {len(result['unmeasured_markups'])}.",
	]
	return "\n".join(lines)


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
	parser.add_argument("report", help="probe_pdf JSON report")
	parser.add_argument("truth", help="ilq/2 package exported by the AutoCAD toolkit")
	parser.add_argument("--subtypes", default=",".join(DEFAULT_SUBTYPES), help="annotation subtypes to match")
	parser.add_argument("--assume-unit", help="unit of computed_length when the probe could not convert it")
	parser.add_argument("--tolerance-pct", type=float, default=1.0)
	parser.add_argument("--markdown", action="store_true", help="print a table for the spike report")
	parser.add_argument("--out", help="write the JSON result here")
	args = parser.parse_args(argv)
	report = json.loads(Path(args.report).read_text(encoding="utf-8"))
	package = json.loads(Path(args.truth).read_text(encoding="utf-8"))
	subtypes = tuple(
		s.strip() if s.strip().startswith("/") else f"/{s.strip()}" for s in args.subtypes.split(",")
	)
	result = compare(
		report, package, subtypes=subtypes, assume_unit=args.assume_unit, tolerance_pct=args.tolerance_pct
	)
	payload = json.dumps(result, indent=2, ensure_ascii=False)
	if args.out:
		Path(args.out).write_text(payload + "\n", encoding="utf-8")
	if args.markdown:
		print(to_markdown(result))
	elif not args.out:
		print(payload)
	return 0


if __name__ == "__main__":
	sys.exit(main())
