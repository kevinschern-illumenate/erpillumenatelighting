"""Local syntax/schema/lint review of this change, including a HEAD lint baseline.

Run with a Python interpreter that can execute Ruff. Does not require a Frappe site.
"""

import ast
import collections
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUFF = ROOT / ".tools/b2b-python/bin/ruff.exe"
if not RUFF.is_file():
	RUFF = shutil.which("ruff") or "ruff"
SCOPES = (
	"illumenate_lighting",
	"tests",
	"tools/check_b2b_changes.py",
	"tools/build_publication_workflow.py",
	"tools/check_portal_templates.py",
	"tools/fixture_builder",
	"tools/validate_authoring_csv.py",
	"tools/check_pdf_fidelity.py",
	"tools/reconcile_webflow.cjs",
)


def git(*args):
	return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def lint(source, path):
	result = subprocess.run(
		[str(RUFF), "check", "--no-cache", "--output-format", "json", "--stdin-filename", path, "-"],
		input=source,
		text=True,
		capture_output=True,
		encoding="utf-8",
		cwd=ROOT,
	)
	if result.returncode not in (0, 1):
		raise RuntimeError(result.stderr)
	return json.loads(result.stdout)


def main():
	base = os.environ.get("B2B_BASE_REF") or "HEAD"
	changed = set(git("diff", "--name-only", "--diff-filter=ACMRT", base, "--", *SCOPES).splitlines())
	added = set(
		git(
			"ls-files",
			"--others",
			"--exclude-standard",
			"--",
			*SCOPES,
		).splitlines()
	)
	added.update(git("diff", "--name-only", "--diff-filter=A", base, "--", *SCOPES).splitlines())
	python = sorted(p for p in changed | added if p.endswith(".py"))
	if "--format-new" in sys.argv:
		subprocess.run(
			[str(RUFF), "format", "--no-cache", *sorted(p for p in added if p.endswith(".py"))],
			cwd=ROOT,
			check=True,
		)
		subprocess.run(
			[str(RUFF), "check", "--no-cache", "--select", "I", "--fix", *python], cwd=ROOT, check=True
		)
	new_errors, baseline_count = [], 0
	for path in python:
		source = (ROOT / path).read_text(encoding="utf-8")
		ast.parse(source, filename=path)
		current = lint(source, path)
		old = [] if path in added else lint(git("show", base + ":" + path), path)
		baseline_count += len(old)
		counts = collections.Counter((d["code"], d["message"]) for d in old)
		for diagnostic in current:
			key = diagnostic["code"], diagnostic["message"]
			if counts[key]:
				counts[key] -= 1
			else:
				new_errors.append(
					{"path": path, "row": diagnostic["location"]["row"], "code": key[0], "message": key[1]}
				)
	for path in changed | added:
		if path.endswith(".json"):
			json.loads((ROOT / path).read_text(encoding="utf-8"))
	result = {
		"python_files": len(python),
		"baseline_lint_diagnostics": baseline_count,
		"new_lint_diagnostics": new_errors,
	}
	output = ROOT / ".tools/b2b-validation.json"
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(json.dumps(result, indent=2), encoding="utf-8")
	print(json.dumps(result, indent=2))
	return bool(new_errors)


if __name__ == "__main__":
	raise SystemExit(main())
