"""Record every interpreter interaction the CAD LISP tests make, for the TypeScript port (W-0.1).

Runs ``tests/portal_unit/test_cad_lisp.py`` and ``tests/portal_unit/test_drawing_checks.py`` with
``mini_lisp.Interpreter`` patched to log, per interpreter instance, every ``load``, ``run``, ``set``,
``get`` and ``call`` with its encoded arguments and result (or the error it raised), plus the contents of
every file the LISP opens for reading. ``packages/cad-lisp`` replays the log and must produce the same
results. Usage::

    python -B -m tools.cad_toolkit.test.trace_mini_lisp --out tools/system_designer/fixtures/cad/web/lisp-trace.json
"""

import argparse
import json
import math
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests/portal_unit"))

from tools.cad_toolkit.test import mini_lisp

REPO_TEXT = str(REPO)
TRACES = []
_current = []


def rel(text):
	return text.replace(REPO_TEXT, "<repo>") if isinstance(text, str) else text


class Unencodable(Exception):
	pass


def encode(value, depth=0):
	if depth > 200:
		raise Unencodable("too deep")
	if value is None:
		return None
	if isinstance(value, bool):
		raise Unencodable("python bool")
	if isinstance(value, int):
		return {"i": value}
	if isinstance(value, float):
		if math.isnan(value):
			return {"r": "nan"}
		if math.isinf(value):
			return {"r": "inf" if value > 0 else "-inf"}
		return {"r": value}
	if isinstance(value, str):
		return rel(value)
	if isinstance(value, mini_lisp.Sym):
		return {"y": value.name}
	if isinstance(value, mini_lisp.Pair):
		return {"p": [encode(value.car, depth + 1), encode(value.cdr, depth + 1)]}
	if isinstance(value, list):
		return [encode(item, depth + 1) for item in value]
	if isinstance(value, mini_lisp.Function):
		return {"fn": value.name}
	if isinstance(value, mini_lisp.CaughtError):
		return {"err": value.message}
	if isinstance(value, mini_lisp.FileHandle):
		return {"file": True}
	raise Unencodable(type(value).__name__)


def safe(value):
	try:
		return encode(value)
	except Unencodable as error:
		return {"unencodable": str(error)}


def patch():
	original_init = mini_lisp.Interpreter.__init__

	def init(self, *args, **kwargs):
		original_init(self, *args, **kwargs)
		self._trace = []
		TRACES.append(self._trace)

	mini_lisp.Interpreter.__init__ = init

	def wrap(name, describe):
		method = getattr(mini_lisp.Interpreter, name)

		def wrapped(self, *args):
			entry = describe(*args)
			_current.append(self._trace)
			try:
				result = method(self, *args)
			except Exception as error:
				entry["error"] = type(error).__name__
				self._trace.append(entry)
				raise
			finally:
				_current.pop()
			if name != "set":
				entry["result"] = safe(result)
			self._trace.append(entry)
			return result

		setattr(mini_lisp.Interpreter, name, wrapped)

	wrap("load", lambda path: {"op": "load", "path": rel(str(path))})
	wrap("run", lambda text: {"op": "run", "text": text})
	wrap("set", lambda name, value: {"op": "set", "name": name, "value": safe(value)})
	wrap("get", lambda name: {"op": "get", "name": name})
	wrap("call", lambda name, *args: {"op": "call", "name": name, "args": [safe(arg) for arg in args]})

	original_file = mini_lisp.FileHandle.__init__

	def file_init(self, path, mode):
		original_file(self, path, mode)
		if mode == "r" and _current:
			with open(path, encoding="utf-8", newline="") as handle:
				_current[-1].append({"op": "file", "path": rel(str(path)), "content": handle.read()})

	mini_lisp.FileHandle.__init__ = file_init


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--out", required=True)
	args = parser.parse_args()
	patch()
	loader = unittest.TestLoader()
	suite = unittest.TestSuite()
	for name in ("test_cad_lisp", "test_drawing_checks"):
		suite.addTests(loader.loadTestsFromName(name))
	result = unittest.TextTestRunner(verbosity=0, stream=sys.stderr).run(suite)
	traces = [trace for trace in TRACES if trace]
	# A load is recorded after the file ran; replay needs it before the calls it made, which it is.
	Path(args.out).parent.mkdir(parents=True, exist_ok=True)
	Path(args.out).write_text(
		json.dumps({"schema": "lisp-trace/1", "traces": traces}, separators=(",", ":")), encoding="utf-8"
	)
	ops = sum(len(trace) for trace in traces)
	print(f"{len(traces)} interpreters, {ops} operations -> {args.out}", file=sys.stderr)
	return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
	sys.exit(main())
