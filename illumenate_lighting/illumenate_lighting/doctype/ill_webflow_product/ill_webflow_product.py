# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	TAPE_NEON_CATEGORIES,
	is_tape_category,
)
from illumenate_lighting.illumenate_lighting.api.tape_selection import closest_tape, transmission_fraction
from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
	format_length_inches,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_spec_profile.ill_spec_profile import (
	compute_profile_dimensions,
)
from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	WEBFLOW_PRODUCT_LINK_TYPES,
	WEBFLOW_PRODUCT_LINKS,
)


def _resolve_attribute_code_field(doctype: str) -> str | None:
	"""Look up the column on an attribute doctype that stores its short code.

	Falls back to "code" for legacy/uncatalogued attribute doctypes; returns
	None if no plausible code column exists on the doctype.

	Most attribute doctypes use ``code``, but a few diverge
	(e.g. ``ilL-Attribute-Output Level`` -> ``sku_code``,
	``ilL-Attribute-Output Voltage`` -> ``voltage_code``).
	"""
	try:
		from illumenate_lighting.illumenate_lighting.api.webflow_attributes import (
			ATTRIBUTE_DOCTYPES,
		)
	except Exception:
		ATTRIBUTE_DOCTYPES = {}

	for cfg in ATTRIBUTE_DOCTYPES.values():
		if cfg.get("doctype") == doctype:
			return cfg.get("code_field") or None

	# Fallback: legacy default
	if frappe.db.has_column(doctype, "code"):
		return "code"
	return None


def _default_variant_spec(
	template_doctype: str, variant_doctype: str, template_name: str | None, spec_fieldname: str
) -> str | None:
	"""Return the spec linked by a template's default (or first active) variant.

	Used so a Driver/Controller product that points at a template instead of a
	single spec still has a representative spec to describe itself with.
	"""
	if not template_name:
		return None

	variants = frappe.get_all(
		variant_doctype,
		filters={
			"parent": template_name,
			"parenttype": template_doctype,
			"is_active": 1,
		},
		fields=[spec_fieldname, "is_default"],
		order_by="is_default desc, idx asc",
		limit=1,
	)
	return variants[0].get(spec_fieldname) if variants else None


