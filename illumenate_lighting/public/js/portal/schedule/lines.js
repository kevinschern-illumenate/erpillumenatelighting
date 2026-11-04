// Schedule detail page (lines). Extracted verbatim from templates/pages/schedule.html (plan 2.1).
var schedule_name = scheduleContext.schedule_name;
// Line actions name the line by its key and the revision this page shows, so a
// change made elsewhere since loading is refused instead of hitting another line.
var scheduleModified = scheduleContext.schedule_modified;
function lineRef(line_idx) {
	var row = document.querySelector('tr[data-line-idx="' + line_idx + '"]');
	return {
		schedule_name: schedule_name,
		line_idx: line_idx,
		line_key: row ? row.getAttribute('data-line-key') : null,
		expected_modified: scheduleModified
	};
}

// Initialize Bootstrap popovers for build description
$('[data-toggle="popover"]').popover();

// Reset add line modal when opened
$('#addLineModal').on('show.bs.modal', function() {
	// Reset the form
	var kept = {};
	try {
		var draftId = sessionStorage.getItem('ill-line-draft-last:' + schedule_name);
		var stored = JSON.parse(sessionStorage.getItem('ill-line-draft:' + draftId) || 'null');
		if (stored && stored.schedule === schedule_name && Date.now() - stored.savedAt < 86400000) kept = stored.metadata;
	} catch (_) {}
	['line_id', 'location', 'qty', 'notes'].forEach(function (field) {
		var input = $('#addLineForm [name="' + field + '"]');
		if (!(field in kept)) kept[field] = input.val();
	});
	$('#addLineForm')[0].reset();
	Object.keys(kept).forEach(function (field) { $('#addLineForm [name="' + field + '"]').val(kept[field]); });
	// Reset to default ilLumenate view
	$('select[name="manufacturer_type"]').val('ILLUMENATE');
	$('.illumenate-fields').show();
	$('.other-fields').hide();
	// Reset product type and related fields
	$('#add_product_type').val('');
	$('.fixture-template-group').hide();
	$('.tape-neon-template-group').hide();
	$('.led-sheet-template-group').hide();
	$('.kit-template-group').hide();
	$('.driver-template-group').hide();
	$('.tape-neon-template-info').hide();
	$('.item-selection-group').hide();
	$('.selected-item-details').hide();
	$('.fixture-configure-section').hide();
	$('.led-sheet-configure-section').hide();
	$('.kit-configure-section').hide();
	$('.driver-configure-section').hide();
	$('#addLineUnconfiguredWarning').hide();
	$('.item-configure-section').hide();
	$('.item-direct-section').hide();
	$('.selected-variant-display').hide();
	$('#add_product_gallery_container').hide();
	resetAddLineGallery();
	$('#add_fixture_template').html('<option value="">' + scheduleText("Select Fixture Template...") + '</option>');
	$('#add_tape_neon_template').html('<option value="">' + scheduleText("Select Product Series...") + '</option>');
	$('#add_led_sheet_template').html('<option value="">' + scheduleText("Select LED Sheet Template...") + '</option>');
	$('#add_kit_template').html('<option value="">' + scheduleText("Select Extrusion Kit...") + '</option>');
	$('#add_driver_template').html('<option value="">' + scheduleText("Select Power Supply...") + '</option>');
	$('#add_selected_item').html('<option value="">' + scheduleText("Select Item...") + '</option>');
	// Reset configure button text to default
	$('#configureFromAddBtn').html('<i class="fa fa-cog" aria-hidden="true"></i> ' + scheduleText("Configure Fixture Now"));
	$('#add_selected_variant').val('');
	// Load product categories
	loadProductCategories();
});

// Toggle manufacturer type fields
$('select[name="manufacturer_type"]').on('change', function() {
	var mfgType = $(this).val();
	$('.illumenate-fields').hide();
	$('.other-fields').hide();
	
	if (mfgType === 'ILLUMENATE') {
		$('.illumenate-fields').show();
	} else if (mfgType === 'OTHER') {
		$('.other-fields').show();
	}
});

// Initialize the visibility on page load (default is ILLUMENATE)
$('.illumenate-fields').show();
$('.other-fields').hide();

// Handle product type selection to show appropriate fields
$('#add_product_type').on('change', function() {
	var productType = $(this).val();
	var $selected = $(this).find('option:selected');
	var rawIsFixtureType = $selected.data('is-fixture-type');
	var isFixtureType = rawIsFixtureType === 1 || rawIsFixtureType === '1' || rawIsFixtureType === true || rawIsFixtureType === 'true';
	var rawIsTapeNeonType = $selected.data('is-tape-neon-type');
	var isTapeNeonType = rawIsTapeNeonType === 1 || rawIsTapeNeonType === '1' || rawIsTapeNeonType === true || rawIsTapeNeonType === 'true';
	var rawIsLedSheetType = $selected.data('is-led-sheet-type');
	var isLedSheetType = rawIsLedSheetType === 1 || rawIsLedSheetType === '1' || rawIsLedSheetType === true || rawIsLedSheetType === 'true';
	var isKitType = isExtrusionKitOption($selected);
	var isPowerSupplyType = isPowerSupplyOption($selected);
	
	// Hide all conditional sections first
	$('.fixture-template-group').hide();
	$('.tape-neon-template-group').hide();
	$('.led-sheet-template-group').hide();
	$('.kit-template-group').hide();
	$('.driver-template-group').hide();
	$('.tape-neon-template-info').hide();
	$('.item-selection-group').hide();
	$('.selected-item-details').hide();
	$('.fixture-configure-section').hide();
	$('.led-sheet-configure-section').hide();
	$('.kit-configure-section').hide();
	$('.driver-configure-section').hide();
	$('#addLineUnconfiguredWarning').hide();
	$('.item-configure-section').hide();
	$('.item-direct-section').hide();
	$('.selected-variant-display').hide();
	$('#add_selected_variant').val('');
	$('#add_product_gallery_container').hide();
	resetAddLineGallery();
	// Reset configure button text to default
	$('#configureFromAddBtn').html('<i class="fa fa-cog" aria-hidden="true"></i> ' + scheduleText("Configure Fixture Now"));
	
	if (!productType) {
		return;
	}
	
	// Check if this is a fixture type (e.g., "Linear Fixture") - show fixture template dropdown
	if (isFixtureType) {
		$('.fixture-template-group').show();
		$('.fixture-configure-section').show();
		loadFixtureTemplates(productType);
	} else if (isTapeNeonType) {
		// LED Tape / COB Tape / LED Neon — show tape/neon template dropdown + configure section
		$('.tape-neon-template-group').show();
		$('.fixture-configure-section').show();
		loadTapeNeonTemplates(productType);
		// Update configure button text for the tape/neon category
		$('#configureFromAddBtn').html('<i class="fa fa-cog" aria-hidden="true"></i> ' + configureTapeNeonLabel(tapeNeonCategoryOf($selected)));
	} else if (isLedSheetType) {
		// LED Sheet — show LED Sheet template dropdown + configure section
		$('.led-sheet-template-group').show();
		$('.led-sheet-configure-section').show();
		loadLedSheetTemplates(productType);
	} else if (isKitType) {
		// Extrusion Kits — pick a kit template, then configure it like tape/neon
		$('.kit-template-group').show();
		$('.kit-configure-section').show();
		loadExtrusionKitTemplates();
	} else if (isPowerSupplyType) {
		// Power Supplies — pick a power supply template, then configure it like kits
		$('.driver-template-group').show();
		$('.driver-configure-section').show();
		loadDriverTemplates();
	} else {
		// For all other product types, show item selection dropdown
		$('.item-selection-group').show();
		loadItemsForProductType(productType);
	}
});

