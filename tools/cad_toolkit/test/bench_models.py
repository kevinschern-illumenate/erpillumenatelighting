"""Benchmark models for the browser LISP spike (W-0.1), and the Python interpreter's baseline times.

Takes the largest drawing model the CAD tests pass to ``il-check`` (from the trace written by
``trace_mini_lisp.py``), scales its runs to 20, 200 and 1,000 (new ids and handles, every other run given
an arc), and times the ILQUOTE steps in ``mini_lisp``: ``il-check``, ``il-model-hash`` (which builds the
package content, writes its JSON and hashes it with the LISP SHA-256), ``il-package`` and
``il-json-text``. Writes the models for ``packages/cad-lisp`` to time the same calls::

    python -B -m tools.cad_toolkit.test.bench_models \
        --trace tools/system_designer/fixtures/cad/web/lisp-trace.json \
        --out tools/system_designer/fixtures/cad/web/bench-models.json
"""

import argparse
import copy
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.cad_toolkit.test import mini_lisp

PURE = ("il-util", "il-json", "il-math", "il-sha256", "il-catalog", "il-model", "il-controls")
SIZES = (20, 200, 1000)


def decode(value):
	if value is None or isinstance(value, str):
		return value
	if isinstance(value, list):
		return [decode(item) for item in value]
	if "i" in value:
		return value["i"]
	if "r" in value:
		return float(value["r"])
	if "y" in value:
		return mini_lisp.Sym(value["y"])
	if "p" in value:
		return mini_lisp.cons(decode(value["p"][0]), decode(value["p"][1]))
	raise ValueError(value)


def source_model(trace_path):
	data = json.loads(Path(trace_path).read_text(encoding="utf-8"))
	best = None
	for trace in data["traces"]:
		for entry in trace:
			if (
				entry["op"] == "call"
				and entry["name"] == "il-check"
				and "unencodable" not in json.dumps(entry["args"])
			):
				runs = next(
					(item for item in entry["args"][0] if isinstance(item, list) and item[0] == "runs"), None
				)
				count = len(runs) - 1 if runs else 0
				if best is None or count > best[0]:
					best = (count, entry["args"])
	return best[1]


def scaled(model, size):
	model = copy.deepcopy(model)
	runs_entry = next(item for item in model if isinstance(item, list) and item[0] == "runs")
	originals = runs_entry[1:]
	runs = []
	for index in range(size):
		run = copy.deepcopy(originals[index % len(originals)])
		for field in run:
			if isinstance(field, dict) and field["p"][0] == "id":
				prefix = field["p"][1].split("-")[0]
				field["p"][1] = f"{prefix}-{index + 1:04d}"
			if isinstance(field, dict) and field["p"][0] == "handle":
				field["p"][1] = f"{0x1000 + index:X}"
			if isinstance(field, list) and field[0] == "vertices" and index % 2 and len(field) >= 3:
				first = field[1]
				first[2] = {"r": 0.25}
		runs.append(run)
	runs_entry[1:] = runs
	return model


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--trace", required=True)
	parser.add_argument("--out", required=True)
	parser.add_argument("--repeat", type=int, default=1)
	parser.add_argument("--time", type=int, nargs="*", default=[20], help="sizes to time in Python")
	args = parser.parse_args()
	model, catalog, today = source_model(args.trace)
	interp = mini_lisp.Interpreter()
	for name in PURE:
		interp.load(REPO / f"tools/cad_toolkit/lisp/{name}.lsp")
	lisp_catalog = decode(catalog)
	out = {"schema": "lisp-bench/1", "catalog": catalog, "today": today, "models": {}, "python_ms": {}}
	for size in SIZES:
		out["models"][str(size)] = scaled(model, size)
	Path(args.out).write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
	for size in args.time:
		encoded = out["models"][str(size)]
		lisp_model = decode(encoded)
		best = {}
		for _ in range(args.repeat):
			times = {}
			start = time.perf_counter()
			issues = interp.call("il-check", lisp_model, lisp_catalog, today)
			times["check"] = time.perf_counter() - start
			start = time.perf_counter()
			interp.call("il-model-hash", lisp_model, lisp_catalog)
			times["hash"] = time.perf_counter() - start
			start = time.perf_counter()
			package = interp.call("il-package", lisp_model, lisp_catalog, issues, "bench")
			times["package"] = time.perf_counter() - start
			start = time.perf_counter()
			text = interp.call("il-json-text", package)
			times["json"] = time.perf_counter() - start
			for key, value in times.items():
				best[key] = min(best.get(key, value), value)
		out["python_ms"][str(size)] = {key: round(value * 1000, 1) for key, value in best.items()}
		out["python_ms"][str(size)]["issues"] = len(issues or [])
		out["python_ms"][str(size)]["package_chars"] = len(text)
		print(size, out["python_ms"][str(size)], file=sys.stderr, flush=True)
		Path(args.out).write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
	return 0


if __name__ == "__main__":
	sys.exit(main())
