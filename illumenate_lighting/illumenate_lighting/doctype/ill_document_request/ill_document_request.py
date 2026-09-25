# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime


class ilLDocumentRequest(Document):
	def before_insert(self):
		"""Set up request before first save."""
		# Set requester info
		if not self.requester_user:
			self.requester_user = frappe.session.user

		# Set owner customer
		if not self.owner_customer:
			self.owner_customer = _get_user_customer(frappe.session.user)

		# Set requester customer if not set
		if not self.requester_customer and self.owner_customer:
			self.requester_customer = self.owner_customer

		# Set default priority from request type
		if self.request_type and not self.priority:
			request_type = frappe.get_doc("ilL-Request-Type", self.request_type)
			self.priority = request_type.default_priority or "Normal"

	def validate(self):
		"""Validate request data."""
		self._update_portal_status_group()
		old = self.get_doc_before_save()
		bind_order = old and not old.get("sales_order") and self.get("sales_order") and self.get("fixture_schedule") == old.get("fixture_schedule") and self.get("required_for_manufacturing") == old.get("required_for_manufacturing")
		if bind_order:
			order = frappe.get_doc("Sales Order", self.sales_order)
			if not _is_request_staff(old, frappe.session.user) or order.get("ill_fixture_schedule") != self.fixture_schedule or order.customer != self.owner_customer:
				frappe.throw(_("Link the current order for this drawing's customer and schedule."), frappe.PermissionError)
		if old and old.get("required_for_manufacturing") and not bind_order and any(self.get(field) != old.get(field) for field in ("required_for_manufacturing", "sales_order", "fixture_schedule")):
			if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
				frappe.throw(_("Only System Manager may waive or move an existing manufacturing drawing requirement."), frappe.PermissionError)
		if self.assigned_to and (not old or old.assigned_to != self.assigned_to):
			if not _is_request_staff(self, self.assigned_to) or not frappe.db.get_value("User", self.assigned_to, "enabled"):
				frappe.throw(_("Choose an enabled drawing staff user."))
		if self.get("technical_reviewer") and (not old or old.get("technical_reviewer") != self.technical_reviewer):
			if self.technical_reviewer == "Guest" or not frappe.db.get_value("User", self.technical_reviewer, "enabled"):
				frappe.throw(_("Choose an enabled technical reviewer."))
			if self.project:
				from illumenate_lighting.illumenate_lighting.portal.access import can_read_project
				if not can_read_project(frappe.get_doc("ilL-Project", self.project), self.technical_reviewer):
					frappe.throw(_("The technical reviewer needs current project access."))
		for field, doctype in (("sales_order", "Sales Order"), ("fixture_schedule", "ilL-Project-Fixture-Schedule"), ("project", "ilL-Project")):
			if self.get(field) and (not old or old.get(field) != self.get(field)):
				linked = frappe.get_doc(doctype, self.get(field))
				customer = linked.get("owner_customer") or linked.get("customer")
				if doctype == "ilL-Project-Fixture-Schedule" and linked.get("ill_project"):
					customer = frappe.db.get_value("ilL-Project", linked.ill_project, "owner_customer") or customer
				if self.owner_customer and customer != self.owner_customer:
					frappe.throw(_("Drawing references must belong to the request's customer."))
		if not _is_request_staff(old, frappe.session.user):
			if self.project:
				from illumenate_lighting.illumenate_lighting.portal.access import can_read_project

				if not can_read_project(frappe.get_doc("ilL-Project", self.project), frappe.session.user):
					frappe.throw(_("Project access denied"), frappe.PermissionError)
			if not old and (self.get("technical_reviewer") or self.get("sales_order") or self.get("fixture_schedule") or self.get("required_for_manufacturing") or self.owner_customer != _get_user_customer(frappe.session.user)):
				frappe.throw(_("Only staff may assign technical review and production requirements."), frappe.PermissionError)
			if not old and (self.deliverables or self.assigned_to or self.hide_from_portal or self.status != "Draft" or self.requester_user != frappe.session.user):
				frappe.throw(_("New portal requests must start as an unassigned draft."), frappe.PermissionError)
			thread_reply = self.flags.portal_thread_transition and old and (old.status, self.status) == ("Waiting on Customer", "In Progress")
			if old and self.status != old.status and (old.status, self.status) != ("Draft", "Submitted") and not thread_reply:
				frappe.throw(_("Only authorized staff may change this request status."), frappe.PermissionError)
		if old:
			published = {row.name: row for row in old.deliverables or [] if row.is_published_to_portal}
			current = {row.name: row for row in self.deliverables or []}
			for name, row in published.items():
				if name not in current or any(row.get(key) != current[name].get(key) for key in ("file", "version", "notes", "is_published_to_portal", "published_on", "published_by", "published_build_hash", "published_file_sha256")):
					frappe.throw(_("Published deliverables are immutable. Add a new revision."))
			if not _is_request_staff(old, frappe.session.user):
				for field in ("deliverables", "assigned_to", "owner_customer", "requester_customer", "requester_user", "hide_from_portal", "project", "sales_order", "fixture_schedule", "technical_reviewer", "required_for_manufacturing", "ill_observed_build_hash", "ill_review_state", "ill_impact_task", "ill_next_action_by", "task_link", "sla_deadline", "completed_on"):
					if frappe.as_json(self.get(field)) != frappe.as_json(old.get(field)):
						frappe.throw(_("Only authorized staff may change request administration or deliverables."), frappe.PermissionError)
		old_rows = {row.name: row for row in old.deliverables or []} if old else {}
		for row in self.deliverables or []:
			previous = old_rows.get(row.name)
			if previous and previous.file == row.file and previous.is_published_to_portal == row.is_published_to_portal:
				continue
			if row.file:
				from illumenate_lighting.illumenate_lighting.portal.file_validation import validate_content

				name = frappe.db.get_value("File", {"file_url": row.file, "is_private": 1, "attached_to_doctype": self.doctype, "attached_to_name": self.name}, "name")
				if not name:
					frappe.throw(_("Deliverables must be private files attached to this saved request."))
				file = frappe.get_doc("File", name)
				validate_content(file.file_name, file.get_content())
			if row.is_published_to_portal and (not row.file or not row.version):
				frappe.throw(_("Published drawings require a file and an explicit revision."))
			if row.is_published_to_portal and (not previous or not previous.is_published_to_portal):
				from hashlib import sha256

				from illumenate_lighting.illumenate_lighting.portal.drawing_impact import request_build_hash

				row.published_on, row.published_by = now_datetime(), frappe.session.user
				row.published_build_hash = request_build_hash(self)
				row.published_file_sha256 = sha256(file.get_content()).hexdigest()
		versions = [row.version for row in self.deliverables or [] if row.is_published_to_portal and row.version]
		if len(versions) != len(set(versions)):
			frappe.throw(_("Each published drawing must have a unique revision."))

	def on_update(self):
		"""Handle status changes and automation."""
		# Check if status changed to trigger automation
		if self.has_value_changed("status"):
			self._handle_status_change()
		from illumenate_lighting.illumenate_lighting.portal.drawing_impact import refresh_request

		refresh_request(self)

	def _update_portal_status_group(self):
		"""Update the portal status group based on current status."""
		pending_statuses = ["Draft", "Submitted", "In Progress", "Waiting on Customer"]
		completed_statuses = ["Completed", "Closed", "Cancelled"]

		if self.status in pending_statuses:
			self.portal_status_group = "Pending"
		elif self.status in completed_statuses:
			self.portal_status_group = "Completed"
		else:
			self.portal_status_group = ""

	def _handle_status_change(self):
		"""Handle automation when status changes."""
		old_status = self.get_doc_before_save()
		old_status_value = old_status.status if old_status else None

		# On submit: calculate SLA, assign, create task
		if self.status == "Submitted" and old_status_value == "Draft":
			self._on_submit()

		# On complete: set completed timestamp
		if self.status == "Completed" and old_status_value != "Completed":
			self._on_complete()

	def _on_submit(self):
		"""Handle request submission."""
		# Calculate SLA deadline
		self._calculate_sla_deadline()

		# Auto-assign
		self._auto_assign()

		# Create task if configured
		self._create_task_if_needed()

		# Send notification
		self._notify_submission()

	def _calculate_sla_deadline(self):
		"""Calculate SLA deadline based on request type and priority."""
		if not self.request_type:
			return

		request_type = frappe.get_doc("ilL-Request-Type", self.request_type)
		sla_hours = request_type.get_sla_hours(self.priority or "Normal")

		self.sla_deadline = add_to_date(now_datetime(), hours=sla_hours)
		self.db_set("sla_deadline", self.sla_deadline)

	def _auto_assign(self):
		"""Auto-assign the request based on request type settings."""
		if self.assigned_to:
			return  # Already assigned

		if not self.request_type:
			return

		request_type = frappe.get_doc("ilL-Request-Type", self.request_type)

		# Try specific user first
		if request_type.default_assignee_user:
			self.assigned_to = request_type.default_assignee_user
		elif request_type.default_assignee_role:
			# Get first user with this role
			users = frappe.get_all(
				"Has Role",
				filters={"role": request_type.default_assignee_role, "parenttype": "User"},
				pluck="parent",
				limit=1,
			)
			if users:
				self.assigned_to = users[0]

		if self.assigned_to:
			if _is_request_staff(self, self.assigned_to) and frappe.db.get_value("User", self.assigned_to, "enabled"):
				self.db_set("assigned_to", self.assigned_to)
			else:
				self.assigned_to = None

	def _create_task_if_needed(self):
		"""Create a linked task if configured on request type."""
		if not self.request_type or self.task_link:
			return

		request_type = frappe.get_doc("ilL-Request-Type", self.request_type)

		if not request_type.auto_create_task:
			return

		task = frappe.new_doc("Task")
		task.subject = f"{request_type.portal_label or request_type.type_name}: {self.name}"
		task.description = self.description
		task.project = request_type.task_project
		task.exp_end_date = self.sla_deadline.date() if self.sla_deadline else None

		task.insert(ignore_permissions=True)
		if self.assigned_to:
			# Native assignments are ToDo records, not a Task child table.
			frappe.get_doc({"doctype": "ToDo", "reference_type": "Task", "reference_name": task.name,
				"allocated_to": self.assigned_to, "assigned_by": frappe.session.user,
				"description": task.subject, "date": task.exp_end_date, "status": "Open"}).insert(ignore_permissions=True)

		self.db_set("task_link", task.name)

	def _notify_submission(self):
		"""Send notification on request submission."""
		if not self.assigned_to:
			return
		from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user

		url = frappe.utils.escape_html(frappe.utils.get_url_to_form(self.doctype, self.name))
		notify_user(self.assigned_to, "notify_drawings", _("New Document Request: {0}").format(self.name),
			f'<p>A document request was assigned to you. <a href="{url}">Open request</a>.</p>',
			reference_doctype=self.doctype, reference_name=self.name)

	def _on_complete(self):
		"""Handle request completion."""
		self.completed_on = now_datetime()
		self.db_set("completed_on", self.completed_on)

		# Notify requester
		self._notify_completion()

	def _notify_completion(self):
		"""Send notification to requester on completion (gated by their preference)."""
		if not self.requester_user:
			return

		from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user

		# Get published deliverables
		deliverables = [d for d in self.deliverables or [] if d.is_published_to_portal]

		notify_user(
			self.requester_user,
			"notify_drawings",
			_("Your Request {0} is Complete").format(self.name),
			_("""
<p>Your document request has been completed.</p>

<p><strong>Request:</strong> {name}<br>
<strong>Type:</strong> {request_type}</p>

{deliverables_text}

<p><a href="{url}">View Request and Download Files</a></p>
""").format(
				name=self.name,
				request_type=self.request_type,
				deliverables_text=_("<p><strong>Deliverables:</strong> {0} file(s) available for download</p>").format(len(deliverables)) if deliverables else "",
				url=frappe.utils.get_url(f"/portal/drawings/{self.name}"),
			),
			reference_doctype=self.doctype,
			reference_name=self.name,
		)

	@frappe.whitelist()
	def submit_request(self):
		"""Submit the request (transition from Draft to Submitted)."""
		if self.status != "Draft":
			frappe.throw(_("Only Draft requests can be submitted"))

		self.status = "Submitted"
		self.save()
		return {"success": True}

	@frappe.whitelist()
	def publish_deliverable(self, deliverable_idx: int):
		"""Publish a deliverable to make it visible on the portal."""
		if not _is_request_staff(self, frappe.session.user):
			frappe.throw(_("Only assigned engineering staff may publish drawings."), frappe.PermissionError)
		if deliverable_idx < 0 or deliverable_idx >= len(self.deliverables or []):
			frappe.throw(_("Invalid deliverable index"))

		deliverable = self.deliverables[deliverable_idx]
		if deliverable.is_published_to_portal:
			return {"success": True, "already_existed": True}
		deliverable.is_published_to_portal = 1
		deliverable.published_on = now_datetime()
		deliverable.published_by = frappe.session.user

		self.save()

		# Notify requester
		self._notify_deliverable_published(deliverable)

		return {"success": True}

	def _notify_deliverable_published(self, deliverable):
		"""Notify requester when a deliverable is published (gated by their preference)."""
		if not self.requester_user:
			return

		from illumenate_lighting.illumenate_lighting.portal.notifications import notify_user

		notify_user(
			self.requester_user,
			"notify_drawings",
			_("New File Available: {0}").format(self.name),
			_("""
<p>A new file has been added to your request.</p>

<p><strong>Request:</strong> {name}<br>
<strong>File:</strong> {file}</p>

<p><a href="{url}">View and Download</a></p>
""").format(
				name=self.name,
				file=frappe.utils.escape_html(deliverable.file.split("/")[-1]) if deliverable.file else "File",
				url=frappe.utils.get_url(f"/portal/drawings/{self.name}"),
			),
			reference_doctype=self.doctype,
			reference_name=self.name,
		)


