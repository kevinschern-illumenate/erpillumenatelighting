/**
 * Fixture Configurator — Guided Wizard (scoped IllConfigurator.Fixture)
 *
 * Runs on the SAME engine as the Multi-Segment Coordinator so both modes
 * produce identical ilL-Configured-Fixture records:
 *
 *   options    → configurator_engine.get_cascading_options_for_template
 *                 get_ccts_for_template / get_delivered_outputs_for_template /
 *                 auto_select_tape_for_configuration
 *   calculate  → configurator_engine.validate_and_quote_multisegment_with_output
 *                 (falls back to validate_and_quote_multisegment with the
 *                 auto-selected tape_offering_id)
 *   save       → portal.save_configured_fixture_to_schedule (portal page)
 *                 or context.saveHandler(payload) (desk Quotation / Sales Order
 *                 dialog → desk_configurator.build_configured_line)
 *
 * All DOM lookups use `this.$()` (scoped to the configurator root element) so
 * multiple instances can coexist (portal page + desk dialog).
 *
 * Public API:
 *   var inst = new IllConfigurator.Fixture(rootEl, context);
 *   inst.init();
 *   inst.resetConfiguration();
 *   inst.validateConfiguration();
 *   inst.addToSchedule();
 *
 * context:
 *   schedule_name, project_name, line_idx, can_save, show_pricing,
 *   is_system_manager, product_slug, saveHandler(payload) (desk), qty
 */
