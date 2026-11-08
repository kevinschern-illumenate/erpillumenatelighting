# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api.configuration_contract import (
	TAPE_NEON_CATEGORIES,
)
from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
	format_length_inches,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_spec_profile.ill_spec_profile import (
	compute_profile_dimensions,
)
from illumenate_lighting.illumenate_lighting.template_calculations import (
	MANAGED_LABELS,
	TemplateCalculator,
)
from illumenate_lighting.illumenate_lighting.web_listing_schema import (
	WEBFLOW_PRODUCT_LINKS,
)

# Specification labels sync_custom_template_data rebuilds on every save (MANAGED_LABELS),
# the environment rating order and the attribute code lookup live in template_calculations.


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
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_web_feature.ill_child_web_feature import (
			ilLChildWebFeature,
		)

		accessory_spec: DF.Link | None
		attribute_links: DF.Table[ilLChildWebflowAttributeLink]
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
		web_features: DF.Table[ilLChildWebFeature]
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
		product_badge: DF.Literal["", "New", "On Sale", "Quick Ship", "Hide"] | None
		is_discontinued: DF.Check
		product_category: DF.Link | None
		product_name: DF.Data
		product_slug: DF.Data
		portal_item: DF.Link | None
		product_type: DF.Literal["Fixture Template", "Driver", "Controller", "Extrusion Kit", "LED Tape", "COB Tape", "LED Neon", "Component", "Accessory", "LED Sheet"]
		profile_spec: DF.Link | None
		series_family_image: DF.AttachImage | None
		short_description: DF.SmallText | None
		sublabel: DF.Data | None
		sync_error_message: DF.SmallText | None
		sync_status: DF.Literal["Pending", "Synced", "Error", "Never Synced"]
		tape_neon_template: DF.Link | None
		tape_spec: DF.Link | None
		warranty_years: DF.Int
		webflow_collection_slug: DF.Data | None
		webflow_item_id: DF.Data | None
	# end: auto-generated types

	def populate_certification_badges(self):
		"""Populate the webflow_badge_images JSON field based on active Target Brands."""
		# Badge fields on ilL-Attribute-Certification (app fields since 2026-11-03); skip any
		# that are absent on a site that has not migrated yet.
		cert_meta = frappe.get_meta("ilL-Attribute-Certification")
		badge_fields = [
			f for f in ("badge_image", "badge_image_dark", "badge_image_light_206", "badge_image_dark_206")
			if cert_meta.has_field(f)
		]

		active_brands = [row.brand for row in self.get("target_brands", []) if row.enabled]
		if not active_brands:
			active_brands = ["lighting_206", "illumenate"]  # Fallback if none selected

		# This site's own address (Phase 7): staging no longer points at production files.
		base_url = frappe.utils.get_url()

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
				badge_data["illumenate_badge_dark"] = make_url(cert_doc.get("badge_image_dark"))

			if "lighting_206" in active_brands:
				badge_data["206_badge_light"] = make_url(cert_doc.get("badge_image_light_206"))
				badge_data["206_badge_dark"] = make_url(cert_doc.get("badge_image_dark_206"))

			# Save as JSON array with a single object inside, matching your request
			row.webflow_badge_images = frappe.as_json([badge_data])
	
	def validate(self):
		# The template owns the link (plan 4.2); the per-type link fields here are mirrors.
		from illumenate_lighting.illumenate_lighting.template_link import validate_product_links

		validate_product_links(self)
	
	def onload(self):
		pass
		
	def before_save(self):
		"""Calculate specifications, attribute links, and configurator options before saving."""
		self.set_dynamic_hero_image()

		# Duplicate guard: clear inherited Webflow sync identity/state
		if getattr(self.flags, "in_copy", False) or self.is_new():
			self.webflow_item_id = None
			self.webflow_collection_slug = None
			self.last_synced_at = None
			self.sync_error_message = None
			self.sync_status = "Never Synced"
			if hasattr(self, "sync_targets"):
				self.set("sync_targets", [])

		# Attribute Links always mirror the template (owner, 2026-11-05).
		self.populate_attribute_links()

		# V2 Custom Specification Sync
		self.sync_custom_template_data()
		self.populate_certification_badges()

		# Owner changes 2026-11-05 (plan 4.17): features from web_features, power supplies as
		# calculated Recommended With rows, and 16:9 warnings.
		from illumenate_lighting.illumenate_lighting import webflow_product_rules

		webflow_product_rules.write_features(self)
		webflow_product_rules.recommend_power_supplies(self)
		webflow_product_rules.warn_aspect_ratios(self)

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

		if self.is_configurable and self.kit_template:
			if self.get("auto_populate_configurator_options", True):
				self.populate_extrusion_kit_configurator_options()

		# The linked template's stored specifications and configurator steps win (Phase 2, D21).
		from illumenate_lighting.illumenate_lighting.template_listing import apply_template_rows

		apply_template_rows(self)

		from illumenate_lighting.illumenate_lighting.webflow_state import set_is_discontinued

		set_is_discontinued(self)

		# Mark as pending sync if substantive changes were made
		# Skip this check if we're being saved from the sync API (sync_status is being set to Synced)
		if not getattr(self, "_skip_sync_status_check", False):
			if (
				self.has_value_changed("attribute_links")
				or self.has_value_changed("configurator_options")
			):
				if self.sync_status == "Synced":
					self.sync_status = "Pending"

	def after_insert(self):
		# A product created with a template link writes the template side (template_link.py).
		from illumenate_lighting.illumenate_lighting.template_link import on_product_insert

		on_product_insert(self)

	def on_update(self):
		"""Sync compatibilities and top up the linked template.

		The template owns the link (plan 4.2): template_link.py writes this product's
		per-type link field, so nothing here writes the template's webflow_product.
		"""
		# 1. Prevent infinite loops globally for this compatibility sync transaction
		if not self.flags.syncing_compatibility:
			# 2. Run deletions first, then additions
			self.handle_deletions()
			self.sync_compatible_products()

		self._top_up_template()

	def set_dynamic_hero_image(self):
		# 1. Define a list of all possible template link fields on the Product doctype
		template_fields = [
			"kit_template",
			"fixture_template",
			"tape_neon_template",
			"driver_template",
			"controller_template",
			"led_sheet_template"
		]

		# 2. Reset the image so it clears out if no template is linked
		self.hero_image = None

		# 3. Loop through the possible fields
		for fieldname in template_fields:
			template_name = self.get(fieldname)
			
			if template_name:
				# Get the DocType of the linked template (e.g., "ilL-Extrusion-Kit-Template")
				template_doctype = self.meta.get_field(fieldname).options
				
				# Fetch the hero_image from that specific template record
				hero_image_url = frappe.db.get_value(template_doctype, template_name, "hero_image")
				
				# If the template actually has an image, apply it to the product and stop searching
				if hero_image_url:
					self.hero_image = hero_image_url
					break
					
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
					rel_type_field: relationship,
					# A calculated power supply link is calculated on both sides (plan 4.17).
					"is_calculated": 1 if row.get("is_calculated") else 0,
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
		"""Add the template's certifications, in table order, as attribute links.

		Read from the template, not this product's (hidden) Certifications table (owner,
		2026-11-05).
		"""
		from illumenate_lighting.illumenate_lighting.webflow_product_rules import linked_template

		doctype, template = linked_template(self)
		if not doctype:
			return
		certifications = frappe.get_all(
			"ilL-Child-Spec-Certification",
			filters={"parenttype": doctype, "parent": template, "parentfield": "certifications"},
			pluck="certification",
			order_by="idx asc",
		)
		display_order = max((a.get("display_order", 0) for a in attribute_links), default=0)
		for cert_name in certifications:
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
		"""Kit attributes (owner, 2026-11-05): the default profile's Environment Ratings and
		Joiner System, the default lens's Lens Appearance, and the kit template's active Allowed
		Options: every Finish, Lens Appearance and Mounting Method. No Series and no Endcap Style."""

		def add(attribute_type, doctype, name):
			if not name or any(
				a["attribute_doctype"] == doctype and a["attribute_name"] == name for a in attribute_links
			):
				return
			attribute_links.append({
				"attribute_type": attribute_type,
				"attribute_doctype": doctype,
				"attribute_name": name,
				"display_label": name,
				"webflow_item_id": self._get_attribute_webflow_id(doctype, name),
				"display_order": len(attribute_links) + 1,
			})

		profile_spec, lens_spec = self._resolve_kit_specs()
		if profile_spec and frappe.db.exists("ilL-Spec-Profile", profile_spec):
			profile = frappe.get_doc("ilL-Spec-Profile", profile_spec)
			for env in getattr(profile, "supported_environment_ratings", None) or []:
				add("Environment Rating", "ilL-Attribute-Environment Rating", getattr(env, "environment_rating", None))
			add("Joiner System", "ilL-Attribute-Joiner System", profile.get("joiner_system"))
		if lens_spec and frappe.db.exists("ilL-Spec-Lens", lens_spec):
			add(
				"Lens Appearance",
				"ilL-Attribute-Lens Appearance",
				frappe.db.get_value("ilL-Spec-Lens", lens_spec, "lens_appearance"),
			)
		if self.kit_template:
			for option in frappe.get_all(
				"ilL-Child-Kit-Allowed-Option",
				filters={"parenttype": "ilL-Extrusion-Kit-Template", "parent": self.kit_template},
				fields=["option_type", "finish", "lens_appearance", "mounting_method", "is_active"],
				order_by="idx asc",
			):
				if option.get("is_active") == 0:
					continue
				if option.get("option_type") == "Finish":
					add("Finish", "ilL-Attribute-Finish", option.get("finish"))
				elif option.get("option_type") == "Lens Appearance":
					add("Lens Appearance", "ilL-Attribute-Lens Appearance", option.get("lens_appearance"))
				elif option.get("option_type") == "Mounting Method":
					add("Mounting Method", "ilL-Attribute-Mounting Method", option.get("mounting_method"))

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

	# ------------------------------------------------------------------
	# Configurator Options: calculated in template_calculations (plan 4.17, 4.18). The
	# wrappers keep this product's table filled exactly as before until it is removed.
	# ------------------------------------------------------------------

	def populate_configurator_options(self):
		"""Fixture Template steps (TemplateCalculator.populate_configurator_options)."""
		self._populate_calculated_configurator("populate_configurator_options")

	def populate_led_sheet_configurator_options(self):
		"""LED Sheet steps (TemplateCalculator.populate_led_sheet_configurator_options)."""
		self._populate_calculated_configurator("populate_led_sheet_configurator_options")

	def populate_driver_configurator_options(self):
		"""Driver steps (TemplateCalculator.populate_driver_configurator_options)."""
		self._populate_calculated_configurator("populate_driver_configurator_options")

	def populate_controller_configurator_options(self):
		"""Controller steps (TemplateCalculator.populate_controller_configurator_options)."""
		self._populate_calculated_configurator("populate_controller_configurator_options")

	def populate_extrusion_kit_configurator_options(self):
		"""Extrusion Kit steps (TemplateCalculator.populate_extrusion_kit_configurator_options)."""
		self._populate_calculated_configurator("populate_extrusion_kit_configurator_options")

	def populate_tape_neon_configurator_options(self):
		"""LED Tape / COB Tape / LED Neon steps
		(TemplateCalculator.populate_tape_neon_configurator_options)."""
		self._populate_calculated_configurator("populate_tape_neon_configurator_options")

	def _populate_calculated_configurator(self, method):
		"""Run one configurator calculation for this product and keep its steps in this
		product's Configurator Options. A calculation that stops early (an Extrusion Kit whose
		template is missing) leaves the table as it is, as it always did."""
		calculator = TemplateCalculator.for_product(self)
		getattr(calculator, method)()
		if calculator.configurator_options is not None:
			self.set("configurator_options", calculator.configurator_options)

	def _template_doc(self, doctype, name):
		"""The linked template. A temporary product (webflow_export_v2.export_template_record)
		is handed the template being exported, so the calculations see its unsaved values."""
		override = self.flags.template_doc
		if override is not None and override.doctype == doctype and override.name == name:
			return override
		return frappe.get_doc(doctype, name)

	def _get_existing_is_required(self) -> dict:
		"""Return {option_step: is_required} as currently stored in the database.

		Lets an admin uncheck "Is Required" on a step without the value being
		clobbered the next time options are auto-populated.
		"""
		# Choices handed in by the caller win (templates use their own rows: template_calculations).
		if self.flags.existing_is_required is not None:
			return self.flags.existing_is_required
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

		# MANAGED_LABELS (module level): labels this calculation rebuilds; other rows are kept.

		debug = {
			"product": self.name,
			"product_type": self.product_type,
			"existing_labels_before": [row.spec_label for row in (self.webflow_specifications or [])],
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
				template_doc = self._template_doc(mapping["doctype"], linked_doc_name)

				# ============================================================
				# PART 1: Core Field, Document, and Certification Sync
				# ============================================================
				
				self.webflow_template_status = template_doc.get("product_status")
				# Product Category mirrors the template's Webflow Category, and decides the
				# Product Type (owner, 2026-11-03).
				from illumenate_lighting.illumenate_lighting.web_listing_schema import (
					CATEGORY_PRODUCT_TYPES,
					template_category,
				)

				category = template_category(template_doc)
				if category:
					self.product_category = category
					if CATEGORY_PRODUCT_TYPES.get(category):
						self.product_type = CATEGORY_PRODUCT_TYPES[category]
				# Series mirrors the template's Series (both link to ilL-Attribute-Series).
				if template_doc.get("series"):
					self.series = template_doc.get("series")

				# --- Documents Sync ---
				existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}
				
				# The stable link when the template has one (D19), else the file itself.
				spec_sheet_file = template_doc.get("spec_sheet_public_url") or template_doc.get("spec_sheet")
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
						if not (d.document_type == "Spec Submittal" and d.document_title == submittal_title and d.document_file != spec_submittal_file)
					]
					existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}
					
					if spec_submittal_file in existing_docs:
						existing_docs[spec_submittal_file].document_type = "Spec Submittal"
						existing_docs[spec_submittal_file].document_title = submittal_title
						existing_docs[spec_submittal_file].display_order = 2
					else:
						self.append("documents", {
							"document_type": "Spec Submittal",
							"document_file": spec_submittal_file,
							"document_title": submittal_title,
							"display_order": 2,
						})
						existing_docs[spec_submittal_file] = self.documents[-1]
				else:
					self.documents = [d for d in (self.documents or []) if not (d.document_type == "Spec Submittal" and d.document_title == submittal_title)]
					existing_docs = {d.document_file: d for d in (self.documents or []) if d.document_file}

				# other_documents ships with the app; custom_documents was the site Custom Field
				# it replaced on the Tape/Neon template (patch move_tape_custom_documents_...).
				other_documents = template_doc.get("other_documents") or template_doc.get("custom_documents") or []
				for d in other_documents:
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
				# PART 3: Custom Spec Child Table Enrichment (template_calculations, plan 4.17)
				# ============================================================
				calculator = TemplateCalculator.for_product(self)
				calculator.calculate_specifications(template_doc, debug)
				self.set("webflow_specifications", calculator.webflow_specifications)

				if self.product_type == "Extrusion Kit":
					# Kit Components Grouping: this product's own table (plan 4.18 K3)
					grouped_components = {}
					grouped_images = {}
					
					for c_row in (template_doc.get("kit_components") or []):
						c_type = c_row.get("component_type")
						if not c_type:
							continue
						
						if c_type not in grouped_components:
							grouped_components[c_type] = []
							
						desc = c_row.get("component_description") or ""
						item_code = c_row.get("component_item")
						
						# Grab image only once per component type
						if c_type not in grouped_images and item_code:
							# First try to get the image from the variant's parent
							variant_of = frappe.db.get_value("Item", item_code, "variant_of")
							img = None
							if variant_of:
								img = frappe.db.get_value("Item", variant_of, "image")
							
							# If no variant parent, or parent has no image, check the item itself
							if not img:
								img = frappe.db.get_value("Item", item_code, "image")
								
							if img:
								grouped_images[c_type] = img if img.startswith("http") else f"{frappe.utils.get_url()}{img}"
						
						grouped_components[c_type].append({
							"code": item_code or "",
							"label": desc
						})
					
					self.kit_components = []
					for c_type, items_list in grouped_components.items():
						final_json_list = []
						
						# Inject the hero image as the first object in the array
						if c_type in grouped_images:
							final_json_list.append({"hero_image": grouped_images[c_type]})
							
						final_json_list.extend(items_list)
						
						self.append("kit_components", {
							"component_type": c_type,
							"component_item": items_list[0]["code"] if items_list else "", 
							"component_description": json.dumps(final_json_list, indent=1)
						})
					
					record(debug, "Kit Components", len(grouped_components), [f"{k} ({len(v)} items)" for k, v in grouped_components.items()], appended=True)

		# --- Sort all rows by display_order ---
		if self.webflow_specifications:
			# 1. Sort the list
			self.webflow_specifications.sort(
				key=lambda row: int(row.get("display_order")) if row.get("display_order") not in (None, "") else 999
			)
			
			# 2. Re-assign idx so ERPNext saves and renders them in the new sorted order
			row_idx = 1
			for row in self.webflow_specifications:
				row.idx = row_idx
				row_idx += 1
			
		debug["existing_labels_after"] = [row.spec_label for row in (self.webflow_specifications or [])]

		# This wrote an Error Log on every save; now only when asked for in site config.
		if frappe.conf.get("webflow_enrichment_debug"):
			frappe.log_error(
				title=f"Combined Full Enrichment Debug: {self.name}",
				message=json.dumps(debug, indent=2, default=str),
			)
