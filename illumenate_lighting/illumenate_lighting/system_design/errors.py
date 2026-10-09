# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The System Designer error contract (plan H6)."""

CODES = frozenset({"NOT_FOUND", "FORBIDDEN", "INVALID", "CONFLICT", "LOCKED", "GATE", "INTERNAL"})


class DesignError(Exception):
	"""An intentional, user-facing failure with a contract ``code``."""

	def __init__(self, code, message):
		if code not in CODES:
			raise ValueError(f"Unknown System Designer error code: {code}")
		super().__init__(message)
		self.code = code
		self.message = message
