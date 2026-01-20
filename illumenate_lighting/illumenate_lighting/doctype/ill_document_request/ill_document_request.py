# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date


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

	def on_update(self):
		"""Handle status changes and automation."""
		# Check if status changed to trigger automation
		if self.has_value_changed("status"):
			self._handle_status_change()

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
			self.db_set("assigned_to", self.assigned_to)

	def _create_task_if_needed(self):
		"""Create a linked task if configured on request type."""
		if not self.request_type:
			return

		request_type = frappe.get_doc("ilL-Request-Type", self.request_type)

		if not request_type.auto_create_task:
			return

		task = frappe.new_doc("Task")
		task.subject = f"{request_type.portal_label or request_type.type_name}: {self.name}"
		task.description = self.description
		task.project = request_type.task_project
		task.exp_end_date = self.sla_deadline.date() if self.sla_deadline else None

		if self.assigned_to:
			task.append("assigned_to", {"user": self.assigned_to})

		task.insert(ignore_permissions=True)

		self.db_set("task_link", task.name)

	def _notify_submission(self):
		"""Send notification on request submission."""
		if not self.assigned_to:
			return

		try:
			frappe.sendmail(
				recipients=[self.assigned_to],
				subject=_("New Document Request: {0}").format(self.name),
				message=_("""
<p>A new document request has been submitted and assigned to you.</p>

<p><strong>Request:</strong> {name}<br>
<strong>Type:</strong> {request_type}<br>
<strong>Priority:</strong> {priority}<br>
<strong>Requester:</strong> {requester}</p>

<p><strong>Description:</strong><br>{description}</p>

<p><a href="{url}">View Request</a></p>
""").format(
					name=self.name,
					request_type=self.request_type,
					priority=self.priority,
					requester=self.requester_user,
					description=self.description or "",
					url=frappe.utils.get_url_to_form("ilL-Document-Request", self.name),
				),
				delayed=False,
			)
		except Exception as e:
			frappe.log_error(f"Failed to send submission notification: {str(e)}")

	def _on_complete(self):
		"""Handle request completion."""
		self.completed_on = now_datetime()
		self.db_set("completed_on", self.completed_on)

		# Notify requester
		self._notify_completion()

	def _notify_completion(self):
		"""Send notification to requester on completion."""
		if not self.requester_user:
			return

		# Get published deliverables
		deliverables = [d for d in self.deliverables or [] if d.is_published_to_portal]

		try:
			frappe.sendmail(
				recipients=[self.requester_user],
				subject=_("Your Request {0} is Complete").format(self.name),
				message=_("""
<p>Your document request has been completed.</p>

<p><strong>Request:</strong> {name}<br>
<strong>Type:</strong> {request_type}</p>

{deliverables_text}

<p><a href="{url}">View Request and Download Files</a></p>
""").format(
					name=self.name,
					request_type=self.request_type,
					deliverables_text=_("<p><strong>Deliverables:</strong> {0} file(s) available for download</p>").format(len(deliverables)) if deliverables else "",
					url=frappe.utils.get_url(f"/portal/requests/{self.name}"),
				),
				delayed=False,
			)
		except Exception as e:
			frappe.log_error(f"Failed to send completion notification: {str(e)}")

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
		if deliverable_idx < 0 or deliverable_idx >= len(self.deliverables or []):
			frappe.throw(_("Invalid deliverable index"))

		deliverable = self.deliverables[deliverable_idx]
		deliverable.is_published_to_portal = 1
		deliverable.published_on = now_datetime()
		deliverable.published_by = frappe.session.user

		self.save()

		# Notify requester
		self._notify_deliverable_published(deliverable)

		return {"success": True}

	def _notify_deliverable_published(self, deliverable):
		"""Notify requester when a deliverable is published."""
		if not self.requester_user:
			return

		try:
			frappe.sendmail(
				recipients=[self.requester_user],
				subject=_("New File Available: {0}").format(self.name),
				message=_("""
<p>A new file has been added to your request.</p>

<p><strong>Request:</strong> {name}<br>
<strong>File:</strong> {file}</p>

<p><a href="{url}">View and Download</a></p>
""").format(
					name=self.name,
					file=deliverable.file.split("/")[-1] if deliverable.file else "File",
					url=frappe.utils.get_url(f"/portal/requests/{self.name}"),
				),
				delayed=False,
			)
		except Exception as e:
			frappe.log_error(f"Failed to send deliverable notification: {str(e)}")


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


def get_permission_query_conditions(user=None):
	"""
	Return SQL conditions to filter ilL-Document-Request for the current user.

	Rules:
	- System Manager sees all
	- Dealers see requests from their company
	- Regular users see only their own requests
	"""
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
		return ""

	user_customer = _get_user_customer(user)

	# Dealers can see all requests from their company
	if "Dealer" in frappe.get_roles(user) and user_customer:
		return f"""(
			`tabilL-Document-Request`.requester_user = {frappe.db.escape(user)}
			OR `tabilL-Document-Request`.owner_customer = {frappe.db.escape(user_customer)}
		)"""

	# Regular users see only their own requests
	return f"""(
		`tabilL-Document-Request`.requester_user = {frappe.db.escape(user)}
		AND `tabilL-Document-Request`.hide_from_portal = 0
	)"""


def has_permission(doc, ptype="read", user=None):
	"""
	Check if user has permission to access this document request.
	"""
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
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
	if doc.assigned_to == user:
		return True

	return False
