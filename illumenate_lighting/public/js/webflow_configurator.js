/**
 * Webflow Configurator JavaScript
 * 
 * Handles the portal configurator UI matching the Webflow design:
 * Series → Dry/Wet → CCT → Output → Lens → Mounting → Finish → Length → Start Feed → End Feed
 */

// Global state
var WebflowConfigurator = {
    context: {},
    productSlug: null,
    selections: {},
    options: {},
    seriesInfo: null,
    isInitialized: false,
    lengthConfig: {}
};

// Step configuration matching the API
var CONFIGURATOR_STEPS = [
    { name: 'series', label: 'Series', locked: true },
    { name: 'environment_rating', label: 'Dry/Wet', depends_on: ['series'] },
    { name: 'cct', label: 'CCT', depends_on: ['series', 'environment_rating'] },
    { name: 'output_level', label: 'Output', depends_on: ['series', 'environment_rating', 'cct'] },
    { name: 'lens_appearance', label: 'Lens', depends_on: ['series'] },
    { name: 'mounting_method', label: 'Mounting', depends_on: [] },
    { name: 'finish', label: 'Finish', depends_on: [] },
    { name: 'length', label: 'Length', depends_on: [] },
    { name: 'start_feed', label: 'Start Feed', depends_on: [] },
    { name: 'end_feed', label: 'End Feed', depends_on: [] }
];

/**
 * Initialize the Webflow configurator
 */
function initWebflowConfigurator(context) {
    console.log('Initializing Webflow Configurator', context);
    WebflowConfigurator.context = context || {};
    
    // Bind event handlers
    bindEventHandlers();
    
    // Load from session if provided
    if (context.session_id) {
        loadFromSession(context.session_id);
    }
    
    // Load from product if provided
    if (context.product_slug) {
        WebflowConfigurator.productSlug = context.product_slug;
        initializeFromProduct(context.product_slug);
    }
    
    // Handle template selection if no product
    var selectedTemplate = $('#fixtureTemplateSelect').val();
    if (selectedTemplate && !context.product_slug) {
        onTemplateSelected(selectedTemplate);
    }
}

/**
 * Bind all event handlers
 */
function bindEventHandlers() {
    // Template selection
    $('#fixtureTemplateSelect').on('change', function() {
        var templateCode = $(this).val();
        if (templateCode) {
            onTemplateSelected(templateCode);
        } else {
            hideAllSections();
        }
    });
    
    // Pill button clicks (delegate for dynamic content)
    $(document).on('click', '.pill-selector .pill', function(e) {
        e.preventDefault();
        handlePillClick($(this));
    });
    
    // Length input changes
    $('input[name="length_value"]').on('change input', debounce(function() {
        updateLengthInches();
        updatePartNumberPreview();
        updateValidateButton();
    }, 300));
    
    $('select[name="length_unit"]').on('change', function() {
        updateLengthInches();
        updatePartNumberPreview();
        updateValidateButton();
    });
    
    // Feed length changes
    $('input[name="start_feed_length_ft"], input[name="end_feed_length_ft"]').on('change input', debounce(function() {
        updatePartNumberPreview();
        updateValidateButton();
    }, 300));
}

/**
 * Handle template selection
 */
function onTemplateSelected(templateCode) {
    console.log('Template selected:', templateCode);
    
    // Update series display
    var $option = $('#fixtureTemplateSelect option:selected');
    var templateName = $option.data('name') || $option.text();
    $('#seriesName').text(templateName);
    $('#seriesCode').text(templateCode);
    
    // Show loading state
    $('#environmentSection').show().find('.pill-selector').html('<span class="text-muted"><i class="fa fa-spinner fa-spin"></i> Loading options...</span>');
    
    // Find or create product slug for API calls
    // For now, use template code as slug if no product
    var productSlug = WebflowConfigurator.productSlug || templateCode;
    
    // Initialize from API
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_configurator_init',
        args: { product_slug: productSlug },
        callback: function(r) {
            if (r.message && r.message.success) {
                handleInitResponse(r.message);
            } else {
                console.log('API returned error, using fallback:', r.message);
                // Fallback - load options directly from template
                loadOptionsFromTemplate(templateCode);
            }
        },
        error: function(err) {
            console.error('API call failed, using fallback:', err);
            // Fallback - load options directly from template
            loadOptionsFromTemplate(templateCode);
        }
    });
    
    // Update progress after template selection
    updateProgress();
}

