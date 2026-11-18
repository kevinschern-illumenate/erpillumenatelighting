/* Executes the checked-in gallery n8n code/branches against a local transport double. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const workflow = JSON.parse(fs.readFileSync('n8n_workflows/webflow_gallery_sync.json', 'utf8'));
const nodes = new Map(workflow.nodes.map(node => [node.name, node]));
const { projectWebflowGallery } = require('../../n8n_workflows/lib/gallery_projection.js');

const COLLECTION = 'b'.repeat(24);
const CREDIT_SLUGS = {
    Integrator: ['client-integrator', 'client-website'], Architect: ['architect', 'architect-website'],
    Designer: ['designer', 'designer-website'], Contractor: ['contractor', 'contractor-website'],
    Owner: ['owner', 'owner-website'], Photographer: ['photo-credit', 'photographer-website']
};
const FIELD_SLUGS = ['name', 'slug', 'erp-sync-id', 'featured', 'featured-image', 'gallery', 'short-description',
    'about', 'case-study', 'project-type', 'applications', 'services-provided', 'products-used', 'series-used',
    'product-notes', 'quote', 'quote-attribution', 'location', 'completion-date', 'videos', 'custom-items',
    ...Object.values(CREDIT_SLUGS).flat()];

function makePayload(index, overrides = {}) {
    const hero = {url: `https://erp.example.test/files/g${index}-1.jpg`, alt: 'Lobby cove'};
    return {
        schema_version: 1, erp_sync_id: `gallery-${index}`, slug: `gallery-${index}`, name: `Gallery ${index}`,
        featured: true, hero_image: hero,
        gallery_images: [hero, {url: `https://erp.example.test/files/g${index}-2.jpg`, alt: ''}],
        seo_description: 'A hotel lobby.', about: 'Warm and calm.', case_study_html: '<p>Case</p>',
        gallery_type: 'Hospitality', applications: ['Cove', 'Accent'], services_provided: ['Takeoff Drawings', 'Troubleshooting'],
        series_used: ['Rainier', 'Custom'], product_item_ids: ['c'.repeat(24), 'd'.repeat(24)],
        product_notes_html: '<p>Rainier: white</p>', quote: 'Lovely light.', quote_attribution: 'A. Owner',
        location: 'Austin, TX', completion_date: '2025-03-14',
        credits: {Integrator: {name: 'Bright Co', website: 'https://bright.example'}, Photographer: {name: 'P. Lens', website: ''}},
        videos: ['https://youtu.be/abc', 'https://vimeo.com/1'], custom_items_html: '<p>Kit: black</p>',
        active: true,
        brand: {brand_code: 'staging2', webflow_site_id: 'a'.repeat(24), galleries_collection_id: COLLECTION,
            erpnext_base_url: 'https://erp.example.test'},
        ...overrides
    };
}

function makeJob(index, operation = 'STAGE', remoteItemId = null, payload = makePayload(index)) {
    return {job: `GJOB${index}`, token: `token${index}`, revision_hash: `revision${index}`, payload_hash: `payload${index}`,
        operation, remote_item_id: remoteItemId, payload};
}

function remoteItem(id, slug, syncId, extra = {}) {
    return {id, isDraft: true, isArchived: false, live: false, fieldData: {name: slug, slug, 'erp-sync-id': syncId}, ...extra};
}

function execute(jobs, options = {}) {
    const queue = [...jobs], output = new Map(), counts = new Map(), receipts = [], requests = [];
    const remote = options.remote || new Map();
    let current = 'Manual Trigger', json = {}, steps = 0, creates = 0, transportFailed = false;
    while (current && ++steps < 30000) {
        const node = nodes.get(current);
        assert.ok(node, `Missing node ${current}`);
        const index = counts.get(current) || 0;
        counts.set(current, index + 1);
        const context = {$json: json, $input: {item: {json}}, $runIndex: index,
            $vars: {ILL_ERP_BASE_URL: 'https://erp.example.test', ILL_WEBFLOW_BRAND: 'staging2'},
            $: name => ({item: {json: output.get(name)}})};
        let branch = 0;
        if (node.type.endsWith('.code')) {
            json = vm.runInNewContext(`(function() {${node.parameters.jsCode}\n})()`, context).json;
        } else if (node.type.endsWith('.if')) {
            const expression = node.parameters.conditions.conditions[0].leftValue.slice(3, -2);
            branch = vm.runInNewContext(expression, context) ? 0 : 1;
        } else if (node.type.endsWith('.httpRequest')) {
            const url = vm.runInNewContext(node.parameters.url.slice(3, -2), context);
            const method = node.parameters.method.startsWith('=')
                ? vm.runInNewContext(node.parameters.method.slice(3, -2), context) : node.parameters.method;
            const body = node.parameters.jsonBody ? JSON.parse(vm.runInNewContext(node.parameters.jsonBody.slice(3, -2), context)) : undefined;
            requests.push({node: current, method, url, body});
            assert.ok(url.startsWith('https://erp.example.test/') || url.startsWith(`https://api.webflow.com/v2/collections/${COLLECTION}/items`), url);
            if (current === 'Claim Job') {
                assert.deepEqual(body, {brand: 'staging2', limit: 1});
                assert.ok(url.endsWith('.api.gallery_publication.claim'));
                json = {message: {jobs: queue.length ? [queue.shift()] : []}};
            } else if (current === 'Find Remote Item') {
                const byId = url.match(/\/items\/([a-f0-9]{24})$/);
                if (options.lookupRateLimit) json = {statusCode: 429, body: {message: 'slow down'}, headers: {'retry-after': '90'}};
                else if (options.lookupTransport) { branch = 1; json = {error: 'ECONNRESET'}; }
                else if (byId) {
                    const item = remote.get(byId[1]);
                    json = item ? {statusCode: 200, body: JSON.parse(JSON.stringify(item))} : {statusCode: 404, body: {}};
                } else {
                    assert.ok(url.endsWith('/items?limit=100&offset=0'), url);
                    const items = JSON.parse(JSON.stringify([...remote.values()]));
                    json = {statusCode: 200, body: {items, pagination: {limit: 100, offset: 0, total: options.total ?? items.length}}};
                }
            } else if (current === 'Write Staged Item') {
                if (options.rateLimit) json = {statusCode: 429, body: {message: 'slow down'}, headers: {'retry-after': '120'}};
                else if (method === 'POST') {
                    assert.ok(url.endsWith('/items'));
                    const id = (++creates).toString(16).padStart(24, '0');
                    remote.set(id, {id, live: false, ...JSON.parse(JSON.stringify(body))});
                    if (options.crashAfterCreate && !transportFailed) { branch = 1; json = {error: 'timeout'}; transportFailed = true; }
                    else json = {statusCode: 202, body: remote.get(id)};
                } else {
                    assert.equal(method, 'PATCH');
                    const id = url.split('/').pop(), item = remote.get(id);
                    assert.ok(item, 'PATCH of a missing item');
                    Object.assign(item, {isDraft: body.isDraft, isArchived: body.isArchived, fieldData: {...item.fieldData, ...body.fieldData}});
                    json = {statusCode: 200, body: item};
                }
            } else if (current === 'Publish Remote Item') {
                assert.ok(url.endsWith('/items/publish'));
                if (options.publishUnverified) json = {statusCode: 202, body: {publishedItemIds: [], errors: []}};
                else { body.itemIds.forEach(id => { remote.get(id).live = true; }); json = {statusCode: 202, body: {publishedItemIds: body.itemIds}}; }
            } else if (current === 'Unpublish Remote Item') {
                assert.equal(method, 'DELETE');
                remote.get(url.split('/').slice(-2)[0]).live = false;
                json = {statusCode: 204, body: {}};
            } else if (current === 'Archive Remote Item') {
                const item = remote.get(url.split('/').pop());
                if (options.archiveUnverified) json = {statusCode: 200, body: {...item}};
                else { Object.assign(item, body); json = {statusCode: 200, body: item}; }
            } else if (current === 'Record Success' || current === 'Record Failure') {
                assert.ok(url.endsWith('.api.gallery_publication.acknowledge'));
                receipts.push(body);
                json = {message: {state: current === 'Record Success' ? 'COMPLETE' : 'FAILED'}};
            } else throw new Error(`Unhandled HTTP node ${current}`);
        }
        output.set(current, json);
        current = workflow.connections[current]?.main[branch]?.[0]?.node;
    }
    assert.ok(steps < 30000, 'Workflow did not terminate');
    return {receipts, remote, creates, counts, requests};
}

const writes = run => run.requests.filter(row => row.node === 'Write Staged Item');

function test_projection_maps_every_field_slug() {
    const staged = projectWebflowGallery(makePayload(1), {isDraft: true});
    assert.equal(staged.isArchived, false);
    assert.equal(staged.isDraft, true);
    assert.equal(projectWebflowGallery(makePayload(1), {isDraft: false}).isDraft, false);
    const data = staged.fieldData;
    for (const slug of FIELD_SLUGS) assert.ok(slug in data, `missing ${slug}`);
    assert.deepEqual(Object.keys(data).sort(), [...FIELD_SLUGS].sort());
    assert.equal(data.name, 'Gallery 1');
    assert.equal(data.slug, 'gallery-1');
    assert.equal(data['erp-sync-id'], 'gallery-1');
    assert.equal(data.featured, true);
    assert.deepEqual(data['featured-image'], {url: 'https://erp.example.test/files/g1-1.jpg', alt: 'Lobby cove'});
    assert.deepEqual(data.gallery, [{url: 'https://erp.example.test/files/g1-1.jpg', alt: 'Lobby cove'},
        {url: 'https://erp.example.test/files/g1-2.jpg', alt: ''}]);
    assert.equal(data['short-description'], 'A hotel lobby.');
    assert.equal(data.about, 'Warm and calm.');
    assert.equal(data['case-study'], '<p>Case</p>');
    assert.equal(data['project-type'], 'Hospitality');
    assert.equal(data.applications, 'Cove, Accent');
    assert.equal(data['services-provided'], 'Takeoff Drawings, Troubleshooting');
    assert.deepEqual(data['products-used'], ['c'.repeat(24), 'd'.repeat(24)]);
    assert.equal(data['series-used'], 'Rainier, Custom');
    assert.equal(data['product-notes'], '<p>Rainier: white</p>');
    assert.equal(data.quote, 'Lovely light.');
    assert.equal(data['quote-attribution'], 'A. Owner');
    assert.equal(data.location, 'Austin, TX');
    assert.equal(data['completion-date'], '2025-03-14T00:00:00.000Z');
    assert.equal(data.videos, 'https://youtu.be/abc, https://vimeo.com/1');
    assert.equal(data['custom-items'], '<p>Kit: black</p>');
    assert.equal(data['client-integrator'], 'Bright Co');
    assert.equal(data['client-website'], 'https://bright.example');
    assert.equal(data['photo-credit'], 'P. Lens');
    // Emptied text fields are sent as '' so clearing a value in ERP clears it in Webflow.
    const cleared = projectWebflowGallery(makePayload(1, {quote: '', case_study_html: '', videos: [], applications: [],
        product_item_ids: [], hero_image: null, gallery_images: []}), {isDraft: true}).fieldData;
    assert.equal(cleared.quote, '');
    assert.equal(cleared['case-study'], '');
    assert.equal(cleared.videos, '');
    assert.equal(cleared.applications, '');
    assert.deepEqual(cleared['products-used'], []);
    assert.deepEqual(cleared.gallery, []);
    assert.equal(cleared['featured-image'], null);
    // completion-date is omitted (not sent) when ERP has none; an invalid date stops the projection.
    assert.equal('completion-date' in projectWebflowGallery(makePayload(1, {completion_date: null}), {isDraft: true}).fieldData, false);
    assert.throws(() => projectWebflowGallery(makePayload(1, {completion_date: 'March'}), {isDraft: true}));
    assert.throws(() => projectWebflowGallery(makePayload(1), {}));
}

function test_unfilled_credit_omitted() {
    const data = projectWebflowGallery(makePayload(2), {isDraft: true}).fieldData;
    // Rule: an unfilled pair is never sent as empty strings. A credit type missing from the payload sends
    // null for both slugs (clears a removed credit); a credit without a website sends null for the website.
    for (const type of ['Architect', 'Designer', 'Contractor', 'Owner']) {
        for (const slug of CREDIT_SLUGS[type]) {
            assert.ok(slug in data, `${slug} must be sent to clear a removed credit`);
            assert.equal(data[slug], null, `${slug} must be null, not an empty string`);
        }
    }
    assert.equal(data['photo-credit'], 'P. Lens');
    assert.equal(data['photographer-website'], null);
    assert.ok(!Object.entries(data).some(([slug, value]) => Object.values(CREDIT_SLUGS).flat().includes(slug) && value === ''));
    // Removing the Integrator credit clears both its slugs.
    const removed = projectWebflowGallery(makePayload(2, {credits: {}}), {isDraft: true}).fieldData;
    assert.equal(removed['client-integrator'], null);
    assert.equal(removed['client-website'], null);
}

function test_stage_creates_item_once() {
    const first = execute([makeJob(3)]);
    assert.equal(first.creates, 1);
    assert.equal(first.receipts.length, 1);
    const [receipt] = first.receipts;
    assert.equal(receipt.outcome, 'success');
    assert.match(receipt.remote_item_id, /^[a-f0-9]{24}$/);
    assert.deepEqual(Object.keys(receipt).sort(), ['job', 'outcome', 'payload_hash', 'remote_item_id', 'revision_hash', 'token']);
    assert.deepEqual([receipt.job, receipt.token, receipt.revision_hash, receipt.payload_hash], ['GJOB3', 'token3', 'revision3', 'payload3']);
    const created = first.remote.get(receipt.remote_item_id);
    assert.equal(created.isDraft, true);
    assert.equal(created.isArchived, false);
    assert.equal(created.fieldData['erp-sync-id'], 'gallery-3');
    assert.equal(first.counts.get('Publish Remote Item'), undefined, 'STAGE must not publish');
    // Restaging (ERP now knows the ID) updates the same item.
    const again = execute([makeJob(3, 'STAGE', receipt.remote_item_id, makePayload(3, {quote: 'Changed'}))], {remote: first.remote});
    assert.equal(again.creates, 0);
    assert.equal(writes(again)[0].method, 'PATCH');
    assert.equal(again.remote.size, 1);
    assert.equal(again.remote.get(receipt.remote_item_id).fieldData.quote, 'Changed');
    assert.equal(again.receipts[0].remote_item_id, receipt.remote_item_id);
}

function test_lost_ack_after_create_does_not_duplicate() {
    const interrupted = execute([makeJob(4)], {crashAfterCreate: true});
    assert.equal(interrupted.creates, 1);
    assert.equal(interrupted.receipts[0].outcome, 'error');
    assert.equal(interrupted.receipts[0].error_code, 'transport');
    assert.equal(interrupted.receipts[0].remote_item_id, null);
    // ERP never learned the ID: the retry claims with remote_item_id null and must find the item by erp-sync-id.
    const recovered = execute([makeJob(4)], {remote: interrupted.remote});
    assert.equal(recovered.creates, 0, 'Retry duplicated the remote item');
    assert.equal(recovered.remote.size, 1);
    assert.equal(recovered.receipts[0].outcome, 'success');
    assert.equal(recovered.receipts[0].remote_item_id, [...interrupted.remote.keys()][0]);
    assert.equal(writes(recovered)[0].method, 'PATCH');
    // Found by erp-sync-id even when someone changed the Webflow slug by hand.
    const renamed = interrupted.remote;
    [...renamed.values()][0].fieldData.slug = 'hand-edited';
    const again = execute([makeJob(4)], {remote: renamed});
    assert.equal(again.creates, 0);
    assert.equal(again.receipts[0].outcome, 'success');
}

function test_slug_fallback_verifies_erp_sync_id() {
    const id = 'e'.repeat(24);
    // Slug matches but the item belongs to another ERP record: stop, never overwrite or create.
    const foreign = execute([makeJob(5)], {remote: new Map([[id, remoteItem(id, 'gallery-5', 'someone-else')]])});
    assert.equal(foreign.receipts[0].outcome, 'error');
    assert.equal(foreign.receipts[0].error_code, 'identity-conflict');
    assert.equal(writes(foreign).length, 0);
    // Slug matches and erp-sync-id is empty: unverified, so also a conflict.
    const blank = execute([makeJob(5)], {remote: new Map([[id, remoteItem(id, 'gallery-5', '')]])});
    assert.equal(blank.receipts[0].error_code, 'identity-conflict');
    assert.equal(writes(blank).length, 0);
    // Slug matches and erp-sync-id agrees: updated in place.
    const own = execute([makeJob(5)], {remote: new Map([[id, remoteItem(id, 'gallery-5', 'gallery-5')]])});
    assert.equal(own.receipts[0].outcome, 'success');
    assert.equal(own.receipts[0].remote_item_id, id);
    assert.equal(writes(own)[0].method, 'PATCH');
    // Known ID (imported gallery) with no erp-sync-id yet and the same slug: backfilled.
    const imported = execute([makeJob(5, 'STAGE', id)], {remote: new Map([[id, remoteItem(id, 'gallery-5', '')]])});
    assert.equal(imported.receipts[0].outcome, 'success');
    assert.equal(imported.remote.get(id).fieldData['erp-sync-id'], 'gallery-5');
    // Known ID whose item carries another erp-sync-id: conflict.
    const swapped = execute([makeJob(5, 'STAGE', id)], {remote: new Map([[id, remoteItem(id, 'gallery-5', 'other')]])});
    assert.equal(swapped.receipts[0].error_code, 'identity-conflict');
    assert.equal(writes(swapped).length, 0);
    // More items than one page lists: absence cannot be proven, so nothing is created.
    const partial = execute([makeJob(5)], {total: 150});
    assert.equal(partial.receipts[0].error_code, 'lookup-incomplete');
    assert.equal(partial.creates, 0);
}

function test_two_matches_is_identity_conflict() {
    const one = 'f'.repeat(24), two = '1'.repeat(24);
    const duplicate = new Map([[one, remoteItem(one, 'gallery-6', 'gallery-6')], [two, remoteItem(two, 'gallery-6-copy', 'gallery-6')]]);
    const run = execute([makeJob(6)], {remote: duplicate});
    assert.equal(run.receipts[0].outcome, 'error');
    assert.equal(run.receipts[0].error_code, 'identity-conflict');
    assert.equal(writes(run).length, 0);
    // One item by erp-sync-id and another holding the slug is also two matches.
    const split = new Map([[one, remoteItem(one, 'old-slug', 'gallery-6')], [two, remoteItem(two, 'gallery-6', 'unrelated')]]);
    assert.equal(execute([makeJob(6)], {remote: split}).receipts[0].error_code, 'identity-conflict');
}

function test_publish_requires_staged_item() {
    const missing = execute([makeJob(7, 'PUBLISH')]);
    assert.equal(missing.receipts[0].outcome, 'error');
    assert.equal(missing.receipts[0].error_code, 'missing-staged-item');
    assert.equal(missing.creates, 0);
    assert.equal(writes(missing).length, 0);
    assert.equal(missing.counts.get('Publish Remote Item'), undefined);
    // A known ID that no longer exists in Webflow is also missing.
    const gone = execute([makeJob(7, 'PUBLISH', '9'.repeat(24))]);
    assert.equal(gone.receipts[0].error_code, 'missing-staged-item');
    assert.equal(writes(gone).length, 0);
    // With a staged item: written as non-draft, then published, then acknowledged.
    const staged = execute([makeJob(7)]);
    const id = staged.receipts[0].remote_item_id;
    const published = execute([makeJob(7, 'PUBLISH', id)], {remote: staged.remote});
    assert.equal(published.receipts[0].outcome, 'success');
    assert.equal(published.receipts[0].remote_item_id, id);
    assert.equal(published.creates, 0);
    assert.equal(writes(published)[0].body.isDraft, false);
    assert.equal(published.counts.get('Publish Remote Item'), 1);
    assert.deepEqual(published.requests.find(row => row.node === 'Publish Remote Item').body, {itemIds: [id]});
    assert.equal(published.remote.get(id).live, true);
    const unverified = execute([makeJob(7, 'PUBLISH', id)], {remote: staged.remote, publishUnverified: true});
    assert.equal(unverified.receipts[0].error_code, 'publication-unverified');
}

function test_retire_unpublishes_and_archives() {
    const staged = execute([makeJob(8)]);
    const id = staged.receipts[0].remote_item_id;
    execute([makeJob(8, 'PUBLISH', id)], {remote: staged.remote});
    const retired = execute([makeJob(8, 'RETIRE', id, makePayload(8, {active: false}))], {remote: staged.remote});
    assert.equal(retired.receipts[0].outcome, 'success');
    assert.equal(retired.receipts[0].remote_item_id, id);
    assert.equal(retired.counts.get('Unpublish Remote Item'), 1);
    assert.equal(retired.counts.get('Archive Remote Item'), 1);
    assert.equal(writes(retired).length, 0, 'RETIRE must not rewrite content');
    assert.ok(retired.requests.find(row => row.node === 'Unpublish Remote Item').url.endsWith(`/items/${id}/live`));
    assert.deepEqual(retired.requests.find(row => row.node === 'Archive Remote Item').body, {isArchived: true, isDraft: true});
    const item = retired.remote.get(id);
    assert.equal(item.live, false);
    assert.equal(item.isArchived, true);
    assert.equal(retired.remote.size, 1, 'RETIRE never deletes');
    const fresh = execute([makeJob(11)]);
    const unverified = execute([makeJob(11, 'RETIRE', fresh.receipts[0].remote_item_id)], {remote: fresh.remote, archiveUnverified: true});
    assert.equal(unverified.receipts[0].error_code, 'archive-unverified');
    // Nothing in Webflow: retirement is already done.
    const absent = execute([makeJob(9, 'RETIRE')]);
    assert.equal(absent.receipts[0].outcome, 'success');
    assert.equal(absent.counts.get('Unpublish Remote Item'), undefined);
}

function test_rate_limit_acknowledges_429_for_retry() {
    const limited = execute([makeJob(10)], {rateLimit: true});
    assert.equal(limited.receipts[0].outcome, 'error');
    assert.equal(limited.receipts[0].error_code, '429');
    assert.equal(limited.receipts[0].retry_after, '120');
    assert.ok(!JSON.stringify(limited.receipts).includes('slow down'), 'Webflow response bodies must not reach ERP');
    const lookup = execute([makeJob(10)], {lookupRateLimit: true});
    assert.equal(lookup.receipts[0].error_code, '429');
    assert.equal(lookup.receipts[0].retry_after, '90');
    assert.equal(writes(lookup).length, 0);
    const transport = execute([makeJob(10)], {lookupTransport: true});
    assert.equal(transport.receipts[0].error_code, 'transport');
    assert.ok(!JSON.stringify(transport.receipts).includes('ECONNRESET'));
}

function test_workflow_shape() {
    assert.equal(workflow.active, false);
    const schedule = workflow.nodes.find(node => node.type === 'n8n-nodes-base.scheduleTrigger');
    assert.ok(schedule, 'schedule trigger missing');
    assert.deepEqual(schedule.parameters.rule.interval, [{field: 'minutes', minutesInterval: 1}]);
    assert.equal(workflow.connections[schedule.name].main[0][0].node, 'Configuration');
    assert.equal(workflow.connections['Manual Trigger'].main[0][0].node, 'Configuration');
    assert.ok(workflow.nodes.every(node => !node.credentials), 'credentials must stay unbound');
    const text = JSON.stringify(workflow);
    assert.ok(!/6afb3d27742d050cf6903677|6aeb4d313e25a078e9393924|695c1f9a18a639365b6a31a7/.test(text), 'hard-coded IDs');
    assert.ok(!/Bearer |api[_-]?key|password/i.test(text), 'secrets in workflow');
    // A batch drains and claims once more to find the queue empty.
    const batch = execute(Array.from({length: 25}, (_, index) => makeJob(100 + index)));
    assert.equal(batch.receipts.length, 25);
    assert.equal(batch.creates, 25);
    assert.equal(batch.counts.get('Claim Job'), 26);
}

const tests = [test_projection_maps_every_field_slug, test_unfilled_credit_omitted, test_stage_creates_item_once,
    test_lost_ack_after_create_does_not_duplicate, test_slug_fallback_verifies_erp_sync_id, test_two_matches_is_identity_conflict,
    test_publish_requires_staged_item, test_retire_unpublishes_and_archives, test_rate_limit_acknowledges_429_for_retry,
    test_workflow_shape];
for (const test of tests) { test(); console.log(`ok ${test.name}`); }
console.log(`Gallery workflow: ${tests.length} tests passed`);
