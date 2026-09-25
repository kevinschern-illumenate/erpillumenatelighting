"""Durable packet jobs. Retries create new attempts and preserve failed inventories."""

import hashlib
import json

import frappe

from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool

DOCTYPE = "ilL-Export-Job"
TYPES = ("SPEC_SUBMITTAL", "SPEC_SUBMITTAL_FULL")


class InterruptedPacket(RuntimeError):
	"""A recovered or finished attempt cannot be updated by a late worker."""


def lock_running(name):
	frappe.db.sql("select name from `tabilL-Export-Job` where name=%s for update", name)
	if frappe.db.get_value(DOCTYPE, name, "status") != "RUNNING":
		raise InterruptedPacket("This packet attempt is no longer running")


def checkpoint(name, progress, message):
	lock_running(name)
	frappe.db.set_value(
		DOCTYPE, name, {"progress": progress, "progress_message": message}, update_modified=False
	)
	frappe.db.commit()


def _access(schedule):
	from illumenate_lighting.illumenate_lighting.api.exports import _check_schedule_access

	allowed, error = _check_schedule_access(schedule)
	if not allowed:
		frappe.throw(error or "Schedule is unavailable", frappe.PermissionError)


def request(
	schedule_name, export_type="SPEC_SUBMITTAL", include_cover=True, *, retry_of=None, allow_partial=False
):
	from illumenate_lighting.illumenate_lighting.api.exports import _create_export_job

	_access(schedule_name)
	if export_type not in TYPES:
		raise ValueError("Choose a supported packet type")
	frappe.db.sql(
		"select name from `tabilL-Project-Fixture-Schedule` where name=%s for update", schedule_name
	)
	_access(schedule_name)
	revision = str(frappe.db.get_value("ilL-Project-Fixture-Schedule", schedule_name, "modified"))
	options = json.dumps(
		{
			"include_cover": parse_bool(include_cover, default=True),
			"allow_partial": parse_bool(allow_partial),
		},
		sort_keys=True,
	)
	existing = frappe.db.get_value(
		DOCTYPE,
		{
			"schedule": schedule_name,
			"source_revision": revision,
			"requested_by": frappe.session.user,
			"export_type": export_type,
			"packet_options": options,
			"status": ["in", ["QUEUED", "RUNNING"]],
		},
		"name",
	)
	if existing:
		return {"success": True, "queued": True, "export_job": existing}
	name = _create_export_job(schedule_name, export_type)
	frappe.db.set_value(
		DOCTYPE,
		name,
		{
			"source_revision": revision,
			"packet_options": options,
			"retry_of": retry_of,
			"progress": 0,
			"progress_message": "Queued",
		},
	)
	frappe.enqueue(
		"illumenate_lighting.illumenate_lighting.portal.packet_jobs.run",
		packet_job=name,
		queue="long",
		timeout=900,
		enqueue_after_commit=True,
	)
	return {"success": True, "queued": True, "export_job": name}


def run(packet_job):
	"""Only the first worker claims an attempt; a crash is retried as a new job."""
	job_name = packet_job
	from illumenate_lighting.illumenate_lighting.portal.packets import generate

	frappe.db.sql("select name from `tabilL-Export-Job` where name=%s for update", job_name)
	job = frappe.get_doc(DOCTYPE, job_name)
	if job.export_type not in TYPES or job.status != "QUEUED":
		return
	frappe.db.set_value(
		DOCTYPE,
		job.name,
		{
			"status": "RUNNING",
			"started_on": frappe.utils.now(),
			"progress": 5,
			"progress_message": "Preparing member documents",
		},
	)
	frappe.db.commit()
	actor = frappe.session.user
	try:
		if not frappe.db.get_value("User", job.requested_by, "enabled"):
			raise PermissionError("Requester is disabled")
		frappe.set_user(job.requested_by)
		_access(job.schedule)
		if (
			str(frappe.db.get_value("ilL-Project-Fixture-Schedule", job.schedule, "modified"))
			!= job.source_revision
		):
			raise ValueError("Schedule changed after this request. Generate a new packet.")
		options = json.loads(job.packet_options)
		generate(
			job.schedule,
			job.export_type,
			options["include_cover"],
			job_name=job.name,
			allow_partial=options.get("allow_partial", False),
		)
		frappe.db.commit()
	except InterruptedPacket:
		frappe.db.rollback()
	except Exception as error:
		frappe.db.rollback()
		try:
			lock_running(job.name)
		except InterruptedPacket:
			frappe.db.rollback()
			return
		frappe.db.set_value(
			DOCTYPE,
			job.name,
			{"status": "FAILED", "error_log": str(error), "progress_message": "Failed; review and retry"},
		)
		frappe.db.commit()
	finally:
		frappe.set_user(actor)