/**
 * Initialize from a Webflow product
 */
function initializeFromProduct(productSlug) {
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_configurator_init',
        args: { product_slug: productSlug },
        callback: function(r) {
            if (r.message && r.message.success) {
                handleInitResponse(r.message);
            } else {
                frappe.msgprint(__('Product not found or not configurable'));
            }
        }
    });
}

/**
 * Handle initialization response from API
 */
function handleInitResponse(data) {
    console.log('Configurator initialized:', data);
    
    WebflowConfigurator.seriesInfo = data.series;
    WebflowConfigurator.options = data.options;
    WebflowConfigurator.lengthConfig = data.length_config;
    WebflowConfigurator.isInitialized = true;
    
    // Update series display
    if (data.series) {
        $('#seriesName').text(data.series.display_name || data.series.series_name);
        $('#seriesCode').text(data.series.series_code);
    }
    
    // Populate initial options
    populatePillSelector('environment_rating', data.options.environment_ratings);
    populatePillSelector('lens_appearance', data.options.lens_appearances);
    populatePillSelector('mounting_method', data.options.mounting_methods);
    populatePillSelector('finish', data.options.finishes);
    
    // Populate feed direction options
    populateFeedDirections(data.options.feed_directions);
    
    // Update length constraints
    if (data.length_config) {
        $('input[name="length_value"]').attr('min', data.length_config.min_inches);
        $('input[name="length_value"]').attr('max', data.length_config.max_inches);
        // Set placeholder instead of value so it doesn't count as completed
        $('input[name="length_value"]').attr('placeholder', data.length_config.default_inches || 50);
        $('#lengthNote').text(data.length_config.max_run_note || 'Maximum length is 30 ft');
        // Store default for later use
        WebflowConfigurator.lengthConfig.default_inches = data.length_config.default_inches || 50;
    }
    
    // Show all sections
    showAllSections();
    
    // Update progress indicators
    updateProgress();
    
    // Update part number preview
    updatePartNumberPreview();
    
    // Show complex fixture banner
    $('#complexFixtureBanner').show();
}

/**
 * Fallback: Load options directly from template
 */
function loadOptionsFromTemplate(templateCode) {
    console.log('Loading options from template:', templateCode);
    
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'ilL-Fixture-Template',
            name: templateCode
        },
        callback: function(r) {
            if (r.message) {
                processTemplateOptions(r.message);
            }
        }
    });
}

/**
 * Process template options (fallback method)
 */
function processTemplateOptions(template) {
    // Extract options from template
    var options = {
        environment_ratings: [],
        lens_appearances: [],
        mounting_methods: [],
        finishes: [],
        feed_directions: [
            { value: 'End', label: 'End', code: 'E' },
            { value: 'Back', label: 'Back', code: 'B' }
        ]
    };
    
    // Parse allowed_options
    (template.allowed_options || []).forEach(function(opt) {
        if (!opt.is_active) return;
        
        switch (opt.option_type) {
            case 'Lens Appearance':
                if (opt.lens_appearance) {
                    options.lens_appearances.push({
                        value: opt.lens_appearance,
                        label: opt.lens_appearance,
                        is_default: opt.is_default
                    });
                }
                break;
            case 'Mounting Method':
                if (opt.mounting_method) {
                    options.mounting_methods.push({
                        value: opt.mounting_method,
                        label: opt.mounting_method,
                        is_default: opt.is_default
                    });
                }
                break;
            case 'Finish':
                if (opt.finish) {
                    options.finishes.push({
                        value: opt.finish,
                        label: opt.finish,
                        is_default: opt.is_default
                    });
                }
                break;
        }
    });
    
    // Parse allowed_tape_offerings for environment ratings
    var envSet = {};
    (template.allowed_tape_offerings || []).forEach(function(tape) {
        if (tape.is_active && tape.environment_rating && !envSet[tape.environment_rating]) {
            envSet[tape.environment_rating] = true;
            options.environment_ratings.push({
                value: tape.environment_rating,
                label: tape.environment_rating
            });
        }
    });
    
    WebflowConfigurator.options = options;
    WebflowConfigurator.seriesInfo = {
        series_code: template.template_code,
        series_name: template.template_name,
        led_package_code: 'XX',
        display_name: template.template_name
    };
    WebflowConfigurator.isInitialized = true;
    
    // Populate options
    populatePillSelector('environment_rating', options.environment_ratings);
    populatePillSelector('lens_appearance', options.lens_appearances);
    populatePillSelector('mounting_method', options.mounting_methods);
    populatePillSelector('finish', options.finishes);
    populateFeedDirections(options.feed_directions);
    
    showAllSections();
    updatePartNumberPreview();
    updateProgress();
}