// Load fixture templates from the server
function loadFixtureTemplates(productType) {
	$('#add_fixture_template').html('<option value="">' + scheduleText("Loading...") + '</option>');
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_fixture_templates',
		args: {
			product_type: productType
		},
		callback: function(r) {
			var options = '<option value="">' + scheduleText("Select Fixture Template...") + '</option>';
			var templates = (r.message && r.message.templates) || [];
			templates.forEach(function(template) {
				var galleryAttr = template.gallery ? JSON.stringify(template.gallery) : '[]';
				var h = PortalUI.escape;
				options += '<option value="' + h(template.name) + '" data-image="' + h(template.image || '') + '" data-gallery="' + h(galleryAttr) + '">' + h(template.template_name) + ' (' + h(template.template_code) + ')</option>';
			});
			$('#add_fixture_template').html(options);
			renderLinearFixturePicker($('#add_fixture_template'), $('#add_fixture_template_cards'), templates);
		},
		error: function() {
			$('#add_fixture_template').html('<option value="">' + scheduleText("Error loading templates") + '</option>');
		}
	});
}

// Series code of a fixture template code: "ILL-SH02-SW" -> "ILL-SH02".
// Codes without a finish suffix form a series of their own.
function linearSeriesCode(code) {
	var parts = String(code || '').split('-');
	return parts.length > 2 ? parts.slice(0, 2).join('-') : String(code || '');
}

// Family label from a template name, up to and including the first "]":
// "St. Helens [SF] Static White" -> "St. Helens [SF]".
function linearFamilyName(templateName) {
	var name = String(templateName || '');
	var end = name.indexOf(']');
	return end === -1 ? name.trim() : name.slice(0, end + 1).trim();
}

// Two-step Linear Fixture picker for the Add Line modal: series families as
// image cards, then a plain list of that series' templates. The hidden
// #add_fixture_template select stays the source of truth.
function renderLinearFixturePicker($select, $container, templates) {
	var ns = '.illLinearPicker';
	var esc = frappe.utils.escape_html;
	var families = [];
	var bySeries = {};
	templates.forEach(function(t) {
		var series = linearSeriesCode(t.template_code);
		if (!bySeries[series]) {
			bySeries[series] = { series: series, name: linearFamilyName(t.template_name), templates: [] };
			families.push(bySeries[series]);
		}
		bySeries[series].templates.push(t);
	});
	families.forEach(function(f) {
		var withImage = f.templates.find(function(t) { return t.image; });
		f.image = withImage ? withImage.image : '';
	});
	// Product line name first, then series code (St. Helens SH01, SH02, SH03).
	families.sort(function(a, b) {
		var baseA = a.name.split('[')[0].trim().toLowerCase();
		var baseB = b.name.split('[')[0].trim().toLowerCase();
		if (baseA !== baseB) return baseA < baseB ? -1 : 1;
		return a.series < b.series ? -1 : (a.series > b.series ? 1 : 0);
	});

	var state = { series: null };

	function templateByValue(value) {
		return templates.find(function(t) { return t.name === value; });
	}
	function media(f) {
		return f.image
			? '<img src="' + esc(f.image) + '" alt="' + esc(f.name) + '" loading="lazy">'
			: '<span class="ill-linear-placeholder" aria-hidden="true"><i class="fa fa-lightbulb-o" aria-hidden="true"></i></span>';
	}
	function optionCount(f) {
		return f.templates.length === 1 ? __('1 option') : __('{0} options', [f.templates.length]);
	}

	function renderFamilies() {
		var q = ($container.find('.ill-linear-search').val() || '').toLowerCase().trim();
		var shown = families.filter(function(f) {
			if (!q) return true;
			var haystack = f.name + ' ' + f.series + ' ' + f.templates.map(function(t) {
				return t.template_name + ' ' + t.template_code;
			}).join(' ');
			return haystack.toLowerCase().indexOf(q) !== -1;
		});
		$container.find('.ill-linear-count').text(shown.length === families.length
			? __('{0} fixtures', [families.length])
			: __('{0} of {1} fixtures', [shown.length, families.length]));
		$container.find('.ill-linear-grid').html(shown.length ? shown.map(function(f) {
			return '<button type="button" class="ill-linear-family" data-series="' + esc(f.series) + '">'
				+ '<span class="ill-linear-family-media">' + media(f) + '</span>'
				+ '<span class="ill-linear-family-body">'
				+ '<span class="ill-linear-family-name">' + esc(f.name) + '</span>'
				+ '<span class="ill-linear-family-meta">'
				+ '<span class="ill-linear-code">' + esc(f.series) + '</span>'
				+ '<span class="ill-linear-family-count">' + esc(optionCount(f)) + ' <i class="fa fa-angle-right" aria-hidden="true"></i></span>'
				+ '</span></span></button>';
		}).join('') : '<div class="ill-linear-empty"><i class="fa fa-search" aria-hidden="true"></i>' + esc(__('No fixtures match your search.')) + '</div>');
	}

	function renderSeries() {
		var f = bySeries[state.series];
		var current = $select.val();
		$container.find('.ill-linear-series-head').html(
			'<span class="ill-linear-thumb">' + media(f) + '</span>'
			+ '<span class="ill-linear-head-text">'
			+ '<span class="ill-linear-eyebrow">' + esc(__('Choose an option')) + '</span>'
			+ '<span class="ill-linear-head-name">' + esc(f.name) + '</span>'
			+ '<span class="ill-linear-code">' + esc(f.series) + '</span>'
			+ '</span>'
		);
		$container.find('.ill-linear-options').html(f.templates.map(function(t) {
			var active = t.name === current;
			return '<button type="button" class="ill-linear-option' + (active ? ' selected' : '')
				+ '" aria-pressed="' + (active ? 'true' : 'false') + '" data-value="' + esc(t.name) + '">'
				+ '<span class="ill-linear-radio" aria-hidden="true"></span>'
				+ '<span class="ill-linear-option-name">' + esc(t.template_name) + '</span>'
				+ '<span class="ill-linear-code">' + esc(t.template_code) + '</span>'
				+ '</button>';
		}).join(''));
	}

	function sync() {
		var t = templateByValue($select.val());
		var $families = $container.find('.ill-linear-families');
		var $series = $container.find('.ill-linear-series');
		var $selected = $container.find('.ill-linear-selected');
		if (t) {
			var f = bySeries[linearSeriesCode(t.template_code)];
			state.series = f.series;
			$selected.html(
				'<span class="ill-linear-thumb">' + media(f) + '</span>'
				+ '<span class="ill-linear-head-text">'
				+ '<span class="ill-linear-eyebrow"><i class="fa fa-check-circle" aria-hidden="true"></i> ' + esc(__('Selected fixture')) + '</span>'
				+ '<span class="ill-linear-head-name">' + esc(t.template_name) + '</span>'
				+ '<span class="ill-linear-code">' + esc(t.template_code) + '</span>'
				+ '</span>'
				+ '<button type="button" class="ill-linear-btn ill-linear-change"><i class="fa fa-pencil" aria-hidden="true"></i> ' + esc(__('Change')) + '</button>'
			).show();
			$families.hide();
			$series.hide();
		} else if (state.series && bySeries[state.series]) {
			$selected.hide();
			$families.hide();
			renderSeries();
			$series.show();
		} else {
			state.series = null;
			$selected.hide();
			$series.hide();
			renderFamilies();
			$families.show();
		}
	}

	$container.off(ns).addClass('ill-linear-picker').html(
		'<div class="ill-linear-families">'
		+ '<div class="ill-linear-toolbar">'
		+ '<span class="ill-linear-search-wrap"><i class="fa fa-search" aria-hidden="true"></i>'
		+ '<input type="search" class="ill-linear-search" placeholder="' + esc(__('Search fixtures...')) + '" aria-label="' + esc(__('Search fixtures...')) + '"></span>'
		+ '<span class="ill-linear-count" role="status" aria-live="polite"></span>'
		+ '</div>'
		+ '<div class="ill-linear-grid"></div>'
		+ '</div>'
		+ '<div class="ill-linear-series" style="display:none;">'
		+ '<div class="ill-linear-panel-head">'
		+ '<div class="ill-linear-series-head"></div>'
		+ '<button type="button" class="ill-linear-btn ill-linear-back"><i class="fa fa-th-large" aria-hidden="true"></i> ' + esc(__('All fixtures')) + '</button>'
		+ '</div>'
		+ '<div class="ill-linear-options"></div>'
		+ '</div>'
		+ '<div class="ill-linear-selected" style="display:none;"></div>'
	);
	$select.addClass('ill-template-select-driven').off(ns).on('change' + ns, sync);

	$container.on('input' + ns, '.ill-linear-search', renderFamilies);
	$container.on('click' + ns, '.ill-linear-family', function() {
		state.series = $(this).attr('data-series');
		sync();
		$container.find('.ill-linear-option').first().trigger('focus');
	});
	$container.on('click' + ns, '.ill-linear-option', function() {
		$select.val($(this).attr('data-value')).trigger('change');
	});
	$container.on('click' + ns, '.ill-linear-back', function() {
		state.series = null;
		$select.val('').trigger('change');
	});
	$container.on('click' + ns, '.ill-linear-change', function() {
		// Back to the same series so a different finish is one click away
		$select.val('').trigger('change');
	});
	if (!$container.data('illLinearImageFallback')) {
		// Image errors don't bubble, so listen in the capture phase (once per container)
		$container[0].addEventListener('error', function(event) {
			if (event.target.tagName === 'IMG') $(event.target).replaceWith('<span class="ill-linear-placeholder"><i class="fa fa-lightbulb-o" aria-hidden="true"></i></span>');
		}, true);
		$container.data('illLinearImageFallback', true);
	}

	sync();
}

