# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Conversion constant: millimeters per foot
MM_PER_FOOT = 304.8


class ilLProjectFixtureSchedule(Document):
	def validate(self):
		"""Validate schedule data and sync customer from project."""
		if self.ill_project:
			project = frappe.get_doc("ilL-Project", self.ill_project)
			# Auto-sync customer from project
			if not self.customer or self.customer != project.customer:
				self.customer = project.customer

	@frappe.whitelist()
	def create_sales_order(self):
		"""
		Create a Sales Order from this fixture schedule.

		Creates a Sales Order for the schedule's customer with SO lines for
		manufacturer_type = ILLUMENATE only. Each SO line links to the chosen
		ilL-Configured-Fixture and copies qty, location/notes, and key computed
		fields into custom SO Item fields for quick visibility.

		Returns:
			str: Name of the created Sales Order document
		"""
		if not self.customer:
			frappe.throw(_("Customer is required to create a Sales Order"))

		# Filter lines to only ILLUMENATE manufacturer type with configured fixtures
		illumenate_lines = [
			line for line in self.lines
			if line.manufacturer_type == "ILLUMENATE" and line.configured_fixture
		]

		if not illumenate_lines:
			frappe.throw(
				_("No ilLumenate fixture lines with configured fixtures found in this schedule")
			)

		# Create Sales Order
		so = frappe.new_doc("Sales Order")
		so.customer = self.customer
		so.project = self.project
		so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)

		# Add SO items for each ILLUMENATE line
		for line in illumenate_lines:
			# Fetch the configured fixture to get computed values
			configured_fixture = frappe.get_doc(
				"ilL-Configured-Fixture", line.configured_fixture
			)

			# Get template code from the fixture template
			template_code = None
			if configured_fixture.fixture_template:
				template_code = configured_fixture.fixture_template

			# Get the configured item or use a placeholder
			# The configured_item is the sellable Item linked from the configured fixture
			item_code = configured_fixture.configured_item
			if not item_code:
				# If no configured item yet, use a placeholder or error
				frappe.throw(
					_(
						"Line {0}: Configured Fixture {1} does not have a configured Item. "
						"Please ensure the fixture has been fully configured."
					).format(line.line_id or line.idx, line.configured_fixture)
				)

			so_item = so.append("items", {})
			so_item.item_code = item_code
			so_item.qty = line.qty or 1
			so_item.description = self._build_item_description(line, configured_fixture)

			# Set custom fields for quick visibility
			so_item.ill_configured_fixture = line.configured_fixture
			so_item.ill_template_code = template_code
			so_item.ill_requested_length_mm = configured_fixture.requested_overall_length_mm
			so_item.ill_mfg_length_mm = configured_fixture.manufacturable_overall_length_mm
			so_item.ill_runs_count = configured_fixture.runs_count
			so_item.ill_total_watts = configured_fixture.total_watts
			so_item.ill_finish = configured_fixture.finish
			so_item.ill_lens = configured_fixture.lens_appearance
			so_item.ill_engine_version = configured_fixture.engine_version

		so.insert()

		# Update schedule status to ORDERED
		self.db_set("status", "ORDERED")

		frappe.msgprint(
			_("Sales Order {0} created successfully").format(
				frappe.utils.get_link_to_form("Sales Order", so.name)
			),
			indicator="green",
			alert=True,
		)

		return so.name

	@frappe.whitelist()
	def request_quote(self):
		"""
		Request a quote for this schedule (for non-dealer customers).

		Changes status to QUOTED and can trigger notification to sales team.

		Returns:
			str: Status update message
		"""
		if self.status not in ["DRAFT", "READY"]:
			frappe.throw(_("Schedule must be in DRAFT or READY status to request a quote"))

		self.db_set("status", "QUOTED")

		frappe.msgprint(
			_("Quote requested for schedule {0}").format(self.name),
			indicator="blue",
			alert=True,
		)

		return "Quote requested"

	@frappe.whitelist()
	def duplicate_line(self, line_idx):
		"""
		Duplicate a schedule line including its configured fixture reference.

		Args:
			line_idx: Index of the line to duplicate

		Returns:
			int: Index of the new line
		"""
		line_idx = int(line_idx)
		if line_idx < 0 or line_idx >= len(self.lines):
			frappe.throw(_("Invalid line index"))

		source_line = self.lines[line_idx]
		new_line = self.append("lines", {})

		# Copy all fields except name and idx
		for field in source_line.as_dict():
			if field not in ["name", "idx", "parent", "parenttype", "parentfield", "doctype"]:
				new_line.set(field, source_line.get(field))

		# Update line_id to indicate it's a copy
		if source_line.line_id:
			new_line.line_id = f"{source_line.line_id} (copy)"

		self.save()

		return len(self.lines) - 1

	def _build_item_description(self, line, configured_fixture):
		"""Build a descriptive text for the SO item."""
		parts = []

		if configured_fixture.fixture_template:
			parts.append(configured_fixture.fixture_template)

		if configured_fixture.manufacturable_overall_length_mm:
			length_ft = configured_fixture.manufacturable_overall_length_mm / MM_PER_FOOT
			parts.append(f"{length_ft:.2f}ft ({configured_fixture.manufacturable_overall_length_mm}mm)")

		if configured_fixture.finish:
			parts.append(configured_fixture.finish)

		if configured_fixture.lens_appearance:
			parts.append(configured_fixture.lens_appearance)

		if line.location:
			parts.append(f"Location: {line.location}")

		if line.notes:
			parts.append(f"Notes: {line.notes}")

		return " | ".join(parts) if parts else None