/**
 * Populate a pill selector with options
 */
function populatePillSelector(fieldName, options) {
    var $container = $('.pill-selector[data-field="' + fieldName + '"]');
    var $select = $('select[name="' + fieldName + '"]');
    
    $container.empty();
    $select.empty().append('<option value="">Select...</option>');
    
    if (!options || !options.length) {
        $container.append('<span class="text-muted">No options available</span>');
        return;
    }
    
    options.forEach(function(opt) {
        // Create pill button
        var $pill = $('<button type="button" class="pill"></button>');
        $pill.attr('data-value', opt.value);
        $pill.attr('data-code', opt.code || '');
        $pill.text(opt.label || opt.value);
        
        if (opt.is_default) {
            $pill.addClass('default');
        }
        
        $container.append($pill);
        
        // Create select option
        var $option = $('<option></option>');
        $option.val(opt.value);
        $option.text(opt.label || opt.value);
        if (opt.is_default) {
            $option.attr('selected', true);
        }
        $select.append($option);
    });
    
    // Auto-select default if exists
    var $default = $container.find('.pill.default');
    if ($default.length) {
        selectPill($default);
    }
}

/**
 * Populate feed direction pill selectors
 */
function populateFeedDirections(directions) {
    var dirOptions = directions || [
        { value: 'End', label: 'End', code: 'E' },
        { value: 'Back', label: 'Back', code: 'B' }
    ];
    
    ['start_feed_direction', 'end_feed_direction'].forEach(function(fieldName) {
        var $container = $('.pill-selector[data-field="' + fieldName + '"]');
        $container.empty();
        
        dirOptions.forEach(function(opt) {
            var $pill = $('<button type="button" class="pill"></button>');
            $pill.attr('data-value', opt.value);
            $pill.attr('data-code', opt.code || '');
            $pill.text(opt.label || opt.value);
            $container.append($pill);
        });
    });
}

/**
 * Handle pill button click
 */
function handlePillClick($pill) {
    var fieldName = $pill.closest('.pill-selector').data('field');
    var value = $pill.data('value');
    
    console.log('Pill clicked:', fieldName, value);
    
    // Toggle active state
    $pill.siblings().removeClass('active');
    $pill.addClass('active');
    
    // Update hidden select
    $('select[name="' + fieldName + '"]').val(value);
    
    // Store selection
    WebflowConfigurator.selections[fieldName] = value;
    
    // Update progress
    updateProgress();
    
    // Handle cascading updates
    handleCascadingUpdate(fieldName, value);
    
    // Update part number preview
    updatePartNumberPreview();
    
    // Update validate button
    updateValidateButton();
    
    // Update summary
    updateSummary();
}

/**
 * Select a pill programmatically
 */
function selectPill($pill) {
    $pill.siblings().removeClass('active');
    $pill.addClass('active');
    
    var fieldName = $pill.closest('.pill-selector').data('field');
    var value = $pill.data('value');
    
    $('select[name="' + fieldName + '"]').val(value);
    WebflowConfigurator.selections[fieldName] = value;
}

/**
 * Handle cascading option updates
 */