// Count line for the shared product pickers in the Add Line modal ("12 products").
function addLinePickerCount(shown, total) {
	return shown === total ? __('{0} products', [total]) : __('{0} of {1} products', [shown, total]);
}

// Template category (LED Tape, COB Tape or LED Neon) of a Product Category option.
// The server names it; older payloads fall back to the group's label.
function tapeNeonCategoryOf($option) {
	var category = $option.data('tape-neon-category');
	if (category) return category;
	var label = ($option.text() || '').trim().toLowerCase();
	if (label.indexOf('neon') !== -1) return 'LED Neon';
	if (label.indexOf('cob') !== -1) return 'COB Tape';
	return 'LED Tape';
}

function configureTapeNeonLabel(category) {
	if (category === 'LED Neon') return scheduleText("Configure LED Neon Now");
	if (category === 'COB Tape') return scheduleText("Configure COB Tape Now");
	return scheduleText("Configure LED Tape Now");
}

// Load tape/neon templates from the server
function loadTapeNeonTemplates(productType) {
	var productCategory = tapeNeonCategoryOf($('#add_product_type option:selected'));

	$('#add_tape_neon_template').html('<option value="">' + scheduleText("Loading...") + '</option>');
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_tape_neon_templates_for_schedule',
		args: {
			product_category: productCategory
		},
		callback: function(r) {
			var options = '<option value="">' + scheduleText("Select Product Series...") + '</option>';
			if (r.message && r.message.templates) {
				r.message.templates.forEach(function(template) {
					var galleryAttr = template.gallery ? JSON.stringify(template.gallery) : '[]';
					var h = PortalUI.escape;
					options += '<option value="' + h(template.name) + '" data-template-code="' + h(template.template_code || '') + '" data-image="' + h(template.image || '') + '" data-gallery="' + h(galleryAttr) + '" data-category="' + h(productCategory) + '" data-description="' + h(template.description || '') + '">' + h(template.template_name) + ' (' + h(template.template_code) + ')</option>';
				});
			}
			$('#add_tape_neon_template').html(options);
			IllConfigurator.renderTemplateCards({ $select: $('#add_tape_neon_template'), $container: $('#add_tape_neon_template_cards'), labels: { search: __('Search products...'), empty: __('No products match your search.'), count: addLinePickerCount } });
		},
		error: function() {
			$('#add_tape_neon_template').html('<option value="">' + scheduleText("Error loading series") + '</option>');
		}
	});
}

// Load LED Sheet templates from the server
function loadLedSheetTemplates(productType) {
	$('#add_led_sheet_template').html('<option value="">' + scheduleText("Loading...") + '</option>');

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_led_sheet_templates',
		callback: function(r) {
			var options = '<option value="">' + scheduleText("Select LED Sheet Template...") + '</option>';
			if (r.message && r.message.templates) {
				r.message.templates.forEach(function(template) {
					var label = template.template_name + (template.template_code ? ' (' + template.template_code + ')' : '');
					options += '<option value="' + PortalUI.escape(template.name) + '">' + PortalUI.escape(label) + '</option>';
				});
			}
			$('#add_led_sheet_template').html(options);
			IllConfigurator.renderTemplateCards({ $select: $('#add_led_sheet_template'), $container: $('#add_led_sheet_template_cards'), labels: { search: __('Search products...'), empty: __('No products match your search.'), count: addLinePickerCount } });
		},
		error: function() {
			$('#add_led_sheet_template').html('<option value="">' + scheduleText("Error loading templates") + '</option>');
		}
	});
}

// Extrusion Kits groups pick an ilL-Extrusion-Kit-Template; the server flags them,
// older payloads fall back to the group's label.
function isExtrusionKitOption($option) {
	var flag = $option.data('is-extrusion-kit-type');
	if (flag !== undefined) return [1, '1', true, 'true'].includes(flag);
	return ($option.text() || '').replace(/[└─]/g, '').trim().toLowerCase().indexOf('extrusion kit') === 0;
}

