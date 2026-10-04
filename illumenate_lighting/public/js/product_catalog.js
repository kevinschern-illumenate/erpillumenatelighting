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
	facetVersion: 0,
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

	var reserved = ['finder', 'schedule', 'line_key', 'line_idx', 'draft', 'view'];
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
		args: {finder: CatalogState.contextParams.finder, view: CatalogState.contextParams.view},
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
	var filters = currentFilters();
	if (replace) {
		refreshFacetCounts(filters);
		renderActiveFilterChips();
	}

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.product_catalog.get_catalog_products',
		args: {
			filters: JSON.stringify(filters),
			search: CatalogState.search,
			page: requestedPage || CatalogState.page,
			page_size: CatalogState.pageSize,
			finder: CatalogState.contextParams.finder, view: CatalogState.contextParams.view,
			sort: CatalogState.contextParams.finder ? "relevance" : "product_name asc"
		},
		callback: function(r) {
			if (version !== CatalogState.requestVersion) return;
			if (!r.message || !r.message.success) { $('#catalogFeedback').text((r.message && r.message.error) || 'Products unavailable. Retry.').addClass('text-danger'); return; }
			var data = r.message;
			renderFinderContext(data.finder);
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
			'<h5>' + escapeHtml(p.product_name) + '</h5>' + finderCardChips(p) +
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

function currentFilters() {
	var filters = {};
	if (CatalogState.productType.length) {
		filters.product_type = CatalogState.productType;
	}
	Object.keys(CatalogState.attrFilters).forEach(function(k) {
		filters[k] = CatalogState.attrFilters[k];
	});
	return filters;
}

// ── Facet counts ────────────────────────────────────────────────────
//
// Counts follow the other active filters and the search, so a count is
// the number of results ticking that value would give. They are updated
// in place (not re-rendered) so the checkbox a dealer just used keeps focus.

function refreshFacetCounts(filters) {
	if (!CatalogState.filterMeta) return;
	var version = ++CatalogState.facetVersion;
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.product_catalog.get_catalog_filter_options',
		args: {filters: JSON.stringify(filters), search: CatalogState.search, finder: CatalogState.contextParams.finder, view: CatalogState.contextParams.view},
		callback: function(r) {
			if (version !== CatalogState.facetVersion || !r.message || !r.message.success) return;
			applyFacetCounts(r.message);
		}
	});
}

function applyFacetCounts(data) {
	var typeCounts = {};
	(data.product_types || []).forEach(function(pt) { typeCounts[pt.value] = pt.count; });
	$('#productTypeTabs .product-type-tab').each(function() {
		var value = this.getAttribute('data-type');
		var count = typeCounts[value] || 0;
		$(this).find('small').text('(' + count + ')');
		$(this).toggle(count > 0 || CatalogState.productType.indexOf(value) !== -1);
	});

	var counts = {};
	(data.filters || []).forEach(function(group) {
		(group.options || []).forEach(function(opt) {
			counts[group.attribute_type + '\u0000' + opt.value] = opt.count;
		});
	});
	$('#filterGroups .filter-group').each(function() {
		var visible = 0;
		$(this).find('input[type=checkbox]').each(function() {
			var count = counts[this.getAttribute('data-attr') + '\u0000' + this.getAttribute('data-val')] || 0;
			var $option = $(this).closest('.filter-option');
			var show = count > 0 || this.checked;
			$option.find('.count').text(count);
			$option.toggle(show);
			if (show) visible++;
		});
		$(this).toggle(visible > 0);
	});
}

// ── Active filter chips ─────────────────────────────────────────────

function renderActiveFilterChips() {
	var $chips = $('#activeFilterChips').empty();
	function chip(kind, attr, value, text) {
		$chips.append($('<button type="button" class="active-filter-chip">')
			.attr({'data-kind': kind, 'data-attr': attr, 'data-val': value, 'aria-label': __('Remove filter {0}', [text])})
			.text(text + ' \u00d7'));
	}
	CatalogState.productType.forEach(function(value) { chip('type', '', value, productFamilyLabel(value)); });
	Object.keys(CatalogState.attrFilters).forEach(function(attr) {
		CatalogState.attrFilters[attr].forEach(function(value) { chip('attr', attr, value, facetLabel(attr) + ': ' + value); });
	});
	$chips.off('click', '.active-filter-chip').on('click', '.active-filter-chip', function() {
		removeFilter(this.getAttribute('data-kind'), this.getAttribute('data-attr'), this.getAttribute('data-val'));
	});
}

