// Edit fixture page script (plan 2.2). The page renders its server values as JSON in
// #edit-fixture-context instead of interpolating Jinja into JavaScript. This is a classic
// (non-module) script, so its top-level names stay global as they were in the inline script.
var editFixtureContext = JSON.parse(document.getElementById('edit-fixture-context').textContent || '{}');
function editFixtureText(text) {
	var strings = editFixtureContext.i18n || {};
	return Object.prototype.hasOwnProperty.call(strings, text) ? strings[text] : text;
}
var schedule_name = editFixtureContext.schedule_name;
var line_idx = editFixtureContext.line_idx;
var configured_fixture_id = editFixtureContext.configured_fixture_id;
var currentResult = null;
var templateOptions = null;
var segmentCount = 0;
var MM_PER_INCH = 25.4;
var MM_PER_FOOT = 304.8;
var INCHES_PER_FOOT = 12;

// Pre-loaded fixture configuration
var existingConfig = editFixtureContext.fixture_config;

console.log('Edit Fixture script loaded');
console.log('Existing config:', existingConfig);

// Wrap event handlers in ready to ensure DOM is available
$(function() {
	console.log('DOM ready - attaching event handlers');
	
	// Load template options when template is selected
	$('select[name="fixture_template_code"]').on('change', function() {
		var template = $(this).val();
		console.log('Template changed to:', template);
		if (template) {
			loadTemplateOptions(template, true);
			$('#templateOptions').show();
			$('#segmentsCard').show();
			$('#actionButtons').show();
		} else {
			$('#templateOptions').hide();
			$('#segmentsCard').hide();
			$('#actionButtons').hide();
		}
	});

	// Cascading option change handlers
	$('select[name="led_package_code"]').on('change', function() {
		updateCCTOptions();
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="environment_rating_code"]').on('change', function() {
		updateCCTOptions();
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="cct_code"]').on('change', function() {
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="lens_appearance_code"]').on('change', function() {
		updateDeliveredOutputs();
		updateUI();
	});

	$('select[name="delivered_output_value"]').on('change', function() {
		autoSelectTape();
		updateUI();
	});

	$('select[name="mounting_method_code"]').on('change', function() {
		updateUI();
	});

	$('select[name="finish_code"]').on('change', function() {
		autoResolveEndcapColor();
		updateUI();
	});

	// Initialize with existing configuration
	initializeWithExistingConfig();
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
		console.log('Auto-resolved endcap color from finish:', finishCode, '->', mapping.endcap_color_code);
	} else {
		// Fallback: if no mapping, use the first endcap color
		if (templateOptions.endcap_colors && templateOptions.endcap_colors.length > 0) {
			$('[name="endcap_color_code"]').val(templateOptions.endcap_colors[0].value);
			$('#endcapColorLabel').text('Endcap Color: ' + templateOptions.endcap_colors[0].label + ' (default)');
			$('#endcapColorDisplay').show();
			console.log('Using default endcap color (no finish mapping):', templateOptions.endcap_colors[0].value);
		} else {
			$('[name="endcap_color_code"]').val('');
			$('#endcapColorDisplay').hide();
		}
	}
}

function initializeWithExistingConfig() {
	console.log('Initializing with existing config:', existingConfig);
	
	if (!existingConfig || !existingConfig.fixture_template_code) {
		console.error('No existing configuration found');
		return;
	}
	
	// Trigger template load with pre-population flag
	var template = existingConfig.fixture_template_code;
	loadTemplateOptions(template, true);
	$('#templateOptions').show();
	$('#segmentsCard').show();
	$('#actionButtons').show();
}

function loadTemplateOptions(template_code, prePopulate) {
	console.log('loadTemplateOptions called with:', template_code, 'prePopulate:', prePopulate);
	// Use the cascading options API
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.get_cascading_options_for_template',
		args: { fixture_template_code: template_code },
		async: false,  // Make synchronous for initial load
		callback: function(r) {
			console.log('API response:', r);
			if (r.message && r.message.success) {
				templateOptions = r.message.options;
				console.log('Template options received:', templateOptions);
				populateOptions(r.message.options, prePopulate);
				
				// Initialize segments after options are loaded
				if (prePopulate && existingConfig.segments && existingConfig.segments.length > 0) {
					initializeSegmentsFromConfig();
				} else if (segmentCount === 0) {
					addSegment(true);
				}
			} else if (r.message && r.message.error) {
				console.error('API error:', r.message.error);
				frappe.msgprint({
					title: __('Error Loading Options'),
					message: r.message.error,
					indicator: 'red'
				});
			} else {
				console.error('Unexpected response:', r);
			}
		},
		error: function(r) {
			console.error('API call failed:', r);
		}
	});
}