@frappe.whitelist()
def status(job_name):
	job = frappe.get_doc(DOCTYPE, job_name)
	_access(job.schedule)
	if job.export_type not in TYPES:
		raise ValueError("This is not a packet job")
	return {
		"success": True,
		"export_job": job.name,
		"status": job.status,
		"progress": job.progress or 0,
		"message": job.progress_message,
		"error": job.error_log if job.status in ("FAILED", "INCOMPLETE") else None,
		"manifest": json.loads(job.manifest_json or "[]"),
		"file_url": job.output_file if job.status in ("COMPLETE", "INCOMPLETE") else None,
	}


@frappe.whitelist(methods=["POST"])
def retry(job_name):
	job = frappe.get_doc(DOCTYPE, job_name)
	_access(job.schedule)
	if job.status not in ("FAILED", "INCOMPLETE") or job.export_type not in TYPES:
		raise ValueError("Only a failed packet can be retried")
	return request(
		job.schedule,
		job.export_type,
		json.loads(job.packet_options or "{}").get("include_cover", True),
		retry_of=job.name,
		allow_partial=json.loads(job.packet_options or "{}").get("allow_partial", False),
	)


@frappe.whitelist(methods=["POST"])
def issue(job_name):
	"""Freeze an identified complete packet; issuing does not send any messages."""
	from illumenate_lighting.illumenate_lighting.portal.access import can_edit_schedule
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	job = frappe.get_doc(DOCTYPE, job_name)
	_access(job.schedule)
	if not (
		allowed("engineering")
		or can_edit_schedule(frappe.get_doc("ilL-Project-Fixture-Schedule", job.schedule))
	):
		frappe.throw("Packet issuance requires schedule editor access", frappe.PermissionError)
	frappe.db.sql("select name from `tabilL-Export-Job` where name=%s for update", job_name)
	job.reload()
	if job.status != "COMPLETE" or not job.output_sha256 or not job.manifest_json:
		raise ValueError("Only a complete verified packet can be issued")
	file_name = frappe.db.get_value(
		"File",
		{
			"file_url": job.output_file,
			"is_private": 1,
			"attached_to_doctype": DOCTYPE,
			"attached_to_name": job.name,
		},
		"name",
	)
	if (
		not file_name
		or hashlib.sha256(frappe.get_doc("File", file_name).get_content()).hexdigest() != job.output_sha256
	):
		raise ValueError("Packet bytes no longer match the verified result; generate a new packet")
	if not job.get("issued_on"):
		frappe.db.set_value(
			DOCTYPE, job.name, {"issued_on": frappe.utils.now(), "issued_by": frappe.session.user}
		)
	return {"success": True, "export_job": job.name, "sha256": job.output_sha256}


def recover():
	"""Requeue committed requests after broker failure and expose abandoned worker attempts."""
	for job in frappe.get_all(
		DOCTYPE, filters={"export_type": ["in", TYPES], "status": "QUEUED"}, pluck="name", limit=100
	):
		frappe.enqueue(
			"illumenate_lighting.illumenate_lighting.portal.packet_jobs.run",
			packet_job=job,
			queue="long",
			timeout=900,
		)
	frappe.db.sql("""update `tabilL-Export-Job` set status='FAILED', error_log='Worker interrupted. Retry this packet.',
		progress_message='Interrupted; retry available' where export_type in ('SPEC_SUBMITTAL','SPEC_SUBMITTAL_FULL')
		and status='RUNNING' and started_on < DATE_SUB(NOW(), INTERVAL 20 MINUTE)""")