function facetLabel(attr) {
	var group = ((CatalogState.filterMeta && CatalogState.filterMeta.filters) || [])
		.find(function(row) { return row.attribute_type === attr; });
	return (group && group.label) || attr;
}

function removeFilter(kind, attr, value) {
	var index = $('#activeFilterChips .active-filter-chip').index(document.activeElement);
	if (kind === 'type') {
		CatalogState.productType = CatalogState.productType.filter(function(v) { return v !== value; });
		$('#productTypeTabs .product-type-tab').each(function() {
			if (this.getAttribute('data-type') === value) $(this).removeClass('active').attr('aria-pressed', 'false');
		});
	} else {
		CatalogState.attrFilters[attr] = (CatalogState.attrFilters[attr] || []).filter(function(v) { return v !== value; });
		if (!CatalogState.attrFilters[attr].length) delete CatalogState.attrFilters[attr];
		$('#filterGroups input[type=checkbox]').each(function() {
			if (this.getAttribute('data-attr') === attr && this.getAttribute('data-val') === value) this.checked = false;
		});
	}
	CatalogState.page = 1;
	fetchProducts(true);
	// Keep keyboard users in the chip row, or return them to search when it empties.
	var $remaining = $('#activeFilterChips .active-filter-chip');
	($remaining.length ? $remaining.eq(Math.min(Math.max(index, 0), $remaining.length - 1)) : $('#catalogSearch')).trigger('focus');
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

function finderCardChips(product) {
	var match = product.match || {};
	var html = match.best ? '<span class="badge badge-primary">Best match</span> ' : '';
	html += (match.reasons || []).slice(0, 2).map(function (text) { return '<span class="badge badge-success">' + escapeHtml(text) + '</span> '; }).join('');
	if ((match.verify || []).length) html += '<span class="badge badge-warning" title="' + escapeHtml(match.verify.join(', ')) + '">Verify with our team</span>';
	if (product.relation) html += '<p class="small">' + escapeHtml(product.relation) + '</p>';
	return html;
}
function renderFinderContext(info) {
	var $banner = $('#finderBanner').empty();
	if (!info) { $banner.hide(); return; }
	$banner.show();
	var edit = '/portal/product-finder?session=' + encodeURIComponent(info.token);
	$banner.append($('<strong>').text('Showing ' + info.counts.match + ' products that fit your answers · ' + info.counts.verify + ' need a quick check with our team'));
	var chips = $('<div class="my-2">');
	(info.answer_chips || []).forEach(function (chip) { chips.append($('<a class="badge badge-light mr-1">').attr('href', edit + '#' + encodeURIComponent(chip.question_id)).text(chip.label)); });
	$banner.append(chips);
	if ((info.relaxed || []).length) $banner.append($('<p>').text('Preferences broadened: ' + info.relaxed.join(', ')));
	$banner.append($('<a class="mr-3">').attr('href', edit).text('Edit answers'), $('<a class="mr-3">').attr('href', '/portal/product-finder').text('Start over'));
	var tabs = $('<div class="btn-group mt-3 d-flex" role="group" aria-label="Product views">');
	[['Recommended (' + info.counts.match + ')',''],['Drivers, controllers & accessories (' + info.companions_count + ')','companions'],['All products','all']].forEach(function (tab) {
		tabs.append($('<button type="button" class="btn btn-outline-primary">').text(tab[0]).attr('aria-pressed', (CatalogState.contextParams.view || '') === tab[1]).on('click', function () {
			if(tab[1] === 'all') { delete CatalogState.contextParams.finder; delete CatalogState.contextParams.view; }
			else CatalogState.contextParams.view = tab[1];
			CatalogState.page = 1; pushUrlState(); fetchProducts(true);
		}));
	});
	$banner.append(tabs);
	if (!info.counts.match) {
		$('#catalogEmpty').empty().append($('<h3>').text('No products match ' + (info.eliminated_by ? info.eliminated_by.answer : 'these answers')), $('<a class="btn btn-link">').attr('href', edit + (info.eliminated_by ? '#' + encodeURIComponent(info.eliminated_by.question) : '')).text('Edit answers'), $('<button type="button" class="btn btn-primary">').text('Ask our team').on('click', function () {
			var button = $(this).prop('disabled', true);
			frappe.call({method:'illumenate_lighting.illumenate_lighting.api.product_finder.request_verification',type:'POST',args:{token:info.token},callback:function(r){button.text('Request ' + r.message.request + ' sent');},error:function(){button.prop('disabled',false);}});
		}));
	}
}