function initializeSegmentsFromConfig() {
	console.log('Initializing segments from config:', existingConfig.segments);
	
	// Clear any existing segments
	$('#segmentsList').empty();
	segmentCount = 0;
	
	// Add each segment from the existing configuration
	existingConfig.segments.forEach(function(segData, index) {
		var isFirst = (index === 0);
		addSegmentWithData(isFirst, segData);
	});
	
	updateUI();
}

function addSegmentWithData(isFirst, segData) {
	segmentCount++;
	var template = document.getElementById('segmentTemplate');
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
	}
	
	document.getElementById('segmentsList').appendChild(clone);
	
	var segmentCard = $('#segmentsList .segment-card').last();
	if (templateOptions) {
		populateSegmentPowerFeedOptions(segmentCard);
	}
	
	// Pre-populate segment data
	if (segData) {
		// Set length (convert from mm to inches for display)
		var lengthInches = (segData.requested_length_mm / MM_PER_INCH).toFixed(1);
		segmentCard.find('[name="requested_length_mm"]').val(lengthInches);
		
		if (isFirst) {
			// Set power feed type for first segment
			if (segData.start_power_feed_type) {
				segmentCard.find('[name="start_power_feed_type"]').val(segData.start_power_feed_type);
			}
			// Set leader cable length (convert from mm to inches)
			if (segData.start_leader_cable_length_mm) {
				var leaderInches = (segData.start_leader_cable_length_mm / MM_PER_INCH).toFixed(1);
				segmentCard.find('[name="start_leader_cable_length_in"]').val(leaderInches);
			}
		}
		
		// Set end type
		var endType = segData.end_type || 'Endcap';
		setEndType(segmentCard.find('.end-type-btn[data-type="' + endType + '"]')[0], endType, true);
		
		if (endType === 'Jumper' && segData.end_power_feed_type) {
			segmentCard.find('[name="end_power_feed_type"]').val(segData.end_power_feed_type);
			if (segData.end_jumper_cable_length_mm) {
				var jumperInches = (segData.end_jumper_cable_length_mm / MM_PER_INCH).toFixed(1);
				segmentCard.find('[name="end_jumper_cable_length_in"]').val(jumperInches);
			}
		}
	} else {
		// Set default end type to Endcap
		setEndType(segmentCard.find('.end-type-btn[data-type="Endcap"]')[0], 'Endcap', true);
	}
	
	// Setup unit change handler for length conversion
	setupUnitChangeHandler(segmentCard);
}

function populateOptions(options, prePopulate) {
	console.log('populateOptions called with:', options, 'prePopulate:', prePopulate);
	
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
				pill.on('click', function() {
					// Update pill selection
					pillContainer.find('.pill-option').removeClass('active');
					$(this).addClass('active');
					// Sync to hidden select
					selectFallback.val(opt.value).trigger('change');
				});
				pillContainer.append(pill);
				
				// Add to fallback select
				selectFallback.append('<option value="' + PortalUI.escape(opt.value) + '">' + PortalUI.escape(opt.label) + '</option>');
			});
			
			// Pre-select if we have existing config
			if (prePopulate && existingConfig[fieldName]) {
				selectFallback.val(existingConfig[fieldName]);
				pillContainer.find('input[value="' + existingConfig[fieldName] + '"]').closest('.pill-option').addClass('active');
			}
		}
	});
	
	// When select changes (mobile), sync to pills
	Object.values(pillFields).forEach(function(fieldName) {
		$('select[name="' + fieldName + '"]').off('change.pillSync').on('change.pillSync', function() {
			var value = $(this).val();
			var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
			pillContainer.find('.pill-option').removeClass('active');
			pillContainer.find('input[value="' + value + '"]').closest('.pill-option').addClass('active');
		});
	});

	// Endcap color is now auto-resolved from finish via ilL-Rel-Finish Endcap Color
	// Auto-resolve after finish has been populated
	autoResolveEndcapColor();

	// For edit mode, we need to trigger cascading updates after pre-populating
	if (prePopulate) {
		// Update CCTs based on pre-selected values
		updateCCTOptions(true);
		// Update delivered outputs
		setTimeout(function() {
			updateDeliveredOutputs(true);
		}, 100);
	} else {
		// Hide output group initially - will be shown when all cascading selections are made
		$('#outputGroup').hide();
		// Clear auto-selected tape offering
		$('input[name="tape_offering_id"]').val('');
	}
}

