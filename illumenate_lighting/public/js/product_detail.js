/**
 * Product Detail JS
 *
 * Drives the /portal/products/<slug> page.
 *  – Fetches full product detail from the catalog API
 *  – Renders gallery, specs, docs, certs
 *  – For configurable products: initialises the embedded configurator
 *    (reuses WebflowConfigurator from webflow_configurator.js)
 *    and wires project → schedule → line cascading selectors.
 */

/* global frappe, WebflowConfigurator, initializeFromProduct,
   handleInitResponse, populatePillSelector, populateFeedDirections,
   showAllSections, updateProgress, updatePartNumberPreview,
   gatherAllSelections, updateValidateButton, validateConfiguration,
   handleValidationResponse, resetConfiguration, handlePillClick, debounce */

// ── Page-level state ────────────────────────────────────────────────

var ProductDetail = {
	slug: null,
	product: null,
	isConfigurable: false,
	fixtureTemplate: ''
};

// ── Initialisation ──────────────────────────────────────────────────

function initProductDetail(slug, isConfigurable, fixtureTemplate) {
	ProductDetail.slug = slug;
	ProductDetail.isConfigurable = isConfigurable;
	ProductDetail.fixtureTemplate = fixtureTemplate;

	loadProductDetail(slug);
}

function loadProductDetail(slug) {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.product_catalog.get_catalog_product_detail',
		args: { product_slug: slug },
		callback: function(r) {
			if (r.message && r.message.success) {
				ProductDetail.product = r.message.product;
				renderDetail(r.message.product);

				if (ProductDetail.isConfigurable) {
					initEmbeddedConfigurator(slug);
					loadProjectDropdown();
				}
			} else {
				$('#detailLoading').html(
					'<p class="text-danger">' + (r.message && r.message.error || 'Product not found') + '</p>'
				);
			}
		}
	});
}

// ── Render product detail ───────────────────────────────────────────

function renderDetail(p) {
	$('#detailLoading').hide();
	$('#detailContent').show();

	// Gallery
	renderGallery(p.gallery || []);

	// Hero info
	var badges = '<span class="badge" style="background:var(--ill-gray-200);color:var(--ill-gray-700)">' + _escHtml(p.product_type) + '</span>';
	if (p.series) {
		badges += ' <span class="badge" style="background:#e7f1ff;color:var(--ill-primary,#1976d2)">' + _escHtml(p.series) + '</span>';
	}
	if (p.is_configurable) {
		badges += ' <span class="badge" style="background:#e8f5e9;color:#2e7d32">Configurable</span>';
	}

	var priceHtml = '';
	if (p.base_price_msrp) {
		priceHtml = '<div class="product-hero-price">From $' + Number(p.base_price_msrp).toLocaleString() + '</div>';
	}

	$('#productInfo').html(
		'<h2>' + _escHtml(p.product_name) + '</h2>' +
		'<div class="product-hero-badges">' + badges + '</div>' +
		'<div class="product-hero-desc">' + (p.short_description ? _escHtml(p.short_description) : '') + '</div>' +
		(p.long_description ? '<div class="mb-3" style="font-size:0.9rem;line-height:1.6">' + p.long_description + '</div>' : '') +
		priceHtml
	);

	// Tabs: specs, docs, certs
	var hasContent = (p.specifications && p.specifications.length) ||
		(p.documents && p.documents.length) ||
		(p.certifications && p.certifications.length);
	if (hasContent) {
		$('#productTabs').show();
		renderSpecs(p.specifications || []);
		renderDocs(p.documents || []);
		renderCerts(p.certifications || []);
	}

	// Configurator intro text
	if (p.configurator_intro_text && ProductDetail.isConfigurable) {
		$('#configuratorIntro').text(p.configurator_intro_text);
	}
}

