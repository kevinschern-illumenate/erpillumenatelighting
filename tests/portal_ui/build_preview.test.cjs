// Plan 6.6: build preview geometry is a pure function of the computed build.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const preview = require('../../illumenate_lighting/public/js/configurator/build_preview.js');

const shapes = (model, cls) => model.shapes.filter(s => s.cls.split(' ').includes(cls));

test('linear pieces scale to their cut lengths with feeds, jumpers and lens cuts', () => {
  const result = { computed: {
    user_segments: [
      { segment_index: 1, user_segment_index: 1, profile_cut_len_mm: 2000, lens_cut_len_mm: 1990, tape_cut_len_mm: 2900, start_leader_len_mm: 1524, end_jumper_len_mm: 0 },
      { segment_index: 2, user_segment_index: 1, profile_cut_len_mm: 1000, lens_cut_len_mm: 990, tape_cut_len_mm: 0, end_jumper_len_mm: 610 },
      { segment_index: 3, user_segment_index: 2, profile_cut_len_mm: 1000, lens_cut_len_mm: 990, tape_cut_len_mm: 990 },
    ],
    runs: [
      { run_index: 1, segment_index: 1, run_len_mm: 2900, run_watts: 20 },
      { run_index: 2, segment_index: 3, run_len_mm: 990, run_watts: 7 },
    ],
  } };
  const model = preview.model(result, 'linear');
  assert.equal(model.kind, 'strip');
  assert.deepEqual(model.counts, { segments: 2, pieces: 3, runs: 2, feeds: 2, jumpers: 1 });
  const pieces = shapes(model, 'ill-bp-piece');
  assert.equal(pieces.length, 3);
  assert.ok(Math.abs(pieces[0].width - 2 * pieces[1].width) < 0.05, 'widths are proportional to cut length');
  assert.equal(pieces[0].x, 16);
  const right = pieces[2].x + pieces[2].width;
  assert.ok(Math.abs(right - (720 - 16)) < 0.05, 'the strip fills the drawing width');
  assert.deepEqual(pieces.map(p => p.title.split(':')[0]), ['Segment 1, piece 1 of 2', 'Segment 1, piece 2 of 2', 'Segment 2']);
  assert.equal(shapes(model, 'ill-bp-jumper').length, 1);
  assert.equal(shapes(model, 'ill-bp-joint').length, 1, 'pieces of one segment are joined, not jumpered');
  assert.match(shapes(model, 'ill-bp-jumper')[0].title, /Jumper 24".*new run with its own feed/);
  assert.match(shapes(model, 'ill-bp-feed')[0].title, /leader 60"/);
  assert.deepEqual(shapes(model, 'ill-bp-note').map(s => s.text), ['Lens 78.3"', 'Lens 39.0"', 'Lens 39.0"']);
  const runs = shapes(model, 'ill-bp-run');
  assert.equal(runs.length, 3, 'run 1 continues across the field joint onto the second piece');
  assert.equal(runs[1].x, pieces[1].x);
  assert.equal(runs[2].x, pieces[2].x);
  assert.equal(shapes(model, 'ill-bp-feed')[1].cx, pieces[2].x, 'run 2 is fed where segment 2 starts');
  assert.equal(model.total_mm, 4000);
});

test('one long segment shipped in pieces spreads its runs along the whole fixture', () => {
  // The reported build: a 25 ft segment cut into four profile pieces, with two 149.6" runs.
  const result = { computed: {
    user_segments: [2000, 2000, 2000, 1618].map((length, i) => ({
      segment_index: i + 1, user_segment_index: 1, profile_cut_len_mm: length, lens_cut_len_mm: length,
      tape_cut_len_mm: i === 0 ? 7600 : 0, start_leader_len_mm: i === 0 ? 3048 : 0,
    })),
    runs: [
      { run_index: 1, segment_index: 1, run_len_mm: 3800, run_watts: 37.4 },
      { run_index: 2, segment_index: 1, run_len_mm: 3800, run_watts: 37.4 },
    ],
  } };
  const model = preview.model(result, 'linear');
  assert.deepEqual(model.counts, { segments: 1, pieces: 4, runs: 2, feeds: 2, jumpers: 0 });
  assert.equal(model.summary, '1 segment, 4 pieces, 2 runs, 2 feed points, 0 jumpers');
  const pieces = shapes(model, 'ill-bp-piece');
  const feeds = shapes(model, 'ill-bp-feed');
  assert.equal(feeds[0].cx, pieces[0].x);
  assert.ok(feeds[1].cx > pieces[1].x && feeds[1].cx < pieces[1].x + pieces[1].width, 'run 2 starts part-way along the second piece');
  const runs = shapes(model, 'ill-bp-run');
  const last = runs[runs.length - 1];
  assert.ok(Math.abs(last.x + last.width - (pieces[3].x + pieces[3].width)) < 1, 'the runs reach the end of the fixture');
  assert.ok(runs.every(r => r.width <= 166.5), 'no run is squeezed onto a single piece');
});

test('jumpered segments show where a new run takes its own feed', () => {
  const segment = (i, jumper) => ({ segment_index: i, user_segment_index: i, profile_cut_len_mm: 1500, tape_cut_len_mm: 1490,
    start_leader_len_mm: i === 1 ? 1524 : 0, end_jumper_len_mm: jumper ? 300 : 0 });
  const model = preview.model({ computed: {
    user_segments: [segment(1, true), segment(2, true), segment(3, true), segment(4, false)],
    runs: [{ run_len_mm: 2980, run_watts: 40 }, { run_len_mm: 2980, run_watts: 40 }],
  } }, 'linear');
  assert.deepEqual(model.counts, { segments: 4, pieces: 4, runs: 2, feeds: 2, jumpers: 3 });
  const pieces = shapes(model, 'ill-bp-piece');
  assert.deepEqual(shapes(model, 'ill-bp-feed').map(f => f.cx), [pieces[0].x, pieces[2].x]);
  assert.deepEqual(shapes(model, 'ill-bp-jumper').map(j => /continues/.test(j.title)), [true, false, true]);
});

test('single-segment linear falls back to computed.segments', () => {
  const model = preview.model({ computed: {
    segments: [{ segment_index: 1, profile_cut_len_mm: 1219.2, lens_cut_len_mm: 1210 }],
    runs: [{ segment_index: 1, run_len_mm: 1200 }],
  } }, 'linear');
  assert.deepEqual(model.counts, { segments: 1, pieces: 1, runs: 1, feeds: 1, jumpers: 0 });
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
    assert.deepEqual(model.counts, { segments: 2, pieces: 2, runs: 3, feeds: 3, jumpers: 1 });
    assert.equal(model.summary, '2 segments, 3 runs, 3 feed points, 1 jumper');
    const pieces = shapes(model, 'ill-bp-piece');
    const feeds = shapes(model, 'ill-bp-feed').map(f => f.cx);
    assert.equal(feeds[0], pieces[0].x);
    assert.ok(Math.abs(feeds[1] - (pieces[0].x + pieces[0].width / 2)) < 0.05, 'the second run starts half-way along segment 1');
    assert.equal(feeds[2], pieces[1].x);
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

test('sheet groups name the supply output that feeds them', () => {
  const model = preview.model({
    panels_wide: 2, panels_tall: 2, panels_needed: 4, sheet_width_ft: 1, sheet_height_ft: 1,
    groups: [
      { group_number: 1, sheet_count: 2, supply_number: 1, output_number: 1 },
      { group_number: 2, sheet_count: 2, supply_number: 1, output_number: 2 },
    ],
    leader_cable_qty: 2, jumper_cable_qty: 4,
  }, 'sheet');
  const panels = shapes(model, 'ill-bp-panel');
  assert.match(panels[0].title, /driver group 1 \(power supply 1, output 1\)/);
  assert.match(panels[3].title, /driver group 2 \(power supply 1, output 2\)/);
  assert.equal(model.summary, '4 panels (2 × 2), 2 driver groups on 1 power supply, 2 leader cables, 4 jumper cables');
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
