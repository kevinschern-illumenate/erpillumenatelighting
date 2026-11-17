# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Site-config access for the ERPNext -> n8n calls (spec generation and Webflow sync).

No n8n URL, header value or environment is hardcoded in the app. Each site sets
them in its ``site_config.json`` so a staging deploy can never call production
n8n by accident (plan 2.8 item 1, task Z1).

Site config keys (values are never logged or returned to the browser):

``n8n_spec_webhook_url``
    Absolute HTTPS URL of the spec-generation webhook (W1).
``n8n_sync_webhook_url``
    Absolute HTTPS URL of the Webflow sync webhook (W2).
``n8n_sync_secret``
    Shared secret sent on every ERPNext -> n8n call. The legacy key
    ``ERP-Sync-Secret-2026`` is still read as a fallback so an existing site
    keeps working until its config is renamed.
``n8n_sync_secret_header``
    Name of the header that carries the secret. Must match the n8n Header Auth
    credential (staging: ``STAGING-Sync-Secret``). Defaults to the header the
    production workflow has always used.
``webflow_environment``
    ``staging`` or ``production`` (default ``production``). See plan 4.11.
"""

import frappe
from frappe import _

SPEC_WEBHOOK_URL_KEY = "n8n_spec_webhook_url"
SYNC_WEBHOOK_URL_KEY = "n8n_sync_webhook_url"
SECRET_KEY = "n8n_sync_secret"
SECRET_HEADER_KEY = "n8n_sync_secret_header"
ENVIRONMENT_KEY = "webflow_environment"

# The key and header name request_spec_sheet used before Z1. Read only as a
# fallback so production keeps working until its site config is updated.
LEGACY_SECRET_KEY = "ERP-Sync-Secret-2026"
DEFAULT_SECRET_HEADER = "ERP-Sync-Secret-2026"

ENVIRONMENTS = ("staging", "production")


def _conf(key):
	value = frappe.conf.get(key)
	return value.strip() if isinstance(value, str) else value


def webhook_url(key):
	"""Return the configured n8n webhook URL for ``key`` or raise.

	There is deliberately no default: a missing key must stop the call rather
	than fall back to a production URL.
	"""
	url = _conf(key)
	if not url:
		frappe.throw(
			_(
				"The n8n webhook URL is not configured. Ask your administrator to set {0} in site config."
			).format(key)
		)
	if not str(url).startswith("https://"):
		frappe.throw(_("Site config {0} must be an absolute https:// URL.").format(key))
	return url


def spec_webhook_url():
	return webhook_url(SPEC_WEBHOOK_URL_KEY)


def sync_webhook_url():
	return webhook_url(SYNC_WEBHOOK_URL_KEY)


def auth_headers():
	"""Return the shared-secret header for ERPNext -> n8n requests, or raise."""
	secret = _conf(SECRET_KEY) or _conf(LEGACY_SECRET_KEY)
	if not secret:
		frappe.throw(
			_(
				"The n8n sync secret is not configured. Ask your administrator to set {0} in site config."
			).format(SECRET_KEY)
		)
	header = _conf(SECRET_HEADER_KEY) or DEFAULT_SECRET_HEADER
	return {header: secret}


def webflow_environment():
	"""Return ``staging`` or ``production`` (default). Unknown values raise."""
	value = (_conf(ENVIRONMENT_KEY) or "production").lower()
	if value not in ENVIRONMENTS:
		frappe.throw(_("Site config {0} must be 'staging' or 'production'.").format(ENVIRONMENT_KEY))
	return value


def is_staging():
	return webflow_environment() == "staging"


@frappe.whitelist()
def get_webflow_environment():
	"""Desk banner helper: return ``staging`` or ``production``. Holds no secrets."""
	return webflow_environment()