// Load Extrusion Kit templates from the server
function loadExtrusionKitTemplates() {
	var $select = $('#add_kit_template');
	$select.html('<option value="">' + scheduleText("Loading...") + '</option>');
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_extrusion_kit_templates_for_schedule',
		callback: function(r) {
			$select.html('<option value="">' + scheduleText("Select Extrusion Kit...") + '</option>');
			((r.message && r.message.templates) || []).forEach(function(template) {
				$('<option>').val(template.name)
					.text(template.template_name + (template.template_code ? ' (' + template.template_code + ')' : ''))
					.attr('data-name', template.template_name)
					.attr('data-image', template.image || '')
					.attr('data-gallery', JSON.stringify(template.gallery || []))
					.attr('data-description', template.description || '')
					.appendTo($select);
			});
			IllConfigurator.renderTemplateCards({ $select: $select, $container: $('#add_kit_template_cards'), labels: { search: __('Search products...'), empty: __('No products match your search.'), count: addLinePickerCount } });
		},
		error: function() {
			$select.html('<option value="">' + scheduleText("Error loading kits") + '</option>');
		}
	});
}

$('#add_kit_template').on('change', function() {
	var gallery = [];
	try { gallery = JSON.parse($(this).find('option:selected').attr('data-gallery') || '[]'); } catch (_) {}
	initAddLineGallery(gallery);
});

// Power Supplies groups pick an ilL-Driver-Template; the server flags them,
// older payloads fall back to the group's label.
function isPowerSupplyOption($option) {
	var flag = $option.data('is-power-supply-type');
	if (flag !== undefined) return [1, '1', true, 'true'].includes(flag);
	var label = ($option.text() || '').replace(/[└─]/g, '').trim().toLowerCase();
	return label.indexOf('power suppl') === 0 || label.indexOf('driver') === 0;
}

// Load power supply (driver) templates from the server
function loadDriverTemplates() {
	var $select = $('#add_driver_template');
	$select.html('<option value="">' + scheduleText("Loading...") + '</option>');
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_driver_templates_for_schedule',
		callback: function(r) {
			$select.html('<option value="">' + scheduleText("Select Power Supply...") + '</option>');
			((r.message && r.message.templates) || []).forEach(function(template) {
				$('<option>').val(template.name)
					.text(template.template_name + (template.template_code && template.template_code !== template.template_name ? ' (' + template.template_code + ')' : ''))
					.attr('data-name', template.template_name)
					.attr('data-image', template.image || '')
					.attr('data-gallery', JSON.stringify(template.gallery || []))
					.attr('data-description', template.description || '')
					.appendTo($select);
			});
			IllConfigurator.renderTemplateCards({ $select: $select, $container: $('#add_driver_template_cards'), labels: { search: __('Search products...'), empty: __('No products match your search.'), count: addLinePickerCount } });
		},
		error: function() {
			$select.html('<option value="">' + scheduleText("Error loading power supplies") + '</option>');
		}
	});
}

$('#add_driver_template').on('change', function() {
	var gallery = [];
	try { gallery = JSON.parse($(this).find('option:selected').attr('data-gallery') || '[]'); } catch (_) {}
	initAddLineGallery(gallery);
});

// Handle tape/neon template selection to show product image gallery and template info
$('#add_tape_neon_template').on('change', function() {
	var $selected = $(this).find('option:selected');
	var gallery = $selected.data('gallery') || [];
	var templateName = $selected.text().trim();
	var category = $selected.data('category') || '';
	var description = $selected.data('description') || '';
	initAddLineGallery(gallery);

	// Show/hide tape-neon template info section
	if ($(this).val()) {
		$('.tape-neon-template-info').show();
		$('#tape_neon_info_name').text(templateName);
		$('#tape_neon_info_category').text(category || 'LED Tape');
		if (description) {
			$('#tape_neon_info_desc').text(description).show();
		} else {
			$('#tape_neon_info_desc').hide();
		}
		// Update configure button text based on category
		$('#configureFromAddBtn').html('<i class="fa fa-cog" aria-hidden="true"></i> ' + configureTapeNeonLabel(category));
	} else {
		$('.tape-neon-template-info').hide();
	}
});

// ─── Add Line Gallery + Zoom/Pan ───
var _addLineGallery = { images: [], index: 0, zoom: 1, panX: 0, panY: 0, dragging: false, startX: 0, startY: 0 };

function initAddLineGallery(images) {
	_addLineGallery.images = (images && images.length) ? images : [];
	_addLineGallery.index = 0;
	resetAddLineZoomPan();
	if (_addLineGallery.images.length) {
		showAddLineGalleryImage();
		$('#add_product_gallery_container').show();
		updateAddLineGalleryNav();
	} else {
		$('#add_product_gallery_container').hide();
	}
}

function resetAddLineGallery() {
	_addLineGallery.images = [];
	_addLineGallery.index = 0;
	resetAddLineZoomPan();
}

function showAddLineGalleryImage() {
	var item = _addLineGallery.images[_addLineGallery.index];
	if (!item) return;
	$('#addLineGalleryImage').attr('src', item.image).attr('alt', item.alt_text || 'Product image');
	applyAddLineTransform();
	$('#addLineGalleryCounter').text((_addLineGallery.index + 1) + ' / ' + _addLineGallery.images.length);
	$('#addLineGalleryCounter').toggle(_addLineGallery.images.length > 1);
}

function updateAddLineGalleryNav() {
	var multi = _addLineGallery.images.length > 1;
	$('#addLineGalleryPrev').toggle(multi).toggleClass('disabled', _addLineGallery.index === 0);
	$('#addLineGalleryNext').toggle(multi).toggleClass('disabled', _addLineGallery.index >= _addLineGallery.images.length - 1);
}

function applyAddLineTransform() {
	var z = _addLineGallery.zoom;
	var tx = _addLineGallery.panX;
	var ty = _addLineGallery.panY;
	$('#addLineGalleryImage').css('transform', 'scale(' + z + ') translate(' + tx + 'px, ' + ty + 'px)');
}

function resetAddLineZoomPan() {
	_addLineGallery.zoom = 1;
	_addLineGallery.panX = 0;
	_addLineGallery.panY = 0;
	$('#addLineZoomSlider').val(100);
	$('#addLineZoomValue').text('100%');
	applyAddLineTransform();
}

// Arrow click handlers
$(document).on('click', '#addLineGalleryPrev', function() {
	if (_addLineGallery.index > 0) {
		_addLineGallery.index--;
		resetAddLineZoomPan();
		showAddLineGalleryImage();
		updateAddLineGalleryNav();
	}
});
$(document).on('click', '#addLineGalleryNext', function() {
	if (_addLineGallery.index < _addLineGallery.images.length - 1) {
		_addLineGallery.index++;
		resetAddLineZoomPan();
		showAddLineGalleryImage();
		updateAddLineGalleryNav();
	}
});

// Zoom slider
$(document).on('input', '#addLineZoomSlider', function() {
	var val = parseInt($(this).val(), 10);
	_addLineGallery.zoom = val / 100;
	if (_addLineGallery.zoom <= 1) { _addLineGallery.panX = 0; _addLineGallery.panY = 0; }
	$('#addLineZoomValue').text(val + '%');
	applyAddLineTransform();
});
$(document).on('click', '#addLineZoomReset', function() {
	resetAddLineZoomPan();
});

