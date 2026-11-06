"""Pure publication revision, lease and retry rules."""

from datetime import datetime, timedelta


def callback_disposition(job, *, token, revision_hash, payload_hash, current_hash):
	if (
		token != job.get("lease_token")
		or revision_hash != job.get("revision_hash")
		or payload_hash != job.get("payload_hash")
	):
		raise ValueError("Callback does not match the claimed revision")
	if job.get("state") == "COMPLETE":
		return "duplicate"
	if job.get("state") != "RUNNING":
		raise ValueError("Job has no active claim")
	return "current" if current_hash == revision_hash else "superseded"


def retry_at(attempts, now=None, retry_after=None):
	if attempts >= 8:
		return None
	delay = min(3600, max(30 * 2 ** max(0, attempts - 1), min(int(retry_after or 0), 3600)))
	return (now or datetime.now()) + timedelta(seconds=delay)


# Plan 4.19 Q3 (sync rebuild step 3): a temporary failure retries after 1, then 5, then 15
# minutes; when the third retry fails too, or the failure is permanent, people are notified.
RETRY_MINUTES = (1, 5, 15)
# n8n reports "transport" when its call to Webflow did not complete; ERPNext reports "timeout"
# when n8n took the job but never answered, and "connection" when n8n could not be reached.
TEMPORARY_CODES = ("transport", "timeout", "connection", "429")
ERROR_REASONS = {
	"429": "Webflow rate limit",
	"transport": "Webflow could not be reached",
	"timeout": "no answer from the sync workflow",
	"connection": "the sync workflow could not be reached",
	"400": "Webflow rejected the data",
	"401": "Webflow or n8n credentials were refused",
	"403": "Webflow or n8n credentials were refused",
	"404": "the Webflow item, collection or n8n webhook was not found",
	"409": "Webflow reported a conflict",
	"422": "Webflow rejected the data",
	"identity-conflict": "more than one Webflow item matches this product; reconcile it",
	"missing-staged-item": "the Webflow item to publish was not found",
	"response-invalid": "Webflow sent an unexpected answer",
	"publication-unverified": "Webflow did not confirm the publish",
	"archive-unverified": "Webflow did not confirm the archive",
	"readiness": "the product is not ready to sync",
}


def is_temporary(error_code):
	"""Rate limit, timeouts, connection errors and 5xx retry; every other failure is permanent."""
	code = str(error_code or "transport").strip().lower()
	return code in TEMPORARY_CODES or (code.isdigit() and 500 <= int(code) <= 599)


def next_retry(error_code, attempts, now, retry_after=None):
	"""When a failed attempt runs again, or None: permanent, or the three retries are used up.

	``attempts`` counts the attempts made so far (1 after the first). A Webflow ``Retry-After``
	longer than the scheduled wait is honoured up to the longest wait (15 minutes).
	"""
	attempts = max(1, int(attempts or 1))
	if not is_temporary(error_code) or attempts > len(RETRY_MINUTES):
		return None
	delay = RETRY_MINUTES[attempts - 1] * 60
	try:
		requested = int(float(retry_after or 0))
	except (TypeError, ValueError):
		requested = 0
	delay = max(delay, min(requested, RETRY_MINUTES[-1] * 60))
	return now + timedelta(seconds=delay)


def failure_reason(error_code):
	"""Pure: a short, safe description of a failure code for people."""
	code = str(error_code or "transport").strip().lower()
	if code in ERROR_REASONS:
		return ERROR_REASONS[code]
	if code.isdigit() and 500 <= int(code) <= 599:
		return "n8n or Webflow had a server error"
	return "the sync failed"
