/** Scoped adapter for the legacy segment/reel coordinator. Geometry remains server-owned. */
(function (root) {
'use strict';
var Base = root.IllConfigurator.Base;
function Coordinator(rootEl, context) {
    context = context || {};
    Base.call(this, rootEl, context);
    var self = this, ready = [], initialized = false;
    function $(value) {
        if (typeof value === 'function') { ready.push(value); return; }
        if (value === document) return self.$root;
        if (typeof value === 'string' && value.trim().charAt(0) !== '<') return self.$(value);
        return root.jQuery(value);
    }
    $.extend = root.jQuery.extend;
    self.invalidateValidation = function () {
        Base.prototype.invalidateValidation.call(self);
        currentResult = tnCurrentResult = bulkReelCurrentResult = null;
        $('#saveBtn, #tnSaveBtn, #brSaveBtn, #buildItemBtn, #tnBuildItemBtn').prop('disabled', true);
        $('#resultsContent, #tnResultsContent, #brResultsContent').hide();
        $('#calculateBtn, #tnCalculateBtn, #brCalculateBtn').each(function () {
            var label = $(this).data('illCalculationLabel');
            if (label) $(this).html(label);
        });
    };
    self._updateButtons = function () { if (isTapeNeon) tnUpdateUI(); else updateUI(); };
	self.restoreGeometry = function (geometry) {
		var list = isTape ? '#tapeSegmentsList' : (isNeon ? '#neonSegmentsList' : '#segmentsList');
		$(list).empty(); segmentCount = tapeSegmentCount = neonSegmentCount = 0;
		(geometry.segments || []).forEach(function (segment, index) {
			if (isTape) addTapeSegment(index === 0); else if (isNeon) addNeonSegment(index === 0); else addSegment(index === 0);
			self.restoreSegment($(list).children().last(), segment, isTape ? 'tape' : (isNeon ? 'neon' : 'linear'));
		});
		if (isTapeNeon) tnUpdateUI(); else updateUI();
	};
	self.exportRequest = function () {
		var selections = {};
		if (isTapeNeon) {
			['environment_rating', 'cct', 'output_level', 'pcb_finish', 'pcb_mounting', 'finish'].forEach(function (key) { selections[key] = self.$name('tn_' + key).val(); });
			var power = powerSelections();
			Object.assign(selections, power || {override_max_run_ft: $('#overrideMaxRunInput').val()});
			if (bulkReelMode) selections.ordering_mode = 'BULK_REEL';
			return {family: productCategory, template: self.$name('fixture_template_code').val() || context.selected_template,
				selections: selections, segments: isTape ? tnCollectTapeSegments() : tnCollectNeonSegments()};
		}
		['fixture_template_code', 'led_package_code', 'environment_rating_code', 'cct_code', 'lens_appearance_code', 'finish_code', 'mounting_method_code', 'endcap_color_code', 'delivered_output_value', 'tape_offering_id'].forEach(function (key) { selections[key] = self.$name(key).val(); });
		selections.segments = collectSegments();
		selections.include_power_supply = $('#includePowerSupply').is(':checked');
		selections.dimming_protocol_code = self.$name('dimming_protocol_code').val() || '';
		selections.override_max_run_ft = $('#overrideMaxRunCheck').is(':checked') ? $('#overrideMaxRunInput').val() : '';
		return {family: productCategory, template: selections.fixture_template_code, selections: selections};
	};
    function coordinatorRequest(options) {
        if (/\.validate_/.test(options.method)) {
            self.invalidateValidation();
            options.isCurrent = self.validationGuard();
			options.args._skip_record_creation = true;
        } else if (!options.isCurrent && /\.(init_|get_|auto_select)/.test(options.method)) {
            var relevant = Object.keys(options.args || {}).map(function (key) {
                var field = {template_code: 'fixture_template_code', environment_rating: 'tn_environment_rating', cct: 'tn_cct', pcb_finish: 'tn_pcb_finish', finish: 'tn_finish'}[key] || key;
                var $field = self.$name(field).filter('select, input').first();
                return { field: $field, value: $field.val() };
            });
            options.isCurrent = function () { return relevant.every(function (entry) { return entry.field.val() === entry.value; }); };
        }
        return self.request(options);
    }
    self.init = function () {
        if (initialized || self.destroyed) return self;
        initialized = true;
		$('#segmentsList, #tapeSegmentsList, #neonSegmentsList').empty();
        $('#calculateBtn, #tnCalculateBtn, #brCalculateBtn').each(function () {
            $(this).data('illCalculationLabel', $(this).html());
        });
        if (context.selected_template) self.$name('fixture_template_code').val(context.selected_template);
        ready.forEach(function (callback) { callback(); });
        return self;
    };
    self.$root.on('click.' + self.instanceId, '[data-coordinator-action]', function (event) {
        event.preventDefault();
        var action = this.getAttribute('data-coordinator-action');
        if (/^(set|select|remove|add)/.test(action)) self.invalidateValidation();
        switch (action) {
case 'dismiss-warning': this.parentNode.style.display='none'; break;
case 'validateAndQuote-1': validateAndQuote(); break;
case 'buildConfiguredFixtureAndItem-2': buildConfiguredFixtureAndItem(); break;
case 'saveToSchedule-3': saveToSchedule(); break;
case 'setTapeMode-4': setTapeMode('custom'); break;
case 'setTapeMode-5': setTapeMode('reel'); break;
case 'selectBulkReelLength-6': selectBulkReelLength(16.4); break;
case 'selectBulkReelLength-7': selectBulkReelLength(50); break;
case 'selectBulkReelLength-8': selectBulkReelLength(100); break;
case 'bulkReelCalculate-9': bulkReelCalculate(); break;
case 'bulkReelSave-10': bulkReelSave(); break;
case 'tnValidateAndQuote-11': tnValidateAndQuote(); break;
case 'tnBuildConfiguredItem-12': tnBuildConfiguredItem(); break;
case 'tnSaveToSchedule-13': tnSaveToSchedule(); break;
case 'copyToClipboard-14': copyToClipboard('partNumberValue'); break;
case 'copyToClipboard-15': copyToClipboard('partDescriptionValue'); break;
case 'copyBothToClipboard-16': copyBothToClipboard(); break;
case 'removeSegment-17': removeSegment(this); break;
case 'setEndType-18': setEndType(this, 'Endcap'); break;
case 'setEndType-19': setEndType(this, 'Jumper'); break;
case 'removeTapeSegment-20': removeTapeSegment(this); break;
case 'setTapeEndType-21': setTapeEndType(this, 'Endcap'); break;
case 'setTapeEndType-22': setTapeEndType(this, 'Jumper'); break;
case 'removeNeonSegment-23': removeNeonSegment(this); break;
case 'setNeonEndType-24': setNeonEndType(this, 'Endcap'); break;
case 'setNeonEndType-25': setNeonEndType(this, 'Jumper'); break;
        }
    });
    self.$root.on('change.' + self.instanceId, self.selector('#overrideMaxRunCheck'), function () {
        $('#overrideMaxRunGroup, #overrideMaxRunWarning').toggle(this.checked);
    });
// Quiz handoff from Webflow configurator — consumed by this page
self.quizHandoff = context.quiz_handoff || {};

var schedule_name = context.schedule_name || '';
var line_idx = context.line_idx == null ? null : context.line_idx;
var prefill_project = context.project_name || '';
var currentResult = null;
var lastFixtureSelections = null, lastTnSelections = null, lastTnSegments = null, lastTnTemplate = null;
var templateOptions = null;
var segmentCount = 0;
var MM_PER_INCH = 25.4;
var MM_PER_FOOT = 304.8;
var INCHES_PER_FOOT = 12;
var scheduleLines = [];  // Cached schedule lines
var canSaveToSchedule = !!context.can_save;
var isSystemManager = !!context.is_system_manager;
var isPopulating = false;  // Flag to suppress cascading events during populateOptions
var isMultiCCT = false;  // Track whether the current LED package is multi-CCT (Tunable White, etc.)
var MULTI_CCT_SPECTRUM_TYPES = ['Tunable White', 'Dim to Warm', 'RGB+TW', 'RGBTW', 'RGB+W', 'RGBW'];

// ─── Category context (from server) ───
var productCategory = context.product_category || 'Linear Fixture';
var isTapeNeon = !!context.is_tape_neon;
var isNeon = !!context.is_neon;
var isTape = !!context.is_tape;
var hasTemplates = !!context.has_templates;
var tnTemplateOptions = null;     // Tape/Neon template init data
var tnCurrentResult = null;       // Tape/Neon validation result
var bulkReelMode = false;         // Whether bulk reel mode is active (tape only)
var bulkReelCurrentResult = null; // Bulk reel validation result
var bulkReelSelectedLength = null;// Selected bulk reel length in feet
var lastBulkSelections = null, lastBulkTemplate = null;
var restoreApplied = false;

function restoreCoordinator() {
	var request = context.initial_request;
	if (restoreApplied || !request) return;
	restoreApplied = true;
	var selections = request.selections || {};
	var fields = {};
	var common = isTapeNeon ? ['environment_rating', 'cct', 'output_level', 'pcb_finish', 'pcb_mounting', 'finish'] : ['led_package_code', 'environment_rating_code', 'cct_code', 'lens_appearance_code', 'finish_code', 'mounting_method_code', 'delivered_output_value', 'tape_offering_id'];
	common.forEach(function (key) { if (selections[key] != null) fields['[name="' + (isTapeNeon ? 'tn_' : '') + key + '"]'] = selections[key]; });
	self.queueRestoreFields(fields);
	self.restorePower(selections);
	if (selections.ordering_mode === 'BULK_REEL') {
		setTapeMode('reel');
		var factor = selections.tape_length_unit === 'ft' ? 1 : 1 / 12;
		selectBulkReelLength(Number(selections.tape_length_value) * factor);
		self.queueRestoreFields({'#brIncludePowerSupply': selections.include_power_supply, '[name="br_dimming_protocol_code"]': selections.dimming_protocol_code || ''});
		return;
	}
	var segments = request.segments || selections.segments || selections.segments_json || [];
	if (typeof segments === 'string') segments = JSON.parse(segments);
	if (!segments.length) return;
	var list = isTape ? '#tapeSegmentsList' : (isNeon ? '#neonSegmentsList' : '#segmentsList');
	$(list).empty(); segmentCount = tapeSegmentCount = neonSegmentCount = 0;
	segments.forEach(function (segment, index) {
		if (isTape) addTapeSegment(index === 0); else if (isNeon) addNeonSegment(index === 0); else addSegment(index === 0);
		var $card = $(list).children().last();
		self.restoreSegment($card, segment, isTape ? 'tape' : (isNeon ? 'neon' : 'linear'));
	});
	if (isTapeNeon) tnUpdateUI(); else updateUI();
}
var neonSegmentCount = 0;         // Neon segment counter
var tapeSegmentCount = 0;         // Tape run/segment counter (jumper chaining)
var DEFAULT_FEED_DIRECTION = 'End Feed';  // Default feed direction for tape


// =====================================================================
// Schedule Context Selectors (Project / Schedule / Line)
// =====================================================================

function loadUserProjects() {
	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_user_projects_for_configurator',
		callback: function(r) {
			if (r.message && r.message.success) {
				var select = $('#projectSelect');
				select.empty().append('<option value="">Select Project...</option>');
				r.message.projects.forEach(function(p) {
					select.append('<option value="' + p.value + '">' + p.label + '</option>');
				});
				// Pre-fill if coming from schedule page
				if (prefill_project) {
					select.val(prefill_project);
					select.trigger('change');
				}
			}
		}
	});
}

function loadSchedulesForProject(project_name) {
	self.setScheduleSnapshot(null);
	$('#scheduleSelect').empty().append('<option value="">Select Schedule...</option>').prop('disabled', true);
	$('#lineSelect').empty().append('<option value="">Select Line...</option><option value="__new__">+ New Line</option>').prop('disabled', true);
	$('#linePreview').hide();
	updateSaveButtonVisibility();

	if (!project_name) return;

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedules_for_project',
		args: { project_name: project_name },
		isCurrent: function () { return $('#projectSelect').val() === project_name; },
		callback: function(r) {
			if (r.message && r.message.success) {
				var select = $('#scheduleSelect');
				select.empty().append('<option value="">Select Schedule...</option>');
				r.message.schedules.forEach(function(s) {
					var statusBadge = s.status ? ' [' + s.status + ']' : '';
					select.append('<option value="' + s.value + '">' + s.label + statusBadge + '</option>');
				});
				select.prop('disabled', false);

				// Pre-fill if coming from schedule page
				if (schedule_name) {
					select.val(schedule_name);
					select.trigger('change');
				}
			}
		}
	});
}

function loadScheduleLines(sched_name) {
	self.setScheduleSnapshot(null);
	$('#lineSelect').empty().append('<option value="">Select Line...</option><option value="__new__">+ New Line</option>').prop('disabled', true);
	$('#linePreview').hide();
	scheduleLines = [];
	schedule_name = sched_name;
	updateSaveButtonVisibility();

	if (!sched_name) return;

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator',
		args: { schedule_name: sched_name },
		isCurrent: function () { return $('#scheduleSelect').val() === sched_name; },
		callback: function(r) {
			if (r.message && r.message.success) {
				scheduleLines = r.message.lines;
				self.setScheduleSnapshot(r.message);
				canSaveToSchedule = r.message.can_save;

				var select = $('#lineSelect');
				select.empty().append('<option value="">Select Line...</option>');

				r.message.lines.forEach(function(l) {
					var typeLabel = '';
					if (l.manufacturer_type === 'OTHER') typeLabel = ' [Other Mfg]';
					else if (l.manufacturer_type === 'ACCESSORY') typeLabel = ' [Accessory]';
					else if (l.configuration_status === 'Configured') typeLabel = ' [Configured]';
					else typeLabel = ' [Pending]';

					select.append('<option value="' + l.idx + '">' + l.line_id + typeLabel + '</option>');
				});

				select.append('<option value="__new__">+ New Line</option>');
				select.prop('disabled', false);

				// Pre-fill if coming from schedule page
				if (context.line_key && sched_name === context.schedule_name) {
					var savedLine = scheduleLines.find(function (line) { return line.line_key === context.line_key; });
					line_idx = savedLine ? savedLine.idx : null;
				}
				if (line_idx !== null) {
					select.val(line_idx);
					select.trigger('change');
				} else if (context.draft_id) {
					select.val('__new__').trigger('change');
				}

				updateSaveButtonVisibility();
			}
		}
	});
}

function showLinePreview(lineIdx) {
	$('#linePreview').hide();

	if (lineIdx === '' || lineIdx === '__new__' || lineIdx === null || lineIdx === undefined) return;

	var idx = parseInt(lineIdx);
	var line = scheduleLines.find(function(l) { return l.idx === idx; });
	if (!line) return;

	// Show preview if line has existing data
	var hasData = (
		line.configured_fixture ||
		line.configured_tape_neon ||
		line.manufacturer_name ||
		line.fixture_model_number ||
		(line.manufacturer_type === 'ILLUMENATE' && line.fixture_template) ||
		(line.manufacturer_type === 'ILLUMENATE' && line.tape_neon_template)
	);

	if (hasData) {
		$('#linePreviewText').text(line.summary);
		$('#linePreview').show();
	}
}

