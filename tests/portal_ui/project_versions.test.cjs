// The project page shows each schedule's latest version and folds earlier
// ones (FLOW-9). Needs tests/portal_ui/rendered/project-versions.html from
// tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('only the latest version of each schedule is listed up front', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/project-versions.html'), 'utf8');
  const doc = new JSDOM(html).window.document;
  const list = doc.querySelector('#scheduleFamilies');
  const upFront = [...list.children].filter(el => el.matches('.js-schedule-row')).map(el => el.dataset.schedule);
  assert.deepEqual(upFront, ['S-3', 'S-9']);
  const folded = list.querySelectorAll('.js-earlier-versions');
  assert.equal(folded.length, 1);
  assert.equal(folded[0].querySelector('summary').textContent, 'v3 · 2 earlier versions');
  assert.deepEqual([...folded[0].querySelectorAll('.js-schedule-row')].map(el => el.dataset.schedule), ['S-2', 'S-1']);
  assert.equal(folded[0].open, false);
});
