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

const tests = [test_lib_snippets_match_live_nodes, test_staging_error_path_has_no_missing_node_refs];

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
