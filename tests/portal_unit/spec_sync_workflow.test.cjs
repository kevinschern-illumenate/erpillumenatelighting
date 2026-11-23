// The spec generator & Webflow sync workflow (W1 spec sheet, W2 product sync).
// n8n_workflows/spec_sync_staging.json is the live staging workflow, exported;
// n8n_workflows/spec_sync_production.json is built from it by tools/build_spec_sync_workflow.py
// (docs/superpowers/plans/2026-11-23-spec-sync-production-linear-fixtures.md).
const assert = require('assert');
const fs = require('fs');

const staging = JSON.parse(fs.readFileSync('n8n_workflows/spec_sync_staging.json', 'utf8'));

// The repo's paste-in copies of the large Code nodes.
const LIB_NODES = {
    'n8n_workflows/lib/spec_sheet_record.js': 'Get Product Info',
    'n8n_workflows/lib/ill_format_data_to_inject.js': '(ilL) Format Data to Inject',
    'n8n_workflows/lib/ill_transform_to_webflow.js': '(ilL) Transform to Webflow Format',
};

const node = (flow, name) => {
    const found = flow.nodes.find(item => item.name === name);
    assert.ok(found, `node ${name}`);
    return found;
};

function nodeRefs(flow) {
    const refs = [];
    const walk = value => {
        if (typeof value === 'string') {
            for (const match of value.matchAll(/\$\(\s*['"]([^'"]+)['"]\s*\)/g)) refs.push(match[1]);
        } else if (value && typeof value === 'object') {
            Object.values(value).forEach(walk);
        }
    };
    flow.nodes.forEach(item => walk(item.parameters));
    return refs;
}

// A leading run of // comment lines (the repo files' "paste into the node" header) is not code.
const body = code => code.trim().replace(/^(\/\/[^\n]*\n)+/, '').trim();

function test_lib_snippets_match_live_nodes() {
    for (const [file, name] of Object.entries(LIB_NODES)) {
        assert.equal(body(fs.readFileSync(file, 'utf8')), body(node(staging, name).parameters.jsCode), `${file} drifted from ${name}`);
    }
}

function test_staging_error_path_has_no_missing_node_refs() {
    const names = new Set(staging.nodes.map(item => item.name));
    const missing = nodeRefs(staging).filter(name => !names.has(name));
    assert.deepEqual([...new Set(missing)], [], 'expressions name nodes that do not exist');
}

// --- The production build --------------------------------------------------------------------

const PRODUCTION_FILE = 'n8n_workflows/spec_sync_production.json';
const production = () => JSON.parse(fs.readFileSync(PRODUCTION_FILE, 'utf8'));

function targets(flow, name) {
    return ((flow.connections[name] || {}).main || []).map(outs => (outs || []).map(out => out.node));
}

// Every node a path from `start` can reach (all outputs).
function reachable(flow, start) {
    const seen = new Set([start]);
    const queue = [start];
    while (queue.length) {
        for (const outs of targets(flow, queue.shift())) {
            for (const next of outs) if (!seen.has(next)) { seen.add(next); queue.push(next); }
        }
    }
    return seen;
}

function test_production_has_no_staging_values() {
    const text = JSON.stringify(production());
    for (const value of ['stagingillumenate', '6aeb4d313e25a078e9393924', '6aeb4d313e25a078e9393a2a', 'staging-', 'STAGING',
        '[staging]', '7UiZ55CCUG84sD4m', 'YXwJzXT13Mw9XMma', 'NDwBLpkiXEGmKznf', 'Staging Guard']) {
        assert.ok(!text.includes(value), `production build still contains ${value}`);
    }
    assert.ok(text.includes('https://app.illumenate.lighting/api/method/'), 'ERP calls use the production origin');
}

function test_production_webhooks_and_settings() {
    const flow = production();
    const hooks = Object.fromEntries(flow.nodes.filter(item => item.type === 'n8n-nodes-base.webhook')
        .map(item => [item.name, item.parameters.path]));
    assert.deepEqual(hooks, {'Webhook': 'ill-generate-spec-sheet', 'Webhook (ilL-Publish-Job)': 'ill-product-sync'});
    const ids = flow.nodes.filter(item => item.type === 'n8n-nodes-base.webhook').map(item => item.webhookId);
    for (const id of ids) assert.ok(!staging.nodes.some(item => item.webhookId === id), 'webhook ids are new');
    assert.equal(flow.active, false);
    assert.equal(flow.name, '[PROD] Spec Gen & Webflow Sync');
    assert.equal(flow.settings.saveDataSuccessExecution, 'none');
    assert.equal(flow.settings.saveManualExecutions, false);
    // n8n stores webhook headers, the shared secret included, with a run's data: failed runs too.
    assert.equal(flow.settings.saveDataErrorExecution, 'none');
    // The webhook secret credential is bound by hand after import (rotated, plan B4).
    for (const name of Object.keys(hooks)) assert.ok(!node(flow, name).credentials, `${name} stays unbound`);
    const erp = flow.nodes.filter(item => item.credentials && item.credentials.erpNextApi).map(item => item.credentials.erpNextApi.id);
    assert.ok(erp.length > 0 && erp.every(id => id === 'q5FbtRYh73x4yYeZ'));
}

