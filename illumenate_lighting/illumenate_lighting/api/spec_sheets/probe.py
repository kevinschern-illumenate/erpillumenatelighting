# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Phase 0 site check: can this bench render spec sheets with Chromium?

Run as a System Manager from the browser console on the site:

	frappe.call({
		method: "illumenate_lighting.illumenate_lighting.api.spec_sheets.probe.run",
		type: "POST",
	}).then((r) => console.log(r.message));

The first call starts a background job when the pinned Chromium is not
installed yet (a ~110 MB download, verified by SHA-256). Call again to read the
result. A successful run attaches the rendered St. Helens page 1 as a
private File so it can be compared with the InDesign golden locally
(``tools/spec_sheets/fidelity.py``).
"""

import io
import json
import os
import time
from pathlib import Path

import frappe

CACHE_KEY = "ill_spec_sheet_render_probe"
JOB_ID = "ill_spec_sheet_render_probe"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "st_helens_sf_sw"


def _expected_chromium_path():
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.render import (
		CHROMIUM_CONFIG_KEY,
		pinned_chromium_path,
	)

	return frappe.conf.get(CHROMIUM_CONFIG_KEY) or str(pinned_chromium_path())


def _render(download=False):
	from pypdf import PdfReader

	from illumenate_lighting.illumenate_lighting.api.spec_sheets.pages import build_html
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.render import (
		chromium_version,
		find_chromium,
		render_pdf,
	)
	from illumenate_lighting.illumenate_lighting.api.spec_sheets.svg import DirectoryAssets

	started = time.monotonic()
	executable = find_chromium(download=download)
	located = time.monotonic()
	model = json.loads((FIXTURE / "model.json").read_text(encoding="utf-8"))
	html = build_html(model, DirectoryAssets(FIXTURE / "assets"))
	pdf = render_pdf(html, executable=executable)
	finished = time.monotonic()
	reader = PdfReader(io.BytesIO(pdf))
	fonts = set()
	for page in reader.pages:
		for font in (page.get("/Resources", {}).get("/Font") or {}).values():
			fonts.add(str(font.get_object().get("/BaseFont", "")).split("+")[-1])
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"spec-sheet-render-probe-{frappe.utils.now_datetime():%Y%m%d%H%M%S}.pdf",
			"is_private": 1,
			"content": pdf,
		}
	).insert(ignore_permissions=True)
	box = reader.pages[0].mediabox
	return {
		"status": "rendered",
		"chromium": executable,
		"chromium_version": chromium_version(executable),
		"locate_seconds": round(located - started, 2),
		"render_seconds": round(finished - located, 2),
		"pdf_bytes": len(pdf),
		"pages": len(reader.pages),
		"page_size_pt": [float(box.width), float(box.height)],
		"fonts": sorted(fonts),
		"file_url": file.file_url,
	}


def background_probe():
	try:
		result = _render(download=True)
	except Exception as error:
		frappe.log_error(title="Spec sheet render probe failed")
		result = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
	result["finished_at"] = str(frappe.utils.now_datetime())
	frappe.cache().set_value(CACHE_KEY, result, expires_in_sec=24 * 3600)


@frappe.whitelist(methods=["POST"])
def run(force_background=0):
	"""Render the Phase 0 page, or report the background job's result.

	From the System Console (Python, with **Commit** ticked):

		print(frappe.call("illumenate_lighting.illumenate_lighting.api.spec_sheets.probe.run"))
	"""
	frappe.only_for("System Manager")
	previous = frappe.cache().get_value(CACHE_KEY)
	expected = _expected_chromium_path()
	installed = os.path.isfile(expected) and os.access(expected, os.X_OK)
	if previous and previous.get("status") == "running" and not _stale(previous):
		job = _job_report()
		if job["job_status"] in ("queued", "started", "deferred", "scheduled"):
			return {**previous, **job, "chromium_expected_at": expected, "chromium_installed": installed}
		# The job ended without recording a result (or was lost): report why and start again.
		previous = {**previous, **job}
	if installed and not frappe.utils.cint(force_background):
		result = _render()
		result["chromium_installed"] = True
		result["note"] = (
			"The PDF's File record is kept only if this call is committed (System Console: tick Commit)."
		)
		return result
	state = {
		"status": "running",
		"started_at": str(frappe.utils.now_datetime()),
		"note": "Chromium is being located or downloaded in a background job. Call run again in a few minutes.",
	}
	frappe.cache().set_value(CACHE_KEY, state, expires_in_sec=3600)
	# Not enqueue_after_commit: the System Console rolls back unless Commit is ticked,
	# and the job does not depend on anything written by this request.
	frappe.enqueue(
		"illumenate_lighting.illumenate_lighting.api.spec_sheets.probe.background_probe",
		queue="long",
		timeout=1800,
		job_id=JOB_ID,
		deduplicate=True,
	)
	return {**state, "chromium_expected_at": expected, "chromium_installed": installed, "previous": previous}


def _job_report():
	"""RQ status of the probe job and how much of the Chromium download has arrived."""
	from frappe.utils.background_jobs import get_job

	from illumenate_lighting.illumenate_lighting.api.spec_sheets.render import pinned_chromium_dir

	report = {"job_status": None}
	try:
		job = get_job(JOB_ID)
	except Exception as error:
		report["job_error"] = f"{type(error).__name__}: {error}"
		job = None
	if job:
		status = job.get_status(refresh=True)
		report["job_status"] = getattr(status, "value", status)
		if job.exc_info:
			report["job_error"] = job.exc_info.strip().splitlines()[-1]
	downloads = sorted(pinned_chromium_dir().parent.glob(".download-*/chromium.zip"))
	if downloads:
		report["download_mb"] = round(sum(path.stat().st_size for path in downloads) / 1_048_576, 1)
	return report


def _stale(state, minutes=30):
	"""A "running" marker whose job never reported back (worker restart, lost job)."""
	try:
		started = frappe.utils.get_datetime(state.get("started_at"))
	except Exception:
		return True
	return (frappe.utils.now_datetime() - started).total_seconds() > minutes * 60


def console_check():
	"""Run the probe from ``bench --site <site> console`` (not the sandboxed System Console).

	Paste these two lines:

		from illumenate_lighting.illumenate_lighting.api.spec_sheets.probe import console_check
		console_check()

	The first run downloads the pinned Chromium (~110 MB, SHA-256 checked); later runs reuse it.
	"""
	print(f"Chromium expected at: {_expected_chromium_path()}")
	try:
		result = _render(download=True)
	except Exception as error:
		frappe.db.rollback()
		print(f"FAILED: {type(error).__name__}: {error}")
		return {"status": "failed", "error": f"{type(error).__name__}: {error}"}
	# The console does not commit on its own; keep the rendered PDF's File record.
	frappe.db.commit()
	result["download_url"] = frappe.utils.get_url(result["file_url"])
	for key, value in result.items():
		print(f"{key}: {value}")
	return result