function handleCascadingUpdate(fieldName, value) {
    var productSlug = WebflowConfigurator.productSlug || $('#fixtureTemplateSelect').val();
    
    if (fieldName === 'environment_rating') {
        // Clear downstream selections
        clearSelection('cct');
        clearSelection('output_level');
        
        // Fetch CCTs for this environment
        frappe.call({
            method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_cascading_options',
            args: {
                product_slug: productSlug,
                step_name: 'environment_rating',
                selections: JSON.stringify(WebflowConfigurator.selections)
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    if (r.message.updated_options && r.message.updated_options.ccts) {
                        populatePillSelector('cct', r.message.updated_options.ccts);
                    }
                }
            }
        });
    } else if (fieldName === 'cct') {
        // Clear downstream selections
        clearSelection('output_level');
        
        // Fetch outputs for this environment + CCT + current lens
        frappe.call({
            method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_cascading_options',
            args: {
                product_slug: productSlug,
                step_name: 'cct',
                selections: JSON.stringify(WebflowConfigurator.selections)
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    if (r.message.updated_options && r.message.updated_options.output_levels) {
                        populatePillSelector('output_level', r.message.updated_options.output_levels);
                    }
                }
            }
        });
    } else if (fieldName === 'lens_appearance') {
        // When lens changes, recalculate output options with new transmission
        // Only if environment and CCT are already selected
        if (WebflowConfigurator.selections['environment_rating'] && WebflowConfigurator.selections['cct']) {
            // Clear output selection since delivered values will change
            clearSelection('output_level');
            
            // Fetch new output levels with updated lens transmission
            frappe.call({
                method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_cascading_options',
                args: {
                    product_slug: productSlug,
                    step_name: 'lens_appearance',
                    selections: JSON.stringify(WebflowConfigurator.selections)
                },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        if (r.message.updated_options && r.message.updated_options.output_levels) {
                            populatePillSelector('output_level', r.message.updated_options.output_levels);
                        }
                    }
                }
            });
        }
    }
}

/**
 * Clear a selection
 */
function clearSelection(fieldName) {
    var $container = $('.pill-selector[data-field="' + fieldName + '"]');
    $container.find('.pill').removeClass('active');
    $('select[name="' + fieldName + '"]').val('');
    delete WebflowConfigurator.selections[fieldName];
}

/**
 * Show all configuration sections
 */
function showAllSections() {
    $('#environmentSection, #cctSection, #outputSection').show();
    $('#lensSection, #mountingSection, #finishSection').show();
    $('#lengthSection, #startFeedSection, #endFeedSection').show();
}

/**
 * Hide all configuration sections
 */
function hideAllSections() {
    $('#environmentSection, #cctSection, #outputSection').hide();
    $('#lensSection, #mountingSection, #finishSection').hide();
    $('#lengthSection, #startFeedSection, #endFeedSection').hide();
    $('#complexFixtureBanner').hide();
}

/**
 * Update progress indicators
 */
function updateProgress() {
    var completed = 0;
    var total = CONFIGURATOR_STEPS.length;
    
    // Count completed steps
    CONFIGURATOR_STEPS.forEach(function(step, index) {
        var $stepEl = $('.progress-step[data-step="' + index + '"]');
        
        // For locked steps (series), check if actually selected
        if (step.locked) {
            if (isStepCompleted(step.name)) {
                $stepEl.addClass('completed').removeClass('active');
                $stepEl.find('.step-number').text('✓');
                completed++;
            } else {
                $stepEl.removeClass('completed').addClass('active');
                $stepEl.find('.step-number').text(index + 1);
            }
        } else if (isStepCompleted(step.name)) {
            $stepEl.addClass('completed').removeClass('active');
            $stepEl.find('.step-number').text('✓');
            completed++;
        } else {
            $stepEl.removeClass('completed active');
            $stepEl.find('.step-number').text(index + 1);
        }
    });
    
    // Find first incomplete step and mark as active
    var foundActive = false;
    CONFIGURATOR_STEPS.forEach(function(step, index) {
        if (!foundActive && !isStepCompleted(step.name)) {
            $('.progress-step[data-step="' + index + '"]').addClass('active');
            foundActive = true;
        }
    });
    
    var pct = Math.round((completed / total) * 100);
    $('#progressBadge').text(pct + '%');
}

