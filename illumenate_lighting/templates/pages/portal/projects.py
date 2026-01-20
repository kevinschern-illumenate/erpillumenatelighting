import frappe


def get_context(context):
	project_name = frappe.form_dict.get("project")
	if project_name:
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = f"/projects?project={project_name}"
		return

	if frappe.session.user == "Guest":
		raise frappe.PermissionError

	project_ids = frappe.get_all(
		"Project User",
		filters={"user": frappe.session.user},
		pluck="parent",
	)

	context.no_cache = 1
	context.show_sidebar = True
	context.projects = []

	if project_ids:
		context.projects = frappe.get_all(
			"Project",
			filters={"name": ("in", project_ids)},
			fields=["name", "project_name", "status", "percent_complete"],
			order_by="modified desc",
		)