class ilLWebflowProduct(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_attribute_link.ill_child_webflow_attribute_link import (
			ilLChildWebflowAttributeLink,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_certification_link.ill_child_webflow_certification_link import (
			ilLChildWebflowCertificationLink,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_compatibility.ill_child_webflow_compatibility import (
			ilLChildWebflowCompatibility,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_configurator_option.ill_child_webflow_configurator_option import (
			ilLChildWebflowConfiguratorOption,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_document.ill_child_webflow_document import (
			ilLChildWebflowDocument,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_gallery_image.ill_child_webflow_gallery_image import (
			ilLChildWebflowGalleryImage,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_kit_component.ill_child_webflow_kit_component import (
			ilLChildWebflowKitComponent,
		)
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_specification.ill_child_webflow_specification import (
			ilLChildWebflowSpecification,
		)

		accessory_spec: DF.Link | None
		attribute_links: DF.Table[ilLChildWebflowAttributeLink]
		auto_calculate_specs: DF.Check
		auto_populate_attributes: DF.Check
		auto_populate_configurator_options: DF.Check
		beam_angle: DF.Float
		certifications: DF.Table[ilLChildWebflowCertificationLink]
		compatible_products: DF.Table[ilLChildWebflowCompatibility]
		configurator_intro_text: DF.SmallText | None
		configurator_options: DF.Table[ilLChildWebflowConfiguratorOption]
		controller_spec: DF.Link | None
		controller_template: DF.Link | None
		documents: DF.Table[ilLChildWebflowDocument]
		driver_spec: DF.Link | None
		driver_template: DF.Link | None
		featured_image: DF.AttachImage | None
		features: DF.JSON | None
		fixture_template: DF.Link | None
		fixture_weight_per_foot_grams: DF.Float
		gallery_images: DF.Table[ilLChildWebflowGalleryImage]
		is_active: DF.Check
		is_configurable: DF.Check
		kit_components: DF.Table[ilLChildWebflowKitComponent]
		kit_template: DF.Link | None
		l70_life_hours: DF.Int
		last_synced_at: DF.Datetime | None
		length_increment_mm: DF.Int
		led_sheet_template: DF.Link | None
		lens_spec: DF.Link | None
		max_length_mm: DF.Int
		min_length_mm: DF.Int
		operating_temp_max_c: DF.Int
		operating_temp_min_c: DF.Int
		product_badge: DF.Literal["", "New", "On Sale", "Quick Ship"] | None
		product_category: DF.Link | None
		product_name: DF.Data
		product_slug: DF.Data
		portal_item: DF.Link | None
		product_type: DF.Literal["Fixture Template", "Driver", "Controller", "Extrusion Kit", "LED Tape", "COB Tape", "LED Neon", "Component", "Accessory", "LED Sheet"]
		profile_spec: DF.Link | None
		series_family_image: DF.AttachImage | None
		short_description: DF.SmallText | None
		sublabel: DF.Data | None
		specifications: DF.Table[ilLChildWebflowSpecification]
		sync_error_message: DF.SmallText | None
		sync_status: DF.Literal["Pending", "Synced", "Error", "Never Synced"]
		tape_neon_template: DF.Link | None
		tape_spec: DF.Link | None
		warranty_years: DF.Int
		webflow_collection_slug: DF.Data | None
		webflow_item_id: DF.Data | None
	# end: auto-generated types

	def populate_certification_badges(self):
		"""Populate the custom_badge_images JSON field based on active Target Brands."""
		# custom_badge_images (certification rows) and the dark/206 badge images (ilL-Attribute-Certification)
		# are site Custom Fields the app does not ship; skip where they are absent.
		if not frappe.get_meta(self.meta.get_field("certifications").options).has_field("custom_badge_images"):
			return
		cert_meta = frappe.get_meta("ilL-Attribute-Certification")
		badge_fields = [
			f for f in ("badge_image", "custom_badge_image_dark", "custom_206_badge_image_light", "custom_206_badge_image_dark")
			if cert_meta.has_field(f)
		]

		active_brands = [row.brand for row in self.get("target_brands", []) if row.enabled]
		if not active_brands:
			active_brands = ["lighting_206", "illumenate"]  # Fallback if none selected

		base_url = "https://app.illumenate.lighting"

		def make_url(path):
			if not path: return None
			if path.startswith("http"): return path
			return f"{base_url}{path}" if path.startswith("/") else f"{base_url}/{path}"

		for row in self.get("certifications", []):
			if not row.certification:
				continue

			cert_doc = frappe.db.get_value(
				"ilL-Attribute-Certification",
				row.certification,
				badge_fields,
				as_dict=True
			)
			if not cert_doc:
				continue

			badge_data = {}

			if "illumenate" in active_brands:
				badge_data["illumenate_badge_light"] = make_url(cert_doc.get("badge_image"))
				badge_data["illumenate_badge_dark"] = make_url(cert_doc.get("custom_badge_image_dark"))

			if "lighting_206" in active_brands:
				badge_data["206_badge_light"] = make_url(cert_doc.get("custom_206_badge_image_light"))
				badge_data["206_badge_dark"] = make_url(cert_doc.get("custom_206_badge_image_dark"))

			# Save as JSON array with a single object inside, matching your request
			row.custom_badge_images = frappe.as_json([badge_data])
	
	def validate(self):
		self._clear_template_links_for_other_types()

	def _clear_template_links_for_other_types(self):
		"""Drop template links left over from a previous product type.

		Only runs when the type changes, so existing products keep whatever they
		link today. Without this a stale link would keep claiming its template's
		Webflow Product backlink.
		"""
		if self.is_new() or not self.has_value_changed("product_type"):
			return
		for fieldname, product_types in WEBFLOW_PRODUCT_LINK_TYPES.items():
			if self.get(fieldname) and self.product_type not in product_types:
				self.set(fieldname, None)
	
	def onload(self):
		pass
		
	def before_save(self):
		"""Calculate specifications, attribute links, and configurator options before saving."""

		# Duplicate guard: clear inherited Webflow sync identity/state
		if getattr(self.flags, "in_copy", False) or self.is_new():
			self.webflow_item_id = None
			self.webflow_collection_slug = None
			self.last_synced_at = None
			self.sync_error_message = None
			self.sync_status = "Never Synced"
			if hasattr(self, "sync_targets"):
				self.set("sync_targets", [])

		# Populate attribute links from fixture template
		if self.get("auto_populate_attributes", True):
			self.populate_attribute_links()

		# Legacy: calculate specifications (deprecated - moving to attribute links)
		if self.auto_calculate_specs:
			self.calculate_specifications()

		# V2 Custom Specification Sync
		self.sync_custom_template_data()
		self.populate_compatible_power_supplies()
		self.populate_certification_badges()

		if self.is_configurable and self.fixture_template:
			if self.get("auto_populate_configurator_options", True):
				self.populate_configurator_options()

		if self.is_configurable and self.tape_neon_template:
			if self.get("auto_populate_configurator_options", True):
				self.populate_tape_neon_configurator_options()

		if self.is_configurable and self.led_sheet_template:
			if self.get("auto_populate_configurator_options", True):
				self.populate_led_sheet_configurator_options()

		if self.is_configurable and self.driver_template:
			if self.get("auto_populate_configurator_options", True):
				self.populate_driver_configurator_options()

		if self.is_configurable and self.controller_template:
			if self.get("auto_populate_configurator_options", True):
				self.populate_controller_configurator_options()

		# Mark as pending sync if substantive changes were made
		# Skip this check if we're being saved from the sync API (sync_status is being set to Synced)
		if not getattr(self, "_skip_sync_status_check", False):
			if (
				self.has_value_changed("attribute_links")
				or self.has_value_changed("configurator_options")
			):
				if self.sync_status == "Synced":
					self.sync_status = "Pending"

	def on_update(self):
		"""Update webflow_product backlink on linked templates after save and sync compatibilities."""
		# 1. Prevent infinite loops globally for this compatibility sync transaction
		if not self.flags.syncing_compatibility:
			# 2. Run deletions first, then additions
			self.handle_deletions()
			self.sync_compatible_products()

		for template_doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items():
			self._update_template_backlink(template_doctype, fieldname)
		self._top_up_template()

	def _top_up_template(self):
		"""Move product data onto a template when this listing is first linked to it."""
		from illumenate_lighting.illumenate_lighting.web_listing_source import top_up_template

		row = top_up_template(self)
		if row and row["action"] == "failed":
			# Never block a save; parity_report shows a template that is missing data.
			frappe.log_error(title=f"Product data top-up failed for {self.name}", message=row["notes"][-1])

	def handle_deletions(self):
		"""Handle removal of bi-directional compatibility links upon row deletion."""
		old_doc = self.get_doc_before_save()
		if not old_doc:
			return # This is a brand new document, so nothing could have been deleted

		child_table = "compatible_products"
		related_field = "related_product"
		rel_type_field = "relationship_type"

		# Create sets of (product, relationship) tuples to easily compare before and after
		old_items = {(row.get(related_field), row.get(rel_type_field)) for row in old_doc.get(child_table) if row.get(related_field)}
		new_items = {(row.get(related_field), row.get(rel_type_field)) for row in self.get(child_table) if row.get(related_field)}
		
		# Find what exists in the old document but is missing from the new one
		deleted_items = old_items - new_items

		for target_product, relationship in deleted_items:
			try:
				target_doc = frappe.get_doc("ilL-Webflow-Product", target_product)
			except frappe.DoesNotExistError:
				continue
			
			# Rebuild the child table on the target document, EXCLUDING the deleted link
			original_row_count = len(target_doc.get(child_table))
			filtered_rows = [
				row for row in target_doc.get(child_table) 
				if not (row.get(related_field) == self.name and row.get(rel_type_field) == relationship)
			]
			
			# If a row was successfully filtered out, update the table and save
			if len(filtered_rows) < original_row_count:
				target_doc.set(child_table, filtered_rows)
				
				# Flag to prevent infinite loops
				target_doc.flags.syncing_compatibility = True
				target_doc.save(ignore_permissions=True)

	def populate_compatible_power_supplies(self):
		"""Fetch eligible drivers from the linked template and populate the child table."""
		# custom_compatible_power_supplies is a site Custom Field the app does not ship; skip where it is absent.
		if not self.meta.has_field("custom_compatible_power_supplies"):
			return

		# 1. Figure out which template is linked to this product
		template_name = (
			self.tape_neon_template or 
			self.fixture_template or 
			self.led_sheet_template or 
			self.kit_template
		)

		if not template_name:
			self.custom_compatible_power_supplies = []
			return

		# 2. Query ilL-Rel-Driver-Eligibility for all drivers linked to this template
		eligible_drivers = frappe.get_all(
			"ilL-Rel-Driver-Eligibility",
			filters={"fixture_template": template_name, "is_active": 1},
			pluck="driver_spec"
		)

		# Clear the table so we can rebuild it cleanly
		self.custom_compatible_power_supplies = []

		if not eligible_drivers:
			return

		# 3. Fetch each Driver Spec and map its fields into the child table
		for driver_name in eligible_drivers:
			try:
				driver_doc = frappe.get_doc("ilL-Spec-Driver", driver_name)
			except frappe.DoesNotExistError:
				continue

			# Format Input Protocols (Comma-separated string of Labels)
			protocols = []
			for row in driver_doc.get("input_protocols", []):
				if row.protocol:
					# Get the pretty label ("0-10V") rather than the database code
					label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", row.protocol, "label")
					protocols.append(label or row.protocol)
			protocol_str = ", ".join(protocols)

			# Format Voltage / Frequency (e.g., "120 - 277VAC")
			v_min = driver_doc.input_voltage_min or ""
			v_max = driver_doc.input_voltage_max or ""
			v_type = driver_doc.input_voltage_type or ""
			
			if v_min and v_max:
				voltage_freq = f"{v_min} - {v_max}{v_type}"
			else:
				voltage_freq = f"{v_min or v_max}{v_type}"

			# Append the mapped row to your custom child table
			self.append("custom_compatible_power_supplies", {
				"part_number": driver_doc.name,
				"input_protocol": protocol_str,
				"voltagefrequency": voltage_freq,
				"output_voltage": str(driver_doc.voltage_output) if driver_doc.voltage_output else "",
				"max_wattage": f"{driver_doc.max_wattage:g}W" if driver_doc.max_wattage else "",
				"location_rating": driver_doc.location_rating or "",
				"output_count": driver_doc.outputs_count  # <-- ADDED NEW FIELD HERE
			})

	def sync_compatible_products(self):
		"""Handle additions for bi-directional compatibility links."""
		child_table = "compatible_products" 
		related_field = "related_product"
		rel_type_field = "relationship_type"

		for row in self.get(child_table):
			if not row.get(related_field):
				continue

			target_product = row.get(related_field)
			relationship = row.get(rel_type_field)

			try:
				target_doc = frappe.get_doc("ilL-Webflow-Product", target_product)
			except frappe.DoesNotExistError:
				continue

			# Check if the reciprocal link already exists in the target doc
			exists = any(
				r.get(related_field) == self.name and 
				r.get(rel_type_field) == relationship 
				for r in target_doc.get(child_table)
			)

			# If it doesn't exist, append it and save the target doc
			if not exists:
				target_doc.append(child_table, {
					related_field: self.name,
					rel_type_field: relationship
				})
				
				# Flag to prevent infinite loops
				target_doc.flags.syncing_compatibility = True
				target_doc.save(ignore_permissions=True)

	def on_trash(self):
		"""Clear webflow_product backlink on linked templates before deletion."""
		for template_doctype, fieldname in WEBFLOW_PRODUCT_LINKS.items():
			template = self.get(fieldname)
			if template and frappe.db.get_value(template_doctype, template, "webflow_product") == self.name:
				frappe.db.set_value(
					template_doctype,
					template,
					"webflow_product",
					None,
					update_modified=False,
				)

	def _update_template_backlink(self, template_doctype: str, fieldname: str):
		"""Point the template's webflow_product backlink at this product.

		Also clears the backlink on the previously linked template when the
		link field was changed.
		"""
		old_doc = self.get_doc_before_save()
		old_template = old_doc.get(fieldname) if old_doc else None
		new_template = self.get(fieldname)

		if old_template and old_template != new_template:
			frappe.db.set_value(
				template_doctype,
				old_template,
				"webflow_product",
				None,
				update_modified=False,
			)

		if new_template:
			frappe.db.set_value(
				template_doctype,
				new_template,
				"webflow_product",
				self.name,
				update_modified=False,
			)

	def populate_attribute_links(self):
		"""Populate attribute links from the linked source spec for each product type."""
		attribute_links = []
		
		# Handle Fixture Template
		if self.product_type == "Fixture Template" and self.fixture_template:
			self._populate_fixture_template_attributes(attribute_links)
		# Handle Extrusion Kit
		elif self.product_type == "Extrusion Kit":
			self._populate_extrusion_kit_attributes(attribute_links)
		# Handle LED Tape / COB Tape / LED Neon via tape_neon_template
		elif self.product_type in TAPE_NEON_CATEGORIES and self.tape_neon_template:
			self._populate_tape_neon_template_attributes(attribute_links)
		elif self.product_type == "LED Sheet" and self.led_sheet_template:
			self._populate_led_sheet_template_attributes(attribute_links)
		# Handle legacy LED Tape via tape_spec (deprecated fallback)
		elif self.product_type == "LED Tape" and self.tape_spec:
			self._populate_led_tape_attributes(attribute_links)
		# Handle Driver
		elif self.product_type == "Driver" and self._resolve_driver_spec():
			self._populate_driver_attributes(attribute_links)
		# Handle Controller
		elif self.product_type == "Controller" and self._resolve_controller_spec():
			self._populate_controller_attributes(attribute_links)
		# Handle Accessory
		elif self.product_type == "Accessory" and self.accessory_spec:
			self._populate_accessory_attributes(attribute_links)
		# Handle Component (lens-based)
		elif self.product_type == "Component" and self.lens_spec:
			self._populate_component_attributes(attribute_links)
		else:
			return
		
		# Add certifications from the certifications child table as attribute links
		self._populate_certification_attributes(attribute_links)
		
		# Clear existing attribute links and add new ones
		self.attribute_links = []
		for link in attribute_links:
			self.append("attribute_links", link)

	def _populate_certification_attributes(self, attribute_links):
		"""Add certifications from the certifications child table as attribute links."""
		display_order = max((a.get("display_order", 0) for a in attribute_links), default=0)
		for cert in getattr(self, 'certifications', []):
			cert_name = cert.certification
			if not cert_name:
				continue
			existing = [a for a in attribute_links
			            if a["attribute_doctype"] == "ilL-Attribute-Certification"
			            and a["attribute_name"] == cert_name]
			if not existing:
				display_order += 1
				cert_data = frappe.db.get_value(
					"ilL-Attribute-Certification", cert_name,
					["certification_name"], as_dict=True
				)
				webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Certification", cert_name)
				attribute_links.append({
					"attribute_type": "Certification",
					"attribute_doctype": "ilL-Attribute-Certification",
					"attribute_name": cert_name,
					"display_label": cert_data.get("certification_name") if cert_data else cert_name,
					"webflow_item_id": webflow_id,
					"display_order": display_order,
				})
	
	def _populate_fixture_template_attributes(self, attribute_links):
		"""Extract attributes from fixture template.
		
		Note: Caller must ensure self.fixture_template is set before calling this method.
		"""
		if not self.fixture_template:
			return
			
		template = frappe.get_doc("ilL-Fixture-Template", self.fixture_template)
		display_order = 0
		
		# Get attributes from allowed_options (Finish, Lens Appearance, Mounting Method, etc.)
		for opt in template.allowed_options or []:
			if hasattr(opt, 'is_active') and not opt.is_active:
				continue
			
			option_type = getattr(opt, 'option_type', None)
			if not option_type:
				continue
			
			# Map option types to their field and doctype
			option_mapping = {
				"Finish": ("finish", "ilL-Attribute-Finish"),
				"Lens Appearance": ("lens_appearance", "ilL-Attribute-Lens Appearance"),
				"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
				"Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style"),
				"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
				"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
			}
			
			if option_type in option_mapping:
				field_name, doctype = option_mapping[option_type]
				attr_value = getattr(opt, field_name, None)
				if attr_value:
					# Check if this attribute is already in the list
					existing = [a for a in attribute_links 
					            if a["attribute_doctype"] == doctype and a["attribute_name"] == attr_value]
					if not existing:
						display_order += 1
						webflow_id = self._get_attribute_webflow_id(doctype, attr_value)
						attribute_links.append({
							"attribute_type": option_type,
							"attribute_doctype": doctype,
							"attribute_name": attr_value,
							"display_label": attr_value,
							"webflow_item_id": webflow_id,
							"display_order": display_order
						})
					
					# For Power Feed Type, also extract the linked Feed Direction
					if option_type == "Power Feed Type":
						feed_direction = frappe.db.get_value(
							"ilL-Attribute-Power Feed Type",
							attr_value,
							"type"
						)
						if feed_direction:
							# Check if this feed direction is already in the list
							existing_fd = [a for a in attribute_links 
							               if a["attribute_doctype"] == "ilL-Attribute-Feed-Direction" and a["attribute_name"] == feed_direction]
							if not existing_fd:
								display_order += 1
								fd_webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Feed-Direction", feed_direction)
								attribute_links.append({
									"attribute_type": "Feed Direction",
									"attribute_doctype": "ilL-Attribute-Feed-Direction",
									"attribute_name": feed_direction,
									"display_label": feed_direction,
									"webflow_item_id": fd_webflow_id,
									"display_order": display_order
								})
		
		# Get attributes from allowed_tape_offerings (CCT, Output Level, LED Package, CRI, etc.)
		for tape_row in template.allowed_tape_offerings or []:
			if not hasattr(tape_row, 'tape_offering') or not tape_row.tape_offering:
				continue
			
			# Get the tape offering details
			tape_offering = frappe.db.get_value(
				"ilL-Rel-Tape Offering",
				tape_row.tape_offering,
				["cct", "output_level", "led_package", "cri"],
				as_dict=True
			)
			if not tape_offering:
				continue
			
			# CCT
			if tape_offering.get("cct"):
				cct_name = tape_offering.cct
				existing = [a for a in attribute_links 
				            if a["attribute_doctype"] == "ilL-Attribute-CCT" and a["attribute_name"] == cct_name]
				if not existing:
					display_order += 1
					cct_data = frappe.db.get_value("ilL-Attribute-CCT", cct_name, ["label"], as_dict=True)
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-CCT", cct_name)
					attribute_links.append({
						"attribute_type": "CCT",
						"attribute_doctype": "ilL-Attribute-CCT",
						"attribute_name": cct_name,
						"display_label": cct_data.get("label") if cct_data else cct_name,
						"webflow_item_id": webflow_id,
						"display_order": display_order
					})
			
			# Output Level
			if tape_offering.get("output_level"):
				level_name = tape_offering.output_level
				existing = [a for a in attribute_links 
				            if a["attribute_doctype"] == "ilL-Attribute-Output Level" and a["attribute_name"] == level_name]
				if not existing:
					display_order += 1
					level_data = frappe.db.get_value("ilL-Attribute-Output Level", level_name, ["value"], as_dict=True)
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Output Level", level_name)
					attribute_links.append({
						"attribute_type": "Output Level",
						"attribute_doctype": "ilL-Attribute-Output Level",
						"attribute_name": level_name,
						"display_label": f"{level_data.get('value', '')} lm/ft" if level_data else level_name,
						"webflow_item_id": webflow_id,
						"display_order": display_order
					})
			
			# LED Package
			if tape_offering.get("led_package"):
				pkg_name = tape_offering.led_package
				existing = [a for a in attribute_links 
				            if a["attribute_doctype"] == "ilL-Attribute-LED Package" and a["attribute_name"] == pkg_name]
				if not existing:
					display_order += 1
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-LED Package", pkg_name)
					attribute_links.append({
						"attribute_type": "LED Package",
						"attribute_doctype": "ilL-Attribute-LED Package",
						"attribute_name": pkg_name,
						"display_label": pkg_name,
						"webflow_item_id": webflow_id,
						"display_order": display_order
					})
			
			# CRI
			if tape_offering.get("cri"):
				cri_name = tape_offering.cri
				existing = [a for a in attribute_links 
				            if a["attribute_doctype"] == "ilL-Attribute-CRI" and a["attribute_name"] == cri_name]
				if not existing:
					display_order += 1
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-CRI", cri_name)
					attribute_links.append({
						"attribute_type": "CRI",
						"attribute_doctype": "ilL-Attribute-CRI",
						"attribute_name": cri_name,
						"display_label": cri_name,
						"webflow_item_id": webflow_id,
						"display_order": display_order
					})
		
		# Get dimming protocols from eligible drivers (ilL-Rel-Driver-Eligibility)
		eligible_drivers = frappe.get_all(
			"ilL-Rel-Driver-Eligibility",
			filters={"fixture_template": self.fixture_template, "is_active": 1},
			fields=["driver_spec"],
		)
		for elig in eligible_drivers:
			driver_doc = frappe.get_doc("ilL-Spec-Driver", elig.driver_spec)
			for ip in getattr(driver_doc, "input_protocols", []):
				protocol_name = ip.protocol
				if not protocol_name:
					continue
				if not any(
					a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
					and a["attribute_name"] == protocol_name
					for a in attribute_links
				):
					display_order += 1
					proto_data = frappe.db.get_value(
						"ilL-Attribute-Dimming Protocol", protocol_name, ["label"], as_dict=True
					)
					webflow_id = self._get_attribute_webflow_id(
						"ilL-Attribute-Dimming Protocol", protocol_name
					)
					attribute_links.append({
						"attribute_type": "Dimming Protocol",
						"attribute_doctype": "ilL-Attribute-Dimming Protocol",
						"attribute_name": protocol_name,
						"display_label": proto_data.get("label") if proto_data else protocol_name,
						"webflow_item_id": webflow_id,
						"display_order": display_order,
					})

	def _resolve_kit_specs(self) -> tuple[str | None, str | None]:
		"""Profile and lens specs to describe an extrusion kit with.

		Explicit profile_spec/lens_spec links win; otherwise the linked kit
		template's default profile and lens fill in.
		"""
		profile_spec, lens_spec = self.profile_spec, self.lens_spec
		if self.kit_template and not (profile_spec and lens_spec):
			defaults = frappe.db.get_value(
				"ilL-Extrusion-Kit-Template",
				self.kit_template,
				["default_profile_spec", "default_lens_spec"],
				as_dict=True,
			) or {}
			profile_spec = profile_spec or defaults.get("default_profile_spec")
			lens_spec = lens_spec or defaults.get("default_lens_spec")
		return profile_spec, lens_spec

	def _populate_extrusion_kit_attributes(self, attribute_links):
		"""Extract attributes from extrusion kit profile spec, lens spec, and kit components."""
		display_order = 0
		profile_spec, lens_spec = self._resolve_kit_specs()

		# Extract attributes from profile_spec if present
		if profile_spec:
			try:
				profile = frappe.get_doc("ilL-Spec-Profile", profile_spec)
			except frappe.DoesNotExistError:
				frappe.log_error(
					message=f"Profile spec {profile_spec} not found for extrusion kit {self.name}",
					title="Extrusion Kit Profile Spec Not Found"
				)
				profile = None
			
			if profile:
				# Series from profile
				if profile.series:
					display_order += 1
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Series", profile.series)
					attribute_links.append({
						"attribute_type": "Series",
						"attribute_doctype": "ilL-Attribute-Series",
						"attribute_name": profile.series,
						"display_label": profile.series,
						"webflow_item_id": webflow_id,
						"display_order": display_order
					})
				
				# Environment Ratings from profile
				for env in getattr(profile, 'supported_environment_ratings', []):
					env_rating = getattr(env, 'environment_rating', None)
					if env_rating:
						existing = [a for a in attribute_links 
						            if a["attribute_doctype"] == "ilL-Attribute-Environment Rating" 
						            and a["attribute_name"] == env_rating]
						if not existing:
							display_order += 1
							webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Environment Rating", env_rating)
							attribute_links.append({
								"attribute_type": "Environment Rating",
								"attribute_doctype": "ilL-Attribute-Environment Rating",
								"attribute_name": env_rating,
								"display_label": env_rating,
								"webflow_item_id": webflow_id,
								"display_order": display_order
							})
				
				# Joiner System from profile
				if profile.joiner_system:
					display_order += 1
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Joiner System", profile.joiner_system)
					attribute_links.append({
						"attribute_type": "Joiner System",
						"attribute_doctype": "ilL-Attribute-Joiner System",
						"attribute_name": profile.joiner_system,
						"display_label": profile.joiner_system,
						"webflow_item_id": webflow_id,
						"display_order": display_order
					})
		
		# Extract attributes from lens_spec if present
		if lens_spec:
			try:
				lens = frappe.get_doc("ilL-Spec-Lens", lens_spec)
			except frappe.DoesNotExistError:
				frappe.log_error(
					message=f"Lens spec {lens_spec} not found for extrusion kit {self.name}",
					title="Extrusion Kit Lens Spec Not Found"
				)
				lens = None
			
			if lens:
				# Lens Appearance
				if lens.lens_appearance:
					existing = [a for a in attribute_links 
					            if a["attribute_doctype"] == "ilL-Attribute-Lens Appearance" 
					            and a["attribute_name"] == lens.lens_appearance]
					if not existing:
						display_order += 1
						webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Lens Appearance", lens.lens_appearance)
						attribute_links.append({
							"attribute_type": "Lens Appearance",
							"attribute_doctype": "ilL-Attribute-Lens Appearance",
							"attribute_name": lens.lens_appearance,
							"display_label": lens.lens_appearance,
							"webflow_item_id": webflow_id,
							"display_order": display_order
						})
				
				# Series from lens (if not already added from profile)
				if lens.series:
					existing = [a for a in attribute_links 
					            if a["attribute_doctype"] == "ilL-Attribute-Series" 
					            and a["attribute_name"] == lens.series]
					if not existing:
						display_order += 1
						webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Series", lens.series)
						attribute_links.append({
							"attribute_type": "Series",
							"attribute_doctype": "ilL-Attribute-Series",
							"attribute_name": lens.series,
							"display_label": lens.series,
							"webflow_item_id": webflow_id,
							"display_order": display_order
						})
		
		# Extract attributes from kit_components (endcaps, mounting accessories, etc.)
		for component in getattr(self, 'kit_components', []):
			if not component.component_spec_doctype or not component.component_spec_name:
				continue
			
			# Only process accessories (endcaps, mounting, etc.)
			if component.component_spec_doctype == "ilL-Spec-Accessory":
				try:
					accessory = frappe.get_doc(component.component_spec_doctype, component.component_spec_name)
					
					# Endcap Style
					if accessory.endcap_style:
						existing = [a for a in attribute_links 
						            if a["attribute_doctype"] == "ilL-Attribute-Endcap Style" 
						            and a["attribute_name"] == accessory.endcap_style]
						if not existing:
							display_order += 1
							webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Endcap Style", accessory.endcap_style)
							attribute_links.append({
								"attribute_type": "Endcap Style",
								"attribute_doctype": "ilL-Attribute-Endcap Style",
								"attribute_name": accessory.endcap_style,
								"display_label": accessory.endcap_style,
								"webflow_item_id": webflow_id,
								"display_order": display_order
							})
					
					# Mounting Method
					if accessory.mounting_method:
						existing = [a for a in attribute_links 
						            if a["attribute_doctype"] == "ilL-Attribute-Mounting Method" 
						            and a["attribute_name"] == accessory.mounting_method]
						if not existing:
							display_order += 1
							webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Mounting Method", accessory.mounting_method)
							attribute_links.append({
								"attribute_type": "Mounting Method",
								"attribute_doctype": "ilL-Attribute-Mounting Method",
								"attribute_name": accessory.mounting_method,
								"display_label": accessory.mounting_method,
								"webflow_item_id": webflow_id,
								"display_order": display_order
							})
					
					# Environment Rating from accessory
					if accessory.environment_rating:
						existing = [a for a in attribute_links 
						            if a["attribute_doctype"] == "ilL-Attribute-Environment Rating" 
						            and a["attribute_name"] == accessory.environment_rating]
						if not existing:
							display_order += 1
							webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Environment Rating", accessory.environment_rating)
							attribute_links.append({
								"attribute_type": "Environment Rating",
								"attribute_doctype": "ilL-Attribute-Environment Rating",
								"attribute_name": accessory.environment_rating,
								"display_label": accessory.environment_rating,
								"webflow_item_id": webflow_id,
								"display_order": display_order
							})
				except (frappe.DoesNotExistError, AttributeError) as e:
					# Skip if component spec doesn't exist or has missing attributes
					frappe.log_error(
						message=f"Error processing kit component {component.component_spec_name}: {str(e)}",
						title="Extrusion Kit Attribute Population Error"
					)
					continue

	def _populate_led_sheet_template_attributes(self, attribute_links):
		if not self.led_sheet_template:
			return
		try:
			template = frappe.get_doc("ilL-LED-Sheet-Template", self.led_sheet_template)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"LED Sheet template {self.led_sheet_template} not found for product {self.name}",
				title="LED Sheet Template Not Found",
			)
			return
		option_mapping = {
			"CCT": "ilL-Attribute-CCT",
			"Output Level": "ilL-Attribute-Output Level",
			"Environment Rating": "ilL-Attribute-Environment Rating",
			"Mounting": "ilL-Attribute-Mounting Method",
			"Finish": "ilL-Attribute-Finish",
		}
		display_order = len(attribute_links)
		for opt in template.allowed_options or []:
			if not getattr(opt, "is_active", 1):
				continue
			doctype = option_mapping.get(getattr(opt, "option_type", None))
			attr_value = getattr(opt, "attribute_link", None)
			if not doctype or not attr_value:
				continue
			if any(a["attribute_doctype"] == doctype and a["attribute_name"] == attr_value for a in attribute_links):
				continue
			display_order += 1
			attribute_links.append({
				"attribute_type": opt.option_type,
				"attribute_doctype": doctype,
				"attribute_name": attr_value,
				"display_label": attr_value,
				"webflow_item_id": self._get_attribute_webflow_id(doctype, attr_value),
				"display_order": display_order,
			})

	def _populate_tape_neon_template_attributes(self, attribute_links):
		"""Extract attributes from tape/neon template's allowed_options and allowed_tape_specs.

		Mirrors _populate_fixture_template_attributes() but for ilL-Tape-Neon-Template.
		Extracts from allowed_options (CCT, Output Level, Environment Rating, IP Rating,
		Feed Direction, Power Feed Type, PCB Mounting, PCB Finish, Mounting Method, Finish,
		Endcap Style) and from allowed_tape_specs → ilL-Spec-LED Tape (LED Package,
		Input Voltage, CRI, Dimming Protocols).
		"""
		if not self.tape_neon_template:
			return

		try:
			template = frappe.get_doc("ilL-Tape-Neon-Template", self.tape_neon_template)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Tape/Neon template {self.tape_neon_template} not found for product {self.name}",
				title="Tape Neon Template Not Found",
			)
			return

		display_order = 0

		# Map option types to (child-table field, attribute doctype)
		option_mapping = {
			"CCT": ("cct", "ilL-Attribute-CCT"),
			"Output Level": ("output_level", "ilL-Attribute-Output Level"),
			"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
			"IP Rating": ("ip_rating", "ilL-Attribute-IP Rating"),
			"Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
			"PCB Mounting": ("pcb_mounting", "ilL-Attribute-PCB Mounting"),
			"PCB Finish": ("pcb_finish", "ilL-Attribute-PCB Finish"),
			"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
			"Finish": ("finish", "ilL-Attribute-Finish"),
			"Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style"),
		}

		# Extract attributes from allowed_options
		for opt in template.allowed_options or []:
			if hasattr(opt, "is_active") and not opt.is_active:
				continue

			option_type = getattr(opt, "option_type", None)
			if not option_type or option_type not in option_mapping:
				continue

			field_name, doctype = option_mapping[option_type]
			attr_value = getattr(opt, field_name, None)
			if not attr_value:
				continue

			# Skip duplicates
			if any(
				a["attribute_doctype"] == doctype and a["attribute_name"] == attr_value
				for a in attribute_links
			):
				continue

			display_order += 1
			# Get display label from the attribute record
			display_label = attr_value
			if option_type == "CCT":
				cct_data = frappe.db.get_value("ilL-Attribute-CCT", attr_value, ["label"], as_dict=True)
				if cct_data and cct_data.get("label"):
					display_label = cct_data["label"]
			elif option_type == "Output Level":
				level_data = frappe.db.get_value("ilL-Attribute-Output Level", attr_value, ["value"], as_dict=True)
				if level_data and level_data.get("value"):
					display_label = f"{level_data['value']} lm/ft"

			webflow_id = self._get_attribute_webflow_id(doctype, attr_value)
			attribute_links.append({
				"attribute_type": option_type,
				"attribute_doctype": doctype,
				"attribute_name": attr_value,
				"display_label": display_label,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Extract attributes from allowed_tape_specs → ilL-Spec-LED Tape
		for spec_row in template.allowed_tape_specs or []:
			tape_spec_name = getattr(spec_row, "tape_spec", None)
			if not tape_spec_name:
				continue

			try:
				tape = frappe.get_doc("ilL-Spec-LED Tape", tape_spec_name)
			except frappe.DoesNotExistError:
				continue

			# LED Package
			if tape.led_package:
				if not any(
					a["attribute_doctype"] == "ilL-Attribute-LED Package"
					and a["attribute_name"] == tape.led_package
					for a in attribute_links
				):
					display_order += 1
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-LED Package", tape.led_package)
					attribute_links.append({
						"attribute_type": "LED Package",
						"attribute_doctype": "ilL-Attribute-LED Package",
						"attribute_name": tape.led_package,
						"display_label": tape.led_package,
						"webflow_item_id": webflow_id,
						"display_order": display_order,
					})

			# Input Voltage (mapped as Output Voltage attribute)
			if tape.input_voltage:
				if not any(
					a["attribute_doctype"] == "ilL-Attribute-Output Voltage"
					and a["attribute_name"] == tape.input_voltage
					for a in attribute_links
				):
					display_order += 1
					voltage_label = frappe.db.get_value(
						"ilL-Attribute-Output Voltage", tape.input_voltage, "dc_voltage"
					)
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Output Voltage", tape.input_voltage)
					attribute_links.append({
						"attribute_type": "Output Voltage",
						"attribute_doctype": "ilL-Attribute-Output Voltage",
						"attribute_name": tape.input_voltage,
						"display_label": f"{voltage_label} VDC" if voltage_label else tape.input_voltage,
						"webflow_item_id": webflow_id,
						"display_order": display_order,
					})

			# CRI
			if getattr(tape, "cri", None):
				if not any(
					a["attribute_doctype"] == "ilL-Attribute-CRI"
					and a["attribute_name"] == tape.cri
					for a in attribute_links
				):
					display_order += 1
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-CRI", tape.cri)
					attribute_links.append({
						"attribute_type": "CRI",
						"attribute_doctype": "ilL-Attribute-CRI",
						"attribute_name": tape.cri,
						"display_label": tape.cri,
						"webflow_item_id": webflow_id,
						"display_order": display_order,
					})

			# Dimming protocols
			if getattr(tape, "input_protocol", None):
				if not any(
					a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
					and a["attribute_name"] == tape.input_protocol
					for a in attribute_links
				):
					display_order += 1
					proto_data = frappe.db.get_value(
						"ilL-Attribute-Dimming Protocol", tape.input_protocol, ["label"], as_dict=True
					)
					webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", tape.input_protocol)
					attribute_links.append({
						"attribute_type": "Dimming Protocol",
						"attribute_doctype": "ilL-Attribute-Dimming Protocol",
						"attribute_name": tape.input_protocol,
						"display_label": proto_data.get("label") if proto_data else tape.input_protocol,
						"webflow_item_id": webflow_id,
						"display_order": display_order,
					})

			for row in getattr(tape, "supported_dimming_protocols", []):
				protocol_name = getattr(row, "protocol", None)
				if not protocol_name:
					continue
				if any(
					a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
					and a["attribute_name"] == protocol_name
					for a in attribute_links
				):
					continue
				display_order += 1
				proto_data = frappe.db.get_value(
					"ilL-Attribute-Dimming Protocol", protocol_name, ["label"], as_dict=True
				)
				webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", protocol_name)
				attribute_links.append({
					"attribute_type": "Dimming Protocol",
					"attribute_doctype": "ilL-Attribute-Dimming Protocol",
					"attribute_name": protocol_name,
					"display_label": proto_data.get("label") if proto_data else protocol_name,
					"webflow_item_id": webflow_id,
					"display_order": display_order,
				})

	def _populate_led_tape_attributes(self, attribute_links):
		"""Extract attributes from LED tape spec.

		Note: Caller must ensure self.tape_spec is set before calling this method.
		"""
		if not self.tape_spec:
			return

		try:
			tape = frappe.get_doc("ilL-Spec-LED Tape", self.tape_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"LED tape spec {self.tape_spec} not found for product {self.name}",
				title="LED Tape Spec Not Found",
			)
			return

		display_order = 0

		# LED Package
		if tape.led_package:
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-LED Package", tape.led_package)
			attribute_links.append({
				"attribute_type": "LED Package",
				"attribute_doctype": "ilL-Attribute-LED Package",
				"attribute_name": tape.led_package,
				"display_label": tape.led_package,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Input Voltage (mapped as Output Voltage attribute)
		if tape.input_voltage:
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Output Voltage", tape.input_voltage)
			voltage_label = frappe.db.get_value(
				"ilL-Attribute-Output Voltage", tape.input_voltage, "dc_voltage"
			)
			attribute_links.append({
				"attribute_type": "Output Voltage",
				"attribute_doctype": "ilL-Attribute-Output Voltage",
				"attribute_name": tape.input_voltage,
				"display_label": f"{voltage_label} VDC" if voltage_label else tape.input_voltage,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Input Protocol (primary dimming protocol)
		if getattr(tape, "input_protocol", None):
			display_order += 1
			proto_data = frappe.db.get_value(
				"ilL-Attribute-Dimming Protocol", tape.input_protocol, ["label"], as_dict=True
			)
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", tape.input_protocol)
			attribute_links.append({
				"attribute_type": "Dimming Protocol",
				"attribute_doctype": "ilL-Attribute-Dimming Protocol",
				"attribute_name": tape.input_protocol,
				"display_label": proto_data.get("label") if proto_data else tape.input_protocol,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Supported dimming protocols from child table
		for row in getattr(tape, "supported_dimming_protocols", []):
			protocol_name = getattr(row, "protocol", None)
			if not protocol_name:
				continue
			# Skip if already added (e.g. same as input_protocol)
			if any(
				a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
				and a["attribute_name"] == protocol_name
				for a in attribute_links
			):
				continue
			display_order += 1
			proto_data = frappe.db.get_value(
				"ilL-Attribute-Dimming Protocol", protocol_name, ["label"], as_dict=True
			)
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", protocol_name)
			attribute_links.append({
				"attribute_type": "Dimming Protocol",
				"attribute_doctype": "ilL-Attribute-Dimming Protocol",
				"attribute_name": protocol_name,
				"display_label": proto_data.get("label") if proto_data else protocol_name,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

	def _resolve_driver_spec(self) -> str | None:
		"""Driver spec to describe this product with.

		Prefers the explicit ``driver_spec`` link; otherwise falls back to the
		default (or first active) variant of the linked Driver template so that
		template-only products still publish attributes.
		"""
		if self.driver_spec:
			return self.driver_spec
		return _default_variant_spec(
			"ilL-Driver-Template",
			"ilL-Child-Driver-Template-Variant",
			self.driver_template,
			"driver_spec",
		)

	def _resolve_controller_spec(self) -> str | None:
		"""Controller spec to describe this product with (see _resolve_driver_spec)."""
		if self.controller_spec:
			return self.controller_spec
		return _default_variant_spec(
			"ilL-Controller-Template",
			"ilL-Child-Controller-Template-Variant",
			self.controller_template,
			"controller_spec",
		)

	def _populate_driver_attributes(self, attribute_links):
		"""Extract attributes from driver spec.

		Note: Caller must ensure a driver spec is resolvable before calling this method.
		"""
		driver_spec = self._resolve_driver_spec()
		if not driver_spec:
			return

		try:
			driver = frappe.get_doc("ilL-Spec-Driver", driver_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Driver spec {driver_spec} not found for product {self.name}",
				title="Driver Spec Not Found",
			)
			return

		display_order = 0

		# Output Voltage
		if driver.voltage_output:
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Output Voltage", driver.voltage_output)
			voltage_label = frappe.db.get_value(
				"ilL-Attribute-Output Voltage", driver.voltage_output, "dc_voltage"
			)
			attribute_links.append({
				"attribute_type": "Output Voltage",
				"attribute_doctype": "ilL-Attribute-Output Voltage",
				"attribute_name": driver.voltage_output,
				"display_label": f"{voltage_label} VDC" if voltage_label else driver.voltage_output,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Output Protocol
		if getattr(driver, "output_protocol", None):
			display_order += 1
			proto_data = frappe.db.get_value(
				"ilL-Attribute-Dimming Protocol", driver.output_protocol, ["label"], as_dict=True
			)
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", driver.output_protocol)
			attribute_links.append({
				"attribute_type": "Dimming Protocol",
				"attribute_doctype": "ilL-Attribute-Dimming Protocol",
				"attribute_name": driver.output_protocol,
				"display_label": proto_data.get("label") if proto_data else driver.output_protocol,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Input Protocols from child table
		for row in getattr(driver, "input_protocols", []):
			protocol_name = getattr(row, "protocol", None)
			if not protocol_name:
				continue
			# Skip if already added (e.g. same as output_protocol)
			if any(
				a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
				and a["attribute_name"] == protocol_name
				for a in attribute_links
			):
				continue
			display_order += 1
			proto_data = frappe.db.get_value(
				"ilL-Attribute-Dimming Protocol", protocol_name, ["label"], as_dict=True
			)
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", protocol_name)
			attribute_links.append({
				"attribute_type": "Dimming Protocol",
				"attribute_doctype": "ilL-Attribute-Dimming Protocol",
				"attribute_name": protocol_name,
				"display_label": proto_data.get("label") if proto_data else protocol_name,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

	def _populate_controller_attributes(self, attribute_links):
		"""Extract attributes from controller spec.

		Note: Caller must ensure a controller spec is resolvable before calling this method.
		"""
		controller_spec = self._resolve_controller_spec()
		if not controller_spec:
			return

		try:
			controller = frappe.get_doc("ilL-Spec-Controller", controller_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Controller spec {controller_spec} not found for product {self.name}",
				title="Controller Spec Not Found",
			)
			return

		display_order = 0

		# Input protocols
		for row in getattr(controller, "input_protocols", []):
			protocol_name = getattr(row, "protocol", None)
			if not protocol_name:
				continue
			if any(
				a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
				and a["attribute_name"] == protocol_name
				for a in attribute_links
			):
				continue
			display_order += 1
			proto_data = frappe.db.get_value(
				"ilL-Attribute-Dimming Protocol", protocol_name, ["label"], as_dict=True
			)
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", protocol_name)
			attribute_links.append({
				"attribute_type": "Dimming Protocol",
				"attribute_doctype": "ilL-Attribute-Dimming Protocol",
				"attribute_name": protocol_name,
				"display_label": proto_data.get("label") if proto_data else protocol_name,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Output protocols
		for row in getattr(controller, "output_protocols", []):
			protocol_name = getattr(row, "protocol", None)
			if not protocol_name:
				continue
			if any(
				a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
				and a["attribute_name"] == protocol_name
				for a in attribute_links
			):
				continue
			display_order += 1
			proto_data = frappe.db.get_value(
				"ilL-Attribute-Dimming Protocol", protocol_name, ["label"], as_dict=True
			)
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Dimming Protocol", protocol_name)
			attribute_links.append({
				"attribute_type": "Dimming Protocol",
				"attribute_doctype": "ilL-Attribute-Dimming Protocol",
				"attribute_name": protocol_name,
				"display_label": proto_data.get("label") if proto_data else protocol_name,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

	def _populate_accessory_attributes(self, attribute_links):
		"""Extract attributes from accessory spec.

		Note: Caller must ensure self.accessory_spec is set before calling this method.
		"""
		if not self.accessory_spec:
			return

		try:
			accessory = frappe.get_doc("ilL-Spec-Accessory", self.accessory_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Accessory spec {self.accessory_spec} not found for product {self.name}",
				title="Accessory Spec Not Found",
			)
			return

		display_order = 0

		# Map accessory fields to attribute types and doctypes
		accessory_field_map = {
			"environment_rating": ("Environment Rating", "ilL-Attribute-Environment Rating"),
			"mounting_method": ("Mounting Method", "ilL-Attribute-Mounting Method"),
			"joiner_system": ("Joiner System", "ilL-Attribute-Joiner System"),
			"joiner_angle": ("Joiner Angle", "ilL-Attribute-Joiner Angle"),
			"endcap_style": ("Endcap Style", "ilL-Attribute-Endcap Style"),
			"leader_cable": ("Leader Cable", "ilL-Attribute-Leader Cable"),
			"feed_type": ("Power Feed Type", "ilL-Attribute-Power Feed Type"),
		}

		for field_name, (attr_type, attr_doctype) in accessory_field_map.items():
			attr_value = getattr(accessory, field_name, None)
			if not attr_value:
				continue
			display_order += 1
			webflow_id = self._get_attribute_webflow_id(attr_doctype, attr_value)
			attribute_links.append({
				"attribute_type": attr_type,
				"attribute_doctype": attr_doctype,
				"attribute_name": attr_value,
				"display_label": attr_value,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

	def _populate_component_attributes(self, attribute_links):
		"""Extract attributes from lens spec for component products.

		Note: Caller must ensure self.lens_spec is set before calling this method.
		"""
		if not self.lens_spec:
			return

		try:
			lens = frappe.get_doc("ilL-Spec-Lens", self.lens_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Lens spec {self.lens_spec} not found for product {self.name}",
				title="Component Lens Spec Not Found",
			)
			return

		display_order = 0

		# Lens Appearance
		if getattr(lens, "lens_appearance", None):
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Lens Appearance", lens.lens_appearance)
			attribute_links.append({
				"attribute_type": "Lens Appearance",
				"attribute_doctype": "ilL-Attribute-Lens Appearance",
				"attribute_name": lens.lens_appearance,
				"display_label": lens.lens_appearance,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Series
		if getattr(lens, "series", None):
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Series", lens.series)
			attribute_links.append({
				"attribute_type": "Series",
				"attribute_doctype": "ilL-Attribute-Series",
				"attribute_name": lens.series,
				"display_label": lens.series,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

		# Lens Interface Type
		if getattr(lens, "lens_interface", None):
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Lens Interface Type", lens.lens_interface)
			attribute_links.append({
				"attribute_type": "Lens Interface Type",
				"attribute_doctype": "ilL-Attribute-Lens Interface Type",
				"attribute_name": lens.lens_interface,
				"display_label": lens.lens_interface,
				"webflow_item_id": webflow_id,
				"display_order": display_order,
			})

	def _get_attribute_webflow_id(self, doctype: str, name: str) -> str | None:
		"""Get the Webflow item ID for an attribute if it has been synced."""
		try:
			return frappe.db.get_value(doctype, name, "webflow_item_id")
		except Exception:
			return None

	def calculate_specifications(self):
		"""Auto-populate specifications from linked source doctype.
		
		When auto_calculate_specs is enabled, auto-calculated specifications
		(is_calculated=1) are cleared and re-populated from the linked spec.
		Manually-added specifications (is_calculated=0) are preserved.
		"""
		if not hasattr(self, 'specifications') or self.meta.get_field('specifications') is None:
			return
		
		if self.product_type == "Fixture Template" and self.fixture_template:
			self._calculate_fixture_specs()
		elif self.product_type == "Driver" and self.driver_spec:
			self._calculate_driver_specs()
		elif self.product_type == "Controller" and self.controller_spec:
			self._calculate_controller_specs()
		elif self.product_type == "LED Sheet" and self.led_sheet_template:
			self._calculate_led_sheet_specs()
		elif self.product_type == "LED Tape" and self.tape_spec:
			self._calculate_tape_specs()
		elif self.product_type in ["Component", "Extrusion Kit"] and self.profile_spec:
			self._calculate_profile_specs()

	def _calculate_fixture_specs(self):
		"""Calculate aggregated specs from fixture template with linked attribute options."""
		template = frappe.get_doc("ilL-Fixture-Template", self.fixture_template)
		specs_to_add = []

		# Aggregate output options from allowed tape offerings
		output_levels = self._get_allowed_output_levels(template)
		output_level_options = self._get_output_level_options_with_links(template)
		if output_levels:
			specs_to_add.append({
				"spec_group": "Performance",
				"spec_label": "Output Options",
				"spec_value": ", ".join(output_levels),
				"spec_unit": "lm/ft",
				"is_calculated": 1,
				"display_order": 10,
				"attribute_doctype": "ilL-Attribute-Output Level",
				"attribute_options_json": frappe.as_json(output_level_options) if output_level_options else None
			})

		# Aggregate CCT options
		ccts = self._get_allowed_ccts(template)
		cct_options = self._get_cct_options_with_links(template)
		if ccts:
			specs_to_add.append({
				"spec_group": "Optical",
				"spec_label": "Light Color (CCT)",
				"spec_value": ", ".join(ccts),
				"is_calculated": 1,
				"display_order": 20,
				"attribute_doctype": "ilL-Attribute-CCT",
				"attribute_options_json": frappe.as_json(cct_options) if cct_options else None
			})

		# Get watts/ft range (no linked attributes for this)
		watts_range = self._get_watts_per_ft_range(template)
		if watts_range:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Watts per Foot",
				"spec_value": watts_range,
				"spec_unit": "W/ft",
				"is_calculated": 1,
				"display_order": 30
			})

		# Get max run length (no linked attributes for this)
		max_run = self._get_max_run_length(template)
		if max_run:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Max Run Length",
				"spec_value": max_run,
				"spec_unit": "ft",
				"is_calculated": 1,
				"display_order": 40
			})

		# Get lens options with linked attributes
		lens_options = self._get_allowed_lens_appearances(template)
		lens_attr_options = self._get_lens_options_with_links(template)
		if lens_options:
			specs_to_add.append({
				"spec_group": "Optical",
				"spec_label": "Lens Options",
				"spec_value": ", ".join(lens_options),
				"is_calculated": 1,
				"display_order": 50,
				"attribute_doctype": "ilL-Attribute-Lens Appearance",
				"attribute_options_json": frappe.as_json(lens_attr_options) if lens_attr_options else None
			})

		# Get mounting options with linked attributes
		mounting_options = self._get_allowed_mounting_methods(template)
		mounting_attr_options = self._get_mounting_options_with_links(template)
		if mounting_options:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Mounting Options",
				"spec_value": ", ".join(mounting_options),
				"is_calculated": 1,
				"display_order": 60,
				"attribute_doctype": "ilL-Attribute-Mounting Method",
				"attribute_options_json": frappe.as_json(mounting_attr_options) if mounting_attr_options else None
			})

		# Get finish options with linked attributes
		finish_options = self._get_allowed_finishes(template)
		finish_attr_options = self._get_finish_options_with_links(template)
		if finish_options:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Finish Options",
				"spec_value": ", ".join(finish_options),
				"is_calculated": 1,
				"display_order": 70,
				"attribute_doctype": "ilL-Attribute-Finish",
				"attribute_options_json": frappe.as_json(finish_attr_options) if finish_attr_options else None
			})

		# Get environment ratings with linked attributes
		env_ratings = self._get_allowed_environment_ratings(template)
		env_attr_options = self._get_environment_options_with_links(template)
		if env_ratings:
			specs_to_add.append({
				"spec_group": "Environmental",
				"spec_label": "Environment Ratings",
				"spec_value": ", ".join(env_ratings),
				"is_calculated": 1,
				"display_order": 80,
				"attribute_doctype": "ilL-Attribute-Environment Rating",
				"attribute_options_json": frappe.as_json(env_attr_options) if env_attr_options else None
			})

		# Operating Temperature from webflow product fields
		if self.operating_temp_min_c is not None and self.operating_temp_max_c is not None:
			c_min = self.operating_temp_min_c
			c_max = self.operating_temp_max_c
			f_min = round(c_min * 9 / 5 + 32)
			f_max = round(c_max * 9 / 5 + 32)
			specs_to_add.append({
				"spec_group": "Environmental",
				"spec_label": "Operating Temperature",
				"spec_value": f"{f_min}°F ({c_min}°C) to {f_max}°F ({c_max}°C)",
				"is_calculated": 1,
				"display_order": 82
			})

		# Dimensions from linked profile spec
		profile_spec_name = getattr(template, "default_profile_spec", None)
		if profile_spec_name:
			dimensions = frappe.db.get_value(
				"ilL-Spec-Profile", profile_spec_name, "dimensions"
			)
			if not dimensions:
				# Profile may not have been re-saved since dimensions field was added;
				# compute it on the fly from width_mm / height_mm.
				raw = frappe.db.get_value(
					"ilL-Spec-Profile", profile_spec_name, ["width_mm", "height_mm"]
				)
				if raw:
					width_mm, height_mm = raw
					dimensions = compute_profile_dimensions(width_mm, height_mm)
			if dimensions:
				specs_to_add.append({
					"spec_group": "Physical",
					"spec_label": "Dimensions",
					"spec_value": dimensions,
					"is_calculated": 1,
					"display_order": 85
				})

		# Production Interval (cut increment from linked tape, in inches)
		cut_increments_mm = set()
		for tape_row in template.allowed_tape_offerings or []:
			offering_name = getattr(tape_row, "tape_offering", None)
			if not offering_name:
				continue
			offering_data = frappe.db.get_value(
				"ilL-Rel-Tape Offering", offering_name,
				["cut_increment_mm_override", "tape_spec"],
				as_dict=True,
			)
			if not offering_data:
				continue
			cut_mm = offering_data.get("cut_increment_mm_override")
			if not cut_mm and offering_data.get("tape_spec"):
				cut_mm = frappe.db.get_value(
					"ilL-Spec-LED Tape", offering_data["tape_spec"],
					"cut_increment_mm",
				)
			if cut_mm:
				cut_increments_mm.add(cut_mm)
		if cut_increments_mm:
			display_parts = [
				format_length_inches(v, precision=2)
				for v in sorted(cut_increments_mm)
				if format_length_inches(v, precision=2)
			]
			if display_parts:
				specs_to_add.append({
					"spec_group": "Physical",
					"spec_label": "Production Interval",
					"spec_value": ", ".join(display_parts),
					"is_calculated": 1,
					"display_order": 90
				})

		# Clear existing calculated specs and add new ones
		self.specifications = [
			s for s in (self.specifications or [])
			if not s.is_calculated
		]
		for spec in specs_to_add:
			self.append("specifications", spec)

	def _calculate_driver_specs(self):
		"""Calculate specs from driver spec doctype."""
		driver = frappe.get_doc("ilL-Spec-Driver", self.driver_spec)
		specs_to_add = []

		if driver.input_voltage:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Input Voltage",
				"spec_value": driver.input_voltage,
				"is_calculated": 1,
				"display_order": 10
			})

		if driver.voltage_output:
			voltage_data = frappe.db.get_value(
				"ilL-Attribute-Output Voltage",
				driver.voltage_output,
				["dc_voltage", "ac_voltage"],
				as_dict=True,
			) or {}
			dc_voltage = voltage_data.get("dc_voltage")
			ac_voltage = voltage_data.get("ac_voltage")
			output_voltage = dc_voltage or ac_voltage
			if output_voltage:
				specs_to_add.append({
					"spec_group": "Electrical",
					"spec_label": "Output Voltage",
					"spec_value": str(output_voltage),
					"spec_unit": "VDC" if dc_voltage else "VAC",
					"is_calculated": 1,
					"display_order": 20
				})

		if driver.max_wattage:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Max Wattage",
				"spec_value": str(driver.max_wattage),
				"spec_unit": "W",
				"is_calculated": 1,
				"display_order": 30
			})

		if driver.outputs_count:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Output Channels",
				"spec_value": str(driver.outputs_count),
				"is_calculated": 1,
				"display_order": 40
			})

		# Handle multiple input protocols from child table
		if driver.input_protocols:
			protocol_labels = []
			for row in driver.input_protocols:
				protocol_label = frappe.db.get_value(
					"ilL-Attribute-Dimming Protocol",
					row.protocol,
					"label"
				)
				if protocol_label:
					protocol_labels.append(protocol_label)
			if protocol_labels:
				specs_to_add.append({
					"spec_group": "Control",
					"spec_label": "Dimming Protocols",
					"spec_value": ", ".join(protocol_labels),
					"is_calculated": 1,
					"display_order": 50
				})

		# Clear existing calculated specs and add new ones
		self.specifications = [
			s for s in (self.specifications or [])
			if not s.is_calculated
		]
		for spec in specs_to_add:
			self.append("specifications", spec)

	def _calculate_controller_specs(self):
		"""Calculate specs from controller spec doctype."""
		controller = frappe.get_doc("ilL-Spec-Controller", self.controller_spec)
		specs_to_add = []

		if controller.controller_type:
			specs_to_add.append({
				"spec_group": "Control",
				"spec_label": "Controller Type",
				"spec_value": controller.controller_type,
				"is_calculated": 1,
				"display_order": 10
			})

		if controller.input_voltage_min and controller.input_voltage_max:
			voltage_str = f"{controller.input_voltage_min}-{controller.input_voltage_max}"
			if controller.input_voltage_type:
				voltage_str += f" {controller.input_voltage_type}"
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Input Voltage",
				"spec_value": voltage_str,
				"is_calculated": 1,
				"display_order": 20
			})

		if controller.channels:
			specs_to_add.append({
				"spec_group": "Control",
				"spec_label": "Channels",
				"spec_value": str(controller.channels),
				"is_calculated": 1,
				"display_order": 30
			})

		if controller.zones:
			specs_to_add.append({
				"spec_group": "Control",
				"spec_label": "Zones",
				"spec_value": str(controller.zones),
				"is_calculated": 1,
				"display_order": 40
			})

		if controller.max_load_watts:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Max Load",
				"spec_value": str(controller.max_load_watts),
				"spec_unit": "W",
				"is_calculated": 1,
				"display_order": 50
			})

		# Collect input protocols
		if controller.input_protocols:
			protocols = []
			for p in controller.input_protocols:
				if p.protocol:
					label = frappe.db.get_value(
						"ilL-Attribute-Dimming Protocol",
						p.protocol,
						"label"
					)
					if label:
						protocols.append(label)
			if protocols:
				specs_to_add.append({
					"spec_group": "Control",
					"spec_label": "Input Protocols",
					"spec_value": ", ".join(protocols),
					"is_calculated": 1,
					"display_order": 60
				})

		# Collect wireless protocols
		if controller.wireless_protocols:
			wireless = [p.protocol for p in controller.wireless_protocols if p.protocol]
			if wireless:
				specs_to_add.append({
					"spec_group": "Control",
					"spec_label": "Wireless Protocols",
					"spec_value": ", ".join(wireless),
					"is_calculated": 1,
					"display_order": 70
				})

		# Clear existing calculated specs and add new ones
		self.specifications = [
			s for s in (self.specifications or [])
			if not s.is_calculated
		]
		for spec in specs_to_add:
			self.append("specifications", spec)

	def _calculate_tape_specs(self):
		"""Calculate specs from LED tape spec doctype."""
		tape = frappe.get_doc("ilL-Spec-LED Tape", self.tape_spec)
		specs_to_add = []

		if tape.watts_per_foot:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Watts per Foot",
				"spec_value": str(tape.watts_per_foot),
				"spec_unit": "W/ft",
				"is_calculated": 1,
				"display_order": 10
			})

		if tape.voltage_drop_max_run_length_ft:
			specs_to_add.append({
				"spec_group": "Electrical",
				"spec_label": "Max Run Length",
				"spec_value": str(tape.voltage_drop_max_run_length_ft),
				"spec_unit": "ft",
				"is_calculated": 1,
				"display_order": 20
			})

		if tape.input_voltage:
			voltage_data = frappe.db.get_value(
				"ilL-Attribute-Output Voltage",
				tape.input_voltage,
				["dc_voltage", "ac_voltage"],
				as_dict=True,
			) or {}
			dc_voltage = voltage_data.get("dc_voltage")
			ac_voltage = voltage_data.get("ac_voltage")
			voltage_value = dc_voltage or ac_voltage
			if voltage_value:
				specs_to_add.append({
					"spec_group": "Electrical",
					"spec_label": "Input Voltage",
					"spec_value": str(voltage_value),
					"spec_unit": "VDC" if dc_voltage else "VAC",
					"is_calculated": 1,
					"display_order": 30
				})

		if tape.cut_increment_mm:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Cut Increment",
				"spec_value": str(tape.cut_increment_mm),
				"spec_unit": "mm",
				"is_calculated": 1,
				"display_order": 40
			})
			# Production Interval: cut increment converted to inches
			formatted = format_length_inches(tape.cut_increment_mm, precision=2)
			if formatted:
				specs_to_add.append({
					"spec_group": "Physical",
					"spec_label": "Production Interval",
					"spec_value": formatted,
					"is_calculated": 1,
					"display_order": 45
				})

		# Check for optional fields that may have been added
		if hasattr(tape, 'lumens_per_foot') and tape.lumens_per_foot:
			specs_to_add.append({
				"spec_group": "Performance",
				"spec_label": "Lumens per Foot",
				"spec_value": str(tape.lumens_per_foot),
				"spec_unit": "lm/ft",
				"is_calculated": 1,
				"display_order": 5
			})

		if hasattr(tape, 'cri_typical') and tape.cri_typical:
			specs_to_add.append({
				"spec_group": "Optical",
				"spec_label": "CRI",
				"spec_value": str(tape.cri_typical),
				"is_calculated": 1,
				"display_order": 50
			})

		# Clear existing calculated specs and add new ones
		self.specifications = [
			s for s in (self.specifications or [])
			if not s.is_calculated
		]
		for spec in specs_to_add:
			self.append("specifications", spec)

	def _calculate_profile_specs(self):
		"""Calculate specs from profile spec doctype."""
		profile = frappe.get_doc("ilL-Spec-Profile", self.profile_spec)
		specs_to_add = []

		if profile.stock_length_mm:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Stock Length",
				"spec_value": str(profile.stock_length_mm),
				"spec_unit": "mm",
				"is_calculated": 1,
				"display_order": 10
			})

		if profile.max_assembled_length_mm:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Max Assembled Length",
				"spec_value": str(profile.max_assembled_length_mm),
				"spec_unit": "mm",
				"is_calculated": 1,
				"display_order": 20
			})

		if profile.is_cuttable:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Cuttable",
				"spec_value": "Yes",
				"is_calculated": 1,
				"display_order": 30
			})

		# Dimensions (pre-computed on save; fall back to on-the-fly computation
		# for profiles that haven't been re-saved since the field was added).
		dimensions = profile.dimensions or compute_profile_dimensions(profile.width_mm, profile.height_mm)
		if dimensions:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Dimensions",
				"spec_value": dimensions,
				"is_calculated": 1,
				"display_order": 40
			})

		if profile.lens_interface:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Lens Interface",
				"spec_value": profile.lens_interface,
				"is_calculated": 1,
				"display_order": 60
			})

		# Environment ratings
		if profile.supported_environment_ratings:
			ratings = []
			for r in profile.supported_environment_ratings:
				if hasattr(r, 'environment_rating') and r.environment_rating:
					ratings.append(r.environment_rating)
			if ratings:
				specs_to_add.append({
					"spec_group": "Environmental",
					"spec_label": "Environment Ratings",
					"spec_value": ", ".join(ratings),
					"is_calculated": 1,
					"display_order": 70
				})

		# Clear existing calculated specs and add new ones
		self.specifications = [
			s for s in (self.specifications or [])
			if not s.is_calculated
		]
		for spec in specs_to_add:
			self.append("specifications", spec)

	def _calculate_led_sheet_specs(self):
		"""Calculate specs from the linked LED Sheet template's allowed_specs.

		Mirrors _enrich_led_sheet_template_specs() in webflow_export.py so the
		persisted Desk-form "Specifications" section matches what the Webflow
		sync will emit. Only active allowed_specs rows pointing at existing
		ilL-Spec-LED-Sheet docs with non-empty computed values contribute rows.
		"""
		try:
			template = frappe.get_doc("ilL-LED-Sheet-Template", self.led_sheet_template)
		except frappe.DoesNotExistError:
			return

		spec_names = [
			row.spec for row in (template.allowed_specs or [])
			if getattr(row, "spec", None) and getattr(row, "is_active", 1)
		]
		spec_docs = [
			frappe.get_doc("ilL-Spec-LED-Sheet", name)
			for name in spec_names
			if frappe.db.exists("ilL-Spec-LED-Sheet", name)
		]

		wattages = sorted({str(getattr(d, "total_sheet_watts", "")) for d in spec_docs if getattr(d, "total_sheet_watts", None)})
		lumens = sorted({str(getattr(d, "total_sheet_lumens", "")) for d in spec_docs if getattr(d, "total_sheet_lumens", None)})
		areas = sorted({str(getattr(d, "sheet_area_sqft", "")) for d in spec_docs if getattr(d, "sheet_area_sqft", None)})
		voltages = sorted({str(getattr(d, "input_voltage", "")) for d in spec_docs if getattr(d, "input_voltage", None)})
		ip_ratings = sorted({str(getattr(d, "ip_rating", "")) for d in spec_docs if getattr(d, "ip_rating", None)})
		cri_values = sorted({str(getattr(d, "cri", "")) for d in spec_docs if getattr(d, "cri", None)})

		specs_to_add = []

		def add(label, group, value, unit="", order=50, attr_doctype=None):
			if value:
				specs_to_add.append({
					"spec_group": group,
					"spec_label": label,
					"spec_value": value,
					"spec_unit": unit,
					"is_calculated": 1,
					"display_order": order,
					"attribute_doctype": attr_doctype,
				})

		# NOTE: spec_group must be a valid ilL-Child-Webflow-Specification Select
		# value (Electrical, Physical, Performance, Optical, Control, Environmental).
		add("Sheet Wattage", "Electrical", ", ".join(wattages), "W", 30)
		add("Sheet Area", "Physical", ", ".join(areas), "sq ft", 35)
		add("Sheet Lumens", "Optical", ", ".join(lumens), "lm", 40)
		add("Input Voltage", "Electrical", ", ".join(voltages), "", 25, "ilL-Attribute-Output Voltage")
		add("Color Rendering", "Optical", ", ".join(cri_values), "CRI", 55)
		add("IP Rating", "Environmental", ", ".join(ip_ratings), "", 60, "ilL-Attribute-IP Rating")
		add("Warranty", "Performance", getattr(template, "warranty", None), "", 90)

		self.specifications = [
			s for s in (self.specifications or [])
			if not s.is_calculated
		]
		for spec in specs_to_add:
			self.append("specifications", spec)

	def populate_configurator_options(self):
		"""Populate configurator options from template's allowed options.

		Step numbering aligns with CONFIGURATOR_STEPS in webflow_configurator.py:
		0-Series (locked), 1-Environment, 2-CCT, 3-Lens, 4-Output,
		5-Mounting, 6-Finish, 7-Length, 8-Start Feed Dir, 9-Start Feed Len,
		10-End Feed Dir, 11-End Feed Len.

		LED Package is part of the locked Series step (not a separate step).
		Endcap Color is auto-resolved from Finish via ilL-Rel-Finish Endcap Color.
		"""
		template = frappe.get_doc("ilL-Fixture-Template", self.fixture_template)

		# Configurator flow aligned with webflow_configurator.py CONFIGURATOR_STEPS
		# (step, option_type, label, depends_on_step)
		option_flow = [
			(1, "Environment Rating", "Dry/Wet", 0),
			(2, "CCT", "CCT", 1),
			(3, "Lens Appearance", "Lens", 0),
			(4, "Output Level", "Output", 3),
			(5, "Mounting Method", "Mounting", 0),
			(6, "Finish", "Finish", 0),
			(7, "Length", "Length", 0),
			(8, "Feed Direction", "Start Feed Direction", 0),
			(9, "Feed Direction", "Start Feed Length", 8),
			(10, "Feed Direction", "End Feed Direction", 0),
			(11, "Feed Direction", "End Feed Length", 10),
		]

		# Clear existing and rebuild
		self.configurator_options = []

		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_allowed_values_for_option(template, option_type, step=step)
			if allowed_values:
				self.append("configurator_options", {
					"option_step": step,
					"option_type": option_type,
					"option_label": label,
					"is_required": 1,
					"depends_on_step": depends_on,
					"allowed_values_json": frappe.as_json(allowed_values)
				})

		# Append Finish→Endcap Color mapping as metadata step
		finish_endcap_map = self._get_finish_endcap_color_mapping()
		if finish_endcap_map:
			self.append("configurator_options", {
				"option_step": 99,
				"option_type": "Endcap Color",
				"option_label": "Finish→Endcap Color Mapping",
				"is_required": 0,
				"depends_on_step": 6,
				"allowed_values_json": frappe.as_json(finish_endcap_map)
			})

		# Append fixture-level output level lookup table as metadata
		fixture_output_levels = self._get_fixture_output_level_table()
		if fixture_output_levels:
			self.append("configurator_options", {
				"option_step": 98,
				"option_type": "Fixture Output Level",
				"option_label": "Fixture Output Level Lookup",
				"is_required": 0,
				"depends_on_step": 4,
				"allowed_values_json": frappe.as_json(fixture_output_levels)
			})

	def populate_led_sheet_configurator_options(self):
		"""Populate configurator options from LED Sheet template allowed options."""
		template = frappe.get_doc("ilL-LED-Sheet-Template", self.led_sheet_template)
		option_flow = [
			(1, "CCT", "CCT", 0),
			(2, "Output Level", "Output", 1),
			(3, "Environment Rating", "Environment", 0),
			(4, "Mounting", "Mounting", 0),
			(5, "Finish", "Finish", 0),
			(6, "Coverage", "Coverage", 0),
		]

		existing_is_required = {}
		if not self.is_new():
			existing_opts = frappe.get_all(
				"ilL-Child-Webflow-Configurator-Option",
				filters={"parent": self.name, "parenttype": "ilL-Webflow-Product"},
				fields=["option_step", "is_required"],
			)
			existing_is_required = {
				int(opt.option_step): int(opt.is_required)
				for opt in existing_opts
				if opt.option_step is not None
			}

		self.configurator_options = []
		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_led_sheet_allowed_values(template, option_type)
			if allowed_values:
				self.append("configurator_options", {
					"option_step": step,
					"option_type": option_type,
					"option_label": label,
					"is_required": existing_is_required.get(step, 1),
					"depends_on_step": depends_on,
					"allowed_values_json": frappe.as_json(allowed_values),
				})

	def _get_led_sheet_allowed_values(self, template, option_type: str) -> list:
		if option_type == "Coverage":
			return [{"value": "__coverage_metadata__", "label": "Coverage", "code": ""}]
		values = []
		seen = set()
		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) != option_type or not getattr(opt, "is_active", 1):
				continue
			val = getattr(opt, "attribute_link", None)
			if not val or val in seen:
				continue
			seen.add(val)
			values.append({
				"value": val,
				"label": val,
				"code": getattr(opt, "option_code", "") or "",
				"is_default": getattr(opt, "is_default", False),
			})
		return values

	def _get_existing_is_required(self) -> dict:
		"""Return {option_step: is_required} as currently stored in the database.

		Lets an admin uncheck "Is Required" on a step without the value being
		clobbered the next time options are auto-populated.
		"""
		if self.is_new():
			return {}
		existing_opts = frappe.get_all(
			"ilL-Child-Webflow-Configurator-Option",
			filters={"parent": self.name, "parenttype": "ilL-Webflow-Product"},
			fields=["option_step", "is_required"],
		)
		return {
			int(opt.option_step): int(opt.is_required)
			for opt in existing_opts
			if opt.option_step is not None
		}

	def populate_driver_configurator_options(self):
		"""Populate configurator options from the linked Driver template.

		Driver flow: Wattage → Voltage Output → Input Protocol → Output Protocol.
		Every axis is independent; the configurator resolves the full selection
		to exactly one ilL-Child-Driver-Template-Variant row.
		"""
		template = frappe.get_doc("ilL-Driver-Template", self.driver_template)
		option_flow = [
			(1, "Wattage", "Wattage", 0),
			(2, "Voltage Output", "Output Voltage", 0),
			(3, "Input Protocol", "Dimming Input", 0),
			(4, "Output Protocol", "Output Protocol", 0),
		]
		self._populate_variant_configurator_options(template, option_flow)

	def populate_controller_configurator_options(self):
		"""Populate configurator options from the linked Controller template.

		Controller flow: Controller Type → Channels → Zones → Input Protocol →
		Output Protocol → Wireless Protocol → Mounting Type. Channels and Zones
		depend on Controller Type; the rest are independent.
		"""
		template = frappe.get_doc("ilL-Controller-Template", self.controller_template)
		option_flow = [
			(1, "Controller Type", "Controller Type", 0),
			(2, "Channels", "Channels", 1),
			(3, "Zones", "Zones", 1),
			(4, "Input Protocol", "Input Protocol", 0),
			(5, "Output Protocol", "Output Protocol", 0),
			(6, "Wireless Protocol", "Wireless Protocol", 0),
			(7, "Mounting Type", "Mounting Type", 0),
		]
		self._populate_variant_configurator_options(template, option_flow)

	def _populate_variant_configurator_options(self, template, option_flow):
		"""Shared rebuild of configurator_options for variant-matched templates.

		Used by the Driver and Controller flows, whose allowed_options child
		tables share the same shape (option_type / attribute_link / option_value
		/ option_label / option_code / is_default / is_active).
		"""
		existing_is_required = self._get_existing_is_required()

		self.configurator_options = []
		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_variant_allowed_values(template, option_type)
			if not allowed_values:
				continue
			self.append("configurator_options", {
				"option_step": step,
				"option_type": option_type,
				"option_label": label,
				"is_required": existing_is_required.get(step, 1),
				"depends_on_step": depends_on,
				"allowed_values_json": frappe.as_json(allowed_values),
			})

	def _get_variant_allowed_values(self, template, option_type: str) -> list:
		"""Extract allowed values for one option type from a template's allowed_options.

		Attribute-backed rows resolve through ``attribute_link``; scalar rows
		(Wattage, Channels, Zones, Wireless Protocol) use ``option_value``.
		"""
		values = []
		seen = set()

		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) != option_type:
				continue
			if hasattr(opt, "is_active") and not opt.is_active:
				continue

			val = getattr(opt, "attribute_link", None) or getattr(opt, "option_value", None)
			if not val or val in seen:
				continue
			seen.add(val)

			code = getattr(opt, "option_code", "") or ""
			attribute_doctype = getattr(opt, "attribute_doctype", None)
			if not code and attribute_doctype:
				code_field = _resolve_attribute_code_field(attribute_doctype)
				if code_field:
					code = frappe.db.get_value(attribute_doctype, val, code_field) or ""

			values.append({
				"value": val,
				"label": getattr(opt, "option_label", None) or val,
				"code": code,
				"is_default": bool(getattr(opt, "is_default", False)),
			})

		return values

	def populate_tape_neon_configurator_options(self):
		"""Populate configurator options from tape/neon template's allowed options.

		LED Tape / COB Tape flow: Environment → CCT → Output → Power Feed Type → Length.
		LED Neon flow: CCT → Output → Finish → IP Rating → Feed Direction → Length.

		Mounting selection (PCB Mounting for tape, Mounting Method for neon) has been
		moved to a post-configuration mounting accessory step.

		User-overridden is_required values are preserved across saves so that, for
		example, Feed Direction can be marked as optional by unchecking the checkbox.
		"""
		template = frappe.get_doc("ilL-Tape-Neon-Template", self.tape_neon_template)

		if is_tape_category(self.product_type):
			option_flow = [
				(1, "Environment Rating", "Environment", 0),
				(2, "CCT", "CCT", 1),
				(3, "Output Level", "Output", 2),
				(4, "Power Feed Type", "Power Feed Type", 0),
				(5, "Length", "Length", 0),
			]
		else:
			# LED Neon
			# Feed Direction is split into Start/End so Webflow can render two
			# distinct cards. The values are filtered by ``feed_position`` on each
			# ilL-Child-Tape-Neon-Allowed-Option row (Both | Start | End).
			option_flow = [
				(1, "CCT", "CCT", 0),
				(2, "Output Level", "Output", 1),
				(3, "Finish", "Finish", 0),
				(4, "IP Rating", "IP Rating", 0),
				(5, "Start Feed Direction", "Start Feed Direction", 0),
				(6, "End Feed Direction", "End Feed Direction", 0),
				(7, "Length", "Length", 0),
			]

		# Preserve any user-modified is_required values from the database
		existing_is_required = {}
		if not self.is_new():
			existing_opts = frappe.get_all(
				"ilL-Child-Webflow-Configurator-Option",
				filters={"parent": self.name, "parenttype": "ilL-Webflow-Product"},
				fields=["option_step", "is_required"],
			)
			existing_is_required = {
				int(opt.option_step): int(opt.is_required)
				for opt in existing_opts
				if opt.option_step is not None
			}

		# Clear existing and rebuild
		self.configurator_options = []

		for step, option_type, label, depends_on in option_flow:
			allowed_values = self._get_tape_neon_allowed_values(template, option_type)
			if allowed_values:
				# Use the previously saved is_required value if present; default to 1
				is_required = existing_is_required.get(step, 1)
				self.append("configurator_options", {
					"option_step": step,
					"option_type": option_type,
					"option_label": label,
					"is_required": is_required,
					"depends_on_step": depends_on,
					"allowed_values_json": frappe.as_json(allowed_values),
				})

	def _get_tape_neon_allowed_values(self, template, option_type: str) -> list:
		"""Extract allowed values from tape/neon template's allowed_options child table.

		Filters by is_active, maps to [{value, label, code, is_default}] format.
		For the Length step, returns length metadata instead.

		``Start Feed Direction`` / ``End Feed Direction`` resolve to the
		template's Feed Direction rows filtered by ``feed_position`` (rows
		marked Both appear in both buckets) so Webflow can render distinct
		Start vs End cards in the part-number builder.
		"""
		if option_type == "Length":
			return self._get_tape_neon_length_metadata(template)

		# Map option types to (child-table field, attribute doctype)
		option_field_map = {
			"CCT": ("cct", "ilL-Attribute-CCT"),
			"Output Level": ("output_level", "ilL-Attribute-Output Level"),
			"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
			"IP Rating": ("ip_rating", "ilL-Attribute-IP Rating"),
			"Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"Start Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"End Feed Direction": ("feed_direction", "ilL-Attribute-Feed-Direction"),
			"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
			"PCB Mounting": ("pcb_mounting", "ilL-Attribute-PCB Mounting"),
			"PCB Finish": ("pcb_finish", "ilL-Attribute-PCB Finish"),
			"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
			"Finish": ("finish", "ilL-Attribute-Finish"),
			"Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style"),
		}

		if option_type not in option_field_map:
			return []

		# Position filter for the Start/End feed-direction buckets.
		position_filter = None
		template_option_type = option_type
		if option_type == "Start Feed Direction":
			position_filter = "Start"
			template_option_type = "Feed Direction"
		elif option_type == "End Feed Direction":
			position_filter = "End"
			template_option_type = "Feed Direction"

		field, doctype = option_field_map[option_type]
		values = []
		seen = set()

		for opt in template.allowed_options or []:
			if getattr(opt, "option_type", None) != template_option_type:
				continue
			if hasattr(opt, "is_active") and not opt.is_active:
				continue

			# For Start/End Feed Direction, include rows whose feed_position is
			# "Both" OR matches the requested side.
			if position_filter is not None:
				row_position = (getattr(opt, "feed_position", None) or "Both")
				if row_position not in (position_filter, "Both"):
					continue

			val = getattr(opt, field, None)
			if not val or val in seen:
				continue
			seen.add(val)

			is_default = getattr(opt, "is_default", False) if hasattr(opt, "is_default") else False
			code = ""
			code_field = _resolve_attribute_code_field(doctype)
			if code_field:
				code = frappe.db.get_value(doctype, val, code_field) or ""

			# Build label
			label = val
			if option_type == "CCT":
				cct_data = frappe.db.get_value("ilL-Attribute-CCT", val, ["label", "kelvin"], as_dict=True)
				if cct_data:
					label = cct_data.get("label") or val
			elif option_type == "Output Level":
				level_data = frappe.db.get_value("ilL-Attribute-Output Level", val, ["value"], as_dict=True)
				if level_data and level_data.get("value"):
					label = f"{level_data['value']} lm/ft"

			values.append({
				"value": val,
				"label": label,
				"code": code,
				"is_default": is_default,
			})

		return values

	def _get_tape_neon_length_metadata(self, template) -> list:
		"""Get length constraints for tape/neon configurator Length step."""
		min_mm = getattr(template, "min_length_mm", None)
		max_mm = getattr(template, "max_length_mm", None)
		default_mm = getattr(template, "default_length_mm", None)
		increment_mm = getattr(template, "cut_increment_mm", None)

		# Convert to inches with sensible defaults
		min_inches = round(min_mm / 25.4, 1) if min_mm else 12
		max_inches = round(max_mm / 25.4, 1) if max_mm else 120
		default_inches = round(default_mm / 25.4, 1) if default_mm else 48
		increment_inches = round(increment_mm / 25.4, 2) if increment_mm else 0.5

		return [{
			"value": "__length_metadata__",
			"label": "Length",
			"code": "",
			"min_inches": min_inches,
			"max_inches": max_inches,
			"default_inches": default_inches,
			"increment_inches": increment_inches,
		}]

	def _get_allowed_values_for_option(self, template, option_type: str, step: int = 0) -> list:
		"""Get allowed values for a given option type.

		Each value includes {value, label, code, is_default} so the Webflow
		CMS JSON has attribute codes needed for part number building.
		"""
		values = []

		# Map option types to (template child-table field, attribute doctype)
		option_field_map = {
			"Finish": ("finish", "ilL-Attribute-Finish"),
			"Lens Appearance": ("lens_appearance", "ilL-Attribute-Lens Appearance"),
			"Mounting Method": ("mounting_method", "ilL-Attribute-Mounting Method"),
			"Environment Rating": ("environment_rating", "ilL-Attribute-Environment Rating"),
			"Power Feed Type": ("power_feed_type", "ilL-Attribute-Power Feed Type"),
			"Endcap Style": ("endcap_style", "ilL-Attribute-Endcap Style"),
		}

		if option_type in option_field_map:
			field, doctype = option_field_map[option_type]
			for opt in template.allowed_options or []:
				if hasattr(opt, 'option_type') and opt.option_type == option_type:
					if hasattr(opt, 'is_active') and not opt.is_active:
						continue
					val = getattr(opt, field, None)
					if val:
						is_default = getattr(opt, 'is_default', False) if hasattr(opt, 'is_default') else False
						code_field = _resolve_attribute_code_field(doctype)
						code = (frappe.db.get_value(doctype, val, code_field) or "") if code_field else ""
						values.append({
							"value": val,
							"label": val,
							"code": code,
							"is_default": is_default
						})

		# Special handling for LED Package, CCT, Output Level (from tape offerings)
		elif option_type == "LED Package":
			values = self._get_led_packages_from_tapes(template)
		elif option_type == "CCT":
			values = self._get_ccts_from_tapes(template)
		elif option_type == "Output Level":
			values = self._get_output_levels_lens_map(template)
		elif option_type == "Endcap Color":
			# Get all endcap colors (globally available)
			colors = frappe.get_all(
				"ilL-Attribute-Endcap Color",
				filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Endcap Color", "is_active") else {},
				fields=["name", "code", "display_name"] if frappe.db.has_column("ilL-Attribute-Endcap Color", "display_name") else ["name", "code"]
			)
			for c in colors:
				values.append({
					"value": c.name,
					"label": c.get("display_name") or c.name,
					"code": c.get("code", "")
				})
		elif option_type == "Feed Direction":
			values = self._get_feed_direction_values(step)
		elif option_type == "Length":
			values = self._get_length_metadata(template)

		return values

	def _get_feed_direction_values(self, step: int) -> list:
		"""Get feed direction or feed length values depending on step.

		Steps 8 (start feed), 10 (end feed) = directions (End, Back, etc.);
		steps 9 (start leader), 11 (end leader) = standard leader lengths.
		"""
		if step in (8, 10):
			# Direction options
			if frappe.db.exists("DocType", "ilL-Attribute-Feed-Direction"):
				directions = frappe.get_all(
					"ilL-Attribute-Feed-Direction",
					filters={"is_active": 1} if frappe.db.has_column("ilL-Attribute-Feed-Direction", "is_active") else {},
					fields=["direction_name as name", "code", "description"],
					order_by="direction_name"
				)
				values = [
					{"value": d.name, "label": d.name, "code": d.get("code", "")}
					for d in directions
				]
			else:
				values = [
					{"value": "End", "label": "End", "code": "E"},
					{"value": "Back", "label": "Back", "code": "B"},
				]
			# End feed direction can also be "Endcap" (no leader)
			if step == 10:
				values.append({"value": "Endcap", "label": "Endcap", "code": "CAP"})
			return values
		else:
			# Leader length options (steps 9, 11)
			standard_lengths = [2, 4, 6, 8, 10, 15, 20, 25, 30]
			return [
				{"value": str(l), "label": f"{l} ft", "code": str(l)}
				for l in standard_lengths
			]

	def _get_length_metadata(self, template) -> list:
		"""Get length constraints as metadata for the Length step."""
		max_length_mm = getattr(template, 'assembled_max_len_mm', None)
		default_stock_mm = getattr(template, 'default_profile_stock_len_mm', None)

		min_inches = 12
		max_inches = round(max_length_mm / 25.4, 1) if max_length_mm else 120
		default_inches = round(default_stock_mm / 25.4, 1) if default_stock_mm else 50

		return [{
			"value": "__length_metadata__",
			"label": "Length",
			"code": "",
			"min_inches": min_inches,
			"max_inches": max_inches,
			"default_inches": default_inches,
			"increment_inches": 0.5,
		}]

	def _get_finish_endcap_color_mapping(self) -> list:
		"""Get Finish→Endcap Color mapping from ilL-Rel-Finish Endcap Color.

		Returns a list of {finish, endcap_color, endcap_color_code, is_default}
		so Webflow JS can filter endcap colors by the selected finish.
		"""
		mappings = frappe.get_all(
			"ilL-Rel-Finish Endcap Color",
			filters={"is_active": 1},
			fields=["finish", "endcap_color", "is_default"],
			order_by="is_default DESC, modified DESC",
		)
		result = []
		for m in mappings:
			ec_code = frappe.db.get_value("ilL-Attribute-Endcap Color", m.endcap_color, "code") or ""
			ec_label = ""
			if frappe.db.has_column("ilL-Attribute-Endcap Color", "display_name"):
				ec_label = frappe.db.get_value("ilL-Attribute-Endcap Color", m.endcap_color, "display_name") or ""
			result.append({
				"finish": m.finish,
				"endcap_color": m.endcap_color,
				"endcap_color_code": ec_code,
				"endcap_color_label": ec_label or ec_code or m.endcap_color,
				"is_default": m.is_default,
			})
		return result

	def _get_fixture_output_level_table(self) -> list:
		"""Get fixture-level output levels for client-side tape×lens→fixture mapping.

		The client multiplies tape output × lens transmission and finds the closest
		fixture-level output level to get the correct sku_code for the part number.
		"""
		fixture_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code"],
			order_by="value asc"
		)
		return [
			{
				"value": fl.name,
				"label": f"{fl.value} lm/ft",
				"code": fl.sku_code or "",
				"numeric_value": fl.value or 0,
			}
			for fl in fixture_levels
		]

	def _get_allowed_output_levels(self, template) -> list:
		"""Get unique output levels from allowed tape offerings."""
		output_levels = set()
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				output_level = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"output_level"
				)
				if output_level:
					value = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						output_level,
						"value"
					)
					if value:
						output_levels.add(str(value))
		return sorted(output_levels, key=lambda x: int(x) if x.isdigit() else 0)

	def _get_allowed_ccts(self, template) -> list:
		"""Get unique CCTs from allowed tape offerings."""
		ccts = set()
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				cct = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"cct"
				)
				if cct:
					ccts.add(cct)
		return sorted(list(ccts))

	def _get_watts_per_ft_range(self, template) -> str:
		"""Get watts per foot range from allowed tape offerings."""
		watts_values = []
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				tape_spec = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"tape_spec"
				)
				if tape_spec:
					watts = frappe.db.get_value(
						"ilL-Spec-LED Tape",
						tape_spec,
						"watts_per_foot"
					)
					if watts:
						watts_values.append(watts)
		
		if not watts_values:
			return ""
		
		min_watts = min(watts_values)
		max_watts = max(watts_values)
		
		if min_watts == max_watts:
			return str(min_watts)
		return f"{min_watts} - {max_watts}"

	def _get_max_run_length(self, template) -> str:
		"""Get max run length from allowed tape offerings."""
		max_runs = []
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				tape_spec = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"tape_spec"
				)
				if tape_spec:
					max_run = frappe.db.get_value(
						"ilL-Spec-LED Tape",
						tape_spec,
						"voltage_drop_max_run_length_ft"
					)
					if max_run:
						max_runs.append(max_run)
		
		if not max_runs:
			return ""
		
		min_run = min(max_runs)
		max_run = max(max_runs)
		
		if min_run == max_run:
			return str(min_run)
		return f"{min_run} - {max_run}"

	def _get_allowed_lens_appearances(self, template) -> list:
		"""Get unique lens appearances from allowed options."""
		lenses = set()
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Lens Appearance":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'lens_appearance') and opt.lens_appearance:
					lenses.add(opt.lens_appearance)
		return sorted(list(lenses))

	def _get_allowed_mounting_methods(self, template) -> list:
		"""Get unique mounting methods from allowed options."""
		methods = set()
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Mounting Method":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'mounting_method') and opt.mounting_method:
					methods.add(opt.mounting_method)
		return sorted(list(methods))

	def _get_allowed_finishes(self, template) -> list:
		"""Get unique finishes from allowed options."""
		finishes = set()
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Finish":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'finish') and opt.finish:
					finishes.add(opt.finish)
		return sorted(list(finishes))

	def _get_led_packages_from_tapes(self, template) -> list:
		"""Get unique LED packages from allowed tape offerings."""
		packages = {}
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				led_package = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"led_package"
				)
				if led_package and led_package not in packages:
					code = frappe.db.get_value(
						"ilL-Attribute-LED Package",
						led_package,
						"code"
					)
					packages[led_package] = {
						"value": led_package,
						"label": led_package,
						"code": code or ""
					}
		return list(packages.values())

	def _get_ccts_from_tapes(self, template) -> list:
		"""Get unique CCTs from allowed tape offerings with details."""
		ccts = {}
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				cct = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"cct"
				)
				if cct and cct not in ccts:
					cct_data = frappe.db.get_value(
						"ilL-Attribute-CCT",
						cct,
						["code", "kelvin", "label"],
						as_dict=True
					)
					if cct_data:
						ccts[cct] = {
							"value": cct,
							"label": cct_data.get("label") or cct,
							"code": cct_data.get("code") or "",
							"kelvin": cct_data.get("kelvin") or 0
						}
		return sorted(list(ccts.values()), key=lambda x: x.get("kelvin", 0))

	def _get_output_levels_from_tapes(self, template) -> list:
		"""Get unique output levels from allowed tape offerings with details.

		Each value includes tape_output_lm_ft so Webflow JS can compute
		delivered output (tape × lens transmission) client-side.
		"""
		levels = {}
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				output_level = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"output_level"
				)
				if output_level and output_level not in levels:
					level_data = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						output_level,
						["sku_code", "value"],
						as_dict=True
					)
					if level_data:
						tape_lm_ft = level_data.get("value") or 0
						levels[output_level] = {
							"value": output_level,
							"label": f"{tape_lm_ft} lm/ft",
							"code": level_data.get("sku_code") or "",
							"lm_per_ft": tape_lm_ft,
							"tape_output_lm_ft": tape_lm_ft,
						}
		return sorted(list(levels.values()), key=lambda x: x.get("lm_per_ft", 0))

	def _get_output_levels_lens_map(self, template) -> dict:
		"""Build lens-keyed output mapping matrix for the Output step.

		Returns a dict with 'lensMap' keyed by lens code (e.g. WH, WL, WX).
		Each entry is a sorted list of output options showing delivered lumens
		(tape output × lens transmission) matched to fixture-level output levels.

		This lets the Webflow script dynamically rebuild Output radio buttons
		whenever the user changes the Lens selection.
		"""
		# Gather allowed lenses for this template
		lenses = []
		for opt in template.allowed_options or []:
			if (getattr(opt, 'option_type', None) == "Lens Appearance"
					and getattr(opt, 'is_active', True)):
				lens_name = getattr(opt, 'lens_appearance', None)
				if lens_name:
					lens_data = frappe.db.get_value(
						"ilL-Attribute-Lens Appearance", lens_name,
						["name", "code", "transmission"], as_dict=True
					)
					if lens_data and lens_data.get("code"):
						lenses.append(lens_data)

		if not lenses:
			return {}

		# Get flat raw tape output levels
		raw_outputs = self._get_output_levels_from_tapes(template)
		if not raw_outputs:
			return {}

		# Get fixture-level output levels for closest-match snapping
		fixture_output_levels = frappe.get_all(
			"ilL-Attribute-Output Level",
			filters={"is_fixture_level": 1},
			fields=["name", "value", "sku_code"],
			order_by="value asc"
		)

		lens_map = {}
		for lens in lenses:
			lens_code = lens.get("code")
			transmission = transmission_fraction(lens.get("transmission"))

			options = []
			by_level = {}
			for raw in raw_outputs:
				tape_lm = raw.get("tape_output_lm_ft") or raw.get("lm_per_ft") or 0
				delivered = tape_lm * transmission

				if fixture_output_levels:
					closest = min(
						fixture_output_levels,
						key=lambda x: abs((x.value or 0) - delivered)
					)
					by_level.setdefault(closest.name, (closest, []))[1].append(
						{**raw, "output_value_lm_ft": tape_lm}
					)
				else:
					delivered_rounded = int(round(delivered))
					options.append({
						"value": raw.get("value"),
						"label": f"{delivered_rounded} lm/ft",
						"code": raw.get("code", ""),
						"tape_output_lm_ft": tape_lm,
						"delivered_lm_ft": delivered_rounded,
					})

			# Same rule as the configurator engine: of the tapes that round to a
			# level, the one whose delivered output is closest builds it.
			for level, candidates in by_level.values():
				raw = closest_tape(candidates, level.value or 0, transmission)
				options.append({
					"value": raw.get("value"),
					"label": f"{level.value} lm/ft",
					"code": level.sku_code or raw.get("code", ""),
					"tape_output_lm_ft": raw["output_value_lm_ft"],
					"delivered_lm_ft": level.value,
				})

			lens_map[lens_code] = sorted(
				options, key=lambda x: x.get("delivered_lm_ft", 0)
			)

		return {"lensMap": lens_map}

	def _get_output_level_options_with_links(self, template) -> list:
		"""Get output level options with doctype links for Webflow."""
		options = []
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				output_level = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"output_level"
				)
				if output_level and output_level not in [o["attribute_value"] for o in options]:
					level_data = frappe.db.get_value(
						"ilL-Attribute-Output Level",
						output_level,
						["sku_code", "value"],
						as_dict=True
					)
					if level_data:
						options.append({
							"attribute_type": "Output Level",
							"attribute_doctype": "ilL-Attribute-Output Level",
							"attribute_value": output_level,
							"display_label": f"{level_data.get('value', '')} lm/ft",
							"code": level_data.get("sku_code") or ""
						})
		return sorted(options, key=lambda x: x.get("display_label", ""))

	def _get_cct_options_with_links(self, template) -> list:
		"""Get CCT options with doctype links for Webflow."""
		options = []
		for tape_row in template.allowed_tape_offerings or []:
			if hasattr(tape_row, 'tape_offering') and tape_row.tape_offering:
				cct = frappe.db.get_value(
					"ilL-Rel-Tape Offering",
					tape_row.tape_offering,
					"cct"
				)
				if cct and cct not in [o["attribute_value"] for o in options]:
					cct_data = frappe.db.get_value(
						"ilL-Attribute-CCT",
						cct,
						["code", "kelvin", "label"],
						as_dict=True
					)
					if cct_data:
						options.append({
							"attribute_type": "CCT",
							"attribute_doctype": "ilL-Attribute-CCT",
							"attribute_value": cct,
							"display_label": cct_data.get("label") or cct,
							"code": cct_data.get("code") or "",
							"kelvin": cct_data.get("kelvin") or 0
						})
		return sorted(options, key=lambda x: x.get("kelvin", 0))

	def _get_lens_options_with_links(self, template) -> list:
		"""Get lens appearance options with doctype links for Webflow."""
		options = []
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Lens Appearance":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'lens_appearance') and opt.lens_appearance:
					if opt.lens_appearance not in [o["attribute_value"] for o in options]:
						options.append({
							"attribute_type": "Lens Appearance",
							"attribute_doctype": "ilL-Attribute-Lens Appearance",
							"attribute_value": opt.lens_appearance,
							"display_label": opt.lens_appearance,
							"is_default": getattr(opt, 'is_default', False)
						})
		return sorted(options, key=lambda x: x.get("display_label", ""))

	def _get_mounting_options_with_links(self, template) -> list:
		"""Get mounting method options with doctype links for Webflow."""
		options = []
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Mounting Method":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'mounting_method') and opt.mounting_method:
					if opt.mounting_method not in [o["attribute_value"] for o in options]:
						options.append({
							"attribute_type": "Mounting Method",
							"attribute_doctype": "ilL-Attribute-Mounting Method",
							"attribute_value": opt.mounting_method,
							"display_label": opt.mounting_method,
							"is_default": getattr(opt, 'is_default', False)
						})
		return sorted(options, key=lambda x: x.get("display_label", ""))

	def _get_finish_options_with_links(self, template) -> list:
		"""Get finish options with doctype links for Webflow."""
		options = []
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Finish":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'finish') and opt.finish:
					if opt.finish not in [o["attribute_value"] for o in options]:
						options.append({
							"attribute_type": "Finish",
							"attribute_doctype": "ilL-Attribute-Finish",
							"attribute_value": opt.finish,
							"display_label": opt.finish,
							"is_default": getattr(opt, 'is_default', False)
						})
		return sorted(options, key=lambda x: x.get("display_label", ""))

	def _get_allowed_environment_ratings(self, template) -> list:
		"""Get unique environment ratings from allowed options."""
		ratings = set()
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Environment Rating":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'environment_rating') and opt.environment_rating:
					ratings.add(opt.environment_rating)
		return sorted(list(ratings))

	def _get_environment_options_with_links(self, template) -> list:
		"""Get environment rating options with doctype links for Webflow."""
		options = []
		for opt in template.allowed_options or []:
			if hasattr(opt, 'option_type') and opt.option_type == "Environment Rating":
				if hasattr(opt, 'is_active') and not opt.is_active:
					continue
				if hasattr(opt, 'environment_rating') and opt.environment_rating:
					if opt.environment_rating not in [o["attribute_value"] for o in options]:
						options.append({
							"attribute_type": "Environment Rating",
							"attribute_doctype": "ilL-Attribute-Environment Rating",
							"attribute_value": opt.environment_rating,
							"display_label": opt.environment_rating,
							"is_default": getattr(opt, 'is_default', False)
						})
		return sorted(options, key=lambda x: x.get("display_label", ""))

	def sync_custom_template_data(self):
		"""V2 Sync: Updates ilL-Webflow-Product custom fields with data from linked templates."""
		# custom_spec_custom is a site Custom Field the app does not ship; skip where it is absent.
		if not self.meta.has_field("custom_spec_custom"):
			return

		PRODUCT_TYPE_TEMPLATE_MAP = {
			"LED Tape": {"link_field": "tape_neon_template", "doctype": "ilL-Tape-Neon-Template"},
			"COB Tape": {"link_field": "tape_neon_template", "doctype": "ilL-Tape-Neon-Template"},
			"LED Neon": {"link_field": "tape_neon_template", "doctype": "ilL-Tape-Neon-Template"},
			"Fixture Template": {"link_field": "fixture_template", "doctype": "ilL-Fixture-Template"},
			"Driver": {"link_field": "driver_template", "doctype": "ilL-Driver-Template"},
			"Controller": {"link_field": "controller_template", "doctype": "ilL-Controller-Template"},
			"LED Sheet": {"link_field": "led_sheet_template", "doctype": "ilL-LED-Sheet-Template"},
			"Extrusion Kit": {"link_field": "kit_template", "doctype": "ilL-Extrusion-Kit-Template"},
		}

		MANAGED_LABELS = (
			"Color Rendering (CRI)", "Output Options", "Light Color (CCT)", "Lens Options",
			"Mounting Options", "Mounting", "Finish Options", "Finish", "Environment Ratings", 
			"Operating Temperature", "Production Interval", "Dimensions", "Dimensions (ft)",
			"Cut Interval", "Watts per Foot", "Watts per Square Foot", "Max Run Length",
			"Input Voltage", "Dimming", "Max Footage per 100W Supply", "Beam Spread",
			"Minimum Bending Diameter", "Warranty", "Power Factor", "Total Harmonic Distortion",
			"Efficiency", "Start Up Time", "Minimum Load", "Inrush Current", "Max Input Current",
			"Output Voltage", "Max Output Current", "Certifications"
		)

		def format_inches(mm):
			if not mm:
				return None
			inches = float(mm) / 25.4
			return f'{inches:.2f}"'

		def ceil_val(num):
			i = int(num)
			if num > i:
				return i + 1
			return i

		def append_spec(current_doc, group, label, value, unit="", order=50, attr_doctype="", options=None):
			current_doc.append("custom_spec_custom", {
				"spec_group": group,
				"spec_label": label,
				"spec_value": value,
				"spec_unit": unit,
				"is_calculated": 1,
				"display_order": order,
				"attribute_doctype": attr_doctype,
				"attribute_options_json": json.dumps(options, default=str, indent=1) if options else None,
			})

		debug = {
			"product": self.name,
			"product_type": self.product_type,
			"existing_labels_before": [row.spec_label for row in (self.custom_spec_custom or [])],
			"results": {},
		}

		def record(debug_dict, label, found_count=None, values=None, appended=False, skip_reason=None):
			debug_dict["results"][label] = {
				"found_count": found_count,
				"values": values or [],
				"appended": appended,
				"skip_reason": skip_reason,
			}

		if self.product_type not in PRODUCT_TYPE_TEMPLATE_MAP:
			for label in MANAGED_LABELS:
				record(debug, label, skip_reason=f"No mapping defined for product_type '{self.product_type}'")
		else:
			mapping = PRODUCT_TYPE_TEMPLATE_MAP[self.product_type]
			linked_doc_name = self.get(mapping["link_field"])
			debug["template_link_field"] = mapping["link_field"]
			debug["template_doctype"] = mapping["doctype"]
			debug["template_name"] = linked_doc_name

			if not linked_doc_name:
				reason = f"Field '{mapping['link_field']}' is empty on this product"
				for label in MANAGED_LABELS:
					record(debug, label, skip_reason=reason)
			else:
				template_doc = frappe.get_doc(mapping["doctype"], linked_doc_name)

				# ============================================================
				# PART 1: Core Field, Document, and Certification Sync
				# ============================================================
				
				self.custom_template_status = template_doc.get("product_status")
				self.custom_web_product_category = template_doc.get("product_category")
				self.custom_web_series = template_doc.get("series")

				# --- Documents Sync ---
				existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}
				
				spec_sheet_file = template_doc.get("spec_sheet")
				spec_title = (self.product_name or "") + " Spec Sheet"
				
				if spec_sheet_file:
					self.documents = [
						d for d in (self.documents or []) 
						if not (d.document_type == "Spec Sheet" and d.document_title == spec_title and d.document_file != spec_sheet_file)
					]
					existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}
					
					if spec_sheet_file in existing_docs:
						existing_docs[spec_sheet_file].document_type = "Spec Sheet"
						existing_docs[spec_sheet_file].document_title = spec_title
						existing_docs[spec_sheet_file].display_order = 1
					else:
						self.append("documents", {
							"document_type": "Spec Sheet",
							"document_file": spec_sheet_file,
							"document_title": spec_title,
							"display_order": 1,
						})
						existing_docs[spec_sheet_file] = self.documents[-1]
				else:
					self.documents = [d for d in (self.documents or []) if not (d.document_type == "Spec Sheet" and d.document_title == spec_title)]
					existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}

				spec_submittal_file = template_doc.get("spec_submittal_template")
				submittal_title = (self.product_name or "") + " Spec Submittal"
				
				if spec_submittal_file:
					self.documents = [
						d for d in (self.documents or []) 
						if not (d.document_type == "Spec Sheet" and d.document_title == submittal_title and d.document_file != spec_submittal_file)
					]
					existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}
					
					if spec_submittal_file in existing_docs:
						existing_docs[spec_submittal_file].document_type = "Spec Sheet"
						existing_docs[spec_submittal_file].document_title = submittal_title
						existing_docs[spec_submittal_file].display_order = 2
					else:
						self.append("documents", {
							"document_type": "Spec Sheet",
							"document_file": spec_submittal_file,
							"document_title": submittal_title,
							"display_order": 2,
						})
						existing_docs[spec_submittal_file] = self.documents[-1]
				else:
					self.documents = [d for d in (self.documents or []) if not (d.document_type == "Spec Sheet" and d.document_title == submittal_title)]
					existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}

				for d in (template_doc.get("custom_documents") or []):
					df = d.get("document_file")
					if df:
						if df in existing_docs:
							existing_docs[df].document_type = d.get("document_type")
							existing_docs[df].document_title = d.get("document_title")
							existing_docs[df].display_order = d.get("display_order") or 10
						else:
							self.append("documents", {
								"document_type": d.get("document_type"),
								"document_title": d.get("document_title"),
								"document_file": df,
								"display_order": d.get("display_order") or 10
							})
							existing_docs[df] = self.documents[-1]

				template_certs = [
					c_row.certification
					for c_row in getattr(template_doc, "certifications", [])
					if c_row.certification
				]
				self.certifications = []
				for cert_name in template_certs:
					self.append("certifications", {
						"certification": cert_name,
						"display_order": 0,
					})

				# ============================================================
				# PART 2: Configurator Option Mirroring
				# ============================================================
				if self.product_type in ("LED Tape", "COB Tape", "LED Neon"):

					LENGTH_METADATA_JSON = json.dumps([
						{
							"code": "",
							"default_inches": 48,
							"increment_inches": 0.5,
							"label": "Length",
							"max_inches": 120,
							"min_inches": 12,
							"value": "__length_metadata__",
						}
					], indent=1)

					OPTION_LINK_MAP = {
						"CCT": {"field": "cct", "doctype": "ilL-Attribute-CCT", "code_field": "code"},
						"Output Level": {"field": "output_level", "doctype": "ilL-Attribute-Output Level", "code_field": "sku_code"},
						"Lens Appearance": {"field": "lens_appearance", "doctype": "ilL-Attribute-Lens Appearance", "code_field": "code"},
						"Environment Rating": {"field": "environment_rating", "doctype": "ilL-Attribute-Environment Rating", "code_field": "code"},
						"IP Rating": {"field": "ip_rating", "doctype": "ilL-Attribute-IP Rating", "code_field": "code"},
						"Feed Direction": {"field": "feed_direction", "doctype": "ilL-Attribute-Feed-Direction", "code_field": "code"},
						"PCB Mounting": {"field": "pcb_mounting", "doctype": "ilL-Attribute-PCB Mounting", "code_field": "code"},
						"PCB Finish": {"field": "pcb_finish", "doctype": "ilL-Attribute-PCB Finish", "code_field": "code"},
						"Mounting Method": {"field": "mounting_method", "doctype": "ilL-Attribute-Mounting Method", "code_field": "code"},
						"Finish": {"field": "finish", "doctype": "ilL-Attribute-Finish", "code_field": "code"},
						"Endcap Style": {"field": "endcap_style", "doctype": "ilL-Attribute-Endcap Style", "code_field": "code"},
					}

					SPECIAL_TYPES = {"Feed Direction", "Length", "Power Feed Type"}

					def build_value(code, label, is_default):
						return {"code": code or "", "is_default": is_default or 0, "label": label, "value": label}

					def build_simple_values(template_rows, mapping_entry):
						values = []
						for t_row in template_rows:
							attr_name = t_row.get(mapping_entry["field"])
							if not attr_name:
								continue
							code_value = frappe.db.get_value(
								mapping_entry["doctype"], attr_name, mapping_entry["code_field"]
							) or ""
							disp = t_row.custom_value_label or attr_name
							values.append({
								"code": code_value or "",
								"is_default": t_row.is_default or 0,
								"label": disp,
								"value": disp,
							})
						return values

					options_by_type = {}
					for t_row in (template_doc.allowed_options or []):
						if not t_row.is_active:
							continue
						if t_row.option_type not in options_by_type:
							options_by_type[t_row.option_type] = []
						options_by_type[t_row.option_type].append(t_row)

					feed_lengths_by_step = {}
					for fl in (template_doc.feed_lengths or []):
						if fl.step not in feed_lengths_by_step:
							feed_lengths_by_step[fl.step] = []
						feed_lengths_by_step[fl.step].append(fl)

					existing_by_type = {}
					for cfg_row in (self.configurator_options or []):
						if cfg_row.option_type not in existing_by_type:
							existing_by_type[cfg_row.option_type] = []
						existing_by_type[cfg_row.option_type].append(cfg_row)

					for cfg_row in (self.configurator_options or []):
						label = cfg_row.option_label
						otype = cfg_row.option_type

						if otype == "Length":
							cfg_row.allowed_values_json = LENGTH_METADATA_JSON
							continue

						if label == "Start Feed Direction" or label == "End Feed Direction":
							is_end = label == "End Feed Direction"
							wanted = {"Both", "End"} if is_end else {"Both", "Start"}
							entry = OPTION_LINK_MAP["Feed Direction"]
							values = []
							for t_row in options_by_type.get("Feed Direction", []):
								if (t_row.feed_position or "Both") not in wanted:
									continue
								attr_name = t_row.get(entry["field"])
								if not attr_name:
									continue
								code_value = frappe.db.get_value(
									entry["doctype"], attr_name, entry["code_field"]
								) or ""
								disp = t_row.custom_value_label or attr_name
								values.append(build_value(code_value, disp, t_row.is_default))
							if is_end:
								values.append(build_value("C", "Endcap", 0))
							cfg_row.allowed_values_json = json.dumps(values, indent=1)
							continue

						if label == "Start Feed Length" or label == "End Feed Length":
							values = [build_value("", "Endcap", 0)]
							for fl in sorted(feed_lengths_by_step.get(cfg_row.option_step, []),
											 key=lambda r: (r.display_order or 0, r.idx or 0)):
								values.append(build_value(fl.code, fl.label, 0))
							cfg_row.allowed_values_json = json.dumps(values, indent=1)
							continue

						entry = OPTION_LINK_MAP.get(otype)
						if entry:
							values = build_simple_values(options_by_type.get(otype, []), entry)
							cfg_row.allowed_values_json = json.dumps(values, indent=1)

					for template_type in options_by_type.keys():
						if template_type in SPECIAL_TYPES:
							continue
						if template_type in existing_by_type:
							continue
						entry = OPTION_LINK_MAP.get(template_type)
						if not entry:
							continue
						values = build_simple_values(options_by_type.get(template_type, []), entry)
						self.append("configurator_options", {
							"option_type": template_type,
							"option_label": template_type,
							"option_step": 99,
							"allowed_values_json": json.dumps(values, indent=1),
						})

					has_length = False
					finish_step = None
					max_step = 0
					for cfg_row in (self.configurator_options or []):
						if cfg_row.option_type == "Length":
							has_length = True
						if cfg_row.option_type == "Finish":
							finish_step = cfg_row.option_step
						if cfg_row.option_step and cfg_row.option_step > max_step:
							max_step = cfg_row.option_step

					if not has_length:
						if finish_step:
							length_step = finish_step + 1
						elif max_step:
							length_step = max_step + 1
						else:
							length_step = 99
						self.append("configurator_options", {
							"option_type": "Length",
							"option_label": "Length",
							"option_step": length_step,
							"allowed_values_json": LENGTH_METADATA_JSON,
						})

				# ============================================================
				# PART 3: Custom Spec Child Table Enrichment
				# ============================================================
				self.custom_spec_custom = [
					row for row in (self.custom_spec_custom or [])
					if row.spec_label not in MANAGED_LABELS
				]
				
				if self.product_type == "Fixture Template":
					offering_rows = template_doc.get("allowed_tape_offerings") or []
					debug["offering_rows_checked"] = len(offering_rows)

					offerings = []
					for t_row in offering_rows:
						offering_name = t_row.get("tape_offering")
						if not offering_name:
							continue
						data = frappe.db.get_value(
							"ilL-Rel-Tape Offering", offering_name,
							["cri", "output_level", "cct", "tape_spec"], as_dict=True,
						)
						if data:
							offerings.append(data)
							
					voltage_values = set()
					for o in offerings:
						tape_spec_name = o.get("tape_spec")
						if not tape_spec_name:
							continue
						input_voltage = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec_name, "input_voltage")
						if input_voltage:
							voltage_values.add(str(input_voltage))
					if voltage_values:
						append_spec(self, "Electrical", "Input Voltage", ", ".join(sorted(voltage_values)), "", 90, "ilL-Attribute-Output Voltage")
						record(debug, "Input Voltage", len(voltage_values), sorted(voltage_values), appended=True)
					else:
						record(debug, "Input Voltage", 0, skip_reason="No input_voltage values resolved from allowed_tape_offerings")
							
					temp_values = set()
					for o in offerings:
						tape_spec_name = o.get("tape_spec")
						if not tape_spec_name:
							continue
						op_temp = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec_name, "operating_temp")
						if op_temp:
							temp_values.add(str(op_temp).strip())
					if temp_values:
						append_spec(self, "Environmental", "Operating Temperature", ", ".join(sorted(temp_values)), "", 120)
						record(debug, "Operating Temperature", len(temp_values), sorted(temp_values), appended=True)
					else:
						record(debug, "Operating Temperature", 0, skip_reason="No operating_temp values resolved from allowed_tape_offerings")

					cri_values = set()
					for o in offerings:
						if o.get("cri"):
							cri_values.add(str(o["cri"]))
					if cri_values:
						append_spec(self, "Optical", "Color Rendering (CRI)", ", ".join(sorted(cri_values)), "CRI", 50)
						record(debug, "Color Rendering (CRI)", len(cri_values), sorted(cri_values), appended=True)
					else:
						record(debug, "Color Rendering (CRI)", 0, skip_reason="No CRI values resolved")

					seen_output = set()
					output_pairs = []
					for o in offerings:
						ol_name = o.get("output_level")
						if ol_name and ol_name not in seen_output:
							seen_output.add(ol_name)
							ol_data = frappe.db.get_value(
								"ilL-Attribute-Output Level", ol_name,
								["output_level_name", "sku_code"], as_dict=True,
							)
							if ol_data and ol_data.get("sku_code"):
								output_pairs.append((ol_data["sku_code"], ol_data.get("output_level_name") or ol_name))
					if output_pairs:
						options = [{"attribute_type": "Output Level", "attribute_doctype": "ilL-Attribute-Output Level", "code": pair[0], "display_label": pair[1]} for pair in output_pairs]
						append_spec(self, "Performance", "Output Options", ", ".join(pair[1] for pair in output_pairs), "lm/ft", 10, "ilL-Attribute-Output Level", options)
						record(debug, "Output Options", len(output_pairs), [pair[1] for pair in output_pairs], appended=True)
					else:
						record(debug, "Output Options", 0, skip_reason="No output_level values resolved")

					cct_pairs = []
					seen_cct = set()
					for o in offerings:
						if o.get("cct") and o["cct"] not in seen_cct:
							seen_cct.add(o["cct"])
							cct_data = frappe.db.get_value("ilL-Attribute-CCT", o["cct"], ["cct_name", "code"], as_dict=True)
							if cct_data:
								cct_pairs.append((cct_data.get("code") or "", cct_data.get("cct_name") or o["cct"]))
					if cct_pairs:
						options = [{"attribute_type": "CCT", "attribute_doctype": "ilL-Attribute-CCT", "code": pair[0], "display_label": pair[1]} for pair in cct_pairs]
						append_spec(self, "Optical", "Light Color (CCT)", ", ".join(pair[1] for pair in cct_pairs), "", 40, "ilL-Attribute-CCT", options)
						record(debug, "Light Color (CCT)", len(cct_pairs), [pair[1] for pair in cct_pairs], appended=True)
					else:
						record(debug, "Light Color (CCT)", 0, skip_reason="No CCT values resolved")

					wpf_values = set()
					run_values = set()
					for o in offerings:
						tape_spec_name = o.get("tape_spec")
						if not tape_spec_name:
							continue
						spec_data = frappe.db.get_value(
							"ilL-Spec-LED Tape", tape_spec_name,
							["watts_per_foot", "voltage_drop_max_run_length_ft"],
							as_dict=True,
						)
						if not spec_data:
							continue
						if spec_data.get("watts_per_foot"):
							wpf_values.add(float(spec_data["watts_per_foot"]))
						if spec_data.get("voltage_drop_max_run_length_ft"):
							run_values.add(float(spec_data["voltage_drop_max_run_length_ft"]))

					if wpf_values:
						sorted_wpf = sorted(wpf_values)
						append_spec(self, "Electrical", "Watts per Foot", ", ".join(f"{v:g}" for v in sorted_wpf), "W/ft", 20)
						record(debug, "Watts per Foot", len(sorted_wpf), [f"{v:g}" for v in sorted_wpf], appended=True)
						
						calc_footage = sorted([ceil_val(80.0 / v) for v in wpf_values if v > 0], reverse=True)
						if calc_footage:
							append_spec(self, "Electrical", "Max Footage per 100W Supply", ", ".join(f"{v} ft" for v in calc_footage), "", 35)
							record(debug, "Max Footage per 100W Supply", len(calc_footage), [f"{v} ft" for v in calc_footage], appended=True)
					else:
						record(debug, "Watts per Foot", 0, skip_reason="No watts_per_foot values resolved")
						record(debug, "Max Footage per 100W Supply", 0, skip_reason="No watts_per_foot values resolved for footage calculation")

					if run_values:
						sorted_run = sorted(run_values, reverse=True)
						append_spec(self, "Electrical", "Max Run Length", ", ".join(f"{v:g} ft" for v in sorted_run), "", 30)
						record(debug, "Max Run Length", len(sorted_run), [f"{v:g} ft" for v in sorted_run], appended=True)
					else:
						record(debug, "Max Run Length", 0, skip_reason="No max_run_length values resolved")

					cut_increments = set()
					for o in offerings:
						tape_spec_name = o.get("tape_spec")
						if not tape_spec_name:
							continue
						cut_mm = frappe.db.get_value("ilL-Spec-LED Tape", tape_spec_name, "cut_increment_mm")
						if cut_mm:
							formatted = format_inches(cut_mm)
							if formatted:
								cut_increments.add(formatted)
					if cut_increments:
						append_spec(self, "Physical", "Production Interval", ", ".join(sorted(cut_increments)), "", 110)
						record(debug, "Production Interval", len(cut_increments), sorted(cut_increments), appended=True)
					else:
						record(debug, "Production Interval", 0, skip_reason="No cut_increment_mm values resolved")

					lens_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Lens Appearance" and o_row.get("lens_appearance"):
							lens_values.add(o_row.get("lens_appearance"))
					if lens_values:
						append_spec(self, "Optical", "Lens Options", ", ".join(sorted(lens_values)), "", 60, "ilL-Attribute-Lens Appearance")
						record(debug, "Lens Options", len(lens_values), sorted(lens_values), appended=True)
					else:
						record(debug, "Lens Options", 0, skip_reason="No active 'Lens Appearance' rows in allowed_options")

					mount_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Mounting Method" and o_row.get("mounting_method"):
							mount_values.add(o_row.get("mounting_method"))
					if mount_values:
						append_spec(self, "Physical", "Mounting Options", ", ".join(sorted(mount_values)), "", 70, "ilL-Attribute-Mounting Method")
						record(debug, "Mounting Options", len(mount_values), sorted(mount_values), appended=True)
					else:
						record(debug, "Mounting Options", 0, skip_reason="No active 'Mounting Method' rows in allowed_options")

					finish_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Finish" and o_row.get("finish"):
							disp = frappe.db.get_value("ilL-Attribute-Finish", o_row.get("finish"), "finish_name") or o_row.get("finish")
							finish_values.add(disp)
					if finish_values:
						append_spec(self, "Physical", "Finish Options", ", ".join(sorted(finish_values)), "", 80, "ilL-Attribute-Finish")
						record(debug, "Finish Options", len(finish_values), sorted(finish_values), appended=True)
					else:
						record(debug, "Finish Options", 0, skip_reason="No active 'Finish' rows in allowed_options")

					profile_spec_name = template_doc.get("default_profile_spec")
					if profile_spec_name:
						profile = frappe.db.get_value(
							"ilL-Spec-Profile", profile_spec_name,
							["dimensions", "width_mm", "height_mm"], as_dict=True,
						)
						dims = profile.get("dimensions") if profile else None
						if not dims and profile and profile.get("width_mm") and profile.get("height_mm"):
							w_in = format_inches(profile["width_mm"])
							h_in = format_inches(profile["height_mm"])
							if w_in and h_in:
								dims = f"{w_in} ({profile['width_mm']:g}mm) x {h_in} ({profile['height_mm']:g}mm)"
						if dims:
							append_spec(self, "Physical", "Dimensions", dims, "", 95)
							record(debug, "Dimensions", 1, [dims], appended=True)
						else:
							record(debug, "Dimensions", 0, skip_reason="Profile has no dimensions/width_mm/height_mm")
					else:
						record(debug, "Dimensions", 0, skip_reason="Template has no default_profile_spec")
						
					dimming_values = set()
					for o in offerings:
						tape_spec_name = o.get("tape_spec")
						if not tape_spec_name:
							continue
						tape_doc = frappe.get_doc("ilL-Spec-LED Tape", tape_spec_name)
						for row in (tape_doc.get("supported_dimming_protocols") or []):
							protocol_name = row.get("protocol")
							if not protocol_name:
								continue
							label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", protocol_name, "label")
							dimming_values.add(label or protocol_name)
					if dimming_values:
						append_spec(self, "Control", "Dimming", ", ".join(sorted(dimming_values)), "", 100, "ilL-Attribute-Dimming Protocol")
						record(debug, "Dimming", len(dimming_values), sorted(dimming_values), appended=True)
					else:
						record(debug, "Dimming", 0, skip_reason="No dimming protocols resolved")
				 
				elif self.product_type in ("LED Tape", "COB Tape", "LED Neon"):
					
					tape_rows = template_doc.get("allowed_tape_specs") or []
					debug["tape_rows_checked"] = len(tape_rows)
					
					tape_specs = []
					for r in tape_rows:
						ts = r.get("tape_spec")
						if ts:
							tape_specs.append(ts)

					seen_output = set()
					output_pairs = []
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Output Level" and o_row.get("output_level"):
							ol_name = o_row.get("output_level")
							if ol_name not in seen_output:
								seen_output.add(ol_name)
								ol_data = frappe.db.get_value(
									"ilL-Attribute-Output Level", ol_name,
									["output_level_name", "sku_code"], as_dict=True,
								)
								if ol_data and ol_data.get("sku_code"):
									output_pairs.append((ol_data["sku_code"], ol_data.get("output_level_name") or ol_name))
					if output_pairs:
						options = [{"attribute_type": "Output Level", "attribute_doctype": "ilL-Attribute-Output Level", "code": pair[0], "display_label": pair[1]} for pair in output_pairs]
						append_spec(self, "Performance", "Output Options", ", ".join(pair[1] for pair in output_pairs), "lm/ft", 10, "ilL-Attribute-Output Level", options)
						record(debug, "Output Options", len(output_pairs), [pair[1] for pair in output_pairs], appended=True)
					else:
						record(debug, "Output Options", 0, skip_reason="No output_level values resolved")
						
					wpf_values = set()
					run_values = set()
					
					for ts in tape_specs:
						spec_data = frappe.db.get_value(
							"ilL-Spec-LED Tape", ts,
							["watts_per_foot", "voltage_drop_max_run_length_ft"],
							as_dict=True,
						)
						if spec_data:
							if spec_data.get("watts_per_foot"):
								wpf_values.add(float(spec_data["watts_per_foot"]))
							if spec_data.get("voltage_drop_max_run_length_ft"):
								run_values.add(float(spec_data["voltage_drop_max_run_length_ft"]))
					
					if wpf_values:
						sorted_wpf = sorted(wpf_values)
						append_spec(self, "Electrical", "Watts per Foot", ", ".join(f"{v:g}" for v in sorted_wpf), "W/ft", 20)
						record(debug, "Watts per Foot", len(sorted_wpf), [f"{v:g}" for v in sorted_wpf], appended=True)
						
						calc_footage = sorted([ceil_val(80.0 / v) for v in wpf_values if v > 0], reverse=True)
						if calc_footage:
							append_spec(self, "Electrical", "Max Footage per 100W Supply", ", ".join(f"{v} ft" for v in calc_footage), "", 40)
							record(debug, "Max Footage per 100W Supply", len(calc_footage), [f"{v} ft" for v in calc_footage], appended=True)
					else:
						record(debug, "Watts per Foot", 0, skip_reason="No watts_per_foot values resolved")
						record(debug, "Max Footage per 100W Supply", 0, skip_reason="No watts_per_foot values resolved for footage calculation")
						
					if run_values:
						sorted_run = sorted(run_values, reverse=True)
						append_spec(self, "Electrical", "Max Run Length", ", ".join(f"{v:g} ft" for v in sorted_run), "", 30)
						record(debug, "Max Run Length", len(sorted_run), [f"{v:g} ft" for v in sorted_run], appended=True)
					else:
						record(debug, "Max Run Length", 0, skip_reason="No voltage_drop_max_run_length_ft values resolved")

					cct_pairs = []
					seen_cct = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "CCT" and o_row.get("cct"):
							cct_val = o_row.get("cct")
							if cct_val not in seen_cct:
								seen_cct.add(cct_val)
								cct_data = frappe.db.get_value("ilL-Attribute-CCT", cct_val, ["cct_name", "code"], as_dict=True)
								if cct_data:
									cct_pairs.append((cct_data.get("code") or "", cct_data.get("cct_name") or cct_val))
					if cct_pairs:
						options = [{"attribute_type": "CCT", "attribute_doctype": "ilL-Attribute-CCT", "code": pair[0], "display_label": pair[1]} for pair in cct_pairs]
						append_spec(self, "Optical", "Light Color (CCT)", ", ".join(pair[1] for pair in cct_pairs), "", 50, "ilL-Attribute-CCT", options)
						record(debug, "Light Color (CCT)", len(cct_pairs), [pair[1] for pair in cct_pairs], appended=True)
					else:
						record(debug, "Light Color (CCT)", 0, skip_reason="No CCT values resolved")

					cri_values = set()
					for ts in tape_specs:
						cri = frappe.db.get_value("ilL-Spec-LED Tape", ts, "cri_typical")
						if cri: cri_values.add(str(cri))
					if cri_values:
						append_spec(self, "Optical", "Color Rendering (CRI)", ", ".join(sorted(cri_values)), "CRI", 60)
						record(debug, "Color Rendering (CRI)", len(cri_values), sorted(cri_values), appended=True)
					else:
						record(debug, "Color Rendering (CRI)", 0, skip_reason="No cri_typical values resolved")

					beam_angle = template_doc.get("beam_angle")
					if beam_angle:
						try:
							ba_int = int(float(beam_angle))
							append_spec(self, "Optical", "Beam Spread", f"{ba_int}°", "", 70)
							record(debug, "Beam Spread", 1, [f"{ba_int}°"], appended=True)
						except (ValueError, TypeError):
							record(debug, "Beam Spread", 0, skip_reason="Invalid beam_angle format")
					else:
						record(debug, "Beam Spread", 0, skip_reason="Template has no beam_angle")

					mount_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Mounting Method" and o_row.get("mounting_method"):
							mount_values.add(o_row.get("mounting_method"))
					if mount_values:
						append_spec(self, "Physical", "Mounting Options", ", ".join(sorted(mount_values)), "", 80, "ilL-Attribute-Mounting Method")
						record(debug, "Mounting Options", len(mount_values), sorted(mount_values), appended=True)
					else:
						record(debug, "Mounting Options", 0, skip_reason="No Mounting Method values resolved")

					finish_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Finish" and o_row.get("finish"):
							disp = frappe.db.get_value("ilL-Attribute-Finish", o_row.get("finish"), "finish_name") or o_row.get("finish")
							finish_values.add(disp)
					if finish_values:
						append_spec(self, "Physical", "Finish Options", ", ".join(sorted(finish_values)), "", 90, "ilL-Attribute-Finish")
						record(debug, "Finish Options", len(finish_values), sorted(finish_values), appended=True)
					else:
						record(debug, "Finish Options", 0, skip_reason="No Finish values resolved")

					voltage_values = set()
					for ts in tape_specs:
						iv = frappe.db.get_value("ilL-Spec-LED Tape", ts, "input_voltage")
						if iv: voltage_values.add(str(iv))
					if voltage_values:
						append_spec(self, "Electrical", "Input Voltage", ", ".join(sorted(voltage_values)), "", 100, "ilL-Attribute-Output Voltage")
						record(debug, "Input Voltage", len(voltage_values), sorted(voltage_values), appended=True)
					else:
						record(debug, "Input Voltage", 0, skip_reason="No input_voltage values resolved")

					dimming_values = set()
					for ts in tape_specs:
						tape_doc = frappe.get_doc("ilL-Spec-LED Tape", ts)
						
						ip = tape_doc.get("input_protocol")
						if ip:
							label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", ip, "label")
							dimming_values.add(label or ip)
						
						for row in (tape_doc.get("supported_dimming_protocols") or []):
							protocol_name = row.get("protocol")
							if protocol_name:
								label = frappe.db.get_value("ilL-Attribute-Dimming Protocol", protocol_name, "label")
								dimming_values.add(label or protocol_name)
					if dimming_values:
						append_spec(self, "Control", "Dimming", ", ".join(sorted(dimming_values)), "", 110, "ilL-Attribute-Dimming Protocol")
						record(debug, "Dimming", len(dimming_values), sorted(dimming_values), appended=True)
					else:
						record(debug, "Dimming", 0, skip_reason="No dimming protocols resolved")

					dimensions = template_doc.get("spec_sheet_dimensions")
					if dimensions:
						append_spec(self, "Physical", "Dimensions", dimensions, "", 120)
						record(debug, "Dimensions", 1, [dimensions], appended=True)
					else:
						record(debug, "Dimensions", 0, skip_reason="Template has no spec_sheet_dimensions")

					side_mm = template_doc.get("minimum_side_bend_diameter_mm")
					top_mm = template_doc.get("minimum_top_bend_diameter_mm")
					bend_parts = []
					
					if side_mm:
						side_in = float(side_mm) / 25.4
						bend_parts.append(f'Side Bend: {side_in:.2f}" ({float(side_mm):g}mm)')
					if top_mm:
						top_in = float(top_mm) / 25.4
						bend_parts.append(f'Top Bend: {top_in:.2f}" ({float(top_mm):g}mm)')
						
					if bend_parts:
						val = ", ".join(bend_parts)
						append_spec(self, "Physical", "Minimum Bending Diameter", val, "", 125)
						record(debug, "Minimum Bending Diameter", len(bend_parts), [val], appended=True)
					else:
						record(debug, "Minimum Bending Diameter", 0, skip_reason="Template has no side/top bend values")

					is_free_cutting = template_doc.get("is_free_cutting")
					template_pi = template_doc.get("production_interval_mm")
					cut_increments = set()
					
					def format_pi(mm_val):
						inches = float(mm_val) / 25.4
						return f'{inches:.2f}" ({float(mm_val):.1f}mm)'
						
					if is_free_cutting and not template_pi:
						cut_increments.add("Free Cutting")
					elif template_pi:
						cut_increments.add(format_pi(template_pi))
					else:
						for ts in tape_specs:
							cut_mm = frappe.db.get_value("ilL-Spec-LED Tape", ts, "cut_increment_mm")
							if is_free_cutting and not cut_mm:
								cut_increments.add("Free Cutting")
							elif cut_mm:
								cut_increments.add(format_pi(cut_mm))
					if cut_increments:
						append_spec(self, "Physical", "Production Interval", ", ".join(sorted(cut_increments)), "", 130)
						record(debug, "Production Interval", len(cut_increments), sorted(cut_increments), appended=True)
					else:
						record(debug, "Production Interval", 0, skip_reason="No cut increments resolved")

					temp_values = set()
					for ts in tape_specs:
						op_temp = frappe.db.get_value("ilL-Spec-LED Tape", ts, "operating_temp")
						if op_temp: temp_values.add(str(op_temp).strip())
					if temp_values:
						append_spec(self, "Environmental", "Operating Temperature", ", ".join(sorted(temp_values)), "", 140)
						record(debug, "Operating Temperature", len(temp_values), sorted(temp_values), appended=True)
					else:
						record(debug, "Operating Temperature", 0, skip_reason="No operating_temp values resolved")

					warranty = template_doc.get("warranty_years")
					if warranty:
						append_spec(self, "Performance", "Warranty", f"{warranty} years", "", 150)
						record(debug, "Warranty", 1, [f"{warranty} years"], appended=True)
					else:
						record(debug, "Warranty", 0, skip_reason="Template has no warranty_years")
  
				elif self.product_type == "LED Sheet":
					
					sheet_rows = template_doc.get("allowed_specs") or []
					debug["sheet_rows_checked"] = len(sheet_rows)
					
					sheet_specs = []
					for r in sheet_rows:
						s = r.get("spec")
						if s: sheet_specs.append(s)
						
					seen_output = set()
					output_pairs = []
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Output Level":
							ol_name = o_row.get("attribute_link") or o_row.get("output_level")
							if ol_name and ol_name not in seen_output:
								seen_output.add(ol_name)
								ol_data = frappe.db.get_value("ilL-Attribute-Output Level", ol_name, ["output_level_name", "sku_code"], as_dict=True)
								if ol_data and ol_data.get("sku_code"):
									output_pairs.append((ol_data["sku_code"], ol_data.get("output_level_name") or ol_name))
					if output_pairs:
						options = [{"attribute_type": "Output Level", "attribute_doctype": "ilL-Attribute-Output Level", "code": pair[0], "display_label": pair[1]} for pair in output_pairs]
						append_spec(self, "Performance", "Output Options", ", ".join(pair[1] for pair in output_pairs), "lm/ft", 10, "ilL-Attribute-Output Level", options)

					wps_values = set()
					for s in sheet_specs:
						wps = frappe.db.get_value("ilL-Spec-LED-Sheet", s, "watts_per_sqft")
						if wps: wps_values.add(float(wps))
					if wps_values:
						sorted_wps = sorted(wps_values)
						append_spec(self, "Electrical", "Watts per Square Foot", ", ".join(f"{v:g}" for v in sorted_wps), "W/sqft", 20)

						calc_footage = sorted([ceil_val(80.0 / v) for v in wps_values if v > 0], reverse=True)
						if calc_footage:
							append_spec(self, "Electrical", "Max Footage per 100W Supply", ", ".join(f"{v} sqft" for v in calc_footage), "", 35)

					cct_pairs = []
					seen_cct = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "CCT":
							cct_val = o_row.get("attribute_link") or o_row.get("cct")
							if cct_val and cct_val not in seen_cct:
								seen_cct.add(cct_val)
								cct_data = frappe.db.get_value("ilL-Attribute-CCT", cct_val, ["cct_name", "code"], as_dict=True)
								if cct_data:
									cct_pairs.append((cct_data.get("code") or "", cct_data.get("cct_name") or cct_val))
					if cct_pairs:
						options = [{"attribute_type": "CCT", "attribute_doctype": "ilL-Attribute-CCT", "code": pair[0], "display_label": pair[1]} for pair in cct_pairs]
						append_spec(self, "Optical", "Light Color (CCT)", ", ".join(pair[1] for pair in cct_pairs), "", 40, "ilL-Attribute-CCT", options)

					cri_values = set()
					for s in sheet_specs:
						cri = frappe.db.get_value("ilL-Spec-LED-Sheet", s, "cri")
						if cri: cri_values.add(str(cri))
					if cri_values:
						append_spec(self, "Optical", "Color Rendering (CRI)", ", ".join(sorted(cri_values)), "CRI", 50)

					beam_angle = template_doc.get("beam_angle")
					if beam_angle:
						try:
							ba_int = int(float(beam_angle))
							append_spec(self, "Optical", "Beam Spread", f"{ba_int}°", "", 65)
						except (ValueError, TypeError):
							pass

					mount_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Mounting Method":
							mv = o_row.get("attribute_link") or o_row.get("mounting_method")
							if mv: mount_values.add(mv)
					if mount_values:
						append_spec(self, "Physical", "Mounting", ", ".join(sorted(mount_values)), "", 70, "ilL-Attribute-Mounting Method")

					finish_values = set()
					for o_row in (template_doc.get("allowed_options") or []):
						if o_row.get("option_type") == "Finish":
							fv = o_row.get("attribute_link") or o_row.get("finish")
							if fv:
								disp = frappe.db.get_value("ilL-Attribute-Finish", fv, "finish_name") or fv
								finish_values.add(disp)
					if finish_values:
						append_spec(self, "Physical", "Finish", ", ".join(sorted(finish_values)), "", 80, "ilL-Attribute-Finish")

					voltage_values = set()
					for s in sheet_specs:
						iv = frappe.db.get_value("ilL-Spec-LED-Sheet", s, "input_voltage")
						if iv: voltage_values.add(str(iv))
					if voltage_values:
						append_spec(self, "Electrical", "Input Voltage", ", ".join(sorted(voltage_values)), "", 90, "ilL-Attribute-Output Voltage")

					append_spec(self, "Control", "Dimming", "TBD", "", 100)

					dims_list = set()
					for s in sheet_specs:
						spec_data = frappe.db.get_value("ilL-Spec-LED-Sheet", s, ["sheet_width_ft", "sheet_height_ft"], as_dict=True)
						if spec_data and spec_data.get("sheet_width_ft") and spec_data.get("sheet_height_ft"):
							w_ft = float(spec_data["sheet_width_ft"])
							h_ft = float(spec_data["sheet_height_ft"])
							w_in = w_ft * 12
							h_in = h_ft * 12
							w_mm = w_ft * 304.8
							h_mm = h_ft * 304.8
							dims_list.add(f'{w_in:.2f}" ({w_mm:.1f}mm) × {h_in:.2f}" ({h_mm:.1f}mm)')
					if dims_list:
						append_spec(self, "Physical", "Dimensions (ft)", ", ".join(sorted(dims_list)), "", 95)

					cut_list = set()
					for s in sheet_specs:
						spec_data = frappe.db.get_value("ilL-Spec-LED-Sheet", s, ["cut_interval_width_in", "cut_interval_height_in"], as_dict=True)
						if spec_data and spec_data.get("cut_interval_width_in") and spec_data.get("cut_interval_height_in"):
							w_in = float(spec_data["cut_interval_width_in"])
							h_in = float(spec_data["cut_interval_height_in"])
							w_mm = w_in * 25.4
							h_mm = h_in * 25.4
							cut_list.add(f'{w_in:.2f}" ({w_mm:.1f}mm) × {h_in:.2f}" ({h_mm:.1f}mm)')
					if cut_list:
						append_spec(self, "Physical", "Cut Interval", ", ".join(sorted(cut_list)), "", 105)

					temp_list = set()
					for s in sheet_specs:
						spec_data = frappe.db.get_value("ilL-Spec-LED-Sheet", s, ["operating_temp_min_c", "operating_temp_max_c"], as_dict=True)
						if spec_data and spec_data.get("operating_temp_min_c") not in (None, "") and spec_data.get("operating_temp_max_c") not in (None, ""):
							min_c = float(spec_data["operating_temp_min_c"])
							max_c = float(spec_data["operating_temp_max_c"])
							min_f = round(min_c * 9/5 + 32)
							max_f = round(max_c * 9/5 + 32)
							temp_list.add(f"{min_f}°F ({int(min_c)}°C) to {max_f}°F ({int(max_c)}°C)")
					if temp_list:
						append_spec(self, "Environmental", "Operating Temperature", ", ".join(sorted(temp_list)), "", 120)

					warranty = template_doc.get("warranty_years")
					if warranty:
						append_spec(self, "Performance", "Warranty", f"{warranty} years", "", 130)
 
				elif self.product_type == "Driver":
					
					variants = frappe.get_all(
						"ilL-Child-Driver-Template-Variant",
						filters={
							"parent": template_doc.name,
							"parenttype": "ilL-Driver-Template",
							"is_active": 1
						},
						fields=["driver_spec"]
					)
					
					spec_names = []
					for v in variants:
						if v.get("driver_spec"):
							spec_names.append(v.get("driver_spec"))
							
					iv_list = set()
					pf_list = set()
					eff_list = set()
					dims_list = set()
					inrush_list = set()
					max_input_list = set()
					out_v_list = set()
					dimming_list = set()
					
					for s in spec_names:
						d_spec = frappe.get_doc("ilL-Spec-Driver", s)
						
						v_min = d_spec.get("input_voltage_min")
						v_max = d_spec.get("input_voltage_max")
						v_type = d_spec.get("input_voltage_type")
						if v_min and v_max and v_type:
							iv_list.add(f"{v_min} - {v_max} {v_type}")
							
						pf = d_spec.get("power_factor")
						if pf:
							pf_list.add(str(pf))
							
						eff = d_spec.get("efficiency")
						if eff:
							eff_list.add(str(eff))
							
						w_mm = d_spec.get("width_mm")
						h_mm = d_spec.get("height_mm")
						d_mm = d_spec.get("depth_mm")
						if w_mm and h_mm and d_mm:
							w_in = format_inches(w_mm)
							h_in = format_inches(h_mm)
							d_in = format_inches(d_mm)
							dims_list.add(f'{w_in} ({w_mm}mm) × {h_in} ({h_mm}mm) × {d_in} ({d_mm}mm)')
							
						inrush = d_spec.get("inrush_aA") or d_spec.get("inrush_aa") or d_spec.get("inrush_a")
						if inrush:
							inrush_list.add(f"{inrush}A")
							
						max_in = d_spec.get("max_input_aA") or d_spec.get("max_input_aa") or d_spec.get("max_input_a")
						if max_in:
							max_input_list.add(f"{max_in}A")
							
						out_v = d_spec.get("voltage_output")
						if out_v:
							out_v_list.add(str(out_v))
							
						for p in (d_spec.get("input_protocols") or []):
							proto = p.get("protocol")
							if proto:
								lbl = frappe.db.get_value("ilL-Attribute-Dimming Protocol", proto, "label")
								dimming_list.add(lbl or proto)
								
					if iv_list: 
						append_spec(self, "Electrical", "Input Voltage", ", ".join(sorted(iv_list)), "", 10)
					if pf_list: 
						append_spec(self, "Electrical", "Power Factor", ", ".join(sorted(pf_list)), "", 20)
						
					append_spec(self, "Electrical", "Total Harmonic Distortion", "TBD", "", 30)
					
					if eff_list: 
						append_spec(self, "Electrical", "Efficiency", ", ".join(sorted(eff_list)), "", 40)
						
					append_spec(self, "Electrical", "Start Up Time", "TBD", "", 50)
					append_spec(self, "Electrical", "Minimum Load", "TBD", "", 60)
					
					if dims_list: 
						append_spec(self, "Physical", "Dimensions", ", ".join(sorted(dims_list)), "", 70)
					if inrush_list: 
						append_spec(self, "Electrical", "Inrush Current", ", ".join(sorted(inrush_list)), "", 80)
					if max_input_list: 
						append_spec(self, "Electrical", "Max Input Current", ", ".join(sorted(max_input_list)), "", 90)
					if out_v_list: 
						append_spec(self, "Electrical", "Output Voltage", ", ".join(sorted(out_v_list)), "", 100)
						
					append_spec(self, "Electrical", "Max Output Current", "TBD", "", 110)
					
					if dimming_list: 
						append_spec(self, "Control", "Dimming", ", ".join(sorted(dimming_list)), "", 120, "ilL-Attribute-Dimming Protocol")
						
					append_spec(self, "Compliance", "Certifications", "TBD", "", 130)
					append_spec(self, "Environmental", "Operating Temperature", "TBD", "", 140)
					
					warranty = template_doc.get("warranty_years") or template_doc.get("warranty")
					if warranty:
						append_spec(self, "Performance", "Warranty", f"{warranty} years", "", 150)

				else:
					for label in MANAGED_LABELS:
						record(debug, label, skip_reason=f"Not yet implemented for product_type '{self.product_type}'")

		# --- Sort all rows by display_order ---
		if self.custom_spec_custom:
			# 1. Sort the list
			self.custom_spec_custom.sort(
				key=lambda row: int(row.get("display_order")) if row.get("display_order") not in (None, "") else 999
			)
			
			# 2. Re-assign idx so ERPNext saves and renders them in the new sorted order
			row_idx = 1
			for row in self.custom_spec_custom:
				row.idx = row_idx
				row_idx += 1
			
		debug["existing_labels_after"] = [row.spec_label for row in (self.custom_spec_custom or [])]

		frappe.log_error(
			title=f"Combined Full Enrichment Debug: {self.name}",
			message=json.dumps(debug, indent=2, default=str),
		)
