# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The ilLumenate email look, shared by every automatic email the site sends.

Frappe wraps outgoing mail in ``templates/emails/standard.html`` (Notifications, Email
Templates, portal emails) or ``templates/emails/auth_email.html`` (password reset, sign-in
link, two-factor). This app ships both files, so Frappe's template loader, which searches
apps installed after Frappe first, uses ours: one navy-and-gold card for every email.

Everything here is presentation and copy. Contact details live in ``BRAND`` so the footer,
the portal emails and the sign-in emails all say the same thing.
"""

from email.header import Header
from email.utils import formataddr, parseaddr
from html import escape

import frappe

BRAND = {
	"name": "ilLumenate Lighting",
	"address": "PO Box 297, Bothell WA 98041",
	"phone": "(425) 381-2447",
	"phone_tel": "+14253812447",
	"email": "sales@illumenate.lighting",
	"website": "https://www.illumenate.lighting",
	"website_label": "illumenate.lighting",
	"logo_path": "/assets/illumenate_lighting/images/email/wordmark-white.png",
	"logo_width": 200,
	"logo_height": 27,
}

# Design System tokens, as hex because email clients ignore CSS variables.
COLORS = {
	"navy": "#172E48",
	"blue": "#00588C",
	"gold": "#FDC757",
	"ink": "#172E48",
	"muted": "#5D6D7F",
	"line": "#E8EAED",
	"canvas": "#F6F8FA",
	"panel": "#F6F8FA",
	"white": "#FFFFFF",
}

FONT_DISPLAY = "Manrope, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_BODY = "Poppins, 'Segoe UI', Helvetica, Arial, sans-serif"

PORTAL_SETTINGS_PATH = "/portal/account"


def ill_email_brand():
	"""Jinja method: brand values for the email wrappers (absolute URLs, colors, fonts)."""
	site = frappe.utils.get_url()
	return frappe._dict(
		BRAND,
		site_url=site,
		logo_url=site + BRAND["logo_path"],
		fonts_url=site + "/assets/illumenate_lighting/fonts/",
		colors=frappe._dict(COLORS),
		font_display=FONT_DISPLAY,
		font_body=FONT_BODY,
	)


def describe_seconds(seconds):
	"""1200 -> "20 minutes", 259200 -> "72 hours", 3600 -> "1 hour"."""
	seconds = int(seconds or 0)
	if seconds <= 0:
		return ""
	if seconds % 3600 == 0:
		hours = seconds // 3600
		return "1 hour" if hours == 1 else f"{hours} hours"
	minutes = max(1, round(seconds / 60))
	return "1 minute" if minutes == 1 else f"{minutes} minutes"


def ill_link_lifetime():
	"""Jinja method: how long a welcome / password-reset link works, from System Settings."""
	return describe_seconds(frappe.get_system_settings("reset_password_link_expiry_duration"))


def ill_is_staff(user=None):
	"""Jinja method: True for a System User (Desk), False for a portal user."""
	if not user:
		return False
	return frappe.db.get_value("User", user, "user_type") == "System User"


# ---------------------------------------------------------------------------
# Portal email bodies
# ---------------------------------------------------------------------------

_P = f"margin:0 0 16px;font-family:{FONT_BODY};font-size:15px;line-height:1.6;color:{COLORS['ink']}"
_SMALL = f"margin:0 0 12px;font-family:{FONT_BODY};font-size:13px;line-height:1.6;color:{COLORS['muted']}"


def button(label, url):
	"""A blue pill button that survives Outlook (table cell with bgcolor, square corners there)."""
	return (
		'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 20px">'
		f'<tr><td bgcolor="{COLORS["blue"]}" style="border-radius:999px;background:{COLORS["blue"]}">'
		f'<a href="{escape(url, quote=True)}" style="display:inline-block;padding:13px 28px;'
		f"font-family:{FONT_BODY};font-size:15px;font-weight:500;line-height:1.2;color:#FFFFFF;"
		f'text-decoration:none;border-radius:999px">{escape(label)}</a></td></tr></table>'
	)


def text_link(label, url):
	return (
		f'<a href="{escape(url, quote=True)}" style="color:{COLORS["blue"]};font-weight:500;'
		f'text-decoration:none">{escape(label)} &rarr;</a>'
	)


def details_panel(rows):
	"""Label / value rows in a soft panel. ``rows`` is [(label, value_html)]; blank values are dropped."""
	rows = [(label, value) for label, value in rows if value]
	if not rows:
		return ""
	cells = "".join(
		"<tr>"
		f'<td valign="top" style="padding:4px 16px 4px 0;font-family:{FONT_BODY};font-size:13px;'
		f'line-height:1.5;color:{COLORS["muted"]};white-space:nowrap">{escape(label)}</td>'
		f'<td valign="top" style="padding:4px 0;font-family:{FONT_BODY};font-size:14px;line-height:1.5;'
		f'color:{COLORS["ink"]}">{value}</td>'
		"</tr>"
		for label, value in rows
	)
	return (
		'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
		f'bgcolor="{COLORS["panel"]}" style="margin:4px 0 20px;background:{COLORS["panel"]};border-radius:10px">'
		f'<tr><td style="padding:14px 18px"><table role="presentation" cellpadding="0" cellspacing="0" '
		f'border="0">{cells}</table></td></tr></table>'
	)


def portal_email(
	title,
	paragraphs=(),
	details=(),
	action=None,
	secondary=None,
	note=None,
	greeting=None,
	preference_note=None,
):
	"""HTML body for a portal email, placed inside the branded card by ``standard.html``.

	``paragraphs`` and ``note`` are trusted HTML (callers escape user text); ``action`` and
	``secondary`` are (label, url); ``preference_note`` names the setting that sends it,
	e.g. "shipping updates", and adds a link to the notification settings.
	"""
	parts = [
		f'<h1 style="margin:0 0 16px;font-family:{FONT_DISPLAY};font-size:24px;font-weight:700;'
		f'line-height:1.25;letter-spacing:-0.02em;color:{COLORS["ink"]}">{escape(title)}</h1>'
	]
	if greeting:
		parts.append(f'<p style="{_P}">Hi {escape(greeting)},</p>')
	parts += [f'<p style="{_P}">{text}</p>' for text in paragraphs if text]
	parts.append(details_panel(details))
	if action:
		parts.append(button(*action))
	if secondary:
		parts.append(f'<p style="{_P}">{text_link(*secondary)}</p>')
	if note:
		parts.append(f'<p style="{_SMALL}">{note}</p>')
	if preference_note:
		url = frappe.utils.get_url(PORTAL_SETTINGS_PATH)
		parts.append(
			f'<p style="{_SMALL}">You get {escape(preference_note)} because they are on in your '
			f'<a href="{escape(url, quote=True)}" style="color:{COLORS["muted"]}">portal notification '
			"settings</a>.</p>"
		)
	return "".join(part for part in parts if part)


def first_name(user):
	"""A portal user's first name for the greeting, or None."""
	if not user or "@" not in str(user):
		return None
	return frappe.db.get_value("User", user, "first_name") or None