function renderGallery(images) {
	var $g = $('#productGallery');
	if (!images.length) {
		$g.html('<div style="width:100%;height:300px;background:var(--ill-gray-100);border-radius:10px;display:flex;align-items:center;justify-content:center;color:var(--ill-gray-400);font-size:3rem"><i class="fa fa-image"></i></div>');
		return;
	}

	var mainSrc = images[0].image;
	var html = '<div class="product-gallery-main"><img id="galleryMainImg" src="' + _escHtml(mainSrc) + '" alt=""></div>';

	if (images.length > 1) {
		html += '<div class="product-gallery-thumbs">';
		images.forEach(function(img, i) {
			html += '<div class="gallery-thumb' + (i === 0 ? ' active' : '') + '" data-idx="' + i + '" data-src="' + _escHtml(img.image) + '">' +
				'<img src="' + _escHtml(img.image) + '" alt="' + _escHtml(img.alt_text || '') + '"></div>';
		});
		html += '</div>';
	}
	$g.html(html);

	$g.off('click', '.gallery-thumb').on('click', '.gallery-thumb', function() {
		var src = $(this).data('src');
		$('#galleryMainImg').attr('src', src);
		$g.find('.gallery-thumb').removeClass('active');
		$(this).addClass('active');
	});
}

function renderSpecs(specs) {
	if (!specs.length) { $('#tabSpecs').html('<p class="text-muted">No specifications available.</p>'); return; }
	var html = '<table class="spec-table">';
	specs.forEach(function(s) {
		html += '<tr><td>' + _escHtml(s.spec_label) + '</td><td>' + _escHtml(s.spec_value) + '</td></tr>';
	});
	html += '</table>';
	$('#tabSpecs').html(html);
}

function renderDocs(docs) {
	if (!docs.length) { $('#tabDocs').html('<p class="text-muted">No documents available.</p>'); return; }
	var html = '<div class="doc-list">';
	docs.forEach(function(d) {
		var icon = d.document_type === 'PDF' ? 'fa-file-pdf-o' : 'fa-file-o';
		html += '<a href="' + _escHtml(d.file_url || '#') + '" target="_blank"><i class="fa ' + icon + '"></i> ' + _escHtml(d.document_name) + '</a>';
	});
	html += '</div>';
	$('#tabDocs').html(html);
}

function renderCerts(certs) {
	if (!certs.length) { $('#tabCerts').html('<p class="text-muted">No certifications listed.</p>'); return; }
	var html = '';
	certs.forEach(function(c) {
		html += '<span class="cert-badge"><i class="fa fa-certificate"></i> ' + _escHtml(c.certification_name || c.certification_body) + '</span>';
	});
	$('#tabCerts').html(html);
}

// ── Embedded Configurator ───────────────────────────────────────────

function initEmbeddedConfigurator(slug) {
	// Re-use WebflowConfigurator global object
	WebflowConfigurator.context = { product_slug: slug, can_save: true, show_pricing: true };
	WebflowConfigurator.productSlug = slug;

	// Build the step HTML inside #configSteps (same IDs the shared JS expects)
	buildConfiguratorDOM();

	// Call the shared init function which fetches options from API
	initializeFromProduct(slug);

	// Bind action buttons
	$('#validateConfigBtn').off('click').on('click', function() {
		validateConfiguration();
	});
	$('#resetConfigBtn').off('click').on('click', function() {
		resetConfiguration();
		$('#validateConfigBtn').prop('disabled', true);
		$('#addToScheduleBtn').prop('disabled', true);
	});
	$('#addToScheduleBtn').off('click').on('click', function() {
		addFixtureFromDetail();
	});
}

/**
 * Build the HTML skeleton the shared webflow_configurator.js expects.
 */
