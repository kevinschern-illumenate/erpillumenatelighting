// The overview leads with what needs the dealer's attention (FLOW-1). Needs
// tests/portal_ui/rendered/overview*.html from tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

function load(name) {
  return new JSDOM(fs.readFileSync(path.join(__dirname, `rendered/${name}.html`), 'utf8')).window.document;
}

test('action items link to their record and show the due label', () => {
  const doc = load('overview');
  const items = [...doc.querySelectorAll('#actionCenter li')];
  assert.equal(items.length, 2);
  const offer = items[0].querySelector('a');
  assert.equal(offer.getAttribute('href'), '/portal/quotes/Q-1');
  assert.equal(offer.querySelector('.ill-attention__title').textContent, 'Respond to quote <Q-1>');
  assert.equal(offer.querySelector('.ill-attention__due').textContent, 'Expires in 3 days');
  assert.equal(items[1].querySelector('.ill-attention__due'), null);
  assert.equal(doc.querySelector('#actionCenterEmpty'), null);
  assert.match(doc.querySelector('#attention-heading').textContent, /2/);
});

test('with nothing pending the overview says the dealer is caught up', () => {
  const doc = load('overview-empty');
  assert.equal(doc.querySelector('#actionCenter'), null);
  assert.match(doc.querySelector('#actionCenterEmpty').textContent, /all caught up/);
});

test('the greeting replaces the logo hero and quick actions stay one click away', () => {
  const doc = load('overview');
  assert.equal(doc.querySelector('h1').textContent.trim(), 'Good morning, Dana <D>');
  assert.equal(doc.querySelector('.portal-hero-logo'), null);
  const quick = [...doc.querySelectorAll('.ill-quick a')].map(a => a.getAttribute('href'));
  assert.deepEqual(quick, ['/portal/projects/new', '/portal/configure', '/portal/drawings']);
  assert.equal(doc.querySelector('[aria-current="page"]').textContent, 'Overview');
});
