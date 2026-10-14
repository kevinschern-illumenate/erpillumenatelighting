# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.portal.project_list import list_projects
from illumenate_lighting.illumenate_lighting.portal.web_guard import require_login

no_cache = 1


def get_context(context):
	"""Projects list: server-side search, filter, sort and pages (FLOW-3)."""
	require_login()

	args = frappe.form_dict
	result = list_projects(
		frappe.session.user,
		search=args.get("search"),
		status=args.get("status"),
		sort=args.get("sort"),
		page=args.get("page"),
	)
	context.update(result)
	context.title = _("Projects")
	context.no_cache = 1

	return context
