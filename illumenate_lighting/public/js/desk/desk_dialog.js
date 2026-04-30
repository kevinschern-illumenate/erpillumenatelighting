/**
 * Desk Configurator Dialog (Phase 5)
 *
 * Multi-step "Build / Add Configured Product" wizard for Quotation and
 * Sales Order. Replaces the legacy "Configure Product" Tools button which
 * only allowed picking an existing ilL-Configured-* record.
 *
 * State machine:
 *
 *   pickType  → user picks Linear Fixture / LED Tape / LED Neon
 *      ↓
 *   configure → product-type-specific form (template, options, length,
 *               feed config, multi-segment toggle, Advanced disclosure)
 *      ↓ Calculate
 *   calculated → calculate_and_lookup result rendered with pricing
 *                breakdown (collapsible). If existing_record found,
 *                offers Reuse / Create New Variant choice.
 *      ↓ Continue
 *   bomReview → preview_bom rows + final confirmation
 *      ↓ Save & Apply
 *   done      → row written to parent doc, dialog closed
 *
 * API surface:
 *   IllDesk.openConfiguratorDialog(frm, opts)
 *   IllDesk.addConfiguratorButton(frm)
 *
 * Backwards-compat: window.illumenate_lighting.quote_order_configurator
 * exposes { add_buttons, show_dialog } via the shim file
 * public/js/quote_order_configurator.js.
 */
