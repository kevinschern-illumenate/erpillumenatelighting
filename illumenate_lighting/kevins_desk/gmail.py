"""A deliberately small Gmail API client for Kevin's Desk.

It can list and read threads, list and create labels, and add or remove the desk's own three labels.
It cannot send, trash, delete, archive or mark anything read: there is no call for it here, and
``modify_thread`` refuses any label but @Action, @Waiting and @Quote (so INBOX, UNREAD, TRASH and
SPAM can never change). Phase 5 adds drafts; sending stays out (tests/portal_unit enforces this).

No Frappe calls in here: the access token is passed in, and reads run in a thread pool.
"""

from concurrent.futures import ThreadPoolExecutor

import requests

API = "https://gmail.googleapis.com/gmail/v1/users/me"
MANAGED_LABELS = ("@Action", "@Waiting", "@Quote")
HEADERS = (
	"From",
	"To",
	"Cc",
	"Subject",
	"Date",
	"Message-ID",
	"List-Unsubscribe",
	"List-Id",
	"Precedence",
	"Auto-Submitted",
)
TIMEOUT = 15
WORKERS = 8


class GmailError(Exception):
	pass


class Gmail:
	def __init__(self, auth_header, session=None):
		self.session = session or requests.Session()
		self.session.headers.update(auth_header)
		self.label_ids = {}  # managed label name -> id, filled by ensure_labels()

	def call(self, method, path, **kwargs):
		r = self.session.request(method, API + path, timeout=TIMEOUT, **kwargs)
		if r.status_code >= 400:
			raise GmailError(f"Gmail {method} {path.split('?')[0]}: HTTP {r.status_code} {r.text[:200]}")
		return r.json() if r.content else {}

	def thread_ids(self, q=None, label_ids=None, limit=50):
		params = {"maxResults": min(limit, 100)}
		if q:
			params["q"] = q
		if label_ids:
			params["labelIds"] = list(label_ids)
		return [t["id"] for t in self.call("GET", "/threads", params=params).get("threads") or []]

	def thread(self, thread_id):
		params = {"format": "metadata", "metadataHeaders": list(HEADERS)}
		return self.call("GET", f"/threads/{thread_id}", params=params)

	def threads(self, ids):
		"""Fetch many threads in parallel; a thread that fails is skipped, not fatal."""
		ids = list(dict.fromkeys(ids))

		def one(thread_id):
			try:
				return self.thread(thread_id)
			except (GmailError, requests.RequestException):
				return None

		with ThreadPoolExecutor(max_workers=WORKERS) as pool:
			return [t for t in pool.map(one, ids) if t]

	def ensure_labels(self):
		"""Look up @Action/@Waiting/@Quote, creating any that are missing."""
		have = {lb["name"]: lb["id"] for lb in self.call("GET", "/labels").get("labels") or []}
		for name in MANAGED_LABELS:
			if name not in have:
				made = self.call(
					"POST",
					"/labels",
					json={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
				)
				have[name] = made["id"]
			self.label_ids[name] = have[name]
		return dict(self.label_ids)

	def modify_thread(self, thread_id, add=(), remove=()):
		"""Add/remove managed labels only (by name)."""
		for name in (*add, *remove):
			if name not in MANAGED_LABELS or name not in self.label_ids:
				raise GmailError(f"Refusing to change label {name!r}")
		if not add and not remove:
			return None
		body = {
			"addLabelIds": [self.label_ids[n] for n in add],
			"removeLabelIds": [self.label_ids[n] for n in remove],
		}
		return self.call("POST", f"/threads/{thread_id}/modify", json=body)
