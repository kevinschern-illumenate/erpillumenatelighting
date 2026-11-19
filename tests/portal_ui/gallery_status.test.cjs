/* The gallery sidebar status: which pill each publication state gets. Needs no DOM, only Node. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { statusOf } = require(path.join(__dirname, '../../illumenate_lighting/public/js/gallery_publication.js'));

const COLORS = new Set(['orange', 'blue', 'yellow', 'green', 'red', 'gray']);

test('no result means no status', () => {
  assert.equal(statusOf(null), null);
  assert.equal(statusOf(undefined), null);
});

test('each publication state gets its own label and colour', () => {
  const cases = [
    [{ state: 'NEEDS_REVIEW' }, 'needs_staging', 'Needs staging', 'orange'],
    [{ state: 'READY' }, 'needs_staging', 'Needs staging', 'orange'],
    [{ state: 'QUEUED' }, 'queued', 'Queued', 'blue'],
    [{ state: 'STAGED', staged_hash: 'a' }, 'staged', 'Staged', 'yellow'],
    [{ state: 'LIVE', staged_hash: 'a', live_hash: 'a' }, 'live', 'Live', 'green'],
    [{ state: 'FAILED' }, 'failed', 'Failed', 'red'],
    [{ state: 'RETIRED' }, 'retired', 'Retired', 'gray'],
  ];
  for (const [result, key, label, color] of cases) {
    const status = statusOf(result);
    assert.deepEqual([status.key, status.label, status.color], [key, label, color], JSON.stringify(result));
  }
});

test('an edited gallery that was staged or live is "Changes not staged", a never-staged one "Needs staging"', () => {
  // A save after staging leaves NEEDS_REVIEW with the old hashes still recorded.
  assert.equal(statusOf({ state: 'NEEDS_REVIEW', staged_hash: 'a' }).label, 'Changes not staged');
  assert.equal(statusOf({ state: 'NEEDS_REVIEW', live_hash: 'a' }).label, 'Changes not staged');
  assert.equal(statusOf({ state: 'NEEDS_REVIEW', staged_hash: '', live_hash: '' }).label, 'Needs staging');
  // After a retire the hashes are cleared, so a reactivated gallery needs staging again.
  assert.equal(statusOf({ state: 'NEEDS_REVIEW', staged_hash: null, live_hash: null }).label, 'Needs staging');
});

test('an unknown state is treated as needing review, never as live', () => {
  assert.equal(statusOf({ state: 'SOMETHING_NEW' }).key, 'needs_staging');
  assert.equal(statusOf({}).key, 'needs_staging');
});

test('every status has a label, a known colour and a hint for the tooltip', () => {
  const states = ['NEEDS_REVIEW', 'QUEUED', 'STAGED', 'LIVE', 'FAILED', 'RETIRED'];
  const seen = new Set(states.map(state => statusOf({ state }).key).concat(statusOf({ state: 'NEEDS_REVIEW', live_hash: 'a' }).key));
  assert.equal(seen.size, 7);
  for (const state of states.concat(['EDITED'])) {
    const status = statusOf({ state, live_hash: state === 'EDITED' ? 'a' : '' });
    assert.ok(status.label && status.hint, state);
    assert.ok(COLORS.has(status.color), `${state} ${status.color}`);
  }
});
