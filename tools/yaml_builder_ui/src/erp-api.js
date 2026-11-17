const BASE = '/api/method/illumenate_lighting.illumenate_lighting.api.catalog_builder.';
export const LOGIN_URL = '/login?redirect-to=/catalog-builder';
const SESSION_MESSAGE = 'Your ERPNext session has expired or you lack access. Reload the page to log in again.';

/** Frappe encodes a list of JSON-encoded message objects. Never render these as HTML. */
export function frappeMessage(data = {}) {
  try {
    const messages = JSON.parse(data._server_messages).map(entry => {
      try { return JSON.parse(entry).message; } catch { return entry; }
    }).filter(message => typeof message === 'string' && message);
    if (messages.length) return messages.join('\n');
  } catch { /* Some HTTP errors have no Frappe body. */ }
  return data.exception || data.exc_type || '';
}

export class ErpError extends Error {
  constructor(status, message, sessionExpired = false) {
    super(message);
    this.name = 'ErpError';
    this.status = status;
    this.sessionExpired = sessionExpired;
  }
}

export function createErpApi({ csrfToken, fetchImpl = fetch }) {
  async function call(method, { body, query } = {}) {
    const url = BASE + method + (query ? `?${new URLSearchParams(query)}` : '');
    // POSTs are deliberately never retried: a lost response may follow a committed import.
    const response = await fetchImpl(url, body ? {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Frappe-CSRF-Token': csrfToken },
      body: JSON.stringify(body),
    } : { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const data = await response.json().catch(() => ({})) || {};
    if (!response.ok) {
      const sessionExpired = [401, 403].includes(response.status) || data.exc_type === 'CSRFTokenError';
      throw new ErpError(response.status, sessionExpired ? SESSION_MESSAGE : frappeMessage(data) || `ERPNext returned ${response.status}`, sessionExpired);
    }
    if (data.message == null) throw new ErpError(response.status, 'ERPNext returned an unreadable response.');
    return data.message;
  }
  return {
    reference: refresh => call('reference', { query: refresh ? { refresh: 1 } : undefined }),
    record: (doctype, name) => call('record', { query: { doctype, name } }),
    /** Full records for [[doctype, name], ...]: one { record } or { error } per pair, in order. */
    records: pairs => call('records', { body: { records: pairs } }),
    /** An optional media manifest ({ manifest, zip }) is sent only when it has rows. */
    check: (catalog, media) => call('check', { body: withMedia({ catalog }, media) }),
    importCatalog: (catalog, expectedHash, media) => call('import_catalog', { body: withMedia({ catalog, expected_hash: expectedHash }, media) }),
    history: () => call('history'),
    designReadiness: () => call('design_readiness'),
  };
}

/** The media keys of a Check/Import body: CSV text and an optional uploaded ZIP (File name or URL). */
export function mediaBody(media) {
  const manifest = (media?.manifest || '').trim();
  if (!manifest) return {};
  const zip = (media.zip || '').trim();
  return zip ? { media: manifest, media_zip: zip } : { media: manifest };
}

const withMedia = (body, media) => ({ ...body, ...mediaBody(media) });

export const slug = doctype => doctype.toLowerCase().replace(/[^a-z0-9]+/g, '-');
export const deskUrl = (doctype, name) => `/app/${slug(doctype)}/${encodeURIComponent(name)}`;
export const recordCounts = catalog => Object.entries(catalog.records || {})
  .filter(([, rows]) => rows.length).map(([doctype, rows]) => ({ doctype, count: rows.length }));
