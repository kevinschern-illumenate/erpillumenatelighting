# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

# Conversion constant: millimeters per foot
MM_PER_FOOT = 304.8

# Default price list for configured fixture pricing
DEFAULT_SELLING_PRICE_LIST = "Standard Selling"

# How LED Tape / LED Neon schedule lines are represented on a transaction:
#   configured_item → one row for the single configured SKU (default)
#   raw_components  → exploded leader / tape / jumper / mounting rows
TAPE_NEON_MODE_CONFIGURED = "configured_item"
TAPE_NEON_MODE_RAW = "raw_components"
TAPE_NEON_MODES = (TAPE_NEON_MODE_CONFIGURED, TAPE_NEON_MODE_RAW)

# Savepoint wrapping the whole schedule → Sales Order conversion.
SO_CONVERSION_SAVEPOINT = "ill_schedule_to_sales_order"

# Schedule lifecycle. A draft Sales Order is the customer's *order request*;
# the schedule only becomes ORDERED when our team submits that Sales Order.
# ISSUE is the exception state after a request is deleted, rejected or the
# order is cancelled.
SCHEDULE_STATUSES = (
	"DRAFT",
	"READY",
	"QUOTED",
	"ORDER_REQUESTED",
	"ORDERED",
	"ISSUE",
	"CLOSED",
)

# Statuses from which a schedule may still be converted to a Sales Order.
CONVERTIBLE_STATUSES = ("READY", "QUOTED")

# Statuses whose lines may still be edited from the portal.
EDITABLE_STATUSES = ("DRAFT", "READY")

# Statuses a portal user may request directly; the rest are system-driven.
PORTAL_SETTABLE_STATUSES = ("DRAFT", "READY", "QUOTED")

# Statuses that must have every ilLumenate line fully configured.
CONFIGURED_REQUIRED_STATUSES = ("READY", "QUOTED", "ORDER_REQUESTED", "ORDERED")

ISSUE_STATUS_NOTE = (
	"We were unable to complete this order request. Please reach out to "
	"sales@illumenate.lighting for more information if we have not already "
	"been in contact with you."
)