/**
 * Check if a step is completed
 */
function isStepCompleted(stepName) {
    switch (stepName) {
        case 'series':
            return !!$('#fixtureTemplateSelect').val();
        case 'length':
            // Check that length has a value and that the configurator is initialized
            var lengthVal = $('input[name="length_value"]').val();
            return WebflowConfigurator.isInitialized && !!lengthVal && lengthVal !== '';
        case 'start_feed':
            var startFeedVal = $('input[name="start_feed_length_ft"]').val();
            return !!WebflowConfigurator.selections['start_feed_direction'] && 
                   !!startFeedVal && startFeedVal !== '';
        case 'end_feed':
            var endFeedVal = $('input[name="end_feed_length_ft"]').val();
            return !!WebflowConfigurator.selections['end_feed_direction'] && 
                   !!endFeedVal && endFeedVal !== '';
        default:
            return !!WebflowConfigurator.selections[stepName];
    }
}

/**
 * Update the length in inches based on current input
 */
function updateLengthInches() {
    var value = parseFloat($('input[name="length_value"]').val()) || 0;
    var unit = $('select[name="length_unit"]').val();
    var inches;
    
    switch (unit) {
        case 'ft':
            inches = value * 12;
            break;
        case 'mm':
            inches = value / 25.4;
            break;
        default: // inches
            inches = value;
    }
    
    WebflowConfigurator.selections['length_inches'] = inches;
}

/**
 * Update part number preview
 */
function updatePartNumberPreview() {
    var productSlug = WebflowConfigurator.productSlug || $('#fixtureTemplateSelect').val();
    if (!productSlug) return;
    
    // Gather all selections
    var selections = gatherAllSelections();
    
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_part_number_preview',
        args: {
            product_slug: productSlug,
            selections: JSON.stringify(selections)
        },
        async: false,
        callback: function(r) {
            if (r.message && r.message.success) {
                displayPartNumberPreview(r.message);
            }
        },
        error: function() {
            // Fallback to local preview
            displayLocalPartNumberPreview();
        }
    });
}

/**
 * Display part number preview from API response
 */
function displayPartNumberPreview(data) {
    var $preview = $('#partNumberPreview');
    $preview.empty();
    
    if (data.segments) {
        data.segments.forEach(function(seg, idx) {
            var $span = $('<span class="segment"></span>');
            $span.text((idx > 0 ? '-' : '') + seg.code);
            
            if (seg.locked) {
                $span.addClass('locked');
            } else if (seg.selected) {
                $span.addClass('selected');
            } else {
                $span.addClass('unselected');
            }
            
            $preview.append($span);
        });
    } else if (data.part_number_preview) {
        $preview.text(data.part_number_preview);
    }
}

/**
 * Display local part number preview (fallback)
 */
function displayLocalPartNumberPreview() {
    var series = WebflowConfigurator.seriesInfo || {};
    var sel = WebflowConfigurator.selections;
    
    var parts = [
        'ILL-' + (series.series_code || 'XX') + '-' + (series.led_package_code || 'XX'),
        sel.environment_rating ? 'I' : 'xx',
        sel.cct || 'xx',
        sel.output_level || 'xx',
        sel.lens_appearance || 'xx',
        sel.mounting_method || 'xx',
        sel.finish || 'xx'
    ];
    
    $('#partNumberPreview').text(parts.join('-'));
}

/**
 * Gather all selections for API calls
 */
