# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Shared utility functions for ilLumenate Lighting.

This module provides common helper functions used across the application,
including input validation and parsing utilities.
"""


def parse_positive_int(value, default: int = 1, minimum: int = 1) -> int:
	"""
	Parse a value as a positive integer with bounds checking.

	Args:
		value: Value to parse
		default: Default value if parsing fails
		minimum: Minimum allowed value

	Returns:
		int: Parsed integer, at least the minimum value
	"""
	try:
		return max(minimum, int(value))
	except (ValueError, TypeError):
		return default


# Pagination constants
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Access level constants
VALID_ACCESS_LEVELS = ["VIEW", "EDIT"]