// Pan (mouse / touch drag)
(function() {
	var vp = document.getElementById('addLineGalleryViewport');
	if (!vp) return;

	function onPointerDown(e) {
		if (_addLineGallery.zoom <= 1) return;
		_addLineGallery.dragging = true;
		_addLineGallery.startX = (e.touches ? e.touches[0].clientX : e.clientX) - _addLineGallery.panX;
		_addLineGallery.startY = (e.touches ? e.touches[0].clientY : e.clientY) - _addLineGallery.panY;
		$(vp).addClass('is-dragging');
		e.preventDefault();
	}
	function onPointerMove(e) {
		if (!_addLineGallery.dragging) return;
		var cx = e.touches ? e.touches[0].clientX : e.clientX;
		var cy = e.touches ? e.touches[0].clientY : e.clientY;
		_addLineGallery.panX = cx - _addLineGallery.startX;
		_addLineGallery.panY = cy - _addLineGallery.startY;
		applyAddLineTransform();
		e.preventDefault();
	}
	function onPointerUp() {
		_addLineGallery.dragging = false;
		$(vp).removeClass('is-dragging');
	}

	vp.addEventListener('mousedown', onPointerDown);
	vp.addEventListener('touchstart', onPointerDown, { passive: false });
	document.addEventListener('mousemove', onPointerMove);
	document.addEventListener('touchmove', onPointerMove, { passive: false });
	document.addEventListener('mouseup', onPointerUp);
	document.addEventListener('touchend', onPointerUp);
})();

// Handle fixture template selection to show product image gallery
$('#add_fixture_template').on('change', function() {
	var $selected = $(this).find('option:selected');
	var gallery = $selected.data('gallery') || [];
	initAddLineGallery(gallery);
});

// Load product categories (Item Groups under Products and Raw Materials)
function loadProductCategories() {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_product_types',
		callback: function(r) {
			var options = '<option value="">' + scheduleText("Select Product Category...") + '</option>';
			if (r.message && r.message.success && r.message.product_types) {
				var currentHeader = null;
				r.message.product_types.forEach(function(pt) {
					if (pt.is_header) {
						// Render as a disabled optgroup-style header
						options += '<option value="" disabled class="ill-option-group">── ' + PortalUI.escape(pt.label) + ' ──</option>';
						currentHeader = pt.label;
						return;
					}
					// Add visual indentation based on level
					var indent = '';
					if (pt.level === 0) {
						indent = '  ';
					} else if (pt.level === 1) {
						indent = '    └─ ';
					} else if (pt.level === 2) {
						indent = '        └─ ';
					}
					// Store is_fixture_type, is_tape_neon_type, tape_neon_category, is_led_sheet_type as data attributes
					options += '<option value="' + PortalUI.escape(pt.value) + '" data-is-fixture-type="' + (pt.is_fixture_type ? '1' : '0') + '" data-is-tape-neon-type="' + (pt.is_tape_neon_type ? '1' : '0') + '" data-tape-neon-category="' + PortalUI.escape(pt.tape_neon_category || '') + '" data-is-led-sheet-type="' + (pt.is_led_sheet_type ? '1' : '0') + '" data-is-extrusion-kit-type="' + (pt.is_extrusion_kit_type ? '1' : '0') + '" data-is-power-supply-type="' + (pt.is_power_supply_type ? '1' : '0') + '" data-root-group="' + PortalUI.escape(pt.root_group || '') + '">' + indent + PortalUI.escape(pt.label) + '</option>';
				});
			}
			$('#add_product_type').html(options);
		},
		error: function(err) {
			// Silent error - options just won't load
		}
	});
}

// Load items for a product type (excluding variants)
function loadItemsForProductType(productType) {
	$('#add_selected_item').html('<option value="">' + scheduleText("Loading...") + '</option>');
	
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_items_by_product_type',
		args: {
			product_type: productType,
			exclude_variants: 1
		},
		callback: function(r) {
			var options = '<option value="">' + scheduleText("Select Item...") + '</option>';
			if (r.message && r.message.success && r.message.items) {
				r.message.items.forEach(function(item) {
					// Strip HTML tags from description for safe use in data attribute
					var cleanDesc = (item.description || '').replace(/<[^>]*>/g, '').substring(0, 100);
					var h = PortalUI.escape;
					options += '<option value="' + h(item.item_code) + '" ' +
						'data-name="' + h(item.item_name || '') + '" ' +
						'data-desc="' + h(cleanDesc) + '" ' +
						'data-uom="' + h(item.stock_uom || 'Nos') + '" ' +
						'data-rate="' + h(item.standard_rate || 0) + '" ' +
						'data-has-variants="' + (item.has_variants ? '1' : '0') + '" ' +
						'data-image="' + h(item.image || '') + '">' +
						h(item.item_name) + ' (' + h(item.item_code) + ')' +
						(item.has_variants ? ' ⚙' : '') +
						'</option>';
				});
			}
			$('#add_selected_item').html(options);
			IllConfigurator.renderTemplateCards({ $select: $('#add_selected_item'), $container: $('#add_selected_item_cards'), labels: { search: __('Search products...'), empty: __('No products match your search.'), count: addLinePickerCount } });
		},
		error: function() {
			$('#add_selected_item').html('<option value="">' + scheduleText("Error loading items") + '</option>');
		}
	});
}

// Handle item selection
$('#add_selected_item').on('change', function() {
	var $selected = $(this).find('option:selected');
	var itemCode = $(this).val();
	
	// Hide all item-related sections first
	$('.selected-item-details').hide();
	$('.item-configure-section').hide();
	$('.item-direct-section').hide();
	$('.selected-variant-display').hide();
	$('#add_selected_variant').val('');
	$('#add_product_gallery_container').hide();
	resetAddLineGallery();
	
	if (!itemCode) {
		return;
	}
	
	// Show item details
	$('#add_selected_item_name').text($selected.data('name') || itemCode);
	$('#add_selected_item_desc').text($selected.data('desc') || '');
	$('#add_selected_item_uom').text($selected.data('uom') || 'Nos');
	$('.selected-item-details').show();

	// Show product image gallery if available
	var imageUrl = $selected.data('image');
	if (imageUrl) {
		// Items only have a single image, wrap in gallery format
		initAddLineGallery([{image: imageUrl, alt_text: ''}]);
	}
	
	// Check if item has variants
	var hasVariants = $selected.data('has-variants') === '1' || $selected.data('has-variants') === 1;
	
	if (hasVariants) {
		// Show badge and configure button
		$('#add_selected_item_has_variants').show();
		$('.item-configure-section').show();
	} else {
		// No variants - direct add
		$('#add_selected_item_has_variants').hide();
		$('.item-direct-section').show();
	}
});

// Store current template item for variant selection
var currentTemplateItem = null;
var currentVariantMatch = null;

