import { afterEach, describe, expect, it, vi } from 'vitest';
import { createProxy } from './proxy.mjs';
const servers = [];
afterEach(async () => {
  await Promise.all(servers.splice(0).map((s) => new Promise((resolve) => s.close(resolve))));
});
async function start(options) {
  const server = createProxy(options).listen(0, '127.0.0.1');
  servers.push(server);
  await new Promise((r) => server.once('listening', r));
  return `http://127.0.0.1:${server.address().port}`;
}
const env = {
  ERPNEXT_BASE_URL: 'https://erp.example.invalid',
  ERPNEXT_API_KEY: 'local-test-key',
  ERPNEXT_API_SECRET: 'local-test-secret',
};
const input = { groups: ['Lighting'], fields: ['item_name', 'item_code'] };
const post = (url, body = input, headers = {}) =>
  fetch(url + '/api/erp/items', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
describe('optional local ERP proxy', () => {
  it('paginates read-only upstream requests, filters groups and keeps credentials out of the response', async () => {
    const upstream = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({
          data: Array.from({ length: 200 }, (_, i) => ({ item_code: `ITEM-${i}` })),
        }),
      )
      .mockResolvedValueOnce(Response.json({ data: [{ item_code: 'LAST' }] }));
    const url = await start({ env, fetchImpl: upstream });
    const response = await post(url);
    const body = await response.json();
    expect(body.data).toHaveLength(201);
    expect(upstream).toHaveBeenCalledTimes(2);
    const [target, options] = upstream.mock.calls[1];
    expect(target.searchParams.get('limit_start')).toBe('200');
    expect(JSON.parse(target.searchParams.get('filters'))[0]).toEqual([
      'Item',
      'item_group',
      'in',
      ['Lighting'],
    ]);
    expect(options.headers.Authorization).toBe('token local-test-key:local-test-secret');
    expect(options.method).toBeUndefined();
    expect(options.redirect).toBe('error');
    expect(JSON.stringify(body)).not.toContain('local-test-secret');
  });
  it('rejects external origins, invalid fields, unconfigured credentials and unsupported methods', async () => {
    const upstream = vi.fn();
    const url = await start({ env: {}, fetchImpl: upstream });
    expect((await post(url, input, { Origin: 'https://attacker.invalid' })).status).toBe(403);
    expect((await post(url, { ...input, fields: ['name; DROP'] })).status).toBe(400);
    expect((await post(url)).status).toBe(503);
    expect((await fetch(url + '/api/erp/items')).status).toBe(404);
    expect(await (await fetch(url + '/api/erp/status')).json()).toEqual({
      configured: false,
      direction: 'pull-only',
    });
    expect(upstream).not.toHaveBeenCalled();
  });
  it('redacts upstream errors and prevents remote plaintext requests', async () => {
    const upstream = vi.fn().mockRejectedValue(new Error('local-test-secret upstream traceback'));
    const url = await start({ env, fetchImpl: upstream });
    const response = await post(url);
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain('local-test-secret');
    const unsafe = await start({
      env: { ...env, ERPNEXT_BASE_URL: 'http://erp.example.invalid' },
      fetchImpl: upstream,
    });
    expect((await post(unsafe)).status).toBe(502);
    expect(upstream).toHaveBeenCalledTimes(1);
  });
});
