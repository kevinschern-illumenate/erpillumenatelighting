import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { CatalogItemSchema } from '@ill/core-schemas/catalog';
import { DesignSchema, type Design } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { WireTypeSchema, type WireType } from '@ill/core-schemas/wire';
import { codeTables } from '@ill/data/codeTables';
import {
  acknowledge,
  checkDesign,
  effectiveTargets,
  heavierWire,
  setRunWire,
  setVdTarget,
  vdLimits,
  withdrawAcknowledgement,
  type Actor,
  type CheckInput,
} from './designCheck';
import { dealerItems } from './derive';
import { expandRuns } from './expand';
import { addSupply, assignRuns, assignToCircuit, catalogMap, circuitProblem } from './power';
import { addCabinet, addCircuit, distanceDefaults, updateCabinet } from './site';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string) => JSON.parse(readFileSync(new URL(path, fixtures), 'utf8'));
const opened = read('open-design/expected.json');
const lines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;
const payload = read('catalog/payload.json');
const products = (payload.items as unknown[]).map((item) => CatalogItemSchema.parse(item));
const catalogWires = (payload.wires as unknown[]).map((wire) => WireTypeSchema.parse(wire));
const context = { catalog: catalogMap(products), lines, builds };
const limits = vdLimits({ vd_target_class2_pct: 3, vd_target_line_pct: 3 });
const dealer: Actor = { by: 'dealer@example.com', at: '2026-10-09T12:00:00Z', staff: false };
const staff: Actor = { by: 'ae@illumenate.com', at: '2026-10-09T12:00:00Z', staff: true };

// Test-only variants of the fixture cable: an unlisted CM cable and a heavier CL3R cable.
const variant = (id: string, changes: Partial<WireType>, awg?: WireType['conductors'][number]['awg']): WireType => {
  const base = catalogWires[0]!;
  return WireTypeSchema.parse({
    ...base,
    ...changes,
    id,
    conductors: base.conductors.map((conductor) => ({ ...conductor, awg: awg ?? conductor.awg })),
  });
};
const cm18 = variant('wire:TEST-CM-18', { listing: 'CM', riserLabel: '18/2 CM' });
const cl3r14 = variant('wire:TEST-CL3R-14', { riserLabel: '14/2 CL3R', ampacityBasis: '310.16' }, '14');

function design(): Design {
  const { spaces, runs } = expandRuns(lines, builds, { groupThresholdQty: 6, defaultHomeRunFt: 10 });
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  const value: Design = { ...base, site: { ...base.site, spaces, cabinets: [] }, runs, zones: [], overrides: [] };
  const cabinet = addCabinet(value, 'space-kitchen', distanceDefaults({}));
  const supply = addSupply(value, context, cabinet, 'drv:TEST-PSU-96');
  assignRuns(value, context, ['a1linear:1:1'], supply, 'OUT1');
  return value;
}

const input = (value: Design, changes: Partial<CheckInput> = {}): CheckInput => ({
  design: value,
  products,
  lines,
  wires: catalogWires,
  codeTables,
  limits,
  ...changes,
});

describe('voltage-drop targets (D5)', () => {
  it('tightens freely and loosens only with an Applications Engineer override', () => {
    const value = design();
    expect(limits).toEqual({ vdTargetLowVoltagePct: 3, vdTargetLineVoltagePct: 3, vdTargetLandscapePct: 5 });
    setVdTarget(value, 'vdTargetLowVoltagePct', 2, limits, dealer);
    expect(effectiveTargets(value, limits).vdTargetLowVoltagePct).toBe(2);
    expect(() => setVdTarget(value, 'vdTargetLowVoltagePct', 4, limits, dealer)).toThrow(
      'The target can be 3% or tighter',
    );
    expect(() => setVdTarget(value, 'vdTargetLowVoltagePct', 4, limits, staff)).toThrow('Give a reason');
    // A saved value above Settings without an override is ignored.
    value.project.settings.vdTargetLineVoltagePct = 5;
    expect(effectiveTargets(value, limits).vdTargetLineVoltagePct).toBe(3);
    value.project.settings.vdTargetLineVoltagePct = 3;

    setVdTarget(value, 'vdTargetLowVoltagePct', 4, limits, staff, 'Long landscape feed, owner accepts');
    expect(value.overrides).toMatchObject([{ code: 'VD_TARGET_LOOSENED', kind: 'staff-override', by: staff.by }]);
    expect(effectiveTargets(value, limits).vdTargetLowVoltagePct).toBe(4);
    const loosened = checkDesign(input(value)).messages.find((item) => item.code === 'VD_TARGET_LOOSENED');
    expect(loosened?.text).toContain('Long landscape feed');
    setVdTarget(value, 'vdTargetLowVoltagePct', 3, limits, dealer);
    expect(value.overrides).toEqual([]);
    expect(() => DesignSchema.parse(value)).not.toThrow();
  });
});