def _validate_tape_neon_mode(mode):
	"""Normalise and validate a tape/neon representation mode."""
	mode = (mode or TAPE_NEON_MODE_CONFIGURED).strip()
	if mode not in TAPE_NEON_MODES:
		frappe.throw(
			_("Invalid LED Tape/Neon mode {0}. Expected one of: {1}").format(
				mode, ", ".join(TAPE_NEON_MODES)
			)
		)
	return mode


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
		# Enforce locking — locked versions cannot be modified
		if self.get("is_locked"):
			frappe.throw(
				_("This schedule version is locked and cannot be modified. Create a new version to make changes.")
			)

		if self.ill_project:
			project = frappe.get_doc("ilL-Project", self.ill_project)
			# Auto-sync customer from project
			if not self.customer or self.customer != project.customer:
				self.customer = project.customer

		# Validate that all ILLUMENATE lines are configured before READY status
		self._validate_configuration_status()

	def _validate_configuration_status(self):
		"""
		Validate that all ILLUMENATE lines have configured fixtures
		before allowing status to be set to READY or beyond.
		"""
		if self.status not in CONFIGURED_REQUIRED_STATUSES:
			return

		unconfigured_lines = []
		for line in self.lines:
			if line.manufacturer_type == "ILLUMENATE":
				# LED Tape/Neon/Extrusion Kit lines are configured via variant_selections
				if line.product_type in ("LED Tape", "LED Neon", "Extrusion Kit"):
					if not line.variant_selections:
						line_id = line.line_id or f"Row {line.idx}"
						unconfigured_lines.append(line_id)
				# LED Sheet lines are configured when a configured LED Sheet record exists
				elif line.product_type == "LED Sheet":
					if not line.configured_led_sheet:
						line_id = line.line_id or f"Row {line.idx}"
						unconfigured_lines.append(line_id)
				elif not line.configured_fixture:
					line_id = line.line_id or f"Row {line.idx}"
					unconfigured_lines.append(line_id)

		if unconfigured_lines:
			frappe.throw(
				_("Cannot set status to {0}. The following ilLumenate lines are not fully configured: {1}. "
				  "Please configure all fixtures before proceeding.").format(
					self.status,
					", ".join(unconfigured_lines)
				),
				title=_("Unconfigured Fixtures")
			)

	@frappe.whitelist()
	def create_new_version(self, version_notes=None):
		"""
		Create a new version of this fixture schedule.

		1. Lock the current schedule (set is_locked=1, locked_at, locked_by)
		2. Duplicate the schedule with all lines
		3. Increment version number
		4. Set version_parent to the original (V1) schedule
		5. New version starts in DRAFT status

		Returns:
			str: Name of the new versioned schedule
		"""
		if self.get("is_locked"):
			frappe.throw(_("This schedule version is already locked. Cannot create another version from a locked schedule."))

		# 1. Lock the current schedule
		# Use frappe.db.set_value to avoid conflict with Document.is_locked property
		frappe.db.set_value(self.doctype, self.name, {
			"is_locked": 1,
			"locked_at": frappe.utils.now_datetime(),
			"locked_by": frappe.session.user,
		})

		# Determine version_parent: always points to the V1 (original) schedule
		version_parent = self.version_parent or self.name

		# 2. Create a new schedule document (deep copy)
		new_schedule = frappe.new_doc("ilL-Project-Fixture-Schedule")
		new_schedule.schedule_name = self.schedule_name
		new_schedule.ill_project = self.ill_project
		new_schedule.customer = self.customer
		new_schedule.status = "DRAFT"
		new_schedule.inherits_project_privacy = self.inherits_project_privacy
		new_schedule.is_private = self.is_private
		new_schedule.notes = self.notes
		new_schedule.project = self.project

		# 3. Set versioning fields
		new_schedule.version = (self.version or 1) + 1
		new_schedule.version_parent = version_parent
		new_schedule.version_notes = version_notes

		# 4. Deep copy all fixture schedule lines
		for line in self.lines:
			new_line = new_schedule.append("lines", {})
			for field in line.as_dict():
				if field not in ("name", "idx", "parent", "parenttype", "parentfield", "doctype", "creation", "modified", "modified_by", "owner"):
					new_line.set(field, line.get(field))

		# 5. Deep copy collaborators
		for collab in (self.collaborators or []):
			new_collab = new_schedule.append("collaborators", {})
			for field in collab.as_dict():
				if field not in ("name", "idx", "parent", "parenttype", "parentfield", "doctype", "creation", "modified", "modified_by", "owner"):
					new_collab.set(field, collab.get(field))

		new_schedule.insert(ignore_permissions=True)
		# No commit here: callers compose this with other writes (e.g. the
		# QUOTED → READY auto-version) and must stay able to roll the lot back.

		frappe.msgprint(
			_("Version {0} created: {1}").format(new_schedule.version, new_schedule.name),
			indicator="green",
			alert=True,
		)

		return new_schedule.name

	@frappe.whitelist()
	def create_sales_order(
		self,
		tape_neon_mode=TAPE_NEON_MODE_CONFIGURED,
		include_accessories=1,
		include_other=0,
	):
		"""
		Convert this fixture schedule to a Sales Order.

		This is the main workflow for dealers: when the schedule is in READY
		(or QUOTED) status they click "Convert to Sales Order", which:

		1. Creates configured Items for each fixture (if they don't exist)
		2. Checks if Items already exist and updates pricing if there are discrepancies
		3. Creates BOMs for each configured fixture (if they don't exist)
		4. Checks if BOMs already exist and updates if there are discrepancies
		5. Creates the Sales Order with all line items

		The line-building itself is delegated to :meth:`append_quote_lines`, the
		single converter shared with the desk "Get Items From → Fixture Schedule"
		flow, so a Sales Order always matches the Quotation built from the same
		schedule.

		The Sales Order is created for the owner's company (the dealer), not the
		end-client customer. The end-client is stored for reference.

		Args:
			tape_neon_mode: ``"configured_item"`` (default) adds a single row per
				configured tape/neon SKU; ``"raw_components"`` explodes the line
				into its component rows.
			include_accessories: Include ACCESSORY lines (default on).
			include_other: Include OTHER-manufacturer lines (default off — they
				have no catalog Item, so they are only reported).

		Returns:
			str: Name of the created Sales Order document
		"""
		return self.create_sales_order_result(
			tape_neon_mode=tape_neon_mode,
			include_accessories=include_accessories,
			include_other=include_other,
		)["sales_order"]

	@frappe.whitelist()
	def create_sales_order_result(
		self,
		tape_neon_mode=TAPE_NEON_MODE_CONFIGURED,
		include_accessories=1,
		include_other=0,
	):
		"""Convert this schedule to a Sales Order and return the full result.

		Same behaviour as :meth:`create_sales_order` but returns a dict::

			{"sales_order": "SAL-ORD-0001", "warnings": [...], "counts": {...}}

		so callers (portal, desk) can surface skipped lines instead of silently
		dropping them.

		The conversion is atomic and idempotent: the schedule row is locked for
		the rest of the request, an already-linked Sales Order is returned as-is,
		and every Item / Item Price / BOM / configured-record write is rolled
		back to a savepoint if anything fails before the order is inserted.
		"""
		tape_neon_mode = _validate_tape_neon_mode(tape_neon_mode)

		allowed, reason = can_convert_schedule_to_order(self, frappe.session.user)
		if not allowed:
			frappe.throw(reason, frappe.PermissionError)

		# Serialise concurrent conversions of the same schedule. The lock is held
		# until the request transaction ends, so a second caller blocks here and
		# then sees the order the first one linked instead of creating its own.
		frappe.db.sql(
			"select name from `tabilL-Project-Fixture-Schedule` where name = %s for update",
			(self.name,),
		)

		existing = self.get_linked_sales_order()
		if existing:
			return {
				"sales_order": existing,
				"warnings": [],
				"counts": {},
				"already_existed": True,
			}

		# Re-read under the lock: the status may have changed since this document
		# was loaded (including by a conversion that just finished).
		current_status = frappe.db.get_value(
			"ilL-Project-Fixture-Schedule", self.name, "status"
		)
		if current_status not in CONVERTIBLE_STATUSES:
			frappe.throw(
				_("Schedule must be in READY or QUOTED status to convert to a Sales Order")
			)

		frappe.db.savepoint(SO_CONVERSION_SAVEPOINT)
		try:
			so_name, counts = self._build_and_insert_sales_order(
				tape_neon_mode=tape_neon_mode,
				include_accessories=bool(cint(include_accessories)),
				include_other=bool(cint(include_other)),
			)
		except Exception:
			# Items, Item Prices, BOMs and configured-record links are written
			# before the Sales Order insert. Without this rollback a failed
			# attempt would leave those partial manufacturing changes behind.
			frappe.db.rollback(save_point=SO_CONVERSION_SAVEPOINT)
			raise

		# The draft Sales Order is the customer's order request; ORDERED is set
		# by the Sales Order submit hook once our team approves it.
		self.set_lifecycle_status("ORDER_REQUESTED", sales_order=so_name)

		# Build success message
		msg_parts = [_("Sales Order {0} created successfully").format(
			frappe.utils.get_link_to_form("Sales Order", so_name)
		)]
		if counts.get("items_created"):
			msg_parts.append(_("{0} Item(s) created").format(counts["items_created"]))
		if counts.get("items_updated"):
			msg_parts.append(_("{0} Item(s) updated").format(counts["items_updated"]))
		if counts.get("boms_created"):
			msg_parts.append(_("{0} BOM(s) created").format(counts["boms_created"]))
		if counts.get("boms_updated"):
			msg_parts.append(_("{0} BOM(s) updated").format(counts["boms_updated"]))

		warnings = list(counts.get("messages") or [])

		message = ". ".join(msg_parts)
		if warnings:
			warning_list = "<br>".join(warnings)
			message += f"<br><br>{_('Some lines were not added:')}<br>{warning_list}"

		frappe.msgprint(
			message,
			indicator="orange" if warnings else "green",
			alert=not warnings,
		)

		return {
			"sales_order": so_name,
			"warnings": warnings,
			"counts": counts,
		}

	def get_linked_sales_order(self):
		"""Return the active Sales Order already created from this schedule, if any.

		Cancelled orders (docstatus 2) do not count, so a schedule can be
		re-converted after its order was cancelled.
		"""
		if not frappe.get_meta("Sales Order").has_field("ill_fixture_schedule"):
			return None

		return frappe.db.get_value(
			"Sales Order",
			{"ill_fixture_schedule": self.name, "docstatus": ["<", 2]},
			"name",
			order_by="creation asc",
		)

	def set_lifecycle_status(self, new_status, sales_order=None, note=None):
		"""System-driven status change (order requested / approved / issue).

		Written directly because these run inside another document's
		transaction (Sales Order submit/cancel) and must never be blocked by
		portal editing rules such as version locks.
		"""
		if new_status not in SCHEDULE_STATUSES:
			frappe.throw(_("Invalid schedule status {0}").format(new_status))

		related_order = sales_order or self.get("sales_order")
		values = {"status": new_status, "status_note": note or None}
		if sales_order is not None:
			values["sales_order"] = sales_order or None
		self.db_set(values, notify=True)
		self.add_comment(
			"Info",
			_("Schedule status set to {0}{1}").format(
				new_status,
				_(" (Sales Order {0})").format(related_order) if related_order else "",
			),
		)

		from illumenate_lighting.illumenate_lighting.portal.notifications import (
			notify_schedule_status,
		)

		notify_schedule_status(self, new_status, sales_order=related_order)

	def _build_and_insert_sales_order(
		self,
		tape_neon_mode,
		include_accessories,
		include_other,
	):
		"""Build the Sales Order rows and insert the order. Returns ``(name, counts)``.

		Must be called inside :attr:`SO_CONVERSION_SAVEPOINT` — it mutates Items,
		Item Prices, BOMs and configured records before inserting the order.
		"""
		if not self.ill_project:
			frappe.throw(_("Project is required to create a Sales Order"))

		project = frappe.get_doc("ilL-Project", self.ill_project)

		# Use owner_customer (the dealer's company) for the Sales Order
		# Fall back to the project's customer if owner_customer is not set
		so_customer = project.owner_customer or self.customer

		if not so_customer:
			frappe.throw(_("Owner Company is required to create a Sales Order"))

		so = frappe.new_doc("Sales Order")
		so.customer = so_customer
		so.project = self.project
		so.delivery_date = frappe.utils.add_days(frappe.utils.nowdate(), 30)
		self._set_optional_doc_value(so, "ill_fixture_schedule", self.name)

		# Store the end-client reference in remarks if different from SO customer
		if project.customer and project.customer != so_customer:
			so.remarks = _("End-Client: {0}").format(project.customer)

		counts = self.append_quote_lines(
			so,
			include_accessories=include_accessories,
			include_other=include_other,
			tape_neon_mode=tape_neon_mode,
			sync_existing_boms=True,
			require_bom=True,
		)

		if not counts.get("rows_added"):
			detail = "<br>".join(counts.get("messages") or []) or _(
				"The schedule has no orderable lines."
			)
			frappe.throw(
				_("Nothing could be added to a Sales Order from this schedule.<br><br>{0}").format(
					detail
				)
			)

		so.insert()

		return so.name, counts

	def get_transaction_line_summary(self, include_accessories=True, include_other=True):
		"""Return a lightweight breakdown of how many lines of each type would
		be imported into a Quotation / Sales Order.

		Used by the desk "Get Items From → Fixture Schedule" picker to preview
		the import before committing. Does not modify any documents.
		"""
		summary = {
			"fixtures": 0,
			"tape_neon": 0,
			"kits": 0,
			"sheets": 0,
			"accessories": 0,
			"other": 0,
			"unconfigured": 0,
		}

		for line in self.lines:
			mt = line.manufacturer_type
			if mt == "ILLUMENATE":
				pt = line.product_type
				if pt in ("LED Tape", "LED Neon"):
					if line.variant_selections:
						summary["tape_neon"] += 1
					else:
						summary["unconfigured"] += 1
				elif pt == "Extrusion Kit":
					if line.variant_selections:
						summary["kits"] += 1
					else:
						summary["unconfigured"] += 1
				elif pt == "LED Sheet":
					if line.configured_led_sheet:
						summary["sheets"] += 1
					else:
						summary["unconfigured"] += 1
				elif line.configured_fixture:
					summary["fixtures"] += 1
				else:
					summary["unconfigured"] += 1
			elif mt == "ACCESSORY":
				if line.accessory_item:
					summary["accessories"] += 1
				else:
					summary["unconfigured"] += 1
			elif mt == "OTHER":
				summary["other"] += 1

		return summary

	def append_quote_lines(
		self,
		target_doc,
		include_accessories=True,
		include_other=False,
		tape_neon_mode=TAPE_NEON_MODE_CONFIGURED,
		sync_existing_boms=False,
		require_bom=False,
	):
		"""Append this schedule's line items onto a target transaction document
		(Quotation or Sales Order) and return a summary dict.

		This is the single schedule → transaction converter. ``create_sales_order``
		delegates to it so a Sales Order and a Quotation built from the same
		schedule always contain the same rows:

		* Configured fixtures → single configured Item row (Item + BOM ensured)
		* LED Tape / LED Neon  → single configured Item row, or exploded
		  component rows when ``tape_neon_mode="raw_components"``
		* Extrusion Kit        → exploded component rows (times ``line.qty``)
		* LED Sheet            → single configured Item row (qty = ``line.qty``)
		* Accessories          → direct Item row
		* Other manufacturer   → reported as skipped (no catalog Item)

		Every row appended for a schedule line is stamped with
		``ill_section_label`` (from ``line.location``), ``ill_fixture_type``
		(from ``line.line_id``), ``ill_schedule_line_id`` and
		``additional_notes`` (fixture type + notes).

		Args:
			sync_existing_boms: When ``True`` an *existing* BOM that no longer
				matches its configured fixture is regenerated. Only the Sales
				Order path enables this — building a quotation must not
				deactivate submitted BOMs.
			require_bom: When ``True`` a manufactured line without a usable BOM
				aborts the whole conversion instead of being ordered unbuildable.
				Only the Sales Order path enables this.

		The schedule status is left unchanged; only ``target_doc.items`` is
		mutated. The caller is responsible for saving ``target_doc``.
		"""
		import json as _json

		tape_neon_mode = _validate_tape_neon_mode(tape_neon_mode)

		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			_create_or_get_bom,
			_create_or_get_configured_item,
			_update_fixture_links,
		)

		counts = {
			"fixtures": 0,
			"tape_neon": 0,
			"kits": 0,
			"sheets": 0,
			"accessories": 0,
			"other": 0,
			"skipped": 0,
			"rows_added": 0,
			"items_created": 0,
			"items_updated": 0,
			"boms_created": 0,
			"boms_updated": 0,
			"messages": [],
		}

		rows_before = len(target_doc.items)

		for line in self.lines:
			line_label = line.line_id or f"Row {line.idx}"
			mt = line.manufacturer_type

			# ── ilLumenate: LED Tape / LED Neon ───────────────────────
			if mt == "ILLUMENATE" and line.product_type in ("LED Tape", "LED Neon"):
				if not line.variant_selections:
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: {1} is not configured — skipped").format(
							line_label, line.product_type
						)
					)
					continue
				try:
					config_data = _json.loads(line.variant_selections)
				except (ValueError, TypeError):
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: invalid {1} configuration data — skipped").format(
							line_label, line.product_type
						)
					)
					continue

				from illumenate_lighting.illumenate_lighting.api.tape_neon_configurator import (
					create_tape_neon_so_lines,
				)

				line_rows_before = len(target_doc.items)
				use_raw_components = tape_neon_mode == TAPE_NEON_MODE_RAW

				if not use_raw_components:
					ctn_name = line.get("configured_tape_neon")
					if not (ctn_name and frappe.db.exists("ilL-Configured-Tape-Neon", ctn_name)):
						use_raw_components = True
						counts["messages"].append(
							_(
								"Line {0}: no configured tape/neon record — "
								"imported as raw components instead"
							).format(line_label)
						)
					else:
						if self._append_configured_tape_neon_row(
							target_doc, line, line_label, ctn_name, counts, require_bom=require_bom
						):
							counts["tape_neon"] += 1
						else:
							counts["skipped"] += 1

				if use_raw_components:
					result = create_tape_neon_so_lines(
						target_doc, line, config_data, qty_multiplier=line.qty or 1
					)
					if result.get("items_added"):
						counts["tape_neon"] += 1
					else:
						counts["skipped"] += 1
					for msg in result.get("messages", []):
						counts["messages"].append(_("Line {0}: {1}").format(line_label, msg))

				self._stamp_group_fields(target_doc, line_rows_before, line)
				continue

			# ── ilLumenate: Extrusion Kit ─────────────────────────────
			if mt == "ILLUMENATE" and line.product_type == "Extrusion Kit":
				if not line.variant_selections:
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: Extrusion Kit is not configured — skipped").format(line_label)
					)
					continue
				try:
					config_data = _json.loads(line.variant_selections)
				except (ValueError, TypeError):
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: invalid Extrusion Kit configuration data — skipped").format(line_label)
					)
					continue

				from illumenate_lighting.illumenate_lighting.api.extrusion_kit_configurator import (
					create_kit_so_lines,
				)
				line_rows_before = len(target_doc.items)
				result = create_kit_so_lines(
					target_doc, line, config_data, qty_multiplier=line.qty or 1
				)
				if result.get("items_added"):
					counts["kits"] += 1
				else:
					counts["skipped"] += 1
				for msg in result.get("messages", []):
					counts["messages"].append(_("Line {0}: {1}").format(line_label, msg))
				self._stamp_group_fields(target_doc, line_rows_before, line)
				continue

			# ── ilLumenate: LED Sheet ─────────────────────────────────
			if mt == "ILLUMENATE" and line.product_type == "LED Sheet":
				if not line.configured_led_sheet:
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: LED Sheet is not configured — skipped").format(line_label)
					)
					continue
				if not frappe.db.exists("ilL-Configured-LED-Sheet", line.configured_led_sheet):
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: configured LED Sheet {1} no longer exists — skipped").format(
							line_label, line.configured_led_sheet
						)
					)
					continue

				from illumenate_lighting.illumenate_lighting.api.quote_order_configurator import (
					PRODUCT_TYPE_SHEET,
					_apply_artifact_to_row,
					_ensure_configured_artifacts,
				)

				try:
					artifact = _ensure_configured_artifacts(
						PRODUCT_TYPE_SHEET, None, None, line.configured_led_sheet
					)
				except Exception as exc:
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: could not prepare LED Sheet {1} — skipped ({2})").format(
							line_label, line.configured_led_sheet, str(exc)
						)
					)
					frappe.log_error(
						title=f"Schedule Conversion: LED Sheet {line.configured_led_sheet}",
						message=frappe.get_traceback(),
					)
					continue

				line_rows_before = len(target_doc.items)
				row = target_doc.append("items", {})
				# qty is the *bundle* count from the schedule line — never
				# sheets_needed. The configured sheet MSRP already prices the
				# whole bundle, so multiplying by sheets_needed double-counts.
				_apply_artifact_to_row(target_doc, row, artifact, line.qty or 1, None)
				self._stamp_group_fields(target_doc, line_rows_before, line)
				counts["sheets"] += 1
				continue

			# ── ilLumenate: Configured Fixture ────────────────────────
			if mt == "ILLUMENATE":
				if not line.configured_fixture:
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: fixture is not configured — skipped").format(line_label)
					)
					continue
				if not frappe.db.exists("ilL-Configured-Fixture", line.configured_fixture):
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: configured fixture {1} no longer exists — skipped").format(
							line_label, line.configured_fixture
						)
					)
					continue

				configured_fixture = frappe.get_doc("ilL-Configured-Fixture", line.configured_fixture)

				# Step 1: ensure the configured Item exists
				item_code = configured_fixture.configured_item
				item_existed = bool(item_code and frappe.db.exists("Item", item_code))
				if not item_existed:
					item_result = _create_or_get_configured_item(configured_fixture, skip_if_exists=True)
					if item_result.get("success") and item_result.get("item_code"):
						item_code = item_result["item_code"]
						if item_result.get("created"):
							counts["items_created"] += 1
					else:
						counts["skipped"] += 1
						counts["messages"].append(
							_("Line {0}: failed to create Item for fixture {1} — skipped").format(
								line_label, line.configured_fixture
							)
						)
						continue

				# Ensure brand + MSRP Item Price so the quotation rate populates.
				if self._check_and_update_item_pricing(item_code, configured_fixture):
					counts["items_updated"] += 1

				# Step 2: ensure the BOM exists
				bom_name = configured_fixture.bom
				bom_existed = bool(bom_name and frappe.db.exists("BOM", bom_name))
				bom_detail = ""
				if not bom_existed:
					bom_result = _create_or_get_bom(configured_fixture, item_code, skip_if_exists=True)
					if bom_result.get("success") and bom_result.get("bom_name"):
						bom_name = bom_result["bom_name"]
						if bom_result.get("created"):
							counts["boms_created"] += 1
					else:
						bom_detail = "; ".join(
							m.get("text", "") for m in bom_result.get("messages", [])
						)
						frappe.log_error(
							title=f"Quote-from-Schedule BOM Warning for {line.configured_fixture}",
							message=bom_detail,
						)
						bom_name = None
				elif sync_existing_boms and self._check_and_update_bom(bom_name, configured_fixture):
					counts["boms_updated"] += 1
					bom_name = configured_fixture.bom or bom_name

				if require_bom and not bom_name:
					# A manufactured fixture with no BOM cannot be built, so ordering
					# it would create an unfulfillable line.
					frappe.throw(
						_(
							"Line {0}: a BOM could not be generated for fixture {1}, "
							"so the order was not created. {2}"
						).format(line_label, line.configured_fixture, bom_detail)
					)

				if not item_existed or not bom_existed:
					_update_fixture_links(
						configured_fixture,
						item_code=item_code,
						bom_name=bom_name,
						work_order_name=None,
					)

				self._cache_line_item_code(line, item_code)

				row = target_doc.append("items", {})
				row.item_code = item_code
				row.qty = line.qty or 1
				row.description = self._build_item_description(line, configured_fixture)
				self._set_optional_row_value(row, "ill_product_type", "Linear Fixture")
				self._set_optional_row_value(row, "ill_configured_fixture", line.configured_fixture)
				self._set_optional_row_value(row, "ill_configured_item", item_code)
				self._set_optional_row_value(row, "ill_bom", bom_name)
				self._set_optional_row_value(row, "ill_template_code", configured_fixture.fixture_template)
				self._set_optional_row_value(
					row, "ill_requested_length_mm", configured_fixture.requested_overall_length_mm
				)
				self._set_optional_row_value(
					row, "ill_mfg_length_mm", configured_fixture.manufacturable_overall_length_mm
				)
				self._set_optional_row_value(row, "ill_runs_count", configured_fixture.runs_count)
				self._set_optional_row_value(row, "ill_total_watts", configured_fixture.total_watts)
				self._set_optional_row_value(row, "ill_finish", configured_fixture.finish)
				self._set_optional_row_value(row, "ill_lens", configured_fixture.lens_appearance)
				self._set_optional_row_value(row, "ill_engine_version", configured_fixture.engine_version)
				self._stamp_group_fields(target_doc, len(target_doc.items) - 1, line)
				counts["fixtures"] += 1
				continue

			# ── Accessory / Component ─────────────────────────────────
			if mt == "ACCESSORY":
				if not include_accessories:
					counts["skipped"] += 1
					continue
				if not line.accessory_item:
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: accessory has no Item selected — skipped").format(line_label)
					)
					continue
				if not frappe.db.exists("Item", line.accessory_item):
					counts["skipped"] += 1
					counts["messages"].append(
						_("Line {0}: accessory Item {1} no longer exists — skipped").format(
							line_label, line.accessory_item
						)
					)
					continue

				row = target_doc.append("items", {})
				row.item_code = line.accessory_item
				row.qty = line.qty or 1
				if line.accessory_item_name:
					row.description = line.accessory_item_name
				self._stamp_group_fields(target_doc, len(target_doc.items) - 1, line)
				counts["accessories"] += 1
				continue

			# ── Other manufacturer (no catalog Item) ──────────────────
			if mt == "OTHER":
				counts["other"] += 1
				if not include_other:
					counts["skipped"] += 1
				label_bits = [b for b in [line.manufacturer_name, line.fixture_model_number] if b]
				counts["messages"].append(
					_("Line {0}: other-manufacturer item ({1}) has no catalog Item and was not added").format(
						line_label, " ".join(label_bits) or _("unspecified")
					)
				)
				continue

		counts["rows_added"] = len(target_doc.items) - rows_before
		return counts

	def _set_optional_row_value(self, row, fieldname, value):
		"""Set a document/child-row field only when it exists on that doctype."""
		if value is None:
			return
		try:
			if not row.meta.has_field(fieldname):
				return
		except Exception:
			return
		row.set(fieldname, value)

	# Parent documents (Quotation / Sales Order headers) use the same guard.
	_set_optional_doc_value = _set_optional_row_value

	def _cache_line_item_code(self, line, item_code):
		"""Persist the resolved configured Item back onto the schedule line.

		Mutating ``line`` alone is a no-op because the schedule is never saved
		during a conversion, so the value is written straight to the child row.
		"""
		if not item_code or line.get("ill_item_code") == item_code:
			return
		line.ill_item_code = item_code
		if not line.get("name") or line.get("__islocal"):
			return
		try:
			frappe.db.set_value(
				line.doctype, line.name, "ill_item_code", item_code, update_modified=False
			)
		except Exception:
			frappe.log_error(
				title=f"Schedule line item-code cache failed for {line.name}",
				message=frappe.get_traceback(),
			)

	def _schedule_line_group_fields(self, line):
		"""Return ``(section_label, additional_notes)`` for a schedule line.

		``line.location`` is the Section / Room grouping key (``ill_section_label``).
		The fixture type lives only in the structural ``ill_fixture_type`` field,
		which print formats render as a row above the item; ``additional_notes``
		carries just the customer's own line notes, printed under the item.
		"""
		section_label = line.location or None
		notes = (line.notes or "").strip() or None
		return section_label, notes

	def _stamp_group_fields(self, target_doc, rows_before_count, line):
		"""Stamp grouping + traceability fields on every row a branch appended.

		Using a before/after row-count diff means this works whether the branch
		added a single row (fixture, accessory, configured tape/neon, LED sheet)
		or several (raw tape/neon components, extrusion kit components).
		"""
		section_label, additional_notes = self._schedule_line_group_fields(line)
		fixture_type = line.line_id or None
		schedule_line_id = line.get("name") or None

		if not (section_label or additional_notes or fixture_type or schedule_line_id):
			return

		for row in target_doc.items[rows_before_count:]:
			self._set_optional_row_value(row, "ill_section_label", section_label)
			self._set_optional_row_value(row, "ill_fixture_type", fixture_type)
			self._set_optional_row_value(row, "ill_schedule_line_id", schedule_line_id)
			self._set_optional_row_value(row, "additional_notes", additional_notes)

	def _append_configured_tape_neon_row(
		self, target_doc, line, line_label, ctn_name, counts, require_bom=False
	):
		"""Append a single row for the configured tape/neon SKU of ``line``.

		Ensures the configured Item, its BOM and its MSRP Item Price exist, then
		appends one row carrying ``line.qty``. Returns ``True`` when a row was
		appended, ``False`` when the line had to be skipped (a message is added
		to ``counts["messages"]`` in that case).

		With ``require_bom`` a missing BOM aborts the conversion instead of
		producing an unbuildable order line.
		"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			_create_or_get_configured_tape_neon_item,
		)
		from illumenate_lighting.illumenate_lighting.api.tape_neon_bom import (
			create_or_get_tape_neon_bom,
		)

		configured = frappe.get_doc("ilL-Configured-Tape-Neon", ctn_name)

		# Step 1: ensure the configured Item exists
		item_code = configured.configured_item
		if not (item_code and frappe.db.exists("Item", item_code)):
			item_result = _create_or_get_configured_tape_neon_item(configured, skip_if_exists=True)
			if not (item_result.get("success") and item_result.get("item_code")):
				counts["messages"].append(
					_("Line {0}: failed to create Item for configured {1} {2} — skipped").format(
						line_label, line.product_type, ctn_name
					)
				)
				return False
			item_code = item_result["item_code"]
			if item_result.get("created"):
				counts["items_created"] += 1
			if configured.configured_item != item_code:
				configured.db_set("configured_item", item_code, update_modified=False)
				configured.configured_item = item_code

		# Ensure brand + MSRP Item Price so the transaction rate populates.
		if self._check_and_update_tape_neon_item_pricing(item_code, configured):
			counts["items_updated"] = counts.get("items_updated", 0) + 1

		# Step 2: ensure the BOM exists
		bom_name = configured.bom
		if not (bom_name and frappe.db.exists("BOM", bom_name)):
			bom_result = create_or_get_tape_neon_bom(configured, item_code, skip_if_exists=True)
			if bom_result.get("success") and bom_result.get("bom_name"):
				bom_name = bom_result["bom_name"]
				if bom_result.get("created"):
					counts["boms_created"] += 1
			else:
				bom_detail = "; ".join(m.get("text", "") for m in bom_result.get("messages", []))
				frappe.log_error(
					title=f"Quote-from-Schedule BOM Warning for {ctn_name}",
					message=bom_detail,
				)
				bom_name = None
				if require_bom:
					# A manufactured tape/neon SKU with no BOM cannot be built.
					frappe.throw(
						_(
							"Line {0}: a BOM could not be generated for configured "
							"{1} {2}, so the order was not created. {3}"
						).format(line_label, line.product_type, ctn_name, bom_detail)
					)

		row = target_doc.append("items", {})
		row.item_code = item_code
		row.qty = line.qty or 1
		row.description = self._build_tape_neon_item_description(line, configured)
		self._set_optional_row_value(row, "ill_product_type", line.product_type)
		self._set_optional_row_value(row, "ill_configured_tape_neon", ctn_name)
		self._set_optional_row_value(row, "ill_configured_item", item_code)
		self._set_optional_row_value(row, "ill_bom", bom_name)
		self._set_optional_row_value(row, "ill_template_code", configured.tape_neon_template)
		self._set_optional_row_value(row, "ill_requested_length_mm", configured.requested_length_mm)
		self._set_optional_row_value(row, "ill_mfg_length_mm", configured.manufacturable_length_mm)
		self._set_optional_row_value(row, "ill_runs_count", configured.total_segments)
		self._set_optional_row_value(row, "ill_total_watts", configured.total_watts)
		self._set_optional_row_value(row, "ill_finish", configured.finish)
		self._set_optional_row_value(row, "ill_engine_version", configured.engine_version)
		return True

	def _check_and_update_item_pricing(self, item_code, configured_fixture):
		"""
		Check if Item pricing and brand match the configured fixture and update if needed.

		Args:
			item_code: The Item code to check
			configured_fixture: The ilL-Configured-Fixture document

		Returns:
			bool: True if the Item was updated, False otherwise
		"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			ILLUMENATE_BRAND,
		)

		updated = False

		# Ensure brand is set on the Item
		current_brand = frappe.db.get_value("Item", item_code, "brand")
		if current_brand != ILLUMENATE_BRAND:
			frappe.db.set_value("Item", item_code, "brand", ILLUMENATE_BRAND)
			updated = True

		# Get the latest pricing from the configured fixture's pricing snapshot
		if not configured_fixture.pricing_snapshot:
			return updated

		latest_pricing = configured_fixture.pricing_snapshot[-1]
		fixture_msrp = latest_pricing.msrp_unit

		# Check current Item pricing (standard_rate in Item Price)
		current_price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "selling": 1, "price_list": DEFAULT_SELLING_PRICE_LIST},
			"price_list_rate"
		)

		# If no price exists or prices don't match, update
		if current_price is None or abs(float(current_price) - float(fixture_msrp)) > 0.01:
			# Create or update Item Price
			if current_price is not None:
				# Update existing price
				frappe.db.set_value(
					"Item Price",
					{"item_code": item_code, "selling": 1, "price_list": DEFAULT_SELLING_PRICE_LIST},
					"price_list_rate",
					fixture_msrp
				)
			else:
				# Check if price list exists
				if frappe.db.exists("Price List", DEFAULT_SELLING_PRICE_LIST):
					# Create new Item Price
					item_price = frappe.new_doc("Item Price")
					item_price.item_code = item_code
					item_price.price_list = DEFAULT_SELLING_PRICE_LIST
					item_price.selling = 1
					item_price.price_list_rate = fixture_msrp
					item_price.insert(ignore_permissions=True)
				else:
					# Log warning if price list doesn't exist
					frappe.log_error(
						title=f"Item Price Not Created for {item_code}",
						message=f"Price list '{DEFAULT_SELLING_PRICE_LIST}' does not exist. Item pricing could not be set."
					)

			updated = True

		return updated

	def _check_and_update_tape_neon_item_pricing(self, item_code, configured_tape_neon):
		"""
		Check if a tape/neon Item has correct brand and MSRP Item Price and update if needed.

		Mirrors ``_check_and_update_item_pricing`` but sources the MSRP from
		the configured tape/neon record's pricing snapshot.

		Args:
			item_code: The Item code to check
			configured_tape_neon: The ilL-Configured-Tape-Neon document

		Returns:
			bool: True if the Item was updated, False otherwise
		"""
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			ILLUMENATE_BRAND,
		)

		updated = False

		# Ensure brand is set on the Item
		current_brand = frappe.db.get_value("Item", item_code, "brand")
		if current_brand != ILLUMENATE_BRAND:
			frappe.db.set_value("Item", item_code, "brand", ILLUMENATE_BRAND)
			updated = True

		# Get the latest pricing from the configured tape/neon's pricing snapshot
		if not configured_tape_neon.pricing_snapshot:
			return updated

		latest_pricing = configured_tape_neon.pricing_snapshot[-1]
		msrp = latest_pricing.msrp_unit

		# Check current Item pricing
		current_price = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "selling": 1, "price_list": DEFAULT_SELLING_PRICE_LIST},
			"price_list_rate"
		)

		if current_price is None or abs(float(current_price) - float(msrp)) > 0.01:
			if current_price is not None:
				frappe.db.set_value(
					"Item Price",
					{"item_code": item_code, "selling": 1, "price_list": DEFAULT_SELLING_PRICE_LIST},
					"price_list_rate",
					msrp
				)
			else:
				if frappe.db.exists("Price List", DEFAULT_SELLING_PRICE_LIST):
					item_price = frappe.new_doc("Item Price")
					item_price.item_code = item_code
					item_price.price_list = DEFAULT_SELLING_PRICE_LIST
					item_price.selling = 1
					item_price.price_list_rate = msrp
					item_price.insert(ignore_permissions=True)
				else:
					frappe.log_error(
						title=f"Item Price Not Created for {item_code}",
						message=f"Price list '{DEFAULT_SELLING_PRICE_LIST}' does not exist. Item pricing could not be set."
					)

			updated = True

		return updated

	def _check_and_update_bom(self, bom_name, configured_fixture):
		"""
		Check if BOM matches the configured fixture and update if there are discrepancies.

		Checks for:
		- Missing components
		- Quantity mismatches
		- Extra components that should not be there

		Args:
			bom_name: The BOM name to check
			configured_fixture: The ilL-Configured-Fixture document

		Returns:
			bool: True if the BOM was updated (or needs regeneration), False otherwise
		"""
		if not frappe.db.exists("BOM", bom_name):
			return False

		bom = frappe.get_doc("BOM", bom_name)

		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			build_fixture_bom_items,
		)

		# Compare against the same generator that builds a BOM, so a changed or
		# extra component is detected rather than only the handful of roles a
		# hand-maintained expectation map happened to cover.
		expected_items = {}
		for row in build_fixture_bom_items(configured_fixture) or []:
			expected_items[row["item_code"]] = expected_items.get(row["item_code"], 0) + row["qty"]

		if not expected_items:
			# Nothing to compare against — leave the existing BOM alone rather
			# than destroying it based on an empty expectation.
			return False

		bom_items = {}
		for item in bom.items or []:
			bom_items[item.item_code] = bom_items.get(item.item_code, 0) + item.qty

		has_discrepancy = set(expected_items) != set(bom_items) or any(
			abs(float(bom_items[code]) - float(qty)) > 0.001
			for code, qty in expected_items.items()
		)

		if not has_discrepancy:
			return False

		# Verify configured_item exists before proceeding
		item_code = configured_fixture.configured_item
		if not item_code:
			frappe.log_error(
				title=f"BOM Update Failed for {configured_fixture.name}",
				message="Cannot update BOM: configured_item is not set on the fixture"
			)
			return False

		# Import manufacturing generator for BOM creation
		from illumenate_lighting.illumenate_lighting.api.manufacturing_generator import (
			_create_or_get_bom,
		)

		if bom.docstatus not in (0, 1):
			return False

		# Build the replacement *before* retiring the current BOM so a failure
		# here leaves the fixture with its existing, working BOM.
		# Submitting a new default BOM re-points the Item at it automatically.
		previous_bom = configured_fixture.bom
		configured_fixture.bom = None
		bom_result = _create_or_get_bom(
			configured_fixture,
			item_code,
			skip_if_exists=False
		)

		if not (bom_result.get("success") and bom_result.get("bom_name")):
			configured_fixture.bom = previous_bom
			frappe.log_error(
				title=f"BOM Update Failed for {configured_fixture.name}",
				message="; ".join(m.get("text", "") for m in bom_result.get("messages", [])),
			)
			return False

		configured_fixture.bom = bom_result["bom_name"]
		configured_fixture.save(ignore_permissions=True)

		# Replacement is in place — now retire the superseded BOM.
		if bom.docstatus == 0:
			frappe.delete_doc("BOM", bom_name, force=True)
		else:
			bom.is_active = 0
			bom.is_default = 0
			bom.save(ignore_permissions=True)

		return True

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
		self.add_comment("Info", _("Quote requested"))

		from illumenate_lighting.illumenate_lighting.portal.notifications import (
			notify_schedule_status,
		)

		notify_schedule_status(self, "QUOTED")

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

	@frappe.whitelist()
	def move_line(self, from_idx, to_idx):
		"""
		Move a schedule line from one position to another.

		After reordering the in-memory list, each child row's ``idx`` is
		explicitly renumbered (1-based) so the new order is persisted on
		``save()``. Frappe orders child rows by ``idx`` on load, so simply
		reordering the Python list is not enough — the ``idx`` values must be
		reassigned to match the new positions.

		Args:
			from_idx: Current index of the line to move
			to_idx: Target index to insert the line at

		Returns:
			int: The target index the line was moved to
		"""
		from_idx = int(from_idx)
		to_idx = int(to_idx)

		if from_idx < 0 or from_idx >= len(self.lines):
			frappe.throw(_("Invalid source line index"))
		if to_idx < 0 or to_idx >= len(self.lines):
			frappe.throw(_("Invalid target line index"))

		if from_idx == to_idx:
			return to_idx

		line = self.lines.pop(from_idx)
		self.lines.insert(to_idx, line)

		# Renumber idx to persist the new order.
		for position, row in enumerate(self.lines):
			row.idx = position + 1

		self.save()

		return to_idx

	def _build_item_description(self, line, configured_fixture):
		"""Build a descriptive text for the SO item."""
		parts = []

		if configured_fixture.fixture_template:
			parts.append(configured_fixture.fixture_template)

		if configured_fixture.manufacturable_overall_length_mm:
			length_inches = configured_fixture.manufacturable_overall_length_mm / 25.4
			parts.append(f'{length_inches:.1f}"')

		if configured_fixture.finish:
			parts.append(configured_fixture.finish)

		if configured_fixture.lens_appearance:
			parts.append(configured_fixture.lens_appearance)

		return " | ".join(parts) if parts else None

	def _build_tape_neon_item_description(self, line, configured_tape_neon):
		"""Build a descriptive text for a single configured tape/neon item row.

		Mirrors :meth:`_build_item_description`. Location and fixture type are
		deliberately excluded — they live on ``ill_section_label`` and
		``additional_notes``.
		"""
		parts = []

		if configured_tape_neon.tape_neon_template:
			parts.append(configured_tape_neon.tape_neon_template)

		if configured_tape_neon.manufacturable_length_mm:
			length_inches = configured_tape_neon.manufacturable_length_mm / 25.4
			parts.append(f'{length_inches:.1f}"')

		if configured_tape_neon.cct:
			parts.append(configured_tape_neon.cct)

		if configured_tape_neon.output_level:
			parts.append(configured_tape_neon.output_level)

		if configured_tape_neon.finish:
			parts.append(configured_tape_neon.finish)

		return " | ".join(parts) if parts else None


