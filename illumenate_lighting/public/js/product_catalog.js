/**
 * Product Catalog JS
 *
 * Drives the /portal/products page – filter sidebar, search, grid, pagination.
 * All data comes from the product_catalog API endpoints.
 */

/* global frappe */

var CatalogState = {
	page: 1,
	pageSize: 12,
	search: '',
	productType: [],
	attrFilters: {},    // { attribute_type: [value, …] }
	products: [],
	total: 0,
	filterMeta: null,
	contextParams: {},
	requestVersion: 0,
	loading: false
};

// ── Initialisation ──────────────────────────────────────────────────

function initProductCatalog() {
	readUrlState();
	bindCatalogEvents();
	loadFilterOptions(function() { fetchProducts(true); });
}

// ── URL state ───────────────────────────────────────────────────────

function readUrlState() {
	var params = new URLSearchParams(window.location.search);
	CatalogState.attrFilters = {};
	CatalogState.contextParams = {};
	CatalogState.search = params.get('q') || '';
	$('#catalogSearch').val(CatalogState.search);

	var typeParam = params.get('type');
	CatalogState.productType = typeParam ? typeParam.split(',') : [];

	var reserved = ['finder', 'schedule', 'line_key', 'line_idx', 'draft'];
	reserved.forEach(function(key) {
		if (params.has(key)) CatalogState.contextParams[key] = params.get(key);
	});

	// Attribute filters encoded as ?Finish=White,Black&CCT=3000K. Ignore
	// tracking and other unknown parameters rather than sending them to SQL.
	var allowed = (CatalogState.filterMeta && CatalogState.filterMeta.filters || [])
		.map(function(group) { return group.attribute_type; });
	params.forEach(function(val, key) {
		if (allowed.indexOf(key) === -1) return;
		CatalogState.attrFilters[key] = val.split(',');
	});

	var pageParam = parseInt(params.get('page'), 10);
	if (pageParam > 0) CatalogState.page = pageParam;
}

function pushUrlState() {
	var params = new URLSearchParams();
	if (CatalogState.search) params.set('q', CatalogState.search);
	if (CatalogState.productType.length) params.set('type', CatalogState.productType.join(','));
	Object.keys(CatalogState.attrFilters).forEach(function(k) {
		var vals = CatalogState.attrFilters[k];
		if (vals && vals.length) params.set(k, vals.join(','));
	});
	if (CatalogState.page > 1) params.set('page', CatalogState.page);
	Object.keys(CatalogState.contextParams).forEach(function(key) {
		params.set(key, CatalogState.contextParams[key]);
	});

	var qs = params.toString();
	var url = window.location.pathname + (qs ? '?' + qs : '');
	window.history.replaceState(null, '', url);
}

// ── Events ──────────────────────────────────────────────────────────

function bindCatalogEvents() {
	var searchTimer;
	$('#catalogSearch').on('input', function() {
		clearTimeout(searchTimer);
		var val = $(this).val();
		searchTimer = setTimeout(function() {
			CatalogState.search = val;
			CatalogState.page = 1;
			fetchProducts(true);
		}, 350);
	});
}

// ── Filter sidebar ──────────────────────────────────────────────────

function loadFilterOptions(done) {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.product_catalog.get_catalog_filter_options',
		callback: function(r) {
			if (r.message && r.message.success) {
				CatalogState.filterMeta = r.message;
				readUrlState();
				renderFilterSidebar(r.message);
			}
			if (done) done();
		},
		error: function() {
			if (done) done();
		}
	});
}

