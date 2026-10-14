# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""The drawings page lists through the same scope as its counts (REL-8).

Every list here is filtered by ``api.document_requests._scoped_request_conditions``,
the predicate behind the dashboard counts and the request APIs, so lists and
counts always agree and project collaborators see their project's requests.
"""

import frappe

FIELDS = (
	"name",
	"request_type",
	"description",
	"project",
	"fixture_or_product_text",
	"priority",
	"status",
	"creation",
	"modified",
)
PAGE_SIZE = 20


def requests(tab="all", page=1, page_size=PAGE_SIZE, user=None):
	"""One page of a tab's requests, newest first, plus whether another page exists."""
	from illumenate_lighting.illumenate_lighting.api.document_requests import (
		REQUEST_TABLE,
		_scoped_request_conditions,
	)

	conditions, params = _scoped_request_conditions(tab=tab, user=user)
	order = "modified" if tab == "completed" else "creation"
	params.update({"start": (max(1, page) - 1) * page_size, "length": page_size + 1})
	rows = frappe.db.sql(
		f"""
		SELECT {", ".join(FIELDS)}
		FROM {REQUEST_TABLE}
		WHERE {" AND ".join(conditions)}
		ORDER BY {order} DESC, name DESC
		LIMIT %(length)s OFFSET %(start)s
		""",
		params,
		as_dict=True,
	)
	return rows[:page_size], len(rows) > page_size


def page_number(value):
	try:
		return max(1, int(value or 1))
	except (TypeError, ValueError):
		return 1