// Open item variant configuration modal
function openItemVariantModal() {
	var itemCode = $('#add_selected_item').val();
	var $selected = $('#add_selected_item option:selected');
	
	if (!itemCode) {
		frappe.msgprint({
			title: scheduleText("Selection Required"),
			indicator: 'orange',
			message: scheduleText("Please select an item first.")
		});
		return;
	}
	
	currentTemplateItem = itemCode;
	currentVariantMatch = null;
	
	// Show loading state
	$('.variant-config-loading').show();
	$('.variant-config-content').hide();
	$('#confirmVariantBtn').prop('disabled', true);
	$('.variant-match-status').hide();
	
	// Set template name in modal
	$('#variant_template_name').text($selected.data('name') || itemCode);
	
	// Open modal
	$('#itemVariantModal').modal('show');
	
	// Load variant attributes
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_item_variant_attributes',
		args: {
			template_item: itemCode
		},
		callback: function(r) {
			$('.variant-config-loading').hide();
			$('.variant-config-content').show();
			
			if (r.message && r.message.success && r.message.attributes && r.message.attributes.length > 0) {
				// Build attribute dropdowns
				var html = '';
				r.message.attributes.forEach(function(attr, index) {
					html += '<div class="form-group">';
					html += '<label for="variant_attr_' + index + '">' + PortalUI.escape(attr.attribute) + '</label>';
					html += '<select id="variant_attr_' + index + '" class="form-control variant-attribute-select" data-attribute="' + PortalUI.escape(attr.attribute) + '">';
					html += '<option value="">' + scheduleText("Select") + ' ' + PortalUI.escape(attr.attribute) + '...</option>';
					attr.values.forEach(function(val) {
						if (val.is_numeric) {
							html += '<option value="' + PortalUI.escape(val.value) + '">' + PortalUI.escape(val.value) + '</option>';
						} else {
							html += '<option value="' + PortalUI.escape(val.value) + '">' + PortalUI.escape(val.value) + '</option>';
						}
					});
					html += '</select>';
					html += '</div>';
				});
				$('#variant_attributes_container').html(html);
				
				// Add change handler to check for matching variants
				$('.variant-attribute-select').on('change', checkVariantMatch);
			} else {
				$('#variant_attributes_container').html('<div class="alert alert-warning">' + scheduleText("No configurable options available for this item.") + '</div>');
			}
		},
		error: function() {
			$('.variant-config-loading').hide();
			$('.variant-config-content').show();
			$('#variant_attributes_container').html('<div class="alert alert-danger">' + scheduleText("Error loading options. Please try again.") + '</div>');
		}
	});
}

// Collect all selected attribute values from variant dropdowns
function collectSelectedAttributes() {
	var result = {attributes: {}, allSelected: true};
	$('.variant-attribute-select').each(function() {
		var attr = $(this).data('attribute');
		var val = $(this).val();
		if (val) {
			result.attributes[attr] = val;
		} else {
			result.allSelected = false;
		}
	});
	return result;
}

// Try to find a matching variant after all attributes are selected
function findMatchingVariant(selectedAttributes) {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.find_matching_variant',
		args: {
			template_item: currentTemplateItem,
			selected_attributes: selectedAttributes
		},
		callback: function(r) {
			$('.variant-match-status').show();
			
			if (r.message && r.message.success && r.message.found) {
				// Match found
				$('.variant-found').show();
				$('.variant-not-found').hide();
				$('#matched_variant_name').text(r.message.variant.item_name + ' (' + r.message.variant.item_code + ')');
				$('#confirmVariantBtn').prop('disabled', false);
				currentVariantMatch = r.message.variant;
			} else {
				// No match
				$('.variant-found').hide();
				$('.variant-not-found').show();
				$('#confirmVariantBtn').prop('disabled', true);
				currentVariantMatch = null;
			}
		}
	});
}

// Check if selected attributes match a variant and filter remaining dropdowns
function checkVariantMatch() {
	var collected = collectSelectedAttributes();
	var selectedAttributes = collected.attributes;
	
	// Filter remaining dropdowns based on current selections
	if (Object.keys(selectedAttributes).length > 0) {
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_filtered_variant_attributes',
			args: {
				template_item: currentTemplateItem,
				selected_attributes: selectedAttributes
			},
			callback: function(r) {
				if (r.message && r.message.success && r.message.attributes) {
					r.message.attributes.forEach(function(attr) {
						var $select = $('.variant-attribute-select[data-attribute="' + attr.attribute + '"]');
						var currentVal = $select.val();
						var validValues = attr.values.map(function(v) { return v.value; });
						
						// Rebuild options preserving current selection
						var opts = '<option value="">' + scheduleText("Select") + ' ' + attr.attribute + '...</option>';
						attr.values.forEach(function(val) {
							var selected = (val.value === currentVal) ? ' selected' : '';
							opts += '<option value="' + PortalUI.escape(val.value) + '"' + selected + '>' + PortalUI.escape(val.value) + '</option>';
						});
						$select.html(opts);
						
						// If current value is no longer valid, reset it
						if (currentVal && validValues.indexOf(currentVal) === -1) {
							$select.val('');
						}
					});
				}
				
				// After filtering, re-check if all are selected and find match
				var updated = collectSelectedAttributes();
				if (!updated.allSelected) {
					$('.variant-match-status').hide();
					$('#confirmVariantBtn').prop('disabled', true);
					currentVariantMatch = null;
					return;
				}
				findMatchingVariant(updated.attributes);
			}
		});
	} else {
		// Nothing selected yet
		$('.variant-match-status').hide();
		$('#confirmVariantBtn').prop('disabled', true);
		currentVariantMatch = null;
	}
}

// Confirm variant selection
function confirmVariantSelection() {
	if (!currentVariantMatch) {
		frappe.msgprint({
			title: scheduleText("No Match"),
			indicator: 'orange',
			message: scheduleText("Please select options that match an available variant.")
		});
		return;
	}
	
	// Store the selected variant
	$('#add_selected_variant').val(currentVariantMatch.item_code);
	
	// Update the display
	$('#selected_variant_name').text(currentVariantMatch.item_name + ' (' + currentVariantMatch.item_code + ')');
	$('.selected-variant-display').show();
	
	// Close modal
	$('#itemVariantModal').modal('hide');
}


