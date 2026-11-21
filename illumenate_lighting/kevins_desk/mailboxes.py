"""The mailboxes the desk reads (ilL-Desk-Settings → Mailboxes) and connecting them to Google.

Each mailbox gets its own Connected App, named ``kevins-desk-<local part>`` (kevins-desk-kevins,
kevins-desk-sales). It copies the client id, secret and scopes of the site's Google Connected App
(ilL-Desk-Settings → Google App, left untouched) and adds ``access_type=offline``, ``prompt=consent``
and ``login_hint=<mailbox>``, so Google issues a refresh token for the right account. Frappe keeps the
tokens in Token Cache (encrypted) and refreshes them. Fixed names mean fixed redirect URIs, which are
registered once on the Google OAuth client.

Tokens are stored for the desk owner's ERPNext user (one Connected App per mailbox keeps them apart),
and never leave the server: ``status()`` returns an auth header for server use only.
"""

import re

import frappe
from frappe import _
from frappe.utils import get_url

from illumenate_lighting.kevins_desk.access import SETTINGS

APP_PREFIX = "kevins-desk-"
CALLBACK = "/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/"
GOOGLE_AUTH = "https://accounts.google.com/"
COPY_FIELDS = (
	"client_id",
	"openid_configuration",
	"authorization_uri",
	"token_uri",
	"revocation_uri",
	"userinfo_uri",
)


def app_name(mailbox):
	local = mailbox.split("@")[0].lower()
	return APP_PREFIX + (re.sub(r"[^a-z0-9]+", "-", local).strip("-") or "mailbox")


def redirect_uri(name):
	return get_url(CALLBACK + name)


def rows():
	settings = frappe.get_single(SETTINGS)
	out = []
	for r in settings.get("mailboxes") or []:
		address = (r.mailbox or "").strip().lower()
		if address and r.enabled:
			out.append(
				{
					"mailbox": address,
					"label": r.label or address,
					"scope": r.get("scope") or "Recent (21 days)",
				}
			)
	return out


def status(row, owner):
	"""Connection state of one mailbox. "auth_header" is present only when connected (server use only)."""
	name = app_name(row["mailbox"])
	out = dict(row, app=name, redirect_uri=redirect_uri(name), state="not_connected", error=None)
	if not frappe.db.exists("Connected App", name):
		out["state"] = "not_set_up"
		return out
	try:
		token = frappe.get_doc("Connected App", name).get_active_token(owner)
	except Exception:
		frappe.log_error(title=f"Kevin's Desk: token for {row['mailbox']} failed")
		return dict(out, state="error", error="Token refresh failed; reconnect")
	if token and token.get_password("access_token", raise_exception=False):
		out["state"] = "connected"
		out["auth_header"] = token.get_auth_header()
	return out


def template_app():
	name = frappe.db.get_single_value(SETTINGS, "google_app")
	if not name or not frappe.db.exists("Connected App", name):
		frappe.throw(_("Set ilL-Desk-Settings → Google App to the site's Google Connected App first."))
	return frappe.get_doc("Connected App", name)


def ensure_app(mailbox):
	"""Create (or bring up to date) the mailbox's Connected App from the template. Returns its name."""
	name = app_name(mailbox)
	params = {"access_type": "offline", "prompt": "consent", "login_hint": mailbox}
	if frappe.db.exists("Connected App", name):
		doc = frappe.get_doc("Connected App", name)
		have = {p.key: p.value for p in doc.query_parameters}
		if have == params:
			return name
		doc.query_parameters = []
	else:
		src = template_app()
		doc = frappe.new_doc("Connected App")
		doc.provider_name = f"Kevin's Desk · {mailbox}"
		for field in COPY_FIELDS:
			doc.set(field, src.get(field))
		doc.client_secret = src.get_password("client_secret")
		for scope in src.scopes:
			doc.append("scopes", {"scope": scope.scope})
	for key, value in params.items():
		doc.append("query_parameters", {"key": key, "value": value})
	if doc.is_new():
		doc.insert(ignore_permissions=True, set_name=name)
	else:
		doc.save(ignore_permissions=True)
	return name


def connect(mailbox, owner, return_to):
	"""Start Google's consent flow for a configured mailbox; returns the authorization URL."""
	mailbox = (mailbox or "").strip().lower()
	if mailbox not in {r["mailbox"] for r in rows()}:
		raise frappe.DoesNotExistError
	app = frappe.get_doc("Connected App", ensure_app(mailbox))
	url = app.initiate_web_application_flow(user=owner, success_uri=return_to)
	if not str(url).startswith(GOOGLE_AUTH):
		frappe.throw(_("Unexpected authorization URL"))
	return url
