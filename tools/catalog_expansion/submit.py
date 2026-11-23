"""Check (and optionally import) catalogs through the site's Catalog Builder API.

    python -m tools.catalog_expansion.submit --site https://<site> catalogs/*.yaml          # Check only
    python -m tools.catalog_expansion.submit --site https://<site> --import catalogs/*.yaml # Check, then Import

Check always rolls back. Import runs only after a Passed Check of the identical catalog and
commits only when every insert succeeds (see tools/fixture_builder/CATALOG.md). Results are
appended to ``--log`` as JSON lines.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

import yaml

API = "/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder."


def post(site, method, payload):
	request = urllib.request.Request(
		site.rstrip("/") + API + method,
		data=json.dumps(payload).encode(),
		headers={"Content-Type": "application/json", "Accept": "application/json"},
		method="POST",
	)
	try:
		with urllib.request.urlopen(request, timeout=600) as response:
			return json.load(response)["message"]
	except urllib.error.HTTPError as error:
		return {
			"ok": False,
			"status": f"HTTP {error.code}",
			"errors": [error.read().decode(errors="replace")[:2000]],
		}


def problems(result):
	out = list(result.get("errors") or [])
	for row in result.get("results") or []:
		if row.get("status") in ("error", "skipped"):
			out.append(
				f"{row.get('doctype')} {row.get('name') or row.get('index')}: {row.get('status')} {row.get('message') or row.get('error') or ''}"
			)
	return out


def run(site, paths, do_import, log):
	summary = []
	with open(log, "a", encoding="utf-8") as handle:
		for path in paths:
			catalog = yaml.safe_load(Path(path).read_text())
			check = post(site, "check", {"catalog": catalog})
			entry = {
				"file": str(path),
				"check": check.get("status"),
				"hash": check.get("catalog_hash"),
				"problems": problems(check)[:40],
			}
			if do_import and check.get("status") == "Passed":
				imported = post(
					site, "import_catalog", {"catalog": catalog, "expected_hash": check.get("catalog_hash")}
				)
				entry.update(
					imported=imported.get("status"),
					import_problems=problems(imported)[:40],
					created=imported.get("summary", {}).get("created"),
				)
			handle.write(json.dumps(entry) + "\n")
			summary.append(entry)
			print(
				Path(path).name,
				entry["check"],
				entry.get("imported", ""),
				(entry["problems"] or entry.get("import_problems") or [""])[0][:300],
			)
	return summary


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--site", required=True)
	parser.add_argument("--import", dest="do_import", action="store_true")
	parser.add_argument("--log", default="catalog_submit.jsonl")
	parser.add_argument("paths", nargs="+")
	args = parser.parse_args()
	run(args.site, args.paths, args.do_import, args.log)
