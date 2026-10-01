const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const jquery = require('jquery');

function setup() {
    const dom = new JSDOM('<body><input id="catalogSearch"><div id="productTypeTabs"></div><div id="filterGroups"></div><div id="productGrid"></div><p id="catalogFeedback"></p><p id="catalogResultCount"></p><div id="catalogEmpty"></div><div id="loadMoreWrap"><button id="loadMoreBtn"></button></div><button id="clearFilters"></button></body>', {runScripts: 'outside-only', url: 'https://portal.test/portal/products'});
    const w = dom.window, requests = [];
    w.$ = jquery(w); w.__ = (value) => value; w.frappe = {call: args => requests.push(args)};
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/product_catalog.js'), 'utf8'));
    return {dom, w, requests};
}

test('a stale catalog response cannot replace newer filters and failed paging can retry the same page', () => {
    const {dom, w, requests} = setup();
    w.fetchProducts(true); const old = requests.at(-1);
    w.CatalogState.search = 'new'; w.fetchProducts(true); const current = requests.at(-1);
    current.callback({message: {success: true, products: [{product_name: 'New', product_slug: 'new', product_type: 'LED Tape'}], total: 30, page: 1}}); current.always();
    old.callback({message: {success: true, products: [], total: 0, page: 1}}); old.always();
    assert.equal(w.document.querySelector('h5').textContent, 'New');
    w.loadMore(); requests.at(-1).error(); requests.at(-1).always();
    assert.equal(w.CatalogState.page, 1);
    w.loadMore(); assert.equal(requests.at(-1).args.page, 2);
    dom.window.close();
});

test('catalog filters are keyboard buttons and image attributes cannot inject markup', () => {
    const {dom, w} = setup();
    w.renderFilterSidebar({product_types: [{value: 'LED Tape', count: 1}], filters: [{attribute_type: 'CCT', options: [{value: '3000K', count: 1}]}]});
    const button = w.document.querySelector('.product-type-tab');
    assert.equal(button.tagName, 'BUTTON'); button.click(); assert.equal(button.getAttribute('aria-pressed'), 'true');
    const group = w.document.querySelector('.filter-group-title'); assert.equal(group.tagName, 'BUTTON'); group.click(); assert.equal(group.getAttribute('aria-expanded'), 'false');
    w.CatalogState.products = [{product_name: 'Name " onerror="alert(1)', product_slug: 'safe', product_type: 'LED Tape', featured_image: '/files/a.png" onerror="alert(1)', price_per_ft_msrp: 12.5}];
    w.renderGrid();
    assert.equal(w.document.querySelector('img').hasAttribute('onerror'), false);
    assert.match(w.document.querySelector('.product-card-price').textContent, /\$12\.50 \/ ft/);
    dom.window.close();
});

test('numeric filters stay strings and unknown query parameters are ignored', () => {
    const {dom, w, requests} = setup();
    dom.reconfigure({url: 'https://portal.test/portal/products?utm_source=x&CCT=90&finder=TOKEN'});
    w.CatalogState.filterMeta = {filters: [{attribute_type: 'CCT', options: [{value: '90', count: 1}]}]};
    w.readUrlState();
    w.renderFilterSidebar(w.CatalogState.filterMeta);
    w.fetchProducts(true);
    assert.deepEqual(Array.from(w.CatalogState.attrFilters.CCT), ['90']);
    assert.equal(typeof w.CatalogState.attrFilters.CCT[0], 'string');
    assert.equal(w.CatalogState.attrFilters.utm_source, undefined);
    assert.deepEqual(JSON.parse(requests.at(-1).args.filters), {CCT: ['90']});
    requests.at(-1).callback({message: {success: true, products: [{product_name: 'P', product_slug: 'p', product_type: 'Fixture Template', is_configurable: true}], total: 1, page: 1}});
    requests.at(-1).always();
    assert.match(w.document.querySelector('.product-card-details').href, /finder=TOKEN/);
    assert.equal(w.document.querySelector('.badge-type').textContent, 'Linear Fixtures');
    dom.window.close();
});

test('product type tabs show family labels and cards offer the action the product page supports', () => {
    const {dom, w} = setup();
    w.renderFilterSidebar({product_types: [{value: 'Fixture Template', count: 2}], filters: []});
    const tab = w.document.querySelector('.product-type-tab');
    assert.match(tab.textContent, /^Linear Fixtures/);
    assert.equal(tab.getAttribute('data-type'), 'Fixture Template');
    w.CatalogState.products = [
        {product_name: 'Fixture', product_slug: 'fixture', product_type: 'Fixture Template', is_configurable: true, capability: 'configure'},
        {product_name: 'Clip', product_slug: 'clip', product_type: 'Accessory', is_configurable: false, capability: 'quantity'},
        {product_name: 'Custom', product_slug: 'custom', product_type: 'Component', is_configurable: false, capability: 'inquiry'},
    ];
    w.CatalogState.total = 3;
    w.renderGrid();
    const ctas = Array.from(w.document.querySelectorAll('.product-card-cta')).map(a => [a.textContent, new w.URL(a.href).pathname + new w.URL(a.href).hash]);
    assert.deepEqual(ctas, [['Configure', '/portal/products/fixture#configure'], ['Add to schedule', '/portal/products/clip#configure']]);
    assert.equal(w.document.querySelectorAll('.product-card-details').length, 3);
    dom.window.close();
});