function updateCCTOptions(prePopulate) {
	var template_code = $('select[name="fixture_template_code"]').val();
	var led_package = $('select[name="led_package_code"]').val();
	var environment = $('select[name="environment_rating_code"]').val();
	
	if (!template_code) return;
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.get_ccts_for_template',
		args: {
			fixture_template_code: template_code,
			led_package_code: led_package || null,
			environment_rating_code: environment || null
		},
		async: !prePopulate,  // Synchronous for pre-population
		callback: function(r) {
			if (r.message && r.message.success) {
				populatePillSelector('cct_code', r.message.ccts, prePopulate ? existingConfig.cct_code : null);
			}
		}
	});
}

function updateDeliveredOutputs(prePopulate) {
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
		lens: lens
	});
	
	// Only fetch outputs when all required fields are selected
	if (!template_code || !led_package || !environment || !cct || !lens) {
		$('#outputGroup').hide();
		$('input[name="tape_offering_id"]').val('');
		return;
	}
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.get_delivered_outputs_for_template',
		args: {
			fixture_template_code: template_code,
			led_package_code: led_package,
			environment_rating_code: environment,
			cct_code: cct,
			lens_appearance_code: lens
		},
		async: !prePopulate,  // Synchronous for pre-population
		callback: function(r) {
			console.log('Delivered outputs response:', r.message);
			if (r.message && r.message.success) {
				$('#outputGroup').show();
				populatePillSelector('delivered_output_value', r.message.delivered_outputs, prePopulate ? existingConfig.delivered_output_value : null);
				
				// Show helpful text about lens transmission
				var transmission = r.message.lens_transmission_pct || 100;
				$('#outputHelpText').text('Output adjusted for ' + transmission.toFixed(0) + '% lens transmission');
				
				// Auto-select tape after setting output value
				if (prePopulate) {
					autoSelectTape();
				}
			} else {
				$('#outputGroup').hide();
				console.log('No outputs available or error:', r.message);
			}
		}
	});
}

function populatePillSelector(fieldName, options, preSelectValue) {
	var pillContainer = $('.pill-selector[data-field="' + fieldName + '"]');
	var selectFallback = $('select[name="' + fieldName + '"]');
	
	// Clear existing
	pillContainer.empty();
	selectFallback.empty().append('<option value="">Select...</option>');
	
	if (options && options.length > 0) {
		options.forEach(function(opt) {
			var label = opt.label || opt.value;
			// Add pill button
			var pill = $('<label class="pill-option">' +
				'<input type="radio" name="' + fieldName + '_pill" value="' + opt.value + '">' +
				label +
			'</label>');
			pill.on('click', function() {
				// Update pill selection
				pillContainer.find('.pill-option').removeClass('active');
				$(this).addClass('active');
				// Sync to select and trigger change
				selectFallback.val(opt.value).trigger('change');
			});
			pillContainer.append(pill);
			
			// Add to fallback select
			selectFallback.append('<option value="' + PortalUI.escape(opt.value) + '">' + PortalUI.escape(label) + '</option>');
		});
		
		// Pre-select if value provided
		if (preSelectValue) {
			selectFallback.val(preSelectValue);
			pillContainer.find('input[value="' + preSelectValue + '"]').closest('.pill-option').addClass('active');
		}
	}
}

