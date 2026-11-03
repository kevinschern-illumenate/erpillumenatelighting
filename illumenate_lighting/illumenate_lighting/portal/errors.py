"""Structured, dealer-readable errors for portal and configurator endpoints.

``portal_error`` (plan item 2.4) raises a ``frappe.ValidationError`` subclass
carrying ``exc.portal_payload`` so callers can map it to inline field errors.

``failure`` (plan item 1.6) is the single boundary used where an endpoint must
keep its legacy ``{"success": False, "error": ...}`` response instead of
raising: expected validation/permission errors keep their message, anything
unexpected is written to the Error Log with context and replaced by a generic
message that carries the Error Log reference.
"""

import frappe

# Matches the ``internal_error`` code used by api/portal.py::_handle_error.
UNEXPECTED = "internal_error"
GENERIC_MESSAGE = "Something went wrong on our side. Please try again or contact ilLumenate support"

# Unit-test doubles sometimes replace frappe with a MagicMock; keep import safe.
_ValidationBase = getattr(frappe, "ValidationError", None)
if not isinstance(_ValidationBase, type):
	_ValidationBase = ValueError


class PortalError(_ValidationBase):
	def __init__(self, code: str, message: str, field: str | None = None, hint: str | None = None):
		super().__init__(message)
		self.portal_payload = {"code": code, "message": message, "field": field, "hint": hint}
		self.msgprinted = None


def portal_error(code: str, message: str, field: str | None = None, hint: str | None = None):
	"""Raise a dealer-readable error.

	Like ``frappe.throw`` the message is msgprinted, so existing callers that read
	``_server_messages`` keep working; the structured payload is also attached to the
	JSON response as ``portal_error`` (Frappe keeps ``frappe.local.response`` keys when it
	builds the error response) for ``PortalAPI.call`` to map onto a field.
	"""
	exc = PortalError(code, message, field=field, hint=hint)
	attach_payload(exc.portal_payload)
	msgprint = getattr(frappe, "msgprint", None)
	if callable(msgprint):
		text = f"{message} {hint}" if hint else message
		try:
			msgprint(text, indicator="red")
			exc.msgprinted = text
		except Exception:
			pass
	raise exc


def attach_payload(payload: dict) -> None:
	response = getattr(getattr(frappe, "local", None), "response", None)
	if response is None:
		return
	try:
		response["portal_error"] = dict(payload)
	except Exception:
		pass


def _expected_types() -> tuple:
	types_ = [ValueError]
	for name in ("ValidationError", "PermissionError", "DoesNotExistError"):
		candidate = getattr(frappe, name, None)
		if isinstance(candidate, type):
			types_.append(candidate)
	return tuple(types_)


def is_expected(exc: BaseException) -> bool:
	return isinstance(exc, _expected_types())


def log_unexpected(exc: BaseException, title: str, context: dict | None = None):
	"""Write an Error Log entry with traceback and context; never raises."""
	lines = [f"{key}: {value}" for key, value in (context or {}).items()]
	try:
		traceback = frappe.get_traceback()
	except Exception:
		traceback = ""
	lines.append(f"Error: {type(exc).__name__}: {exc}")
	if traceback:
		lines.append(traceback)
	try:
		# defer_insert keeps the Error Log even if the caller rolls back.
		return frappe.log_error(title=title[:140], message="\n".join(lines), defer_insert=True)
	except Exception:
		return None


def _retract(exc: PortalError) -> None:
	"""A caught PortalError becomes a normal reply: drop its queued msgprint and response payload."""
	local = getattr(frappe, "local", None)
	log = getattr(local, "message_log", None)
	if exc.msgprinted and isinstance(log, list):
		for index in range(len(log) - 1, -1, -1):
			entry = log[index]
			text = entry.get("message") if isinstance(entry, dict) else entry
			if text == exc.msgprinted:
				del log[index]
				break
	response = getattr(local, "response", None)
	if response is not None and hasattr(response, "pop"):
		response.pop("portal_error", None)


def _rollback_write_request():
	request = getattr(getattr(frappe, "local", None), "request", None)
	if getattr(request, "method", None) in ("POST", "PUT", "DELETE"):
		frappe.db.rollback()


def _clean(message: str) -> str:
	strip_html = getattr(getattr(frappe, "utils", None), "strip_html", None)
	return (strip_html(message) if callable(strip_html) else message).strip()


def failure(
	exc: BaseException, code: str, *, title: str, context: dict | None = None, rollback: bool = False
) -> dict:
	"""Map an exception to ``{"success": False, "error", "error_code"[, "field", "hint"]}``.

	``rollback=True`` discards partial writes on POST/PUT/DELETE requests, which
	Frappe would otherwise commit because the endpoint returns normally.
	"""
	if rollback:
		try:
			_rollback_write_request()
		except Exception:
			pass
	if isinstance(exc, PortalError):
		_retract(exc)
		payload = exc.portal_payload
		response = {"success": False, "error": payload["message"], "error_code": payload["code"]}
		for key in ("field", "hint"):
			if payload.get(key):
				response[key] = payload[key]
		return response
	if is_expected(exc):
		return {"success": False, "error": _clean(str(exc)) or f"{GENERIC_MESSAGE}.", "error_code": code}
	log = log_unexpected(exc, title, context)
	reference = getattr(log, "name", None)
	message = f"{GENERIC_MESSAGE} (reference {reference})." if reference else f"{GENERIC_MESSAGE}."
	return {"success": False, "error": message, "error_code": UNEXPECTED}