function updateSaveButtonVisibility() {
	if (context.saveHandler && !isTapeNeon) {
		$('#saveBtn').show().prop('disabled', !(currentResult && currentResult.is_valid));
		return;
	}
	var hasSchedule = !!$('#scheduleSelect').val();
	var hasLine = !!$('#lineSelect').val();

	if (isTapeNeon) {
		// Tape/Neon uses separate save button
		if (typeof tnUpdateSaveButtonVisibility === 'function') {
			tnUpdateSaveButtonVisibility();
		}
		return;
	}

	if (hasSchedule && hasLine && canSaveToSchedule) {
		$('#saveBtn').show();
		// Only enable if we have a valid calculation result
		if (currentResult && currentResult.is_valid) {
			$('#saveBtn').prop('disabled', false);
		} else {
			$('#saveBtn').prop('disabled', true);
		}
	} else {
		$('#saveBtn').hide();
	}

	// Show/enable Build Item button for System Managers when config is valid
	if (isSystemManager) {
		if (currentResult && currentResult.is_valid) {
			$('#buildItemBtn').show().prop('disabled', false);
		} else {
			$('#buildItemBtn').show().prop('disabled', true);
		}
	}
}

// =====================================================================
// DOM Ready
// =====================================================================

$(function() {

	// Visual template card picker (shared with the Guided Wizard / desk dialog).
	// Drives the hidden select so every existing change handler keeps working.
	if (window.IllConfigurator && IllConfigurator.renderTemplateCards) {
		IllConfigurator.renderTemplateCards({
			$container: $('#templatePicker'),
			$select: $('select[name="fixture_template_code"]')
		});
	}

	// Load projects for the selector
	if (!context.saveHandler) loadUserProjects();
	else $('#categorySelector').hide();

	// Schedule context selectors
	$('#projectSelect').on('change.' + self.instanceId, function() {
		loadSchedulesForProject($(this).val());
	});

	$('#scheduleSelect').on('change.' + self.instanceId, function() {
		loadScheduleLines($(this).val());
	});

	$('#lineSelect').on('change.' + self.instanceId, function() {
		var val = $(this).val();
		if (val === '__new__') {
			line_idx = null;
			$('#linePreview').hide();
		} else if (val) {
			line_idx = parseInt(val);
			showLinePreview(val);
		} else {
			line_idx = null;
			$('#linePreview').hide();
		}
		updateSaveButtonVisibility();
	});
	
	// Load template options when template is selected (Linear Fixture only)
	if (!isTapeNeon) {
	$('select[name="fixture_template_code"]').on('change.' + self.instanceId, function() {
		var template = $(this).val();

		// Show/hide product image gallery
		var $selected = $(this).find('option:selected');
		var gallery = $selected.data('gallery') || [];
		initProductGallery(gallery, $selected.text().trim());

		if (template) {
			loadTemplateOptions(template, function(success) {
				if (success) {
					$('#templateOptions').show();
					$('#segmentsCard').show();
					$('#powerSupplySection').show();
					$('#actionButtons').show();
					// Initialize first segment if none exist
					if (segmentCount === 0) {
						addSegment(true);
					}
				}
			});
		} else {
			$('#templateOptions').hide();
			$('#segmentsCard').hide();
			$('#powerSupplySection').hide();
			$('#actionButtons').hide();
		}
	});

	// Cascading option change handlers
	$('select[name="led_package_code"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		// Re-detect multi-CCT based on selected LED package
		var selectedPkg = $(this).val();
		if (templateOptions && templateOptions.led_packages) {
			isMultiCCT = false;
			templateOptions.led_packages.forEach(function(pkg) {
				if (pkg.value === selectedPkg && pkg.spectrum_type && MULTI_CCT_SPECTRUM_TYPES.indexOf(pkg.spectrum_type) !== -1) {
					isMultiCCT = true;
				}
			});
		}
		updateCCTOptions();
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="environment_rating_code"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		updateCCTOptions();
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="cct_code"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="lens_appearance_code"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="delivered_output_value"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		autoSelectTape();
		updateUI();
	});

	$('select[name="mounting_method_code"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		updateUI();
	});

	$('select[name="finish_code"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		// Auto-resolve endcap color from finish
		autoResolveEndcapColor();
		updateUI();
	});
}
});

function autoResolveEndcapColor() {
	var finishCode = $('select[name="finish_code"]').val() || $('.pill-selector[data-field="finish_code"] .pill-option.active input').val();
	if (!finishCode || !templateOptions || !templateOptions.finish_endcap_color_map) {
		$('[name="endcap_color_code"]').val('');
		$('#endcapColorDisplay').hide();
		return;
	}

	var mapping = templateOptions.finish_endcap_color_map[finishCode];
	if (mapping) {
		$('[name="endcap_color_code"]').val(mapping.endcap_color_code);
		$('#endcapColorLabel').text('Endcap Color: ' + mapping.endcap_color_label);
		$('#endcapColorDisplay').show();
	} else {
		// Fallback: if no mapping, use the first endcap color
		if (templateOptions.endcap_colors && templateOptions.endcap_colors.length > 0) {
			$('[name="endcap_color_code"]').val(templateOptions.endcap_colors[0].value);
			$('#endcapColorLabel').text('Endcap Color: ' + templateOptions.endcap_colors[0].label + ' (default)');
			$('#endcapColorDisplay').show();
		} else {
			$('[name="endcap_color_code"]').val('');
			$('#endcapColorDisplay').hide();
		}
	}
}

function loadTemplateOptions(template_code, onComplete) {
	self.loadPowerOptions('ilL-Fixture-Template', template_code);
	// Show loading indicator
	$('#templateOptions .pill-selector').each(function() {
		$(this).html('<span class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading...</span>');
	});
	$('#templateOptions').show();

	// Use the cascading options API
	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.get_cascading_options_for_template',
		args: { fixture_template_code: template_code },
		callback: function(r) {
			if (r.message && r.message.success) {
				templateOptions = r.message.options;
				populateOptions(r.message.options);
				// Populate power feed options in existing segments
				$('.segment-card').each(function() {
					populateSegmentPowerFeedOptions($(this));
				});
				if (typeof onComplete === 'function') onComplete(true);
				restoreCoordinator();
			} else if (r.message && r.message.error) {
				console.error('API error:', r.message.error);
				frappe.msgprint({
					title: __('Error Loading Options'),
					message: r.message.error,
					indicator: 'red'
				});
				if (typeof onComplete === 'function') onComplete(false);
			} else {
				console.error('Unexpected response:', r);
				frappe.msgprint({
					title: __('Error Loading Options'),
					message: __('Unexpected response from server. Please try again.'),
					indicator: 'red'
				});
				if (typeof onComplete === 'function') onComplete(false);
			}
		},
		error: function(r) {
			console.error('API call failed:', r);
			frappe.msgprint({
				title: __('Error Loading Options'),
				message: __('Failed to load configuration options. Please refresh the page and try again.'),
				indicator: 'red'
			});
			if (typeof onComplete === 'function') onComplete(false);
		}
	});
}

function updateCCTOptions() {
	var template_code = $('select[name="fixture_template_code"]').val();
	var led_package = $('select[name="led_package_code"]').val();
	var environment = $('select[name="environment_rating_code"]').val();


	if (!template_code) return;

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.get_ccts_for_template',
		args: {
			fixture_template_code: template_code,
			led_package_code: led_package || null,
			environment_rating_code: environment || null
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				var ccts = r.message.ccts || [];
				var apiIsMultiCCT = r.message.is_multi_cct || false;
				if (ccts.length > 0) {
					populatePillSelector('cct_code', ccts);
				} else if (apiIsMultiCCT) {
					// Multi-CCT package but no compatible_ccts defined on the LED Package.
					// Clear stale static-white CCTs rather than keeping wrong options.
					console.warn('updateCCTOptions: multi-CCT package has no compatible CCTs defined. '
						+ 'Please add compatible CCTs to the LED Package document.');
					populatePillSelector('cct_code', []);
				} else {
				}
				// Re-evaluate button state after async re-population
				updateUI();
			} else {
			}
		},
		error: function(r) {
			console.error('updateCCTOptions API call failed:', r);
		}
	});
}

function updateDeliveredOutputs() {
	var template_code = $('select[name="fixture_template_code"]').val();
	var led_package = $('select[name="led_package_code"]').val();
	var environment = $('select[name="environment_rating_code"]').val();
	var cct = $('select[name="cct_code"]').val();
	var lens = $('select[name="lens_appearance_code"]').val();

	console.log('updateDeliveredOutputs called with:', {
		template_code: template_code,
		led_package: led_package,
		environment: environment,
		cct: cct,
		lens: lens,
		isMultiCCT: isMultiCCT
	});

	// For multi-CCT packages (Tunable White, etc.), CCT is not required to show outputs
	// because the tape offering output is the same regardless of selected CCT.
	var cctRequired = !isMultiCCT;

	// Only fetch outputs when all required fields are selected
	if (!template_code || !led_package || !environment || !lens || (cctRequired && !cct)) {
		$('#outputGroup').hide();
		$('input[name="tape_offering_id"]').val('');
		return;
	}
	
	// For multi-CCT packages, pass cct as null if not selected (API handles this)
	var cctArg = cct || null;

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.get_delivered_outputs_for_template',
		args: {
			fixture_template_code: template_code,
			led_package_code: led_package,
			environment_rating_code: environment,
			cct_code: cctArg,
			lens_appearance_code: lens
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				$('#outputGroup').show();
				populatePillSelector('delivered_output_value', r.message.delivered_outputs);
				
				// Show helpful text about lens transmission
				var transmission = r.message.lens_transmission_pct || 100;
				$('#outputHelpText').text('Output adjusted for ' + transmission.toFixed(0) + '% lens transmission');
			} else {
				$('#outputGroup').hide();
			}
			// Re-evaluate button state after async re-population
			updateUI();
		}
	});
}

function autoSelectTape() {
	var template_code = $('select[name="fixture_template_code"]').val();
	var led_package = $('select[name="led_package_code"]').val();
	var environment = $('select[name="environment_rating_code"]').val();
	var cct = $('select[name="cct_code"]').val();
	var lens = $('select[name="lens_appearance_code"]').val();
	var output = $('select[name="delivered_output_value"]').val();
	
	var cctRequired = !isMultiCCT;
	if (!template_code || !led_package || !environment || !lens || !output || (cctRequired && !cct)) {
		$('input[name="tape_offering_id"]').val('');
		return;
	}
	
	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.auto_select_tape_for_configuration',
		args: {
			fixture_template_code: template_code,
			led_package_code: led_package,
			environment_rating_code: environment,
			cct_code: cct || null,
			lens_appearance_code: lens,
			delivered_output_value: parseInt(output)
		},
		callback: function(r) {
			if (r.message && r.message.success && r.message.tape_offering_id) {
				$('input[name="tape_offering_id"]').val(r.message.tape_offering_id);
			} else {
				$('input[name="tape_offering_id"]').val('');
				if (r.message && r.message.error) {
					frappe.msgprint({
						title: __('Tape Selection'),
						message: r.message.error,
						indicator: 'orange'
					});
				}
			}
		}
	});
}

function populatePillSelector(fieldName, options) {
	var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
	var selectFallback = $('select[name="' + fieldName + '"]');
	
	// Preserve the previously selected value so async re-population doesn't clobber it
	var previousValue = selectFallback.val();
	
	// Clear existing
	pillContainer.empty();
	selectFallback.empty().append('<option value="">Select...</option>');
	
	var restoredPrevious = false;
	if (options && options.length > 0) {
		options.forEach(function(opt) {
			var label = opt.label || opt.value;
			// Add pill button
			var pill = $('<label class="pill-option">' +
				'<input type="radio" name="' + fieldName + '_pill" value="' + opt.value + '">' +
				label +
			'</label>');
			pill.on('click.' + self.instanceId, function() {
				// Update pill selection
				pillContainer.find('.pill-option').removeClass('active');
				$(this).addClass('active');
				// Sync to select and trigger change
				selectFallback.val(opt.value).trigger('change');
			});
			// Restore previously selected value if it still exists
			if (previousValue && String(opt.value) === String(previousValue)) {
				pill.addClass('active');
				restoredPrevious = true;
			}
			pillContainer.append(pill);
			
			// Add to fallback select
			selectFallback.append('<option value="' + opt.value + '">' + label + '</option>');
		});
		
		// Restore the select value (without triggering change to avoid cascading loops)
		if (restoredPrevious) {
			selectFallback.val(previousValue);
		} else if (options.length === 1) {
			// Auto-select if there's only one option
			selectFallback.val(options[0].value).trigger('change');
			pillContainer.find('.pill-option').first().addClass('active');
		}
	}
}

function populateOptions(options) {
	isPopulating = true;  // Suppress cascading change events during population
	
	// Map API response keys to form field names
	var pillFields = {
		'led_packages': 'led_package_code',
		'environment_ratings': 'environment_rating_code',
		'ccts': 'cct_code',
		'lens_appearances': 'lens_appearance_code',
		'mountings': 'mounting_method_code',
		'finishes': 'finish_code'
	};
	
	// Populate pill selectors and their fallback selects
	Object.keys(pillFields).forEach(function(optionKey) {
		var fieldName = pillFields[optionKey];
		var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
		var selectFallback = $('select[name="' + fieldName + '"]');
		
		
		// Clear existing
		pillContainer.empty();
		selectFallback.empty().append('<option value="">Select...</option>');
		
		if (options[optionKey] && options[optionKey].length > 0) {
			options[optionKey].forEach(function(opt) {
				// Add pill button
				var pill = $('<label class="pill-option">' +
					'<input type="radio" name="' + fieldName + '_pill" value="' + opt.value + '">' +
					opt.label +
				'</label>');
				pill.on('click.' + self.instanceId, function() {
					// Update pill selection
					pillContainer.find('.pill-option').removeClass('active');
					$(this).addClass('active');
					// Sync to hidden select
					selectFallback.val(opt.value).trigger('change');
				});
				pillContainer.append(pill);
				
				// Add to fallback select
				selectFallback.append('<option value="' + opt.value + '">' + opt.label + '</option>');
			});
		} else {
		}
	});
	
	// When select changes (mobile), sync to pills
	Object.values(pillFields).forEach(function(fieldName) {
		$('select[name="' + fieldName + '"]').off('change.pillSync.' + self.instanceId).on('change.pillSync.' + self.instanceId, function() {
			var value = $(this).val();
			var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
			pillContainer.find('.pill-option').removeClass('active');
			pillContainer.find('input[value="' + value + '"]').closest('.pill-option').addClass('active');
		});
	});

	// Endcap color is now auto-resolved from finish via ilL-Rel-Finish Endcap Color
	// No pill selector needed — hidden field is set by autoResolveEndcapColor()

	// Hide output group initially - will be shown when all cascading selections are made
	$('#outputGroup').hide();
	
	// Clear auto-selected tape offering
	$('input[name="tape_offering_id"]').val('');

	// Detect multi-CCT LED package (Tunable White, Dim to Warm, etc.)
	// For multi-CCT packages, outputs can be shown without explicit CCT selection.
	isMultiCCT = false;
	if (options.led_packages && options.led_packages.length > 0) {
		// Check if any (or the only) LED package is multi-CCT
		options.led_packages.forEach(function(pkg) {
			if (pkg.spectrum_type && MULTI_CCT_SPECTRUM_TYPES.indexOf(pkg.spectrum_type) !== -1) {
				isMultiCCT = true;
			}
		});
	}

	// Auto-select single-option fields and trigger cascading
	isPopulating = false;  // Re-enable cascading before auto-selection
	
	var cascadingFields = ['led_packages', 'environment_ratings', 'ccts', 'lens_appearances', 'mountings', 'finishes'];
	cascadingFields.forEach(function(optionKey) {
		var fieldName = pillFields[optionKey];
		if (options[optionKey] && options[optionKey].length === 1) {
			var onlyValue = options[optionKey][0].value;
			var selectFallback = $('select[name="' + fieldName + '"]');
			var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
			selectFallback.val(onlyValue).trigger('change');
			pillContainer.find('.pill-option').first().addClass('active');
		}
	});

	// Auto-resolve endcap color from finish (after finish may have been auto-selected above)
	autoResolveEndcapColor();
}