function buildConfiguratorDOM() {
	var $steps = $('#configSteps').empty();

	// Series (locked)
	$steps.append(
		'<div class="config-step locked" id="seriesSection">' +
		'<h6><i class="fa fa-lock text-muted mr-1"></i> Series</h6>' +
		'<div class="series-badge" id="seriesName">Loading…</div>' +
		'<span id="seriesCode" style="display:none"></span>' +
		'</div>'
	);

	// Dynamic steps
	var stepDefs = [
		{ id: 'environmentSection', field: 'environment_rating', label: 'Environment (Dry/Wet)' },
		{ id: 'cctSection', field: 'cct', label: 'CCT' },
		{ id: 'lensSection', field: 'lens_appearance', label: 'Lens' },
		{ id: 'outputSection', field: 'output_level', label: 'Output' },
		{ id: 'mountingSection', field: 'mounting_method', label: 'Mounting' },
		{ id: 'finishSection', field: 'finish', label: 'Finish' }
	];

	stepDefs.forEach(function(s) {
		$steps.append(
			'<div class="config-step" id="' + s.id + '" style="display:none">' +
			'<h6>' + s.label + '</h6>' +
			'<div class="pill-selector" data-field="' + s.field + '"></div>' +
			'<select class="form-control form-control-sm mt-2 select-fallback" name="' + s.field + '" style="display:none"></select>' +
			'</div>'
		);
	});

	// Length
	$steps.append(
		'<div class="config-step" id="lengthSection" style="display:none">' +
		'<h6>Length</h6>' +
		'<div class="length-group">' +
		'<input type="number" class="form-control form-control-sm" name="length_value" placeholder="50">' +
		'<select class="form-control form-control-sm" name="length_unit">' +
		'<option value="inches" selected>in</option><option value="mm">mm</option>' +
		'</select></div>' +
		'<small class="text-muted" id="lengthNote"></small>' +
		'</div>'
	);

	// Feed directions
	$steps.append(
		'<div class="config-step" id="feedSection" style="display:none">' +
		'<h6>Feed Directions</h6>' +
		'<div class="feed-row">' +
		'<div>' +
		'<label class="small font-weight-bold">Start Feed</label>' +
		'<div class="pill-selector" data-field="start_feed_direction"></div>' +
		'<select class="form-control form-control-sm mt-1 select-fallback" name="start_feed_direction" style="display:none"></select>' +
		'<label class="small mt-2">Start Leader (ft)</label>' +
		'<select class="form-control form-control-sm" name="start_feed_length_ft"></select>' +
		'</div>' +
		'<div>' +
		'<label class="small font-weight-bold">End Feed</label>' +
		'<div class="pill-selector" data-field="end_feed_direction"></div>' +
		'<select class="form-control form-control-sm mt-1 select-fallback" name="end_feed_direction" style="display:none"></select>' +
		'<label class="small mt-2">End Leader (ft)</label>' +
		'<select class="form-control form-control-sm" name="end_feed_length_ft"></select>' +
		'</div></div></div>'
	);

	// Power Supply Option
	$steps.append(
		'<div class="config-step mt-3" id="powerSupplySection">' +
		'<div class="custom-control custom-checkbox">' +
		'<input type="checkbox" class="custom-control-input" id="includePowerSupply" name="include_power_supply" checked>' +
		'<label class="custom-control-label" for="includePowerSupply">' +
		'<strong>Include Power Supplies?</strong>' +
		'<small class="text-muted d-block">Uncheck to exclude drivers/power supplies from this fixture and source them separately.</small>' +
		'</label></div></div>'
	);

	// Validation messages
	$steps.append(
		'<div id="validationMessages" style="display:none"><div id="messagesList"></div></div>'
	);

	// Hidden helpers the shared JS looks for
	$steps.append('<span id="validationStatus" class="badge badge-secondary" style="display:none"></span>');
	$steps.append('<span id="summaryList" style="display:none"></span>');
	$steps.append('<span id="summaryPlaceholder" style="display:none"></span>');
	$steps.append('<div id="pricingPreview" style="display:none"><span id="basePrice"></span><span id="lengthPrice"></span><span id="totalMsrp"></span></div>');
	$steps.append('<div id="complexFixtureBanner" style="display:none"></div>');
}

// ── Schedule cascading dropdowns ────────────────────────────────────

