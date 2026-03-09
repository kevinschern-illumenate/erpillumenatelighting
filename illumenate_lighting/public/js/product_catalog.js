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
	filterMeta: null
};

// ── Initialisation ──────────────────────────────────────────────────

function initProductCatalog() {
	loadFilterOptions();
	readUrlState();
	bindCatalogEvents();
	fetchProducts(true);
}

// ── URL state ───────────────────────────────────────────────────────

function readUrlState() {
	var params = new URLSearchParams(window.location.search);
	CatalogState.search = params.get('q') || '';
	$('#catalogSearch').val(CatalogState.search);

	var typeParam = params.get('type');
	CatalogState.productType = typeParam ? typeParam.split(',') : [];

	// Attribute filters encoded as ?Finish=White,Black&CCT=3000K
	params.forEach(function(val, key) {
		if (key === 'q' || key === 'type' || key === 'page') return;
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

function loadFilterOptions() {
	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.product_catalog.get_catalog_filter_options',
		callback: function(r) {
			if (r.message && r.message.success) {
				CatalogState.filterMeta = r.message;
				renderFilterSidebar(r.message);
			}
		}
	});
}

function renderFilterSidebar(data) {
	// Product type tabs
	var $tabs = $('#productTypeTabs').empty();
	(data.product_types || []).forEach(function(pt) {
		var active = CatalogState.productType.indexOf(pt.value) !== -1 ? ' active' : '';
		$tabs.append(
			'<span class="product-type-tab' + active + '" data-type="' +
			escapeHtml(pt.value) + '">' + escapeHtml(pt.value) +
			' <small class="text-muted">(' + pt.count + ')</small></span>'
		);
	});
	$tabs.off('click', '.product-type-tab').on('click', '.product-type-tab', function() {
		var type = $(this).data('type');
		$(this).toggleClass('active');
		// Rebuild array from active tabs
		CatalogState.productType = [];
		$tabs.find('.active').each(function() {
			CatalogState.productType.push($(this).data('type'));
		});
		CatalogState.page = 1;
		fetchProducts(true);
	});

	// Attribute filter groups
	var $groups = $('#filterGroups').empty();
	(data.filters || []).forEach(function(group) {
		var $g = $('<div class="filter-group">');
		$g.append(
			'<div class="filter-group-title" onclick="$(this).parent().toggleClass(\'collapsed\')">' +
			escapeHtml(group.attribute_type) +
			' <i class="fa fa-chevron-down"></i></div>'
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
		var attr = $(this).data('attr');
		var val = $(this).data('val');
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

function fetchProducts(replace) {
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
			page: CatalogState.page,
			page_size: CatalogState.pageSize
		},
		callback: function(r) {
			if (!r.message || !r.message.success) return;
			var data = r.message;
			CatalogState.total = data.total;
			if (replace) {
				CatalogState.products = data.products;
			} else {
				CatalogState.products = CatalogState.products.concat(data.products);
			}
			renderGrid();
			pushUrlState();
			updateClearBtn();
		}
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
		var imgHtml;
		if (p.featured_image) {
			imgHtml = '<img class="product-card-img" src="' + escapeHtml(p.featured_image) +
				'" alt="' + escapeHtml(p.product_name) + '" loading="lazy">';
		} else {
			imgHtml = '<div class="product-card-img placeholder"><i class="fa fa-cube"></i></div>';
		}

		var priceHtml = '';
		if (p.base_price_msrp) {
			priceHtml = '<span class="product-card-price">From $' + Number(p.base_price_msrp).toLocaleString() + '</span>';
		}

		var ctaLabel = p.is_configurable ? 'Configure' : 'View Details';
		var ctaClass = p.is_configurable ? 'btn-primary' : 'btn-outline-primary';

		var seriesBadge = p.series ? '<span class="badge badge-series">' + escapeHtml(p.series) + '</span>' : '';

		$grid.append(
			'<div class="product-card" data-slug="' + escapeHtml(p.product_slug) + '">' +
			imgHtml +
			'<div class="product-card-body">' +
			'<h5>' + escapeHtml(p.product_name) + '</h5>' +
			'<div class="product-card-meta">' +
			'<span class="badge badge-type">' + escapeHtml(p.product_type) + '</span>' +
			seriesBadge +
			'</div>' +
			'<div class="product-card-desc">' + escapeHtml(p.short_description || '') + '</div>' +
			'<div class="product-card-footer">' +
			priceHtml +
			'<a class="btn btn-sm product-card-cta ' + ctaClass + '" href="/portal/products/' +
			encodeURIComponent(p.product_slug) + '">' + ctaLabel + '</a>' +
			'</div></div></div>'
		);
	});

	// Navigate on card click (except the CTA link)
	$grid.off('click', '.product-card').on('click', '.product-card', function(e) {
		if ($(e.target).closest('a').length) return; // let links work normally
		var slug = $(this).data('slug');
		if (slug) window.location.href = '/portal/products/' + encodeURIComponent(slug);
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
	CatalogState.page++;
	fetchProducts(false);
}

// ── Helpers ─────────────────────────────────────────────────────────

function escapeHtml(str) {
	if (!str) return '';
	var div = document.createElement('div');
	div.textContent = str;
	return div.innerHTML;
}