describe('design checks', () => {
  it('sizes assigned runs and adds the designer checks', () => {
    const value = design();
    const check = checkDesign(input(value, { reviewRequired: true, outOfSync: true }));
    expect(check.runs['a1linear:1:1']).toMatchObject({
      wireTypeId: 'wire:TEST-WIRE-18-2',
      lengthFt: 10,
      vdPct: expect.closeTo(0.729, 3),
    });
    const codes = check.messages.map((item) => [item.code, item.severity, item.entityRef]);
    expect(codes).toEqual(
      expect.arrayContaining([
        ['SUPPLY_NO_ACCESS', 'warning', 'cab-1'],
        ['UNRESOLVED_REF', 'warning', 'PS-1'],
        ['RUN_UNASSIGNED', 'warning', 'space-kitchen'],
        ['DATA_BY_DEALER', 'info', 'line:e1other'],
        ['SCHEDULE_OUT_OF_SYNC', 'warning', 'project'],
        ['REVIEW_REQUIRED', 'info', 'project'],
      ]),
    );
    expect(check.messages.find((item) => item.entityRef === 'PS-1')?.text).toBe('PS-1 is not on a panel circuit yet.');
    expect(check.messages.findIndex((item) => item.severity !== 'error')).toBeGreaterThanOrEqual(0);
    // Errors sort first, notes last.
    const order = check.messages.map((item) => item.severity);
    expect(order).toEqual(
      [...order].sort((a, b) => ['error', 'warning', 'info'].indexOf(a) - ['error', 'warning', 'info'].indexOf(b)),
    );

    updateCabinet(value, 'cab-1', { accessNote: 'Pantry ceiling hatch', sourceId: addCircuit(value) });
    const fixed = checkDesign(input(value)).messages.map((item) => item.code);
    expect(fixed).not.toContain('SUPPLY_NO_ACCESS');
    expect(fixed).not.toContain('UNRESOLVED_REF');
  });

  it('feeds line-voltage third-party fixtures from a circuit with dealer data', () => {
    const value = design();
    const circuit = addCircuit(value);
    expect(circuitProblem(value, context, ['a1linear:1:2'], circuit)).toBe(
      'A1-1.2 is low voltage; put it on a supply output',
    );
    assignToCircuit(value, context, ['e1other:1:1'], circuit);
    expect(value.runs.find((run) => run.key === 'e1other:1:1')?.assignment).toEqual({
      equipmentId: circuit,
      port: 'LINE',
    });
    const items = dealerItems(lines);
    expect(items.map((item) => [item.id, item.specs.kind])).toEqual([
      ['tp:e1other', 'fixture'],
      ['tp:f1other', 'incomplete'],
    ]);
    expect(items[0]).toMatchObject({
      source: { kind: 'user-supplied', reference: 'Data by dealer' },
      isExample: false,
    });
    const check = checkDesign(input(value));
    expect(check.runs['e1other:1:1']).toMatchObject({ type: 'lv-branch', wattsW: 12 });
    expect(check.messages.some((item) => item.code === 'UNRESOLVED_REF' && item.entityRef === 'load:e1other:1:1')).toBe(
      false,
    );
  });

  it('uses CL2 or CL3 listed cable for in-wall runs', () => {
    const value = design();
    const loose = checkDesign(input(value, { wires: [cm18, ...catalogWires] }));
    expect(loose.runs['a1linear:1:1']?.wireTypeId).toBe('wire:TEST-CM-18');
    value.runs.find((run) => run.key === 'a1linear:1:1')!.envChoice = 'in-wall';
    const inWall = checkDesign(input(value, { wires: [cm18, ...catalogWires] }));
    expect(inWall.runs['a1linear:1:1']?.wireTypeId).toBe('wire:TEST-WIRE-18-2');
    expect(inWall.inWall).toEqual({ 'power:load:a1linear:1:1': 'wire:TEST-WIRE-18-2' });
    const none = checkDesign(input(value, { wires: [cm18] }));
    expect(none.messages.find((item) => item.code === 'NO_VALID_WIRE')?.text).toBe(
      'W-01: no CL2 or CL3 listed cable in the catalog passes for this in-wall run.',
    );
  });

  it('offers a heavier wire and pins it as a wire override', () => {
    const value = design();
    const check = checkDesign(input(value, { wires: [...catalogWires, cl3r14] }));
    const run = check.runs['a1linear:1:1']!;
    expect(run.wireTypeId).toBe('wire:TEST-WIRE-18-2');
    expect(heavierWire(run)).toBe('wire:TEST-CL3R-14');
    setRunWire(value, run.runId, 'wire:TEST-CL3R-14');
    const pinned = checkDesign(input(value, { wires: [...catalogWires, cl3r14] })).runs['a1linear:1:1']!;
    expect(pinned).toMatchObject({ wireTypeId: 'wire:TEST-CL3R-14', overridden: true });
    expect(pinned.vdPct!).toBeLessThan(run.vdPct!);
    expect(heavierWire(pinned)).toBeNull();
    setRunWire(value, run.runId, undefined);
    expect(value.project.wireOverrides).toEqual({});
  });

  it('lets dealers acknowledge warnings, and only staff override errors', () => {
    const value = design();
    const check = checkDesign(input(value));
    const warning = check.messages.find((item) => item.code === 'SUPPLY_NO_ACCESS')!;
    acknowledge(value, warning, 'Access through the attic', dealer);
    const after = checkDesign(input(value)).messages.find((item) => item.code === 'SUPPLY_NO_ACCESS');
    expect(after?.override).toMatchObject({ kind: 'acknowledge', reason: 'Access through the attic' });
    const error = { code: 'PSU_OVERLOAD' as const, severity: 'error' as const, entityRef: 'PS-1', text: 'x' };
    expect(() => acknowledge(value, error, 'Fine', dealer)).toThrow('Errors must be fixed');
    acknowledge(value, error, 'Reviewed with the installer', staff);
    expect(value.overrides.map((item) => item.kind)).toEqual(['acknowledge', 'staff-override']);
    withdrawAcknowledgement(value, 'SUPPLY_NO_ACCESS', 'cab-1');
    expect(value.overrides).toHaveLength(1);
    expect(() => DesignSchema.parse(value)).not.toThrow();
  });
});
