# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
QuickBooks Online API client that goes through the n8n relay workflow.

n8n holds the QuickBooks OAuth2 credential, so ERPNext never stores QBO tokens.
Each call is one signed POST to the n8n workflow ``quickbooks_api_proxy.json``::

    {"method": "GET" | "POST", "path": "/invoice", "params": {...}, "body": {...}, "ts": 1760000000}

``X-QBO-Signature`` is the hex HMAC-SHA256 of the raw body, keyed with the
same shared secret as the inbound payment webhook. n8n rejects stale
timestamps and anything outside its path allowlist, then answers with
``{"ok": bool, "status": int, "body": <QBO JSON>, "intuit_tid": str}``.
"""

import hashlib
import hmac
import json
import time

import frappe

SETTINGS_DOCTYPE = "ilL-QBO-Settings"
TIMEOUT_SECONDS = 60
# QBO error codes worth retrying automatically: stale SyncToken, throttling, server-side.
TRANSIENT_FAULT_CODES = {"5010", "003001", "3001", "10000", "3200"}


class QBOError(Exception):
	"""A failed QBO call. ``transient`` errors are retried by the push scheduler."""

	def __init__(self, message, status=None, code=None, detail=None, transient=False, intuit_tid=None):
		super().__init__(message)
		self.message = message
		self.status = status
		self.code = code
		self.detail = detail
		self.transient = transient
		self.intuit_tid = intuit_tid

	def __str__(self):
		parts = [self.message]
		if self.detail and self.detail != self.message:
			parts.append(self.detail)
		if self.code:
			parts.append(f"code {self.code}")
		if self.status:
			parts.append(f"HTTP {self.status}")
		if self.intuit_tid:
			parts.append(f"intuit_tid {self.intuit_tid}")
		return " | ".join(parts)


def escape_query_value(value):
	"""Quote a string for a QBO query literal."""
	return str(value).replace("\\", "\\\\").replace("'", "\\'")


class QBOClient:
	def __init__(self, proxy_url=None, secret=None):
		settings = None
		if not proxy_url or not secret:
			settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
		self.proxy_url = (proxy_url or (settings.get("n8n_proxy_url") if settings else "") or "").strip()
		self.secret = secret or _shared_secret(settings)
		# Retryable: once someone fills in the settings, queued pushes go through on their own.
		if not self.proxy_url:
			raise QBOError("n8n QuickBooks proxy URL is not set in ilL-QBO-Settings", transient=True)
		if not self.secret:
			raise QBOError("Webhook Shared Secret is not set in ilL-QBO-Settings", transient=True)

	# -- transport -----------------------------------------------------------

	def call(self, method, path, params=None, body=None):
		import requests

		payload = {
			"method": method,
			"path": path,
			"params": params or {},
			"body": body,
			"ts": int(time.time()),
		}
		raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
		signature = hmac.new(self.secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
		try:
			resp = requests.post(
				self.proxy_url,
				data=raw,
				headers={"Content-Type": "application/json", "X-QBO-Signature": signature},
				timeout=TIMEOUT_SECONDS,
			)
		except requests.RequestException as e:
			raise QBOError(f"Could not reach the n8n QuickBooks proxy: {e}", transient=True)

		try:
			data = resp.json()
		except ValueError:
			data = None
		if not isinstance(data, dict) or "ok" not in data:
			# n8n itself failed (workflow inactive, crashed, wrong URL).
			snippet = (resp.text or "")[:300]
			raise QBOError(
				f"Unexpected response from the n8n QuickBooks proxy (HTTP {resp.status_code}): {snippet}",
				status=resp.status_code,
				transient=resp.status_code >= 500 or resp.status_code in (404, 408, 429),
			)
		if not data.get("ok"):
			raise _fault_to_error(data)
		return data.get("body") or {}

	# -- helpers -------------------------------------------------------------

	def query(self, statement):
		"""Run a QBO SQL-like query; returns the QueryResponse dict."""
		return (self.call("GET", "/query", {"query": statement}).get("QueryResponse")) or {}

	def query_one(self, entity, statement):
		rows = self.query(statement).get(entity) or []
		return rows[0] if rows else None

	def read(self, entity, qbo_id):
		return self.call("GET", f"/{entity.lower()}/{qbo_id}").get(entity) or {}

	def create(self, entity, body, requestid):
		return self.call("POST", f"/{entity.lower()}", {"requestid": requestid}, body).get(entity) or {}

	def update(self, entity, body, requestid):
		return self.call("POST", f"/{entity.lower()}", {"requestid": requestid}, body).get(entity) or {}

	def operation(self, entity, body, operation, requestid, include=None):
		params = {"operation": operation, "requestid": requestid}
		if include:
			params["include"] = include
		return self.call("POST", f"/{entity.lower()}", params, body).get(entity) or {}


def _shared_secret(settings):
	secret = frappe.conf.get("qbo_webhook_secret")
	if secret:
		return str(secret)
	if settings is None:
		return None
	try:
		return settings.get_password("webhook_secret", raise_exception=False)
	except Exception:
		return None


def _fault_to_error(data):
	status = data.get("status")
	body = data.get("body") or {}
	tid = data.get("intuit_tid")
	if data.get("error"):
		# Proxy-level failure. Bad signature / disallowed path need a config fix, not a retry;
		# anything else (Intuit unreachable) is retried.
		return QBOError(
			f"n8n proxy: {data.get('error')}", status=status, transient=status not in (400, 401, 403)
		)
	fault = (body.get("Fault") or body.get("fault") or {}) if isinstance(body, dict) else {}
	errors = fault.get("Error") or fault.get("error") or []
	first = errors[0] if errors else {}
	code = str(first.get("code") or "") or None
	message = first.get("Message") or first.get("message") or f"QuickBooks returned HTTP {status}"
	detail = first.get("Detail") or first.get("detail")
	transient = (status in (401, 429) or (status or 0) >= 500) or (code in TRANSIENT_FAULT_CODES)
	if status == 401:
		message = "QuickBooks authorization failed — reconnect the QuickBooks credential in n8n"
	return QBOError(message, status=status, code=code, detail=detail, transient=transient, intuit_tid=tid)
