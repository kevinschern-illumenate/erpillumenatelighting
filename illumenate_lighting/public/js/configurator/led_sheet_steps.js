/**
 * LED Sheet Configurator (scoped IllConfigurator.LedSheet)
 *
 * Drives templates/includes/configurator_led_sheet_form.html on the portal
 * LED Sheet page and inside the desk Quotation / Sales Order dialog.
 *
 *   options    → template data embedded by the include (portal.get_led_sheet_templates)
 *   calculate  → led_sheet_configurator.validate_sheet_configuration
 *   save       → led_sheet_configurator.save_sheet_configuration (portal page,
 *                 + portal.add_schedule_line for a new line)
 *                 or context.saveHandler(payload) (desk dialog →
 *                 desk_configurator.build_configured_line)
 *
 * All DOM lookups use `this.$()` (scoped to the configurator root) so several
 * instances can coexist.
 *
 * context: templates (optional; else read from the embedded JSON), existing
 *          (ilL-Configured-LED-Sheet dict to pre-fill), schedule_name,
 *          project_name, line_idx, can_save, show_pricing, saveHandler
 */
(function (root) {
	'use strict';

	if (!root.IllConfigurator) {
		console.error('shared_configurator.js must load before led_sheet_steps.js');
		return;
	}

	var Base = root.IllConfigurator.Base;
	var escapeHtml = root.IllConfigurator.escapeHtml;
	var SHEET_API = 'illumenate_lighting.illumenate_lighting.api.led_sheet_configurator.';
	var PORTAL = 'illumenate_lighting.illumenate_lighting.api.portal.';

	// option_type on ilL-Child-LED-Sheet-Allowed-Option → field / select id.
	var OPTION_FIELDS = [
		{ type: 'CCT',                field: 'sheet_cct',         select: '#sheetCct',         label: __('CCT') },
		{ type: 'Output Level',       field: 'sheet_output',      select: '#sheetOutput',      label: __('Output Level') },
		{ type: 'Environment Rating', field: 'sheet_environment', select: '#sheetEnvironment', label: __('Environment') },
		{ type: 'Mounting',           field: 'sheet_mounting',    select: '#sheetMounting',    label: __('Mounting') },
		{ type: 'Finish',             field: 'sheet_finish',      select: '#sheetFinish',      label: __('Finish') }
	];
	var STEPS = ['template', 'spec', 'CCT', 'Output Level', 'Environment Rating', 'Mounting', 'Finish', 'coverage'];

	function money(v) { return '$' + Number(v || 0).toFixed(2); }
	function num(v, d) { return Number(v || 0).toFixed(d === undefined ? 2 : d); }

	function LedSheet(rootEl, context) {
		Base.call(this, rootEl, context);
		this.$root.addClass('ill-configurator ill-configurator-sheet');
		this.templates = (context && context.templates) || null;
		this.template = null;
		this.spec = null;
		this.lastResult = null;
		this.scheduleTarget = null;
		this.templatePicker = null;
	}
	LedSheet.prototype = Object.create(Base.prototype);
	LedSheet.prototype.constructor = LedSheet;

	// ────────────────────────────────────────────────────────────────
	// Lifecycle
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype.init = function () {
		var self = this;
		if (!this.templates) this.templates = this._readEmbeddedTemplates();
		this._bindEvents();

		var $select = this.$('#sheetTemplate');
		if (root.IllConfigurator.renderTemplateCards && this.$('#sheetTemplatePicker').length) {
			this.templatePicker = root.IllConfigurator.renderTemplateCards({
				$container: this.$('#sheetTemplatePicker'),
				$select: $select
			});
		}
		if (!this._usesSaveHandler()) {
			this.scheduleTarget = root.IllConfigurator.bindScheduleContext({
				instance: this,
				context: this.context,
				onChange: function () { self._updateButtons(); }
			});
		}

		var existing = this.context.existing || null;
		if (existing && existing.sheet_template) {
			$select.val(existing.sheet_template);
			this._onTemplateSelected(existing.sheet_template, existing);
			if (this.templatePicker) this.templatePicker.refresh();
		} else if ($select.val()) {
			setTimeout(function () { $select.trigger('change'); }, 0);
		}
	};

	LedSheet.prototype._usesSaveHandler = function () {
		return typeof this.context.saveHandler === 'function';
	};

	LedSheet.prototype._readEmbeddedTemplates = function () {
		var $data = this.$('script.ill-sheet-templates').first();
		if ($data.length) {
			try { return JSON.parse($data.text() || '[]'); } catch (_) { /* fall through */ }
		}
		return root.ILL_LED_SHEET_TEMPLATES || [];
	};

	LedSheet.prototype._bindEvents = function () {
		var self = this;

		this.$('#sheetTemplate').on('change', function () {
			self._onTemplateSelected($(this).val());
		});

		this.$root.on('click', '.pill-selector .pill', function (e) {
			e.preventDefault();
			var $pill = $(this);
			var $selector = $pill.closest('.pill-selector');
			var $select = $pill.closest('.config-section').find('select[name="' + $selector.data('field') + '"]').first();
			$selector.find('.pill').removeClass('active');
			$pill.addClass('active');
			if ($select.length) $select.val(String($pill.attr('data-value'))).trigger('change');
		});
		this.$root.on('change', 'select.select-fallback', function () {
			var $select = $(this);
			var $selector = $select.closest('.config-section').find('.pill-selector[data-field="' + $select.attr('name') + '"]').first();
			$selector.find('.pill').removeClass('active');
			$selector.find('.pill[data-value="' + $select.val() + '"]').addClass('active');
		});

		this.$('#sheetSpec').on('change', function () {
			self.spec = self._specByName($(this).val());
			self._updateSpecHint();
			self._afterChange();
		});
		OPTION_FIELDS.forEach(function (f) {
			self.$(f.select).on('change', function () { self._afterChange(); });
		});
		this.$('#coverageWidthValue, #coverageHeightValue').on('input change', root.IllConfigurator.debounce(function () { self._afterChange(); }, 200));
		this.$('#coverageWidthUnit, #coverageHeightUnit, #sheetIncludePowerSupply').on('change', function () { self._afterChange(); });

		this.$('[data-action="reset"]').on('click', function () { self.resetConfiguration(); });
		this.$('[data-action="validate"]').on('click', function () { self.validateConfiguration(); });
		this.$('[data-action="add-to-schedule"]').on('click', function () { self.addToSchedule(); });
	};

	LedSheet.prototype._afterChange = function () {
		this._invalidateResult();
		this._updateEstimate();
		this._updateProgress();
		this._updateSummary();
		this._updateButtons();
	};

	// ────────────────────────────────────────────────────────────────
	// Template → specs / options
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype._templateByName = function (name) {
		return (this.templates || []).find(function (t) { return t.name === name; }) || null;
	};

	LedSheet.prototype._specByName = function (name) {
		var specs = (this.template && this.template.allowed_specs) || [];
		return specs.find(function (s) { return s.name === name; }) || null;
	};

	LedSheet.prototype._onTemplateSelected = function (name, existing) {
		this._invalidateResult();
		this.template = this._templateByName(name);
		if (!this.template) {
			this.spec = null;
			this.$('#sheetOptions, #sheetActionButtons').hide();
			this._updateProgress();
			this._updateSummary();
			this._updateButtons();
			return;
		}

		var self = this;
		var specs = this.template.allowed_specs || [];
		this._populatePill('sheet_spec', '#sheetSpec', specs.map(function (s) {
			return {
				value: s.name,
				label: (s.item || s.name) + ' · ' + num(s.total_sheet_watts, 0) + 'W · '
					+ num(s.sheet_width_ft, 1) + '×' + num(s.sheet_height_ft, 1) + ' ft'
			};
		}), existing ? existing.sheet_spec : null);
		this.spec = this._specByName(this.$('#sheetSpec').val());
		this._updateSpecHint();

		var byType = {};
		(this.template.allowed_options || []).forEach(function (o) {
			(byType[o.option_type] = byType[o.option_type] || []).push(o);
		});
		var existingKey = {
			'CCT': 'selected_cct', 'Output Level': 'selected_output_level',
			'Environment Rating': 'selected_environment_rating', 'Mounting': 'selected_mounting', 'Finish': 'selected_finish'
		};
		OPTION_FIELDS.forEach(function (f) {
			var rows = byType[f.type] || [];
			var items = rows.map(function (o) {
				var label = o.attribute_link || o.option_code;
				if (Number(o.msrp_adder) > 0) label += ' (+' + money(o.msrp_adder) + '/panel)';
				return { value: o.attribute_link, label: label, is_default: !!o.is_default };
			});
			self._populatePill(f.field, f.select, items, existing ? existing[existingKey[f.type]] : null);
			self.$(f.select).closest('.config-section').toggle(items.length > 0);
		});

		if (existing) {
			this.$('#coverageWidthValue').val(existing.coverage_width_ft || '');
			this.$('#coverageWidthUnit').val('ft');
			this.$('#coverageHeightValue').val(existing.coverage_height_ft || '');
			this.$('#coverageHeightUnit').val('ft');
			this.$('#sheetIncludePowerSupply').prop('checked', existing.include_power_supply == null ? true : !!existing.include_power_supply);
		}

		this.$('#sheetOptions, #sheetActionButtons').show();
		this._afterChange();
	};

	LedSheet.prototype._populatePill = function (fieldName, selectSel, items, preselect) {
		var $section = this.$(selectSel).closest('.config-section');
		var $container = $section.find('.pill-selector[data-field="' + fieldName + '"]');
		var $select = this.$(selectSel);
		$container.empty();
		$select.empty().append('<option value="">' + __('Select...') + '</option>');
		if (!items.length) {
			$container.append('<span class="text-muted">' + __('No options available') + '</span>');
			return;
		}
		items.forEach(function (o) {
			$container.append($('<button type="button" class="pill"></button>').attr('data-value', o.value).text(o.label));
			$select.append($('<option></option>').val(o.value).text(o.label));
		});
		var chosen = null;
		if (preselect && items.some(function (o) { return o.value === preselect; })) chosen = preselect;
		else {
			var def = items.find(function (o) { return o.is_default; });
			chosen = def ? def.value : (items.length === 1 ? items[0].value : null);
		}
		if (chosen !== null) {
			$select.val(chosen);
			$container.find('.pill[data-value="' + chosen + '"]').addClass('active');
		}
	};

	LedSheet.prototype._updateSpecHint = function () {
		var s = this.spec;
		var $hint = this.$('#sheetSpecHint');
		if (!s) { $hint.text(''); return; }
		var parts = [];
		if (s.led_package) parts.push(__('LED package: {0}', [s.led_package]));
		if (s.watts_per_sqft) parts.push(num(s.watts_per_sqft, 1) + ' W/sqft');
		if (s.lumens_per_sqft) parts.push(num(s.lumens_per_sqft, 0) + ' lm/sqft');
		if (s.total_sheet_lumens) parts.push(num(s.total_sheet_lumens, 0) + ' lm/panel');
		$hint.text(parts.join(' · '));
	};

	// ────────────────────────────────────────────────────────────────
	// Coverage
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype._coverageFt = function () {
		var w = parseFloat(this.$('#coverageWidthValue').val()) || 0;
		var h = parseFloat(this.$('#coverageHeightValue').val()) || 0;
		if (this.$('#coverageWidthUnit').val() === 'in') w = w / 12;
		if (this.$('#coverageHeightUnit').val() === 'in') h = h / 12;
		return { width: w, height: h };
	};

	// Client-side preview only; the server layout is authoritative.
	LedSheet.prototype._updateEstimate = function () {
		var $est = this.$('#sheetPanelEstimate');
		var c = this._coverageFt();
		var s = this.spec;
		if (!s || c.width <= 0 || c.height <= 0 || !s.sheet_width_ft || !s.sheet_height_ft) { $est.text(''); return; }
		var wide = Math.ceil(c.width / s.sheet_width_ft);
		var tall = Math.ceil(c.height / s.sheet_height_ft);
		var panels = wide * tall;
		var watts = panels * (Number(s.total_sheet_watts) || 0);
		$est.text(__('≈ {0} panels ({1} wide × {2} tall) · {3} sq ft · ≈ {4} W — click Calculate to confirm',
			[panels, wide, tall, num(c.width * c.height, 1), num(watts, 0)]));
	};

	// ────────────────────────────────────────────────────────────────
	// Progress / summary / buttons
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype._optionValue = function (type) {
		var f = OPTION_FIELDS.find(function (x) { return x.type === type; });
		return f ? (this.$(f.select).val() || '') : '';
	};

	LedSheet.prototype._optionRequired = function (type) {
		var f = OPTION_FIELDS.find(function (x) { return x.type === type; });
		return !!(f && this.$(f.select).closest('.config-section').is(':visible') && this.$(f.select).find('option').length > 1);
	};

	LedSheet.prototype._isStepCompleted = function (step) {
		if (step === 'template') return !!this.template;
		if (step === 'spec') return !!this.spec;
		if (step === 'coverage') { var c = this._coverageFt(); return c.width > 0 && c.height > 0; }
		return !this._optionRequired(step) || !!this._optionValue(step);
	};

	LedSheet.prototype._updateProgress = function () {
		var self = this;
		var done = STEPS.filter(function (s) { return self._isStepCompleted(s); }).length;
		this.$('#sheetProgressBadge').text(Math.round((done / STEPS.length) * 100) + '%');
	};

	LedSheet.prototype._requiredComplete = function () {
		var self = this;
		return STEPS.every(function (s) { return self._isStepCompleted(s); });
	};

	LedSheet.prototype._updateSummary = function () {
		var self = this;
		var $list = this.$('#sheetSummaryList');
		var $placeholder = this.$('#sheetSummaryPlaceholder');
		var items = [];
		if (this.template) items.push({ label: __('Template'), value: this.template.template_name || this.template.name });
		if (this.spec) items.push({ label: __('Panel'), value: (this.spec.item || this.spec.name) + ' · ' + num(this.spec.sheet_width_ft, 1) + '×' + num(this.spec.sheet_height_ft, 1) + ' ft' });
		OPTION_FIELDS.forEach(function (f) {
			var v = self._optionValue(f.type);
			if (v) items.push({ label: f.label, value: v });
		});
		var c = this._coverageFt();
		if (c.width > 0 && c.height > 0) items.push({ label: __('Coverage'), value: num(c.width, 2) + ' × ' + num(c.height, 2) + ' ft (' + num(c.width * c.height, 1) + ' sq ft)' });
		if (!this.$('#sheetIncludePowerSupply').is(':checked')) items.push({ label: __('Power Supply'), value: __('Excluded') });

		if (!items.length) { $placeholder.show(); $list.hide().empty(); return; }
		$placeholder.hide();
		$list.empty().show();
		items.forEach(function (i) {
			$list.append('<li class="list-group-item d-flex justify-content-between py-1 px-0">'
				+ '<span class="text-muted mr-2">' + escapeHtml(i.label) + '</span>'
				+ '<strong class="text-right">' + escapeHtml(i.value) + '</strong></li>');
		});
	};

	LedSheet.prototype._hasScheduleTarget = function () {
		if (!this.scheduleTarget) return !!this.context.schedule_name;
		return this.scheduleTarget.hasTarget();
	};

	LedSheet.prototype._canSaveToSchedule = function () {
		return this.scheduleTarget ? this.scheduleTarget.canSave : !!this.context.can_save;
	};

	LedSheet.prototype._updateButtons = function () {
		var ready = this._requiredComplete();
		this.$('#calculateSheet').prop('disabled', !ready);
		var $status = this.$('#sheetValidationStatus');
		if (this.lastResult && this.lastResult.success) {
			$status.removeClass('badge-secondary badge-info badge-danger').addClass('badge-success').text(__('Valid'));
		} else if (ready) {
			$status.removeClass('badge-secondary badge-success badge-danger').addClass('badge-info').text(__('Ready'));
		} else {
			$status.removeClass('badge-info badge-success badge-danger').addClass('badge-secondary').text(__('Incomplete'));
		}
		var valid = !!(this.lastResult && this.lastResult.success);
		var canSave = valid && (this._usesSaveHandler() || (this._hasScheduleTarget() && this._canSaveToSchedule()));
		this.$('#saveSheet').prop('disabled', !canSave);
	};

	LedSheet.prototype._invalidateResult = function () {
		if (!this.lastResult) return;
		this.lastResult = null;
		this.$('#sheetResults').hide();
		this.$('#sheetValidationMessages').hide();
		this.$('#sheetMessagesList').empty();
	};

	// ────────────────────────────────────────────────────────────────
	// Payload / validate
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype._gatherAllSelections = function () {
		var self = this;
		var options = {};
		OPTION_FIELDS.forEach(function (f) { options[f.type] = self._optionValue(f.type); });
		return {
			template: this.$('#sheetTemplate').val(),
			spec: this.$('#sheetSpec').val(),
			options: options,
			coverage_width_value: this.$('#coverageWidthValue').val(),
			coverage_width_unit: this.$('#coverageWidthUnit').val(),
			coverage_height_value: this.$('#coverageHeightValue').val(),
			coverage_height_unit: this.$('#coverageHeightUnit').val(),
			include_power_supply: this.$('#sheetIncludePowerSupply').is(':checked') ? 1 : 0
		};
	};

	LedSheet.prototype.validateConfiguration = function () {
		var self = this;
		var $btn = this.$('#calculateSheet');
		var original = $btn.html();
		$btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + __('Calculating…'));
		frappe.call({
			method: SHEET_API + 'validate_sheet_configuration',
			args: this._gatherAllSelections(),
			callback: function (r) {
				$btn.html(original);
				var msg = r.message || {};
				if (msg.success) {
					self.lastResult = msg;
					self._displayResults(msg);
				} else {
					self.lastResult = null;
					self._showError(msg.error || msg.message || __('Validation failed.'));
				}
				self._updateButtons();
			},
			error: function (e) {
				$btn.html(original);
				self.lastResult = null;
				self._showError(__('An error occurred while calculating. Please check your selections and try again.'));
				self._updateButtons();
				console.error('validate_sheet_configuration error:', e);
			}
		});
	};

	LedSheet.prototype._showError = function (text) {
		this.$('#sheetResults').hide();
		this.$('#sheetMessagesList').html('<div class="alert alert-danger py-2 mb-1 small">' + escapeHtml(text) + '</div>');
		this.$('#sheetValidationMessages').show();
		this.$('#sheetValidationStatus').removeClass('badge-secondary badge-info badge-success').addClass('badge-danger').text(__('Invalid'));
	};

	LedSheet.prototype._displayResults = function (r) {
		var showPricing = this.context.show_pricing !== false;
		var includePs = !!r.include_power_supply;
		this.$('#sheetValidationMessages').hide();
		this.$('#sheetMessagesList').empty();

		var groups = (r.groups || []).map(function (g) {
			return '<tr><td>' + escapeHtml(g.group_number) + '</td><td>' + escapeHtml(g.sheet_count) + '</td>'
				+ '<td>' + num(g.group_watts, 1) + '</td><td>' + escapeHtml(g.compatible_driver || '—') + '</td></tr>';
		}).join('');
		var psRows = (r.power_supplies || []).map(function (ps) {
			return '<tr><td>' + escapeHtml(ps.item_name || ps.driver_item) + '</td><td class="text-center">' + escapeHtml(ps.qty) + '</td>'
				+ '<td>' + escapeHtml(ps.max_wattage || '') + 'W</td>' + (showPricing ? '<td class="text-right">' + money(ps.line_total) + '</td>' : '') + '</tr>';
		}).join('');
		var p = r.pricing || {};

		var html = '<h6 class="mb-1">' + __('Part Number') + '</h6>'
			+ '<code class="d-block mb-3" style="font-size:.95rem;">' + escapeHtml(r.part_number || '—') + '</code>'
			+ '<h6>' + __('Layout') + '</h6>'
			+ '<table class="table table-sm mb-3">'
			+ '<tr><td>' + __('Requested area') + '</td><td class="text-right">' + num(r.total_coverage_sqft) + ' sq ft</td></tr>'
			+ '<tr><td>' + __('Normalized dimensions') + '</td><td class="text-right">' + num(r.coverage_width_ft) + ' × ' + num(r.coverage_height_ft) + ' ft</td></tr>'
			+ '<tr><td>' + __('Panel dimensions') + '</td><td class="text-right">' + num(r.sheet_width_ft) + ' × ' + num(r.sheet_height_ft) + ' ft</td></tr>'
			+ '<tr><td>' + __('Total panels') + '</td><td class="text-right"><strong>' + escapeHtml(r.panels_needed) + '</strong></td></tr>'
			+ '<tr><td>' + __('Panels wide / tall') + '</td><td class="text-right">' + escapeHtml(r.panels_wide) + ' / ' + escapeHtml(r.panels_tall) + '</td></tr>'
			+ '<tr><td>' + __('Driver groups') + '</td><td class="text-right">' + escapeHtml(r.total_groups) + '</td></tr>'
			+ '<tr><td>' + __('Panels per group') + '</td><td class="text-right">' + escapeHtml((r.panels_per_group || []).join(', ')) + '</td></tr>'
			+ '<tr><td>' + __('Jumper cables') + '</td><td class="text-right">' + escapeHtml(r.jumper_cable_qty) + '</td></tr>'
			+ '<tr><td>' + __('Leader cables') + '</td><td class="text-right">' + escapeHtml(r.leader_cable_qty) + '</td></tr>'
			+ '<tr><td>' + __('Total watts') + '</td><td class="text-right">' + num(r.total_system_watts, 1) + ' W</td></tr>'
			+ '</table>'
			+ '<h6>' + __('Groups') + '</h6>'
			+ '<table class="table table-sm table-bordered mb-3"><thead class="thead-light"><tr><th>' + __('Group') + '</th><th>' + __('Panels') + '</th><th>' + __('Watts') + '</th><th>' + __('Driver') + '</th></tr></thead><tbody>' + groups + '</tbody></table>';

		if (includePs) {
			html += '<h6>' + __('Power Supplies') + '</h6>'
				+ '<table class="table table-sm mb-3"><thead><tr><th>' + __('Item') + '</th><th class="text-center">' + __('Qty') + '</th><th>' + __('Supports') + '</th>' + (showPricing ? '<th class="text-right">' + __('MSRP') + '</th>' : '') + '</tr></thead>'
				+ '<tbody>' + (psRows || '<tr><td colspan="4" class="text-muted">' + __('None') + '</td></tr>') + '</tbody></table>';
		} else {
			html += '<div class="alert alert-info py-2 small"><i class="fa fa-info-circle mr-2"></i>' + __('Power supplies excluded (groups calculated for validation only).') + '</div>';
		}

		if (showPricing) {
			html += '<h6>' + __('Pricing (MSRP)') + '</h6><table class="table table-sm mb-0"><tbody>'
				+ '<tr><td>' + __('Panels') + '</td><td class="text-right">' + money(p.sheets_msrp) + '</td></tr>'
				+ (Number(p.option_msrp) ? '<tr><td>' + __('Option adders') + '</td><td class="text-right">' + money(p.option_msrp) + '</td></tr>' : '')
				+ '<tr><td>' + __('Jumpers') + '</td><td class="text-right">' + money(p.jumpers_msrp) + '</td></tr>'
				+ '<tr><td>' + __('Leaders') + '</td><td class="text-right">' + money(p.leaders_msrp) + '</td></tr>'
				+ (includePs ? '<tr><td>' + __('Power supplies') + '</td><td class="text-right">' + money(p.power_supplies_msrp) + '</td></tr>' : '')
				+ '<tr class="font-weight-bold"><td>' + __('Total MSRP') + '</td><td class="text-right">' + money(p.total_msrp != null ? p.total_msrp : r.total_msrp) + '</td></tr>'
				+ '</tbody></table>'
				+ '<small class="text-muted d-block mt-1">' + __('The panel bundle is one schedule line; cables and power supplies are added as accessory lines.') + '</small>';
		}

		this.$('#sheetSummary').html(html);
		this.$('#sheetResults').show();
	};

	// ────────────────────────────────────────────────────────────────
	// Save
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype.addToSchedule = function () {
		var self = this;
		if (!this.lastResult || !this.lastResult.success) {
			frappe.msgprint(__('Cannot save: click "Calculate & Validate" first.'));
			return;
		}
		var selections = this._gatherAllSelections();

		if (this._usesSaveHandler()) {
			this.context.saveHandler({
				product_type: 'LED Sheet',
				selections: selections,
				led_sheet_template: selections.template,
				validation: this.lastResult,
				instance: this
			});
			return;
		}

		var target = this.scheduleTarget;
		var scheduleName = target ? target.scheduleName() : this.context.schedule_name;
		var lineVal = target ? target.lineValue() : (this.context.line_idx != null ? String(this.context.line_idx) : '__new__');
		if (!scheduleName) { frappe.msgprint(__('Please select a schedule to save to')); return; }
		if (!lineVal) { frappe.msgprint(__('Please select a line or choose "New Line"')); return; }

		var $btn = this.$('#saveSheet');
		var original = $btn.html();
		$btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + __('Saving…'));
		var fail = function (text) {
			$btn.html(original);
			self._updateButtons();
			frappe.msgprint({ title: __('Save Error'), indicator: 'red', message: text || __('Error saving configuration') });
		};
		var finish = function (lineIdx) {
			var args = $.extend({}, selections, { schedule_name: scheduleName, line_idx: lineIdx });
			frappe.call({
				method: SHEET_API + 'save_sheet_configuration',
				args: args,
				callback: function (r) {
					var msg = r.message || {};
					if (!msg.success) { fail(msg.error); return; }
					frappe.show_alert({ message: __('LED Sheet saved to schedule'), indicator: 'green' });
					window.location.href = '/portal/schedules/' + encodeURIComponent(scheduleName);
				},
				error: function () { fail(); }
			});
		};

		if (lineVal === '__new__') {
			frappe.call({
				method: PORTAL + 'add_schedule_line',
				args: {
					schedule_name: scheduleName,
					line_data: { manufacturer_type: 'ILLUMENATE', product_type: 'LED Sheet', led_sheet_template: selections.template, configuration_status: 'Pending', qty: 1 }
				},
				callback: function (r) {
					var msg = r.message || {};
					if (msg.success && msg.line_idx !== undefined) finish(msg.line_idx);
					else fail(msg.error);
				},
				error: function () { fail(); }
			});
			return;
		}

		var lineIdx = parseInt(lineVal, 10);
		var existing = target ? target.lineAt(lineIdx) : null;
		if (existing && (existing.configured_led_sheet || existing.configured_fixture || existing.configured_tape_neon || existing.manufacturer_name)) {
			$btn.html(original);
			frappe.confirm(
				'<strong>' + __('Warning:') + '</strong> ' + __('This will override the existing data for line "{0}".', [escapeHtml(existing.line_id)])
				+ '<div class="bg-light p-2 rounded mt-2 mb-2 small">' + escapeHtml(existing.summary || '').replace(/\|/g, '<br>') + '</div>'
				+ __('Are you sure you want to replace this with the new configuration?'),
				function () { $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + __('Saving…')); finish(lineIdx); },
				function () { self._updateButtons(); }
			);
			return;
		}
		finish(lineIdx);
	};

	// ────────────────────────────────────────────────────────────────
	// Reset
	// ────────────────────────────────────────────────────────────────
	LedSheet.prototype.resetConfiguration = function () {
		var self = this;
		frappe.confirm(__('Are you sure you want to reset all selections?'), function () {
			self.template = null;
			self.spec = null;
			self.lastResult = null;
			self.$('#sheetOptions .pill-selector').empty();
			self.$('#sheetOptions select').val('');
			self.$('#coverageWidthValue, #coverageHeightValue').val('');
			self.$('#coverageWidthUnit, #coverageHeightUnit').val('ft');
			self.$('#sheetIncludePowerSupply').prop('checked', true);
			self.$('#sheetPanelEstimate, #sheetSpecHint').text('');
			self.$('#sheetOptions, #sheetActionButtons, #sheetResults, #sheetValidationMessages').hide();
			self.$('#sheetTemplate').val('').trigger('change');
		});
	};

	root.IllConfigurator.LedSheet = LedSheet;

	// Portal LED Sheet page entry point (mirrors initWebflowConfigurator).
	root.initLedSheetConfigurator = function (context) {
		var inst = new LedSheet(document, context || {});
		inst.init();
		return inst;
	};

}(window));