function gatherAllSelections() {
    updateLengthInches();
    
    return {
        environment_rating: WebflowConfigurator.selections['environment_rating'] || '',
        cct: WebflowConfigurator.selections['cct'] || '',
        output_level: WebflowConfigurator.selections['output_level'] || '',
        lens_appearance: WebflowConfigurator.selections['lens_appearance'] || '',
        mounting_method: WebflowConfigurator.selections['mounting_method'] || '',
        finish: WebflowConfigurator.selections['finish'] || '',
        length_inches: WebflowConfigurator.selections['length_inches'] || '',
        start_feed_direction: WebflowConfigurator.selections['start_feed_direction'] || '',
        start_feed_length_ft: $('input[name="start_feed_length_ft"]').val() || '',
        end_feed_direction: WebflowConfigurator.selections['end_feed_direction'] || '',
        end_feed_length_ft: $('input[name="end_feed_length_ft"]').val() || '',
        product_slug: WebflowConfigurator.productSlug || $('#fixtureTemplateSelect').val()
    };
}

/**
 * Update validate button state
 */
function updateValidateButton() {
    var requiredFields = [
        'environment_rating', 'cct', 'output_level', 'lens_appearance',
        'mounting_method', 'finish', 'start_feed_direction', 'end_feed_direction'
    ];
    
    var allFilled = true;
    requiredFields.forEach(function(field) {
        if (!WebflowConfigurator.selections[field]) {
            allFilled = false;
        }
    });
    
    // Check length
    if (!$('input[name="length_value"]').val()) {
        allFilled = false;
    }
    
    // Check feed lengths
    if (!$('input[name="start_feed_length_ft"]').val() || 
        !$('input[name="end_feed_length_ft"]').val()) {
        allFilled = false;
    }
    
    $('#validateBtn').prop('disabled', !allFilled);
    
    if (allFilled) {
        $('#validationStatus').removeClass('badge-secondary').addClass('badge-info').text(__('Ready'));
    } else {
        $('#validationStatus').removeClass('badge-info badge-success').addClass('badge-secondary').text(__('Incomplete'));
    }
}

/**
 * Update configuration summary
 */
function updateSummary() {
    var $list = $('#summaryList');
    var $placeholder = $('#summaryPlaceholder');
    
    var items = [];
    
    // Add selected items
    var labels = {
        'environment_rating': 'Environment',
        'cct': 'CCT',
        'output_level': 'Output',
        'lens_appearance': 'Lens',
        'mounting_method': 'Mounting',
        'finish': 'Finish'
    };
    
    for (var field in labels) {
        if (WebflowConfigurator.selections[field]) {
            items.push({
                label: labels[field],
                value: WebflowConfigurator.selections[field]
            });
        }
    }
    
    // Add length
    var length = $('input[name="length_value"]').val();
    var unit = $('select[name="length_unit"]').val();
    if (length) {
        items.push({
            label: 'Length',
            value: length + ' ' + unit
        });
    }
    
    // Add feeds
    if (WebflowConfigurator.selections['start_feed_direction']) {
        var startLen = $('input[name="start_feed_length_ft"]').val();
        items.push({
            label: 'Start Feed',
            value: WebflowConfigurator.selections['start_feed_direction'] + ' - ' + startLen + ' ft'
        });
    }
    if (WebflowConfigurator.selections['end_feed_direction']) {
        var endLen = $('input[name="end_feed_length_ft"]').val();
        items.push({
            label: 'End Feed',
            value: WebflowConfigurator.selections['end_feed_direction'] + ' - ' + endLen + ' ft'
        });
    }
    
    // Update UI
    if (items.length > 0) {
        $placeholder.hide();
        $list.empty().show();
        
        items.forEach(function(item) {
            $list.append(
                '<li class="list-group-item d-flex justify-content-between">' +
                '<span class="text-muted">' + item.label + '</span>' +
                '<strong>' + item.value + '</strong>' +
                '</li>'
            );
        });
    } else {
        $placeholder.show();
        $list.hide();
    }
}

/**
 * Validate configuration via API
 */
function validateConfiguration() {
    var productSlug = WebflowConfigurator.productSlug || $('#fixtureTemplateSelect').val();
    var selections = gatherAllSelections();
    
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.validate_configuration',
        args: {
            product_slug: productSlug,
            selections: JSON.stringify(selections)
        },
        freeze: true,
        freeze_message: __('Validating configuration...'),
        callback: function(r) {
            if (r.message) {
                handleValidationResponse(r.message);
            }
        }
    });
}

/**
 * Handle validation response
 */