function populateSegmentPowerFeedOptions(segmentCard) {
	if (!templateOptions || !templateOptions.power_feed_type) return;
	
	['start_power_feed_type', 'end_power_feed_type'].forEach(function(fieldName) {
		var select = segmentCard.find('[name="' + fieldName + '"]');
		select.empty().append('<option value="">Select...</option>');
		templateOptions.power_feed_type.forEach(function(opt) {
			select.append('<option value="' + opt.value + '">' + opt.label + '</option>');
		});
	});

	// Populate feed direction dropdowns
	var feedDirs = (templateOptions.feed_directions && templateOptions.feed_directions.length > 0)
		? templateOptions.feed_directions
		: [
			{value: 'End', label: 'End'},
			{value: 'Back', label: 'Back'},
			{value: 'Left', label: 'Left'},
			{value: 'Right', label: 'Right'}
		];
	['start_feed_direction', 'end_feed_direction'].forEach(function(fieldName) {
		var select = segmentCard.find('[name="' + fieldName + '"]');
		select.empty().append('<option value="">Select...</option>');
		feedDirs.forEach(function(opt) {
			select.append('<option value="' + opt.value + '">' + opt.label + '</option>');
		});
	});
}

function addSegment(isFirst) {
	segmentCount++;
	var template = $('#' + 'segmentTemplate')[0];
	var clone = template.content.cloneNode(true);
	var card = clone.querySelector('.segment-card');
	
	card.dataset.segmentIndex = segmentCount;
	card.querySelector('.segment-number').textContent = segmentCount;
	
	if (isFirst) {
		// First segment: show power feed type and leader cable selection
		card.querySelector('.first-segment-start').style.display = 'block';
		card.querySelector('.inherited-start').style.display = 'none';
	} else {
		// Subsequent segments: show inherited from prior
		card.querySelector('.first-segment-start').style.display = 'none';
		card.querySelector('.inherited-start').style.display = 'block';
		// Can be removed
		card.querySelector('.remove-segment-btn').style.display = 'inline-block';
		
		// Copy feed direction, power feed and jumper length from prior segment's end
		var priorSegment = $('#segmentsList .segment-card').last();
		if (priorSegment.length) {
			var priorEndFeedDir = priorSegment.find('[name="end_feed_direction"]').val();
			var priorEndPFT = priorSegment.find('[name="end_power_feed_type"]').val();
			var priorJumperLenIn = priorSegment.find('[name="end_jumper_cable_length_in"]').val();
			// Convert inches to mm for storage in data attribute
			var priorJumperLenMm = Math.round((parseFloat(priorJumperLenIn) || 12) * MM_PER_INCH);
			
			// Store inherited values as data attributes (in mm for backend)
			card.dataset.inheritedFeedDirection = priorEndFeedDir || '';
			card.dataset.inheritedPowerFeedType = priorEndPFT || '';
			card.dataset.inheritedCableLength = priorJumperLenMm;
			
			// Update inherited text (display in inches)
			var inheritedText = 'From prior segment: ' + (priorEndFeedDir ? priorEndFeedDir + ' ' : '') + (priorEndPFT || 'N/A') + ', ' + (priorJumperLenIn || '12') + '" jumper';
			card.querySelector('.inherited-text').textContent = inheritedText;
		}
	}
	
	$('#' + 'segmentsList')[0].appendChild(clone);
	
	var segmentCard = $('#segmentsList .segment-card').last();
	if (templateOptions) {
		populateSegmentPowerFeedOptions(segmentCard);
	}
	
	// Set default end type to Endcap
	setEndType(segmentCard.find('.end-type-btn[data-type="Endcap"]')[0], 'Endcap');
	
	// Setup unit change handler for length conversion
	setupUnitChangeHandler(segmentCard);
	
	updateUI();
}

function removeSegment(btn) {
	var card = $(btn).closest('.segment-card');
	var index = parseInt(card.data('segment-index'));
	
	// Only allow removing if it's not the first segment
	if (index <= 1) {
		frappe.msgprint('Cannot remove the first segment');
		return;
	}
	
	// Remove this segment and all following segments
	var segmentsToRemove = [];
	$('.segment-card').each(function() {
		if (parseInt($(this).data('segment-index')) >= index) {
			segmentsToRemove.push($(this));
		}
	});
	
	segmentsToRemove.forEach(function(s) {
		s.remove();
		segmentCount--;
	});
	
	// Update the prior segment's end type to Endcap
	var lastSegment = $('#segmentsList .segment-card').last();
	if (lastSegment.length) {
		setEndType(lastSegment.find('.end-type-btn[data-type="Endcap"]')[0], 'Endcap');
	}
	
	updateUI();
}

function setEndType(btn, type) {
	var card = $(btn).closest('.segment-card');
	var endTypeInput = card.find('[name="end_type"]');
	
	// Update button states
	card.find('.end-type-btn').removeClass('active btn-primary').addClass('btn-outline-secondary');
	$(btn).removeClass('btn-outline-secondary').addClass('active btn-primary');
	
	endTypeInput.val(type);
	
	if (type === 'Endcap') {
		card.find('.endcap-fields').show();
		card.find('.jumper-fields').hide();
		
		// Remove any segments after this one
		var currentIndex = parseInt(card.data('segment-index'));
		var segmentsToRemove = [];
		$('.segment-card').each(function() {
			if (parseInt($(this).data('segment-index')) > currentIndex) {
				segmentsToRemove.push($(this));
			}
		});
		segmentsToRemove.forEach(function(s) {
			s.remove();
			segmentCount--;
		});
		
		$('#addSegmentHint').hide();
	} else {
		// Jumper
		card.find('.endcap-fields').hide();
		card.find('.jumper-fields').show();
		
		// Auto-add next segment if this is the last one
		var currentIndex = parseInt(card.data('segment-index'));
		var hasNextSegment = false;
		$('.segment-card').each(function() {
			if (parseInt($(this).data('segment-index')) > currentIndex) {
				hasNextSegment = true;
			}
		});
		
		if (!hasNextSegment) {
			// Wait a moment then add the next segment
			self.delay(function() {
				addSegment(false);
			}, 100);
		}
	}
	
	updateUI();
}

function convertSegmentLength(segmentCard, newUnit, oldUnit) {
	var lengthInput = segmentCard.find('[name="requested_length_mm"]');
	var feetInchesRow = segmentCard.find('.feet-inches-row');
	var feetInput = segmentCard.find('[name="length_feet"]');
	var inchesInput = segmentCard.find('[name="length_inches"]');
	
	// First, get current value in mm
	var currentMm = 0;
	if (oldUnit === 'mm') {
		currentMm = parseFloat(lengthInput.val()) || 0;
	} else if (oldUnit === 'in') {
		currentMm = (parseFloat(lengthInput.val()) || 0) * MM_PER_INCH;
	} else if (oldUnit === 'ft_in') {
		var feet = parseFloat(feetInput.val()) || 0;
		var inches = parseFloat(inchesInput.val()) || 0;
		currentMm = (feet * INCHES_PER_FOOT + inches) * MM_PER_INCH;
	}
	
	// Now convert to new unit
	if (newUnit === 'mm') {
		lengthInput.val(Math.round(currentMm));
		lengthInput.closest('.form-group').show();
		feetInchesRow.hide();
	} else if (newUnit === 'in') {
		lengthInput.val((currentMm / MM_PER_INCH).toFixed(2));
		lengthInput.closest('.form-group').show();
		feetInchesRow.hide();
	} else if (newUnit === 'ft_in') {
		// Hide the single input, show feet+inches
		lengthInput.closest('.form-group').hide();
		feetInchesRow.show();
		
		var totalInches = currentMm / MM_PER_INCH;
		var feet = Math.floor(totalInches / INCHES_PER_FOOT);
		var inches = totalInches % INCHES_PER_FOOT;
		feetInput.val(feet);
		inchesInput.val(inches.toFixed(2));
	}
}

function setupUnitChangeHandler(segmentCard) {
	var unitSelect = segmentCard.find('[name="length_unit"]');
	// Store current unit in data attribute for persistence
	unitSelect.data('lastUnit', unitSelect.val());
	
	unitSelect.on('change.' + self.instanceId, function() {
		var newUnit = $(this).val();
		var lastUnit = $(this).data('lastUnit') || 'in';
		convertSegmentLength(segmentCard, newUnit, lastUnit);
		$(this).data('lastUnit', newUnit);
	});
	
	// Initialize feet+inches row visibility
	var currentUnit = unitSelect.val();
	if (currentUnit === 'ft_in') {
		segmentCard.find('[name="requested_length_mm"]').closest('.form-group').hide();
		segmentCard.find('.feet-inches-row').show();
	} else {
		segmentCard.find('.feet-inches-row').hide();
	}
}

function updateUI() {
	// Update segment count badge
	$('#segmentCountBadge').text(segmentCount + ' segment' + (segmentCount !== 1 ? 's' : ''));
	
	// Check if fixture is complete
	var lastSegment = $('#segmentsList .segment-card').last();
	var segmentComplete = lastSegment.length && lastSegment.find('[name="end_type"]').val() === 'Endcap';
	
	// Check if all required cascading fields are selected
	// For multi-CCT packages (Tunable White, etc.), CCT is optional for output calculation
	// Note: endcap_color_code is NOT required here — the backend auto-resolves it from finish
	var cctComplete = isMultiCCT || !!$('[name="cct_code"]').val();
	var cascadingComplete = (
		$('[name="led_package_code"]').val() &&
		$('[name="environment_rating_code"]').val() &&
		cctComplete &&
		$('[name="lens_appearance_code"]').val() &&
		$('[name="delivered_output_value"]').val() &&
		$('[name="mounting_method_code"]').val() &&
		$('[name="finish_code"]').val()
	);
	
	// Enable/disable calculate button based on completeness
	var isComplete = segmentComplete && cascadingComplete;
	$('#calculateBtn').prop('disabled', !isComplete);
	
	// Update segment numbers
	$('.segment-card').each(function(index) {
		$(this).attr('data-segment-index', index + 1);
		$(this).find('.segment-number').text(index + 1);
		
		// Show/hide remove button (can't remove first segment)
		if (index === 0) {
			$(this).find('.remove-segment-btn').hide();
		} else {
			$(this).find('.remove-segment-btn').show();
		}
	});
	
	// Update inherited values display
	$('.segment-card').each(function(index) {
		if (index > 0) {
			var priorSegment = $('.segment-card').eq(index - 1);
			var priorEndFeedDir = priorSegment.find('[name="end_feed_direction"]').val();
			var priorEndPFT = priorSegment.find('[name="end_power_feed_type"]').val();
			var priorJumperLenIn = priorSegment.find('[name="end_jumper_cable_length_in"]').val();
			// Convert inches to mm for storage
			var priorJumperLenMm = Math.round((parseFloat(priorJumperLenIn) || 12) * MM_PER_INCH);
			
			$(this)[0].dataset.inheritedFeedDirection = priorEndFeedDir || '';
			$(this)[0].dataset.inheritedPowerFeedType = priorEndPFT || '';
			$(this)[0].dataset.inheritedCableLength = priorJumperLenMm;
			
			var inheritedText = 'From prior: ' + (priorEndFeedDir ? priorEndFeedDir + ' ' : '') + (priorEndPFT || 'N/A') + ', ' + (priorJumperLenIn || '12') + '"';
			$(this).find('.inherited-text').text(inheritedText);
		}
	});
	
	segmentCount = $('.segment-card').length;
}

function collectSegments() {
	var segments = [];
	$('.segment-card').each(function(index) {
		var card = $(this);
		
		// Get length in mm based on unit
		var length = 0;
		var unit = card.find('[name="length_unit"]').val();
		if (unit === 'mm') {
			length = parseFloat(card.find('[name="requested_length_mm"]').val()) || 0;
		} else if (unit === 'in') {
			length = Math.round((parseFloat(card.find('[name="requested_length_mm"]').val()) || 0) * MM_PER_INCH);
		} else if (unit === 'ft_in') {
			var feet = parseFloat(card.find('[name="length_feet"]').val()) || 0;
			var inches = parseFloat(card.find('[name="length_inches"]').val()) || 0;
			length = Math.round((feet * INCHES_PER_FOOT + inches) * MM_PER_INCH);
		}
		
		var segment = {
			segment_index: index + 1,
			requested_length_mm: length,
			end_type: card.find('[name="end_type"]').val()
		};
		
		if (index === 0) {
			// First segment: get start feed direction, power feed and leader cable
			segment.start_feed_direction = card.find('[name="start_feed_direction"]').val();
			segment.start_power_feed_type = card.find('[name="start_power_feed_type"]').val();
			// Convert inches to mm for backend
			var leaderInches = Number(card.find('[name="start_leader_cable_length_in"]').val());
			segment.start_leader_cable_length_mm = Math.round(leaderInches * MM_PER_INCH);
		} else {
			// Inherited from prior segment
			segment.start_feed_direction = card[0].dataset.inheritedFeedDirection || '';
			segment.start_power_feed_type = card[0].dataset.inheritedPowerFeedType || '';
			segment.start_leader_cable_length_mm = Number(card[0].dataset.inheritedCableLength || 0);
		}
		
		if (segment.end_type === 'Jumper') {
			segment.end_feed_direction = card.find('[name="end_feed_direction"]').val();
			segment.end_power_feed_type = card.find('[name="end_power_feed_type"]').val();
			// Convert inches to mm for backend
			var jumperInches = parseFloat(card.find('[name="end_jumper_cable_length_in"]').val()) || 12;
			segment.end_jumper_cable_length_mm = Math.round(jumperInches * MM_PER_INCH);
		}
		
		segments.push(segment);
	});
	return segments;
}

