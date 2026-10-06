import 'dotenv/config';
import express from 'express';
import { z } from 'zod';
import { pathToFileURL } from 'node:url';

const requestSchema = z
  .object({
    groups: z.array(z.string().trim().min(1).max(120)).min(1).max(20),
    fields: z
      .array(z.string().regex(/^[a-zA-Z][a-zA-Z0-9_]*$/))
      .min(1)
      .max(80),
  })
  .strict();
export function createProxy({ env = process.env, fetchImpl = fetch } = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.use((req, res, next) => {
    const origin = req.get('origin');
    const host = req.hostname;
    const validOrigin = !origin || /^http:\/\/(127\.0\.0\.1|localhost):(5173|4173)$/.test(origin);
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(host) || !validOrigin)
      return res.status(403).json({ error: 'Loopback requests only' });
    res.set('Cache-Control', 'no-store');
    next();
  });
  app.use(express.json({ limit: '64kb' }));
  app.get('/api/erp/status', (_req, res) =>
    res.json({
      configured: !!(env.ERPNEXT_BASE_URL && env.ERPNEXT_API_KEY && env.ERPNEXT_API_SECRET),
      direction: 'pull-only',
    }),
  );
  app.post('/api/erp/items', async (req, res) => {
    const input = requestSchema.safeParse(req.body);
    if (!input.success)
      return res.status(400).json({ error: 'Provide item groups and valid ERP field names.' });
    if (!env.ERPNEXT_BASE_URL || !env.ERPNEXT_API_KEY || !env.ERPNEXT_API_SECRET)
      return res.status(503).json({ error: 'Configure the local .env first.' });
    try {
      const base = new URL(env.ERPNEXT_BASE_URL);
      if (
        base.protocol !== 'https:' &&
        !(base.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(base.hostname))
      )
        throw new Error('Use HTTPS for remote ERPNext');
      if (base.username || base.password) throw new Error('Use token configuration');
      const data = [];
      const pageSize = 200;
      for (let start = 0; start < 20000; start += pageSize) {
        const url = new URL('/api/resource/Item', base);
        url.searchParams.set(
          'fields',
          JSON.stringify([...new Set(['item_code', ...input.data.fields])]),
        );
        url.searchParams.set(
          'filters',
          JSON.stringify([
            ['Item', 'item_group', 'in', input.data.groups],
            ['Item', 'disabled', '=', 0],
          ]),
        );
        url.searchParams.set('limit_start', String(start));
        url.searchParams.set('limit_page_length', String(pageSize));
        url.searchParams.set('order_by', 'name asc');
        const upstream = await fetchImpl(url, {
          headers: {
            Authorization: `token ${env.ERPNEXT_API_KEY}:${env.ERPNEXT_API_SECRET}`,
            Accept: 'application/json',
          },
          redirect: 'error',
          signal: AbortSignal.timeout(15000),
        });
        if (!upstream.ok) throw new Error('ERP request failed');
        const page = z
          .object({ data: z.array(z.record(z.string(), z.unknown())) })
          .parse(await upstream.json()).data;
        data.push(...page);
        if (page.length < pageSize) return res.json({ data });
      }
      return res.status(422).json({ error: 'More than 20,000 items. Narrow the item groups.' });
    } catch {
      return res.status(502).json({
        error:
          'ERP pull failed. Check URL, token permissions, field mapping and item groups locally.',
      });
    }
  });
  app.use((err, _req, res, _next) =>
    res.status(err.status === 413 ? 413 : 400).json({ error: 'Invalid request body' }),
  );
  return app;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.PROXY_PORT || 8787);
  createProxy().listen(port, '127.0.0.1', () =>
    process.stdout.write(`ERPNext pull proxy listening on http://127.0.0.1:${port}\n`),
  );
}
