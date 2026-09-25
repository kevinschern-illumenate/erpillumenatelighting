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
