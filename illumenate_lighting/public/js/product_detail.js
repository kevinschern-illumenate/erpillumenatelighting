/**
 * Product Detail JS
 *
 * Drives the /portal/products/<slug> page.
 *  – Fetches full product detail from the catalog API
 *  – Renders gallery, specs, docs, certs and the per-foot MSRP
 *  – Renders the "Add to a Fixture Schedule" panel: configurable products
 *    route to their family configurator; everything else becomes an
 *    accessory line.
 */

/* global frappe, __ */

// ── Page-level state ────────────────────────────────────────────────

var ProductDetail = {
	slug: null,
	product: null,
	schedules: [],
	scheduleRequest: 0,
	saveAttempt: null,
	pageContext: {}
};

// ── Initialisation ──────────────────────────────────────────────────

function initProductDetail(slug, pageContext) {
	ProductDetail.slug = slug;
	ProductDetail.pageContext = pageContext || {};
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
				renderProductAction(r.message.product);
				focusActionIfRequested();
			} else {
				$('#detailLoading').html(
					'<p class="text-danger">' + _escHtml(r.message && r.message.error || 'Product not found') + '</p>'
				);
			}
		},
		error: function() {
			$('#detailLoading').text(__('Unable to load this product. Please reload to try again.'));
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
	if (p.price_per_ft_msrp !== undefined && p.price_per_ft_msrp !== null) {
		priceHtml = '<div class="product-hero-price">' + _escHtml(formatPerFoot(p.price_per_ft_msrp)) + ' <small>MSRP, before options</small></div>';
	}

	$('#productInfo').html(
		'<h2>' + _escHtml(p.product_name) + '</h2>' +
		'<div class="product-hero-badges">' + badges + '</div>' +
		'<div class="product-hero-desc">' + (p.short_description ? _escHtml(p.short_description) : '') + '</div>' +
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

}

function formatPerFoot(amount) {
	return '$' + Number(amount).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' / ft';
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
		html += '<tr><td>' + _escHtml(s.spec_label) + '</td><td>' + _escHtml(s.spec_value) + ' ' + _escHtml(s.spec_unit || '') + '</td></tr>';
	});
	html += '</table>';
	$('#tabSpecs').html(html);
}