function loadProjectDropdown() {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_user_projects_for_configurator',
		callback: function(r) {
			if (!r.message || !r.message.success) return;
			var $sel = $('#projectSelect').empty().append('<option value="">Select project…</option>');
			(r.message.projects || []).forEach(function(p) {
				$sel.append('<option value="' + _escHtml(p.value) + '">' + _escHtml(p.label) + '</option>');
			});
		}
	});

	$('#projectSelect').off('change').on('change', function() {
		var proj = $(this).val();
		$('#scheduleSelect').prop('disabled', !proj).empty().append('<option value="">Select schedule…</option>');
		$('#lineSelect').prop('disabled', true).empty().append('<option value="">New line</option>');
		if (!proj) return;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedules_for_project',
			args: { project_name: proj },
			callback: function(r) {
				if (!r.message || !r.message.success) return;
				var $s = $('#scheduleSelect');
				(r.message.schedules || []).forEach(function(s) {
					$s.append('<option value="' + _escHtml(s.value) + '">' + _escHtml(s.label) + '</option>');
				});
			}
		});
	});

	$('#scheduleSelect').off('change').on('change', function() {
		var sched = $(this).val();
		$('#lineSelect').prop('disabled', !sched).empty().append('<option value="">New line</option>');
		if (!sched) return;
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator',
			args: { schedule_name: sched },
			callback: function(r) {
				if (!r.message || !r.message.success) return;
				var $l = $('#lineSelect');
				(r.message.lines || []).forEach(function(line) {
					$l.append('<option value="' + _escHtml(line.line_id) + '">' +
						_escHtml(line.line_id) + ' — ' + _escHtml(line.summary || '') + '</option>');
				});
			}
		});
	});
}

// ── Add to schedule from detail page ────────────────────────────────

function addFixtureFromDetail() {
	var project = $('#projectSelect').val();
	var schedule = $('#scheduleSelect').val();
	var lineId = $('#lineSelect').val();

	if (!project || !schedule) {
		frappe.msgprint(__('Please select a project and fixture schedule first.'));
		return;
	}

	// Gather part number from the validated configuration
	var partNumber = $('#partNumberPreview').text().trim();
	if (!partNumber || partNumber.indexOf('…') !== -1) {
		frappe.msgprint(__('Please complete and validate the configuration first.'));
		return;
	}

	var overwrite = lineId ? '1' : '0';

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.webflow_portal.add_fixture_to_schedule',
		args: {
			project: project,
			fixture_schedule: schedule,
			fixture_part_number: partNumber,
			line_id: lineId || '',
			overwrite: overwrite
		},
		freeze: true,
		freeze_message: __('Adding to schedule…'),
		callback: function(r) {
			if (r.message && r.message.success) {
				frappe.show_alert({
					message: __('Fixture added to schedule (Line {0})', [r.message.line_id]),
					indicator: 'green'
				});

				$('#addToScheduleBtn').prop('disabled', true);

				// Offer next actions
				var $msg = $(
					'<div class="alert alert-success mt-3">' +
					'<strong>Success!</strong> Line ' + _escHtml(r.message.line_id) + ' ' + r.message.action + '.' +
					'<div class="mt-2">' +
					'<a href="/portal/products/' + encodeURIComponent(ProductDetail.slug) + '" class="btn btn-sm btn-outline-primary mr-2">Configure Another</a>' +
					'<a href="/portal/schedules/' + encodeURIComponent(schedule) + '" class="btn btn-sm btn-primary">View Schedule</a>' +
					'</div></div>'
				);
				$('#configuratorSection').append($msg);
			} else {
				frappe.msgprint({
					title: __('Error'),
					message: (r.message && r.message.error) || __('Failed to add fixture'),
					indicator: 'red'
				});
			}
		}
	});
}

// ── Helpers ─────────────────────────────────────────────────────────

function _escHtml(str) {
	if (!str) return '';
	var div = document.createElement('div');
	div.textContent = str;
	return div.innerHTML;
}
