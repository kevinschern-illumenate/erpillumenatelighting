import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { CatalogItemSchema, type CatalogItem } from '@ill/core-schemas/catalog';
import { DesignSchema, type Design, type Run } from '@ill/core-schemas/design';
import { buildHash } from '@ill/core-schemas/hash';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { WireTypeSchema, type WireType } from '@ill/core-schemas/wire';
import { codeTables } from '@ill/data/codeTables';
import { checkDesign, vdLimits, type VdLimits } from '../src/designCheck';
import { dealerItems } from '../src/derive';
import { expandRuns } from '../src/expand';
import { addSupply, catalogMap } from '../src/power';
import { addCabinet, addCircuit, distanceDefaults } from '../src/site';
import { verifySubset } from '../src/verify';

/**
 * Golden fixtures (plan H10, WP-3.6). Each case is `<name>.input.json` (design, catalog subset, wires,
 * VD limits) and `<name>.expected.json` (engine results and the `verify` subset that
 * `tests/portal_unit/test_system_design_parity.py` holds the Python mirror to). `UPDATE_GOLDEN=1`
 * rebuilds both from the case builders below; say why in the PR.
 */

const GOLDEN = new URL('../../../fixtures/golden/', import.meta.url);
const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string, base = fixtures) => JSON.parse(readFileSync(new URL(path, base), 'utf8'));
const opened = read('open-design/expected.json');
const lines = LineSchema.array().parse(opened.lines) as Line[];
const builds = BuildsSchema.parse(opened.builds) as Builds;
const payload = read('catalog/payload.json');
const catalog = [...(payload.items as unknown[]).map((item) => CatalogItemSchema.parse(item)), ...dealerItems(lines)];
const fixtureWires = (payload.wires as unknown[]).map((wire) => WireTypeSchema.parse(wire));
const context = { catalog: catalogMap(catalog), lines, builds };
const limits = vdLimits({ vd_target_class2_pct: 3, vd_target_line_pct: 3, vd_target_landscape_pct: 5 });

const variant = (id: string, changes: Partial<WireType>, awg?: WireType['conductors'][number]['awg']): WireType => {
  const base = fixtureWires[0]!;
  return WireTypeSchema.parse({
    ...base,
    ...changes,
    id,
    erpItemCode: id.replace('wire:', ''),
    conductors: base.conductors.map((conductor) => ({ ...conductor, awg: awg ?? conductor.awg })),
  });
};
const cm18 = variant('wire:TEST-CM-18', { listing: 'CM', riserLabel: '18/2 CM' });
const cl3r14 = variant('wire:TEST-CL3R-14', { riserLabel: '14/2 CL3R', ampacityBasis: '310.16' }, '14');

interface GoldenInput {
  description: string;
  design: Design;
  products: CatalogItem[];
  wires: WireType[];
  limits: VdLimits;
}

/** A design holding only `keys` of the TEST schedule's runs, with `changes` applied to each. */
function design(keys: string[], changes: Record<string, Partial<Run>> = {}): Design {
  const { spaces, runs } = expandRuns(lines, builds, { groupThresholdQty: 6, defaultHomeRunFt: 10 });
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  const picked = runs.filter((run) => keys.includes(run.key)).map((run) => ({ ...run, ...changes[run.key] }));
  return { ...base, site: { ...base.site, spaces, cabinets: [] }, runs: picked, zones: [], overrides: [] };
}
const run = (value: Design, key: string) => value.runs.find((item) => item.key === key)!;
/** Assign without the power board's refusals, so cases can hold the faults the checks must find. */
function feed(value: Design, key: string, equipmentId: string, port: string) {
  run(value, key).assignment = { equipmentId, port };
}
function supply(value: Design, catalogId: string) {
  const cabinet = value.site.cabinets[0]?.id ?? addCabinet(value, 'space-kitchen', distanceDefaults({}));
  return addSupply(value, context, cabinet, catalogId);
}

