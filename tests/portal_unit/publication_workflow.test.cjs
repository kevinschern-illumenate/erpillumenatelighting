/* Executes the checked-in n8n code/branches against a local transport double. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const workflow = JSON.parse(fs.readFileSync('n8n_workflows/webflow_product_sync.json', 'utf8'));
const nodes = new Map(workflow.nodes.map(node => [node.name, node]));
const { projectWebflowProduct } = require('../../n8n_workflows/lib/product_projection.js');

function makeJob(index, operation = 'STAGE') {
    return {
        job: `JOB${index}`, token: `token${index}`, revision_hash: `revision${index}`, payload_hash: `payload${index}`,
        operation, payload: {projection_version: 1, product_slug: `product-${index}`,
            brand: {collections: {Products: 'a'.repeat(24)}, erpnext_base_url: 'https://erp.example.test', include_configurator_payload: true},
            product: {product_slug: `product-${index}`, product_name: `Product ${index}`, product_type: 'LED Tape',
                is_configurable: 1, documents: [], specifications: [], configurator_options: [], gallery_images: [], certifications: []}}
    };
}

function execute(jobs, options = {}) {
    const queue = [...jobs], output = new Map(), counts = new Map(), receipts = [], remote = options.remote || new Map();
    let current = 'Manual Trigger', json = {}, steps = 0, creates = 0, transportFailed = false;
    while (current && ++steps < 30000) {
        const node = nodes.get(current);
        assert.ok(node, `Missing node ${current}`);
        const index = counts.get(current) || 0;
        counts.set(current, index + 1);
        const context = {$json: json, $input: {item: {json}}, $runIndex: index,
            $vars: {ILL_ERP_BASE_URL: 'https://erp.example.test', ILL_WEBFLOW_BRAND: 'a'},
            $: name => ({item: {json: output.get(name)}})};
        let branch = 0;
        if (node.type.endsWith('.code')) {
            json = vm.runInNewContext(`(function() {${node.parameters.jsCode}\n})()`, context).json;
        } else if (node.type.endsWith('.if')) {
            const expression = node.parameters.conditions.conditions[0].leftValue.slice(3, -2);
            branch = vm.runInNewContext(expression, context) ? 0 : 1;
        } else if (node.type.endsWith('.httpRequest')) {
            const expression = node.parameters.url.slice(3, -2);
            const url = vm.runInNewContext(expression, context);
            assert.ok(url.startsWith('https://erp.example.test/') || url.startsWith('https://api.webflow.com/v2/'));
            const job = output.get('Prepare Claim');
            if (current === 'Claim Job') json = {message: {jobs: queue.length ? [queue.shift()] : []}};
            else if (current === 'Find Remote Item') {
                const items = [...remote.values()].filter(item => item.fieldData['erp-sync-id'] === job.payload.product_slug);
                json = {statusCode: 200, body: {items, pagination: {total: items.length}}};
            } else if (current === 'Write Staged Item') {
                const write = output.get('Prepare Write');
                if (options.rateLimit) json = {statusCode: 429, body: {}, headers: {'retry-after': '120'}};
                else {
                    const id = write.remote_item_id || (++creates).toString(16).padStart(24, '0');
                    const item = {...JSON.parse(JSON.stringify(write.write_body)), id};
                    remote.set(id, item);
                    if (options.crashAfterCreate && !transportFailed) { branch = 1; json = {error: 'timeout'}; transportFailed = true; }
                    else json = {statusCode: 200, body: item};
                }
            } else if (current === 'Publish Remote Item') json = {statusCode: 200, body: {publishedItemIds: [json.remote_item_id]}};
            else if (current === 'Unpublish Remote Item') json = {statusCode: 204, body: {}};
            else if (current === 'Archive Remote Item') json = {statusCode: 200, body: {isArchived: true}};
            else if (current === 'Record Success' || current === 'Record Failure') {
                const bodyExpression = node.parameters.jsonBody.slice(3, -2);
                receipts.push(JSON.parse(vm.runInNewContext(bodyExpression, context)));
                json = {message: {state: current === 'Record Success' ? 'COMPLETE' : 'FAILED'}};
            } else throw new Error(`Unhandled HTTP node ${current}`);
        }
        output.set(current, json);
        current = workflow.connections[current]?.main[branch]?.[0]?.node;
    }
    assert.ok(steps < 30000, 'Workflow did not terminate');
    return {receipts, remote, creates, counts};
}

const batch = execute(Array.from({length: 123}, (_, index) => makeJob(index)));
assert.equal(batch.receipts.length, 123);
assert.equal(batch.creates, 123);
assert.ok(batch.receipts.every(row => row.outcome === 'success'));
assert.equal(batch.counts.get('Claim Job'), 124);

const interrupted = execute([makeJob(1)], {crashAfterCreate: true});
assert.equal(interrupted.receipts[0].outcome, 'error');
const recovered = execute([makeJob(1)], {remote: interrupted.remote});
assert.equal(recovered.creates, 0, 'Retry duplicated the remote item');
assert.equal(recovered.receipts[0].outcome, 'success');

const limited = execute([makeJob(2)], {rateLimit: true});
assert.equal(limited.receipts[0].error_code, '429');
assert.equal(limited.receipts[0].retry_after, '120');
const duplicate = new Map([
    ['1', {id: '1', fieldData: {'erp-sync-id': 'product-1'}}],
    ['2', {id: '2', fieldData: {'erp-sync-id': 'product-1'}}]
]);
assert.equal(execute([makeJob(1)], {remote: duplicate}).receipts[0].error_code, 'identity-conflict');

const publishing = execute([makeJob(1, 'PUBLISH')], {remote: recovered.remote});
assert.equal(publishing.receipts[0].outcome, 'success');
assert.equal(publishing.counts.get('Publish Remote Item'), 1);
const retiring = execute([makeJob(1, 'RETIRE')], {remote: recovered.remote});
assert.equal(retiring.receipts[0].outcome, 'success');
assert.equal(retiring.counts.get('Unpublish Remote Item'), 1);
assert.equal(retiring.counts.get('Archive Remote Item'), 1);

const stripped = projectWebflowProduct(makeJob(3).payload.product, {...makeJob(3).payload.brand, include_configurator_payload: false});
assert.equal(stripped.json.webflowData.fieldData['configurator-options-json'], undefined);
console.log('Publication workflow: 123-job drain, create recovery, 429, identity conflict, publish, retirement, brand stripping passed');