function addLine() {
	var form = $('#addLineForm');
	var manufacturerType = form.find('[name="manufacturer_type"]').val();
	var productType = form.find('[name="product_type"]').val();
	var $productTypeSelected = form.find('[name="product_type"] option:selected');
	var rawIsFixtureType = $productTypeSelected.data('is-fixture-type');
	var isFixtureType = rawIsFixtureType === 1 || rawIsFixtureType === '1' || rawIsFixtureType === true || rawIsFixtureType === 'true';
	var rawIsTapeNeonType = $productTypeSelected.data('is-tape-neon-type');
	var isTapeNeonType = rawIsTapeNeonType === 1 || rawIsTapeNeonType === '1' || rawIsTapeNeonType === true || rawIsTapeNeonType === 'true';
	var rawIsLedSheetType = $productTypeSelected.data('is-led-sheet-type');
	var isLedSheetType = rawIsLedSheetType === 1 || rawIsLedSheetType === '1' || rawIsLedSheetType === true || rawIsLedSheetType === 'true';
	var isKitType = isExtrusionKitOption($productTypeSelected);
	var isPowerSupplyType = isPowerSupplyOption($productTypeSelected);
	
	var data = {
		line_id: form.find('[name="line_id"]').val(),
		qty: form.find('[name="qty"]').val(),
		location: form.find('[name="location"]').val(),
		manufacturer_type: manufacturerType,
		notes: form.find('[name="notes"]').val()
	};

	// Handle ilLumenate products
	if (manufacturerType === 'ILLUMENATE') {
		data.product_type = productType;
		
		// Check if this is a linear fixture type using the data attribute
		if (isFixtureType) {
			// Linear Fixture path - uses fixture template and configurator
			data.fixture_template = form.find('[name="fixture_template"]').val();
			data.configuration_status = 'Pending';
		} else if (isTapeNeonType) {
			// LED Tape / COB Tape / LED Neon path - uses tape/neon template and configurator
			var tapeNeonTemplate = form.find('[name="tape_neon_template"]').val();
			if (!tapeNeonTemplate) {
				frappe.msgprint({
					title: scheduleText("Selection Required"),
					indicator: 'orange',
					message: scheduleText("Please select a Product Series before adding the line.")
				});
				return;
			}
			data.tape_neon_template = tapeNeonTemplate;
			data.configuration_status = 'Pending';
		} else if (isLedSheetType) {
			// LED Sheet path - uses LED Sheet template and configurator
			var ledSheetTemplate = form.find('[name="led_sheet_template"]').val();
			if (!ledSheetTemplate) {
				frappe.msgprint({
					title: scheduleText("Selection Required"),
					indicator: 'orange',
					message: scheduleText("Please select an LED Sheet Template before adding the line.")
				});
				return;
			}
			data.product_type = 'LED Sheet';
			data.led_sheet_template = ledSheetTemplate;
			data.configuration_status = 'Pending';
		} else if (isKitType) {
			// Extrusion Kit path - uses the kit template and the kit configurator
			var kitTemplate = form.find('[name="kit_template"]').val();
			if (!kitTemplate) {
				frappe.msgprint({
					title: scheduleText("Selection Required"),
					indicator: 'orange',
					message: scheduleText("Please select an Extrusion Kit before adding the line.")
				});
				return;
			}
			data.product_type = 'Extrusion Kit';
			data.kit_template = kitTemplate;
			data.configuration_status = 'Pending';
		} else if (isPowerSupplyType) {
			// Power supply path - uses the power supply template and the power supply configurator
			var driverTemplate = form.find('[name="driver_template"]').val();
			if (!driverTemplate) {
				frappe.msgprint({
					title: scheduleText("Selection Required"),
					indicator: 'orange',
					message: scheduleText("Please select a power supply before adding the line.")
				});
				return;
			}
			data.manufacturer_type = 'ACCESSORY';
			data.accessory_product_type = productType;
			data.driver_template = driverTemplate;
		} else if (productType) {
			// Other product types - uses item selection (potentially with variants)
			var selectedItem = form.find('[name="selected_item"]').val();
			var selectedVariant = form.find('[name="selected_variant"]').val();
			
			if (!selectedItem) {
				frappe.msgprint({
					title: scheduleText("Selection Required"),
					indicator: 'orange',
					message: scheduleText("Please select an item before adding the line.")
				});
				return;
			}
			
			// Check if item has variants and if one was selected
			var $selectedOption = form.find('[name="selected_item"] option:selected');
			var hasVariants = $selectedOption.data('has-variants') === '1' || $selectedOption.data('has-variants') === 1;
			
			if (hasVariants && !selectedVariant) {
				frappe.msgprint({
					title: scheduleText("Configuration Required"),
					indicator: 'orange',
					message: scheduleText("This item has options. Please click \"Configure Options\" to select your preferred variant.")
				});
				return;
			}
			
			// Use ACCESSORY manufacturer type internally for items (keeps data model compatibility)
			data.manufacturer_type = 'ACCESSORY';
			data.accessory_product_type = productType;
			
			// If variant was selected, use that; otherwise use the template item
			if (selectedVariant) {
				data.accessory_item = selectedVariant;
				data.accessory_item_name = $('#selected_variant_name').text().split(' (')[0];
				// Capture the variant attribute selections for display
				var variantSelections = {};
				$('.variant-attribute-select').each(function() {
					var attr = $(this).data('attribute');
					var val = $(this).val();
					if (attr && val) {
						variantSelections[attr] = val;
					}
				});
				if (Object.keys(variantSelections).length > 0) {
					data.variant_selections = variantSelections;
				}
			} else {
				data.accessory_item = selectedItem;
				data.accessory_item_name = $selectedOption.data('name') || '';
			}
		}
	}

	// Add Other manufacturer fields if applicable
	if (manufacturerType === 'OTHER') {
		data.manufacturer_name = form.find('[name="manufacturer_name"]').val();
		data.fixture_model_number = form.find('[name="fixture_model_number"]').val();
		data.trim_info = form.find('[name="trim_info"]').val();
		data.housing_model_number = form.find('[name="housing_model_number"]').val();
		data.driver_model_number = form.find('[name="driver_model_number"]').val();
		data.lamp_info = form.find('[name="lamp_info"]').val();
		data.dimming_protocol = form.find('[name="dimming_protocol"]').val();
		data.input_voltage = form.find('[name="input_voltage"]').val();
		data.other_finish = form.find('[name="other_finish"]').val();
		DEALER_DATA_FIELDS.forEach(function(field) {
			data[field] = form.find('[name="' + field + '"]').val();
		});
	}

	// Handle file upload if present
	var fileInput = document.getElementById('add_spec_sheet_file');
	if (manufacturerType === 'OTHER' && fileInput && fileInput.files.length > 0) {
		uploadFile(fileInput, function(fileUrl) {
			if (fileUrl) {
				data.spec_sheet_file_id = fileUrl;
			}
			submitAddLine(data);
		});
	} else {
		submitAddLine(data);
	}
}

function submitAddLine(data) {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.add_schedule_line',
		args: {
			schedule_name: schedule_name,
			line_data: data
		},
		callback: function(r) {
			if (r.message && r.message.success) {
				$('#addLineModal').modal('hide');
				location.reload();
			} else {
				frappe.msgprint(r.message.error || 'Error adding line');
			}
		}
	});
}