const CASES: Record<string, { description: string; build(): Design; wires?: WireType[] }> = {
  'cove-24v-single': {
    description: '20 ft cove at 4.4 W/ft, both ends fed from one 96 W Class 2 supply over a 15 ft home run.',
    build() {
      const value = design(['a1linear:1:1'], {
        'a1linear:1:1': { lengthFt: 20, watts: 88, feedMethod: 'double-end', homeRunLengthFt: 15 },
      });
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      return value;
    },
  },
  'cove-too-long': {
    description: '18 ft end-fed cove past its 16 ft single-feed limit.',
    build() {
      const value = design(['a1linear:1:1'], { 'a1linear:1:1': { lengthFt: 18, watts: 79.2 } });
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      return value;
    },
  },
  'class2-over': {
    description: '105.6 W on one 96 W Class 2 output: over the output and over 100 VA.',
    build() {
      const value = design(['a1linear:1:1'], {
        'a1linear:1:1': { lengthFt: 24, watts: 105.6, feedMethod: 'double-end' },
      });
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      return value;
    },
  },
  'vd-over-target': {
    description:
      'Two 16 ft runs on 35 ft home runs. Automatic selection moves up to 14 AWG; a run pinned to 18 AWG is over the 3% target.',
    wires: [...fixtureWires, cl3r14],
    build() {
      const changes = { lengthFt: 16, watts: 70.4, homeRunLengthFt: 35 };
      const value = design(['a1linear:1:1', 'a1linear:1:2'], { 'a1linear:1:1': changes, 'a1linear:1:2': changes });
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      feed(value, 'a1linear:1:2', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      value.project.wireOverrides['power:load:a1linear:1:2'] = {
        wireTypeId: 'wire:TEST-WIRE-18-2',
        parallelSets: 1,
        parallelCommonConductors: 1,
      };
      return value;
    },
  },
  'tape-undervoltage': {
    description: 'A 110 ft home run pinned to 18 AWG leaves the tape below its 20 V minimum.',
    build() {
      const value = design(['a1linear:1:1'], {
        'a1linear:1:1': { lengthFt: 16, watts: 70.4, homeRunLengthFt: 110 },
      });
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      value.project.wireOverrides['power:load:a1linear:1:1'] = {
        wireTypeId: 'wire:TEST-WIRE-18-2',
        parallelSets: 1,
        parallelCommonConductors: 1,
      };
      return value;
    },
  },
  'in-wall': {
    description: 'In-wall runs take CL2 or CL3 cable over a lighter CM cable; a CM pin is refused.',
    wires: [cm18, ...fixtureWires],
    build() {
      const value = design(['a1linear:1:1', 'a1linear:1:2', 'a1linear:2:1'], {
        'a1linear:1:2': { envChoice: 'in-wall' },
        'a1linear:2:1': { envChoice: 'in-wall' },
      });
      const id = supply(value, 'drv:TEST-PSU-96');
      feed(value, 'a1linear:1:1', id, 'OUT1');
      feed(value, 'a1linear:1:2', id, 'OUT1');
      feed(value, 'a1linear:2:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      value.project.wireOverrides['power:load:a1linear:2:1'] = {
        wireTypeId: 'wire:TEST-CM-18',
        parallelSets: 1,
        parallelCommonConductors: 1,
      };
      return value;
    },
  },
  'third-party-mixed': {
    description: 'Dealer-entered line-voltage fixtures on a panel circuit beside ilLumenate tape on a supply.',
    build() {
      const value = design(['a1linear:1:1', 'e1other:1:1', 'e1other:2:1']);
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      const circuit = addCircuit(value);
      feed(value, 'e1other:1:1', circuit, 'LINE');
      feed(value, 'e1other:2:1', circuit, 'LINE');
      return value;
    },
  },
  'voltage-mismatch': {
    description: 'A 120 V dealer fixture put on a 24 V supply output.',
    build() {
      const value = design(['e1other:1:1']);
      feed(value, 'e1other:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      return value;
    },
  },
  'pixel-tape': {
    description: 'Free-cut pixel tape sized from its pixel count and amps per pixel.',
    build() {
      const value = design(['a1linear:1:1'], {
        'a1linear:1:1': { catalogId: 'tape:TEST-TAPE-RGB:6:free', lengthFt: 8, watts: 48 },
      });
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-96'), 'OUT1');
      return value;
    },
  },
  'two-output-supply': {
    description: 'Runs on both outputs of a two-output supply, one output above the operating target.',
    build() {
      const value = design(['a1linear:1:1', 'd1group:1:1', 'b1tape:1:1']);
      const id = supply(value, 'drv:TEST-PSU-60');
      feed(value, 'd1group:1:1', id, 'OUT1');
      feed(value, 'b1tape:1:1', id, 'OUT2');
      feed(value, 'a1linear:1:1', id, 'OUT2');
      return value;
    },
  },
  'kitchen-zones': {
    description: 'A phase-cut zone and a DMX zone in use trigger the D4 review.',
    build() {
      const value = design(['a1linear:1:1', 'a1linear:1:2', 'd1group:1:1']);
      value.zones = [
        { id: 'zone-1', name: 'Perimeter', color: '#3366cc', method: 'phase-forward' },
        { id: 'zone-2', name: 'Accent', color: '#cc6633', method: 'DMX512' },
      ];
      run(value, 'a1linear:1:1').zoneId = 'zone-1';
      run(value, 'd1group:1:1').zoneId = 'zone-2';
      feed(value, 'a1linear:1:1', supply(value, 'drv:TEST-PSU-60'), 'OUT1');
      return value;
    },
  },
  'load-over-1500': {
    description: '1,600 W connected: over the D4 load threshold.',
    build() {
      return design(['a1linear:1:1', 'a1linear:1:2'], {
        'a1linear:1:1': { watts: 800 },
        'a1linear:1:2': { watts: 800 },
      });
    },
  },
  'load-at-1500': {
    description: 'Exactly 1,500 W connected: no D4 trigger.',
    build() {
      return design(['a1linear:1:1', 'a1linear:1:2'], {
        'a1linear:1:1': { watts: 750 },
        'a1linear:1:2': { watts: 750 },
      });
    },
  },
  'incomplete-product': {
    description: 'An incomplete supply in the design stops the calculation, as in the riser engine.',
    build() {
      const value = design(['a1linear:1:1']);
      const id = supply(value, 'drv:TEST-PSU-96');
      // The power board refuses incomplete supplies; a saved design can still carry one.
      value.project.equipment[0]!.catalogId = 'drv:TEST-PSU-BAD';
      feed(value, 'a1linear:1:1', id, 'OUT1');
      return value;
    },
  },
};

function inputFor(name: string): GoldenInput {
  const spec = CASES[name]!;
  const value = DesignSchema.parse(spec.build());
  const used = new Set([
    ...value.runs.map((item) => item.catalogId),
    ...value.project.equipment.map((e) => e.catalogId),
  ]);
  return {
    description: spec.description,
    design: value,
    products: catalog.filter((item) => used.has(item.id)),
    wires: spec.wires ?? fixtureWires,
    limits,
  };
}

function expectedFor(input: GoldenInput) {
  const check = checkDesign({
    design: input.design,
    products: input.products,
    lines: [],
    wires: input.wires,
    codeTables,
    limits: input.limits,
  });
  return {
    buildHash: buildHash(input.design as unknown as Record<string, unknown>),
    runs: Object.fromEntries(
      check.result.runs.map((item) => [
        item.runId,
        { type: item.type, wireTypeId: item.wireTypeId, vdPct: item.vdPct, endV: item.endV },
      ]),
    ),
    messages: check.messages.map((item) => `${item.severity}|${item.code}|${item.entityRef}`),
    verify: verifySubset(input.design, check),
  };
}

const update = process.env.UPDATE_GOLDEN === '1';
const json = (value: unknown) => `${JSON.stringify(value, null, 1)}\n`;

describe('golden fixtures', () => {
  it('has a case file for every builder and nothing else', () => {
    if (update)
      for (const name of Object.keys(CASES)) {
        const input = inputFor(name);
        writeFileSync(new URL(`${name}.input.json`, GOLDEN), json(input));
        writeFileSync(new URL(`${name}.expected.json`, GOLDEN), json(expectedFor(input)));
      }
    const files = readdirSync(GOLDEN).filter((file) => file.endsWith('.input.json'));
    expect(files.map((file) => file.replace('.input.json', '')).sort()).toEqual(Object.keys(CASES).sort());
  });

  for (const name of Object.keys(CASES))
    it(name, () => {
      const path = new URL(`${name}.input.json`, GOLDEN);
      if (!existsSync(path)) throw new Error(`Missing ${name}.input.json; run with UPDATE_GOLDEN=1`);
      const input = read(`${name}.input.json`, GOLDEN) as GoldenInput;
      expect(() => DesignSchema.parse(input.design)).not.toThrow();
      expect(expectedFor(input)).toEqual(read(`${name}.expected.json`, GOLDEN));
    });
});