function test_guard_removal_keeps_publish_path() {
    const flow = production();
    const names = new Set(flow.nodes.map(item => item.name));
    for (const [from, value] of Object.entries(flow.connections)) {
        assert.ok(names.has(from), `connection from missing node ${from}`);
        for (const outs of value.main || []) for (const out of outs || []) assert.ok(names.has(out.node), `${from} -> missing ${out.node}`);
    }
    assert.deepEqual(targets(flow, 'Should Publish? (Update)')[0], ['Brand: Publish (Update)']);
    assert.deepEqual(targets(flow, 'Should Publish? (New)')[0], ['Brand: Publish (New)']);
    assert.ok(reachable(flow, 'Should Publish? (Update)').has('(ilL) Publish Webflow Item (Update)'));
    assert.ok(reachable(flow, 'Should Publish? (New)').has('(ilL) Publish Webflow Item (New)'));
    assert.ok(reachable(flow, 'Webhook (ilL-Publish-Job)').has('(ilL) Webflow: Update Product'));
    assert.ok(reachable(flow, 'Webhook').has('Respond to Webhook: Success (W1)'));
    // The callback after each write is still wired.
    assert.ok(reachable(flow, '(ilL) Webflow: Update Product').has('(Update) Respond to ilL-Publication-Job'));
}

function test_206_routes_to_brand_not_enabled() {
    const flow = production();
    for (const name of ['Switch', 'Split by Brand', 'Brand: Update Product', 'Brand: New Product', 'Brand: Publish (Update)', 'Brand: Publish (New)']) {
        assert.deepEqual(targets(flow, name)[1], ['Brand not enabled'], `${name} 206 output`);
    }
    assert.ok(!flow.nodes.some(item => item.name.startsWith('(206)')), 'no 206 nodes');
    const refusal = node(flow, 'Brand not enabled');
    assert.equal(refusal.type, 'n8n-nodes-base.respondToWebhook');
    assert.equal(refusal.parameters.options.responseCode, 409);
}

function test_production_has_no_missing_node_refs() {
    const flow = production();
    const names = new Set(flow.nodes.map(item => item.name));
    const missing = nodeRefs(flow).filter(name => !names.has(name));
    assert.deepEqual([...new Set(missing)], [], 'expressions name removed nodes');
}

function test_transform_fails_closed_and_knows_published() {
    const code = node(production(), '(ilL) Transform to Webflow Format').parameters.jsCode;
    assert.ok(/case\s+["']Published["']/.test(code), 'Published case');
    assert.ok(/default:/.test(code), 'fail-closed default');
}

function test_template_fetch_reads_main_site() {
    const url = node(production(), '(ilL) Fetch Webflow Template').parameters.url;
    assert.ok(url.startsWith('=https://illumenate.lighting/spec-sheet-templates/'), url);
}

function test_build_is_reproducible() {
    const before = fs.readFileSync(PRODUCTION_FILE, 'utf8');
    require('child_process').execFileSync('python3', ['-I', 'tools/build_spec_sync_workflow.py', '--env', 'production']);
    assert.equal(fs.readFileSync(PRODUCTION_FILE, 'utf8'), before, 'the committed build is stale; rebuild it');
}

const tests = [test_lib_snippets_match_live_nodes, test_staging_error_path_has_no_missing_node_refs,
    test_production_has_no_staging_values, test_production_webhooks_and_settings, test_guard_removal_keeps_publish_path,
    test_206_routes_to_brand_not_enabled, test_production_has_no_missing_node_refs, test_transform_fails_closed_and_knows_published, test_template_fetch_reads_main_site,
    test_build_is_reproducible];

let failed = 0;
for (const test of tests) {
    try {
        test();
        console.log(`ok ${test.name}`);
    } catch (error) {
        failed += 1;
        console.log(`not ok ${test.name}\n  ${error.message.split('\n').slice(0, 6).join('\n  ')}`);
    }
}
if (failed) {
    console.log(`${failed} of ${tests.length} failed`);
    process.exit(1);
}
console.log(`${tests.length} passed`);
