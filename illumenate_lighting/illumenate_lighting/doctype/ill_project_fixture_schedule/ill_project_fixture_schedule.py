# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Conversion constant: millimeters per foot
MM_PER_FOOT = 304.8


# Import permission helpers from project module
def _is_internal_user(user=None):
	"""Check if user has internal/admin access."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_internal_user as project_is_internal,
	)
	return project_is_internal(user)


def _is_dealer_user(user=None):
	"""Check if user has Dealer role."""
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_is_dealer_user as project_is_dealer,
	)
	return project_is_dealer(user)


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

		Creates a Sales Order for the owner's company (the dealer who created the
		project), not the end-client customer. The end-client is stored in the
		project's 'customer' field for reference. Each SO line links to the chosen
		ilL-Configured-Fixture and copies qty, location/notes, and key computed
		fields into custom SO Item fields for quick visibility.

		Returns:
			str: Name of the created Sales Order document
		"""
		# Get the project to access owner_customer
		if not self.ill_project:
			frappe.throw(_("Project is required to create a Sales Order"))

		project = frappe.get_doc("ilL-Project", self.ill_project)

		# Use owner_customer (the dealer's company) for the Sales Order
		# Fall back to the project's customer if owner_customer is not set
		so_customer = project.owner_customer or self.customer

		if not so_customer:
			frappe.throw(_("Owner Company is required to create a Sales Order"))

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
		so.customer = so_customer
		so.project = self.project
		so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)

		# Store the end-client reference in remarks if different from SO customer
		if project.customer and project.customer != so_customer:
			so.remarks = _("End-Client: {0}").format(project.customer)

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

			# Get the configured item or create one if it doesn't exist
			# The configured_item is the sellable Item linked from the configured fixture
			item_code = configured_fixture.configured_item
			if not item_code:
				# Auto-create the configured item for this fixture
				from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
					_create_or_get_configured_item,
					_update_fixture_links,
				)

				item_result = _create_or_get_configured_item(configured_fixture, skip_if_exists=True)
				if item_result.get("success") and item_result.get("item_code"):
					item_code = item_result["item_code"]
					# Update the fixture with the new item code
					_update_fixture_links(
						configured_fixture,
						item_code=item_code,
						bom_name=None,
						work_order_name=None,
					)
					# Also update the cached item code on the schedule line
					line.ill_item_code = item_code
				else:
					frappe.throw(
						_(
							"Line {0}: Failed to create configured Item for fixture {1}. "
							"{2}"
						).format(
							line.line_id or line.idx,
							line.configured_fixture,
							"; ".join(m.get("text", "") for m in item_result.get("messages", [])),
						)
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
	- Dealers see all schedules for their company

	Args:
		user: The user to check permissions for. Defaults to current user.

	Returns:
		str: SQL WHERE clause conditions or empty string for full access
	"""
	if not user:
		user = frappe.session.user

	# Internal users have full access
	if _is_internal_user(user):
		return ""

	# Import project permission helper
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
	)

	user_customer = _get_user_customer(user)
	is_dealer = _is_dealer_user(user)

	if not user_customer:
		# User has no customer link - can only see schedules they own
		return f"""(
			`tabilL-Project-Fixture-Schedule`.owner = {frappe.db.escape(user)}
		)"""

	if is_dealer:
		# Dealers see all schedules for their company (via project link)
		return f"""(
			`tabilL-Project-Fixture-Schedule`.owner = {frappe.db.escape(user)}
			OR `tabilL-Project-Fixture-Schedule`.customer = {frappe.db.escape(user_customer)}
			OR `tabilL-Project-Fixture-Schedule`.ill_project IN (
				SELECT p.name FROM `tabilL-Project` p
				WHERE p.owner_customer = {frappe.db.escape(user_customer)}
			)
		)"""

	# Non-dealer portal user: apply privacy rules
	# Schedule is accessible if:
	# 1. inherits_project_privacy = 1 AND linked project is accessible
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
					p.owner_customer = {frappe.db.escape(user_customer)} AND p.is_private = 0
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
	Dealers have access to all schedules for their company.

	Args:
		doc: The ilL-Project-Fixture-Schedule document
		ptype: Permission type (read, write, delete, etc.)
		user: The user to check permissions for. Defaults to current user.

	Returns:
		bool: True if user has permission, False otherwise
	"""
	if not user:
		user = frappe.session.user

	# Internal users have full access
	if _is_internal_user(user):
		return True

	# Owner always has full access
	if doc.owner == user:
		return True

	# Import project permission helpers
	from illumenate_lighting.illumenate_lighting.doctype.ill_project.ill_project import (
		_get_user_customer,
		has_permission as project_has_permission,
	)

	user_customer = _get_user_customer(user)
	is_dealer = _is_dealer_user(user)

	# If inherits project privacy, delegate to project permission check
	if doc.inherits_project_privacy and doc.ill_project:
		project = frappe.get_doc("ilL-Project", doc.ill_project)
		return project_has_permission(project, ptype, user)

	# Dealers can access all schedules for their company
	if is_dealer and user_customer and user_customer == doc.customer:
		return True

	# Schedule-level privacy check (when not inheriting from project)
	# Non-dealer users can only access non-private schedules
	if not doc.is_private:
		if user_customer and user_customer == doc.customer:
			return True

	return False