function handleValidationResponse(data) {
    var $messages = $('#validationMessages');
    var $messagesList = $('#messagesList');
    
    $messagesList.empty();
    
    if (data.success && data.is_valid) {
        // Success
        $('#validationStatus').removeClass('badge-secondary badge-info badge-danger')
            .addClass('badge-success').text(__('Valid'));
        
        $messagesList.append(
            '<div class="alert alert-success">' +
            '<i class="fa fa-check-circle mr-2"></i>' +
            __('Configuration is valid!') +
            '</div>'
        );
        
        // Update part number
        if (data.part_number) {
            $('#partNumberPreview').text(data.part_number);
        }
        
        // Store tape offering
        if (data.tape_offering_id) {
            $('input[name="tape_offering_id"]').val(data.tape_offering_id);
        }
        
        // Show pricing if available
        if (data.pricing && WebflowConfigurator.context.show_pricing) {
            $('#basePrice').text('$' + data.pricing.base_price.toFixed(2));
            $('#lengthPrice').text('$' + data.pricing.length_price.toFixed(2));
            $('#totalMsrp').text('$' + data.pricing.total_msrp.toFixed(2));
            $('#pricingPreview').show();
        }
        
        // Enable add to schedule button
        $('#addToScheduleBtn').prop('disabled', false);
        
    } else {
        // Error
        $('#validationStatus').removeClass('badge-secondary badge-info badge-success')
            .addClass('badge-danger').text(__('Invalid'));
        
        $messagesList.append(
            '<div class="alert alert-danger">' +
            '<i class="fa fa-exclamation-circle mr-2"></i>' +
            (data.error || __('Configuration is invalid')) +
            '</div>'
        );
        
        $('#addToScheduleBtn').prop('disabled', true);
    }
    
    $messages.show();
}

/**
 * Add configuration to schedule
 */
function addToSchedule() {
    var scheduleId = WebflowConfigurator.context.schedule_name;
    
    if (!scheduleId) {
        // Show schedule selection dialog
        showScheduleSelectionDialog();
        return;
    }
    
    var selections = gatherAllSelections();
    var quantity = 1; // Could add quantity input
    
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.add_to_schedule',
        args: {
            schedule_id: scheduleId,
            configuration: JSON.stringify(selections),
            quantity: quantity
        },
        freeze: true,
        freeze_message: __('Adding to schedule...'),
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: r.message.message || __('Added to schedule successfully'),
                    indicator: 'green'
                });
                
                // Redirect to schedule
                setTimeout(function() {
                    window.location.href = '/portal/schedule?name=' + scheduleId;
                }, 1000);
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: r.message.error || __('Failed to add to schedule'),
                    indicator: 'red'
                });
            }
        }
    });
}

/**
 * Show schedule selection dialog
 */
function showScheduleSelectionDialog() {
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.get_user_schedules',
        callback: function(r) {
            if (r.message && r.message.success) {
                var schedules = r.message.schedules;
                
                if (schedules.length === 0) {
                    // No schedules - offer to create one
                    showCreateScheduleDialog();
                    return;
                }
                
                // Show selection dialog
                var d = new frappe.ui.Dialog({
                    title: __('Select Schedule'),
                    fields: [
                        {
                            fieldname: 'schedule',
                            fieldtype: 'Select',
                            label: __('Schedule'),
                            reqd: 1,
                            options: schedules.map(function(s) {
                                return {
                                    value: s.name,
                                    label: s.schedule_name + ' (' + s.project_name + ')'
                                };
                            })
                        }
                    ],
                    primary_action_label: __('Add to Schedule'),
                    primary_action: function(values) {
                        WebflowConfigurator.context.schedule_name = values.schedule;
                        d.hide();
                        addToSchedule();
                    }
                });
                d.show();
            }
        }
    });
}

/**
 * Show create schedule dialog
 */