def get_permission_query_conditions(user=None):
	"""
	Return SQL conditions to filter ilL-Project-Fixture-Schedule list for the current user.

	Generated from the same policy as :func:`has_permission` (see
	``illumenate_lighting.illumenate_lighting.portal.access``) so that a
	schedule the user may open by URL is also discoverable in lists, and
	vice versa.

	Args:
		user: The user to check permissions for. Defaults to current user.

	Returns:
		str: SQL WHERE clause conditions or empty string for full access
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import (
		schedule_query_conditions,
	)

	return schedule_query_conditions(user)


def has_permission(doc, ptype="read", user=None):
	"""
	Check if user has permission to access this specific schedule.

	Inherited schedules follow the linked project's decision (including its
	read-only rule for same-company non-dealer users). Non-inherited schedules
	apply schedule-level privacy; Dealers of the owning company always have
	access.

	Args:
		doc: The ilL-Project-Fixture-Schedule document
		ptype: Permission type (read, write, delete, etc.)
		user: The user to check permissions for. Defaults to current user.

	Returns:
		bool: True if user has permission, False otherwise
	"""
	from illumenate_lighting.illumenate_lighting.portal.access import (
		schedule_permission,
	)

	return schedule_permission(doc, ptype, user)


def can_convert_schedule_to_order(doc, user=None):
	"""Single policy for "may this user convert this schedule to a Sales Order?".

	Used by the portal page context, the portal endpoint and the conversion
	itself so the button, the API and the document all agree. Previously the
	rule only existed in the page template, which let any collaborator with
	write access call the endpoint directly.

	Args:
		doc: Schedule document or its name.
		user: Defaults to the session user.

	Returns:
		tuple[bool, str]: ``(allowed, reason)`` where ``reason`` is a
		user-facing message when the conversion is not allowed.
	"""
	if not user:
		user = frappe.session.user

	if isinstance(doc, str):
		if not frappe.db.exists("ilL-Project-Fixture-Schedule", doc):
			return False, _("Schedule not found")
		doc = frappe.get_doc("ilL-Project-Fixture-Schedule", doc)

	if user == "Guest":
		return False, _("Please log in to convert this schedule")

	if not has_permission(doc, "write", user):
		return False, _("You don't have permission to create a Sales Order for this schedule")

	if doc.get("is_locked"):
		return False, _("This schedule version is locked and cannot be converted")

	status = doc.get("status")
	is_privileged = _is_internal_user(user) or _is_dealer_user(user)

	if not is_privileged:
		# Product decision: only Dealers and internal users place orders.
		# EDIT collaborators and same-company users go through Request Quote.
		return False, _(
			"Only dealers can convert a schedule to an order. Please contact your dealer."
		)

	if status not in CONVERTIBLE_STATUSES:
		return False, _(
			"Schedule must be in READY or QUOTED status to convert to a Sales Order"
		)

	return True, ""


# ---------------------------------------------------------------------------
# Status state machine (portal-driven transitions)
# ---------------------------------------------------------------------------


def allowed_portal_transitions(current_status, user=None):
	"""Statuses ``user`` may move a schedule to from ``current_status``.

	- Anyone with write access: DRAFT <-> READY, QUOTED -> DRAFT/READY
	- Dealers/internal: READY -> QUOTED
	- Internal only: ISSUE -> DRAFT/READY (controlled retry)
	- ORDER_REQUESTED / ORDERED / CLOSED are system-driven and not settable.
	"""
	if not user:
		user = frappe.session.user
	is_internal = _is_internal_user(user)
	is_privileged = is_internal or _is_dealer_user(user)

	transitions = {
		"DRAFT": ["READY"],
		"READY": ["DRAFT", "QUOTED"] if is_privileged else ["DRAFT"],
		"QUOTED": ["DRAFT", "READY"],
		"ISSUE": ["DRAFT", "READY"] if is_internal else [],
	}
	return transitions.get(current_status, [])


def transition_schedule_status(schedule, new_status, user=None):
	"""Apply a portal-requested status change and return the outcome.

	Single state machine used by every UI/API path. Raises
	``frappe.ValidationError`` for anything not allowed. Leaving QUOTED
	snapshots the quoted schedule as a locked version and continues on a new
	version, so the returned dict may name a different schedule::

		{"new_status": "READY", "new_schedule_name": "...", "auto_versioned": True}
	"""
	if not user:
		user = frappe.session.user

	if new_status not in PORTAL_SETTABLE_STATUSES:
		frappe.throw(
			_("Invalid status. Must be one of: {0}").format(", ".join(PORTAL_SETTABLE_STATUSES))
		)

	if schedule.get("is_locked"):
		frappe.throw(
			_("This schedule version is locked. Create a new version to make changes.")
		)

	current_status = schedule.status
	if new_status == current_status:
		return {"new_status": new_status, "new_schedule_name": schedule.name, "auto_versioned": False}

	if new_status not in allowed_portal_transitions(current_status, user):
		frappe.throw(
			_("Cannot change status from {0} to {1}").format(current_status, new_status)
		)

	if current_status == "QUOTED":
		# Preserve the quoted state as a locked snapshot and continue on a
		# fresh version carrying the requested status.
		new_name = schedule.create_new_version(
			version_notes=_("Auto-versioned: leaving QUOTED to continue editing")
		)
		if new_status != "DRAFT":
			frappe.get_doc(schedule.doctype, new_name).db_set("status", new_status)
		return {"new_status": new_status, "new_schedule_name": new_name, "auto_versioned": True}

	# Save through the document so controller validation (e.g. all lines
	# configured before READY) runs instead of being bypassed with db_set.
	schedule.status = new_status
	schedule.save(ignore_permissions=True)
	if new_status == "QUOTED":
		from illumenate_lighting.illumenate_lighting.portal.notifications import (
			notify_schedule_status,
		)

		notify_schedule_status(schedule, "QUOTED")
	return {"new_status": new_status, "new_schedule_name": schedule.name, "auto_versioned": False}


# ---------------------------------------------------------------------------
# Sales Order lifecycle hooks (system-driven transitions)
# ---------------------------------------------------------------------------


def _linked_schedule(sales_order):
	name = sales_order.get("ill_fixture_schedule")
	if not name or not frappe.db.exists("ilL-Project-Fixture-Schedule", name):
		return None
	return frappe.get_doc("ilL-Project-Fixture-Schedule", name)


def on_sales_order_submit(doc, method=None):
	"""Submitting the Sales Order is how our team approves an order request."""
	schedule = _linked_schedule(doc)
	if schedule and schedule.status in ("ORDER_REQUESTED", "READY", "QUOTED", "ISSUE"):
		schedule.set_lifecycle_status("ORDERED", sales_order=doc.name)


def on_sales_order_cancel(doc, method=None):
	"""A cancelled order leaves the schedule in an explicit exception state."""
	schedule = _linked_schedule(doc)
	if schedule and schedule.status in ("ORDER_REQUESTED", "ORDERED"):
		schedule.set_lifecycle_status("ISSUE", sales_order="", note=ISSUE_STATUS_NOTE)


def on_sales_order_trash(doc, method=None):
	"""Deleting a draft order request without submitting it is an exception."""
	schedule = _linked_schedule(doc)
	if not schedule:
		return
	if doc.docstatus == 0 and schedule.status == "ORDER_REQUESTED":
		schedule.set_lifecycle_status("ISSUE", sales_order="", note=ISSUE_STATUS_NOTE)
	elif schedule.get("sales_order") == doc.name:
		schedule.db_set("sales_order", None)
