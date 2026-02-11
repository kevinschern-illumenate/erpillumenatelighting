# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


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

	def populate_attribute_links(self):
		"""Populate attribute links from the linked fixture template's allowed options and tape offerings."""
		if self.product_type != "Fixture Template" or not self.fixture_template:
			return
		
		template = frappe.get_doc("ilL-Fixture-Template", self.fixture_template)
		attribute_links = []
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
				existing = [a for a in attribute_links
				            if a["attribute_doctype"] == "ilL-Attribute-Dimming Protocol"
				            and a["attribute_name"] == protocol_name]
				if not existing:
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

		# Clear existing attribute links and add new ones
		self.attribute_links = []
		for link in attribute_links:
			self.append("attribute_links", link)

	def _get_attribute_webflow_id(self, doctype: str, name: str) -> str | None:
		"""Get the Webflow item ID for an attribute if it has been synced."""
		try:
			return frappe.db.get_value(doctype, name, "webflow_item_id")
		except Exception:
			return None

	def calculate_specifications(self):
		"""Auto-populate specifications from linked source doctype.
		
		DEPRECATED: This method is no longer used as the specifications table field
		has been removed. Attribute links are now used instead. This method is kept
		for backwards compatibility but does nothing.
		"""
		# The specifications field no longer exists - this feature is deprecated
		# Use attribute_links instead (auto-populated via populate_attribute_links)
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

		# Check for optional dimension fields that may have been added
		if hasattr(profile, 'width_mm') and profile.width_mm:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Width",
				"spec_value": str(profile.width_mm),
				"spec_unit": "mm",
				"is_calculated": 1,
				"display_order": 40
			})

		if hasattr(profile, 'height_mm') and profile.height_mm:
			specs_to_add.append({
				"spec_group": "Physical",
				"spec_label": "Height",
				"spec_value": str(profile.height_mm),
				"spec_unit": "mm",
				"is_calculated": 1,
				"display_order": 50
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
		"""Populate configurator options from template's allowed options."""
		template = frappe.get_doc("ilL-Fixture-Template", self.fixture_template)

		# Define the configurator flow order
		option_flow = [
			("LED Package", 1),
			("Environment Rating", 2),
			("CCT", 3),
			("Output Level", 4),
			("Lens Appearance", 5),
			("Finish", 6),
			("Mounting Method", 7),
			("Power Feed Type", 8),
			("Endcap Style", 9),
			("Endcap Color", 10),
		]

		# Clear existing and rebuild
		self.configurator_options = []

		for option_type, step in option_flow:
			allowed_values = self._get_allowed_values_for_option(template, option_type)
			if allowed_values:
				self.append("configurator_options", {
					"option_step": step,
					"option_type": option_type,
					"option_label": f"Select {option_type}",
					"is_required": 1,
					"allowed_values_json": frappe.as_json(allowed_values)
				})

	def _get_allowed_values_for_option(self, template, option_type: str) -> list:
		"""Get allowed values for a given option type."""
		values = []

		# Map option types to template allowed_options fields
		option_field_map = {
			"Finish": "finish",
			"Lens Appearance": "lens_appearance",
			"Mounting Method": "mounting_method",
			"Environment Rating": "environment_rating",
			"Power Feed Type": "power_feed_type",
			"Endcap Style": "endcap_style",
		}

		if option_type in option_field_map:
			field = option_field_map[option_type]
			for opt in template.allowed_options or []:
				if hasattr(opt, 'option_type') and opt.option_type == option_type:
					if hasattr(opt, 'is_active') and not opt.is_active:
						continue
					val = getattr(opt, field, None)
					if val:
						is_default = getattr(opt, 'is_default', False) if hasattr(opt, 'is_default') else False
						values.append({
							"value": val,
							"label": val,
							"is_default": is_default
						})

		# Special handling for LED Package, CCT, Output Level (from tape offerings)
		elif option_type == "LED Package":
			values = self._get_led_packages_from_tapes(template)
		elif option_type == "CCT":
			values = self._get_ccts_from_tapes(template)
		elif option_type == "Output Level":
			values = self._get_output_levels_from_tapes(template)
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

		return values

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
		"""Get unique output levels from allowed tape offerings with details."""
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
						levels[output_level] = {
							"value": output_level,
							"label": f"{level_data.get('value', '')} lm/ft",
							"code": level_data.get("sku_code") or "",
							"lm_per_ft": level_data.get("value") or 0
						}
		return sorted(list(levels.values()), key=lambda x: x.get("lm_per_ft", 0))

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