function showCreateScheduleDialog() {
    var d = new frappe.ui.Dialog({
        title: __('Create New Project'),
        fields: [
            {
                fieldname: 'project_name',
                fieldtype: 'Data',
                label: __('Project Name'),
                reqd: 1
            },
            {
                fieldname: 'schedule_name',
                fieldtype: 'Data',
                label: __('Schedule Name'),
                default: __('Main Schedule')
            }
        ],
        primary_action_label: __('Create & Add'),
        primary_action: function(values) {
            frappe.call({
                method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.create_quick_project_and_schedule',
                args: values,
                callback: function(r) {
                    if (r.message && r.message.success) {
                        WebflowConfigurator.context.schedule_name = r.message.schedule_id;
                        d.hide();
                        addToSchedule();
                    } else {
                        frappe.msgprint(r.message.error || __('Failed to create project'));
                    }
                }
            });
        }
    });
    d.show();
}

/**
 * Reset configuration
 */
function resetConfiguration() {
    frappe.confirm(
        __('Are you sure you want to reset all selections?'),
        function() {
            // Clear all selections
            WebflowConfigurator.selections = {};
            WebflowConfigurator.seriesInfo = null;
            WebflowConfigurator.options = {};
            WebflowConfigurator.isInitialized = false;
            WebflowConfigurator.lengthConfig = {};
            
            // Reset template dropdown
            $('#fixtureTemplateSelect').val('');
            $('#seriesName').text(__('Select a template...'));
            $('#seriesCode').text('');
            
            // Clear all pill selections
            $('.pill-selector .pill').removeClass('active');
            $('.pill-selector').each(function() {
                $(this).empty();
            });
            
            // Reset inputs to empty/placeholder state
            $('input[name="length_value"]').val('').attr('placeholder', '50');
            $('select[name="length_unit"]').val('inches');
            $('input[name="start_feed_length_ft"]').val('').attr('placeholder', '2');
            $('input[name="end_feed_length_ft"]').val('').attr('placeholder', '2');
            
            // Hide all sections
            hideAllSections();
            
            // Reset progress steps to initial state
            $('.progress-step').removeClass('completed active');
            $('.progress-step').each(function(index) {
                $(this).find('.step-number').text(index);
            });
            $('.progress-step[data-step="0"]').find('.step-number').text('1');
            
            // Reset UI elements
            $('#progressBadge').text('0%');
            $('#partNumberPreview').html('<span class="segment locked">ILL-XX-XX</span><span class="segment unselected">-xx-xx-xx-xx-xx-xx</span>');
            
            $('#validationMessages').hide();
            $('#pricingPreview').hide();
            $('#validationStatus').removeClass('badge-success badge-danger badge-info')
                .addClass('badge-secondary').text(__('Incomplete'));
            
            // Disable buttons
            $('#validateBtn').prop('disabled', true);
            $('#addToScheduleBtn').prop('disabled', true);
            
            // Clear summary
            $('#summaryList').hide().empty();
            $('#summaryPlaceholder').show();
        }
    );
}

/**
 * Load configuration from session
 */
function loadFromSession(sessionId) {
    frappe.call({
        method: 'illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_session',
        args: { session_id: sessionId },
        callback: function(r) {
            if (r.message && r.message.success) {
                var config = r.message.configuration || {};
                
                // Apply configuration
                for (var key in config) {
                    WebflowConfigurator.selections[key] = config[key];
                    
                    // Select pill if exists
                    var $pill = $('.pill-selector[data-field="' + key + '"] .pill[data-value="' + config[key] + '"]');
                    if ($pill.length) {
                        selectPill($pill);
                    }
                }
                
                // Set inputs
                if (config.length_inches) {
                    $('input[name="length_value"]').val(config.length_inches);
                }
                if (config.start_feed_length_ft) {
                    $('input[name="start_feed_length_ft"]').val(config.start_feed_length_ft);
                }
                if (config.end_feed_length_ft) {
                    $('input[name="end_feed_length_ft"]').val(config.end_feed_length_ft);
                }
                
                // Update UI
                updateProgress();
                updatePartNumberPreview();
                updateSummary();
                updateValidateButton();
            }
        }
    });
}

/**
 * Debounce helper
 */
function debounce(func, wait) {
    var timeout;
    return function() {
        var context = this, args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(function() {
            func.apply(context, args);
        }, wait);
    };
}
