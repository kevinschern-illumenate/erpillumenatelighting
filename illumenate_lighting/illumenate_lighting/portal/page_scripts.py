# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Content-hash versions for portal page scripts served as plain /assets files (plan 2.2).

Each page keeps its scripts in public/js/portal/<folder>/*.js and loads them with
``?v=<script_version(folder)>`` so a deploy busts browser caches.
"""

import functools
import hashlib
from pathlib import Path

import frappe

PORTAL_JS = Path(__file__).resolve().parents[2] / "public" / "js" / "portal"


@functools.cache
def _folder_hash(folder: str) -> str:
	digest = hashlib.sha1(usedforsecurity=False)
	for path in sorted((PORTAL_JS / folder).glob("*.js")):
		digest.update(path.name.encode())
		digest.update(path.read_bytes())
	return digest.hexdigest()[:12]


def script_version(folder: str) -> str:
	if frappe.conf.get("developer_mode"):
		_folder_hash.cache_clear()
	return _folder_hash(folder)
