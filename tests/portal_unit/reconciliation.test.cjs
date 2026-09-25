const {test} = require('node:test');
const assert = require('node:assert/strict');
const {compareContent, audit, requestJSON} = require('../../tools/reconcile_webflow.cjs');
const {projectWebflowProduct} = require('../../n8n_workflows/lib/product_projection.js');
const id = 'a'.repeat(24), collection = 'b'.repeat(24);
const payload = name => ({brand: {brand_code: 'a', erpnext_base_url: 'https://erp.example.test', include_configurator_payload: true},
    product: {product_slug: 'tape', product_name: name, product_type: 'LED Tape', documents: [], specifications: [], configurator_options: [], gallery_images: [], certifications: []}});
const remote = p => ({id, ...projectWebflowProduct({...p.product, webflow_item_id: id}, p.brand).json.webflowData});
test('detects manual CMS edits even with unchanged ERP identity', async () => {
    const p = payload('Original'), r = remote(p); r.fieldData.name = 'Edited remotely';
    const result = await compareContent(p, id, r);
    assert.equal(result.status, 'DRIFT'); assert.deepEqual(result.fields, ['name']);
});
test('new staged content and last-good live content are checked independently', async () => {
    const p1 = payload('Old live'), p2 = payload('New staged');
    const row = {name: 'PUB', collection_id: collection, remote_item_id: id, staged_hash: 'v2', live_hash: 'v1', staged_payload: p2, live_payload: p1};
    const result = await audit(row, async url => remote(url.endsWith('/live') ? p1 : p2));
    assert.equal(result.status, 'MATCH');
});
test('missing live item and unexpected live item both fail', async () => {
    const p = payload('Product'), row = {collection_id: collection, remote_item_id: id, staged_hash: 'v1', staged_payload: p, live_hash: 'v1', live_payload: p};
    assert.equal((await audit(row, async url => url.endsWith('/live') ? null : remote(p))).live.status, 'DRIFT');
    row.live_hash = null;
    assert.deepEqual((await audit(row, async () => remote(p))).live.fields, ['unexpected_live_item']);
});
test('retirement requires remote absence or archival and no live item', async () => {
    const row = {state: 'RETIRED', collection_id: collection, remote_item_id: id};
    assert.equal((await audit(row, async () => null)).status, 'MATCH');
    assert.equal((await audit(row, async url => url.endsWith('/live') ? null : remote(payload('Active')))).status, 'DRIFT');
});
test('asset URLs are compared by bytes and inaccessible assets remain unverified', async () => {
    const p = payload('Image'); p.product.featured_image = '/files/product.png';
    const r = remote(p); r.fieldData['featured-image'].url = 'https://cdn.website-files.com/copied.png';
    assert.equal((await compareContent(p, id, r, async () => 'same-sha256')).status, 'MATCH');
    assert.equal((await compareContent(p, id, r, async url => url)).status, 'DRIFT');
    assert.equal((await compareContent(p, id, r, async () => { throw Error('denied'); })).status, 'UNVERIFIED');
});
test('HTTP throttling retries boundedly without logging response bodies', async () => {
    let attempts = 0; const delays = [];
    const value = await requestJSON('https://api.webflow.com/test', {}, async () => ++attempts < 3
        ? {status: 429, headers: new Headers({'retry-after': '2'})}
        : {status: 200, ok: true, json: async () => ({ok: true})}, async delay => delays.push(delay));
    assert.deepEqual(value, {ok: true}); assert.deepEqual(delays, [2000, 2000]);
});