test('facet counts follow the other filters in place and ignore stale responses', () => {
    const {dom, w, requests} = setup();
    const meta = {
        product_types: [{value: 'LED Tape', count: 5}, {value: 'LED Neon', count: 2}],
        filters: [
            {attribute_type: 'CCT', options: [{value: '2700K', count: 3}, {value: '3000K', count: 4}]},
            {attribute_type: 'Finish', options: [{value: 'Black', count: 2}]},
        ],
    };
    w.CatalogState.filterMeta = meta;
    w.renderFilterSidebar(meta);
    const box = w.document.querySelector('input[data-val="3000K"]');
    box.checked = true;
    w.$(box).trigger('change');
    const facetCalls = requests.filter(r => r.method.endsWith('get_catalog_filter_options'));
    assert.equal(facetCalls.length, 1);
    assert.deepEqual(JSON.parse(facetCalls[0].args.filters), {CCT: ['3000K']});
    assert.ok(requests.at(-1).method.endsWith('get_catalog_products'));

    w.CatalogState.search = 'cove';
    w.fetchProducts(true);
    const latest = requests.filter(r => r.method.endsWith('get_catalog_filter_options')).at(-1);
    assert.equal(latest.args.search, 'cove');
    facetCalls[0].callback({message: {success: true, product_types: [], filters: []}});
    assert.equal(w.document.querySelector('.product-type-tab').style.display, '');

    latest.callback({message: {success: true,
        product_types: [{value: 'LED Tape', count: 1}],
        filters: [{attribute_type: 'CCT', options: [{value: '3000K', count: 0}]}]}});
    const tabs = Array.from(w.document.querySelectorAll('.product-type-tab'));
    assert.match(tabs[0].textContent, /\(1\)/);
    assert.equal(tabs[1].style.display, 'none');
    assert.strictEqual(w.document.querySelector('input[data-val="3000K"]'), box);
    assert.equal(box.closest('.filter-option').style.display, '');
    assert.equal(box.closest('.filter-option').querySelector('.count').textContent, '0');
    assert.equal(w.document.querySelector('input[data-val="2700K"]').closest('.filter-option').style.display, 'none');
    assert.equal(w.document.querySelector('input[data-attr="Finish"]').closest('.filter-group').style.display, 'none');
    dom.window.close();
});

test('active filter chips remove one filter, sync the sidebar and keep keyboard focus nearby', () => {
    const {dom, w, requests} = setup();
    w.document.body.insertAdjacentHTML('afterbegin', '<div id="activeFilterChips"></div>');
    const meta = {product_types: [{value: 'Fixture Template', count: 2}],
        filters: [{attribute_type: 'product_category', label: 'Application', options: [{value: 'Cove', count: 2}]},
                  {attribute_type: 'CCT', options: [{value: '3000K', count: 2}]}]};
    w.CatalogState.filterMeta = meta;
    w.CatalogState.productType = ['Fixture Template'];
    w.CatalogState.attrFilters = {product_category: ['Cove'], CCT: ['3000K']};
    w.renderFilterSidebar(meta);
    w.fetchProducts(true);
    const labels = () => Array.from(w.document.querySelectorAll('.active-filter-chip')).map(b => b.textContent);
    assert.deepEqual(labels(), ['Linear Fixtures ×', 'Application: Cove ×', 'CCT: 3000K ×']);
    const cove = w.document.querySelectorAll('.active-filter-chip')[1];
    cove.focus();
    cove.click();
    assert.deepEqual(JSON.parse(requests.at(-1).args.filters), {product_type: ['Fixture Template'], CCT: ['3000K']});
    assert.equal(w.document.querySelector('input[data-val="Cove"]').checked, false);
    assert.deepEqual(labels(), ['Linear Fixtures ×', 'CCT: 3000K ×']);
    assert.equal(w.document.activeElement.textContent, 'CCT: 3000K ×');
    w.document.querySelector('.active-filter-chip').click();
    assert.equal(w.document.querySelector('.product-type-tab').getAttribute('aria-pressed'), 'false');
    w.document.querySelector('.active-filter-chip').click();
    assert.deepEqual(labels(), []);
    assert.equal(w.document.activeElement.id, 'catalogSearch');
    dom.window.close();
});