function validateAndQuote() {
	if (!self.canCalculateRestored()) return;
	var power = powerSelections();
	if (!power) return;
	var form = $('#configuratorForm');
	var segments = collectSegments();
	
	if (segments.length === 0) {
		frappe.msgprint('Please add at least one segment');
		return;
	}
	
	// Check if last segment ends with Endcap
	var lastSegment = segments[segments.length - 1];
	if (lastSegment.end_type !== 'Endcap') {
		frappe.msgprint('The fixture must end with an Endcap. Please select Endcap on the last segment.');
		return;
	}
	
	// Check if tape was auto-selected
	var tapeOfferingId = form.find('[name="tape_offering_id"]').val();
	var deliveredOutputValue = form.find('[name="delivered_output_value"]').val();
	
	// Build request data for the output-based API
	var data = {
		fixture_template_code: form.find('[name="fixture_template_code"]').val(),
		led_package_code: form.find('[name="led_package_code"]').val(),
		environment_rating_code: form.find('[name="environment_rating_code"]').val(),
		cct_code: form.find('[name="cct_code"]').val(),
		lens_appearance_code: form.find('[name="lens_appearance_code"]').val(),
		finish_code: form.find('[name="finish_code"]').val(),
		mounting_method_code: form.find('[name="mounting_method_code"]').val(),
		endcap_color_code: form.find('[name="endcap_color_code"]').val(),
		segments_json: JSON.stringify(segments),
		include_power_supply: power.include_power_supply,
		dimming_protocol_code: power.dimming_protocol_code,
		override_max_run_ft: power.override_max_run_ft
	};

	// Optional fixture-wide max run length override
	if ($('#overrideMaxRunCheck').is(':checked')) {
		var overrideMaxRunVal = parseFloat($('#overrideMaxRunInput').val());
		if (!isNaN(overrideMaxRunVal) && overrideMaxRunVal > 0) {
			data.override_max_run_ft = overrideMaxRunVal;
		}
	}
	
	// Show loading state
	$('#calculateBtn').prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> ' + __('Calculating...') + '');
	
	function resetCalculateBtn() {
		$('#calculateBtn').html('<i class="fa fa-calculator"></i> ' + __('Calculate & Validate') + '');
		updateUI();  // Re-evaluate button state
	}
	
	function handleError(r) {
		resetCalculateBtn();
		frappe.msgprint({
			title: __('Calculation Error'),
			message: __('An error occurred while calculating. Please check your selections and try again.'),
			indicator: 'red'
		});
		console.error('validateAndQuote API error:', r);
	}
	
	lastFixtureSelections = Object.assign({}, data, { delivered_output_value: deliveredOutputValue, tape_offering_id: tapeOfferingId });
	// Use the output-based API if we have delivered_output_value, otherwise use tape_offering_id
	if (deliveredOutputValue) {
		data.delivered_output_value = parseInt(deliveredOutputValue);
		coordinatorRequest({
			method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote_multisegment_with_output',
			args: data,
			callback: function(r) {
				resetCalculateBtn();
				if (r.message) {
					currentResult = r.message;
					displayResults(r.message);
				}
			},
			error: handleError
		});
	} else if (tapeOfferingId) {
		// Fallback to old API with tape_offering_id
		data.tape_offering_id = tapeOfferingId;
		coordinatorRequest({
			method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote_multisegment',
			args: data,
			callback: function(r) {
				resetCalculateBtn();
				if (r.message) {
					currentResult = r.message;
					displayResults(r.message);
				}
			},
			error: handleError
		});
	} else {
		resetCalculateBtn();
		frappe.msgprint({
			title: __('Missing Selection'),
			message: __('Please select an Output Level to continue.'),
			indicator: 'orange'
		});
		return;
	}
}

function copyToClipboard(elementId) {
	var text = $('#' + elementId)[0].innerText;
	navigator.clipboard.writeText(text).then(function() {
		frappe.show_alert({message: __('Copied to clipboard'), indicator: 'green'}, 2);
	}).catch(function() {
		// Fallback for older browsers
		var textarea = document.createElement('textarea');
		textarea.value = text;
		document.body.appendChild(textarea);
		textarea.select();
		document.execCommand('copy');
		document.body.removeChild(textarea);
		frappe.show_alert({message: __('Copied to clipboard'), indicator: 'green'}, 2);
	});
}

function copyBothToClipboard() {
	var partNumber = $('#' + 'partNumberValue')[0].innerText;
	var description = $('#' + 'partDescriptionValue')[0].innerText;
	var combined = partNumber + '\n' + description;
	navigator.clipboard.writeText(combined).then(function() {
		frappe.show_alert({message: __('Part number and description copied to clipboard'), indicator: 'green'}, 2);
	}).catch(function() {
		var textarea = document.createElement('textarea');
		textarea.value = combined;
		document.body.appendChild(textarea);
		textarea.select();
		document.execCommand('copy');
		document.body.removeChild(textarea);
		frappe.show_alert({message: __('Part number and description copied to clipboard'), indicator: 'green'}, 2);
	});
}

function displayResults(result) {
	$('#noResults').hide();
	
	// Update validation status
	var statusBadge = $('#validationStatus');
	if (result.is_valid) {
		statusBadge.removeClass('badge-secondary badge-danger').addClass('badge-success').text('Valid');
	} else {
		statusBadge.removeClass('badge-secondary badge-success').addClass('badge-danger').text('Invalid');
	}

	// Update save button based on schedule selection
	updateSaveButtonVisibility();

	// Display part number and description
	if (result.configured_fixture_id || result.candidate_part_number || result.part_number) {
		$('#partNumberPanel').show();
		$('#partNumberValue').text(result.part_number || result.candidate_part_number || result.configured_fixture_id);
		var desc = (result.computed && (result.computed.build_description_display || result.computed.build_description)) || '-';
		$('#partDescriptionValue').text(desc);
	} else {
		$('#partNumberPanel').hide();
	}
	
	// Display messages
	if (result.messages && result.messages.length > 0) {
		$('#messagesPanel').show();
		var messagesList = $('#messagesList').empty();
		result.messages.forEach(function(msg) {
			var alertClass = msg.severity === 'error' ? 'danger' : (msg.severity === 'warning' ? 'warning' : 'info');
			messagesList.append('<div class="alert alert-' + alertClass + ' py-2 mb-1">' + msg.text + '</div>');
		});
	} else {
		$('#messagesPanel').hide();
	}
	
	// Display length results
	if (result.computed) {
		$('#lengthResults').show();
		// Display lengths in inches for US market (with mm in parentheses)
		var requestedIn = result.computed.total_requested_length_in || (result.computed.total_requested_length_mm / MM_PER_INCH).toFixed(1);
		var mfgIn = result.computed.manufacturable_overall_length_in || (result.computed.manufacturable_overall_length_mm / MM_PER_INCH).toFixed(1);
		$('#requestedLength').text(requestedIn + '" (' + result.computed.total_requested_length_mm + ' mm)');
		$('#mfgLength').text(mfgIn + '" (' + result.computed.manufacturable_overall_length_mm + ' mm)');
		$('#segmentCountResult').text(result.computed.user_segment_count);
		
		$('#manufacturingResults').show();
		$('#profileSegmentsCount').text(result.computed.segments_count);
		$('#runsCount').text(result.computed.runs_count);
		$('#endcapsCount').text(result.computed.total_endcaps);
		$('#mountingCount').text(result.computed.total_mounting_accessories);
		$('#totalWatts').text(result.computed.total_watts + ' W');
		$('#assemblyMode').text(result.computed.assembly_mode);

		// Max run length display
		if (result.computed.max_run_ft_effective) {
			$('#maxRunLengthRow').show();
			var maxRunText = result.computed.max_run_ft_effective + ' ft';
			if (result.computed.override_max_run_ft_active) {
				maxRunText += ' (' + __('Overridden') + ')';
			} else if (result.computed.max_run_ft_by_voltage_drop && result.computed.max_run_ft_by_watts) {
				var limiting = (result.computed.max_run_ft_by_voltage_drop <= result.computed.max_run_ft_by_watts) ? 'voltage drop' : 'wattage';
				maxRunText += ' (' + limiting + ')';
			}
			$('#maxRunLength').text(maxRunText);
		} else {
			$('#maxRunLengthRow').hide();
		}
		
		// Display build description (use display version with inches for UI)
		if (result.computed.build_description_display || result.computed.build_description) {
			$('#buildDescriptionPanel').show();
			$('#buildDescription').text(result.computed.build_description_display || result.computed.build_description);
		}
		
		// Display LED run details for complex fixtures
		if (result.computed.runs && result.computed.runs.length > 0) {
			$('#ledRunDetailsPanel').show();
			var runsHtml = '<table class="table table-sm table-bordered mb-0">';
			runsHtml += '<thead class="thead-light"><tr>';
			runsHtml += '<th>' + __('Run') + '</th>';
			runsHtml += '<th>' + __('Segment') + '</th>';
			runsHtml += '<th>' + __('Length') + '</th>';
			runsHtml += '<th>' + __('Watts') + '</th>';
			runsHtml += '</tr></thead><tbody>';
			
			result.computed.runs.forEach(function(run) {
				// Use pre-computed inch value if available, otherwise calculate
				var lengthIn = run.run_len_in || (run.run_len_mm / MM_PER_INCH).toFixed(1);
				var lengthFt = (run.run_len_mm / MM_PER_FOOT).toFixed(2);
				runsHtml += '<tr>';
				runsHtml += '<td class="text-center">' + run.run_index + '</td>';
				runsHtml += '<td class="text-center">' + run.segment_index + '</td>';
				runsHtml += '<td class="text-right">' + lengthIn + '" (' + lengthFt + ' ft)</td>';
				runsHtml += '<td class="text-right">' + run.run_watts.toFixed(1) + ' W</td>';
				runsHtml += '</tr>';
			});
			
			runsHtml += '</tbody></table>';
			$('#ledRunDetails').html(runsHtml);
		} else {
			$('#ledRunDetailsPanel').hide();
		}
	}
	
	// Display driver plan
	if (result.resolved_items && result.resolved_items.driver_plan) {
		var dp = result.resolved_items.driver_plan;
		$('#driverResults').show();
		if (dp.status === 'not_required') {
			$('#driverPlan').html(
				'<div class="alert alert-info py-2 mb-0">' +
				'<i class="fa fa-info-circle mr-2"></i>' +
				__('Power supplies excluded from this configuration.') +
				'</div>'
			);
		} else if (dp.status === 'selected' && dp.drivers && dp.drivers.length > 0) {
			var driverHtml = '<table class="table table-sm">';
			dp.drivers.forEach(function(d) {
				driverHtml += '<tr><td>' + d.item_code + '</td><td>×' + d.qty + '</td></tr>';
			});
			driverHtml += '</table>';
			$('#driverPlan').html(driverHtml);
		} else {
			$('#driverPlan').html('<span class="text-muted">' + dp.status + '</span>');
		}
	}
	
	// Display pricing
	if (result.pricing) {
		$('#pricingResults').show();
		var tbody = $('#priceBreakdownBody').empty();

		if (result.pricing.item_pricing && result.pricing.item_pricing.length > 0) {
			result.pricing.item_pricing.forEach(function(item) {
				if (!item.item_code) return;
				var tierDisplay = '$' + item.tier_unit.toFixed(2);
				if (item.discount_amount > 0) {
					tierDisplay += ' <small class="text-success">(-$' + item.discount_amount.toFixed(2) + ')</small>';
				}
				tbody.append(
					'<tr>' +
					'<td>' + (item.item_code || '-') + '</td>' +
					'<td class="text-right"><strong>$' + item.msrp_unit.toFixed(2) + '</strong></td>' +
					'<td class="text-right">' + tierDisplay + '</td>' +
					'</tr>'
				);
			});
		} else {
			// Fallback: show totals if no item_pricing
			tbody.append(
				'<tr>' +
				'<td>Total</td>' +
				'<td class="text-right"><strong>$' + result.pricing.msrp_unit.toFixed(2) + '</strong></td>' +
				'<td class="text-right">$' + result.pricing.tier_unit.toFixed(2) + '</td>' +
				'</tr>'
			);
		}

		if (result.pricing.adder_breakdown && result.pricing.adder_breakdown.length > 0) {
			var breakdownHtml = '<details><summary class="text-muted">Fixture Price Breakdown</summary><table class="table table-sm mt-2">';
			result.pricing.adder_breakdown.forEach(function(adder) {
				breakdownHtml += '<tr><td>' + adder.component + '</td><td class="text-right">$' + adder.amount.toFixed(2) + '</td></tr>';
			});
			breakdownHtml += '</table></details>';
			$('#adderBreakdown').html(breakdownHtml);
		}
	}
}

function buildConfiguredFixtureAndItem() {
	if (!currentResult || !currentResult.is_valid || !currentResult.configured_fixture_id) {
		frappe.msgprint(__('Cannot build: configuration is not valid or missing fixture ID'));
		return;
	}

	$('#buildItemBtn').prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Building...');

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.build_configured_fixture_and_item',
		args: {
			configured_fixture_id: currentResult.configured_fixture_id
		},
		callback: function(r) {
			$('#buildItemBtn').html('<i class="fa fa-wrench"></i> Build Configured Fixture & Item');
			if (r.message && r.message.success) {
				var msg = r.message.created
					? __('Created Item: {0}', [r.message.item_code])
					: __('Item already exists: {0}', [r.message.item_code]);
				frappe.msgprint({
					title: __('Build Successful'),
					message: msg,
					indicator: 'green'
				});
			} else {
				frappe.msgprint({
					title: __('Build Failed'),
					message: (r.message && r.message.error) || __('An error occurred'),
					indicator: 'red'
				});
			}
			$('#buildItemBtn').prop('disabled', false);
		},
		error: function() {
			$('#buildItemBtn').html('<i class="fa fa-wrench"></i> Build Configured Fixture & Item').prop('disabled', false);
		}
	});
}

function saveToSchedule() {
	if (!currentResult || !currentResult.is_valid) {
		frappe.msgprint('Cannot save: configuration is not valid');
		return;
	}

	if (context.saveHandler) return context.saveHandler({product_type: productCategory,
		selections: lastFixtureSelections, validation: currentResult, instance: self});
	var selectedSchedule = $('#scheduleSelect').val();
	var selectedLine = $('#lineSelect').val();

	if (!selectedSchedule) {
		frappe.msgprint('Please select a schedule to save to');
		return;
	}

	if (!selectedLine) {
		frappe.msgprint('Please select a line or choose "New Line"');
		return;
	}

	var saveLine = (selectedLine === '__new__') ? null : parseInt(selectedLine);

	// Check if we're overriding an existing line
	if (saveLine !== null) {
		var existingLine = scheduleLines.find(function(l) { return l.idx === saveLine; });
		if (existingLine && (existingLine.configured_fixture || existingLine.manufacturer_name || existingLine.fixture_model_number)) {
			// Show override confirmation
			var confirmMsg = '<strong>Warning:</strong> This will override the existing data for line "' +
				existingLine.line_id + '".<br><br>' +
				'<strong>Current data:</strong><br>' +
				'<div class="bg-light p-2 rounded mt-1 mb-2" style="font-size: 0.85rem;">' +
				existingLine.summary.replace(/\|/g, '<br>') +
				'</div>' +
				'Are you sure you want to replace this with the new configuration?';

			frappe.confirm(
				confirmMsg,
				function() {
					// Yes - proceed with save
					doSaveToSchedule(selectedSchedule, saveLine);
				},
				function() {
					// No - cancel
				}
			);
			return;
		}
	}

	doSaveToSchedule(selectedSchedule, saveLine);
}