def get_permission_query_conditions(user=None):
	"""
	Return SQL conditions to filter ilL-Project-Fixture-Schedule list for the current user.

	Schedule inherits project privacy rules:
	- If inherits_project_privacy is True, uses linked ilL-Project's access rules
	- Internal roles see all schedules

	Args:
		user: The user to check permissions for. Defaults to current user.

	Returns:
		str: SQL WHERE clause conditions or empty string for full access
	"""
	if not user:
		user = frappe.session.user

	# System Manager and Administrator have full access
	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
		return ""

	# Import project permission helper
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)

	user_customer = _get_user_customer(user)

	if not user_customer:
		# User has no customer link - can only see schedules they own
		return f"""(
			`tabilL-Project-Fixture-Schedule`.owner = {frappe.db.escape(user)}
		)"""

	# Build conditions that check project access
	# Schedule is accessible if:
	# 1. inherits_project_privacy = 1 AND linked project is accessible (project is non-private and same customer, or user is owner/collaborator)
	# 2. inherits_project_privacy = 0 AND schedule.is_private = 0 AND schedule.customer = user_customer
	# 3. Owner always has access
	return f"""(
		`tabilL-Project-Fixture-Schedule`.owner = {frappe.db.escape(user)}
		OR (
			`tabilL-Project-Fixture-Schedule`.customer = {frappe.db.escape(user_customer)}
			AND (
				`tabilL-Project-Fixture-Schedule`.inherits_project_privacy = 0
				AND (`tabilL-Project-Fixture-Schedule`.is_private = 0 OR `tabilL-Project-Fixture-Schedule`.is_private IS NULL)
			)
		)
		OR (
			`tabilL-Project-Fixture-Schedule`.inherits_project_privacy = 1
			AND `tabilL-Project-Fixture-Schedule`.ill_project IN (
				SELECT p.name FROM `tabilL-Project` p
				WHERE (
					p.customer = {frappe.db.escape(user_customer)} AND p.is_private = 0
				) OR (
					p.is_private = 1 AND (
						p.owner = {frappe.db.escape(user)}
						OR p.name IN (
							SELECT parent FROM `tabilL-Child-Project-Collaborator`
							WHERE user = {frappe.db.escape(user)} AND is_active = 1
						)
					)
				)
			)
		)
	)"""


def has_permission(doc, ptype="read", user=None):
	"""
	Check if user has permission to access this specific schedule.

	Schedule inherits project privacy rules when inherits_project_privacy is True.

	Args:
		doc: The ilL-Project-Fixture-Schedule document
		ptype: Permission type (read, write, delete, etc.)
		user: The user to check permissions for. Defaults to current user.

	Returns:
		bool: True if user has permission, False otherwise
	"""
	if not user:
		user = frappe.session.user

	# System Manager and Administrator have full access
	if "System Manager" in frappe.get_roles(user) or user == "Administrator":
		return True

	# Owner always has full access
	if doc.owner == user:
		return True

	# Import project permission helpers
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		has_permission as project_has_permission,
	)

	# If inherits project privacy, delegate to project permission check
	if doc.inherits_project_privacy and doc.ill_project:
		project = frappe.get_doc("ilL-Project", doc.ill_project)
		return project_has_permission(project, ptype, user)

	# Schedule-level privacy check (when not inheriting from project)
	user_customer = _get_user_customer(user)

	# If schedule is not private and user is from same customer
	if not doc.is_private:
		if user_customer and user_customer == doc.customer:
			return True

	return False