(function (root) {
	'use strict';

	if (!root.IllConfigurator) {
		console.error('shared_configurator.js must load before fixture_steps.js');
		return;
	}

	var Base = root.IllConfigurator.Base;
	var escapeHtml = root.IllConfigurator.escapeHtml;
	var ENGINE = 'illumenate_lighting.illumenate_lighting.api.configurator_engine.';
	var PORTAL = 'illumenate_lighting.illumenate_lighting.api.portal.';
	var MM_PER_INCH = 25.4;
	var MM_PER_FOOT = 304.8;
	var MULTI_CCT_SPECTRUM_TYPES = ['Tunable White', 'Dim to Warm', 'RGB+TW', 'RGBTW', 'RGB+W', 'RGBW'];

	// Option keys returned by get_cascading_options_for_template → form fields.
	var OPTION_FIELDS = {
		led_packages: 'led_package_code',
		environment_ratings: 'environment_rating_code',
		ccts: 'cct_code',
		lens_appearances: 'lens_appearance_code',
		mountings: 'mounting_method_code',
		finishes: 'finish_code'
	};
	var STEP_FIELDS = [
		'fixture_template_code', 'led_package_code', 'environment_rating_code', 'cct_code',
		'lens_appearance_code', 'delivered_output_value', 'mounting_method_code', 'finish_code', 'segments'
	];
	var SUMMARY_LABELS = {
		led_package_code: __('LED Package'),
		environment_rating_code: __('Environment'),
		cct_code: __('CCT'),
		lens_appearance_code: __('Lens'),
		delivered_output_value: __('Output'),
		mounting_method_code: __('Mounting'),
		finish_code: __('Finish')
	};

	function Fixture(rootEl, context) {
		Base.call(this, rootEl, context);
		this.$root.addClass('ill-configurator ill-configurator-fixture');
		this.productSlug = (context && context.product_slug) || null;
		this.templateOptions = null;
		this.isMultiCCT = false;
		this.isPopulating = false;
		this.segmentCount = 0;
		this.currentResult = null;
		this.lastValidation = null;
		this.scheduleTarget = null;
		this.templatePicker = null;
		this.isInitialized = false;
		this.restoreApplied = false;
	}
	Fixture.prototype = Object.create(Base.prototype);
	Fixture.prototype.constructor = Fixture;
	Fixture.prototype.exportRequest = function () {
		var selections = this._gatherAllSelections();
		return {family: 'Linear Fixture', template: selections.fixture_template_code, selections: selections};
	};

	// ────────────────────────────────────────────────────────────────
	// Lifecycle
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.init = function () {
		var self = this;
		this._bindEvents();
		this._initTemplatePicker();
		this._initScheduleContext();

		var $select = this.$('#fixtureTemplateSelect');
		var preselected = $select.val();
		var initial = this.context.initial_request;
		if (initial) {
			preselected = initial.template || (initial.selections || {}).fixture_template_code || preselected;
			$select.val(preselected);
		}
		if (!preselected && this.productSlug) {
			// Product slugs from Webflow may equal the template code.
			if ($select.find('option[value="' + this.productSlug + '"]').length) {
				$select.val(this.productSlug);
				preselected = this.productSlug;
			}
		}
		if (preselected) {
			// Defer so the template picker has synced its selected state.
			setTimeout(function () { $select.trigger('change'); }, 0);
		}
	};

	Fixture.prototype._usesSaveHandler = function () {
		return typeof this.context.saveHandler === 'function';
	};

	Fixture.prototype._bindEvents = function () {
		var self = this;

		// Template selection (driven by the card picker or the fallback select)
		this.$('#fixtureTemplateSelect').on('change' + '.' + self.instanceId, function () {
			self._onTemplateSelected($(this).val());
		});

		// Option pills — delegated so re-rendered pills keep working.
		this.$root.on('click' + '.' + self.instanceId, '.pill-selector .pill', function (e) {
			e.preventDefault();
			var $pill = $(this);
			var $selector = $pill.closest('.pill-selector');
			var fieldName = $selector.data('field');
			var $select = $selector.siblings('select[name="' + fieldName + '"]').first();
			if (!$select.length) $select = $pill.closest('.form-group, .config-section').find('select[name="' + fieldName + '"]').first();
			$selector.find('.pill').removeClass('active');
			$pill.addClass('active');
			if ($select.length) $select.val(String($pill.attr('data-value'))).trigger('change');
		});

		// Mobile fallback selects → mirror to pills.
		this.$root.on('change' + '.' + self.instanceId, 'select.select-fallback', function () {
			var $select = $(this);
			var fieldName = $select.attr('name');
			var $selector = $select.siblings('.pill-selector[data-field="' + fieldName + '"]').first();
			if (!$selector.length) $selector = $select.closest('.form-group, .config-section').find('.pill-selector[data-field="' + fieldName + '"]').first();
			$selector.find('.pill').removeClass('active');
			$selector.find('.pill[data-value="' + $select.val() + '"]').addClass('active');
		});

		// Cascading option handlers (same dependency graph as the coordinator).
		this.$name('led_package_code').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._detectMultiCCT($(this).val());
			self._updateCCTOptions();
			self._updateDeliveredOutputs();
			self._afterChange();
		});
		this.$name('environment_rating_code').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._updateCCTOptions();
			self._updateDeliveredOutputs();
			self._afterChange();
		});
		this.$name('cct_code').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._updateDeliveredOutputs();
			self._afterChange();
		});
		this.$name('lens_appearance_code').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._updateDeliveredOutputs();
			self._afterChange();
		});
		this.$name('delivered_output_value').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._autoSelectTape();
			self._afterChange();
		});
		this.$name('mounting_method_code').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._afterChange();
		});
		this.$name('finish_code').on('change' + '.' + self.instanceId, function () {
			if (self.isPopulating) return;
			self._autoResolveEndcapColor();
			self._afterChange();
		});

		// Segment cards (delegated).
		this.$root.on('click' + '.' + self.instanceId, '.segment-card .end-type-btn', function () {
			self._setEndType($(this).closest('.segment-card'), $(this).attr('data-end-type'));
		});
		this.$root.on('click' + '.' + self.instanceId, '.segment-card [data-action="remove-segment"]', function () {
			self._removeSegment($(this).closest('.segment-card'));
		});
		this.$root.on('change' + '.' + self.instanceId, '.segment-card select[name="length_unit"]', function () {
			var $card = $(this).closest('.segment-card');
			self._convertSegmentLength($card, $(this).val(), $card.data('prevUnit') || 'in');
			$card.data('prevUnit', $(this).val());
			self._afterChange();
		});
		this.$root.on('input' + '.' + self.instanceId + ' ' + 'change' + '.' + self.instanceId, '.segment-card input, .segment-card select', this.debounce(function () {
			self._afterChange();
		}, 250));
		this.$root.on('change' + '.' + self.instanceId, '.segment-card select[name="start_power_feed_type"], .segment-card select[name="start_feed_direction"], .segment-card input[name="start_leader_cable_length_in"], .segment-card select[name="end_power_feed_type"], .segment-card select[name="end_feed_direction"], .segment-card input[name="end_jumper_cable_length_in"]', function () {
			self._propagateInheritedStarts();
		});

		// Power supply / override.
		this.$('#includePowerSupply').on('change' + '.' + self.instanceId, function () { self._afterChange(); });
		this.$('#overrideMaxRunCheck').on('change' + '.' + self.instanceId, function () {
			var on = $(this).is(':checked');
			self.$('#overrideMaxRunGroup').toggle(on);
			self.$('#overrideMaxRunWarning').toggle(on);
			self._afterChange();
		});
		this.$('#overrideMaxRunInput').on('input' + '.' + self.instanceId + ' ' + 'change' + '.' + self.instanceId, this.debounce(function () { self._afterChange(); }, 250));

		// Action buttons.
		this.$('[data-action="reset"]').on('click' + '.' + self.instanceId, function () { self.resetConfiguration(); });
		this.$('[data-action="validate"]').on('click' + '.' + self.instanceId, function () { self.validateConfiguration(); });
		this.$('[data-action="add-to-schedule"]').on('click' + '.' + self.instanceId, function () { self.addToSchedule(); });
		this.$('[data-action="build-item"]').on('click' + '.' + self.instanceId, function () { self.buildFixtureAndItem(); });
		this.$('[data-action="copy-part-number"]').on('click' + '.' + self.instanceId, function () { self._copy(self.$('#partNumberValue').text()); });
		this.$('[data-action="copy-description"]').on('click' + '.' + self.instanceId, function () { self._copy(self.$('#partDescriptionValue').text()); });
		this.$('[data-action="copy-both"]').on('click' + '.' + self.instanceId, function () {
			self._copy(self.$('#partNumberValue').text() + '\n' + self.$('#partDescriptionValue').text());
		});
	};

	Fixture.prototype._afterChange = function () {
		this._invalidateResult();
		this._updateProgress();
		this._updateSummary();
		this._updateButtons();
	};

	// ────────────────────────────────────────────────────────────────
	// Template picker
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._initTemplatePicker = function () {
		var $picker = this.$('#fixtureTemplatePicker');
		var $select = this.$('#fixtureTemplateSelect');
		if (!$picker.length || !$select.length) return;
		this.templatePicker = root.IllConfigurator.renderTemplateCards({
			$container: $picker,
			$select: $select
		});
	};

	Fixture.prototype._onTemplateSelected = function (templateCode) {
		var self = this;
		this._invalidateResult();
		this._requests = Object.create(null);
		if (!templateCode) {
			this.templateOptions = null;
			this.isInitialized = false;
			this.$('#templateOptions').hide();
			this.$('#actionButtons').hide();
			this._clearSegments();
			this._updateProgress();
			this._updateSummary();
			this._updateButtons();
			return;
		}

		this.loadPowerOptions('ilL-Fixture-Template', templateCode);
		this.$('#templateOptions').show();
		this.$('#templateOptions .pill-selector').html(
			'<span class="text-muted"><i class="fa fa-spinner fa-spin"></i> ' + __('Loading options…') + '</span>'
		);

		self.request({
			method: ENGINE + 'get_cascading_options_for_template',
			args: { fixture_template_code: templateCode },
			callback: function (r) {
				var msg = r.message || {};
				if (!msg.success) {
					frappe.msgprint({ title: __('Error Loading Options'), indicator: 'red',
						message: msg.error || __('Unexpected response from server. Please try again.') });
					self.$('#templateOptions').hide();
					return;
				}
				self.templateOptions = msg.options || {};
				self.isInitialized = true;
				self._populateOptions(self.templateOptions);
				if (!self.segmentCount) self._addSegment(true);
				self.$('.segment-card').each(function () { self._populateSegmentFeedOptions($(this)); });
				self.$('#actionButtons').show();
				self._restoreRequest();
				self._afterChange();
			},
			error: function () {
				frappe.msgprint({ title: __('Error Loading Options'), indicator: 'red',
					message: __('Failed to load configuration options. Please refresh the page and try again.') });
				self.$('#templateOptions').hide();
			}
		});
	};

	Fixture.prototype.restoreGeometry = function (geometry) {
		var self = this;
		this._clearSegments();
		(geometry.segments || []).forEach(function (segment, index) { self.restoreSegment(self._addSegment(index === 0), segment, 'linear'); });
		this._propagateInheritedStarts();
		this._afterChange();
	};

	Fixture.prototype._restoreRequest = function () {
		var request = this.context.initial_request;
		if (!request || this.restoreApplied) return;
		this.restoreApplied = true;
		var values = request.selections || {}, fields = {}, self = this;
		['led_package_code', 'environment_rating_code', 'cct_code', 'lens_appearance_code', 'finish_code', 'mounting_method_code', 'delivered_output_value', 'tape_offering_id'].forEach(function (key) {
			if (values[key] != null) fields['[name="' + key + '"]'] = values[key];
		});
		this.queueRestoreFields(fields);
		this.restorePower(values);
		var segments = request.segments || values.segments || values.segments_json || [];
		if (typeof segments === 'string') segments = JSON.parse(segments);
		if (segments.length) {
			this._clearSegments();
			segments.forEach(function (segment, index) { self.restoreSegment(self._addSegment(index === 0), segment, 'linear'); });
			this._propagateInheritedStarts();
		}
	};

	// ────────────────────────────────────────────────────────────────
	// Options (mirrors coordinator populateOptions / populatePillSelector)
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._populatePill = function (fieldName, options, opts) {
		opts = opts || {};
		var $container = this.$('.pill-selector[data-field="' + fieldName + '"]').first();
		var $select = this.$name(fieldName).filter('select').first();
		var previous = opts.keepValue === false ? '' : $select.val();

		$container.empty();
		$select.empty().append('<option value="">' + __('Select...') + '</option>');

		if (!options || !options.length) {
			$container.append('<span class="text-muted">' + __('No options available') + '</span>');
			return { restored: false, autoSelected: false };
		}

		var restored = false;
		options.forEach(function (opt) {
			var label = opt.label || opt.value;
			var $pill = $('<button type="button" class="pill"></button>')
				.attr('data-value', opt.value)
				.text(label);
			if (opt.transmission !== undefined && opt.transmission !== null && opt.transmission !== 100 && fieldName === 'lens_appearance_code') {
				$pill.append(' <small class="text-muted">' + escapeHtml(opt.transmission) + '%</small>');
			}
			if (previous !== '' && previous !== null && String(opt.value) === String(previous)) {
				$pill.addClass('active');
				restored = true;
			}
			$container.append($pill);
			$select.append($('<option></option>').val(opt.value).text(label));
		});

		if (restored) {
			$select.val(previous);
			return { restored: true, autoSelected: false };
		}
		if (options.length === 1 && opts.autoSelectSingle !== false) {
			$select.val(options[0].value);
			$container.find('.pill').first().addClass('active');
			if (!this.isPopulating) $select.trigger('change');
			return { restored: false, autoSelected: true };
		}
		return { restored: false, autoSelected: false };
	};

	Fixture.prototype._populateOptions = function (options) {
		var self = this;
		this.isPopulating = true;
		Object.keys(OPTION_FIELDS).forEach(function (key) {
			self._populatePill(OPTION_FIELDS[key], options[key] || [], { keepValue: false, autoSelectSingle: false });
		});
		this._populatePill('delivered_output_value', [], { keepValue: false });
		this.$('#outputHint').show();
		this.$('#outputHelpText').text('');
		this.$name('tape_offering_id').val('');
		this.$name('endcap_color_code').val('');
		this.$('#endcapColorDisplay').hide();

		// Detect multi-CCT packages (Tunable White etc.) up front.
		this.isMultiCCT = false;
		(options.led_packages || []).forEach(function (pkg) {
			if (pkg.spectrum_type && MULTI_CCT_SPECTRUM_TYPES.indexOf(pkg.spectrum_type) !== -1) self.isMultiCCT = true;
		});
		this.isPopulating = false;

		// Auto-select single-option fields, letting cascades run.
		Object.keys(OPTION_FIELDS).forEach(function (key) {
			var list = options[key] || [];
			if (list.length === 1) {
				var fieldName = OPTION_FIELDS[key];
				self.$name(fieldName).val(list[0].value).trigger('change');
				self.$('.pill-selector[data-field="' + fieldName + '"] .pill').first().addClass('active');
			}
		});
		this._autoResolveEndcapColor();
	};

	Fixture.prototype._detectMultiCCT = function (selectedPkg) {
		var self = this;
		this.isMultiCCT = false;
		((this.templateOptions && this.templateOptions.led_packages) || []).forEach(function (pkg) {
			if (pkg.value === selectedPkg && pkg.spectrum_type && MULTI_CCT_SPECTRUM_TYPES.indexOf(pkg.spectrum_type) !== -1) {
				self.isMultiCCT = true;
			}
		});
	};

	Fixture.prototype._updateCCTOptions = function () {
		var self = this;
		delete this._requests[ENGINE + 'get_ccts_for_template'];
		var templateCode = this.$('#fixtureTemplateSelect').val();
		if (!templateCode) return;
		self.request({
			method: ENGINE + 'get_ccts_for_template',
			args: {
				fixture_template_code: templateCode,
				led_package_code: this.$name('led_package_code').val() || null,
				environment_rating_code: this.$name('environment_rating_code').val() || null
			},
			callback: function (r) {
				var msg = r.message || {};
				if (!msg.success) return;
				var ccts = msg.ccts || [];
				if (ccts.length) {
					self._populatePill('cct_code', ccts);
				} else if (msg.is_multi_cct) {
					self._populatePill('cct_code', []);
				}
				self._afterChange();
			}
		});
	};

	Fixture.prototype._updateDeliveredOutputs = function () {
		var self = this;
		delete this._requests[ENGINE + 'get_delivered_outputs_for_template'];
		var templateCode = this.$('#fixtureTemplateSelect').val();
		var ledPackage = this.$name('led_package_code').val();
		var environment = this.$name('environment_rating_code').val();
		var cct = this.$name('cct_code').val();
		var lens = this.$name('lens_appearance_code').val();
		var cctRequired = !this.isMultiCCT;

		if (!templateCode || !ledPackage || !environment || !lens || (cctRequired && !cct)) {
			this._populatePill('delivered_output_value', [], { keepValue: false });
			this.$('#outputHint').show();
			this.$('#outputHelpText').text('');
			this.$name('tape_offering_id').val('');
			return;
		}

		self.request({
			method: ENGINE + 'get_delivered_outputs_for_template',
			args: {
				fixture_template_code: templateCode,
				led_package_code: ledPackage,
				environment_rating_code: environment,
				cct_code: cct || null,
				lens_appearance_code: lens
			},
			callback: function (r) {
				var msg = r.message || {};
				if (msg.success) {
					self.$('#outputHint').hide();
					var res = self._populatePill('delivered_output_value', msg.delivered_outputs || []);
					var transmission = msg.lens_transmission_pct || 100;
					self.$('#outputHelpText').text(__('Output adjusted for {0}% lens transmission', [Number(transmission).toFixed(0)]));
					if (res.restored) self._autoSelectTape();
				} else {
					self._populatePill('delivered_output_value', [], { keepValue: false });
					self.$('#outputHint').show().text(msg.error || __('No output levels available for this combination.'));
					self.$name('tape_offering_id').val('');
				}
				self._afterChange();
			}
		});
	};

	Fixture.prototype._autoSelectTape = function () {
		var self = this;
		delete this._requests[ENGINE + 'auto_select_tape_for_configuration'];
		var templateCode = this.$('#fixtureTemplateSelect').val();
		var ledPackage = this.$name('led_package_code').val();
		var environment = this.$name('environment_rating_code').val();
		var cct = this.$name('cct_code').val();
		var lens = this.$name('lens_appearance_code').val();
		var output = this.$name('delivered_output_value').val();
		var cctRequired = !this.isMultiCCT;
		if (!templateCode || !ledPackage || !environment || !lens || !output || (cctRequired && !cct)) {
			this.$name('tape_offering_id').val('');
			return;
		}
		self.request({
			method: ENGINE + 'auto_select_tape_for_configuration',
			args: {
				fixture_template_code: templateCode,
				led_package_code: ledPackage,
				environment_rating_code: environment,
				cct_code: cct || null,
				lens_appearance_code: lens,
				delivered_output_value: parseInt(output, 10)
			},
			callback: function (r) {
				var msg = r.message || {};
				if (msg.success && msg.tape_offering_id) {
					self.$name('tape_offering_id').val(msg.tape_offering_id);
				} else {
					self.$name('tape_offering_id').val('');
					if (msg.error) frappe.msgprint({ title: __('Tape Selection'), message: msg.error, indicator: 'orange' });
				}
				self._updateButtons();
			}
		});
	};

	Fixture.prototype._autoResolveEndcapColor = function () {
		var finish = this.$name('finish_code').val();
		var opts = this.templateOptions || {};
		var $display = this.$('#endcapColorDisplay');
		var $hidden = this.$name('endcap_color_code');
		if (!finish || !opts.finish_endcap_color_map) {
			$hidden.val('');
			$display.hide();
			return;
		}
		var mapping = opts.finish_endcap_color_map[finish];
		if (mapping) {
			$hidden.val(mapping.endcap_color_code);
			this.$('#endcapColorLabel').text(__('Endcap Color: {0}', [mapping.endcap_color_label]));
			$display.show();
		} else if (opts.endcap_colors && opts.endcap_colors.length) {
			$hidden.val(opts.endcap_colors[0].value);
			this.$('#endcapColorLabel').text(__('Endcap Color: {0} (default)', [opts.endcap_colors[0].label]));
			$display.show();
		} else {
			$hidden.val('');
			$display.hide();
		}
	};

	// ────────────────────────────────────────────────────────────────
	// Segments (mirrors coordinator addSegment / setEndType / collectSegments)
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._segmentTemplate = function () {
		var tpl = this.$('template.ill-segment-template')[0];
		return tpl ? tpl.content : null;
	};

	Fixture.prototype._addSegment = function (isFirst) {
		var content = this._segmentTemplate();
		if (!content) return null;
		this.segmentCount++;
		var $card = $(content.cloneNode(true)).find('.segment-card').first();
		if (!$card.length) $card = $(content.firstElementChild.cloneNode(true));
		$card.attr('data-segment-index', this.segmentCount);
		$card.find('.segment-number').text(this.segmentCount);
		$card.data('prevUnit', 'in');

		if (isFirst) {
			$card.find('.first-segment-start').show();
			$card.find('.inherited-start').hide();
		} else {
			$card.find('.first-segment-start').hide();
			$card.find('.inherited-start').show();
			$card.find('.remove-segment-btn').show();
		}

		this.$('#segmentsList').append($card);
		this._populateSegmentFeedOptions($card);
		this._setEndType($card, 'Endcap', true);
		this._propagateInheritedStarts();
		this._refreshSegmentChrome();
		return $card;
	};

	Fixture.prototype._removeSegment = function ($card) {
		var self = this;
		if (!$card || !$card.length) return;
		$card.remove();
		// Renumber and make sure the (new) last segment ends with an endcap.
		this.segmentCount = 0;
		this.$('.segment-card').each(function () {
			self.segmentCount++;
			$(this).attr('data-segment-index', self.segmentCount).find('.segment-number').text(self.segmentCount);
		});
		var $last = this.$('.segment-card').last();
		if ($last.length && $last.find('[name="end_type"]').val() === 'Jumper') this._setEndType($last, 'Endcap', true);
		this._propagateInheritedStarts();
		this._refreshSegmentChrome();
		this._afterChange();
	};

	Fixture.prototype._clearSegments = function () {
		this.$('#segmentsList').empty();
		this.segmentCount = 0;
		this._refreshSegmentChrome();
	};

	Fixture.prototype._setEndType = function ($card, type, silent) {
		if (!$card || !$card.length) return;
		$card.find('.end-type-btn').removeClass('active btn-secondary').addClass('btn-outline-secondary');
		$card.find('.end-type-btn[data-end-type="' + type + '"]').addClass('active');
		$card.find('[name="end_type"]').val(type);
		$card.find('.endcap-fields').toggle(type === 'Endcap');
		$card.find('.jumper-fields').toggle(type === 'Jumper');

		var isLast = $card.is(this.$('.segment-card').last());
		if (type === 'Jumper') {
			if (isLast) this._addSegment(false);
		} else if (isLast) {
			// Nothing to do: endcap on the last segment closes the fixture.
		} else {
			// Endcap on a middle segment removes everything after it.
			$card.nextAll('.segment-card').remove();
			this.segmentCount = this.$('.segment-card').length;
		}
		this._propagateInheritedStarts();
		this._refreshSegmentChrome();
		if (!silent) this._afterChange();
	};

	Fixture.prototype._refreshSegmentChrome = function () {
		var n = this.$('.segment-card').length;
		this.$('#segmentCountBadge').text(n === 1 ? __('1 segment') : __('{0} segments', [n]));
		var $last = this.$('.segment-card').last();
		this.$('#addSegmentHint').toggle(n > 0 && $last.find('[name="end_type"]').val() === 'Endcap');
	};

	Fixture.prototype._populateSegmentFeedOptions = function ($card) {
		var opts = this.templateOptions || {};
		var feedTypes = opts.power_feed_type || [];
		var feedDirs = (opts.feed_directions && opts.feed_directions.length) ? opts.feed_directions : [
			{ value: 'End', label: 'End' }, { value: 'Back', label: 'Back' },
			{ value: 'Left', label: 'Left' }, { value: 'Right', label: 'Right' }
		];

		function fill(fieldName, items) {
			var $select = $card.find('select[name="' + fieldName + '"]');
			var $pills = $card.find('.pill-selector[data-field="' + fieldName + '"]');
			var prev = $select.val();
			$select.empty().append('<option value="">' + __('Select...') + '</option>');
			$pills.empty();
			if (!items.length) {
				$pills.append('<span class="text-muted small">' + __('No options available') + '</span>');
				return;
			}
			items.forEach(function (o) {
				$select.append($('<option></option>').val(o.value).text(o.label || o.value));
				$pills.append($('<button type="button" class="pill pill-sm"></button>').attr('data-value', o.value).text(o.label || o.value));
			});
			var keep = prev && items.some(function (o) { return String(o.value) === String(prev); });
			var value = keep ? prev : (items.length === 1 ? items[0].value : '');
			if (value !== '') {
				$select.val(value);
				$pills.find('.pill[data-value="' + value + '"]').addClass('active');
			}
		}

		fill('start_feed_direction', feedDirs);
		fill('start_power_feed_type', feedTypes);
		fill('end_feed_direction', feedDirs);
		fill('end_power_feed_type', feedTypes);
	};

	// Non-first segments inherit their start from the prior segment's jumper.
	Fixture.prototype._propagateInheritedStarts = function () {
		var $cards = this.$('.segment-card');
		$cards.each(function (i) {
			if (i === 0) return;
			var $prior = $cards.eq(i - 1);
			var card = this;
			card.dataset.inheritedFeedDirection = $prior.find('[name="end_feed_direction"]').val() || '';
			card.dataset.inheritedPowerFeedType = $prior.find('[name="end_power_feed_type"]').val() || '';
			var jumperIn = parseFloat($prior.find('[name="end_jumper_cable_length_in"]').val()) || 12;
			card.dataset.inheritedCableLength = Math.round(jumperIn * MM_PER_INCH);
			var text = __('Continues from segment {0}', [i]);
			if (card.dataset.inheritedPowerFeedType) text += ' · ' + card.dataset.inheritedPowerFeedType;
			if (card.dataset.inheritedFeedDirection) text += ' · ' + card.dataset.inheritedFeedDirection;
			text += ' · ' + __('{0}" jumper', [jumperIn]);
			$(card).find('.inherited-text').text(text);
		});
	};

	Fixture.prototype._convertSegmentLength = function ($card, newUnit, oldUnit) {
		if (newUnit === oldUnit) return;
		var $len = $card.find('[name="requested_length_mm"]');
		var $ft = $card.find('[name="length_feet"]');
		var $in = $card.find('[name="length_inches"]');
		var mm = this._segmentLengthMm($card, oldUnit);
		$card.find('.feet-inches-row').toggle(newUnit === 'ft_in');
		$len.closest('.length-input-group').find('input').toggle(newUnit !== 'ft_in');
		if (!mm) return;
		if (newUnit === 'mm') $len.val(Math.round(mm));
		else if (newUnit === 'in') $len.val((mm / MM_PER_INCH).toFixed(1));
		else {
			var totalIn = mm / MM_PER_INCH;
			$ft.val(Math.floor(totalIn / 12));
			$in.val((totalIn % 12).toFixed(1));
		}
	};

	Fixture.prototype._segmentLengthMm = function ($card, unit) {
		unit = unit || $card.find('[name="length_unit"]').val();
		if (unit === 'mm') return parseFloat($card.find('[name="requested_length_mm"]').val()) || 0;
		if (unit === 'ft_in') {
			var feet = parseFloat($card.find('[name="length_feet"]').val()) || 0;
			var inches = parseFloat($card.find('[name="length_inches"]').val()) || 0;
			return Math.round((feet * 12 + inches) * MM_PER_INCH);
		}
		return Math.round((parseFloat($card.find('[name="requested_length_mm"]').val()) || 0) * MM_PER_INCH);
	};

	Fixture.prototype._collectSegments = function () {
		var self = this;
		var segments = [];
		this.$('.segment-card').each(function (index) {
			var $card = $(this);
			var segment = {
				segment_index: index + 1,
				requested_length_mm: self._segmentLengthMm($card),
				end_type: $card.find('[name="end_type"]').val() || 'Endcap'
			};
			if (index === 0) {
				segment.start_feed_direction = $card.find('[name="start_feed_direction"]').val() || '';
				segment.start_power_feed_type = $card.find('[name="start_power_feed_type"]').val() || '';
				var leaderIn = Number($card.find('[name="start_leader_cable_length_in"]').val());
				segment.start_leader_cable_length_mm = Math.round(leaderIn * MM_PER_INCH);
			} else {
				segment.start_feed_direction = this.dataset.inheritedFeedDirection || '';
				segment.start_power_feed_type = this.dataset.inheritedPowerFeedType || '';
				segment.start_leader_cable_length_mm = Number(this.dataset.inheritedCableLength || 0);
			}
			if (segment.end_type === 'Jumper') {
				segment.end_feed_direction = $card.find('[name="end_feed_direction"]').val() || '';
				segment.end_power_feed_type = $card.find('[name="end_power_feed_type"]').val() || '';
				var jumperIn = parseFloat($card.find('[name="end_jumper_cable_length_in"]').val()) || 12;
				segment.end_jumper_cable_length_mm = Math.round(jumperIn * MM_PER_INCH);
			}
			segments.push(segment);
		});
		return segments;
	};

	Fixture.prototype._segmentsComplete = function () {
		var segments = this._collectSegments();
		if (!segments.length) return false;
		var first = segments[0];
		if (!first.start_power_feed_type || !first.start_feed_direction) return false;
		for (var i = 0; i < segments.length; i++) {
			var s = segments[i];
			if (!s.requested_length_mm || s.requested_length_mm <= 0) return false;
			if (s.end_type === 'Jumper' && !s.end_power_feed_type) return false;
		}
		return segments[segments.length - 1].end_type === 'Endcap';
	};

	// ────────────────────────────────────────────────────────────────
	// Progress / summary / buttons
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._isStepCompleted = function (step) {
		if (step === 'segments') return this._segmentsComplete();
		if (step === 'fixture_template_code') return !!this.$('#fixtureTemplateSelect').val();
		return !!this.$name(step).val();
	};

	Fixture.prototype._updateProgress = function () {
		var self = this;
		var completed = 0;
		var foundActive = false;
		STEP_FIELDS.forEach(function (step, index) {
			var $el = self.$('.progress-step[data-step="' + step + '"]');
			var done = self._isStepCompleted(step);
			$el.toggleClass('completed', done).removeClass('active');
			$el.find('.step-number').text(done ? '\u2713' : (index + 1));
			if (done) completed++;
			else if (!foundActive) { $el.addClass('active'); foundActive = true; }
		});
		this.$('#progressBadge').text(Math.round((completed / STEP_FIELDS.length) * 100) + '%');
	};

	Fixture.prototype._optionLabel = function (fieldName) {
		var $select = this.$name(fieldName).filter('select').first();
		var val = $select.val();
		if (!val) return '';
		var text = $select.find('option:selected').text();
		if (fieldName === 'delivered_output_value') return text || (val + ' lm/ft');
		return text || val;
	};

	Fixture.prototype._updateSummary = function () {
		var self = this;
		var $list = this.$('#summaryList');
		var $placeholder = this.$('#summaryPlaceholder');
		var items = [];

		var templateCode = this.$('#fixtureTemplateSelect').val();
		if (templateCode) {
			var $opt = this.$('#fixtureTemplateSelect option:selected');
			items.push({ label: __('Template'), value: ($opt.attr('data-name') || templateCode) });
		}
		Object.keys(SUMMARY_LABELS).forEach(function (f) {
			var label = self._optionLabel(f);
			if (label) items.push({ label: SUMMARY_LABELS[f], value: label });
		});
		var endcap = this.$name('endcap_color_code').val();
		if (endcap) items.push({ label: __('Endcap Color'), value: this.$('#endcapColorLabel').text().replace(/^.*?:\s*/, '') || endcap });

		var segments = this._collectSegments();
		var totalMm = 0;
		segments.forEach(function (s) { totalMm += s.requested_length_mm || 0; });
		if (totalMm > 0) {
			items.push({
				label: segments.length > 1 ? __('Total Length ({0} segments)', [segments.length]) : __('Length'),
				value: (totalMm / MM_PER_INCH).toFixed(1) + '" (' + (totalMm / MM_PER_FOOT).toFixed(2) + ' ft)'
			});
		}
		if (segments.length && segments[0].start_power_feed_type) {
			var feed = segments[0].start_power_feed_type;
			if (segments[0].start_feed_direction) feed += ' · ' + segments[0].start_feed_direction;
			items.push({ label: __('Power Feed'), value: feed });
		}
		if (!this.$('#includePowerSupply').is(':checked')) items.push({ label: __('Power Supply'), value: __('Excluded') });
		var override = this._getOverrideMaxRunFt();
		if (override !== '') items.push({ label: __('Max Run Override'), value: override + ' ft' });

		if (!items.length) {
			$placeholder.show();
			$list.hide().empty();
			return;
		}
		$placeholder.hide();
		$list.empty().show();
		items.forEach(function (item) {
			$list.append('<li class="list-group-item d-flex justify-content-between py-1 px-0">'
				+ '<span class="text-muted mr-2">' + escapeHtml(item.label) + '</span>'
				+ '<strong class="text-right">' + escapeHtml(item.value) + '</strong></li>');
		});
	};

	Fixture.prototype._requiredComplete = function () {
		var self = this;
		var required = ['led_package_code', 'environment_rating_code', 'lens_appearance_code',
			'delivered_output_value', 'mounting_method_code', 'finish_code'];
		if (!this.isMultiCCT) required.push('cct_code');
		if (!this.$('#fixtureTemplateSelect').val()) return false;
		for (var i = 0; i < required.length; i++) {
			if (!self.$name(required[i]).val()) return false;
		}
		return this._segmentsComplete();
	};

	Fixture.prototype._getOverrideMaxRunFt = function () {
		if (!this.$('#overrideMaxRunCheck').is(':checked')) return '';
		var val = parseFloat(this.$('#overrideMaxRunInput').val());
		return (!isNaN(val) && val > 0) ? val : '';
	};

	Fixture.prototype._updateButtons = function () {
		var ready = this.isInitialized && this._requiredComplete();
		this.$('#validateBtn').prop('disabled', !ready);

		var $status = this.$('#validationStatus');
		if (this.currentResult) {
			if (this.currentResult.is_valid) {
				$status.removeClass('badge-secondary badge-info badge-danger').addClass('badge-success').text(__('Valid'));
			} else {
				$status.removeClass('badge-secondary badge-info badge-success').addClass('badge-danger').text(__('Invalid'));
			}
		} else if (ready) {
			$status.removeClass('badge-secondary badge-success badge-danger').addClass('badge-info').text(__('Ready'));
		} else {
			$status.removeClass('badge-info badge-success badge-danger').addClass('badge-secondary').text(__('Incomplete'));
		}

		var valid = !!(this.currentResult && this.currentResult.is_valid);
		var canSave = valid && (this._usesSaveHandler() || (this._hasScheduleTarget() && this._canSaveToSchedule()));
		this.$('#addToScheduleBtn').prop('disabled', !canSave);
		this.$('#buildItemBtn').prop('disabled', !(valid && this.currentResult.configured_fixture_id));
	};

	Fixture.prototype._invalidateResult = function () {
		this.invalidateValidation();
		this.currentResult = null;
		this.lastValidation = null;
		this.$('#resultsPanel').hide();
		this.$('#validationMessages').hide();
		this.$('#messagesList').empty();
	};

	// ────────────────────────────────────────────────────────────────
	// Schedule target (portal page only; desk uses saveHandler)
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._initScheduleContext = function () {
		var self = this;
		if (this._usesSaveHandler()) return;
		this.scheduleTarget = root.IllConfigurator.bindScheduleContext({
			instance: this,
			context: this.context,
			onChange: function () { self._updateButtons(); }
		});
	};

	Fixture.prototype._hasScheduleTarget = function () {
		if (!this.scheduleTarget) return !!this.context.schedule_name;
		return this.scheduleTarget.hasTarget();
	};

	Fixture.prototype._canSaveToSchedule = function () {
		return this.scheduleTarget ? this.scheduleTarget.canSave : !!this.context.can_save;
	};

	// ────────────────────────────────────────────────────────────────
	// Engine payload
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._gatherAllSelections = function () {
		return {
			fixture_template_code: this.$('#fixtureTemplateSelect').val(),
			led_package_code: this.$name('led_package_code').val(),
			environment_rating_code: this.$name('environment_rating_code').val(),
			cct_code: this.$name('cct_code').val() || null,
			lens_appearance_code: this.$name('lens_appearance_code').val(),
			delivered_output_value: this.$name('delivered_output_value').val() ? parseInt(this.$name('delivered_output_value').val(), 10) : null,
			tape_offering_id: this.$name('tape_offering_id').val() || null,
			mounting_method_code: this.$name('mounting_method_code').val(),
			finish_code: this.$name('finish_code').val(),
			endcap_color_code: this.$name('endcap_color_code').val() || null,
			segments: this._collectSegments(),
			include_power_supply: this.$('#includePowerSupply').is(':checked'),
			dimming_protocol_code: this.$name('dimming_protocol_code').val() || null,
			override_max_run_ft: this._getOverrideMaxRunFt(),
			product_slug: this.productSlug || this.$('#fixtureTemplateSelect').val()
		};
	};

	// ────────────────────────────────────────────────────────────────
	// Calculate & Validate
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.validateConfiguration = function () {
		if (!this.canCalculateRestored()) return;
		this.invalidateValidation();
		var self = this;
		var sel = this._gatherAllSelections();
		var segments = sel.segments;

		if (!segments.length) {
			frappe.msgprint(__('Please add at least one segment'));
			return;
		}
		if (segments[segments.length - 1].end_type !== 'Endcap') {
			frappe.msgprint(__('The fixture must end with an Endcap. Please select Endcap on the last segment.'));
			return;
		}

		var data = {
			fixture_template_code: sel.fixture_template_code,
			led_package_code: sel.led_package_code,
			environment_rating_code: sel.environment_rating_code,
			cct_code: sel.cct_code,
			lens_appearance_code: sel.lens_appearance_code,
			finish_code: sel.finish_code,
			mounting_method_code: sel.mounting_method_code,
			endcap_color_code: sel.endcap_color_code,
			segments_json: JSON.stringify(segments),
			include_power_supply: sel.include_power_supply,
			dimming_protocol_code: sel.dimming_protocol_code
		};
		if (sel.override_max_run_ft !== '') data.override_max_run_ft = sel.override_max_run_ft;
		// Portal and Desk both persist only when Save is requested.
		data._skip_record_creation = true;

		var method;
		if (sel.delivered_output_value) {
			data.delivered_output_value = sel.delivered_output_value;
			method = ENGINE + 'validate_and_quote_multisegment_with_output';
		} else if (sel.tape_offering_id) {
			data.tape_offering_id = sel.tape_offering_id;
			method = ENGINE + 'validate_and_quote_multisegment';
		} else {
			frappe.msgprint({ title: __('Missing Selection'), indicator: 'orange',
				message: __('Please select an Output Level to continue.') });
			return;
		}

		var $btn = this.$('#validateBtn');
		var original = $btn.html();
		$btn.data('illCalculationLabel', original);
		$btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + __('Calculating…'));

		self.request({
			method: method,
			isCurrent: this.validationGuard(),
			args: data,
			callback: function (r) {
				$btn.html(original);
				if (r.message) {
					self.currentResult = r.message;
					self.lastValidation = r.message;
					self._displayResults(r.message);
				}
				self._updateButtons();
			},
			error: function (e) {
				$btn.html(original);
				self._updateButtons();
				frappe.msgprint({ title: __('Calculation Error'), indicator: 'red',
					message: __('An error occurred while calculating. Please check your selections and try again.') });
				console.error('validateConfiguration API error:', e);
			}
		});
	};

	Fixture.prototype._displayResults = function (result) {
		var showPricing = this.context.show_pricing !== false;
		this.$('#resultsPanel').show();

		// Messages
		var $messages = this.$('#validationMessages');
		var $list = this.$('#messagesList').empty();
		if (result.messages && result.messages.length) {
			result.messages.forEach(function (m) {
				var cls = m.severity === 'error' ? 'danger' : (m.severity === 'warning' ? 'warning' : 'info');
				$list.append('<div class="alert alert-' + cls + ' py-2 mb-1 small">' + escapeHtml(m.text || m.message || '') + '</div>');
			});
			$messages.show();
		} else {
			$messages.hide();
		}

		// Part number & description
		var partNumber = result.configured_fixture_id || result.candidate_part_number;
		var computed = result.computed || {};
		if (partNumber) {
			this.$('#partNumberPanel').show();
			this.$('#partNumberValue').text(partNumber);
			this.$('#partDescriptionValue').text(computed.build_description_display || computed.build_description || '-');
		} else {
			this.$('#partNumberPanel').hide();
		}

		if (result.computed) {
			this.$('#lengthResults').show();
			var requestedIn = computed.total_requested_length_in || (computed.total_requested_length_mm / MM_PER_INCH).toFixed(1);
			var mfgIn = computed.manufacturable_overall_length_in || (computed.manufacturable_overall_length_mm / MM_PER_INCH).toFixed(1);
			this.$('#requestedLength').text(requestedIn + '" (' + computed.total_requested_length_mm + ' mm)');
			this.$('#mfgLength').text(mfgIn + '" (' + computed.manufacturable_overall_length_mm + ' mm)');
			this.$('#segmentCountResult').text(computed.user_segment_count);

			this.$('#manufacturingResults').show();
			this.$('#profileSegmentsCount').text(computed.segments_count);
			this.$('#runsCount').text(computed.runs_count);
			this.$('#endcapsCount').text(computed.total_endcaps);
			this.$('#mountingCount').text(computed.total_mounting_accessories);
			this.$('#totalWatts').text(computed.total_watts + ' W');
			this.$('#assemblyMode').text(computed.assembly_mode);

			if (computed.max_run_ft_effective) {
				var maxRun = computed.max_run_ft_effective + ' ft';
				if (computed.override_max_run_ft_active) maxRun += ' (' + __('Overridden') + ')';
				else if (computed.max_run_ft_by_voltage_drop && computed.max_run_ft_by_watts) {
					maxRun += ' (' + (computed.max_run_ft_by_voltage_drop <= computed.max_run_ft_by_watts ? __('voltage drop') : __('wattage')) + ')';
				}
				this.$('#maxRunLength').text(maxRun);
				this.$('#maxRunLengthRow').show();
			} else {
				this.$('#maxRunLengthRow').hide();
			}

			if (computed.build_description_display || computed.build_description) {
				this.$('#buildDescriptionPanel').show();
				this.$('#buildDescription').text(computed.build_description_display || computed.build_description);
			} else {
				this.$('#buildDescriptionPanel').hide();
			}

			if (computed.runs && computed.runs.length) {
				var html = '<table class="table table-sm table-bordered mb-0"><thead class="thead-light"><tr>'
					+ '<th>' + __('Run') + '</th><th>' + __('Segment') + '</th><th>' + __('Length') + '</th><th>' + __('Watts') + '</th>'
					+ '</tr></thead><tbody>';
				computed.runs.forEach(function (run) {
					var lengthIn = run.run_len_in || (run.run_len_mm / MM_PER_INCH).toFixed(1);
					var lengthFt = (run.run_len_mm / MM_PER_FOOT).toFixed(2);
					html += '<tr><td class="text-center">' + run.run_index + '</td>'
						+ '<td class="text-center">' + run.segment_index + '</td>'
						+ '<td class="text-right">' + lengthIn + '" (' + lengthFt + ' ft)</td>'
						+ '<td class="text-right">' + Number(run.run_watts).toFixed(1) + ' W</td></tr>';
				});
				html += '</tbody></table>';
				this.$('#ledRunDetails').html(html);
				this.$('#ledRunDetailsPanel').show();
			} else {
				this.$('#ledRunDetailsPanel').hide();
			}
		} else {
			this.$('#lengthResults, #manufacturingResults, #buildDescriptionPanel, #ledRunDetailsPanel').hide();
		}

		// Driver plan
		var dp = result.resolved_items && result.resolved_items.driver_plan;
		if (dp) {
			this.$('#driverResults').show();
			if (dp.status === 'not_required') {
				this.$('#driverPlan').html('<div class="alert alert-info py-2 mb-0"><i class="fa fa-info-circle mr-2"></i>'
					+ __('Power supplies excluded from this configuration.') + '</div>');
			} else if (dp.status === 'selected' && dp.drivers && dp.drivers.length) {
				var dhtml = '<table class="table table-sm mb-0">';
				dp.drivers.forEach(function (d) {
					dhtml += '<tr><td>' + escapeHtml(d.item_code) + '</td><td class="text-right">×' + escapeHtml(d.qty) + '</td></tr>';
				});
				this.$('#driverPlan').html(dhtml + '</table>');
			} else {
				this.$('#driverPlan').html('<span class="text-muted">' + escapeHtml(dp.status || '') + '</span>');
			}
		} else {
			this.$('#driverResults').hide();
		}

		// Pricing
		if (showPricing && result.pricing) {
			this.$('#pricingResults').show();
			var $tbody = this.$('#priceBreakdownBody').empty();
			var p = result.pricing;
			if (p.item_pricing && p.item_pricing.length) {
				p.item_pricing.forEach(function (item) {
					if (!item.item_code) return;
					var tier = '$' + Number(item.tier_unit).toFixed(2);
					if (item.discount_amount > 0) tier += ' <small class="text-success">(-$' + Number(item.discount_amount).toFixed(2) + ')</small>';
					$tbody.append('<tr><td>' + escapeHtml(item.item_code) + '</td>'
						+ '<td class="text-right"><strong>$' + Number(item.msrp_unit).toFixed(2) + '</strong></td>'
						+ '<td class="text-right">' + tier + '</td></tr>');
				});
			} else if (p.msrp_unit !== undefined) {
				$tbody.append('<tr><td>' + __('Total') + '</td>'
					+ '<td class="text-right"><strong>$' + Number(p.msrp_unit).toFixed(2) + '</strong></td>'
					+ '<td class="text-right">$' + Number(p.tier_unit || p.msrp_unit).toFixed(2) + '</td></tr>');
			}
			if (p.adder_breakdown && p.adder_breakdown.length) {
				var bhtml = '<details><summary class="text-muted">' + __('Fixture Price Breakdown') + '</summary><table class="table table-sm mt-2 mb-0">';
				p.adder_breakdown.forEach(function (a) {
					bhtml += '<tr><td>' + escapeHtml(a.component) + '</td><td class="text-right">$' + Number(a.amount).toFixed(2) + '</td></tr>';
				});
				this.$('#adderBreakdown').html(bhtml + '</table></details>');
			} else {
				this.$('#adderBreakdown').empty();
			}
		} else {
			this.$('#pricingResults').hide();
		}

		if (result.stock_availability) this._renderStockAvailability(result.stock_availability);
		else this.$('#stockAvailability').hide();
	};

	Fixture.prototype._renderStockAvailability = function (stockData) {
		var $container = this.$('#stockAvailability');
		var $list = this.$('#stockItemsList').empty();
		if (!stockData || !stockData.items || !stockData.items.length) { $container.hide(); return; }
		var items = stockData.items;
		var inStock = items.filter(function (i) { return i.is_sufficient; }).length;
		var hasQty = typeof items[0].qty_required !== 'undefined';
		var cls = stockData.all_in_stock ? 'text-success' : (inStock ? 'text-warning' : 'text-danger');
		var text = stockData.all_in_stock ? __('All In Stock') : (inStock ? __('Partial') : __('Not In Stock'));
		var html = '<details class="stock-breakdown"><summary><span class="' + cls + '">'
			+ '<i class="fa fa-circle mr-1" style="font-size:.6em;vertical-align:middle;"></i>' + text
			+ ' (' + inStock + '/' + items.length + ')</span></summary>'
			+ '<table class="table table-sm table-borderless mb-0 small mt-2"><tbody>';
		items.forEach(function (item) {
			var icon = item.is_sufficient
				? '<i class="fa fa-check-circle text-success"></i>'
				: '<i class="fa fa-times-circle text-danger"></i>';
			html += '<tr><td style="width:20px;">' + icon + '</td><td>' + escapeHtml(item.component_type || '') + '</td>'
				+ '<td class="text-muted">' + escapeHtml(item.item_name || item.item_code || '—') + '</td>';
			if (hasQty) html += '<td class="text-center">' + escapeHtml(item.qty_required) + '/' + escapeHtml(item.qty_available) + '</td>';
			html += '</tr>';
		});
		$list.html(html + '</tbody></table></details>');
		$container.show();
	};

	// ────────────────────────────────────────────────────────────────
	// Save
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.addToSchedule = function () {
		var self = this;
		if (!this.currentResult || !this.currentResult.is_valid) {
			frappe.msgprint(__('Cannot save: configuration is not valid. Click "Calculate & Validate" first.'));
			return;
		}

		// Pluggable save target: the desk Quotation / Sales Order dialog.
		if (this._usesSaveHandler()) {
			this.context.saveHandler({
				product_type: 'Linear Fixture',
				selections: this._gatherAllSelections(),
				product_slug: this.productSlug || this.$('#fixtureTemplateSelect').val(),
				validation: this.currentResult,
				instance: this
			});
			return;
		}

		var target = this.scheduleTarget;
		var scheduleName = target ? target.scheduleName() : this.context.schedule_name;
		var lineVal = target ? target.lineValue() : (this.context.line_idx != null ? String(this.context.line_idx) : '__new__');
		if (!scheduleName) {
			frappe.msgprint(__('Please select a schedule to save to'));
			return;
		}
		if (!lineVal) {
			frappe.msgprint(__('Please select a line or choose "New Line"'));
			return;
		}
		var lineIdx = (lineVal === '__new__') ? null : parseInt(lineVal, 10);

		if (lineIdx !== null) {
			var existing = target ? target.lineAt(lineIdx) : null;
			if (existing && (existing.configured_fixture || existing.configured_tape_neon || existing.manufacturer_name || existing.fixture_model_number)) {
				frappe.confirm(
					'<strong>' + __('Warning:') + '</strong> ' + __('This will override the existing data for line "{0}".', [escapeHtml(existing.line_id)])
					+ '<div class="bg-light p-2 rounded mt-2 mb-2 small">' + escapeHtml(existing.summary || '').replace(/\|/g, '<br>') + '</div>'
					+ __('Are you sure you want to replace this with the new configuration?'),
					function () { self._doSaveToSchedule(scheduleName, lineIdx); }
				);
				return;
			}
		}
		this._doSaveToSchedule(scheduleName, lineIdx);
	};

	Fixture.prototype._doSaveToSchedule = function (scheduleName, lineIdx) {
        return this.saveScheduleConfiguration({
            family: 'Linear Fixture', schedule_name: scheduleName, line_idx: lineIdx,
            selections: this._gatherAllSelections(), product_slug: this.productSlug || this.$('#fixtureTemplateSelect').val()
        });
    };

	Fixture.prototype.buildFixtureAndItem = function () {
		var self = this;
		if (!this.currentResult || !this.currentResult.is_valid || !this.currentResult.configured_fixture_id) {
			frappe.msgprint(__('Cannot build: configuration is not valid or missing fixture ID'));
			return;
		}
		var $btn = this.$('#buildItemBtn');
		var original = $btn.html();
		$btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + __('Building…'));
		self.request({
			method: PORTAL + 'build_configured_fixture_and_item',
			args: { configured_fixture_id: this.currentResult.configured_fixture_id },
			callback: function (r) {
				$btn.html(original).prop('disabled', false);
				var msg = r.message || {};
				if (msg.success) {
					frappe.msgprint({ title: __('Build Successful'), indicator: 'green',
						message: msg.created ? __('Created Item: {0}', [escapeHtml(msg.item_code)]) : __('Item already exists: {0}', [escapeHtml(msg.item_code)]) });
				} else {
					frappe.msgprint({ title: __('Build Failed'), indicator: 'red', message: msg.error || __('An error occurred') });
				}
			},
			error: function () { $btn.html(original).prop('disabled', false); }
		});
	};

	Fixture.prototype._copy = function (text) {
		if (!text) return;
		var done = function () { frappe.show_alert({ message: __('Copied to clipboard'), indicator: 'green' }, 2); };
		if (navigator.clipboard && navigator.clipboard.writeText) {
			navigator.clipboard.writeText(text).then(done).catch(function () { fallback(); });
		} else {
			fallback();
		}
		function fallback() {
			var ta = document.createElement('textarea');
			ta.value = text;
			document.body.appendChild(ta);
			ta.select();
			try { document.execCommand('copy'); } catch (_) { /* noop */ }
			document.body.removeChild(ta);
			done();
		}
	};

	// ────────────────────────────────────────────────────────────────
	// Reset
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.resetConfiguration = function () {
		var self = this;
		frappe.confirm(__('Are you sure you want to reset all selections?'), function () {
			self.selections = {};
			self.templateOptions = null;
			self.isInitialized = false;
			self.isMultiCCT = false;
			self.currentResult = null;
			self.lastValidation = null;
			self._clearSegments();
			self.$('#templateOptions .pill-selector').empty();
			self.$('#templateOptions select').val('');
			self.$name('tape_offering_id').val('');
			self.$name('endcap_color_code').val('');
			self.$('#endcapColorDisplay').hide();
			self.$('#includePowerSupply').prop('checked', true);
			self.$('#overrideMaxRunCheck').prop('checked', false);
			self.$('#overrideMaxRunInput').val('');
			self.$('#overrideMaxRunGroup, #overrideMaxRunWarning').hide();
			self.$('#templateOptions').hide();
			self.$('#actionButtons').hide();
			self.$('#resultsPanel').hide();
			self.$('#validationMessages').hide();
			self.$('#messagesList').empty();
			self.$('#fixtureTemplateSelect').val('').trigger('change');
		});
	};

	root.IllConfigurator.Fixture = Fixture;

}(window));