function doSaveToSchedule(scheduleName, lineIdx) {
    return self.saveScheduleConfiguration({ family: 'Linear Fixture', schedule_name: scheduleName,
        line_idx: lineIdx, selections: lastFixtureSelections });
}

var _gallery = { images: [], index: 0, zoom: 1, panX: 0, panY: 0, dragging: false, startX: 0, startY: 0 };

function initProductGallery(images, altPrefix) {
	_gallery.images = (images && images.length) ? images : [];
	_gallery.index = 0;
	_gallery.zoom = 1;
	_gallery.panX = 0;
	_gallery.panY = 0;
	$('#zoomSlider').val(100);
	$('#zoomValue').text('100%');
	if (_gallery.images.length) {
		showGalleryImage();
		$('#productGalleryContainer').show();
		updateGalleryNav();
	} else {
		$('#productGalleryContainer').hide();
	}
}

function showGalleryImage() {
	var item = _gallery.images[_gallery.index];
	if (!item) return;
	var $img = $('#galleryImage');
	$img.attr('src', item.image).attr('alt', item.alt_text || 'Product image');
	applyTransform();
	$('#galleryCounter').text((_gallery.index + 1) + ' / ' + _gallery.images.length);
	$('#galleryCounter').toggle(_gallery.images.length > 1);
}

function updateGalleryNav() {
	var multi = _gallery.images.length > 1;
	$('#galleryPrev').toggle(multi).toggleClass('disabled', _gallery.index === 0);
	$('#galleryNext').toggle(multi).toggleClass('disabled', _gallery.index >= _gallery.images.length - 1);
}

function applyTransform() {
	var z = _gallery.zoom;
	var tx = _gallery.panX;
	var ty = _gallery.panY;
	$('#galleryImage').css('transform', 'scale(' + z + ') translate(' + tx + 'px, ' + ty + 'px)');
}

function resetZoomPan() {
	_gallery.zoom = 1;
	_gallery.panX = 0;
	_gallery.panY = 0;
	$('#zoomSlider').val(100);
	$('#zoomValue').text('100%');
	applyTransform();
}

// Arrow click handlers
$(document).on('click.' + self.instanceId, self.selector('#galleryPrev'), function() {
	if (_gallery.index > 0) {
		_gallery.index--;
		resetZoomPan();
		showGalleryImage();
		updateGalleryNav();
	}
});
$(document).on('click.' + self.instanceId, self.selector('#galleryNext'), function() {
	if (_gallery.index < _gallery.images.length - 1) {
		_gallery.index++;
		resetZoomPan();
		showGalleryImage();
		updateGalleryNav();
	}
});

// Zoom slider
$(document).on('input.' + self.instanceId, self.selector('#zoomSlider'), function() {
	var val = parseInt($(this).val(), 10);
	_gallery.zoom = val / 100;
	// Reset pan when zooming back to 1x
	if (_gallery.zoom <= 1) { _gallery.panX = 0; _gallery.panY = 0; }
	$('#zoomValue').text(val + '%');
	applyTransform();
});
$(document).on('click.' + self.instanceId, self.selector('#zoomReset'), function() {
	resetZoomPan();
});

// Pan (mouse drag)
(function() {
	var vp = $('#' + 'galleryViewport')[0];
	if (!vp) return;

	function onPointerDown(e) {
		if (_gallery.zoom <= 1) return;
		_gallery.dragging = true;
		_gallery.startX = (e.touches ? e.touches[0].clientX : e.clientX) - _gallery.panX;
		_gallery.startY = (e.touches ? e.touches[0].clientY : e.clientY) - _gallery.panY;
		$(vp).addClass('is-dragging');
		e.preventDefault();
	}
	function onPointerMove(e) {
		if (!_gallery.dragging) return;
		var cx = e.touches ? e.touches[0].clientX : e.clientX;
		var cy = e.touches ? e.touches[0].clientY : e.clientY;
		_gallery.panX = cx - _gallery.startX;
		_gallery.panY = cy - _gallery.startY;
		applyTransform();
		e.preventDefault();
	}
	function onPointerUp() {
		_gallery.dragging = false;
		$(vp).removeClass('is-dragging');
	}

	self.listen(vp, 'mousedown', onPointerDown);
	self.listen(vp, 'touchstart', onPointerDown, { passive: false });
	self.listen(document, 'mousemove', onPointerMove);
	self.listen(document, 'touchmove', onPointerMove, { passive: false });
	self.listen(document, 'mouseup', onPointerUp);
	self.listen(document, 'touchend', onPointerUp);
})();

// Keyboard navigation for gallery
$(document).on('keydown.' + self.instanceId, function(e) {
	if (!$('#productGalleryContainer').is(':visible')) return;
	// Only handle if not focused on an input
	if ($(e.target).is('input, select, textarea')) return;
	if (e.key === 'ArrowLeft') { $('#galleryPrev').click(); }
	if (e.key === 'ArrowRight') { $('#galleryNext').click(); }
});

// Load template options if pre-selected
if (context.selected_template) {
$(function() {
	// Show product gallery if available for pre-selected template
	var $selected = $('select[name="fixture_template_code"] option:selected');
	var gallery = $selected.data('gallery') || [];
	initProductGallery(gallery, $selected.text().trim());
	if (!isTapeNeon) {
	loadTemplateOptions(context.selected_template, function(success) {
		if (success) {
			$('#templateOptions').show();
			$('#segmentsCard').show();
			$('#powerSupplySection').show();
			$('#actionButtons').show();
			if (segmentCount === 0) {
				addSegment(true);
			}
		}
	});
	} else {
	tnLoadTemplateOptions(context.selected_template, function(success) {
		if (success) {
			$('#templateOptions').show();
			if (isTape) {
			$('#tapeLengthCard').show();
			$('#tapeModeToggleCard').show();
			if (tapeSegmentCount === 0) {
				addTapeSegment(true);
			}
			}
			if (isNeon) {
			$('#neonSegmentsCard').show();
			if (neonSegmentCount === 0) {
				addNeonSegment(true);
			}
			}
			$('#tnActionButtons').show();
		}
	});
	}
});
}


// ═════════════════════════════════════════════════════════════════════
// CATEGORY SWITCHING
// ═════════════════════════════════════════════════════════════════════

function switchCategory(category) {
	if (category === productCategory) return;

	// Build new URL preserving schedule context params
	var url = new URL(window.location.href);
	url.searchParams.set('category', category);
	// Remove template param when switching categories (templates differ)
	url.searchParams.delete('template');
	window.location.href = url.toString();
}

// Bind category pill clicks via event delegation (robust, no inline onclick)
$(document).on('click.' + self.instanceId, self.selector('#categorySelector .pill-option[data-category]'), function(e) {
	e.preventDefault();
	e.stopPropagation();
	var category = $(this).data('category');
	if (category) {
		switchCategory(category);
	}
});
// Also handle keyboard activation (Enter/Space)
$(document).on('keydown.' + self.instanceId, self.selector('#categorySelector .pill-option[data-category]'), function(e) {
	if (e.key === 'Enter' || e.key === ' ') {
		e.preventDefault();
		var category = $(this).data('category');
		if (category) {
			switchCategory(category);
		}
	}
});

// ═════════════════════════════════════════════════════════════════════
// LED TAPE & LED NEON CONFIGURATOR (template-aware + spec-fallback)
// ═════════════════════════════════════════════════════════════════════

// ═════════════════════════════════════════════════════════════════════
// LED TAPE RUN / SEGMENT MANAGEMENT (jumper chaining)
// ═════════════════════════════════════════════════════════════════════

function tnPopulateTapeSegmentOptions(segmentCard) {
	var opts = (tnTemplateOptions && tnTemplateOptions.options) || {};

	// feed_directions = directional options (End, Back).
	var feedDirs = opts.feed_directions || [{value: 'End', label: DEFAULT_FEED_DIRECTION}];
	var startDirs = opts.start_feed_directions || feedDirs;
	var endDirs = opts.end_feed_directions || feedDirs;

	var startSelect = segmentCard.find('[name="tape_start_feed_direction"]');
	if (startSelect.length) {
		var prevStart = startSelect.val();
		startSelect.empty();
		startDirs.forEach(function(opt) {
			startSelect.append('<option value="' + opt.value + '">' + (opt.label || opt.value) + '</option>');
		});
		if (prevStart) { startSelect.val(prevStart); }
	}

	var endSelect = segmentCard.find('[name="tape_end_feed_direction"]');
	if (endSelect.length) {
		var prevEnd = endSelect.val();
		endSelect.empty();
		endDirs.forEach(function(opt) {
			endSelect.append('<option value="' + opt.value + '">' + (opt.label || opt.value) + '</option>');
		});
		if (prevEnd) { endSelect.val(prevEnd); }
	}
}

function addTapeSegment(isFirst) {
	tapeSegmentCount++;
	var template = $('#' + 'tapeSegmentTemplate')[0];
	if (!template) return;
	var clone = template.content.cloneNode(true);
	var card = clone.querySelector('.tape-segment-card');

	card.dataset.segmentIndex = tapeSegmentCount;
	card.querySelector('.tape-segment-number').textContent = tapeSegmentCount;

	if (isFirst) {
		card.querySelector('.tape-first-segment-start').style.display = 'block';
		card.querySelector('.tape-inherited-start').style.display = 'none';
	} else {
		card.querySelector('.tape-first-segment-start').style.display = 'none';
		card.querySelector('.tape-inherited-start').style.display = 'block';
		card.querySelector('.remove-tape-segment-btn').style.display = 'inline-block';

		// Copy inherited info from the prior run's jumper
		var priorSegment = $('#tapeSegmentsList .tape-segment-card').last();
		if (priorSegment.length) {
			var priorEndDir = priorSegment.find('[name="tape_end_feed_direction"]').val() || '';
			var priorJumperIn = priorSegment.find('[name="tape_end_feed_length_inches"]').val() || '12';
			card.dataset.inheritedFeedDirection = priorEndDir;
			card.dataset.inheritedCableLength = priorJumperIn;
			card.querySelector('.tape-inherited-text').textContent =
				'From prior run: ' + priorEndDir + ', ' + priorJumperIn + '" jumper';
		}
	}

	$('#' + 'tapeSegmentsList')[0].appendChild(clone);

	var segmentCard = $('#tapeSegmentsList .tape-segment-card').last();
	tnPopulateTapeSegmentOptions(segmentCard);

	// Default to Endcap
	setTapeEndType(segmentCard.find('.tape-end-type-btn[data-type="Endcap"]')[0], 'Endcap');

	tnUpdateUI();
}

function removeTapeSegment(btn) {
	var card = $(btn).closest('.tape-segment-card');
	var index = parseInt(card.data('segment-index'));
	if (index <= 1) return;

	// Remove this and all following runs
	$('#tapeSegmentsList .tape-segment-card').each(function() {
		if (parseInt($(this).data('segment-index')) >= index) {
			$(this).remove();
			tapeSegmentCount--;
		}
	});

	// Cap off the new last run
	var lastSeg = $('#tapeSegmentsList .tape-segment-card').last();
	if (lastSeg.length) {
		setTapeEndType(lastSeg.find('.tape-end-type-btn[data-type="Endcap"]')[0], 'Endcap');
	}

	tnUpdateUI();
}

function setTapeEndType(btn, type) {
	if (!btn) return;
	var card = $(btn).closest('.tape-segment-card');
	card.find('.tape-end-type-btn').removeClass('active btn-primary').addClass('btn-outline-secondary');
	$(btn).removeClass('btn-outline-secondary').addClass('active btn-primary');
	card.find('[name="tape_end_type"]').val(type);

	var currentIndex = parseInt(card.data('segment-index'));

	if (type === 'Endcap') {
		card.find('.tape-endcap-fields').show();
		card.find('.tape-jumper-fields').hide();

		// Remove subsequent runs
		$('#tapeSegmentsList .tape-segment-card').each(function() {
			if (parseInt($(this).data('segment-index')) > currentIndex) {
				$(this).remove();
				tapeSegmentCount--;
			}
		});
	} else {
		card.find('.tape-endcap-fields').hide();
		card.find('.tape-jumper-fields').show();

		// Auto-add the next run
		var hasNext = false;
		$('#tapeSegmentsList .tape-segment-card').each(function() {
			if (parseInt($(this).data('segment-index')) > currentIndex) hasNext = true;
		});
		if (!hasNext) {
			self.delay(function() { addTapeSegment(false); }, 100);
		}
	}

	tnUpdateUI();
}

function tnCollectTapeSegments() {
	var segments = [];
	$('#tapeSegmentsList .tape-segment-card').each(function(index) {
		var card = $(this);

		var seg = {
			tape_length_unit: card.find('[name="tape_length_unit"]').val() || 'in',
			tape_length_value: parseFloat(card.find('[name="tape_length_value"]').val()) || 0,
			tape_length_feet: parseFloat(card.find('[name="tape_length_feet"]').val()) || 0,
			tape_length_inches: parseFloat(card.find('[name="tape_length_inches"]').val()) || 0,
			end_type: card.find('[name="tape_end_type"]').val() || 'Endcap',
			end_feed_direction: card.find('[name="tape_end_feed_direction"]').val() || '',
			end_feed_length_inches: parseFloat(card.find('[name="tape_end_feed_length_inches"]').val()) || 0,
		};

		if (index === 0) {
			seg.start_feed_direction = card.find('[name="tape_start_feed_direction"]').val() || '';
			seg.start_lead_length_inches = parseFloat(card.find('[name="tape_start_lead_length_inches"]').val()) || 0;
		} else {
			seg.start_feed_direction = card[0].dataset.inheritedFeedDirection || '';
			seg.start_lead_length_inches = parseFloat(card[0].dataset.inheritedCableLength) || 0;
		}

		segments.push(seg);
	});
	return segments;
}