# ---------------------------------------------------------------------------
# Sender name
# ---------------------------------------------------------------------------


def brand_sender(email_id):
	return formataddr((str(Header(BRAND["name"], "utf-8")), email_id))


def _replace_from_header(message, sender):
	"""Swap the From header in a queued MIME message, leaving the body untouched."""
	return replace_header(message, "From", sender)


def replace_header(message, header, value):
	"""Swap one header (and its folded lines) in a queued MIME message; the body is untouched.

	A message without that header comes back unchanged.
	"""
	if not message:
		return message
	newline = "\r\n" if "\r\n" in message else "\n"
	split = message.find(newline + newline)
	if split < 0:
		return message
	head, body = message[:split], message[split:]
	lines = head.split(newline)
	prefix = header.lower() + ":"
	out, skipping, replaced = [], False, False
	for line in lines:
		if skipping and line[:1] in (" ", "\t"):
			continue
		skipping = False
		if line.lower().startswith(prefix) and not replaced:
			out.append(f"{header}: {value}")
			skipping = replaced = True
			continue
		out.append(line)
	return newline.join(out) + body if replaced else message


def rebrand_sender(queue):
	"""Send automatic email as "ilLumenate Lighting <account address>".

	Applies to mail that goes out under the default account's own name ("Info"), which is
	every email no person sent (Notifications, portal, password reset, sign-in link,
	two-factor), and to Frappe's welcome / reset mail, which otherwise carries the name of
	whoever created the user. A person's email from the composer keeps their name.
	"""
	try:
		account = queue.get_email_account() if hasattr(queue, "get_email_account") else None
	except Exception:
		account = None
	if not account or not account.get("email_id"):
		return False
	name, address = parseaddr(queue.sender or "")
	default_named = name == account.name and address.lower() == account.email_id.lower()
	sign_in_mail = bool(queue.get("redact_message_after_send")) and not queue.get("reference_doctype")
	if not (default_named or sign_in_mail):
		return False
	sender = brand_sender(account.email_id)
	queue.sender = sender
	queue.message = _replace_from_header(queue.message, sender)
	return True