function startConfigurationDraft(category, template) {
	var form = $('#addLineForm');
	var metadata = {};
	['line_id', 'location', 'qty', 'notes'].forEach(function (field) { metadata[field] = form.find('[name="' + field + '"]').val(); });
	var qty = Number(metadata.qty);
	if (!Number.isInteger(qty) || qty < 1) { frappe.msgprint(__('Enter a positive whole quantity.')); return; }
	var id = crypto.randomUUID();
	try {
		sessionStorage.setItem('ill-line-draft:' + id, JSON.stringify({ schedule: schedule_name, metadata: metadata, savedAt: Date.now() }));
		sessionStorage.setItem('ill-line-draft-last:' + schedule_name, id);
	} catch (_) { frappe.msgprint(__('Browser storage is unavailable. Allow session storage to preserve this draft.')); return; }
	var params = new URLSearchParams({ category: category, template: template, schedule: schedule_name, draft: id });
	window.location.href = '/portal/configure?' + params.toString();
}
function configureFromAddModal() {
	var form = $('#addLineForm');
	var option = form.find('[name="product_type"] option:selected');
	var fixture = [1, '1', true, 'true'].includes(option.data('is-fixture-type'));
	var tapeNeon = [1, '1', true, 'true'].includes(option.data('is-tape-neon-type'));
	if (form.find('[name="manufacturer_type"]').val() !== 'ILLUMENATE' || (!fixture && !tapeNeon)) return;
	var selector = fixture ? '[name="fixture_template"]' : '[name="tape_neon_template"]';
	var template = form.find(selector).val();
	if (!template) { frappe.msgprint(__('Select a product before configuring.')); return; }
	var category = fixture ? 'Linear Fixture' : tapeNeonCategoryOf(option);
	startConfigurationDraft(category, form.find(selector + ' option:selected').data('template-code') || template);
}
function configureDriverFromAddModal() {
	var template = $('#addLineForm [name="driver_template"]').val();
	if (!template) { frappe.msgprint(__('Select a power supply.')); return; }
	startConfigurationDraft('Driver', template);
}
function configureKitFromAddModal() {
	var template = $('#addLineForm [name="kit_template"]').val();
	if (!template) { frappe.msgprint(__('Select an Extrusion Kit.')); return; }
	startConfigurationDraft('Extrusion Kit', template);
}
function configureLedSheetFromAddModal() {
	var template = $('#addLineForm [name="led_sheet_template"]').val();
	if (!template) { frappe.msgprint(__('Select an LED Sheet template.')); return; }
	startConfigurationDraft('LED Sheet', template);
}

function duplicateLine(line_idx) {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.duplicate_schedule_line',
		args: lineRef(line_idx),
		callback: function(r) {
			if (r.message && r.message.success) {
				location.reload();
			} else {
				frappe.msgprint((r.message && r.message.error) || 'Error duplicating line');
			}
		}
	});
}

// Line data for editing
var lineData = scheduleContext.lines;
// Dealer-entered design data on third-party lines (System Designer D8).
var DEALER_DATA_FIELDS = ['watts_each', 'input_voltage_v', 'voltage_class', 'third_party_drive', 'third_party_ma', 'third_party_dimming'];
function toggleDealerCurrent($drive) {
	$drive.closest('.dealer-design-data').find('.dealer-ma').toggle($drive.val() === 'CC');
}
$(document).on('change', '.dealer-drive', function() { toggleDealerCurrent($(this)); });
$(function() { $('.dealer-drive').each(function() { toggleDealerCurrent($(this)); }); });

function editLine(line_idx) {
	var line = lineData[line_idx];
	if (!line) {
		frappe.msgprint('Line not found');
		return;
	}

	// Populate the edit form
	$('#edit_line_idx').val(line_idx);
	$('#edit_line_id').val(line.line_id || '');
	$('#edit_qty').val(line.qty || 1);
	$('#edit_location').val(line.location || '');
	$('#edit_notes').val(line.notes || '');
	$('#edit_manufacturer_type').val(line.manufacturer_type || 'ILLUMENATE');

	// Hide all type-specific fields first
	$('.edit-other-fields').hide();
	$('.edit-accessory-fields').hide();

	// Show/hide fields based on manufacturer type
	if (line.manufacturer_type === 'OTHER') {
		$('.edit-other-fields').show();
		$('#edit_manufacturer_name').val(line.manufacturer_name || '');
		$('#edit_fixture_model_number').val(line.fixture_model_number || '');
		$('#edit_trim_info').val(line.trim_info || '');
		$('#edit_housing_model_number').val(line.housing_model_number || '');
		$('#edit_driver_model_number').val(line.driver_model_number || '');
		$('#edit_lamp_info').val(line.lamp_info || '');
		$('#edit_dimming_protocol').val(line.dimming_protocol || '');
		$('#edit_input_voltage').val(line.input_voltage || '');
		$('#edit_other_finish').val(line.other_finish || '');
		DEALER_DATA_FIELDS.forEach(function(field) {
			var value = line[field];
			if (field === 'input_voltage_v' && value) value = String(parseInt(value, 10));
			$('#edit_' + field).val(value === null || value === undefined ? '' : value);
		});
		toggleDealerCurrent($('#edit_third_party_drive'));

		// Show current spec sheet if exists
		if (line.spec_sheet) {
			$('#edit_spec_sheet_current').html(
				'<a href="' + PortalUI.escape(line.spec_sheet) + '" target="_blank" class="btn btn-sm btn-outline-secondary">' +
				'<i class="fa fa-file-pdf-o" aria-hidden="true"></i> Current Spec Sheet</a>'
			);
		} else {
			$('#edit_spec_sheet_current').html('<span class="text-muted">No spec sheet uploaded</span>');
		}
	} else if (line.manufacturer_type === 'ACCESSORY') {
		$('.edit-accessory-fields').show();
		$('#edit_accessory_product_type').val(line.accessory_product_type || '');
		$('#edit_accessory_item').val((line.accessory_item_name || '') + ' (' + (line.accessory_item || '') + ')');
	}

	$('#editLineModal').modal('show');
}

function saveEditLine() {
	var line_idx = $('#edit_line_idx').val();
	var line = lineData[line_idx];
	var line_data = {
		line_id: $('#edit_line_id').val(),
		qty: $('#edit_qty').val(),
		location: $('#edit_location').val(),
		notes: $('#edit_notes').val()
	};

	// Add Other manufacturer fields if applicable
	if (line && line.manufacturer_type === 'OTHER') {
		line_data.manufacturer_name = $('#edit_manufacturer_name').val();
		line_data.fixture_model_number = $('#edit_fixture_model_number').val();
		line_data.trim_info = $('#edit_trim_info').val();
		line_data.housing_model_number = $('#edit_housing_model_number').val();
		line_data.driver_model_number = $('#edit_driver_model_number').val();
		line_data.lamp_info = $('#edit_lamp_info').val();
		line_data.dimming_protocol = $('#edit_dimming_protocol').val();
		line_data.input_voltage = $('#edit_input_voltage').val();
		line_data.other_finish = $('#edit_other_finish').val();
		DEALER_DATA_FIELDS.forEach(function(field) {
			line_data[field] = $('#edit_' + field).val();
		});

		// Handle file upload if present
		var fileInput = document.getElementById('edit_spec_sheet_file');
		if (fileInput && fileInput.files.length > 0) {
			uploadFile(fileInput, function(fileUrl) {
				if (fileUrl) {
					line_data.spec_sheet_file_id = fileUrl;
				}
				submitEditLine(line_idx, line_data);
			});
			return;
		}
	}

	submitEditLine(line_idx, line_data);
}

function submitEditLine(line_idx, line_data) {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.update_schedule_line',
		args: Object.assign(lineRef(line_idx), { line_data: line_data }),
		callback: function(r) {
			if (r.message && r.message.success) {
				$('#editLineModal').modal('hide');
				location.reload();
			} else {
				frappe.msgprint((r.message && r.message.error) || 'Error updating line');
			}
		}
	});
}

function deleteLine(line_idx) {
	frappe.confirm('Are you sure you want to delete this line?', function() {
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.delete_schedule_line',
			args: lineRef(line_idx),
			callback: function(r) {
				if (r.message && r.message.success) {
					location.reload();
				} else {
					frappe.msgprint((r.message && r.message.error) || 'Error deleting line');
				}
			}
		});
	});
}
