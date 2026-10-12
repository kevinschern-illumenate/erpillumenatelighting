import test from 'node:test';
import assert from 'node:assert/strict';
import { createErpApi, ErpError, frappeMessage, slug, deskUrl, recordCounts } from '../src/erp-api.js';

test('Frappe errors decode nested messages and tolerate malformed error bodies', () => {
  assert.equal(frappeMessage({ _server_messages: JSON.stringify([JSON.stringify({ message: 'First' }), JSON.stringify({ message: 'Second' })]) }), 'First\nSecond');
  assert.equal(frappeMessage({ _server_messages: JSON.stringify(['Plain message']) }), 'Plain message');
  assert.equal(frappeMessage({ _server_messages: '{bad', exception: 'Validation failed' }), 'Validation failed');
  assert.equal(frappeMessage({ _server_messages: '{}', exc_type: 'ValidationError' }), 'ValidationError');
  assert.equal(frappeMessage({}), '');
});

test('all endpoints use same-origin credentials, encoded queries, and exact CSRF POST bodies', async () => {
  const calls = [];
  const api = createErpApi({ csrfToken: 'csrf-value', fetchImpl: async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ message: { success: true } }) };
  } });
  assert.deepEqual(await api.reference(), { success: true });
  await api.reference(true);
  await api.record('ilL-Rel-Profile Lens', 'A&B +/?');
  const catalog = { series_name: 'Unicode café', records: { Item: [{ item_code: 'A' }] } };
  await api.check(catalog);
  await api.importCatalog(catalog, 'checked-hash');
  await api.history();
  await api.designReadiness();
  assert.deepEqual(calls.map(call => new URL(call.url, 'https://test').pathname.split('.').at(-1)), ['reference', 'reference', 'record', 'check', 'import_catalog', 'history', 'design_readiness']);
  assert.ok(calls[1].url.endsWith('?refresh=1'));
  const query = new URL(calls[2].url, 'https://test').searchParams;
  assert.equal(query.get('doctype'), 'ilL-Rel-Profile Lens');
  assert.equal(query.get('name'), 'A&B +/?');
  for (const { options } of calls) {
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers.Accept, 'application/json');
  }
  for (const { options } of calls.slice(3, 5)) {
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.equal(options.headers['X-Frappe-CSRF-Token'], 'csrf-value');
  }
  assert.deepEqual(JSON.parse(calls[3].options.body), { catalog });
  assert.deepEqual(JSON.parse(calls[4].options.body), { catalog, expected_hash: 'checked-hash' });
  assert.equal(calls[5].options.body, undefined);
});

test('session and CSRF failures include reload advice and an actionable session flag', async () => {
  for (const [status, data] of [[401, {}], [403, {}], [400, { exc_type: 'CSRFTokenError' }]]) {
    const api = createErpApi({ csrfToken: '', fetchImpl: async () => ({ ok: false, status, json: async () => data }) });
    await assert.rejects(api.check({}), error => error instanceof ErpError && error.status === status && error.sessionExpired && /Reload the page/.test(error.message));
  }
});

test('HTTP and non-JSON failures remain errors, including a successful login HTML redirect', async () => {
  for (const [ok, status] of [[false, 502], [true, 200]]) {
    const api = createErpApi({ fetchImpl: async () => ({ ok, status, json: async () => { throw new Error('HTML'); } }) });
    await assert.rejects(api.history(), error => error instanceof ErpError && error.status === status);
  }
  const api = createErpApi({ fetchImpl: async () => ({ ok: false, status: 417, json: async () => ({ exception: 'Permission denied' }) }) });
  await assert.rejects(api.record('Item', 'A'), /Permission denied/);
});

test('an uncertain import is never automatically retried', async () => {
  let attempts = 0;
  const api = createErpApi({ fetchImpl: async () => { attempts += 1; throw new Error('Connection lost'); } });
  await assert.rejects(api.importCatalog({}, 'hash'), /Connection lost/);
  assert.equal(attempts, 1);
});

test('Desk links slug DocTypes and encode record names as one path segment', () => {
  assert.equal(slug('ilL-Rel-Profile Lens'), 'ill-rel-profile-lens');
  assert.equal(deskUrl('Item Price', 'A/B &?#'), '/app/item-price/A%2FB%20%26%3F%23');
});

test('confirmation counts include parent records, excluding empty DocTypes and child rows', () => {
  assert.deepEqual(recordCounts({ records: { Item: [{ taxes: [{}, {}] }, {}], Brand: [], 'ilL-Extrusion-Kit-Template': [{}] } }), [{ doctype: 'Item', count: 2 }, { doctype: 'ilL-Extrusion-Kit-Template', count: 1 }]);
  assert.deepEqual(recordCounts({}), []);
});
