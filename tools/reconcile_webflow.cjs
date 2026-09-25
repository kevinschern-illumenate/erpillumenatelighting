/* Read-only ERP/Webflow audit. Environment secrets never enter the report. */
'use strict';
const {createHash} = require('node:crypto');
const {projectWebflowProduct} = require('../n8n_workflows/lib/product_projection.js');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
    return value;
}
const equal = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const assets = value => value && typeof value === 'object' && (value.url || Array.isArray(value) && value.some(v => v?.url));
function expected(payload, remoteId) {
    return projectWebflowProduct({...payload.product, webflow_item_id: remoteId}, payload.brand).json.webflowData;
}
async function compareContent(payload, remoteId, remote, hashAsset) {
    if (!remote) return {status: 'DRIFT', fields: ['missing_item']};
    if (!payload) return {status: 'UNVERIFIED', fields: ['missing_frozen_payload']};
    const wanted = expected(payload, remoteId), fields = [], unverified = [];
    if (remote.id !== remoteId) fields.push('id');
    if (remote.isArchived) fields.push('isArchived');
    for (const [key, value] of Object.entries(wanted.fieldData)) {
        const actual = remote.fieldData?.[key];
        if (!assets(value)) {
            // Webflow may return null for an optional empty string field.
            if (!equal(value, actual == null && value === '' ? '' : actual)) fields.push(key);
            continue;
        }
        const originals = Array.isArray(value) ? value : [value];
        const copies = Array.isArray(actual) ? actual : actual ? [actual] : [];
        if (originals.length !== copies.length) { fields.push(key); continue; }
        if (!hashAsset) { unverified.push(key); continue; }
        try {
            for (let i = 0; i < originals.length; i++) {
                if (!copies[i]?.url || await hashAsset(originals[i].url) !== await hashAsset(copies[i].url)) {
                    fields.push(key); break;
                }
            }
        } catch { unverified.push(key); }
    }
    return {status: fields.length ? 'DRIFT' : unverified.length ? 'UNVERIFIED' : 'MATCH', fields, unverified};
}
async function requestJSON(url, headers, fetcher = fetch, sleep = ms => new Promise(resolve => setTimeout(resolve, ms))) {
    for (let attempt = 0; attempt < 4; attempt++) {
        const response = await fetcher(url, {headers, redirect: 'error', signal: AbortSignal.timeout(30000)});
        if (response.status === 404) return null;
        if ([429, 500, 502, 503, 504].includes(response.status) && attempt < 3) {
            const delay = Math.min(30, Math.max(1, Number(response.headers.get('retry-after')) || 2 ** attempt));
            await sleep(delay * 1000); continue;
        }
        if (!response.ok) throw new Error(`Remote request failed (HTTP ${response.status})`);
        return response.json();
    }
}
function assetReader(erpOrigin) {
    const cache = new Map();
    return async original => {
        if (cache.has(original)) return cache.get(original);
        let url = new URL(original);
        for (let hop = 0; hop < 4; hop++) {
            const allowed = url.origin === erpOrigin || /(^|\.)website-files\.com$/.test(url.hostname) || /(^|\.)webflow\.com$/.test(url.hostname);
            if (!allowed || url.protocol !== 'https:' || url.username || url.password) throw new Error('Asset origin is not approved');
            const response = await fetch(url, {redirect: 'manual', signal: AbortSignal.timeout(30000)});
            if ([301,302,303,307,308].includes(response.status)) { url = new URL(response.headers.get('location'), url); continue; }
            if (!response.ok || Number(response.headers.get('content-length')) > 20 * 1024 * 1024) throw new Error('Asset unavailable');
            const hash = createHash('sha256'); let size = 0;
            for await (const chunk of response.body) {
                size += chunk.length;
                if (size > 20 * 1024 * 1024) throw new Error('Asset exceeds limit');
                hash.update(chunk);
            }
            const result = hash.digest('hex'); cache.set(original, result); return result;
        }
        throw new Error('Asset redirect limit');
    };
}
async function audit(row, getRemote, hashAsset) {
    const result = {publication: row.name, product: row.product, brand: row.brand, remote_item_id: row.remote_item_id,
        staged_hash: row.staged_hash, live_hash: row.live_hash};
    if (!row.remote_item_id) return {...result, status: row.staged_hash || row.live_hash ? 'DRIFT' : 'UNVERIFIED', fields: ['remote_identity']};
    if (!/^[a-f0-9]{24}$/i.test(row.remote_item_id) || !/^[a-f0-9]{24}$/i.test(row.collection_id || '')) throw new Error('Invalid CMS identity');
    const base = `https://api.webflow.com/v2/collections/${row.collection_id}/items/${row.remote_item_id}`;
    const staged = await getRemote(base), live = await getRemote(base + '/live');
    result.staged = row.state === 'RETIRED'
        ? {status: !staged || staged.isArchived ? 'MATCH' : 'DRIFT', fields: !staged || staged.isArchived ? [] : ['retired_item_active']}
        : await compareContent(row.staged_payload, row.remote_item_id, staged, hashAsset);
    result.live = row.live_hash
        ? await compareContent(row.live_payload, row.remote_item_id, live, hashAsset)
        : {status: live ? 'DRIFT' : 'MATCH', fields: live ? ['unexpected_live_item'] : []};
    const states = [result.staged.status, result.live.status];
    result.status = states.includes('DRIFT') ? 'DRIFT' : states.includes('UNVERIFIED') ? 'UNVERIFIED' : 'MATCH';
    return result;
}
async function main() {
    for (const key of ['ILL_ERP_BASE_URL','ILL_ERP_API_KEY','ILL_ERP_API_SECRET','ILL_WEBFLOW_BRAND','ILL_WEBFLOW_TOKEN']) {
        if (!process.env[key]) throw new Error(`Set ${key} as a process secret/configuration value`);
    }
    const origin = new URL(process.env.ILL_ERP_BASE_URL);
    if (origin.protocol !== 'https:' || origin.username || origin.password || origin.search || origin.hash || origin.pathname !== '/') throw new Error('Use an HTTPS ERP origin');
    const erpHeaders = {Authorization: `token ${process.env.ILL_ERP_API_KEY}:${process.env.ILL_ERP_API_SECRET}`};
    const remoteHeaders = {Authorization: `Bearer ${process.env.ILL_WEBFLOW_TOKEN}`};
    const hashAsset = assetReader(origin.origin), rows = []; let after = '', pages = 0;
    do {
        const url = new URL('/api/method/illumenate_lighting.illumenate_lighting.api.publication.reconciliation_batch', origin);
        url.search = new URLSearchParams({brand: process.env.ILL_WEBFLOW_BRAND, after, limit: '25'});
        const page = (await requestJSON(url, erpHeaders))?.message;
        if (!page || !Array.isArray(page.publications)) throw new Error('Invalid ERP audit page');
        for (const row of page.publications) rows.push(await audit(row, url => requestJSON(url, remoteHeaders), hashAsset));
        if (page.next_cursor && page.next_cursor <= after) throw new Error('Nonadvancing audit cursor');
        after = page.next_cursor;
        if (++pages > 1000) throw new Error('Audit page limit reached');
    } while (after);
    const report = {schema_version: 1, observed_on: new Date().toISOString(), brand: process.env.ILL_WEBFLOW_BRAND, publications: rows};
    report.report_hash = digest(JSON.stringify(canonical(report)));
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
    if (rows.some(row => row.status !== 'MATCH')) process.exitCode = 2;
}
module.exports = {compareContent, audit, requestJSON};
if (require.main === module) main().catch(() => { console.error('Reconciliation failed. Check configured identities, credentials and connectivity; no remote content was changed.'); process.exitCode = 1; });
