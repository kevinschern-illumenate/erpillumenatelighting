# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Render self-contained spec sheet HTML to PDF with headless Chromium.

Frappe v16's Chrome print path is built for Print Formats: without a header or
footer it forces 15 mm page margins and it rounds "Letter" to 216 x 279 mm.
Spec sheets are full-bleed US Letter pages, so this module prints the page
itself with the exact CSS page size and no browser margins.

It also pins its own Chromium. Frappe v16 downloads Chrome 133 by default, and
Chrome 136 and earlier embed @font-face fonts as Type 3 glyph procedures instead
of the real TrueType fonts (fixed in 137). The pinned Chrome for Testing
headless shell is downloaded once per bench, checked against its SHA-256, and
kept apart from Frappe's own Chromium so Print Formats are unaffected.

The HTML must be self-contained (fonts and images as data URIs). A strict
Content-Security-Policy is injected so the page cannot run scripts or load
anything from the network or the file system; rendering therefore never
depends on file permissions or the public URL of the bench.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

CHROMIUM_ENV = "ILL_SPEC_SHEET_CHROMIUM"
CHROMIUM_CONFIG_KEY = "spec_sheet_chromium_path"
DEFAULT_TIMEOUT = 60

PINNED_CHROMIUM = {
	"version": "141.0.7390.54",
	"url": (
		"https://storage.googleapis.com/chrome-for-testing-public/141.0.7390.54/"
		"linux64/chrome-headless-shell-linux64.zip"
	),
	"sha256": "cba167189d1e676a10bb0a1d52b43a26eb7d6c15dd6f05ae76cff100c30d547a",
	"executable": ("chrome-headless-shell-linux64", "chrome-headless-shell"),
}

CHROMIUM_ARGS = (
	"--headless",
	"--no-sandbox",
	"--disable-gpu",
	"--disable-dev-shm-usage",
	"--disable-extensions",
	"--disable-background-networking",
	"--disable-component-update",
	"--disable-default-apps",
	"--disable-sync",
	"--no-first-run",
	"--no-default-browser-check",
	"--hide-scrollbars",
	"--mute-audio",
	"--force-color-profile=srgb",
	"--font-render-hinting=none",
	"--no-pdf-header-footer",
	"--run-all-compositor-stages-before-draw",
	"--virtual-time-budget=10000",
)


# Chromium's scriptEnabled=false blink setting also stops --print-to-pdf, so
# scripts and every non-inline resource are blocked by policy instead.
CONTENT_SECURITY_POLICY = (
	"default-src 'none'; script-src 'none'; connect-src 'none'; object-src 'none'; "
	"style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'"
)
_CSP_META = f'<meta http-equiv="Content-Security-Policy" content="{CONTENT_SECURITY_POLICY}">'


class RenderError(RuntimeError):
	pass


def with_security_policy(html):
	"""Insert the CSP as the first element of <head> so it applies to everything after it."""
	lower = html.lower()
	start = lower.find("<head")
	if start == -1:
		raise RenderError("Spec sheet HTML must contain a <head> element")
	end = lower.find(">", start)
	return html[: end + 1] + _CSP_META + html[end + 1 :]


def pinned_chromium_dir():
	import frappe

	return Path(frappe.utils.get_bench_path(), "chromium-spec-sheets", PINNED_CHROMIUM["version"])


def pinned_chromium_path():
	return pinned_chromium_dir().joinpath(*PINNED_CHROMIUM["executable"])


def _is_executable(path):
	return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def download_pinned_chromium(timeout=600):
	"""Download, verify and unpack the pinned headless shell. Safe to repeat."""
	import requests

	if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
		raise RenderError(
			f"No pinned Chromium for {platform.system()} {platform.machine()}; set {CHROMIUM_CONFIG_KEY}"
		)
	target = pinned_chromium_dir()
	if _is_executable(pinned_chromium_path()):
		return pinned_chromium_path()
	target.parent.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory(dir=target.parent, prefix=".download-") as workdir:
		archive = Path(workdir, "chromium.zip")
		digest = hashlib.sha256()
		with requests.get(PINNED_CHROMIUM["url"], stream=True, timeout=timeout) as response:
			response.raise_for_status()
			with archive.open("wb") as handle:
				for chunk in response.iter_content(chunk_size=1 << 20):
					digest.update(chunk)
					handle.write(chunk)
		if digest.hexdigest() != PINNED_CHROMIUM["sha256"]:
			raise RenderError("Downloaded Chromium failed its SHA-256 check")
		unpacked = Path(workdir, "unpacked")
		with zipfile.ZipFile(archive) as bundle:
			root = unpacked.resolve()
			for member in bundle.infolist():
				destination = (unpacked / member.filename).resolve()
				if root not in destination.parents and destination != root:
					raise RenderError("Chromium archive contains an unsafe path")
				bundle.extract(member, unpacked)
				mode = member.external_attr >> 16
				if mode:
					os.chmod(destination, mode)
		executable = unpacked.joinpath(*PINNED_CHROMIUM["executable"])
		executable.chmod(0o755)
		try:
			os.replace(unpacked, target)
		except OSError:
			if not _is_executable(pinned_chromium_path()):
				raise
	return pinned_chromium_path()


def find_chromium(download=False):
	"""Return the Chromium executable used for spec sheets.

	Order: the ``ILL_SPEC_SHEET_CHROMIUM`` environment variable (local tools and CI),
	the ``spec_sheet_chromium_path`` site config key, then the pinned headless shell
	(downloaded only when ``download`` is true, e.g. from a background job).
	"""
	override = os.environ.get(CHROMIUM_ENV)
	if override:
		return override
	try:
		import frappe
	except ImportError as error:
		raise RenderError(f"Set {CHROMIUM_ENV} to a headless Chromium executable") from error
	configured = frappe.conf.get(CHROMIUM_CONFIG_KEY)
	if configured:
		return configured
	if _is_executable(pinned_chromium_path()):
		return str(pinned_chromium_path())
	if download:
		return str(download_pinned_chromium())
	raise RenderError("Spec sheet Chromium is not installed yet; run the render probe or setup job")


def chromium_version(executable=None):
	executable = executable or find_chromium()
	result = subprocess.run(
		[executable, "--version"], capture_output=True, text=True, timeout=20, check=False
	)
	return (result.stdout or result.stderr).strip()


def render_pdf(html, *, executable=None, timeout=DEFAULT_TIMEOUT):
	"""Return PDF bytes for ``html``. Raises :class:`RenderError` on any failure."""
	executable = executable or find_chromium()
	if not executable or not (shutil.which(executable) or Path(executable).is_file()):
		raise RenderError(f"Chromium executable not found: {executable!r}")
	with tempfile.TemporaryDirectory(prefix="ill-spec-sheet-") as workdir:
		source = Path(workdir, "sheet.html")
		target = Path(workdir, "sheet.pdf")
		source.write_text(with_security_policy(html), encoding="utf-8")
		command = [
			executable,
			*CHROMIUM_ARGS,
			f"--user-data-dir={Path(workdir, 'profile')}",
			f"--print-to-pdf={target}",
			source.as_uri(),
		]
		try:
			result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
		except subprocess.TimeoutExpired as error:
			raise RenderError(f"Chromium did not finish within {timeout}s") from error
		if not target.is_file():
			detail = (result.stderr or result.stdout or "").strip()[-2000:]
			raise RenderError(f"Chromium produced no PDF (exit {result.returncode}): {detail}")
		content = target.read_bytes()
		if not content.startswith(b"%PDF-"):
			raise RenderError("Chromium output is not a PDF")
		return content