(function (root) {
	'use strict';

	var IllDesk = root.IllDesk = root.IllDesk || {};
	var API = 'illumenate_lighting.illumenate_lighting.api.configured_product_builder.';
	var QOC_API = 'illumenate_lighting.illumenate_lighting.api.quote_order_configurator.';

	var PRODUCT_TYPES = [
		{ value: 'Linear Fixture', label: __('Linear Fixture') },
		{ value: 'LED Tape',       label: __('LED Tape') },
		{ value: 'LED Neon',       label: __('LED Neon') }
	];

	// ──────────────────────────────────────────────────────────────────
	// Public entry points
	// ──────────────────────────────────────────────────────────────────

	IllDesk.addConfiguratorButton = function (frm) {
		if (!canConfigure(frm)) return;
		frm.add_custom_button(__('Build / Add Configured Product'), function () {
			IllDesk.openConfiguratorDialog(frm);
		}, __('Tools'));
	};

	IllDesk.openConfiguratorDialog = function (frm, opts) {
		var ctrl = new DialogController(frm, opts || {});
		ctrl.start();
		return ctrl;
	};

	// ──────────────────────────────────────────────────────────────────
	// Helpers
	// ──────────────────────────────────────────────────────────────────

	function canConfigure(frm) {
		if (!frm || !frm.doc) return false;
		if (frm.doc.docstatus !== 0) return false;
		if (typeof frm.is_new === 'function' && frm.is_new()) return false;
		if (typeof frm.is_read_only === 'function' && frm.is_read_only()) return false;
		return true;
	}

	function selectedItemRowName(frm) {
		var selected = (frm && frm.get_selected) ? frm.get_selected() : null;
		if (!selected || !selected.items || selected.items.length !== 1) return null;
		return selected.items[0];
	}

	function escapeHtml(value) {
		return $('<div>').text(value == null ? '' : String(value)).html();
	}

	// ──────────────────────────────────────────────────────────────────
	// Controller
	// ──────────────────────────────────────────────────────────────────

	function DialogController(frm, opts) {
		this.frm = frm;
		this.opts = opts;
		this.dialog = null;
		this.state = 'pickType';
		this.productType = null;

		// Working state
		this.payload = null;            // engine payload built from form
		this.validation = null;         // calculate_and_lookup response
		this.lookupResult = null;       // existing_record / candidate hash
		this.reuseExisting = false;
		this.parentConfiguredFixture = null;
		this.parentConfiguredTapeNeon = null;
		this.tapeNeonTemplate = null;
		this.qty = 1;
	}

	DialogController.prototype.start = function () {
		var self = this;
		this.dialog = new frappe.ui.Dialog({
			title: __('Build / Add Configured Product'),
			size: 'large',
			fields: [
				{ fieldtype: 'HTML', fieldname: 'step_indicator' },
				{ fieldtype: 'HTML', fieldname: 'body' }
			],
			primary_action_label: __('Continue'),
			primary_action: function () { self.onPrimary(); }
		});
		this.dialog.show();
		this.renderStepIndicator();
		this.renderPickType();
	};

	DialogController.prototype.renderStepIndicator = function () {
		var steps = [
			{ key: 'pickType',   label: __('Type') },
			{ key: 'configure',  label: __('Configure') },
			{ key: 'calculated', label: __('Calculate') },
			{ key: 'bomReview',  label: __('BOM') }
		];
		var current = this.state;
		var passedKeys = ['pickType'];
		if (current === 'configure' || current === 'calculated' || current === 'bomReview') passedKeys.push('configure');
		if (current === 'calculated' || current === 'bomReview') passedKeys.push('calculated');
		if (current === 'bomReview') passedKeys.push('bomReview');

		var html = '<div class="ill-desk-stepper d-flex align-items-center mb-2">';
		steps.forEach(function (s, i) {
			var active = (s.key === current);
			var passed = passedKeys.indexOf(s.key) >= 0;
			var color = active ? '#0d6efd' : (passed ? '#198754' : '#adb5bd');
			html += '<span class="badge mr-2" style="background:' + color + '; color:white;">' + (i + 1) + '. ' + s.label + '</span>';
			if (i < steps.length - 1) html += '<span style="color:#dee2e6;">›</span><span class="mr-2"></span>';
		});
		html += '</div>';
		this.dialog.fields_dict.step_indicator.$wrapper.html(html);
	};

	DialogController.prototype.body$ = function () {
		return this.dialog.fields_dict.body.$wrapper;
	};

	DialogController.prototype.setPrimaryLabel = function (label, secondaryLabel, onSecondary) {
		this.dialog.set_primary_action(label, this.onPrimary.bind(this));
		if (secondaryLabel) {
			this.dialog.set_secondary_action_label(secondaryLabel);
			this.dialog.set_secondary_action(onSecondary || function () {});
		} else {
			this.dialog.set_secondary_action_label(__('Cancel'));
			this.dialog.set_secondary_action(function () {});
		}
	};

	DialogController.prototype.onPrimary = function () {
		switch (this.state) {
			case 'pickType':   return this.advanceFromPickType();
			case 'configure':  return this.advanceFromConfigure();
			case 'calculated': return this.advanceFromCalculated();
			case 'bomReview':  return this.advanceFromBomReview();
		}
	};

	// ── Step 1: pick product type ────────────────────────────────────
	DialogController.prototype.renderPickType = function () {
		this.state = 'pickType';
		this.renderStepIndicator();
		this.setPrimaryLabel(__('Continue'));

		var $body = this.body$();
		$body.html('');

		var html = '<div class="form-group">'
			+ '<label class="control-label">' + __('Product Type') + ' <span class="text-danger">*</span></label>'
			+ '<div class="ill-desk-type-pills">';
		var self = this;
		PRODUCT_TYPES.forEach(function (pt) {
			var active = (self.productType === pt.value) ? 'active' : '';
			html += '<button type="button" class="btn btn-default mr-2 mb-2 ill-desk-type-pill ' + active + '" data-value="' + escapeHtml(pt.value) + '">' + escapeHtml(pt.label) + '</button>';
		});
		html += '</div>'
			+ '<div class="form-group mt-3">'
			+   '<label class="control-label">' + __('Quantity') + '</label>'
			+   '<input type="number" class="form-control ill-desk-qty" min="1" step="1" value="' + (this.qty || 1) + '">'
			+ '</div>';

		$body.html(html);
		$body.find('.ill-desk-type-pill').on('click', function () {
			$body.find('.ill-desk-type-pill').removeClass('active btn-primary').addClass('btn-default');
			$(this).removeClass('btn-default').addClass('active btn-primary');
			self.productType = $(this).data('value');
		});
	};

	DialogController.prototype.advanceFromPickType = function () {
		var qtyVal = parseFloat(this.body$().find('.ill-desk-qty').val());
		if (qtyVal && qtyVal > 0) this.qty = qtyVal;
		if (!this.productType) {
			frappe.msgprint(__('Please choose a product type.'));
			return;
		}
		this.renderConfigure();
	};

	// ── Step 2: configure ────────────────────────────────────────────
	DialogController.prototype.renderConfigure = function () {
		this.state = 'configure';
		this.renderStepIndicator();
		this.setPrimaryLabel(__('Calculate'), __('Back'), this.renderPickType.bind(this));

		var $body = this.body$();
		$body.html('');

		if (this.productType === 'Linear Fixture') {
			this.renderFixtureForm($body);
		} else {
			this.renderTapeNeonForm($body);
		}
	};

	DialogController.prototype.renderFixtureForm = function ($body) {
		var self = this;
		this.formFields = new frappe.ui.FieldGroup({
			parent: $body[0],
			fields: [
				{
					fieldtype: 'Link', fieldname: 'fixture_template_code',
					label: __('Fixture Template'), options: 'ilL-Fixture-Template', reqd: 1,
					onchange: function () {
						var tpl = self.formFields.get_value('fixture_template_code');
						self.formFields.set_value('tape_offering_id', null);
						self.formFields.fields_dict.tape_offering_id.df.get_query = function () {
							return {
								query: 'illumenate_lighting.illumenate_lighting.api.configured_product_builder.allowed_tape_offerings_for_template',
								filters: { fixture_template: tpl }
							};
						};
					}
				},
				{
					fieldtype: 'Link', fieldname: 'tape_offering_id',
					label: __('Tape Offering'), options: 'ilL-Rel-Tape Offering', reqd: 1
				},
				{ fieldtype: 'Column Break' },
				{
					fieldtype: 'Link', fieldname: 'environment_rating_code',
					label: __('Environment Rating'), options: 'ilL-Attribute-Environment Rating', reqd: 1
				},
				{
					fieldtype: 'Link', fieldname: 'lens_appearance_code',
					label: __('Lens Appearance'), options: 'ilL-Attribute-Lens Appearance', reqd: 1
				},
				{ fieldtype: 'Section Break', label: __('Mounting & Finish') },
				{
					fieldtype: 'Link', fieldname: 'mounting_method_code',
					label: __('Mounting Method'), options: 'ilL-Attribute-Mounting Method', reqd: 1
				},
				{
					fieldtype: 'Link', fieldname: 'finish_code',
					label: __('Finish'), options: 'ilL-Attribute-Finish', reqd: 1
				},
				{ fieldtype: 'Column Break' },
				{
					fieldtype: 'Link', fieldname: 'endcap_color_code',
					label: __('Endcap Color'), options: 'ilL-Attribute-Endcap Color'
				},
				{
					fieldtype: 'Link', fieldname: 'power_feed_type_code',
					label: __('Power Feed Type'), options: 'ilL-Attribute-Power Feed Type'
				},
				{
					fieldtype: 'Link', fieldname: 'endcap_style_start_code',
					label: __('Endcap Style (Start)'), options: 'ilL-Attribute-Endcap Style', reqd: 1
				},
				{
					fieldtype: 'Link', fieldname: 'endcap_style_end_code',
					label: __('Endcap Style (End)'), options: 'ilL-Attribute-Endcap Style', reqd: 1
				},
				{ fieldtype: 'Section Break', label: __('Length & Feed') },
				{
					fieldtype: 'Check', fieldname: 'multi_segment',
					label: __('Multi-segment fixture'), default: 0,
					onchange: function () {
						var on = !!self.formFields.get_value('multi_segment');
						self.formFields.fields_dict.requested_overall_length_mm.df.hidden = on ? 1 : 0;
						self.formFields.fields_dict.start_feed_direction_code.df.hidden = on ? 1 : 0;
						self.formFields.fields_dict.end_feed_direction_code.df.hidden = on ? 1 : 0;
						self.formFields.fields_dict.start_leader_len_mm.df.hidden = on ? 1 : 0;
						self.formFields.fields_dict.end_leader_len_mm.df.hidden = on ? 1 : 0;
						self.formFields.fields_dict.segments_json.df.hidden = on ? 0 : 1;
						self.formFields.refresh();
					}
				},
				{
					fieldtype: 'Float', fieldname: 'requested_overall_length_mm',
					label: __('Requested Length (mm)'), reqd: 1
				},
				{ fieldtype: 'Column Break' },
				{
					fieldtype: 'Link', fieldname: 'start_feed_direction_code',
					label: __('Start Feed Direction'), options: 'ilL-Attribute-Feed-Direction'
				},
				{
					fieldtype: 'Float', fieldname: 'start_leader_len_mm',
					label: __('Start Leader Length (mm)')
				},
				{
					fieldtype: 'Link', fieldname: 'end_feed_direction_code',
					label: __('End Feed Direction'), options: 'ilL-Attribute-Feed-Direction'
				},
				{
					fieldtype: 'Float', fieldname: 'end_leader_len_mm',
					label: __('End Leader Length (mm)')
				},
				{
					fieldtype: 'Code', fieldname: 'segments_json', options: 'JSON',
					label: __('Segments (JSON array)'), hidden: 1,
					description: __('Each segment: { "length_mm": Number, "start_feed_direction_code": "...", "start_leader_len_mm": Number, "end_feed_direction_code": "...", "end_leader_len_mm": Number }')
				},
				{ fieldtype: 'Section Break', label: __('Advanced'), collapsible: 1, collapsible_depends_on: 'eval:false' },
				{
					fieldtype: 'Link', fieldname: 'dimming_protocol_code',
					label: __('Dimming Protocol'), options: 'ilL-Attribute-Dimming Protocol'
				},
				{
					fieldtype: 'Check', fieldname: 'include_power_supply',
					label: __('Include Power Supply'), default: 1
				},
				{ fieldtype: 'Column Break' },
				{
					fieldtype: 'Link', fieldname: 'parent_configured_fixture',
					label: __('Variant of (existing Configured Fixture)'),
					options: 'ilL-Configured-Fixture',
					description: __('Optional. When set, the result is always saved as a new -V(NNNN) variant.')
				}
			]
		});
		this.formFields.make();
	};

	DialogController.prototype.renderTapeNeonForm = function ($body) {
		var self = this;
		var isNeon = (this.productType === 'LED Neon');
		this.formFields = new frappe.ui.FieldGroup({
			parent: $body[0],
			fields: [
				{
					fieldtype: 'Link', fieldname: 'tape_neon_template',
					label: __('Tape/Neon Template'), options: 'ilL-Tape-Neon-Template', reqd: 1
				},
				{ fieldtype: 'Column Break' },
				{
					fieldtype: 'Link', fieldname: 'cct',
					label: __('CCT'), options: 'ilL-Attribute-CCT', reqd: 1
				},
				{
					fieldtype: 'Link', fieldname: 'output_level',
					label: __('Output Level'), options: 'ilL-Attribute-Output Level', reqd: 1
				},
				{ fieldtype: 'Section Break' },
				isNeon
					? { fieldtype: 'Link', fieldname: 'finish',
					    label: __('Finish'), options: 'ilL-Attribute-PCB Finish', reqd: 1 }
					: { fieldtype: 'Link', fieldname: 'environment_rating',
					    label: __('Environment Rating'), options: 'ilL-Attribute-Environment Rating' }
			]
				.concat(isNeon ? [
					{
						fieldtype: 'Code', fieldname: 'segments_json', options: 'JSON', reqd: 1,
						label: __('Segments (JSON array)'),
						description: __('Each segment: { "ip_rating": "...", "start_feed_direction": "...", "start_lead_length_inches": Number, "fixture_length_unit": "in|ft|ft_in", "fixture_length_value": Number, "end_feed_direction": "...", "end_feed_length_inches": Number }'),
						default: '[\n  {\n    "ip_rating": "",\n    "start_feed_direction": "",\n    "start_lead_length_inches": 0,\n    "fixture_length_unit": "in",\n    "fixture_length_value": 0,\n    "end_feed_direction": "",\n    "end_feed_length_inches": 0\n  }\n]'
					}
				] : [
					{ fieldtype: 'Column Break' },
					{ fieldtype: 'Link', fieldname: 'feed_type',
					  label: __('Feed Type'), options: 'ilL-Attribute-Power Feed Type' },
					{ fieldtype: 'Float', fieldname: 'lead_length_inches',
					  label: __('Lead Length (in)'), default: 12, reqd: 1 },
					{ fieldtype: 'Select', fieldname: 'tape_length_unit',
					  label: __('Length Unit'), options: 'in\nft\nft_in', default: 'in' },
					{ fieldtype: 'Float', fieldname: 'tape_length_value',
					  label: __('Length Value (in or ft)') },
					{ fieldtype: 'Float', fieldname: 'tape_length_feet',
					  label: __('Length — Feet (when ft_in)') },
					{ fieldtype: 'Float', fieldname: 'tape_length_inches',
					  label: __('Length — Inches (when ft_in)') }
				])
				.concat([
					{ fieldtype: 'Section Break', label: __('Advanced'), collapsible: 1, collapsible_depends_on: 'eval:false' },
					{ fieldtype: 'Link', fieldname: 'dimming_protocol_code',
					  label: __('Dimming Protocol'), options: 'ilL-Attribute-Dimming Protocol' },
					{ fieldtype: 'Check', fieldname: 'include_power_supply',
					  label: __('Include Power Supply'), default: 1 },
					{ fieldtype: 'Column Break' },
					{ fieldtype: 'Link', fieldname: 'parent_configured_tape_neon',
					  label: __('Variant of (existing Configured Tape/Neon)'),
					  options: 'ilL-Configured-Tape-Neon',
					  description: __('Optional. When set, the result is always saved as a new -V(NNNN) variant.') }
				])
		});
		this.formFields.make();
	};

	DialogController.prototype.advanceFromConfigure = function () {
		var values = this.formFields.get_values();
		if (!values) return;       // FieldGroup will surface validation errors

		var payload, parents = {};
		try {
			if (this.productType === 'Linear Fixture') {
				payload = this.buildFixturePayload(values, parents);
			} else {
				payload = this.buildTapeNeonPayload(values, parents);
			}
		} catch (e) {
			frappe.msgprint({ title: __('Invalid configuration'), message: e.message, indicator: 'red' });
			return;
		}

		this.payload = payload;
		this.parentConfiguredFixture = parents.parent_configured_fixture || null;
		this.parentConfiguredTapeNeon = parents.parent_configured_tape_neon || null;
		this.tapeNeonTemplate = parents.tape_neon_template || null;

		this.runCalculate();
	};

	DialogController.prototype.buildFixturePayload = function (values, parents) {
		var payload = {};
		[
			'fixture_template_code', 'finish_code', 'lens_appearance_code',
			'mounting_method_code', 'endcap_color_code', 'power_feed_type_code',
			'endcap_style_start_code', 'endcap_style_end_code',
			'environment_rating_code', 'tape_offering_id', 'dimming_protocol_code'
		].forEach(function (k) {
			if (values[k]) payload[k] = values[k];
		});
		payload.qty = this.qty;
		payload.include_power_supply = values.include_power_supply ? 1 : 0;

		if (values.multi_segment) {
			var raw = values.segments_json;
			if (!raw) throw new Error(__('Segments JSON is required for multi-segment fixtures.'));
			var parsed;
			try { parsed = JSON.parse(raw); }
			catch (e) { throw new Error(__('Segments JSON is not valid JSON: {0}', [e.message])); }
			if (!Array.isArray(parsed) || !parsed.length) {
				throw new Error(__('Segments JSON must be a non-empty array.'));
			}
			payload.multi_segment = 1;
			payload.segments_json = JSON.stringify(parsed);
		} else {
			if (!values.requested_overall_length_mm) {
				throw new Error(__('Requested length is required.'));
			}
			payload.requested_overall_length_mm = values.requested_overall_length_mm;
			['start_feed_direction_code', 'end_feed_direction_code',
			 'start_leader_len_mm', 'end_leader_len_mm'].forEach(function (k) {
				if (values[k]) payload[k] = values[k];
			});
		}

		parents.parent_configured_fixture = values.parent_configured_fixture || null;
		return payload;
	};

	DialogController.prototype.buildTapeNeonPayload = function (values, parents) {
		var isNeon = (this.productType === 'LED Neon');
		var selections = {
			cct: values.cct,
			output_level: values.output_level
		};
		if (isNeon) {
			selections.finish = values.finish;
		} else {
			if (values.environment_rating) selections.environment_rating = values.environment_rating;
			if (values.feed_type) selections.feed_type = values.feed_type;
			selections.feed_direction = 'End Feed';
			selections.lead_length_inches = values.lead_length_inches || 0;
			selections.tape_length_unit = values.tape_length_unit || 'in';
			selections.tape_length_value = values.tape_length_value || 0;
			selections.tape_length_feet = values.tape_length_feet || 0;
			selections.tape_length_inches = values.tape_length_inches || 0;
		}

		var payload = { selections: selections };
		payload.include_power_supply = values.include_power_supply ? 1 : 0;
		if (values.dimming_protocol_code) payload.dimming_protocol_code = values.dimming_protocol_code;

		if (isNeon) {
			var raw = values.segments_json;
			if (!raw) throw new Error(__('Segments JSON is required for LED Neon.'));
			var parsed;
			try { parsed = JSON.parse(raw); }
			catch (e) { throw new Error(__('Segments JSON is not valid JSON: {0}', [e.message])); }
			if (!Array.isArray(parsed) || !parsed.length) {
				throw new Error(__('Segments JSON must be a non-empty array.'));
			}
			payload.segments_json = JSON.stringify(parsed);
		}

		parents.parent_configured_tape_neon = values.parent_configured_tape_neon || null;
		parents.tape_neon_template = values.tape_neon_template || null;
		return payload;
	};

	// ── Step 3: calculate & lookup ───────────────────────────────────
	DialogController.prototype.runCalculate = function () {
		var self = this;
		frappe.call({
			method: API + 'calculate_and_lookup',
			args: {
				product_type: this.productType,
				payload_json: JSON.stringify(this.payload),
				parent_configured_fixture: this.parentConfiguredFixture,
				parent_configured_tape_neon: this.parentConfiguredTapeNeon,
				tape_neon_template: this.tapeNeonTemplate
			},
			freeze: true,
			freeze_message: __('Calculating...'),
			callback: function (r) {
				var msg = r.message || {};
				if (!msg.success || !msg.is_valid) {
					self.renderCalculateError(msg);
					return;
				}
				self.lookupResult = msg;
				self.validation = msg.validation || {};
				self.reuseExisting = !!msg.existing_record;
				self.renderCalculated();
			}
		});
	};

	DialogController.prototype.renderCalculateError = function (msg) {
		var $body = this.body$();
		var errors = (msg.messages || []).filter(function (m) { return m && m.severity === 'error'; });
		var html = '<div class="alert alert-danger"><strong>' + __('Validation failed') + '</strong>'
			+ '<div class="small">' + escapeHtml(msg.error || (msg.validation && msg.validation.error) || __('Engine returned an error')) + '</div>'
			+ (errors.length ? '<ul class="mb-0 mt-2">' + errors.map(function (e) {
				return '<li class="small">' + escapeHtml(e.text || '') + '</li>';
			}).join('') + '</ul>' : '')
			+ '</div>';
		$body.html(html);
		this.setPrimaryLabel(__('Back to Configure'), __('Cancel'));
		this.state = 'configure-error';
		var self = this;
		this.dialog.set_primary_action(__('Back to Configure'), function () { self.renderConfigure(); });
	};

	DialogController.prototype.renderCalculated = function () {
		this.state = 'calculated';
		this.renderStepIndicator();
		this.setPrimaryLabel(__('Continue to BOM'), __('Back'), this.renderConfigure.bind(this));

		var $body = this.body$();
		$body.html('');

		var $summary = $('<div class="ill-desk-summary mb-2"></div>');
		$body.append($summary);

		var existing = this.lookupResult.existing_record;
		var partNumber = this.lookupResult.candidate_part_number;

		$summary.append(
			'<div class="mb-2"><strong>' + __('Candidate Part Number') + ':</strong> '
			+ '<code>' + escapeHtml(partNumber || '-') + '</code></div>'
		);

		if (existing) {
			var self = this;
			var radioId = 'ill-desk-reuse-' + Math.floor(Math.random() * 1e9);
			$summary.append(
				'<div class="alert alert-info py-2 px-2">'
				+ '<div><strong>' + __('Existing record matches this configuration:') + '</strong> '
				+ '<a href="/app/' + (this.productType === 'Linear Fixture' ? 'ill-configured-fixture' : 'ill-configured-tape-neon')
				+ '/' + encodeURIComponent(existing) + '" target="_blank">' + escapeHtml(existing) + '</a></div>'
				+ '<div class="form-check mt-1">'
				+ '<input class="form-check-input" type="radio" name="' + radioId + '" id="' + radioId + '-reuse" value="reuse" checked>'
				+ '<label class="form-check-label" for="' + radioId + '-reuse">' + __('Reuse existing record') + '</label>'
				+ '</div>'
				+ '<div class="form-check">'
				+ '<input class="form-check-input" type="radio" name="' + radioId + '" id="' + radioId + '-new" value="new">'
				+ '<label class="form-check-label" for="' + radioId + '-new">' + __('Create as a new -V(NNNN) variant') + '</label>'
				+ '</div>'
				+ '</div>'
			);
			$summary.find('input[name="' + radioId + '"]').on('change', function () {
				self.reuseExisting = ($(this).val() === 'reuse');
			});
		} else {
			$summary.append(
				'<div class="alert alert-secondary py-2 px-2 small">'
				+ __('No existing record matches. A new Configured record will be created on save.')
				+ '</div>'
			);
		}

		var $pricing = $('<div class="ill-desk-pricing"></div>');
		$body.append($pricing);
		if (root.IllDesk && typeof root.IllDesk.renderPricingBreakdown === 'function') {
			IllDesk.renderPricingBreakdown($pricing, this.validation);
		}

		var msgs = (this.lookupResult.messages || []).filter(function (m) { return m && m.text; });
		if (msgs.length) {
			var $m = $('<div class="ill-desk-messages mt-2"></div>');
			msgs.forEach(function (m) {
				var sev = m.severity || 'info';
				var cls = (sev === 'warning') ? 'alert-warning' : 'alert-info';
				$m.append($('<div></div>').addClass('alert ' + cls + ' py-1 px-2 small').text(m.text));
			});
			$body.append($m);
		}
	};

	DialogController.prototype.advanceFromCalculated = function () {
		// If reusing existing record, we can skip straight to BOM review using
		// preview_bom on the existing record.
		if (this.reuseExisting && this.lookupResult.existing_record) {
			this.renderBomReviewExisting();
		} else {
			// New record: BOM cannot be previewed without persisting. Show a
			// summary with the validation's anticipated items where possible
			// (engine returns BOM-relevant lists), and let user proceed to
			// Save & Apply which will persist + write to row.
			this.renderBomReviewProspective();
		}
	};

	// ── Step 4: BOM Review ───────────────────────────────────────────
	DialogController.prototype.renderBomReviewExisting = function () {
		this.state = 'bomReview';
		this.renderStepIndicator();
		this.setPrimaryLabel(__('Save & Apply to Row'), __('Back'), this.renderCalculated.bind(this));

		var $body = this.body$();
		$body.html('<div class="text-muted small">' + __('Loading BOM...') + '</div>');

		var self = this;
		var args = { product_type: this.productType };
		if (this.productType === 'Linear Fixture') {
			args.configured_fixture = this.lookupResult.existing_record;
		} else {
			args.configured_tape_neon = this.lookupResult.existing_record;
		}
		frappe.call({
			method: API + 'preview_bom',
			args: args,
			callback: function (r) {
				$body.html('');
				var msg = r.message || {};
				IllDesk.renderBOMReview($body, msg.items || [], {
					title: __('BOM for {0}', [self.lookupResult.existing_record]),
					messages: msg.messages || [],
					empty_message: __('No BOM rows found for the existing record.')
				});
			}
		});
	};

	DialogController.prototype.renderBomReviewProspective = function () {
		this.state = 'bomReview';
		this.renderStepIndicator();
		this.setPrimaryLabel(__('Save & Apply to Row'), __('Back'), this.renderCalculated.bind(this));

		var $body = this.body$();
		$body.html('');

		// Best-effort prospective BOM rows from the validation response. The
		// engines return resolved item lists (profile, tape, lens, endcaps,
		// drivers, leader cables) under various keys. We surface what we can
		// and note that the final BOM is generated on Save.
		var v = this.validation || {};
		var prospective = collectProspectiveItems(v);

		$body.append(
			'<div class="alert alert-info py-2 px-2 small mb-2">'
			+ __('A new Configured record will be created and its BOM generated on Save & Apply.')
			+ '</div>'
		);
		IllDesk.renderBOMReview($body, prospective, {
			title: __('Prospective BOM components'),
			empty_message: __('Prospective component list not available; full BOM will be generated on save.')
		});
	};

	function collectProspectiveItems(validation) {
		var rows = [];
		var seen = {};
		function push(item_code, item_name, qty, uom) {
			if (!item_code || seen[item_code]) return;
			seen[item_code] = true;
			rows.push({ item_code: item_code, item_name: item_name || item_code, qty: qty || 1, uom: uom || 'Nos' });
		}
		var c = validation.computed || {};
		var bom = validation.bom || validation.bom_preview || c.bom || c.bom_items || [];
		if (Array.isArray(bom)) {
			bom.forEach(function (it) {
				push(it.item_code, it.item_name || it.description, it.qty, it.uom || it.stock_uom);
			});
		}
		var components = validation.components || c.components || {};
		Object.keys(components || {}).forEach(function (key) {
			var v = components[key];
			if (Array.isArray(v)) {
				v.forEach(function (it) {
					if (it && (it.item_code || it.item)) {
						push(it.item_code || it.item, it.item_name || it.description, it.qty, it.uom);
					}
				});
			} else if (v && (v.item_code || v.item)) {
				push(v.item_code || v.item, v.item_name || v.description, v.qty, v.uom);
			}
		});
		return rows;
	}

	DialogController.prototype.advanceFromBomReview = function () {
		if (this.reuseExisting && this.lookupResult.existing_record) {
			this.applyExistingRecord();
		} else {
			this.saveAndApply();
		}
	};

	// ── Save / Apply ─────────────────────────────────────────────────
	DialogController.prototype.applyExistingRecord = function () {
		var self = this;
		var args = {
			product_type: this.productType,
			parent_doctype: this.frm.doctype,
			parent_name: this.frm.doc.name,
			row_name: selectedItemRowName(this.frm),
			qty: this.qty
		};
		if (this.productType === 'Linear Fixture') {
			args.configured_fixture = this.lookupResult.existing_record;
		} else {
			args.configured_tape_neon = this.lookupResult.existing_record;
		}
		frappe.call({
			method: QOC_API + 'apply_existing_configured_product',
			args: args,
			freeze: true,
			freeze_message: __('Applying to row...'),
			callback: function (r) {
				var msg = r.message || {};
				if (!msg.success) {
					frappe.msgprint({ title: __('Apply failed'), indicator: 'red',
						message: msg.error || __('Could not apply configured product to row.') });
					return;
				}
				frappe.show_alert({
					message: __('Applied: {0}', [msg.item_code || self.lookupResult.existing_record]),
					indicator: 'green'
				});
				self.dialog.hide();
				self.frm.reload_doc();
			}
		});
	};

	DialogController.prototype.saveAndApply = function () {
		var self = this;
		frappe.call({
			method: API + 'save_and_apply',
			args: {
				parent_doctype: this.frm.doctype,
				parent_name: this.frm.doc.name,
				product_type: this.productType,
				payload_json: JSON.stringify(this.payload),
				parent_configured_fixture: this.parentConfiguredFixture,
				parent_configured_tape_neon: this.parentConfiguredTapeNeon,
				tape_neon_template: this.tapeNeonTemplate,
				row_name: selectedItemRowName(this.frm),
				qty: this.qty,
				variant_origin: 'Quotation Tool'
			},
			freeze: true,
			freeze_message: __('Saving & applying...'),
			callback: function (r) {
				var msg = r.message || {};
				if (!msg.success) {
					frappe.msgprint({ title: __('Save failed'), indicator: 'red',
						message: msg.error || __('Configured product save failed.') });
					return;
				}
				frappe.show_alert({
					message: __('Saved & applied: {0}', [msg.item_code]),
					indicator: 'green'
				});
				self.dialog.hide();
				self.frm.reload_doc();
			}
		});
	};

}(window));