// Keep the Calculate button in sync while the user types run lengths, and
// toggle the feet+inches inputs per run.
$(document).on('change.' + self.instanceId, self.selector('#tapeSegmentsList [name="tape_length_unit"]'), function() {
	var card = $(this).closest('.tape-segment-card');
	if ($(this).val() === 'ft_in') {
		card.find('.tape-ft-in-row').show();
		card.find('[name="tape_length_value"]').closest('.form-group').hide();
	} else {
		card.find('.tape-ft-in-row').hide();
		card.find('[name="tape_length_value"]').closest('.form-group').show();
	}
	tnUpdateUI();
});
$(document).on('input.' + self.instanceId + ' change.' + self.instanceId, self.selector('#tapeSegmentsList input, #tapeSegmentsList select'), function() {
	tnUpdateUI();
});

// ─── Spec-based init (no template needed) ────────────────────────────
function tnLoadSpecOptions() {
	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_tape_neon_spec_init',
		args: { product_category: productCategory },
		callback: function(r) {
			if (r.message && r.message.success) {
				tnTemplateOptions = r.message;
				tnPopulateOptions(r.message.options);
				restoreCoordinator();
			} else if (r.message && r.message.error) {
				console.error('Tape/Neon spec API error:', r.message.error);
				frappe.msgprint({
					title: __('Error Loading Options'),
					message: r.message.error,
					indicator: 'red'
				});
			}
		},
		error: function(r) {
			console.error('Tape/Neon spec API call failed:', r);
		}
	});
}

// ─── Template change handler (tape/neon) ─────────────────────────────
$(function() {
	if (!isTapeNeon) return;
	if (!hasTemplates) {
	// No templates available – load spec-derived options immediately
	tnLoadSpecOptions();
	if (isTape) {
	if (tapeSegmentCount === 0) {
		addTapeSegment(true);
	}
	}
	if (isNeon) {
	if (neonSegmentCount === 0) {
		addNeonSegment(true);
	}
	}
	} else {
	$('select[name="fixture_template_code"]').off('change.' + self.instanceId).on('change.' + self.instanceId, function() {
		var templateCode = $(this).val();

		// Show/hide product image gallery
		var $selected = $(this).find('option:selected');
		var gallery = $selected.data('gallery') || [];
		initProductGallery(gallery, $selected.text().trim());

		if (templateCode) {
			// Show containers with loading state, then populate via async callback
			tnLoadTemplateOptions(templateCode, function(success) {
				if (success) {
					$('#templateOptions').show();
					if (isTape) {
					$('#tapeLengthCard').show();
					$('#tapeModeToggleCard').show();
					if (tapeSegmentCount === 0) {
						addTapeSegment(true);
					}
					}
					if (isNeon) {
					$('#neonSegmentsCard').show();
					if (neonSegmentCount === 0) {
						addNeonSegment(true);
					}
					}
					$('#tnActionButtons').show();
				} else {
				}
			});
		} else {
			$('#templateOptions').hide();
			if (isTape) {
			$('#tapeLengthCard').hide();
			$('#tapeModeToggleCard').hide();
			$('#bulkReelCard').hide();
			if (bulkReelMode) { setTapeMode('custom'); }
			}
			if (isNeon) {
			$('#neonSegmentsCard').hide();
			}
			$('#tnActionButtons').hide();
		}
	});
	}

	// Cascading option change handlers for tape/neon
	$('select[name="tn_environment_rating"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		tnUpdateCascading();
		tnUpdateUI();
	});
	$('select[name="tn_cct"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		tnUpdateCascading();
		tnUpdateUI();
	});
	$('select[name="tn_output_level"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		tnUpdateUI();
	});
	$('select[name="tn_pcb_finish"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		tnUpdateUI();
	});
	$('select[name="tn_finish"]').on('change.' + self.instanceId, function() {
		if (isPopulating) return;
		tnUpdateUI();
	});
});

// ─── Load template options (tape/neon) ───────────────────────────────
function tnLoadTemplateOptions(templateCode, onComplete) {
	self.loadPowerOptions('ilL-Tape-Neon-Template', templateCode);
	// Show loading indicator in the template options area
	$('#templateOptions .pill-selector').each(function() {
		$(this).html('<span class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading...</span>');
	});
	$('#templateOptions').show();

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_tape_neon_template_init',
		args: { template_code: templateCode },
		callback: function(r) {
			if (r.message && r.message.success) {
				tnTemplateOptions = r.message;
				tnPopulateOptions(r.message.options);
				$('#templateOptions').show();
				if (typeof onComplete === 'function') onComplete(true);
				restoreCoordinator();
			} else if (r.message && r.message.error) {
				console.error('Tape/Neon API error:', r.message.error);
				frappe.msgprint({
					title: __('Error Loading Options'),
					message: r.message.error,
					indicator: 'red'
				});
				if (typeof onComplete === 'function') onComplete(false);
			} else {
				console.error('Tape/Neon API unexpected response:', r);
				frappe.msgprint({
					title: __('Error Loading Options'),
					message: __('Unexpected response from server. Please try again.'),
					indicator: 'red'
				});
				if (typeof onComplete === 'function') onComplete(false);
			}
		},
		error: function(r) {
			console.error('Tape/Neon API call failed:', r);
			frappe.msgprint({
				title: __('Error Loading Options'),
				message: __('Failed to load configuration options. Please refresh the page and try again.'),
				indicator: 'red'
			});
			if (typeof onComplete === 'function') onComplete(false);
		}
	});
}

// ─── Populate pill selectors for tape/neon ───────────────────────────
function tnPopulateOptions(options) {
	isPopulating = true;

	// Field mappings: API key → form field name
	var fieldMap = {};
	if (isTape) {
		fieldMap = {
			'environment_ratings': 'tn_environment_rating',
			'ccts': 'tn_cct',
			'output_levels': 'tn_output_level',
			'pcb_finishes': 'tn_pcb_finish',
		};
	} else if (isNeon) {
		fieldMap = {
			'ccts': 'tn_cct',
			'output_levels': 'tn_output_level',
			'finishes': 'tn_finish',
		};
	}

	Object.keys(fieldMap).forEach(function(optionKey) {
		var fieldName = fieldMap[optionKey];
		var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
		var selectFallback = $('select[name="' + fieldName + '"]');

		pillContainer.empty();
		selectFallback.empty().append('<option value="">Select...</option>');

		var opts = options[optionKey] || [];
		if (opts.length > 0) {
			opts.forEach(function(opt) {
				var label = opt.label || opt.value;
				var pill = $('<label class="pill-option">' +
					'<input type="radio" name="' + fieldName + '_pill" value="' + opt.value + '">' +
					label +
				'</label>');
				pill.on('click.' + self.instanceId, function() {
					pillContainer.find('.pill-option').removeClass('active');
					$(this).addClass('active');
					selectFallback.val(opt.value).trigger('change');
				});
				// Mark default
				if (opt.is_default) {
					pill.addClass('active');
				}
				pillContainer.append(pill);
				selectFallback.append('<option value="' + opt.value + '"' + (opt.is_default ? ' selected' : '') + '>' + label + '</option>');
			});
		}

		// Sync select → pill
		selectFallback.off('change.pillSync.' + self.instanceId).on('change.pillSync.' + self.instanceId, function() {
			var value = $(this).val();
			pillContainer.find('.pill-option').removeClass('active');
			pillContainer.find('input[value="' + value + '"]').closest('.pill-option').addClass('active');
		});
	});

	if (isNeon) {
	// Populate IP rating and feed direction options for neon segments
	$('.neon-segment-card').each(function() {
		tnPopulateNeonSegmentOptions($(this));
	});
	}

	if (isTape) {
	// Populate start/end feed direction dropdowns on each tape run card.
	$('#tapeSegmentsList .tape-segment-card').each(function() {
		tnPopulateTapeSegmentOptions($(this));
	});
	}

	isPopulating = false;

	// Auto-select single-option fields
	Object.keys(fieldMap).forEach(function(optionKey) {
		var fieldName = fieldMap[optionKey];
		var opts = options[optionKey] || [];
		if (opts.length === 1) {
			var selectFallback = $('select[name="' + fieldName + '"]');
			selectFallback.val(opts[0].value).trigger('change');
		} else {
			// Auto-select defaults
			opts.forEach(function(opt) {
				if (opt.is_default) {
					$('select[name="' + fieldName + '"]').val(opt.value).trigger('change');
				}
			});
		}
	});
}

// ─── Cascading update for tape/neon ──────────────────────────────────
function tnUpdateCascading() {
	var templateCode = $('select[name="fixture_template_code"]').val();

	var method, args;

	if (templateCode && hasTemplates) {
		// Template-based cascading
		method = 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_tape_neon_template_cascading';
		args = {
			template_code: templateCode,
			environment_rating: $('select[name="tn_environment_rating"]').val() || null,
			cct: $('select[name="tn_cct"]').val() || null,
		};
		if (isTape) {
			args.pcb_mounting = $('select[name="tn_pcb_mounting"]').val() || null;
			args.pcb_finish = $('select[name="tn_pcb_finish"]').val() || null;
		}
		if (isNeon) {
			args.finish = $('select[name="tn_finish"]').val() || null;
		}
	} else {
		// Spec-based cascading (no template)
		method = 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.get_tape_neon_spec_cascading';
		args = {
			product_category: productCategory,
			environment_rating: $('select[name="tn_environment_rating"]').val() || null,
			cct: $('select[name="tn_cct"]').val() || null,
		};
		if (isTape) {
			args.pcb_mounting = $('select[name="tn_pcb_mounting"]').val() || null;
			args.pcb_finish = $('select[name="tn_pcb_finish"]').val() || null;
		}
	}

	coordinatorRequest({
		method: method,
		args: args,
		callback: function(r) {
			if (r.message && r.message.success) {
				// Update CCT and output level pills from cascaded results
				// tnPopulateSinglePillSelector automatically preserves previously selected values
				if (r.message.ccts && r.message.ccts.length > 0) {
					tnPopulateSinglePillSelector('tn_cct', r.message.ccts);
				}
				if (r.message.output_levels && r.message.output_levels.length > 0) {
					tnPopulateSinglePillSelector('tn_output_level', r.message.output_levels);
				}
				tnUpdateUI();
			}
		}
	});
}

function tnPopulateSinglePillSelector(fieldName, opts) {
	var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
	var selectFallback = $('select[name="' + fieldName + '"]');

	// Preserve the previously selected value
	var previousValue = selectFallback.val();

	pillContainer.empty();
	selectFallback.empty().append('<option value="">Select...</option>');

	var restoredPrevious = false;
	opts.forEach(function(opt) {
		var label = opt.label || opt.value;
		var pill = $('<label class="pill-option">' +
			'<input type="radio" name="' + fieldName + '_pill" value="' + opt.value + '">' +
			label +
		'</label>');
		pill.on('click.' + self.instanceId, function() {
			pillContainer.find('.pill-option').removeClass('active');
			$(this).addClass('active');
			selectFallback.val(opt.value).trigger('change');
		});
		// Restore pill active state for previously selected value
		if (previousValue && String(opt.value) === String(previousValue)) {
			pill.addClass('active');
			restoredPrevious = true;
		}
		pillContainer.append(pill);
		selectFallback.append('<option value="' + opt.value + '">' + label + '</option>');
	});

	// Restore select value without triggering change to avoid cascading loops
	if (restoredPrevious) {
		selectFallback.val(previousValue);
	} else if (opts.length === 1) {
		// Auto-select single option
		selectFallback.val(opts[0].value).trigger('change');
		pillContainer.find('.pill-option').first().addClass('active');
	}
}

// ─── UI state update for tape/neon ───────────────────────────────────
function tnUpdateUI() {
	// When bulk reel mode is active, delegate to that flow
	if (bulkReelMode) {
		bulkReelUpdateCalculateBtn();
		bulkReelUpdateSaveBtn();
		return;
	}
	var isComplete = false;

	if (isTape) {
		var lastTapeSeg = $('#tapeSegmentsList .tape-segment-card').last();
		var tapeSegmentsDone = lastTapeSeg.length && lastTapeSeg.find('[name="tape_end_type"]').val() === 'Endcap';
		// Every run needs a positive length
		var allTapeLengthsSet = tapeSegmentCount > 0;
		$('#tapeSegmentsList .tape-segment-card').each(function() {
			var card = $(this);
			var unit = card.find('[name="tape_length_unit"]').val();
			var hasLength = (parseFloat(card.find('[name="tape_length_value"]').val()) > 0) ||
				(unit === 'ft_in' &&
				 (parseFloat(card.find('[name="tape_length_feet"]').val()) > 0 ||
				  parseFloat(card.find('[name="tape_length_inches"]').val()) > 0));
			if (!hasLength) { allTapeLengthsSet = false; }
		});
		var firstTapeSeg = $('#tapeSegmentsList .tape-segment-card').first();
		isComplete = !!(
			$('select[name="tn_cct"]').val() &&
			$('select[name="tn_output_level"]').val() &&
			$('select[name="tn_pcb_finish"]').val() &&
			parseFloat(firstTapeSeg.find('[name="tape_start_lead_length_inches"]').val()) > 0 &&
			allTapeLengthsSet &&
			tapeSegmentsDone
		);
	} else if (isNeon) {
		var lastSeg = $('#neonSegmentsList .neon-segment-card').last();
		var segmentsDone = lastSeg.length && lastSeg.find('[name="neon_end_type"]').val() === 'Endcap';
		// Finish is optional — only require it when options are actually present
		var finishSel = $('select[name="tn_finish"]');
		var finishOk = finishSel.find('option[value!=""]').length === 0 || finishSel.val();
		isComplete = (
			$('select[name="tn_cct"]').val() &&
			$('select[name="tn_output_level"]').val() &&
			finishOk &&
			neonSegmentCount > 0 &&
			segmentsDone
		);
	}

	$('#tnCalculateBtn').prop('disabled', !isComplete);

	// Update save button
	tnUpdateSaveButtonVisibility();

	if (isNeon) {
	// Update neon segment count badge
	$('#neonSegmentCountBadge').text(neonSegmentCount + ' segment' + (neonSegmentCount !== 1 ? 's' : ''));
	}

	if (isTape) {
	// Update tape run count badge
	$('#tapeSegmentCountBadge').text(tapeSegmentCount + ' run' + (tapeSegmentCount !== 1 ? 's' : ''));
	}
}

function tnUpdateSaveButtonVisibility() {
	if (context.saveHandler && !bulkReelMode) {
		$('#tnSaveBtn').show().prop('disabled', !(tnCurrentResult && tnCurrentResult.is_valid));
		return;
	}
	if (bulkReelMode) {
		bulkReelUpdateSaveBtn();
		return;
	}
	var hasSchedule = !!$('#scheduleSelect').val();
	var hasLine = !!$('#lineSelect').val();

	if (hasSchedule && hasLine && canSaveToSchedule) {
		$('#tnSaveBtn').show();
		if (tnCurrentResult && tnCurrentResult.is_valid) {
			$('#tnSaveBtn').prop('disabled', false);
		} else {
			$('#tnSaveBtn').prop('disabled', true);
		}
	} else {
		$('#tnSaveBtn').hide();
	}
}

function tnUpdateBuildButtonVisibility() {
	if (isSystemManager && tnCurrentResult && tnCurrentResult.is_valid && tnCurrentResult.configured_tape_neon) {
		$('#tnBuildItemBtn').show().prop('disabled', false);
	} else {
		$('#tnBuildItemBtn').hide();
	}
}