function renderFilterSidebar(data) {
	// Product type tabs
	var $tabs = $('#productTypeTabs').empty();
	(data.product_types || []).forEach(function(pt) {
		var active = CatalogState.productType.indexOf(pt.value) !== -1 ? ' active' : '';
		$tabs.append(
			'<button type="button" aria-pressed="' + (active ? 'true' : 'false') + '" class="product-type-tab' + active + '" data-type="' +
			escapeHtml(pt.value) + '">' + escapeHtml(productFamilyLabel(pt.value)) +
			' <small class="text-muted">(' + pt.count + ')</small></button>'
		);
	});
	$tabs.off('click', '.product-type-tab').on('click', '.product-type-tab', function() {
		var type = this.getAttribute('data-type');
		$(this).toggleClass('active').attr('aria-pressed', $(this).hasClass('active') ? 'true' : 'false');
		// Rebuild array from active tabs
		CatalogState.productType = [];
		$tabs.find('.active').each(function() {
			CatalogState.productType.push(this.getAttribute('data-type'));
		});
		CatalogState.page = 1;
		fetchProducts(true);
	});

	// Attribute filter groups
	var $groups = $('#filterGroups').empty();
	(data.filters || []).forEach(function(group) {
		var $g = $('<div class="filter-group">');
		$g.append(
			'<button type="button" class="filter-group-title btn btn-link p-0" aria-expanded="true">' +
			escapeHtml(group.label || group.attribute_type) +
			' <i class="fa fa-chevron-down"></i></button>'
		);
		var $opts = $('<div class="filter-options">');
		(group.options || []).forEach(function(opt) {
			var checked = '';
			var arr = CatalogState.attrFilters[group.attribute_type] || [];
			if (arr.indexOf(opt.value) !== -1) checked = ' checked';
			$opts.append(
				'<label class="filter-option">' +
				'<input type="checkbox" data-attr="' + escapeHtml(group.attribute_type) +
				'" data-val="' + escapeHtml(opt.value) + '"' + checked + '> ' +
				escapeHtml(opt.value) +
				'<span class="count">' + opt.count + '</span></label>'
			);
		});
		$g.append($opts);
		$groups.append($g);
	});

	$groups.off('change', 'input[type=checkbox]').on('change', 'input[type=checkbox]', function() {
		var attr = this.getAttribute('data-attr');
		var val = this.getAttribute('data-val');
		if (!CatalogState.attrFilters[attr]) CatalogState.attrFilters[attr] = [];
		if (this.checked) {
			CatalogState.attrFilters[attr].push(val);
		} else {
			CatalogState.attrFilters[attr] = CatalogState.attrFilters[attr].filter(function(v) { return v !== val; });
			if (!CatalogState.attrFilters[attr].length) delete CatalogState.attrFilters[attr];
		}
		CatalogState.page = 1;
		fetchProducts(true);
	});

	$groups.find('.filter-group-title').on('click', function () { const collapsed = $(this).parent().toggleClass('collapsed').hasClass('collapsed'); $(this).attr('aria-expanded', !collapsed); });
	updateClearBtn();
}

function updateClearBtn() {
	var hasFilters = CatalogState.productType.length ||
		Object.keys(CatalogState.attrFilters).length ||
		CatalogState.search;
	$('#clearFilters').toggleClass('visible', !!hasFilters);
}

function clearAllFilters() {
	CatalogState.productType = [];
	CatalogState.attrFilters = {};
	CatalogState.search = '';
	CatalogState.page = 1;
	$('#catalogSearch').val('');
	// Re-render sidebar to clear checkmarks
	if (CatalogState.filterMeta) renderFilterSidebar(CatalogState.filterMeta);
	fetchProducts(true);
}

function toggleMobileFilters() {
	$('#filterSidebar').toggleClass('collapsed-mobile');
}

// ── Fetch & Render Products ─────────────────────────────────────────

function fetchProducts(replace, requestedPage) {
	var version = ++CatalogState.requestVersion;
	CatalogState.loading = true;
	$('#productGrid').attr('aria-busy', 'true');
	$('#catalogFeedback').text('Loading products...').removeClass('text-danger');
	$('#loadMoreBtn').prop('disabled', true);
	var filters = {};
	if (CatalogState.productType.length) {
		filters.product_type = CatalogState.productType;
	}
	Object.keys(CatalogState.attrFilters).forEach(function(k) {
		filters[k] = CatalogState.attrFilters[k];
	});

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.product_catalog.get_catalog_products',
		args: {
			filters: JSON.stringify(filters),
			search: CatalogState.search,
			page: requestedPage || CatalogState.page,
			page_size: CatalogState.pageSize
		},
		callback: function(r) {
			if (version !== CatalogState.requestVersion) return;
			if (!r.message || !r.message.success) { $('#catalogFeedback').text((r.message && r.message.error) || 'Products unavailable. Retry.').addClass('text-danger'); return; }
			var data = r.message;
			CatalogState.page = data.page;
			$('#catalogFeedback').text('');
			CatalogState.total = data.total;
			if (replace) {
				CatalogState.products = data.products;
			} else {
				CatalogState.products = CatalogState.products.concat(data.products);
			}
			renderGrid();
			pushUrlState();
			updateClearBtn();
		},
        error: function () { if (version === CatalogState.requestVersion) $('#catalogFeedback').text('Products unavailable. Check your connection or access, then retry.').addClass('text-danger'); },
        always: function () { if (version === CatalogState.requestVersion) { CatalogState.loading = false; $('#productGrid').attr('aria-busy', 'false'); $('#loadMoreBtn').prop('disabled', false); } }
	});
}

