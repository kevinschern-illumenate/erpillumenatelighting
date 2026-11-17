"""Size and range guards for parameters accepted by guest (allow_guest) endpoints.

Guest endpoints are reachable from the public Webflow site, so every
attacker-controlled JSON string and count must be bounded before it is parsed
or turned into a query limit.
"""

import json

MAX_GUEST_JSON_BYTES = 64 * 1024


class PayloadTooLarge(json.JSONDecodeError):
	"""Raised for oversized JSON strings.

	Subclasses ``json.JSONDecodeError`` so existing ``except json.JSONDecodeError``
	handlers keep returning their established "Invalid selections JSON" shape.
	"""

	def __init__(self, size: int, limit: int = MAX_GUEST_JSON_BYTES):
		super().__init__(f"Payload of {size} bytes exceeds the {limit} byte limit", "", 0)
		self.size = size
		self.limit = limit


class NotAnObject(json.JSONDecodeError):
	def __init__(self, value):
		super().__init__(f"Expected a JSON object, got {type(value).__name__}", "", 0)


def load_guest_json(value, limit: int = MAX_GUEST_JSON_BYTES, object_only: bool = False):
	"""Decode ``value`` when it is a string, refusing payloads over ``limit`` bytes.

	Non-string values (already-decoded dicts from a JSON request body) are
	returned unchanged, matching the ``json.loads(x) if isinstance(x, str) else x``
	idiom this replaces. ``object_only`` additionally requires a dict, raising
	``NotAnObject`` (also a ``json.JSONDecodeError``) for lists, scalars and null.
	"""
	if isinstance(value, str):
		size = len(value.encode("utf-8"))
		if size > limit:
			raise PayloadTooLarge(size, limit)
		value = json.loads(value)
	if object_only and not isinstance(value, dict):
		raise NotAnObject(value)
	return value


def bounded_int(value, default: int, minimum: int, maximum: int) -> int:
	"""Coerce a form-string/int to an int clamped to ``[minimum, maximum]``."""
	try:
		number = int(str(value).strip()) if value not in (None, "") else default
	except (TypeError, ValueError):
		number = default
	return max(minimum, min(maximum, number))
