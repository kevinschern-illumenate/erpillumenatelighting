// Plan 6.6: build preview geometry is a pure function of the computed build.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const preview = require('../../illumenate_lighting/public/js/configurator/build_preview.js');

const shapes = (model, cls) => model.shapes.filter(s => s.cls.split(' ').includes(cls));

test('linear pieces scale to their cut lengths with feeds, jumpers and lens cuts', () => {
  const result = { computed: {
    user_segments: [
      { segment_index: 1, user_segment_index: 1, profile_cut_len_mm: 2000, lens_cut_len_mm: 1990, start_leader_len_mm: 1524, end_jumper_len_mm: 0 },
      { segment_index: 2, user_segment_index: 1, profile_cut_len_mm: 1000, lens_cut_len_mm: 990, end_jumper_len_mm: 610 },
      { segment_index: 3, user_segment_index: 2, profile_cut_len_mm: 1000, lens_cut_len_mm: 990 },
    ],
    runs: [
      { run_index: 1, segment_index: 1, run_len_mm: 2900, run_watts: 20 },
      { run_index: 2, segment_index: 3, run_len_mm: 990, run_watts: 7 },
    ],
  } };
  const model = preview.model(result, 'linear');
  assert.equal(model.kind, 'strip');
  assert.deepEqual(model.counts, { pieces: 3, runs: 2, feeds: 2, jumpers: 1 });
  const pieces = shapes(model, 'ill-bp-piece');
  assert.equal(pieces.length, 3);
  assert.ok(Math.abs(pieces[0].width - 2 * pieces[1].width) < 0.05, 'widths are proportional to cut length');
  assert.equal(pieces[0].x, 16);
  const right = pieces[2].x + pieces[2].width;
  assert.ok(Math.abs(right - (720 - 16)) < 0.05, 'the strip fills the drawing width');
  assert.equal(shapes(model, 'ill-bp-jumper').length, 1);
  assert.equal(shapes(model, 'ill-bp-joint').length, 1, 'pieces of one segment are joined, not jumpered');
  assert.match(shapes(model, 'ill-bp-jumper')[0].title, /Jumper 24"/);
  assert.match(shapes(model, 'ill-bp-feed')[0].title, /leader 60"/);
  assert.deepEqual(shapes(model, 'ill-bp-note').map(s => s.text), ['Lens 78.3"', 'Lens 39.0"', 'Lens 39.0"']);
  const runs = shapes(model, 'ill-bp-run');
  assert.ok(runs[0].width <= pieces[0].width + 0.01, 'a run longer than its piece is clipped to the piece');
  assert.equal(runs[1].x, pieces[2].x);
  assert.equal(model.total_mm, 4000);
});

test('single-segment linear falls back to computed.segments', () => {
  const model = preview.model({ computed: {
    segments: [{ segment_index: 1, profile_cut_len_mm: 1219.2, lens_cut_len_mm: 1210 }],
    runs: [{ segment_index: 1, run_len_mm: 1200 }],
  } }, 'linear');
  assert.deepEqual(model.counts, { pieces: 1, runs: 1, feeds: 1, jumpers: 0 });
  assert.equal(shapes(model, 'ill-bp-label')[0].text, '48.0"');
});

test('tape and neon segments draw runs, leaders and jumper ends', () => {
  const result = { computed: { segments: [
    { segment_index: 1, manufacturable_length_mm: 3000, start_lead_length_inches: 72, end_type: 'Jumper', end_feed_length_inches: 12,
      runs: [{ run_len_mm: 1500, run_watts: 9 }, { run_len_mm: 1500, run_watts: 9 }] },
    { segment_index: 2, manufacturable_length_mm: 1500, start_lead_length_inches: 0, end_type: 'Endcap', runs: [{ run_len_mm: 1500 }] },
  ] } };
  for (const family of ['tape', 'neon']) {
    const model = preview.model(result, family);
    assert.equal(model.family, family);
    assert.deepEqual(model.counts, { pieces: 2, runs: 3, feeds: 3, jumpers: 1 });
    assert.equal(model.summary, '2 segments, 3 runs, 3 feed points, 1 jumper');
  }
});

test('sheet panels tile the grid and colour by driver group in panel order', () => {
  const model = preview.model({
    panels_wide: 3, panels_tall: 2, panels_needed: 5, sheet_width_ft: 2, sheet_height_ft: 1,
    groups: [{ group_number: 1, sheet_count: 3 }, { group_number: 2, sheet_count: 2 }],
    leader_cable_qty: 2, jumper_cable_qty: 3,
  }, 'sheet');
  assert.equal(model.kind, 'grid');
  const panels = shapes(model, 'ill-bp-panel');
  assert.equal(panels.length, 5);
  assert.deepEqual(panels.map(p => p.cls.split('--')[1]), ['0', '0', '0', '1', '1']);
  assert.equal(panels[3].x, panels[0].x, 'the fourth panel starts the second row');
  assert.ok(panels[3].y > panels[0].y);
  assert.ok(Math.abs((panels[0].height + 2) * 2 - (panels[0].width + 2)) < 0.05, 'cells keep the panel aspect ratio');
  assert.equal(model.summary, '5 panels (3 × 2), 2 driver groups, 2 leader cables, 3 jumper cables');
});

test('missing, empty or hostile builds produce no drawing and labels are numbers only', () => {
  assert.equal(preview.model(null, 'linear'), null);
  assert.equal(preview.model({ computed: {} }, 'linear'), null);
  assert.equal(preview.model({ panels_wide: 0, panels_tall: 0 }, 'sheet'), null);
  const model = preview.model({ computed: { segments: [{ segment_index: '<b>', manufacturable_length_mm: '<img src=x>' }, { manufacturable_length_mm: 100 }] } }, 'tape');
  assert.equal(model.counts.pieces, 1);
  assert.ok(model.shapes.every(s => !/[<>]/.test(String(s.text || '') + String(s.title || ''))));
});

test('very large builds are capped and flagged as truncated', () => {
  const segments = Array.from({ length: 80 }, (_, i) => ({ segment_index: i + 1, manufacturable_length_mm: 100, runs: [] }));
  const model = preview.model({ computed: { segments } }, 'tape');
  assert.equal(model.counts.pieces, 60);
  assert.equal(model.truncated, true);
});