// ═════════════════════════════════════════════════════════════════════
// BULK REEL MODE (LED Tape only)
// ═════════════════════════════════════════════════════════════════════

function setTapeMode(mode) {
	self.invalidateValidation();
	$('#runsCount').closest('tr').find('td').first().text(mode === 'reel' ? __('Installation circuits') : __('LED Tape Runs'));
	$('#powerSupplySection').toggle(mode !== 'reel');
	bulkReelMode = (mode === 'reel');
	if (bulkReelMode) {
		$('#tapeLengthCard').hide();
		$('#bulkReelCard').show();
		$('#tapeModeCustomBtn').removeClass('btn-primary active').addClass('btn-outline-secondary');
		$('#tapeModeReelBtn').removeClass('btn-outline-secondary').addClass('btn-primary active');
		$('#tapeModeReelHint').show();
		$('#tnActionButtons').hide();
		bulkReelCurrentResult = null;
		bulkReelUpdateCalculateBtn();
		bulkReelUpdateSaveBtn();
	} else {
		$('#bulkReelCard').hide();
		$('#tapeLengthCard').show();
		$('#tapeModeCustomBtn').removeClass('btn-outline-secondary').addClass('btn-primary active');
		$('#tapeModeReelBtn').removeClass('btn-primary active').addClass('btn-outline-secondary');
		$('#tapeModeReelHint').hide();
		$('#tnActionButtons').show();
		tnUpdateUI();
	}
}

function selectBulkReelLength(lengthFt) {
	bulkReelSelectedLength = lengthFt;
	$('#brReelLengthPills .bulk-reel-pill').removeClass('active');
	if (lengthFt === 16.4) { $('#brReel164').addClass('active'); }
	else if (lengthFt === 50) { $('#brReel50').addClass('active'); }
	else if (lengthFt === 100) { $('#brReel100').addClass('active'); }
	$('#brReelLength').val(lengthFt);
	bulkReelCurrentResult = null;
	bulkReelUpdateSaveBtn();
	bulkReelUpdateCalculateBtn();
}

function bulkReelUpdateCalculateBtn() {
	var cct = $('select[name="tn_cct"]').val();
	var output = $('select[name="tn_output_level"]').val();
	var length = bulkReelSelectedLength;
	$('#brCalculateBtn').prop('disabled', !(cct && output && length));
}

function bulkReelUpdateSaveBtn() {
	if (context.saveHandler) {
		$('#brSaveBtn').show().prop('disabled', !(bulkReelCurrentResult && bulkReelCurrentResult.is_valid));
		return;
	}
	var hasSchedule = !!$('#scheduleSelect').val();
	var hasLine = !!$('#lineSelect').val();
	if (hasSchedule && hasLine && canSaveToSchedule && bulkReelCurrentResult && bulkReelCurrentResult.is_valid) {
		$('#brSaveBtn').show().prop('disabled', false);
	} else {
		$('#brSaveBtn').hide();
	}
}

function bulkReelCalculate() {
	if (!self.canCalculateRestored()) return;
	var templateCode = $('select[name="fixture_template_code"]').val();
	if (!templateCode) {
		frappe.msgprint(__('Please select a product family first'));
		return;
	}
	var cct = $('select[name="tn_cct"]').val();
	var output = $('select[name="tn_output_level"]').val();
	var environment = $('select[name="tn_environment_rating"]').val();
	var lengthFt = bulkReelSelectedLength;
	var includePowerSupply = $('#brIncludePowerSupply').prop('checked') ? 1 : 0;

	if (!cct || !output || !lengthFt) {
		frappe.msgprint(__('Please complete all selections: CCT, Output Level, and Reel Length'));
		return;
	}

	var selections = {
		environment_rating: environment || '',
		cct: cct,
		output_level: output,
		ordering_mode: 'BULK_REEL',
		dimming_protocol_code: self.$name('br_dimming_protocol_code').val() || null,
		feed_direction: 'End Feed',
		lead_length_inches: 0,
		tape_length_value: lengthFt,
		tape_length_unit: 'ft',
		include_power_supply: includePowerSupply,
	};
	lastBulkSelections = JSON.parse(JSON.stringify(selections));
	lastBulkTemplate = templateCode;

	$('#brCalculateBtn').html('<i class="fa fa-spinner fa-spin"></i> ' + __('Calculating...') + '');

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.validate_tape_neon_template_config',
		args: {
			template_code: templateCode,
			selections: JSON.stringify(selections),
		},
		btn: $('#brCalculateBtn'),
		callback: function(r) {
			$('#brCalculateBtn').html('<i class="fa fa-calculator"></i> ' + __('Calculate &amp; Validate') + '');
			if (r.message) {
				bulkReelCurrentResult = r.message;
				bulkReelCurrentResult._reel_length_ft = lengthFt;
				bulkReelCurrentResult._include_power_supply = includePowerSupply;
				bulkReelDisplayResults(r.message);
				bulkReelUpdateSaveBtn();
			}
		},
		error: function(r) {
			$('#brCalculateBtn').html('<i class="fa fa-calculator"></i> ' + __('Calculate &amp; Validate') + '');
			frappe.msgprint({ title: __('Calculation Error'), message: __('An error occurred. Please check your selections.'), indicator: 'red' });
		}
	});
}

function bulkReelDisplayResults(result) {
	var statusBadge = $('#validationStatus');
	$('#noResults').hide();

	if (result.is_valid) {
		statusBadge.removeClass('badge-secondary badge-danger').addClass('badge-success').text(__('Valid'));
	} else {
		statusBadge.removeClass('badge-secondary badge-success').addClass('badge-danger').text(__('Invalid'));
		$('#messagesPanel').show();
		$('#messagesList').empty().append(
			$('<div class="alert alert-danger py-2 mb-1"></div>').text(result.error || __('Validation failed'))
		);
		$('#partNumberPanel, #lengthResults, #manufacturingResults, #buildDescriptionPanel, #driverResults, #pricingResults').hide();
		return;
	}

	// Messages (warnings / info)
	if (result.messages && result.messages.length > 0) {
		$('#messagesPanel').show();
		var msgList = $('#messagesList').empty();
		result.messages.forEach(function(msg) {
			var cls = msg.severity === 'error' ? 'danger' : (msg.severity === 'warning' ? 'warning' : 'info');
			msgList.append($('<div></div>').addClass('alert alert-' + cls + ' py-2 mb-1').text(msg.text));
		});
	} else {
		$('#messagesPanel').hide();
	}

	// Part number
	if (result.part_number) {
		$('#partNumberPanel').show();
		$('#partNumberValue').text(result.part_number);
		$('#partDescriptionValue').text(result.build_description || '-');
	} else {
		$('#partNumberPanel').hide();
	}

	// Length + wattage summary
	if (result.computed) {
		var c = result.computed;
		$('#lengthResults').show();
		var reelLabel = bulkReelCurrentResult && bulkReelCurrentResult._reel_length_ft
			? ' [' + bulkReelCurrentResult._reel_length_ft + ' ft reel]' : '';
		$('#requestedLength').text((c.requested_length_in || 0) + '"' + reelLabel);
		$('#mfgLength').text((c.manufacturable_length_in || 0) + '" (' + (c.manufacturable_length_mm || 0) + ' mm)');
		$('#segmentCountResult').text('1');
		$('#manufacturingResults').show();
		$('#runsCount').text(c.runs_count || 1);
		$('#maxRunLengthRow').hide();
		$('#profileSegmentsCount, #endcapsCount, #mountingCount').each(function() { $(this).text('\u2014'); });
		$('#totalWatts').text((c.total_watts || 0) + ' W');
		$('#assemblyMode').text(__('Bulk Reel'));
	}

	// Build description
	if (result.build_description) {
		$('#buildDescriptionPanel').show();
		$('#buildDescription').text(result.build_description);
	}

	var dp = (result.resolved_items || {}).driver_plan;
	$('#driverResults').toggle(!!dp);
	var $plan = $('#driverPlan').empty();
	if (dp && dp.drivers && dp.drivers.length) {
		var $table = $('<table class="table table-sm mb-0"></table>');
		dp.drivers.forEach(function (driver) {
			$('<tr></tr>').append($('<td></td>').text(driver.driver_item),
				$('<td></td>').text('?' + driver.qty)).appendTo($table);
		});
		$plan.append($table);
	} else if (dp) {
		$plan.text(__('Power supplies excluded. Follow the installation circuit requirements.'));
	}
	$('#pricingResults').hide();
}

function bulkReelSave() {
	if (!bulkReelCurrentResult || !bulkReelCurrentResult.is_valid) {
		frappe.msgprint(__('Cannot save: please calculate first to validate the configuration'));
		return;
	}
	if (context.saveHandler) return context.saveHandler({product_type: 'LED Tape',
		selections: lastBulkSelections, tape_neon_template: lastBulkTemplate, validation: bulkReelCurrentResult, instance: self});
	var selectedSchedule = $('#scheduleSelect').val();
	var selectedLine = $('#lineSelect').val();
	if (!selectedSchedule) {
		frappe.msgprint(__('Please select a schedule to save to'));
		return;
	}
	if (!selectedLine) {
		frappe.msgprint(__('Please select a line or choose \u201cNew Line\u201d'));
		return;
	}
	self.saveScheduleConfiguration({
		family: 'LED Tape', schedule_name: selectedSchedule,
		template: lastBulkTemplate, selections: lastBulkSelections
	});
}

// ─── Validate & Quote (tape/neon) ────────────────────────────────────
function tnValidateAndQuote() {
	if (!self.canCalculateRestored()) return;
	var power = powerSelections();
	if (!power) return;
	var templateCode = $('select[name="fixture_template_code"]').val();
	if (!templateCode && hasTemplates) {
		frappe.msgprint('Please select a product family');
		return;
	}

	var selections = {};
	var tapeSegments = null;
	if (isTape) {
		tapeSegments = tnCollectTapeSegments();
		var firstTapeSegment = tapeSegments[0] || {};
		selections = {
			environment_rating: $('select[name="tn_environment_rating"]').val() || '',
			cct: $('select[name="tn_cct"]').val(),
			output_level: $('select[name="tn_output_level"]').val(),
			pcb_finish: $('select[name="tn_pcb_finish"]').val(),
			// Top-level feed mirrors the first run so legacy consumers
			// (configured record fields, pricing) keep working.
			feed_direction: firstTapeSegment.start_feed_direction || DEFAULT_FEED_DIRECTION,
			lead_length_inches: firstTapeSegment.start_lead_length_inches,
		};
	} else if (isNeon) {
		selections = {
			cct: $('select[name="tn_cct"]').val(),
			output_level: $('select[name="tn_output_level"]').val(),
			finish: $('select[name="tn_finish"]').val() || '',
		};
	}

	Object.assign(selections, power);
	var method, args;
	if (templateCode && hasTemplates) {
		method = 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.validate_tape_neon_template_config';
		args = {
			template_code: templateCode,
			selections: JSON.stringify(selections),
		};
	} else if (isTape) {
		method = 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.validate_tape_configuration';
		args = { selections: JSON.stringify(selections) };
	} else {
		method = 'illumenate_lighting.illumenate_lighting.api.tape_neon_configurator.validate_neon_configuration';
		args = {
			selections: JSON.stringify(selections),
			segments_json: JSON.stringify(tnCollectNeonSegments()),
		};
	}

	if (isNeon && templateCode && hasTemplates) {
		args.segments_json = JSON.stringify(tnCollectNeonSegments());
	}
	if (isTape && tapeSegments && tapeSegments.length) {
		args.segments_json = JSON.stringify(tapeSegments);
	}

	if (!templateCode || !hasTemplates) Object.assign(args, power);
	lastTnSelections = selections;
	lastTnSegments = args.segments_json || null;
	lastTnTemplate = templateCode || null;
	// The same power contract reaches both template and direct-spec adapters.
	if (args.segments_json) {
	}

	$('#tnCalculateBtn').prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Calculating...');

	function resetTnCalculateBtn() {
		$('#tnCalculateBtn').html('<i class="fa fa-calculator"></i> Calculate & Validate');
		tnUpdateUI();  // Re-evaluate button state
	}

	coordinatorRequest({
		method: method,
		args: args,
		callback: function(r) {
			resetTnCalculateBtn();
			if (r.message && !r.message.is_valid) {
				if (r.message.missing_fields) {
				}
			}
			if (r.message) {
				tnCurrentResult = r.message;
				tnDisplayResults(r.message);
			}
		},
		error: function(r) {
			resetTnCalculateBtn();
			console.error('[TN Configurator] API call error:', r);
			frappe.msgprint({
				title: __('Calculation Error'),
				message: __('An error occurred while calculating. Please check your selections and try again.'),
				indicator: 'red'
			});
		}
	});
}

