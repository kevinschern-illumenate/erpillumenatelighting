const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const jquery = require('jquery');

function setup() {
    const dom = new JSDOM('<body><input id="catalogSearch"><div id="productTypeTabs"></div><div id="filterGroups"></div><div id="productGrid"></div><p id="catalogFeedback"></p><p id="catalogResultCount"></p><div id="catalogEmpty"></div><div id="loadMoreWrap"><button id="loadMoreBtn"></button></div><button id="clearFilters"></button></body>', {runScripts: 'outside-only', url: 'https://portal.test/portal/products'});
    const w = dom.window, requests = [];
    w.$ = jquery(w); w.frappe = {call: args => requests.push(args)};
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
    w.CatalogState.products = [{product_name: 'Name " onerror="alert(1)', product_slug: 'safe', product_type: 'LED Tape', featured_image: '/files/a.png" onerror="alert(1)', base_price_msrp: 0}];
    w.renderGrid();
    assert.equal(w.document.querySelector('img').hasAttribute('onerror'), false);
    assert.match(w.document.querySelector('.product-card-price').textContent, /Base MSRP \$0/);
    dom.window.close();
});