function renderGrid() {
	var $grid = $('#productGrid').empty();
	var products = CatalogState.products;

	if (!products.length) {
		$('#catalogEmpty').show();
		$('#loadMoreWrap').hide();
		$('#catalogResultCount').text('0 products');
		return;
	}
	$('#catalogEmpty').hide();
	$('#catalogResultCount').text(CatalogState.total + ' product' + (CatalogState.total !== 1 ? 's' : ''));

	products.forEach(function(p) {
		var detailUrl = productDetailHref(p.product_slug);
		var imgHtml;
		if (p.featured_image) {
			imgHtml = '<img class="product-card-img" src="' + escapeHtml(p.featured_image) +
				'" alt="' + escapeHtml(p.product_name) + '" loading="lazy">';
		} else {
			imgHtml = '<div class="product-card-img placeholder"><i class="fa fa-cube"></i></div>';
		}

		var priceHtml = '';
		if (p.price_per_ft_msrp != null) {
			priceHtml = '<span class="product-card-price">$' + Number(p.price_per_ft_msrp).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' / ft<small class="d-block">MSRP, before options</small></span>';
		}

		var actionHtml = '<a class="btn btn-sm btn-outline-primary product-card-details" href="' +
			escapeHtml(detailUrl) + '">' + __('View details') + '</a>';
		if (p.is_configurable) {
			actionHtml = '<a class="btn btn-sm btn-primary product-card-cta" href="' +
				escapeHtml(detailUrl + '#configure') + '">' + __('Configure') + '</a>' + actionHtml;
		} else if (p.capability === 'quantity') {
			actionHtml = '<a class="btn btn-sm btn-primary product-card-cta" href="' +
				escapeHtml(detailUrl + '#configure') + '">' + __('Add to schedule') + '</a>' + actionHtml;
		}

		var seriesBadge = p.series ? '<span class="badge badge-series">' + escapeHtml(p.series) + '</span>' : '';

		$grid.append(
			'<div class="product-card" data-slug="' + escapeHtml(p.product_slug) + '">' +
			imgHtml +
			'<div class="product-card-body">' +
			'<h5>' + escapeHtml(p.product_name) + '</h5>' +
			'<div class="product-card-meta">' +
			'<span class="badge badge-type">' + escapeHtml(productFamilyLabel(p.product_type)) + '</span>' +
			seriesBadge +
			'</div>' +
			'<div class="product-card-desc">' + escapeHtml(p.short_description || '') + '</div>' +
			'<div class="product-card-footer">' +
			priceHtml +
			actionHtml +
			'</div></div></div>'
		);
	});

	$grid.find('img').on('error', function () { $(this).replaceWith('<div class="product-card-img placeholder" role="img" aria-label="Image unavailable"><i class="fa fa-cube"></i></div>'); });

	// Navigate on card click (except the CTA link)
	$grid.off('click', '.product-card').on('click', '.product-card', function(e) {
		if ($(e.target).closest('a').length) return; // let links work normally
		var slug = this.getAttribute('data-slug');
		if (slug) window.location.href = productDetailHref(slug);
	});

	// Load-more button visibility
	var loaded = CatalogState.products.length;
	if (loaded < CatalogState.total) {
		$('#loadMoreWrap').show();
	} else {
		$('#loadMoreWrap').hide();
	}
}

function loadMore() {
	if (CatalogState.loading) return;
	fetchProducts(false, CatalogState.page + 1);
}

// ── Helpers ─────────────────────────────────────────────────────────

function escapeHtml(str) {
	if (!str) return '';
	var div = document.createElement('div');
	div.textContent = str;
	return div.innerHTML.replaceAll('"', '&quot;').replaceAll("'", "&#39;");
}

function productFamilyLabel(family) {
	return family === 'Fixture Template' ? __('Linear Fixtures') : family;
}

function productDetailHref(slug) {
	var params = new URLSearchParams(CatalogState.contextParams);
	var query = params.toString();
	return '/portal/products/' + encodeURIComponent(slug) + (query ? '?' + query : '');
}
