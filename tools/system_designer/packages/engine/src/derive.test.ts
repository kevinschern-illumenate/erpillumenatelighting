import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DesignSchema } from '@ill/core-schemas/design';
import { LoadSchema } from '@ill/core-schemas/project';
import { DATA_BY_DEALER_NOTE, deriveLoads, withDerivedLoads } from './derive';

const design = DesignSchema.parse(
  JSON.parse(
    readFileSync(
      resolve(import.meta.dirname, '../../core-schemas/fixtures/designs/valid/runs-and-site.json'),
      'utf8',
    ),
  ),
);

describe('deriveLoads', () => {
  it('turns assigned runs into riser loads and skips unassigned ones', () => {
    const loads = deriveLoads(design);
    expect(loads.map((load) => load.id)).toEqual(['load:LK-1:1:1', 'load:TP-9:1:1']);
    for (const load of loads) expect(LoadSchema.safeParse(load).success).toBe(true);
    const [tape, thirdParty] = loads;
    expect(tape).toMatchObject({
      typeTag: 'A1',
      zone: 'Kitchen',
      catalogId: 'tape:TAPE-24:4.4:50',
      lengthFt: 12.34567,
      fedFrom: { ref: 'PS-1', port: 'OUT1' },
      feedMethod: 'end',
    });
    expect(tape).not.toHaveProperty('qty');
    expect(thirdParty).toMatchObject({ qty: 1, zone: 'Patio café', notes: DATA_BY_DEALER_NOTE, env: 'wet' });
  });

  it('replaces project.loads without touching the rest of the project', () => {
    const next = withDerivedLoads(design);
    expect(next.project.loads).toHaveLength(2);
    expect(next.project.sources).toBe(design.project.sources);
    expect(design.project.loads).toHaveLength(0);
  });
});
