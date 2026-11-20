import { describe, expect, it } from 'vitest';
import type { Design } from '@ill/core-schemas/design';
import { applyCadSite, CadSiteSchema } from './cadSite';

const run = (lineKey: string, spaceId: string) => ({
  key: `${lineKey}:1:1`,
  lineKey,
  lineId: 'L1',
  buildIndex: 1,
  runIndex: 1,
  source: { kind: 'configured' as const, doctype: 'ilL-Configured-Tape-Neon' as const, name: 'CTN-1', configHash: 'h' },
  catalogId: 'tape:T:4.4:50',
  watts: 30,
  feedMethod: 'end' as const,
  spaceId,
  env: 'dry-concealed' as const,
  homeRunLengthFt: 10,
  homeRunProvenance: 'estimate' as const,
});

function design(): Design {
  return {
    site: {
      spaces: [
        { id: 'space-kitchen', name: 'Kitchen', level: '', type: 'other', archetype: 'none', env: 'dry-concealed' },
        { id: 'space-primary-bath', name: 'Primary Bath', level: '', type: 'other', archetype: 'none', env: 'dry-concealed' },
      ],
      cabinets: [],
      floorPlans: [],
    },
    runs: [run('K1', 'space-kitchen'), run('K2', 'space-primary-bath'), run('K3', 'space-kitchen')],
  } as unknown as Design;
}

const SITE = CadSiteSchema.parse({
  schema: 'cad-site/1',
  import: 'CADI-00001',
  drawing: { file: 'Ybarra_L1.dwg', rev: 1 },
  rooms: [
    { id: 'Z-Kitchen', name: 'Kitchen', level: 'L1', envChoice: 'dry-concealed' },
    { id: 'Z-Bath', name: 'Primary Bath', level: 'L2', envChoice: 'damp' },
    { id: 'Z-Patio', name: 'Patio', level: 'L1', envChoice: 'outdoor-exposed' },
  ],
  cabinets: [
    { id: 'CAB-1', room: 'Kitchen', locationRating: 'Dry', accessNote: 'Pantry', feedLengthFt: 45 },
    { id: 'CAB-2', room: 'Primary Bath', locationRating: 'Damp' },
  ],
  lines: {
    K1: { runId: 'L1-01', room: 'Kitchen', cabinet: 'CAB-1', feedMethod: 'end', homeRunLengthFt: 11.46 },
    K2: { runId: 'L4-01', room: 'Primary Bath', feedMethod: 'double-end' },
    K9: { runId: 'L9-01', room: 'Kitchen' },
  },
});

describe('applying the drawing site to a new design (draw-to-quote 2.3)', () => {
  it('sets levels and environments on spaces matched by room name, and adds rooms without lines', () => {
    const target = design();
    const result = applyCadSite(target, SITE);
    expect(result.spaces).toBe(3);
    const bath = target.site.spaces.find((space) => space.id === 'space-primary-bath')!;
    expect([bath.level, bath.env, bath.envChoice]).toEqual(['L2', 'wet', 'damp']);
    expect(target.site.spaces.find((space) => space.id === 'space-patio')?.env).toBe('outdoor-exposed');
  });

  it('adds the drawn cabinets with measured feeds', () => {
    const target = design();
    applyCadSite(target, SITE);
    const [first, second] = target.site.cabinets;
    expect(first).toMatchObject({ id: 'CAB-1', tag: 'CAB-1', spaceId: 'space-kitchen', feedLengthFt: 45, feedLengthProvenance: 'measured', accessNote: 'Pantry' });
    expect(second).toMatchObject({ spaceId: 'space-primary-bath', locationRating: 'Damp', feedLengthProvenance: 'estimate' });
    applyCadSite(target, SITE);
    expect(target.site.cabinets).toHaveLength(2);
  });

  it('marks measured home runs and feed methods; lines without runs are reported', () => {
    const target = design();
    const result = applyCadSite(target, SITE);
    const [kitchen, bath, untouched] = target.runs;
    expect([kitchen!.homeRunLengthFt, kitchen!.homeRunProvenance]).toEqual([11.46, 'measured']);
    expect([bath!.homeRunProvenance, bath!.feedMethod, bath!.env]).toEqual(['estimate', 'double-end', 'wet']);
    expect(untouched!.homeRunProvenance).toBe('estimate');
    expect(result.runs).toBe(2);
    expect(result.unmatchedLines).toEqual(['K9']);
  });
});
