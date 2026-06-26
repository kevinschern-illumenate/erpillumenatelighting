/**
 * Fixture Configurator (Phase 4)
 *
 * Scoped, multi-instance-safe port of the legacy webflow_configurator.js.
 * All DOM lookups use `this.$()` (scoped to the configurator root element)
 * so multiple instances can coexist on a single page (portal page + builder
 * dialog, etc.).
 *
 * Public API:
 *   var inst = new IllConfigurator.Fixture(rootEl, context);
 *   inst.init();                  // bind events + load from context
 *   inst.resetConfiguration();
 *   inst.validateConfiguration();
 *   inst.addToSchedule();
 *
 * Back-compat:
 *   window.initWebflowConfigurator(ctx) defined in shared_configurator.js
 *   creates an instance bound to `document` and registers it as the default.
 */
(function (root) {
	'use strict';

	if (!root.IllConfigurator) {
		console.error('shared_configurator.js must load before fixture_steps.js');
		return;
	}

	var Base = root.IllConfigurator.Base;

	function Fixture(rootEl, context) {
		Base.call(this, rootEl, context);
		this.$root.addClass('ill-configurator ill-configurator-fixture');
		this.productSlug = null;
		this.options = {};
		this.seriesInfo = null;
		this.isInitialized = false;
		this.lengthConfig = {};
		this.steps = [];
	}
	Fixture.prototype = Object.create(Base.prototype);
	Fixture.prototype.constructor = Fixture;

	// ────────────────────────────────────────────────────────────────
	// Lifecycle
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.init = function () {
		console.log('Initializing Fixture configurator', this.context);
		this._bindEvents();

		if (this.context.session_id) {
			this._loadFromSession(this.context.session_id);
		}
		if (this.context.product_slug) {
			this.productSlug = this.context.product_slug;
			this._initializeFromProduct(this.context.product_slug);
		}

		var selectedTemplate = this.$('#fixtureTemplateSelect').val();
		if (selectedTemplate && !this.context.product_slug) {
			this._onTemplateSelected(selectedTemplate);
		}
	};

	Fixture.prototype._bindEvents = function () {
		var self = this;

		// Template selection
		this.$('#fixtureTemplateSelect').on('change', function () {
			var templateCode = $(this).val();
			if (templateCode) {
				self._onTemplateSelected(templateCode);
			} else {
				self._hideAllSections();
			}
		});

		// Pill clicks (delegate to root so dynamically-added pills work)
		this.$root.on('click', '.pill-selector .pill', function (e) {
			e.preventDefault();
			self._handlePillClick($(this));
		});

		// Select fallback (mobile) → mirror to pill
		this.$root.on('change', '.select-fallback', function () {
			var $select = $(this);
			var fieldName = $select.attr('name');
			var value = $select.val();
			if (!value) return;
			var $pill = self.$('.pill-selector[data-field="' + fieldName + '"] .pill[data-value="' + value + '"]');
			if ($pill.length) {
				self._handlePillClick($pill);
			} else {
				self.selections[fieldName] = value;
				self._handleCascadingUpdate(fieldName, value);
				self._updateProgress();
				self._updatePartNumberPreview();
				self._updateValidateButton();
				self._updateSummary();
			}
		});

		// Length value
		this.$name('length_value').on('change input', root.IllConfigurator.debounce(function () {
			self._updateLengthInches();
			self._updatePartNumberPreview();
			self._updateValidateButton();
		}, 300));

		this.$name('length_unit').on('change', function () {
			self._updateLengthInches();
			self._updatePartNumberPreview();
			self._updateValidateButton();
		});

		// Feed lengths
		this.$('input[name="start_feed_length_ft"], input[name="end_feed_length_ft"]')
			.on('change input', root.IllConfigurator.debounce(function () {
				self._updatePartNumberPreview();
				self._updateValidateButton();
			}, 300));

		// Reset / validate / add-to-schedule buttons (if present in the markup)
		this.$('[data-action="reset"]').on('click', function () { self.resetConfiguration(); });
		this.$('[data-action="validate"]').on('click', function () { self.validateConfiguration(); });
		this.$('[data-action="add-to-schedule"]').on('click', function () { self.addToSchedule(); });
	};

	// ────────────────────────────────────────────────────────────────
	// Template / product initialisation
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._onTemplateSelected = function (templateCode) {
		var self = this;
		var $option = this.$('#fixtureTemplateSelect option:selected');
		var templateName = $option.data('name') || $option.text();
		this.$('#seriesName').text(templateName);
		this.$('#seriesCode').text(templateCode);

		this.$('#environmentSection').show().find('.pill-selector')
			.html('<span class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading options...</span>');

		var productSlug = this.productSlug || templateCode;

		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_configurator_init',
			args: { product_slug: productSlug },
			callback: function (r) {
				if (r.message && r.message.success) {
					self._handleInitResponse(r.message);
				} else {
					self._loadOptionsFromTemplate(templateCode);
				}
			},
			error: function () { self._loadOptionsFromTemplate(templateCode); }
		});

		this._updateProgress();
	};

	Fixture.prototype._initializeFromProduct = function (productSlug) {
		var self = this;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_configurator_init',
			args: { product_slug: productSlug },
			callback: function (r) {
				if (r.message && r.message.success) {
					self._handleInitResponse(r.message);
				} else {
					frappe.msgprint(__('Product not found or not configurable'));
				}
			}
		});
	};

	Fixture.prototype._handleInitResponse = function (data) {
		this.seriesInfo = data.series;
		this.options = data.options;
		this.lengthConfig = data.length_config || {};
		this.isInitialized = true;
		if (data.steps && data.steps.length) this.steps = data.steps;

		if (data.series) {
			this.$('#seriesName').text(data.series.display_name || data.series.series_name);
			this.$('#seriesCode').text(data.series.series_code);
		}

		this._populatePill('environment_rating', data.options.environment_ratings);
		this._populatePill('lens_appearance', data.options.lens_appearances);
		this._populatePill('mounting_method', data.options.mounting_methods);
		this._populatePill('finish', data.options.finishes);
		this._populateFeedDirections(data.options.feed_directions);

		if (data.length_config) {
			var $lv = this.$name('length_value');
			$lv.attr('min', data.length_config.min_inches);
			$lv.attr('max', data.length_config.max_inches);
			$lv.attr('placeholder', data.length_config.default_inches || 50);
			this.$('#lengthNote').text(data.length_config.max_run_note || 'Maximum length is 30 ft');
			this.lengthConfig.default_inches = data.length_config.default_inches || 50;
		}

		this._showAllSections();
		this._updateProgress();
		this._updatePartNumberPreview();
		this.$('#complexFixtureBanner').show();
	};

	Fixture.prototype._loadOptionsFromTemplate = function (templateCode) {
		var self = this;
		frappe.call({
			method: 'frappe.client.get',
			args: { doctype: 'ilL-Fixture-Template', name: templateCode },
			callback: function (r) { if (r.message) self._processTemplateOptions(r.message); }
		});
	};

	Fixture.prototype._processTemplateOptions = function (template) {
		var options = {
			environment_ratings: [], lens_appearances: [],
			mounting_methods: [], finishes: [],
			feed_directions: [
				{ value: 'End', label: 'End', code: 'E' },
				{ value: 'Back', label: 'Back', code: 'B' },
				{ value: 'Left', label: 'Left', code: 'L' },
				{ value: 'Right', label: 'Right', code: 'R' }
			]
		};

		(template.allowed_options || []).forEach(function (opt) {
			if (!opt.is_active) return;
			switch (opt.option_type) {
				case 'Lens Appearance':
					if (opt.lens_appearance) options.lens_appearances.push({
						value: opt.lens_appearance, label: opt.lens_appearance, is_default: opt.is_default
					});
					break;
				case 'Mounting Method':
					if (opt.mounting_method) options.mounting_methods.push({
						value: opt.mounting_method, label: opt.mounting_method, is_default: opt.is_default
					});
					break;
				case 'Finish':
					if (opt.finish) options.finishes.push({
						value: opt.finish, label: opt.finish, is_default: opt.is_default
					});
					break;
			}
		});

		var envSet = {};
		(template.allowed_tape_offerings || []).forEach(function (tape) {
			if (tape.is_active && tape.environment_rating && !envSet[tape.environment_rating]) {
				envSet[tape.environment_rating] = true;
				options.environment_ratings.push({
					value: tape.environment_rating, label: tape.environment_rating
				});
			}
		});

		this.options = options;
		this.seriesInfo = {
			series_code: template.template_code,
			series_name: template.template_name,
			led_package_code: 'XX',
			display_name: template.template_name
		};
		this.isInitialized = true;
		if (!this.steps.length) this.steps = Fixture._defaultSteps();

		this._populatePill('environment_rating', options.environment_ratings);
		this._populatePill('lens_appearance', options.lens_appearances);
		this._populatePill('mounting_method', options.mounting_methods);
		this._populatePill('finish', options.finishes);
		this._populateFeedDirections(options.feed_directions);

		this._showAllSections();
		this._updatePartNumberPreview();
		this._updateProgress();
	};

	// ────────────────────────────────────────────────────────────────
	// Pill rendering
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._populatePill = function (fieldName, items) {
		var $container = this.$('.pill-selector[data-field="' + fieldName + '"]');
		var $select = this.$name(fieldName);

		$container.empty();
		$select.empty().append('<option value="">Select...</option>');

		if (!items || !items.length) {
			$container.append('<span class="text-muted">No options available</span>');
			return;
		}

		var self = this;
		items.forEach(function (opt) {
			var $pill = $('<button type="button" class="pill"></button>')
				.attr('data-value', opt.value)
				.attr('data-code', opt.code || '')
				.text(opt.label || opt.value);
			if (opt.is_default) $pill.addClass('default');
			$container.append($pill);

			var $opt = $('<option></option>').val(opt.value).text(opt.label || opt.value);
			if (opt.is_default) $opt.attr('selected', true);
			$select.append($opt);
		});

		var $default = $container.find('.pill.default');
		if ($default.length) self._selectPill($default);
	};

	Fixture.prototype._populateFeedDirections = function (directions) {
		var dirOptions = directions || [
			{ value: 'End', label: 'End', code: 'E' },
			{ value: 'Back', label: 'Back', code: 'B' },
			{ value: 'Left', label: 'Left', code: 'L' },
			{ value: 'Right', label: 'Right', code: 'R' }
		];
		var endDirOptions = dirOptions.slice();
		var hasEndcap = endDirOptions.some(function (o) { return o.value === 'Endcap'; });
		if (!hasEndcap) endDirOptions.push({ value: 'Endcap', label: 'Endcap', code: 'CAP' });

		var self = this;
		['start_feed_direction', 'end_feed_direction'].forEach(function (fieldName) {
			var $container = self.$('.pill-selector[data-field="' + fieldName + '"]');
			$container.empty();
			var opts = (fieldName === 'end_feed_direction') ? endDirOptions : dirOptions;
			opts.forEach(function (opt) {
				var $pill = $('<button type="button" class="pill"></button>')
					.attr('data-value', opt.value)
					.attr('data-code', opt.code || '')
					.text(opt.label || opt.value);
				$container.append($pill);
			});
		});
	};

	// ────────────────────────────────────────────────────────────────
	// Pill click / cascading
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._handlePillClick = function ($pill) {
		var fieldName = $pill.closest('.pill-selector').data('field');
		var value = $pill.data('value');

		$pill.siblings().removeClass('active');
		$pill.addClass('active');

		this.$name(fieldName).val(value);
		this.selections[fieldName] = value;

		if (fieldName === 'end_feed_direction') {
			if (value === 'Endcap') {
				this.$('input[name="end_feed_length_ft"]').val('0').prop('disabled', true);
				this.$('#endFeedLengthGroup').hide();
			} else {
				var $efl = this.$('input[name="end_feed_length_ft"]');
				var curVal = $efl.val();
				if (!curVal || curVal === '0') $efl.val('2');
				$efl.prop('disabled', false);
				this.$('#endFeedLengthGroup').show();
			}
		}

		this._updateProgress();
		this._handleCascadingUpdate(fieldName, value);
		this._updatePartNumberPreview();
		this._updateValidateButton();
		this._updateSummary();
	};

	Fixture.prototype._selectPill = function ($pill) {
		$pill.siblings().removeClass('active');
		$pill.addClass('active');
		var fieldName = $pill.closest('.pill-selector').data('field');
		var value = $pill.data('value');
		this.$name(fieldName).val(value);
		this.selections[fieldName] = value;
	};

	Fixture.prototype._handleCascadingUpdate = function (fieldName, value) {
		var self = this;
		var productSlug = this.productSlug || this.$('#fixtureTemplateSelect').val();

		if (fieldName === 'lens_appearance') {
			this.$('#outputSection').removeClass('awaiting-lens');
			this.$('#outputHint').hide();
		}

		var dependentSteps = this._getDependentStepNames(fieldName);
		if (!dependentSteps.length) return;

		if (fieldName === 'lens_appearance') {
			if (!this.selections['environment_rating'] || !this.selections['cct']) return;
		}

		dependentSteps.forEach(function (stepName) { self._clearSelection(stepName); });

		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_cascading_options',
			args: {
				product_slug: productSlug,
				step_name: fieldName,
				selections: JSON.stringify(this.selections)
			},
			callback: function (r) {
				if (!(r.message && r.message.success)) return;
				var updated = r.message.updated_options || {};
				(r.message.clear_selections || []).forEach(function (s) { self._clearSelection(s); });
				for (var optionKey in updated) {
					var stepName = Fixture._optionKeyToStepName(optionKey);
					if (stepName) self._populatePill(stepName, updated[optionKey]);
				}
			}
		});
	};

	Fixture.prototype._getDependentStepNames = function (fieldName) {
		var dependents = [];
		this.steps.forEach(function (step) {
			if ((step.depends_on || []).indexOf(fieldName) !== -1) dependents.push(step.name);
		});
		var allDependents = dependents.slice();
		var toCheck = dependents.slice();
		var steps = this.steps;
		while (toCheck.length) {
			var current = toCheck.shift();
			steps.forEach(function (step) {
				if ((step.depends_on || []).indexOf(current) !== -1 && allDependents.indexOf(step.name) === -1) {
					allDependents.push(step.name);
					toCheck.push(step.name);
				}
			});
		}
		return allDependents;
	};

	Fixture._optionKeyToStepName = function (optionKey) {
		var mapping = {
			ccts: 'cct', output_levels: 'output_level', environment_ratings: 'environment_rating',
			lens_appearances: 'lens_appearance', mounting_methods: 'mounting_method',
			finishes: 'finish', feed_directions: 'start_feed_direction'
		};
		return mapping[optionKey] || null;
	};

	Fixture.prototype._clearSelection = function (fieldName) {
		this.$('.pill-selector[data-field="' + fieldName + '"]').find('.pill').removeClass('active');
		this.$name(fieldName).val('');
		delete this.selections[fieldName];
	};

	// ────────────────────────────────────────────────────────────────
	// Show/hide sections
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._showAllSections = function () {
		this.$('#environmentSection, #cctSection').show();
		this.$('#outputSection').show();
		this.$('#lensSection, #mountingSection, #finishSection').show();
		this.$('#lengthSection, #startFeedSection, #endFeedSection').show();
		if (this.selections['lens_appearance']) {
			this.$('#outputSection').removeClass('awaiting-lens');
			this.$('#outputHint').hide();
		}
	};

	Fixture.prototype._hideAllSections = function () {
		this.$('#environmentSection, #cctSection, #outputSection').hide();
		this.$('#lensSection, #mountingSection, #finishSection').hide();
		this.$('#lengthSection, #startFeedSection, #endFeedSection').hide();
		this.$('#complexFixtureBanner').hide();
		this.$('#outputSection').addClass('awaiting-lens');
		this.$('#outputHint').show();
	};

	// ────────────────────────────────────────────────────────────────
	// Progress / completion
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._updateProgress = function () {
		var self = this;
		var steps = this.steps;
		var completed = 0;
		var total = steps.length;
		if (!total) return;

		steps.forEach(function (step, index) {
			var $stepEl = self.$('.progress-step[data-step="' + index + '"]');
			if (step.locked) {
				if (self._isStepCompleted(step.name)) {
					$stepEl.addClass('completed').removeClass('active');
					$stepEl.find('.step-number').text('\u2713');
					completed++;
				} else {
					$stepEl.removeClass('completed').addClass('active');
					$stepEl.find('.step-number').text(index + 1);
				}
			} else if (self._isStepCompleted(step.name)) {
				$stepEl.addClass('completed').removeClass('active');
				$stepEl.find('.step-number').text('\u2713');
				completed++;
			} else {
				$stepEl.removeClass('completed active');
				$stepEl.find('.step-number').text(index + 1);
			}
		});

		var foundActive = false;
		steps.forEach(function (step, index) {
			if (!foundActive && !self._isStepCompleted(step.name)) {
				self.$('.progress-step[data-step="' + index + '"]').addClass('active');
				foundActive = true;
			}
		});

		var pct = Math.round((completed / total) * 100);
		this.$('#progressBadge').text(pct + '%');
	};

	Fixture.prototype._isStepCompleted = function (stepName) {
		switch (stepName) {
			case 'series':
				return !!this.$('#fixtureTemplateSelect').val();
			case 'length':
				var lengthVal = this.$name('length_value').val();
				return this.isInitialized && !!lengthVal && lengthVal !== '';
			case 'start_feed':
				var startFeedVal = this.$('input[name="start_feed_length_ft"]').val();
				return !!this.selections['start_feed_direction'] && !!startFeedVal && startFeedVal !== '';
			case 'end_feed':
				if (this.selections['end_feed_direction'] === 'Endcap') return true;
				var endFeedVal = this.$('input[name="end_feed_length_ft"]').val();
				return !!this.selections['end_feed_direction'] && !!endFeedVal && endFeedVal !== '';
			default:
				return !!this.selections[stepName];
		}
	};

	Fixture.prototype._updateLengthInches = function () {
		var value = parseFloat(this.$name('length_value').val()) || 0;
		var unit = this.$name('length_unit').val();
		var inches;
		switch (unit) {
			case 'ft': inches = value * 12; break;
			case 'mm': inches = value / 25.4; break;
			default: inches = value;
		}
		this.selections['length_inches'] = inches;
	};

	// ────────────────────────────────────────────────────────────────
	// Part number preview
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._updatePartNumberPreview = function () {
		var self = this;
		var productSlug = this.productSlug || this.$('#fixtureTemplateSelect').val();
		if (!productSlug) return;

		var selections = this._gatherAllSelections();
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_part_number_preview',
			args: { product_slug: productSlug, selections: JSON.stringify(selections) },
			async: false,
			callback: function (r) {
				if (r.message && r.message.success) self._displayPartNumberPreview(r.message);
			},
			error: function () { self._displayLocalPartNumberPreview(); }
		});
	};

	Fixture.prototype._displayPartNumberPreview = function (data) {
		var $preview = this.$('#partNumberPreview');
		$preview.empty();
		if (data.segments) {
			data.segments.forEach(function (seg, idx) {
				var $span = $('<span class="segment"></span>')
					.text((idx > 0 ? '-' : '') + seg.code);
				if (seg.locked) $span.addClass('locked');
				else if (seg.selected) $span.addClass('selected');
				else $span.addClass('unselected');
				$preview.append($span);
			});
		} else if (data.part_number_preview) {
			$preview.text(data.part_number_preview);
		}
	};

	Fixture.prototype._displayLocalPartNumberPreview = function () {
		var series = this.seriesInfo || {};
		var sel = this.selections;
		var parts = [
			'ILL-' + (series.series_code || 'XX') + '-' + (series.led_package_code || 'XX'),
			sel.environment_rating ? 'I' : 'xx',
			sel.cct || 'xx',
			sel.output_level || 'xx',
			sel.lens_appearance || 'xx',
			sel.mounting_method || 'xx',
			sel.finish || 'xx',
			sel.endcap_color || 'xx'
		];
		this.$('#partNumberPreview').text(parts.join('-'));
	};

	Fixture.prototype._gatherAllSelections = function () {
		this._updateLengthInches();
		var s = this.selections;
		return {
			environment_rating: s['environment_rating'] || '',
			cct: s['cct'] || '',
			output_level: s['output_level'] || '',
			lens_appearance: s['lens_appearance'] || '',
			mounting_method: s['mounting_method'] || '',
			finish: s['finish'] || '',
			length_inches: s['length_inches'] || '',
			start_feed_direction: s['start_feed_direction'] || '',
			start_feed_length_ft: this.$('input[name="start_feed_length_ft"]').val() || '',
			end_feed_direction: s['end_feed_direction'] || '',
			end_feed_length_ft: s['end_feed_direction'] === 'Endcap'
				? '0'
				: (this.$('input[name="end_feed_length_ft"]').val() || ''),
			product_slug: this.productSlug || this.$('#fixtureTemplateSelect').val(),
			include_power_supply: this.$('#includePowerSupply').is(':checked'),
			override_max_run_ft: this._getOverrideMaxRunFt()
		};
	};

	// Read the optional "Override Max Run Length" value. Returns the parsed
	// float when the checkbox is ticked and a positive value is entered,
	// otherwise an empty string (treated as "no override" by the backend).
	Fixture.prototype._getOverrideMaxRunFt = function () {
		if (!this.$('#overrideMaxRunCheck').is(':checked')) return '';
		var val = parseFloat(this.$('#overrideMaxRunInput').val());
		return (!isNaN(val) && val > 0) ? val : '';
	};

	// ────────────────────────────────────────────────────────────────
	// Validate button + summary
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._updateValidateButton = function () {
		var self = this;
		var requiredFields = [
			'environment_rating', 'cct', 'output_level', 'lens_appearance',
			'mounting_method', 'finish', 'start_feed_direction', 'end_feed_direction'
		];
		var allFilled = true;
		requiredFields.forEach(function (f) { if (!self.selections[f]) allFilled = false; });
		if (!this.$name('length_value').val()) allFilled = false;
		if (!this.$('input[name="start_feed_length_ft"]').val()) allFilled = false;
		if (this.selections['end_feed_direction'] !== 'Endcap'
			&& !this.$('input[name="end_feed_length_ft"]').val()) allFilled = false;

		this.$('#validateBtn').prop('disabled', !allFilled);
		var $status = this.$('#validationStatus');
		if (allFilled) {
			$status.removeClass('badge-secondary').addClass('badge-info').text(__('Ready'));
		} else {
			$status.removeClass('badge-info badge-success').addClass('badge-secondary').text(__('Incomplete'));
		}
	};

	Fixture.prototype._updateSummary = function () {
		var $list = this.$('#summaryList');
		var $placeholder = this.$('#summaryPlaceholder');

		var labels = {
			environment_rating: 'Environment', cct: 'CCT', output_level: 'Output',
			lens_appearance: 'Lens', mounting_method: 'Mounting', finish: 'Finish'
		};
		var items = [];
		for (var f in labels) {
			if (this.selections[f]) items.push({ label: labels[f], value: this.selections[f] });
		}
		var length = this.$name('length_value').val();
		var unit = this.$name('length_unit').val();
		if (length) items.push({ label: 'Length', value: length + ' ' + unit });

		if (this.selections['start_feed_direction']) {
			items.push({
				label: 'Start Feed',
				value: this.selections['start_feed_direction'] + ' - '
					+ this.$('input[name="start_feed_length_ft"]').val() + ' ft'
			});
		}
		if (this.selections['end_feed_direction']) {
			if (this.selections['end_feed_direction'] === 'Endcap') {
				items.push({ label: 'End Feed', value: 'Endcap (capped, no leader)' });
			} else {
				items.push({
					label: 'End Feed',
					value: this.selections['end_feed_direction'] + ' - '
						+ this.$('input[name="end_feed_length_ft"]').val() + ' ft'
				});
			}
		}

		if (items.length > 0) {
			$placeholder.hide();
			$list.empty().show();
			items.forEach(function (item) {
				$list.append(
					'<li class="list-group-item d-flex justify-content-between">'
					+ '<span class="text-muted">' + item.label + '</span>'
					+ '<strong>' + item.value + '</strong></li>'
				);
			});
		} else {
			$placeholder.show();
			$list.hide();
		}
	};

	// ────────────────────────────────────────────────────────────────
	// Validation API
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.validateConfiguration = function () {
		var self = this;
		var productSlug = this.productSlug || this.$('#fixtureTemplateSelect').val();
		var selections = this._gatherAllSelections();
		var args = { product_slug: productSlug, selections: JSON.stringify(selections) };
		var overrideMaxRun = this._getOverrideMaxRunFt();
		if (overrideMaxRun !== '') args.override_max_run_ft = overrideMaxRun;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.validate_configuration',
			args: args,
			freeze: true,
			freeze_message: __('Validating configuration...'),
			callback: function (r) { if (r.message) self._handleValidationResponse(r.message); }
		});
	};

	Fixture.prototype._handleValidationResponse = function (data) {
		this.lastValidation = data;
		var $messages = this.$('#validationMessages');
		var $messagesList = this.$('#messagesList');
		$messagesList.empty();

		if (data.success && data.is_valid) {
			this.$('#validationStatus')
				.removeClass('badge-secondary badge-info badge-danger')
				.addClass('badge-success').text(__('Valid'));
			$messagesList.append(
				'<div class="alert alert-success"><i class="fa fa-check-circle mr-2"></i>'
				+ __('Configuration is valid!') + '</div>'
			);
			if (data.part_number) this.$('#partNumberPreview').text(data.part_number);
			if (data.tape_offering_id) this.$('input[name="tape_offering_id"]').val(data.tape_offering_id);
			if (data.pricing && this.context.show_pricing) {
				this.$('#basePrice').text('$' + data.pricing.base_price.toFixed(2));
				this.$('#lengthPrice').text('$' + data.pricing.length_price.toFixed(2));
				this.$('#totalMsrp').text('$' + data.pricing.total_msrp.toFixed(2));
				this.$('#pricingPreview').show();
			}
			if (data.stock_availability) this._renderStockAvailability(data.stock_availability);
			if (data.override_max_run_ft_active) {
				$messagesList.append(
					'<div class="alert alert-warning py-2"><i class="fa fa-exclamation-triangle mr-2"></i>'
					+ __('Max run length overridden to {0} ft. Verify compliance with applicable electrical codes.',
						[data.override_max_run_ft]) + '</div>'
				);
			}
			if (!this.$('#includePowerSupply').is(':checked')) {
				$messagesList.append(
					'<div class="alert alert-info py-2"><i class="fa fa-info-circle mr-2"></i>'
					+ __('Power Supply Not Included') + ' &mdash; '
					+ __('drivers/power supplies are excluded from this configuration.') + '</div>'
				);
			}
			this.$('#addToScheduleBtn').prop('disabled', false);
		} else {
			this.$('#validationStatus')
				.removeClass('badge-secondary badge-info badge-success')
				.addClass('badge-danger').text(__('Invalid'));
			$messagesList.append(
				'<div class="alert alert-danger"><i class="fa fa-exclamation-circle mr-2"></i>'
				+ (data.error || __('Configuration is invalid')) + '</div>'
			);
			this.$('#addToScheduleBtn').prop('disabled', true);
		}
		$messages.show();
	};

	Fixture.prototype._renderStockAvailability = function (stockData) {
		var $container = this.$('#stockAvailability');
		var $list = this.$('#stockItemsList');
		var $badge = this.$('#stockOverallBadge');
		$list.empty();
		$badge.hide();
		if (!stockData || !stockData.items || !stockData.items.length) {
			$container.hide();
			return;
		}
		var items = stockData.items;
		var inStockCount = 0;
		var totalCount = items.length;
		var hasQty = typeof items[0].qty_required !== 'undefined';
		for (var i = 0; i < items.length; i++) if (items[i].is_sufficient) inStockCount++;

		var summaryClass, summaryText;
		if (stockData.all_in_stock) {
			summaryClass = 'text-success';
			summaryText = __('All In Stock') + ' (' + totalCount + '/' + totalCount + ')';
		} else if (inStockCount > 0) {
			summaryClass = 'text-warning';
			summaryText = __('Partial') + ' (' + inStockCount + '/' + totalCount + ')';
		} else {
			summaryClass = 'text-danger';
			summaryText = __('Not In Stock') + ' (0/' + totalCount + ')';
		}

		var html = '<details class="stock-breakdown kit-stock-breakdown">';
		html += '<summary><span class="' + summaryClass + '">';
		html += '<i class="fa fa-circle mr-1" style="font-size:0.6em;vertical-align:middle;"></i>' + summaryText;
		html += '</span> <i class="fa fa-caret-right stock-toggle-arrow"></i></summary>';
		html += '<table class="table table-sm table-borderless mb-0 small kit-stock-table" style="font-size:0.85em;">';
		html += '<thead><tr class="text-muted">';
		html += '<th style="width:20px;padding:2px 4px;"></th>';
		html += '<th style="padding:2px 4px;">' + __('Component') + '</th>';
		html += '<th style="padding:2px 4px;">' + __('Item') + '</th>';
		if (hasQty) {
			html += '<th class="text-center" style="padding:2px 4px;">' + __('Needed') + '</th>';
			html += '<th class="text-center" style="padding:2px 4px;">' + __('Available') + '</th>';
		}
		html += '</tr></thead><tbody>';
		for (var j = 0; j < items.length; j++) {
			var item = items[j];
			var icon = item.is_sufficient
				? '<i class="fa fa-check-circle text-success" style="font-size:0.8em;"></i>'
				: '<i class="fa fa-times-circle text-danger" style="font-size:0.8em;"></i>';
			var displayName = item.item_name || item.item_code || '\u2014';
			var qtyClass = (hasQty && item.qty_available >= item.qty_required)
				? 'text-success' : 'text-danger font-weight-bold';
			html += '<tr>';
			html += '<td style="padding:2px 4px;">' + icon + '</td>';
			html += '<td style="padding:2px 4px;">' + (item.component_type || '') + '</td>';
			html += '<td style="padding:2px 4px;"><span class="text-muted">' + displayName + '</span></td>';
			if (hasQty) {
				html += '<td class="text-center" style="padding:2px 4px;">' + item.qty_required + '</td>';
				html += '<td class="text-center" style="padding:2px 4px;"><span class="' + qtyClass + '">' + item.qty_available + '</span></td>';
			}
			html += '</tr>';
		}
		html += '</tbody></table></details>';
		$list.html(html);
		$container.show();
	};

	// ────────────────────────────────────────────────────────────────
	// Add to Schedule
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.addToSchedule = function () {
		var self = this;

		// Pluggable save target (Phase C): when the host (e.g. the desk
		// quote/order dialog) supplies a saveHandler, delegate to it with the
		// validated selections instead of writing to a portal schedule.
		if (typeof this.context.saveHandler === 'function') {
			this.context.saveHandler({
				product_type: 'Linear Fixture',
				selections: this._gatherAllSelections(),
				product_slug: this.productSlug || this.$('#fixtureTemplateSelect').val(),
				validation: this.lastValidation || null,
				instance: this
			});
			return;
		}

		var scheduleId = this.context.schedule_name;
		if (!scheduleId) {
			this._showScheduleSelectionDialog();
			return;
		}
		var selections = this._gatherAllSelections();
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.add_to_schedule',
			args: {
				schedule_id: scheduleId,
				configuration: JSON.stringify(selections),
				quantity: 1
			},
			freeze: true,
			freeze_message: __('Adding to schedule...'),
			callback: function (r) {
				if (r.message && r.message.success) {
					frappe.show_alert({
						message: r.message.message || __('Added to schedule successfully'),
						indicator: 'green'
					});
					setTimeout(function () {
						window.location.href = '/portal/schedule?name=' + scheduleId;
					}, 1000);
				} else {
					frappe.msgprint({
						title: __('Error'),
						message: (r.message && r.message.error) || __('Failed to add to schedule'),
						indicator: 'red'
					});
				}
			}
		});
	};

	Fixture.prototype._showScheduleSelectionDialog = function () {
		var self = this;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.get_user_schedules',
			callback: function (r) {
				if (!(r.message && r.message.success)) return;
				var schedules = r.message.schedules;
				if (schedules.length === 0) { self._showCreateScheduleDialog(); return; }
				var d = new frappe.ui.Dialog({
					title: __('Select Schedule'),
					fields: [{
						fieldname: 'schedule', fieldtype: 'Select', label: __('Schedule'), reqd: 1,
						options: schedules.map(function (s) {
							return { value: s.name, label: s.schedule_name + ' (' + s.project_name + ')' };
						})
					}],
					primary_action_label: __('Add to Schedule'),
					primary_action: function (values) {
						self.context.schedule_name = values.schedule;
						d.hide();
						self.addToSchedule();
					}
				});
				d.show();
			}
		});
	};

	Fixture.prototype._showCreateScheduleDialog = function () {
		var self = this;
		var d = new frappe.ui.Dialog({
			title: __('Create New Project'),
			fields: [
				{ fieldname: 'project_name', fieldtype: 'Data', label: __('Project Name'), reqd: 1 },
				{ fieldname: 'schedule_name', fieldtype: 'Data', label: __('Schedule Name'), default: __('Main Schedule') }
			],
			primary_action_label: __('Create & Add'),
			primary_action: function (values) {
				frappe.call({
					method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.create_quick_project_and_schedule',
					args: values,
					callback: function (r) {
						if (r.message && r.message.success) {
							self.context.schedule_name = r.message.schedule_id;
							d.hide();
							self.addToSchedule();
						} else {
							frappe.msgprint((r.message && r.message.error) || __('Failed to create project'));
						}
					}
				});
			}
		});
		d.show();
	};

	// ────────────────────────────────────────────────────────────────
	// Reset
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype.resetConfiguration = function () {
		var self = this;
		frappe.confirm(
			__('Are you sure you want to reset all selections?'),
			function () {
				self.selections = {};
				self.seriesInfo = null;
				self.options = {};
				self.isInitialized = false;
				self.lengthConfig = {};
				self.steps = [];

				self.$('#fixtureTemplateSelect').val('');
				self.$('#seriesName').text(__('Select a template...'));
				self.$('#seriesCode').text('');

				self.$('.pill-selector .pill').removeClass('active');
				self.$('.pill-selector').each(function () { $(this).empty(); });

				self.$name('length_value').val('').attr('placeholder', '50');
				self.$name('length_unit').val('inches');
				self.$('input[name="start_feed_length_ft"]').val('').attr('placeholder', '2');
				self.$('input[name="end_feed_length_ft"]').val('').attr('placeholder', '2').prop('disabled', false);
				self.$('#endFeedLengthGroup').show();

				self._hideAllSections();

				self.$('.progress-step').removeClass('completed active');
				self.$('.progress-step').each(function (index) {
					$(this).find('.step-number').text(index);
				});
				self.$('.progress-step[data-step="0"]').find('.step-number').text('1');

				self.$('#progressBadge').text('0%');
				self.$('#partNumberPreview').html(
					'<span class="segment locked">ILL-XX-XX</span>'
					+ '<span class="segment unselected">-xx-xx-xx-xx-xx-xx</span>'
				);

				self.$('#validationMessages').hide();
				self.$('#pricingPreview').hide();
				self.$('#validationStatus')
					.removeClass('badge-success badge-danger badge-info')
					.addClass('badge-secondary').text(__('Incomplete'));

				self.$('#validateBtn').prop('disabled', true);
				self.$('#addToScheduleBtn').prop('disabled', true);

				self.$('#summaryList').hide().empty();
				self.$('#summaryPlaceholder').show();
			}
		);
	};

	// ────────────────────────────────────────────────────────────────
	// Session loading
	// ────────────────────────────────────────────────────────────────
	Fixture.prototype._loadFromSession = function (sessionId) {
		var self = this;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_session',
			args: { session_id: sessionId },
			callback: function (r) {
				if (!(r.message && r.message.success)) return;
				var config = r.message.configuration || {};
				for (var key in config) {
					self.selections[key] = config[key];
					var $pill = self.$('.pill-selector[data-field="' + key + '"] .pill[data-value="' + config[key] + '"]');
					if ($pill.length) self._selectPill($pill);
				}
				if (config.length_inches) self.$name('length_value').val(config.length_inches);
				if (config.start_feed_length_ft) self.$('input[name="start_feed_length_ft"]').val(config.start_feed_length_ft);
				if (config.end_feed_length_ft) self.$('input[name="end_feed_length_ft"]').val(config.end_feed_length_ft);
				self._updateProgress();
				self._updatePartNumberPreview();
				self._updateSummary();
				self._updateValidateButton();
			}
		});
	};

	// ────────────────────────────────────────────────────────────────
	// Default steps fallback
	// ────────────────────────────────────────────────────────────────
	Fixture._defaultSteps = function () {
		return [
			{ step: 0, name: 'series', label: 'Series', required: true, locked: true, depends_on: [] },
			{ step: 1, name: 'environment_rating', label: 'Dry/Wet', required: true, locked: false, depends_on: ['series'] },
			{ step: 2, name: 'cct', label: 'CCT', required: true, locked: false, depends_on: ['series', 'environment_rating'] },
			{ step: 3, name: 'lens_appearance', label: 'Lens', required: true, locked: false, depends_on: ['series'] },
			{ step: 4, name: 'output_level', label: 'Output', required: true, locked: false, depends_on: ['series', 'environment_rating', 'cct', 'lens_appearance'] },
			{ step: 5, name: 'mounting_method', label: 'Mounting', required: true, locked: false, depends_on: [] },
			{ step: 6, name: 'finish', label: 'Finish', required: true, locked: false, depends_on: [] },
			{ step: 7, name: 'length', label: 'Length', required: true, locked: false, depends_on: [] },
			{ step: 8, name: 'start_feed_direction', label: 'Start Feed Direction', required: true, locked: false, depends_on: [] },
			{ step: 9, name: 'start_feed_length', label: 'Start Feed Length', required: true, locked: false, depends_on: ['start_feed_direction'] },
			{ step: 10, name: 'end_feed_direction', label: 'End Feed Direction', required: true, locked: false, depends_on: [] },
			{ step: 11, name: 'end_feed_length', label: 'End Feed Length', required: true, locked: false, depends_on: ['end_feed_direction'] }
		];
	};

	root.IllConfigurator.Fixture = Fixture;

}(window));