function renderDocs(docs) {
	if (!docs.length) { $('#tabDocs').html('<p class="text-muted">No documents available.</p>'); return; }
	var html = '<div class="doc-list">';
	docs.forEach(function(d) {
		if (!d.file_url) return;
		var icon = d.document_type === 'PDF' ? 'fa-file-pdf-o' : 'fa-file-o';
		html += '<a href="' + _escHtml(d.file_url) + '" target="_blank" rel="noopener"><i class="fa ' + icon + '"></i> ' + _escHtml(d.document_name) + '</a>';
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

// ── Add to fixture schedule ─────────────────────────────────────────
//
// Configurable products (linear fixtures, LED tape, LED neon, LED sheets)
// hand off to their family's configurator with a line draft, so the saved
// configuration lands on a new schedule line carrying the fixture type and
// location entered here. Other products (extrusion kits, components,
// accessories, drivers, controllers) are added directly as accessory lines.

var STANDARD_API = 'illumenate_lighting.illumenate_lighting.portal.standard_products.';
var FAMILY_LABELS = {
	'Linear Fixture': 'linear fixture',
	'LED Tape': 'LED tape',
	'LED Neon': 'LED neon',
	'LED Sheet': 'LED sheet'
};

function navigateTo(href) {
	window.location.assign(href);
}

function productActionMode(product) {
	if (product.configure_url) return 'configure';
	if (product.capability === 'quantity') return 'standard';
	return 'inquiry';
}

function configureHref(product, params) {
	var url = new URL(product.configure_url, window.location.origin);
	Object.keys(params || {}).forEach(function(key) {
		if (params[key] !== null && params[key] !== undefined && params[key] !== '') url.searchParams.set(key, params[key]);
	});
	return url.pathname + url.search;
}

function renderProductAction(product) {
	var $section = $('#productActionSection').empty().show();
	var mode = productActionMode(product);
	var context = new URLSearchParams(window.location.search);
	$section.append($('<h5>').text(__('Add to a Fixture Schedule')));

	if (mode === 'inquiry') {
		var messages = {
			inactive: __('This product is not currently available.'),
			not_configurable: __('This product is available with help from our team.'),
			missing_template: __('This product needs a configurator template before it can be ordered online.'),
			inactive_template: __('This product\'s configurator is temporarily unavailable.'),
			family_not_enabled: __('Online configuration for this product family is not enabled yet.'),
			pilot_only: __('Online configuration for this product family is not yet available for your account.')
		};
		var reason = String(product.capability_reason || '');
		var message = messages[reason] || (reason.indexOf('invalid_options:') === 0
			? __('This product\'s configurator options need review before it can be ordered online.')
			: __('This product is not yet orderable from the portal. Contact us and we will add it to your schedule.'));
		$section.append($('<p class="text-muted">').text(message));
		if (ProductDetail.pageContext.isStaff) {
			$section.append($('<p class="small text-muted">')
				.append(document.createTextNode(__('Catalog capability reason: {0}. ', [reason || 'unknown'])))
				.append($('<a>').attr('href', ProductDetail.pageContext.deskUrl).text(__('Open product in Desk'))));
		}
		$section.append($('<a class="btn btn-outline-primary">').attr('href', '/portal/support').text(__('Request product assistance')));
		return;
	}

	var familyLabel = FAMILY_LABELS[product.family] || String(product.family || '').toLowerCase();
	if (mode === 'configure' && (context.has('line_idx') || context.has('line_key'))) {
		// Reconfiguring an existing schedule line: its fixture type and location are already set.
		$section.append($('<p class="text-muted">').text(__('Open the {0} configurator to update the selected schedule line.', [familyLabel])));
		$section.append($('<a class="btn btn-primary" id="productActionSubmit">').attr('href', configureHref(product, {
			schedule: context.get('schedule'), line_idx: context.get('line_idx'), line_key: context.get('line_key')
		})).text(__('Configure this product')));
		return;
	}

	if (mode === 'configure' && product.configurator_intro_text) {
		$section.append($('<p>').text(product.configurator_intro_text));
	}
	$section.append($('<p class="text-muted">').text(mode === 'configure'
		? __('Enter the fixture type and location for the new schedule line, then configure this product in the {0} configurator. The line is added when you save the configuration.', [familyLabel])
		: __('This product is added to the schedule as an accessory line. Enter the fixture type and location for the line.')));

	var $form = $('<form id="scheduleLineForm" novalidate>');
	function field(id, label, $input, cols) {
		return $('<div class="form-group">').addClass(cols || 'col-md-6')
			.append($('<label>').attr('for', id).text(label))
			.append($input.attr('id', id).addClass('form-control form-control-sm'));
	}
	$form.append($('<div class="form-row">')
		.append(field('scheduleSearch', __('Find schedule'), $('<input type="search">').attr('placeholder', __('Search by schedule name'))))
		.append(field('scheduleSelect', __('Fixture schedule') + ' *', $('<select required>'))));
	if (mode === 'standard') {
		var $sku = $('<select required>');
		(product.standard_choices || []).forEach(function(row) {
			$sku.append($('<option>').val(row.item_code).text(row.label + ' [' + row.stock_uom + ']'));
		});
		$form.append($('<div class="form-row">').append(field('skuSelect', __('SKU') + ' *', $sku, 'col-md-12')));
	}
	$form.append($('<div class="form-row">')
		.append(field('lineFixtureType', __('Fixture type') + ' *', $('<input type="text" required maxlength="140">').attr('placeholder', __('e.g. A1')), 'col-md-4'))
		.append(field('lineLocation', __('Location'), $('<input type="text" maxlength="140">').attr('placeholder', __('e.g. Lobby cove')), 'col-md-5'))
		.append(field('lineQty', mode === 'standard' ? __('Quantity (stock UOM)') + ' *' : __('Quantity') + ' *', $('<input type="number" min="1" step="1" required>').val(1), 'col-md-3')));
	$form.append($('<div class="form-row">').append(field('lineNotes', __('Notes'), $('<textarea rows="2" maxlength="4000">'), 'col-md-12')));
	var $actions = $('<div class="d-flex flex-wrap align-items-center" style="gap:0.5rem">');
	$actions.append($('<button type="submit" class="btn btn-primary" id="productActionSubmit">')
		.text(mode === 'configure' ? __('Configure & add to schedule') : __('Add to schedule')));
	if (mode === 'configure') {
		$actions.append($('<a class="btn btn-link btn-sm" id="configureOnlyLink">').attr('href', configureHref(product, {}))
			.text(__('Configure without a schedule')));
	}
	$form.append($actions);
	$section.append($form);

	ProductDetail.schedules = [];
	ProductDetail.saveAttempt = null;
	$form.on('submit', function(event) {
		event.preventDefault();
		submitProductAction(product, mode);
	});
	var searchTimer = null;
	$('#scheduleSearch').on('input', function() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(function() { loadSchedules(product, $('#scheduleSearch').val()); }, 250);
	});
	return loadSchedules(product, '', context.get('schedule'));
}

function loadSchedules(product, search, preferred) {
	var serial = ++ProductDetail.scheduleRequest;
	var previous = preferred || $('#scheduleSelect').val();
	return Promise.resolve(frappe.call({method: STANDARD_API + 'prepare', args: {product_slug: product.product_slug, search: search || ''}}))
		.then(function(r) {
			if (serial !== ProductDetail.scheduleRequest) return;
			var data = (r && r.message) || {};
			ProductDetail.schedules = data.schedules || [];
			var $select = $('#scheduleSelect').empty()
				.append($('<option value="">').text(ProductDetail.schedules.length ? __('Select schedule…') : __('No editable schedules found')));
			ProductDetail.schedules.forEach(function(row) {
				$select.append($('<option>').val(row.name).text(row.schedule_name + ' (' + row.name + ')'));
			});
			if (previous && ProductDetail.schedules.some(function(row) { return row.name === previous; })) $select.val(previous);
		})
		.catch(function() {
			if (serial === ProductDetail.scheduleRequest) frappe.msgprint(__('Schedules could not be loaded. Your entries are retained; try the search again.'));
		});
}

function readLineForm() {
	return {
		schedule_name: $('#scheduleSelect').val(),
		item_code: $('#skuSelect').val(),
		line_id: String($('#lineFixtureType').val() || '').trim(),
		location: String($('#lineLocation').val() || '').trim(),
		qty: Number($('#lineQty').val()),
		notes: String($('#lineNotes').val() || '')
	};
}

function submitProductAction(product, mode) {
	var values = readLineForm();
	var schedule = ProductDetail.schedules.find(function(row) { return row.name === values.schedule_name; });
	if (!schedule) { frappe.msgprint(__('Choose an editable fixture schedule.')); return; }
	if (!values.line_id) { frappe.msgprint(__('Enter a fixture type for the schedule line.')); return; }
	if (!Number.isInteger(values.qty) || values.qty < 1) { frappe.msgprint(__('Enter a positive whole quantity.')); return; }
	if (mode === 'standard' && !values.item_code) { frappe.msgprint(__('Choose a SKU.')); return; }
	return mode === 'configure' ? startConfigureDraft(product, schedule, values) : addStandardLine(product, schedule, values);
}

function startConfigureDraft(product, schedule, values) {
	var id = window.crypto.randomUUID();
	var metadata = {line_id: values.line_id, location: values.location, qty: values.qty, notes: values.notes};
	try {
		window.sessionStorage.setItem('ill-line-draft:' + id, JSON.stringify({schedule: schedule.name, metadata: metadata, savedAt: Date.now()}));
		window.sessionStorage.setItem('ill-line-draft-last:' + schedule.name, id);
	} catch (_) {
		frappe.msgprint(__('Browser storage is unavailable. Allow session storage to carry the fixture type and location into the configurator.'));
		return;
	}
	navigateTo(configureHref(product, {schedule: schedule.name, draft: id}));
}

async function addStandardLine(product, schedule, values) {
	var args = {
		product_slug: product.product_slug, item_code: values.item_code, schedule_name: schedule.name,
		quantity: values.qty, line_id: values.line_id, location: values.location, notes: values.notes,
		expected_modified: schedule.modified
	};
	// Retries of identical content reuse the key so a lost response cannot add a duplicate line.
	var signature = JSON.stringify(args);
	if (!ProductDetail.saveAttempt || ProductDetail.saveAttempt.signature !== signature) {
		ProductDetail.saveAttempt = {signature: signature, key: window.crypto.randomUUID()};
	}
	args.idempotency_key = ProductDetail.saveAttempt.key;
	var $button = $('#productActionSubmit').prop('disabled', true);
	try {
		var response = await frappe.call({method: STANDARD_API + 'add', type: 'POST', args: args});
		navigateTo('/portal/schedules/' + encodeURIComponent(response.message.schedule_name));
	} catch (error) {
		frappe.msgprint(__('The line was not confirmed. Your entries are retained; retry, or reload the schedule if it changed.'));
	} finally {
		$button.prop('disabled', false);
	}
}

// Catalog cards link to "#configure" so the dealer lands on this panel, not the page top.
function focusActionIfRequested() {
	if (window.location.hash !== '#configure') return;
	var section = document.getElementById('productActionSection');
	if (!section) return;
	section.setAttribute('tabindex', '-1');
	section.scrollIntoView({block: 'start'});
	var target = section.querySelector('input, select, textarea, button, a[href]') || section;
	target.focus({preventScroll: true});
}

// ── Helpers ─────────────────────────────────────────────────────────

function _escHtml(str) {
	if (!str) return '';
	var div = document.createElement('div');
	div.textContent = str;
	return div.innerHTML.replaceAll('"', '&quot;').replaceAll("'", "&#39;");
}