function autoSelectTape() {
	var template_code = $('select[name="fixture_template_code"]').val();
	var led_package = $('select[name="led_package_code"]').val();
	var environment = $('select[name="environment_rating_code"]').val();
	var cct = $('select[name="cct_code"]').val();
	var lens = $('select[name="lens_appearance_code"]').val();
	var output = $('select[name="delivered_output_value"]').val();
	
	if (!template_code || !led_package || !environment || !cct || !lens || !output) {
		$('input[name="tape_offering_id"]').val('');
		return;
	}
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.auto_select_tape_for_configuration',
		args: {
			fixture_template_code: template_code,
			led_package_code: led_package,
			environment_rating_code: environment,
			cct_code: cct,
			lens_appearance_code: lens,
			delivered_output_value: parseInt(output)
		},
		callback: function(r) {
			if (r.message && r.message.success && r.message.tape_offering_id) {
				$('input[name="tape_offering_id"]').val(r.message.tape_offering_id);
				updateUI();
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

function populateSegmentPowerFeedOptions(segmentCard) {
	if (!templateOptions || !templateOptions.power_feed_type) return;
	
	['start_power_feed_type', 'end_power_feed_type'].forEach(function(fieldName) {
		var select = segmentCard.find('[name="' + fieldName + '"]');
		select.empty().append('<option value="">Select...</option>');
		templateOptions.power_feed_type.forEach(function(opt) {
			select.append('<option value="' + PortalUI.escape(opt.value) + '">' + PortalUI.escape(opt.label) + '</option>');
		});
	});
}

function addSegment(isFirst) {
	addSegmentWithData(isFirst, null);
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

function setEndType(btn, type, skipAutoAdd) {
	var card = $(btn).closest('.segment-card');
	var endTypeInput = card.find('[name="end_type"]');
	
	// Update button states
	card.find('.end-type-btn').removeClass('active btn-primary').addClass('btn-outline-secondary');
	$(btn).removeClass('btn-outline-secondary').addClass('active btn-primary');
	
	endTypeInput.val(type);
	
	if (type === 'Endcap') {
		card.find('.endcap-fields').show();
		card.find('.jumper-fields').hide();
		
		// Remove any segments after this one (unless we're initializing from config)
		if (!skipAutoAdd) {
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
		}
		
		$('#addSegmentHint').hide();
	} else {
		// Jumper
		card.find('.endcap-fields').hide();
		card.find('.jumper-fields').show();
		
		// Auto-add next segment if this is the last one (unless we're initializing from config)
		if (!skipAutoAdd) {
			var currentIndex = parseInt(card.data('segment-index'));
			var hasNextSegment = false;
			$('.segment-card').each(function() {
				if (parseInt($(this).data('segment-index')) > currentIndex) {
					hasNextSegment = true;
				}
			});
			
			if (!hasNextSegment) {
				// Wait a moment then add the next segment
				setTimeout(function() {
					addSegment(false);
				}, 100);
			}
		}
	}
	
	if (!skipAutoAdd) {
		updateUI();
	}
}

function setupUnitChangeHandler(segmentCard) {
	var unitSelect = segmentCard.find('[name="length_unit"]');
	// Store current unit in data attribute for persistence
	unitSelect.data('lastUnit', unitSelect.val());
	
	unitSelect.on('change', function() {
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

function updateUI() {
	// Update segment count badge
	$('#segmentCountBadge').text(segmentCount + ' segment' + (segmentCount !== 1 ? 's' : ''));
	
	// Check if fixture is complete
	var lastSegment = $('#segmentsList .segment-card').last();
	var segmentComplete = lastSegment.length && lastSegment.find('[name="end_type"]').val() === 'Endcap';
	
	// Check if all required cascading fields are selected
	var cascadingComplete = (
		$('[name="led_package_code"]').val() &&
		$('[name="environment_rating_code"]').val() &&
		$('[name="cct_code"]').val() &&
		$('[name="lens_appearance_code"]').val() &&
		$('[name="delivered_output_value"]').val() &&
		$('[name="mounting_method_code"]').val() &&
		$('[name="finish_code"]').val() &&
		$('[name="endcap_color_code"]').val()
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
			var priorEndPFT = priorSegment.find('[name="end_power_feed_type"]').val();
			var priorJumperLenIn = priorSegment.find('[name="end_jumper_cable_length_in"]').val();
			// Convert inches to mm for storage
			var priorJumperLenMm = Math.round((parseFloat(priorJumperLenIn) || 12) * MM_PER_INCH);
			
			$(this)[0].dataset.inheritedPowerFeedType = priorEndPFT || '';
			$(this)[0].dataset.inheritedCableLength = priorJumperLenMm;
			
			var inheritedText = 'From prior: ' + (priorEndPFT || 'N/A') + ', ' + (priorJumperLenIn || '12') + '"';
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
			// First segment: get start power feed and leader cable
			segment.start_power_feed_type = card.find('[name="start_power_feed_type"]').val();
			// Convert inches to mm for backend
			var leaderInches = parseFloat(card.find('[name="start_leader_cable_length_in"]').val()) || 12;
			segment.start_leader_cable_length_mm = Math.round(leaderInches * MM_PER_INCH);
		} else {
			// Inherited from prior segment
			segment.start_power_feed_type = card[0].dataset.inheritedPowerFeedType || '';
			segment.start_leader_cable_length_mm = parseInt(card[0].dataset.inheritedCableLength) || 300;
		}
		
		if (segment.end_type === 'Jumper') {
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
		segments_json: JSON.stringify(segments)
	};
	
	// Use the output-based API if we have delivered_output_value
	if (deliveredOutputValue) {
		data.delivered_output_value = parseInt(deliveredOutputValue);
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote_multisegment_with_output',
			args: data,
			callback: function(r) {
				if (r.message) {
					currentResult = r.message;
					displayResults(r.message);
				}
			}
		});
	} else if (tapeOfferingId) {
		// Fallback to old API with tape_offering_id
		data.tape_offering_id = tapeOfferingId;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote_multisegment',
			args: data,
			callback: function(r) {
				if (r.message) {
					currentResult = r.message;
					displayResults(r.message);
				}
			}
		});
	} else {
		frappe.msgprint({
			title: __('Missing Selection'),
			message: __('Please select an Output Level to continue.'),
			indicator: 'orange'
		});
		return;
	}
}

function copyToClipboard(elementId) {
	var text = document.getElementById(elementId).innerText;
	navigator.clipboard.writeText(text).then(function() {
		frappe.show_alert({message: __('Copied to clipboard'), indicator: 'green'}, 2);
	}).catch(function() {
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
	var partNumber = document.getElementById('partNumberValue').innerText;
	var description = document.getElementById('partDescriptionValue').innerText;
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
		$('#saveBtn').prop('disabled', false);
	} else {
		statusBadge.removeClass('badge-secondary badge-success').addClass('badge-danger').text('Invalid');
		$('#saveBtn').prop('disabled', true);
	}

	// Display part number and description
	if (result.configured_fixture_id) {
		$('#partNumberPanel').show();
		$('#partNumberValue').text(result.configured_fixture_id);
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
			messagesList.append('<div class="alert alert-' + alertClass + ' py-2 mb-1">' + PortalUI.escape(msg.text) + '</div>');
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
			runsHtml += '<th>' + editFixtureText("Run") + '</th>';
			runsHtml += '<th>' + editFixtureText("Segment") + '</th>';
			runsHtml += '<th>' + editFixtureText("Length") + '</th>';
			runsHtml += '<th>' + editFixtureText("Watts") + '</th>';
			runsHtml += '</tr></thead><tbody>';
			
			result.computed.runs.forEach(function(run) {
				// Use pre-computed inch value if available, otherwise calculate
				var lengthIn = run.run_len_in || (run.run_len_mm / MM_PER_INCH).toFixed(1);
				var lengthFt = (run.run_len_mm / MM_PER_FOOT).toFixed(2);
				runsHtml += '<tr>';
				runsHtml += '<td class="text-center">' + PortalUI.escape(run.run_index) + '</td>';
				runsHtml += '<td class="text-center">' + PortalUI.escape(run.segment_index) + '</td>';
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
		if (dp.status === 'selected' && dp.drivers && dp.drivers.length > 0) {
			var driverHtml = '<table class="table table-sm">';
			dp.drivers.forEach(function(d) {
				driverHtml += '<tr><td>' + PortalUI.escape(d.item_code) + '</td><td>×' + PortalUI.escape(d.qty) + '</td></tr>';
			});
			driverHtml += '</table>';
			$('#driverPlan').html(driverHtml);
		} else {
			$('#driverPlan').html('<span class="text-muted">' + PortalUI.escape(dp.status) + '</span>');
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
				breakdownHtml += '<tr><td>' + PortalUI.escape(adder.component) + '</td><td class="text-right">$' + adder.amount.toFixed(2) + '</td></tr>';
			});
			breakdownHtml += '</table></details>';
			$('#adderBreakdown').html(breakdownHtml);
		}
	}
}

function updateFixture() {
	if (!currentResult || !currentResult.is_valid || !schedule_name) {
		frappe.msgprint('Cannot save: configuration is not valid or no schedule specified');
		return;
	}
	
	// Disable button to prevent double-clicks
	$('#saveBtn').prop('disabled', true).html('<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> Updating...');
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.update_configured_fixture_on_schedule',
		args: {
			schedule_name: schedule_name,
			line_idx: line_idx,
			new_configured_fixture_id: currentResult.configured_fixture_id,
			manufacturable_length_mm: currentResult.computed.manufacturable_overall_length_mm
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				frappe.msgprint({
					title: 'Success',
					indicator: 'green',
					message: 'Fixture configuration updated successfully'
				});
				// Redirect back to schedule
				setTimeout(function() {
					window.location.href = '/portal/schedules/' + schedule_name;
				}, 1000);
			} else {
				frappe.msgprint(r.message.error || 'Error updating fixture configuration');
				$('#saveBtn').prop('disabled', false).html('<i class="fa fa-save" aria-hidden="true"></i> Update Fixture');
			}
		},
		error: function() {
			$('#saveBtn').prop('disabled', false).html('<i class="fa fa-save" aria-hidden="true"></i> Update Fixture');
		}
	});
}