def _get_user_customer(user):
	"""Get the Customer linked to a user via Contact."""
	contact = frappe.db.get_value("Contact", {"user": user}, "name")
	if contact:
		customer = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
			"link_name",
		)
		return customer
	return None


def _is_request_staff(doc, user):
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("engineering", user):
		return True
	return bool(doc and doc.assigned_to == user and frappe.db.get_value("User", user, "enabled") and frappe.db.get_value("User", user, "user_type") == "System User")


def get_permission_query_conditions(user=None):
	from illumenate_lighting.illumenate_lighting.portal.access import project_query_conditions
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	user = user or frappe.session.user
	if user == "Guest" or (user != "Administrator" and not frappe.db.get_value("User", user, "enabled")):
		return "1=0"
	if _is_request_staff(None, user):
		return ""
	if allowed("operations", user):
		return "`tabilL-Document-Request`.required_for_manufacturing = 1"
	table = "`tabilL-Document-Request`"
	actor = frappe.db.escape(user)
	owners = [f"{table}.requester_user = {actor}", f"{table}.owner = {actor}"]
	owners.append(f"{table}.technical_reviewer = {actor}")
	customer = _get_user_customer(user)
	if "Dealer" in frappe.get_roles(user) and customer:
		owners.append(f"{table}.owner_customer = {frappe.db.escape(customer)}")
	project = project_query_conditions(user) or "1=1"
	scope = f"(({' OR '.join(owners)}) AND {table}.hide_from_portal = 0 AND (COALESCE({table}.project, '') = '' OR {table}.project IN (SELECT name FROM `tabilL-Project` WHERE {project})))"
	if frappe.db.get_value("User", user, "user_type") == "System User":
		scope = f"({scope} OR {table}.assigned_to = {actor})"
	return scope


def has_permission(doc, ptype="read", user=None):
	"""
	Check if user has permission to access this document request.
	"""
	if not user:
		user = frappe.session.user
	if user == "Guest" or (user != "Administrator" and not frappe.db.get_value("User", user, "enabled")):
		return False

	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
		return True
	if user == "Guest":
		return False
	if _is_request_staff(doc, user):
		return True
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if allowed("operations", user) and doc.required_for_manufacturing and ptype in ("read", "select", "report"):
		return True
	if doc.hide_from_portal:
		return False
	if doc.project:
		from illumenate_lighting.illumenate_lighting.portal.access import can_read_project

		if not can_read_project(frappe.get_doc("ilL-Project", doc.project), user):
			return False
	if ptype not in ("read", "select", "print", "write", "create"):
		return False
	if doc.get("technical_reviewer") == user and ptype in ("read", "select", "print"):
		return True

	# Owner/requester always has access
	if doc.requester_user == user or doc.owner == user:
		return True

	# Dealers can access requests from their company
	if "Dealer" in frappe.get_roles(user):
		user_customer = _get_user_customer(user)
		if user_customer and user_customer == doc.owner_customer:
			return True

	# Check if user is assigned
	return False
