/**
 * Tape / Neon Configurator (Phase 4)
 *
 * Scoped, multi-instance-safe port of the inline IIFE that previously lived
 * in configure_tape.html. All DOM lookups go through `this.$()` so the same
 * markup can be embedded in a dialog or sub-section without conflict.
 *
 * Usage:
 *   var inst = new IllConfigurator.TapeNeon(rootEl, {
 *       product_category: 'LED Tape',
 *       is_neon: false,
 *       schedule_name: '...',
 *       project_name: '...',
 *       line_idx: null,
 *       can_save: true
 *   });
 *   inst.init();
 */
(function (root) {
	'use strict';

	if (!root.IllConfigurator) {
		console.error('shared_configurator.js must load before tape_neon_steps.js');
		return;
	}

	var Base = root.IllConfigurator.Base;

	function TapeNeon(rootEl, context) {
		Base.call(this, rootEl, context);
		this.$root.addClass('ill-configurator ill-configurator-tape-neon');
		this.IS_NEON = !!context.is_neon;
		this.PRODUCT_CATEGORY = context.product_category || (this.IS_NEON ? 'LED Neon' : 'LED Tape');
		this.SCHEDULE_NAME = context.schedule_name || null;
		this.PROJECT_NAME = context.project_name || null;
		this.LINE_IDX = (context.line_idx !== undefined) ? context.line_idx : null;
		this.CAN_SAVE = !!context.can_save;

		this.initData = null;
		this.lastResult = null;
		this.neonSegmentCount = 0;
		this.selectedMountingAccessory = null;

		this.selections = {
			environment_rating: null,
			cct: null,
			output_level: null,
			feed_type: null,
			lead_length_inches: null,
			tape_length_unit: 'in',
			tape_length_value: null,
			tape_length_feet: null,
			tape_length_inches: null,
			finish: null
		};
	}
	TapeNeon.prototype = Object.create(Base.prototype);
	TapeNeon.prototype.constructor = TapeNeon;

	// ────────────────────────────────────────────────────────────────
	// Lifecycle
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype.init = function () {
		this._loadInitData();
		this._bindEvents();
		this._loadScheduleContext();
	};

	TapeNeon.prototype._loadInitData = function () {
		var self = this;
		var method = this.IS_NEON
			? 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_neon_configurator_init'
			: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_tape_configurator_init';
		frappe.call({
			method: method,
			freeze: true,
			freeze_message: 'Loading options...',
			callback: function (r) {
				if (r.message && r.message.success) {
					self.initData = r.message;
					self._populateOptions(r.message.options);
				} else {
					frappe.msgprint({
						title: 'Error', indicator: 'red',
						message: (r.message && r.message.error) || 'Failed to load configurator data'
					});
				}
			}
		});
	};

	// ────────────────────────────────────────────────────────────────
	// Populate options
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._populateOptions = function (options) {
		if (!options) return;
		var self = this;

		if (!this.IS_NEON && options.environment_ratings) {
			this._populatePill('pillEnvironment', 'selEnvironment', options.environment_ratings,
				'value', 'label', function (v, item) { self._onEnvironmentSelect(v, item); });
			if (options.environment_ratings.length === 1) {
				this.$('#pillEnvironment .pill-option:first').click();
			}
		}
		if (options.ccts) {
			this._populatePill('pillCCT', 'selCCT', options.ccts, 'value', 'label',
				function (v, item) { self._onCCTSelect(v, item); });
		}
		if (options.output_levels) {
			this._populatePill('pillOutput', 'selOutput', options.output_levels, 'value', 'label',
				function (v, item) { self._onOutputSelect(v, item); });
		}
		if (this.IS_NEON && options.finishes) {
			this._populatePill('pillFinish', 'selFinish', options.finishes, 'value', 'label',
				function (v, item) { self._onFinishSelect(v, item); });
		}
		if (!this.IS_NEON && options.feed_types) {
			this._populatePill('pillFeedType', 'selFeedType', options.feed_types, 'value', 'label',
				function (v, item) { self._onFeedTypeSelect(v, item); });
		}
		if (this.IS_NEON) {
			this.$('#stepCCT').removeClass('disabled-step');
		}
	};

	TapeNeon.prototype._populatePill = function (pillId, selectId, items, valueKey, labelKey, onClick) {
		var self = this;
		var $pill = this.$('#' + pillId);
		var $sel = this.$('#' + selectId);
		$pill.empty();
		$sel.find('option:not(:first)').remove();

		items.forEach(function (item) {
			var val = item[valueKey];
			var label = item[labelKey] || val;
			var $opt = $('<span class="pill-option"></span>')
				.text(label)
				.attr('data-value', val)
				.on('click', function () {
					$pill.find('.pill-option').removeClass('active');
					$(this).addClass('active');
					$sel.val(val);
					if (onClick) onClick(val, item);
				});
			$pill.append($opt);
			$sel.append($('<option></option>').val(val).text(label));
		});

		$sel.off('change.illTapeNeon').on('change.illTapeNeon', function () {
			var v = $(this).val();
			$pill.find('.pill-option').removeClass('active');
			$pill.find('[data-value="' + v + '"]').addClass('active');
			var matched = items.find(function (i) { return i[valueKey] === v; });
			if (onClick) onClick(v, matched);
		});
	};

	// ────────────────────────────────────────────────────────────────
	// Selection handlers
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._onEnvironmentSelect = function (val) {
		this.selections.environment_rating = val;
		this.$('#stepCCT').removeClass('disabled-step');
		this._cascadeOptions();
	};
	TapeNeon.prototype._onCCTSelect = function (val) {
		this.selections.cct = val;
		this.$('#stepOutput').removeClass('disabled-step');
		this._cascadeOptions();
	};
	TapeNeon.prototype._onOutputSelect = function (val) {
		this.selections.output_level = val;
		if (this.IS_NEON) {
			this.$('#stepFinish').removeClass('disabled-step');
		} else {
			this.$('#stepTapeFeed').removeClass('disabled-step');
		}
		this._updateCalculateButton();
	};
	TapeNeon.prototype._onFinishSelect = function (val) {
		this.selections.finish = val;
		this.$('#stepNeonSegments').removeClass('disabled-step');
		if (this.neonSegmentCount === 0) this._addNeonSegment();
		this._updateCalculateButton();
	};
	TapeNeon.prototype._onFeedTypeSelect = function (val) {
		this.selections.feed_type = val;
		this._updateCalculateButton();
	};

	TapeNeon.prototype._cascadeOptions = function () {
		if (this.IS_NEON) return;
		var self = this;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_tape_cascading_options',
			args: {
				environment_rating: this.selections.environment_rating || '',
				cct: this.selections.cct || ''
			},
			callback: function (r) {
				if (r.message && r.message.success && r.message.output_levels) {
					self._populatePill('pillOutput', 'selOutput', r.message.output_levels,
						'value', 'label', function (v, item) { self._onOutputSelect(v, item); });
				}
			}
		});
	};

	// ────────────────────────────────────────────────────────────────
	// Neon segment builder
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._addNeonSegment = function () {
		var self = this;
		this.neonSegmentCount++;
		var idx = this.neonSegmentCount;

		var ipOptions = (this.initData && this.initData.options && this.initData.options.ip_ratings) || [];
		var startFeedDirOptions = (this.initData && this.initData.options && (this.initData.options.start_feed_directions || this.initData.options.feed_directions)) || [];
		var endFeedDirOptions = (this.initData && this.initData.options && (this.initData.options.end_feed_directions || this.initData.options.feed_directions)) || [];

		var ipOptionsHtml = '<option value="">Select...</option>';
		ipOptions.forEach(function (o) { ipOptionsHtml += '<option value="' + o.value + '">' + o.label + '</option>'; });
		var startFeedDirHtml = '<option value="">Select...</option>';
		startFeedDirOptions.forEach(function (o) { startFeedDirHtml += '<option value="' + o.value + '">' + o.label + '</option>'; });
		var endFeedDirHtml = '<option value="">Select...</option>';
		endFeedDirOptions.forEach(function (o) { endFeedDirHtml += '<option value="' + o.value + '">' + o.label + '</option>'; });

		var html = ''
			+ '<div class="segment-card" id="neonSeg' + idx + '" data-seg-idx="' + idx + '">'
			+ '<div class="card-header">'
			+ '<strong>Segment ' + idx + '</strong>'
			+ (idx > 1 ? '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-seg" data-seg="' + idx + '"><i class="fa fa-trash"></i></button>' : '')
			+ '</div>'
			+ '<div class="card-body">'
			+ '<div class="row">'
			+   '<div class="col-md-6"><div class="form-group mb-2">'
			+     '<label class="small font-weight-bold">IP Rating (Endcaps)</label>'
			+     '<select class="form-control seg-ip-rating" data-seg="' + idx + '">' + ipOptionsHtml + '</select>'
			+   '</div></div>'
			+   '<div class="col-md-6"><div class="form-group mb-2">'
			+     '<label class="small font-weight-bold">Start Feed Direction</label>'
			+     '<select class="form-control seg-start-feed-dir" data-seg="' + idx + '">' + startFeedDirHtml + '</select>'
			+   '</div></div>'
			+ '</div>'
			+ '<div class="row">'
			+   '<div class="col-md-4"><div class="form-group mb-2">'
			+     '<label class="small font-weight-bold">Start Lead Length (in)</label>'
			+     '<input type="number" class="form-control seg-start-lead" data-seg="' + idx + '" min="0" step="0.25" placeholder="e.g. 12">'
			+   '</div></div>'
			+   '<div class="col-md-4"><div class="form-group mb-2">'
			+     '<label class="small font-weight-bold">Fixture Length</label>'
			+     '<div class="input-group">'
			+       '<input type="number" class="form-control seg-fixture-len" data-seg="' + idx + '" min="0" step="0.125" placeholder="Length">'
			+       '<select class="form-control seg-fixture-unit" data-seg="' + idx + '" style="max-width: 80px;">'
			+         '<option value="in">in</option><option value="ft">ft</option><option value="ft_in">ft+in</option>'
			+       '</select>'
			+     '</div>'
			+     '<div class="seg-ft-in-row mt-1" data-seg="' + idx + '" style="display:none;">'
			+       '<div class="row">'
			+         '<div class="col-6"><input type="number" class="form-control seg-ft-val" data-seg="' + idx + '" min="0" step="1" placeholder="ft"></div>'
			+         '<div class="col-6"><input type="number" class="form-control seg-in-val" data-seg="' + idx + '" min="0" step="0.125" placeholder="in"></div>'
			+       '</div>'
			+     '</div>'
			+   '</div></div>'
			+   '<div class="col-md-4"><div class="form-group mb-2">'
			+     '<label class="small font-weight-bold">End Feed Direction</label>'
			+     '<select class="form-control seg-end-feed-dir" data-seg="' + idx + '">' + endFeedDirHtml + '</select>'
			+   '</div></div>'
			+ '</div>'
			+ '<div class="row">'
			+   '<div class="col-md-4"><div class="form-group mb-2">'
			+     '<label class="small font-weight-bold">Exit / Jumper Length (in)</label>'
			+     '<input type="number" class="form-control seg-end-feed-len" data-seg="' + idx + '" min="0" step="0.25" placeholder="e.g. 6">'
			+   '</div></div>'
			+ '</div>'
			+ '</div></div>';

		this.$('#neonSegmentContainer').append(html);

		this.$('#neonSeg' + idx + ' .seg-fixture-unit').on('change', function () {
			var unit = $(this).val();
			var segIdx = $(this).data('seg');
			if (unit === 'ft_in') {
				self.$('.seg-ft-in-row[data-seg="' + segIdx + '"]').show();
				self.$('.seg-fixture-len[data-seg="' + segIdx + '"]').hide();
			} else {
				self.$('.seg-ft-in-row[data-seg="' + segIdx + '"]').hide();
				self.$('.seg-fixture-len[data-seg="' + segIdx + '"]').show();
			}
		});

		this.$('#neonSeg' + idx + ' .btn-remove-seg').on('click', function () {
			self._removeNeonSegment($(this).data('seg'));
		});

		this._updateCalculateButton();
	};

	TapeNeon.prototype._removeNeonSegment = function (segIdx) {
		this.$('#neonSeg' + segIdx).remove();
		this._renumberNeonSegments();
		this._updateCalculateButton();
	};

	TapeNeon.prototype._renumberNeonSegments = function () {
		var count = 0;
		this.$('#neonSegmentContainer .segment-card').each(function (i) {
			count = i + 1;
			$(this).find('.card-header strong').text('Segment ' + count);
		});
		this.neonSegmentCount = count;
	};

	TapeNeon.prototype._collectNeonSegments = function () {
		var segments = [];
		this.$('#neonSegmentContainer .segment-card').each(function () {
			var $card = $(this);
			var unit = $card.find('.seg-fixture-unit').val() || 'in';
			var seg = {
				ip_rating: $card.find('.seg-ip-rating').val(),
				start_feed_direction: $card.find('.seg-start-feed-dir').val(),
				start_lead_length_inches: parseFloat($card.find('.seg-start-lead').val()) || 0,
				fixture_length_unit: unit,
				end_feed_direction: $card.find('.seg-end-feed-dir').val(),
				end_feed_length_inches: parseFloat($card.find('.seg-end-feed-len').val()) || 0
			};
			if (unit === 'ft_in') {
				seg.fixture_length_feet = parseFloat($card.find('.seg-ft-val').val()) || 0;
				seg.fixture_length_inches = parseFloat($card.find('.seg-in-val').val()) || 0;
			} else {
				seg.fixture_length_value = parseFloat($card.find('.seg-fixture-len').val()) || 0;
			}
			segments.push(seg);
		});
		return segments;
	};

	// ────────────────────────────────────────────────────────────────
	// Calculate
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._updateCalculateButton = function () {
		var ready = false;
		if (this.IS_NEON) {
			ready = this.selections.cct && this.selections.output_level
				&& this.selections.finish
				&& this.neonSegmentCount > 0;
		} else {
			var hasLength = false;
			var unit = this.selections.tape_length_unit || 'in';
			if (unit === 'ft_in') {
				var ftVal = parseFloat(this.$('#tapeLengthFeet').val());
				var inVal = parseFloat(this.$('#tapeLengthInches').val());
				hasLength = (ftVal > 0 || inVal > 0);
			} else {
				hasLength = parseFloat(this.$('#tapeLengthValue').val()) > 0;
			}
			ready = this.selections.cct && this.selections.output_level
				&& this.selections.feed_type
				&& parseFloat(this.$('#leadLengthInches').val()) > 0
				&& hasLength;
		}
		this.$('#btnCalculate').prop('disabled', !ready);
	};

	TapeNeon.prototype.doCalculate = function () {
		this.$('#resultsCard').hide();
		this.$('#errorsCard').hide();
		if (this.IS_NEON) this._calculateNeon();
		else this._calculateTape();
	};

	TapeNeon.prototype._calculateTape = function () {
		var self = this;
		var unit = this.selections.tape_length_unit || 'in';
		var leadVal = parseFloat(this.$('#leadLengthInches').val());
		var leadLength = (!isNaN(leadVal) && leadVal > 0) ? leadVal : 0;

		var args = {
			selections: JSON.stringify({
				environment_rating: this.selections.environment_rating || '',
				cct: this.selections.cct,
				output_level: this.selections.output_level,
				feed_direction: 'End Feed',
				feed_type: this.selections.feed_type || '',
				lead_length_inches: leadLength,
				tape_length_unit: unit,
				tape_length_value: parseFloat(this.$('#tapeLengthValue').val()) || 0,
				tape_length_feet: parseFloat(this.$('#tapeLengthFeet').val()) || 0,
				tape_length_inches: parseFloat(this.$('#tapeLengthInches').val()) || 0
			})
		};
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.validate_tape_configuration',
			args: args, freeze: true, freeze_message: 'Calculating...',
			callback: function (r) { self._handleResult(r.message); }
		});
	};

	TapeNeon.prototype._calculateNeon = function () {
		var self = this;
		var segments = this._collectNeonSegments();
		var args = {
			selections: JSON.stringify({
				cct: this.selections.cct,
				output_level: this.selections.output_level,
				finish: this.selections.finish
			}),
			segments_json: JSON.stringify(segments)
		};
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.validate_neon_configuration',
			args: args, freeze: true, freeze_message: 'Calculating...',
			callback: function (r) { self._handleResult(r.message); }
		});
	};

	TapeNeon.prototype._handleResult = function (result) {
		if (!result) { this._showError('No response from server'); return; }
		this.lastResult = result;
		if (result.is_valid) this._showResults(result);
		else this._showError(result.error || 'Validation failed');
	};

	// ────────────────────────────────────────────────────────────────
	// Display results
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._showResults = function (result) {
		this.$('#errorsCard').hide();
		this.$('#resultsCard').show();
		this.$('#resultPartNumber').text(result.part_number || '-');
		this.$('#resultDescription').text(result.build_description || '-');

		var c = result.computed || {};
		if (this.IS_NEON) {
			this.$('#resultMfgLength').text(
				(c.total_manufacturable_length_in || 0).toFixed(2) + '" ('
				+ (c.total_manufacturable_length_ft || 0).toFixed(2) + ' ft)');
			this.$('#resultReqLength').text((c.total_requested_length_in || 0).toFixed(2) + '"');
			var totalDiff = (c.total_requested_length_mm || 0) - (c.total_manufacturable_length_mm || 0);
			this.$('#resultDifference').text((totalDiff / 25.4).toFixed(2) + '"');
		} else {
			this.$('#resultMfgLength').text(
				(c.manufacturable_length_in || 0).toFixed(2) + '" ('
				+ (c.manufacturable_length_ft || 0).toFixed(2) + ' ft)');
			this.$('#resultReqLength').text((c.requested_length_in || 0).toFixed(2) + '"');
			this.$('#resultDifference').text(((c.difference_mm || 0) / 25.4).toFixed(2) + '"');
		}
		this.$('#resultWatts').text((c.total_watts || 0).toFixed(2) + ' W');

		if (c.max_run_ft_effective) {
			this.$('#resultMaxRunRow').show();
			var maxRunText = c.max_run_ft_effective + ' ft';
			if (c.max_run_ft_by_voltage_drop && c.max_run_ft_by_watts) {
				var limiting = (c.max_run_ft_by_voltage_drop <= c.max_run_ft_by_watts) ? 'voltage drop' : 'wattage';
				maxRunText += ' (' + limiting + ')';
			}
			this.$('#resultMaxRunLength').text(maxRunText);
		} else {
			this.$('#resultMaxRunRow').hide();
		}

		if (c.runs_count && c.runs_count > 1) {
			this.$('#resultRunsCountRow').show();
			this.$('#resultRunsCount').text(c.runs_count);
		} else {
			this.$('#resultRunsCountRow').hide();
		}

		if (c.is_free_cutting) {
			this.$('#resultCutInfo').text('Free cutting (no increment restriction)');
		} else {
			this.$('#resultCutInfo').text('Cut increment: ' + (c.cut_increment_mm || 0) + ' mm');
		}

		this.$('#resultMessages').empty();
		if (result.messages && result.messages.length) {
			var $msg = this.$('#resultMessages');
			result.messages.forEach(function (msg) {
				var cls = msg.severity === 'warning' ? 'alert-warning' : 'alert-info';
				$msg.append('<div class="alert ' + cls + ' py-1 px-2 small">' + msg.text + '</div>');
			});
		}

		if (c.runs && c.runs.length > 1) {
			this.$('#resultRunBreakdown').show();
			var runsHtml = '<table class="table table-sm table-bordered mb-0">'
				+ '<thead class="thead-light"><tr><th>Run</th><th>Length</th><th>Watts</th></tr></thead><tbody>';
			c.runs.forEach(function (run) {
				var lengthIn = (run.run_len_in || (run.run_len_mm / 25.4)).toFixed(2);
				var lengthFt = (run.run_len_ft || (run.run_len_mm / 304.8)).toFixed(2);
				runsHtml += '<tr><td class="text-center">' + run.run_index + '</td>'
					+ '<td class="text-right">' + lengthIn + '" (' + lengthFt + ' ft)</td>'
					+ '<td class="text-right">' + run.run_watts.toFixed(1) + ' W</td></tr>';
			});
			runsHtml += '</tbody></table>';
			this.$('#resultRunsList').html(runsHtml);
		} else {
			this.$('#resultRunBreakdown').hide();
		}

		if (this.IS_NEON && c.segments && c.segments.length) {
			this.$('#resultSegments').show();
			var $list = this.$('#resultSegmentsList');
			$list.empty();
			c.segments.forEach(function (seg) {
				$list.append(
					'<div class="small result-row">'
					+ '<strong>Seg ' + seg.segment_index + '</strong>: '
					+ seg.manufacturable_length_in.toFixed(2) + '" | '
					+ 'IP: ' + (seg.ip_rating || '-') + ' | '
					+ 'Start: ' + (seg.start_feed_direction || '-') + ' ' + seg.start_lead_length_inches + '" | '
					+ 'End: ' + (seg.end_feed_direction || '-') + ' ' + seg.end_feed_length_inches + '"'
					+ '</div>'
				);
			});
		} else {
			this.$('#resultSegments').hide();
		}

		this.$('#btnSaveToSchedule').prop('disabled', !this.CAN_SAVE && !this.$('#scheduleSelect').val());
		this._loadMountingAccessories(result);
	};

	TapeNeon.prototype._showError = function (msg) {
		this.$('#resultsCard').hide();
		this.$('#errorsCard').show();
		this.$('#mountingAccessorySection').hide();
		this.$('#errorMessage').text(msg);
	};

	// ────────────────────────────────────────────────────────────────
	// Mounting accessory picker
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._loadMountingAccessories = function (result) {
		var self = this;
		this.$('#mountingAccessorySection').hide();
		this.selectedMountingAccessory = null;

		var templateCode = result.template_code;
		if (!templateCode) return;

		var computed = result.computed || {};
		var lengthMm = this.IS_NEON
			? (computed.total_manufacturable_length_mm || 0)
			: (computed.manufacturable_length_mm || 0);
		var segmentCount = computed.segment_count || 1;

		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_mounting_accessories',
			args: {
				template_code: templateCode,
				product_category: this.PRODUCT_CATEGORY,
				length_mm: lengthMm,
				environment_rating: this.selections.environment_rating || '',
				segments: segmentCount
			},
			callback: function (r) {
				if (r.message && r.message.success && r.message.accessories && r.message.accessories.length) {
					self._renderMountingAccessoryCards(r.message.accessories);
				}
			}
		});
	};

	TapeNeon.prototype._renderMountingAccessoryCards = function (accessories) {
		var self = this;
		var $container = this.$('#mountingAccessoryCards');
		$container.empty();

		var skipHtml = '<div class="card mb-2 mounting-card active" data-item="" style="cursor:pointer; border: 2px solid #007bff;">'
			+ '<div class="card-body py-2 px-3"><strong>Skip</strong> — No mounting accessory</div></div>';
		$container.append(skipHtml);

		accessories.forEach(function (acc) {
			var totalStr = '$' + acc.total_msrp.toFixed(2);
			var unitStr = '$' + acc.unit_msrp.toFixed(2);
			var html = '<div class="card mb-2 mounting-card" data-item="' + acc.accessory_item + '" '
				+ 'data-qty="' + acc.qty_recommended + '" '
				+ 'data-unit-msrp="' + acc.unit_msrp + '" '
				+ 'style="cursor:pointer;">'
				+ '<div class="card-body py-2 px-3">'
				+ '<strong>' + acc.mounting_method + '</strong> (' + acc.accessory_item + ')<br>'
				+ '<small class="text-muted">Recommended: ' + acc.qty_recommended + ' pcs × ' + unitStr + ' = ' + totalStr + '</small><br>'
				+ '<small class="text-muted">' + acc.qty_rule_description + '</small>'
				+ '</div></div>';
			$container.append(html);
		});

		$container.find('.mounting-card').on('click', function () {
			$container.find('.mounting-card').css('border', '1px solid #dee2e6').removeClass('active');
			$(this).css('border', '2px solid #007bff').addClass('active');

			var itemCode = $(this).data('item');
			if (itemCode) {
				self.selectedMountingAccessory = {
					accessory_item: itemCode,
					qty: parseInt($(this).data('qty')) || 0,
					unit_msrp: parseFloat($(this).data('unit-msrp')) || 0
				};
				self.selectedMountingAccessory.total_msrp =
					self.selectedMountingAccessory.qty * self.selectedMountingAccessory.unit_msrp;
				self.$('#mountingAccessoryQty').val(self.selectedMountingAccessory.qty);
				self._updateMountingAccessoryPrice();
				self.$('#mountingAccessoryQtyRow').show();
			} else {
				self.selectedMountingAccessory = null;
				self.$('#mountingAccessoryQtyRow').hide();
			}
		});

		this.$('#mountingAccessorySection').show();
	};

	TapeNeon.prototype._updateMountingAccessoryPrice = function () {
		if (!this.selectedMountingAccessory) return;
		var qty = parseInt(this.$('#mountingAccessoryQty').val()) || 0;
		this.selectedMountingAccessory.qty = qty;
		this.selectedMountingAccessory.total_msrp = qty * this.selectedMountingAccessory.unit_msrp;
		this.$('#mountingAccessoryPriceCalc').text(
			'$' + this.selectedMountingAccessory.unit_msrp.toFixed(2) + ' × ' + qty
			+ ' = $' + this.selectedMountingAccessory.total_msrp.toFixed(2)
		);
	};

	// ────────────────────────────────────────────────────────────────
	// Save
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype.saveToSchedule = function () {
		if (!this.lastResult || !this.lastResult.is_valid) {
			frappe.msgprint({ title: 'Error', message: 'Please calculate a valid configuration first', indicator: 'red' });
			return;
		}
		var scheduleName = this.$('#scheduleSelect').val() || this.SCHEDULE_NAME;
		if (!scheduleName) {
			frappe.msgprint({ title: 'Error', message: 'Please select a schedule first', indicator: 'orange' });
			return;
		}

		var resultToSave = JSON.parse(JSON.stringify(this.lastResult));
		if (this.selectedMountingAccessory && this.selectedMountingAccessory.accessory_item) {
			resultToSave.selections = resultToSave.selections || {};
			resultToSave.selections.mounting_accessory_item = this.selectedMountingAccessory.accessory_item;
			resultToSave.selections.mounting_accessory_qty = this.selectedMountingAccessory.qty;
			resultToSave.selections.mounting_accessory_unit_msrp = this.selectedMountingAccessory.unit_msrp;
			resultToSave.selections.mounting_accessory_total_msrp = this.selectedMountingAccessory.total_msrp;
		}

		var lineIdx = this.$('#lineSelect').val();
		var lineIdxVal = (lineIdx && lineIdx !== '__new__') ? parseInt(lineIdx) : null;

		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.save_tape_to_schedule',
			args: {
				schedule_name: scheduleName,
				line_idx: lineIdxVal,
				configuration_result: JSON.stringify(resultToSave)
			},
			freeze: true, freeze_message: 'Saving...',
			callback: function (r) {
				if (r.message && r.message.success) {
					frappe.msgprint({
						title: 'Saved', indicator: 'green',
						message: r.message.message || 'Configuration saved to schedule'
					});
				} else {
					frappe.msgprint({
						title: 'Error', indicator: 'red',
						message: (r.message && r.message.error) || 'Failed to save'
					});
				}
			}
		});
	};

	// ────────────────────────────────────────────────────────────────
	// Schedule context (project / schedule / line dropdowns)
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._loadScheduleContext = function () {
		var $proj = this.$('#projectSelect');
		root.IllConfigurator.loadUserProjects($proj, this.PROJECT_NAME || null);
	};

	// ────────────────────────────────────────────────────────────────
	// Event bindings
	// ────────────────────────────────────────────────────────────────
	TapeNeon.prototype._bindEvents = function () {
		var self = this;

		this.$('#btnCalculate').on('click', function () { self.doCalculate(); });
		this.$('#btnSaveToSchedule').on('click', function () { self.saveToSchedule(); });

		if (this.IS_NEON) {
			this.$('#btnAddNeonSegment').on('click', function () { self._addNeonSegment(); });
		}

		// Tape length unit tabs
		this.$('#tapeLengthUnitTabs .nav-link').on('click', function (e) {
			e.preventDefault();
			self.$('#tapeLengthUnitTabs .nav-link').removeClass('active');
			$(this).addClass('active');
			var unit = $(this).data('unit');
			self.selections.tape_length_unit = unit;
			if (unit === 'ft_in') {
				self.$('#tapeLengthSingle').hide();
				self.$('#tapeLengthFtIn').show();
			} else {
				self.$('#tapeLengthSingle').show();
				self.$('#tapeLengthFtIn').hide();
				self.$('#tapeLengthValue').attr('placeholder', unit === 'ft' ? 'Feet' : 'Inches');
			}
			self._updateCalculateButton();
		});

		// Re-evaluate Calculate when input fields change
		this.$('#leadLengthInches, #tapeLengthValue, #tapeLengthFeet, #tapeLengthInches')
			.on('input change', function () { self._updateCalculateButton(); });

		// Mounting accessory qty
		this.$root.on('change', '#mountingAccessoryQty', function () {
			self._updateMountingAccessoryPrice();
		});

		// Project select → load schedules
		this.$('#projectSelect').on('change', function () {
			var proj = $(this).val();
			var $sch = self.$('#scheduleSelect');
			var $ln = self.$('#lineSelect');
			if (!proj) {
				$sch.prop('disabled', true).val('');
				$ln.prop('disabled', true).val('');
				return;
			}
			root.IllConfigurator.loadSchedulesForProject(proj, $sch, self.SCHEDULE_NAME || null);
		});

		// Schedule select → load lines
		this.$('#scheduleSelect').on('change', function () {
			var sch = $(this).val();
			var $ln = self.$('#lineSelect');
			if (!sch) { $ln.prop('disabled', true).val(''); return; }
			root.IllConfigurator.loadLinesForSchedule(sch, $ln, self.LINE_IDX);
		});
	};

	root.IllConfigurator.TapeNeon = TapeNeon;

}(window));
