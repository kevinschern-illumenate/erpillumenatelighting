# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from illumenate_lighting.illumenate_lighting.api.unit_conversion import (
	format_length_inches,
)
from illumenate_lighting.illumenate_lighting.doctype.ill_spec_profile.ill_spec_profile import (
	compute_profile_dimensions,
)


class ilLWebflowProduct(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_specification.ill_child_webflow_specification import ilLChildWebflowSpecification
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_configurator_option.ill_child_webflow_configurator_option import ilLChildWebflowConfiguratorOption
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_kit_component.ill_child_webflow_kit_component import ilLChildWebflowKitComponent
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_certification_link.ill_child_webflow_certification_link import ilLChildWebflowCertificationLink
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_compatibility.ill_child_webflow_compatibility import ilLChildWebflowCompatibility
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_gallery_image.ill_child_webflow_gallery_image import ilLChildWebflowGalleryImage
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_document.ill_child_webflow_document import ilLChildWebflowDocument
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_webflow_attribute_link.ill_child_webflow_attribute_link import ilLChildWebflowAttributeLink

		accessory_spec: DF.Link | None
		attribute_links: DF.Table[ilLChildWebflowAttributeLink]
		auto_calculate_specs: DF.Check
		auto_populate_attributes: DF.Check
		certifications: DF.Table[ilLChildWebflowCertificationLink]
		compatible_products: DF.Table[ilLChildWebflowCompatibility]
		configurator_intro_text: DF.SmallText | None
		configurator_options: DF.Table[ilLChildWebflowConfiguratorOption]
		controller_spec: DF.Link | None
		documents: DF.Table[ilLChildWebflowDocument]
		driver_spec: DF.Link | None
		featured_image: DF.AttachImage | None
		fixture_template: DF.Link | None
		gallery_images: DF.Table[ilLChildWebflowGalleryImage]
		is_active: DF.Check
		is_configurable: DF.Check
		kit_components: DF.Table[ilLChildWebflowKitComponent]
		last_synced_at: DF.Datetime | None
		length_increment_mm: DF.Int
		lens_spec: DF.Link | None
		long_description: DF.TextEditor | None
		max_length_mm: DF.Int
		min_length_mm: DF.Int
		product_category: DF.Link | None
		product_name: DF.Data
		product_slug: DF.Data
		product_type: DF.Literal["Fixture Template", "Driver", "Controller", "Extrusion Kit", "LED Tape", "Component", "Accessory"]
		profile_spec: DF.Link | None
		short_description: DF.SmallText | None
		specifications: DF.Table[ilLChildWebflowSpecification]
		sync_error_message: DF.SmallText | None
		sync_status: DF.Literal["Pending", "Synced", "Error", "Never Synced"]
		tape_spec: DF.Link | None
		webflow_collection_slug: DF.Data | None
		webflow_item_id: DF.Data | None
	# end: auto-generated types

	def before_save(self):
		"""Calculate specifications, attribute links, and configurator options before saving."""
		# Populate attribute links from fixture template
		if self.get("auto_populate_attributes", True):
			self.populate_attribute_links()
		
		# Legacy: calculate specifications (deprecated - moving to attribute links)
		if self.auto_calculate_specs:
			self.calculate_specifications()
		
		if self.is_configurable and self.fixture_template:
			self.populate_configurator_options()
		
		# Mark as pending sync if substantive changes were made
		# Skip this check if we're being saved from the sync API (sync_status is being set to Synced)
		if not getattr(self, '_skip_sync_status_check', False):
			if (self.has_value_changed("attribute_links") or 
			    self.has_value_changed("configurator_options")):
				if self.sync_status == "Synced":
					self.sync_status = "Pending"

	def on_update(self):
		"""Update webflow_product backlink on linked fixture template after save."""
		self._update_fixture_template_backlink()

	def on_trash(self):
		"""Clear webflow_product backlink on linked fixture template before deletion."""
		if self.fixture_template:
			frappe.db.set_value(
				"ilL-Fixture-Template",
				self.fixture_template,
				"webflow_product",
				None,
				update_modified=False,
			)

	def _update_fixture_template_backlink(self):
		"""Set the webflow_product backlink on the linked fixture template.

		Also clears the backlink on the previously linked fixture template
		if the fixture_template field was changed.
		"""
		old_template = self.get_doc_before_save()
		old_fixture = old_template.fixture_template if old_template else None

		# Clear backlink on old fixture template if it changed
		if old_fixture and old_fixture != self.fixture_template:
			frappe.db.set_value(
				"ilL-Fixture-Template",
				old_fixture,
				"webflow_product",
				None,
				update_modified=False,
			)

		# Set backlink on new fixture template
		if self.fixture_template:
			frappe.db.set_value(
				"ilL-Fixture-Template",
				self.fixture_template,
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
		# Handle LED Tape
		elif self.product_type == "LED Tape" and self.tape_spec:
			self._populate_led_tape_attributes(attribute_links)
		# Handle Driver
		elif self.product_type == "Driver" and self.driver_spec:
			self._populate_driver_attributes(attribute_links)
		# Handle Controller
		elif self.product_type == "Controller" and self.controller_spec:
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

	def _populate_extrusion_kit_attributes(self, attribute_links):
		"""Extract attributes from extrusion kit profile spec, lens spec, and kit components."""
		display_order = 0
		
		# Extract attributes from profile_spec if present
		if self.profile_spec:
			try:
				profile = frappe.get_doc("ilL-Spec-Profile", self.profile_spec)
			except frappe.DoesNotExistError:
				frappe.log_error(
					message=f"Profile spec {self.profile_spec} not found for extrusion kit {self.name}",
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
		if self.lens_spec:
			try:
				lens = frappe.get_doc("ilL-Spec-Lens", self.lens_spec)
			except frappe.DoesNotExistError:
				frappe.log_error(
					message=f"Lens spec {self.lens_spec} not found for extrusion kit {self.name}",
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
				"ilL-Attribute-Output Voltage", tape.input_voltage, "voltage"
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

	def _populate_driver_attributes(self, attribute_links):
		"""Extract attributes from driver spec.

		Note: Caller must ensure self.driver_spec is set before calling this method.
		"""
		if not self.driver_spec:
			return

		try:
			driver = frappe.get_doc("ilL-Spec-Driver", self.driver_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Driver spec {self.driver_spec} not found for product {self.name}",
				title="Driver Spec Not Found",
			)
			return

		display_order = 0

		# Output Voltage
		if driver.voltage_output:
			display_order += 1
			webflow_id = self._get_attribute_webflow_id("ilL-Attribute-Output Voltage", driver.voltage_output)
			voltage_label = frappe.db.get_value(
				"ilL-Attribute-Output Voltage", driver.voltage_output, "voltage"
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

		Note: Caller must ensure self.controller_spec is set before calling this method.
		"""
		if not self.controller_spec:
			return

		try:
			controller = frappe.get_doc("ilL-Spec-Controller", self.controller_spec)
		except frappe.DoesNotExistError:
			frappe.log_error(
				message=f"Controller spec {self.controller_spec} not found for product {self.name}",
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
				"spec_value": " + ".join(ccts),
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
			output_voltage = frappe.db.get_value(
				"ilL-Attribute-Output Voltage",
				driver.voltage_output,
				"voltage"
			)
			if output_voltage:
				specs_to_add.append({
					"spec_group": "Electrical",
					"spec_label": "Output Voltage",
					"spec_value": str(output_voltage),
					"spec_unit": "VDC",
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
			voltage = frappe.db.get_value(
				"ilL-Attribute-Output Voltage",
				tape.input_voltage,
				"voltage"
			)
			if voltage:
				specs_to_add.append({
					"spec_group": "Electrical",
					"spec_label": "Input Voltage",
					"spec_value": str(voltage),
					"spec_unit": "VDC",
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
						code = frappe.db.get_value(doctype, val, "code") or ""
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
			transmission = float(lens.get("transmission") or 1.0)

			options = []
			seen = set()
			for raw in raw_outputs:
				tape_lm = raw.get("tape_output_lm_ft") or raw.get("lm_per_ft") or 0
				delivered = tape_lm * transmission

				if fixture_output_levels:
					closest = min(
						fixture_output_levels,
						key=lambda x: abs((x.value or 0) - delivered)
					)
					if closest.name not in seen:
						seen.add(closest.name)
						options.append({
							"value": raw.get("value"),
							"label": f"{closest.value} lm/ft",
							"code": closest.sku_code or raw.get("code", ""),
							"tape_output_lm_ft": tape_lm,
							"delivered_lm_ft": closest.value,
						})
				else:
					delivered_rounded = int(round(delivered))
					options.append({
						"value": raw.get("value"),
						"label": f"{delivered_rounded} lm/ft",
						"code": raw.get("code", ""),
						"tape_output_lm_ft": tape_lm,
						"delivered_lm_ft": delivered_rounded,
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
