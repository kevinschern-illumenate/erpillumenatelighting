import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { IlqPackageSchema, ilqJsonSchema } from './ilq';

const FIXTURES = resolve(import.meta.dirname, '../../../fixtures/cad/packages');
const read = (path: string) => JSON.parse(readFileSync(resolve(FIXTURES, path), 'utf8'));
const names = (dir: string) => readdirSync(resolve(FIXTURES, dir)).filter((name) => name.endsWith('.json'));

describe('ilq/2 draw-to-quote package (CAD toolkit 1.5)', () => {
  it('accepts every valid package', () => {
    for (const name of names('valid')) {
      const result = IlqPackageSchema.safeParse(read(`valid/${name}`));
      expect(result.success, `${name}: ${JSON.stringify(result.error?.issues)}`).toBe(true);
    }
  });

  it('rejects every invalid package', () => {
    for (const name of names('invalid'))
      expect(IlqPackageSchema.safeParse(read(`invalid/${name}`)).success, name).toBe(false);
  });

  it('fills defaults the AutoLISP writer may leave out', () => {
    const parsed = IlqPackageSchema.parse(read('valid/minimal.json'));
    expect(parsed.rooms).toEqual([]);
    expect(parsed.runs[0]!.segments[0]!.end_type).toBe('ENDCAP');
    expect(parsed.runs[0]!.feed).toEqual({ method: 'end', point_handles: [] });
  });

  it('matches the committed JSON Schema the portal import validates with', () => {
    const committed = resolve(
      import.meta.dirname,
      '../../../../../illumenate_lighting/public/system_designer/schema/ilq.schema.json',
    );
    expect(JSON.parse(readFileSync(committed, 'utf8'))).toEqual(ilqJsonSchema());
  });
});