// ─── Display results (tape/neon) ─────────────────────────────────────
function tnDisplayResults(result) {
	$('#noResults').hide();

	var statusBadge = $('#validationStatus');
	if (result.is_valid) {
		statusBadge.removeClass('badge-secondary badge-danger').addClass('badge-success').text('Valid');
	} else {
		statusBadge.removeClass('badge-secondary badge-success').addClass('badge-danger').text('Invalid');
	}

	// Show validation error when is_valid is false
	if (!result.is_valid && result.error) {
		$('#messagesPanel').show();
		var messagesList = $('#messagesList').empty();
		messagesList.append(
			'<div class="alert alert-danger py-2 mb-1">' +
			'<i class="fa fa-exclamation-circle mr-1"></i> ' +
			__('Validation failed') + ': ' + result.error +
			'</div>'
		);
		if (result.missing_fields && result.missing_fields.length > 0) {
			messagesList.append(
				'<div class="alert alert-warning py-2 mb-1">' +
				__('Missing fields') + ': ' + result.missing_fields.join(', ') +
				'</div>'
			);
		}
		// Hide result panels since validation failed
		$('#partNumberPanel').hide();
		$('#lengthResults').hide();
		$('#manufacturingResults').hide();
		$('#buildDescriptionPanel').hide();
		$('#pricingResults').hide();
		$('#ledRunDetailsPanel').hide();
		$('#driverResults').hide();
		tnUpdateSaveButtonVisibility();
		tnUpdateBuildButtonVisibility();
		return;
	}

	// Messages (warnings/info from successful validation)
	if (result.messages && result.messages.length > 0) {
		$('#messagesPanel').show();
		var messagesList = $('#messagesList').empty();
		result.messages.forEach(function(msg) {
			var alertClass = msg.severity === 'error' ? 'danger' : (msg.severity === 'warning' ? 'warning' : 'info');
			messagesList.append('<div class="alert alert-' + alertClass + ' py-2 mb-1">' + msg.text + '</div>');
		});
	} else {
		$('#messagesPanel').hide();
	}

	// Part number
	if (result.part_number) {
		$('#partNumberPanel').show();
		$('#partNumberValue').text(result.part_number);
		$('#partDescriptionValue').text(result.build_description || '-');
	} else {
		$('#partNumberPanel').hide();
	}

	// Length results
	if (result.computed) {
		$('#lengthResults').show();
		var c = result.computed;
		if (isNeon) {
			$('#requestedLength').text((c.total_requested_length_in || 0) + '" (' + (c.total_requested_length_mm || 0) + ' mm)');
			$('#mfgLength').text((c.total_manufacturable_length_in || 0) + '" (' + (c.total_manufacturable_length_mm || 0) + ' mm)');
			$('#segmentCountResult').text(c.segment_count || 0);
		} else {
			$('#requestedLength').text((c.requested_length_in || 0) + '" (' + (c.requested_length_mm || 0) + ' mm)');
			$('#mfgLength').text((c.manufacturable_length_in || 0) + '" (' + (c.manufacturable_length_mm || 0) + ' mm)');
			$('#segmentCountResult').text(c.segment_count || 1);
		}

		// Manufacturing summary
		$('#manufacturingResults').show();
		$('#profileSegmentsCount').text('-');
		$('#runsCount').text(c.runs_count || 1);
		$('#endcapsCount').text('-');
		$('#mountingCount').text('-');
		$('#totalWatts').text((c.total_watts || 0) + ' W');
		$('#assemblyMode').text((c.segment_count || 1) > 1 ? 'Multi-Segment' : 'Single');

		// Max run length display
		if (c.max_run_ft_effective) {
			$('#maxRunLengthRow').show();
			var maxRunText = c.max_run_ft_effective + ' ft';
			if (c.max_run_ft_by_voltage_drop && c.max_run_ft_by_watts) {
				var limiting = (c.max_run_ft_by_voltage_drop <= c.max_run_ft_by_watts) ? 'voltage drop' : 'wattage';
				maxRunText += ' (' + limiting + ')';
			}
			$('#maxRunLength').text(maxRunText);
		} else {
			$('#maxRunLengthRow').hide();
		}

		// Build description
		if (result.build_description) {
			$('#buildDescriptionPanel').show();
			$('#buildDescription').text(result.build_description);
		}

		// LED Run Details for tape/neon (when runs > 1)
		if (c.runs && c.runs.length > 1) {
			$('#ledRunDetailsPanel').show();
			var runsHtml = '<table class="table table-sm table-bordered mb-0">';
			runsHtml += '<thead class="thead-light"><tr>';
			runsHtml += '<th>' + __('Run') + '</th>';
			runsHtml += '<th>' + __('Length') + '</th>';
			runsHtml += '<th>' + __('Watts') + '</th>';
			runsHtml += '</tr></thead><tbody>';

			c.runs.forEach(function(run) {
				var lengthIn = (run.run_len_in || (run.run_len_mm / 25.4)).toFixed(2);
				var lengthFt = (run.run_len_ft || (run.run_len_mm / 304.8)).toFixed(2);
				runsHtml += '<tr>';
				runsHtml += '<td class="text-center">' + run.run_index + '</td>';
				runsHtml += '<td class="text-right">' + lengthIn + '" (' + lengthFt + ' ft)</td>';
				runsHtml += '<td class="text-right">' + run.run_watts.toFixed(1) + ' W</td>';
				runsHtml += '</tr>';
			});

			runsHtml += '</tbody></table>';
			$('#ledRunDetails').html(runsHtml);
		} else {
			$('#ledRunDetailsPanel').hide();
		}
		$('#driverResults').hide();
	}

	// Pricing (basic for tape/neon)
	if (tnTemplateOptions && tnTemplateOptions.pricing) {
		var p = tnTemplateOptions.pricing;
		var c = result.computed || {};
		if (p.price_per_ft_msrp && c.manufacturable_length_ft) {
			$('#pricingResults').show();
			var msrp = p.base_price_msrp + (p.price_per_ft_msrp * c.manufacturable_length_ft);
			if (isNeon && p.price_per_segment_msrp && c.segment_count) {
				msrp += p.price_per_segment_msrp * c.segment_count;
			}
			// Sum option adders from template options
			var sel = result.selections || {};
			var opts = (tnTemplateOptions.options || {});
			var adderMappings = isNeon
				? [['ccts', 'cct'], ['output_levels', 'output_level'], ['finishes', 'finish']]
				: [['ccts', 'cct'], ['output_levels', 'output_level'], ['environment_ratings', 'environment_rating'],
				   ['pcb_finishes', 'pcb_finish']];
			adderMappings.forEach(function(pair) {
				var optList = opts[pair[0]] || [];
				var selVal = sel[pair[1]];
				if (selVal) {
					var match = optList.find(function(o) { return o.value === selVal; });
					if (match && match.msrp_adder) { msrp += match.msrp_adder; }
				}
			});
			var tbody = $('#priceBreakdownBody').empty();
			tbody.append(
				'<tr>' +
				'<td>Total</td>' +
				'<td class="text-right"><strong>$' + msrp.toFixed(2) + '</strong></td>' +
				'<td class="text-right">-</td>' +
				'</tr>'
			);
		}
	}

	tnUpdateSaveButtonVisibility();
	tnUpdateBuildButtonVisibility();
}

// ─── Build Configured Item (tape/neon) ───────────────────────────────
function tnBuildConfiguredItem() {
	if (!tnCurrentResult || !tnCurrentResult.is_valid || !tnCurrentResult.configured_tape_neon) {
		frappe.msgprint(__('Cannot build: configuration is not valid or missing configured tape/neon ID'));
		return;
	}

	$('#tnBuildItemBtn').prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Building...');

	coordinatorRequest({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.build_configured_tape_neon_and_item',
		args: {
			configured_tape_neon_id: tnCurrentResult.configured_tape_neon
		},
		callback: function(r) {
			$('#tnBuildItemBtn').html('<i class="fa fa-wrench"></i> Build Configured Item');
			if (r.message && r.message.success) {
				var msg = r.message.created
					? __('Created Item: {0}', [r.message.item_code])
					: __('Item already exists: {0}', [r.message.item_code]);
				frappe.msgprint({
					title: __('Build Successful'),
					message: msg,
					indicator: 'green'
				});
			} else {
				frappe.msgprint({
					title: __('Build Failed'),
					message: (r.message && r.message.error) || __('An error occurred'),
					indicator: 'red'
				});
			}
			$('#tnBuildItemBtn').prop('disabled', false);
		},
		error: function() {
			$('#tnBuildItemBtn').html('<i class="fa fa-wrench"></i> Build Configured Item').prop('disabled', false);
		}
	});
}

// ─── Save to schedule (tape/neon) ────────────────────────────────────
function tnSaveToSchedule() {
    if (!tnCurrentResult || !tnCurrentResult.is_valid) {
        frappe.msgprint(__('Calculate a valid configuration before saving.'));
        return;
    }
    if (context.saveHandler) return context.saveHandler({product_type: productCategory,
        selections: lastTnSelections, segments: lastTnSegments, tape_neon_template: lastTnTemplate, validation: tnCurrentResult, instance: self});
    return self.saveScheduleConfiguration({ family: productCategory,
        selections: lastTnSelections, segments: lastTnSegments, template: lastTnTemplate });
}

function tnPopulateNeonSegmentOptions(segmentCard) {
	if (!tnTemplateOptions || !tnTemplateOptions.options) return;

	var opts = tnTemplateOptions.options;

	// IP ratings
	var ipSelect = segmentCard.find('[name="neon_ip_rating"]');
	ipSelect.empty().append('<option value="">Select...</option>');
	(opts.ip_ratings || []).forEach(function(opt) {
		ipSelect.append('<option value="' + opt.value + '">' + opt.label + '</option>');
	});

	// Feed directions — use separate start/end lists when available
	var defaultDirs = [{value: 'End', label: 'End'}, {value: 'Back', label: 'Back'}];
	var startFeedDirs = opts.start_feed_directions || opts.feed_directions || defaultDirs;
	var endFeedDirs = opts.end_feed_directions || opts.feed_directions || defaultDirs;

	var startSelect = segmentCard.find('[name="neon_start_feed_direction"]');
	startSelect.empty().append('<option value="">Select...</option>');
	startFeedDirs.forEach(function(opt) {
		startSelect.append('<option value="' + opt.value + '">' + opt.label + '</option>');
	});

	var endSelect = segmentCard.find('[name="neon_end_feed_direction"]');
	endSelect.empty().append('<option value="">Select...</option>');
	endFeedDirs.forEach(function(opt) {
		endSelect.append('<option value="' + opt.value + '">' + opt.label + '</option>');
	});

	// Unit change handler for neon segment length
	var unitSelect = segmentCard.find('[name="neon_fixture_length_unit"]');
	unitSelect.on('change.' + self.instanceId, function() {
		var unit = $(this).val();
		if (unit === 'ft_in') {
			segmentCard.find('.neon-ft-in-row').show();
			segmentCard.find('[name="neon_fixture_length_value"]').closest('.form-group').hide();
		} else {
			segmentCard.find('.neon-ft-in-row').hide();
			segmentCard.find('[name="neon_fixture_length_value"]').closest('.form-group').show();
		}
	});
}

function addNeonSegment(isFirst) {
	neonSegmentCount++;
	var template = $('#' + 'neonSegmentTemplate')[0];
	var clone = template.content.cloneNode(true);
	var card = clone.querySelector('.neon-segment-card');

	card.dataset.segmentIndex = neonSegmentCount;
	card.querySelector('.neon-segment-number').textContent = neonSegmentCount;

	if (isFirst) {
		card.querySelector('.neon-first-segment-start').style.display = 'block';
		card.querySelector('.neon-inherited-start').style.display = 'none';
	} else {
		card.querySelector('.neon-first-segment-start').style.display = 'none';
		card.querySelector('.neon-inherited-start').style.display = 'block';
		card.querySelector('.remove-neon-segment-btn').style.display = 'inline-block';

		// Copy inherited info from prior segment's end
		var priorSegment = $('#neonSegmentsList .neon-segment-card').last();
		if (priorSegment.length) {
			var priorEndDir = priorSegment.find('[name="neon_end_feed_direction"]').val() || '';
			var priorJumperIn = priorSegment.find('[name="neon_end_feed_length_inches"]').val() || '12';
			card.dataset.inheritedFeedDirection = priorEndDir;
			card.dataset.inheritedCableLength = priorJumperIn;
			card.querySelector('.neon-inherited-text').textContent = 'From prior: ' + priorEndDir + ', ' + priorJumperIn + '" jumper';
		}
	}

	$('#' + 'neonSegmentsList')[0].appendChild(clone);

	var segmentCard = $('#neonSegmentsList .neon-segment-card').last();
	tnPopulateNeonSegmentOptions(segmentCard);

	// Default to Endcap
	setNeonEndType(segmentCard.find('.neon-end-type-btn[data-type="Endcap"]')[0], 'Endcap');

	tnUpdateUI();
}

function removeNeonSegment(btn) {
	var card = $(btn).closest('.neon-segment-card');
	var index = parseInt(card.data('segment-index'));
	if (index <= 1) return;

	// Remove this and all following segments
	$('.neon-segment-card').each(function() {
		if (parseInt($(this).data('segment-index')) >= index) {
			$(this).remove();
			neonSegmentCount--;
		}
	});

	// Set previous segment end to Endcap
	var lastSeg = $('#neonSegmentsList .neon-segment-card').last();
	if (lastSeg.length) {
		setNeonEndType(lastSeg.find('.neon-end-type-btn[data-type="Endcap"]')[0], 'Endcap');
	}

	tnUpdateUI();
}

function setNeonEndType(btn, type) {
	var card = $(btn).closest('.neon-segment-card');
	card.find('.neon-end-type-btn').removeClass('active btn-primary').addClass('btn-outline-secondary');
	$(btn).removeClass('btn-outline-secondary').addClass('active btn-primary');
	card.find('[name="neon_end_type"]').val(type);

	if (type === 'Endcap') {
		card.find('.endcap-fields').show();
		card.find('.jumper-fields').hide();

		// Remove subsequent segments
		var currentIndex = parseInt(card.data('segment-index'));
		$('.neon-segment-card').each(function() {
			if (parseInt($(this).data('segment-index')) > currentIndex) {
				$(this).remove();
				neonSegmentCount--;
			}
		});
	} else {
		card.find('.endcap-fields').hide();
		card.find('.jumper-fields').show();

		// Auto-add next segment
		var currentIndex = parseInt(card.data('segment-index'));
		var hasNext = false;
		$('.neon-segment-card').each(function() {
			if (parseInt($(this).data('segment-index')) > currentIndex) hasNext = true;
		});
		if (!hasNext) {
			self.delay(function() { addNeonSegment(false); }, 100);
		}
	}

	tnUpdateUI();
}

function tnCollectNeonSegments() {
	var segments = [];
	$('#neonSegmentsList .neon-segment-card').each(function(index) {
		var card = $(this);

		// Parse fixture length
		var unit = card.find('[name="neon_fixture_length_unit"]').val() || 'in';
		var lengthVal = parseFloat(card.find('[name="neon_fixture_length_value"]').val()) || 0;
		var feetVal = parseFloat(card.find('[name="neon_fixture_length_feet"]').val()) || 0;
		var inchesVal = parseFloat(card.find('[name="neon_fixture_length_inches"]').val()) || 0;

		var endType = card.find('[name="neon_end_type"]').val() || 'Endcap';
		var seg = {
			ip_rating: card.find('[name="neon_ip_rating"]').val(),
			fixture_length_unit: unit,
			fixture_length_value: lengthVal,
			fixture_length_feet: feetVal,
			fixture_length_inches: inchesVal,
			end_type: endType,
			end_feed_direction: card.find('[name="neon_end_feed_direction"]').val() || '',
			end_feed_length_inches: parseFloat(card.find('[name="neon_end_feed_length_inches"]').val()) || 0,
		};

		if (index === 0) {
			seg.start_feed_direction = card.find('[name="neon_start_feed_direction"]').val();
			seg.start_lead_length_inches = Number(card.find('[name="neon_start_lead_length_inches"]').val());
		} else {
			seg.start_feed_direction = card[0].dataset.inheritedFeedDirection || 'End';
			seg.start_lead_length_inches = Number(card[0].dataset.inheritedCableLength || 0);
		}

		segments.push(seg);
	});
	return segments;
}

function powerSelections() {
	var override = '';
	if ($('#overrideMaxRunCheck').is(':checked')) {
		override = Number($('#overrideMaxRunInput').val());
		if (!Number.isFinite(override) || override <= 0) {
			frappe.msgprint(__('Enter a finite maximum run length greater than zero.'));
			$('#overrideMaxRunInput').trigger('focus');
			return null;
		}
	}
	return { include_power_supply: $('#includePowerSupply').is(':checked'),
		dimming_protocol_code: self.$name('dimming_protocol_code').val() || null,
		override_max_run_ft: override };
}
}
Coordinator.prototype = Object.create(Base.prototype);
Coordinator.prototype.constructor = Coordinator;
root.IllConfigurator.Coordinator = Coordinator;
})(window);
