import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DesignSchema, designJsonSchema } from './design';
import { buildHash, canonicalJson, roundNumber, sha256Hex } from './hash';

const FIXTURES = resolve(import.meta.dirname, '../fixtures/designs');
const read = (path: string) => JSON.parse(readFileSync(resolve(FIXTURES, path), 'utf8'));
const names = (dir: string) => readdirSync(resolve(FIXTURES, dir)).filter((name) => name.endsWith('.json'));

describe('design schema (H5)', () => {
  it('accepts every valid fixture and round-trips it unchanged', () => {
    for (const name of names('valid')) {
      const parsed = DesignSchema.parse(read(`valid/${name}`));
      expect(DesignSchema.parse(JSON.parse(JSON.stringify(parsed)))).toEqual(parsed);
    }
  });

  it('rejects every invalid fixture', () => {
    for (const name of names('invalid'))
      expect(DesignSchema.safeParse(read(`invalid/${name}`)).success, name).toBe(false);
  });

  it('matches the committed JSON Schema the server validates with', () => {
    const committed = resolve(
      import.meta.dirname,
      '../../../../../illumenate_lighting/public/system_designer/schema/design.schema.json',
    );
    expect(JSON.parse(readFileSync(committed, 'utf8'))).toEqual(designJsonSchema());
  });
});

describe('canonical JSON and build hash', () => {
  it('computes SHA-256 like node:crypto across block boundaries and Unicode', () => {
    for (const text of ['', 'abc', 'a'.repeat(55), 'a'.repeat(56), 'a'.repeat(64), 'café ☕ 𝄞', 'x'.repeat(1000)])
      expect(sha256Hex(text)).toBe(createHash('sha256').update(text, 'utf8').digest('hex'));
  });

  it('sorts keys, drops undefined, rounds to 3 decimals and writes integral values bare', () => {
    expect(canonicalJson({ b: 1.23456, a: [3.0, -0.0001, undefined], c: undefined, d: 'é' })).toBe(
      '{"a":[3,0,null],"b":1.235,"d":"é"}',
    );
    expect(() => canonicalJson({ a: Number.NaN })).toThrow();
    for (const [value, expected] of read('rounding.json') as [number, number][])
      expect(roundNumber(value)).toBe(expected);
  });

  it('matches the shared hashes and ignores views', () => {
    const hashes = read('hashes.json') as Record<string, string>;
    for (const [name, hash] of Object.entries(hashes)) expect(buildHash(read(`valid/${name}`))).toBe(hash);
    const design = read('valid/runs-and-site.json');
    expect(buildHash({ ...design, views: { saved3d: [] } })).toBe(hashes['runs-and-site.json']);
    design.runs[0].lengthFt = 12.3457; // rounds to the same 12.346
    expect(buildHash(design)).toBe(hashes['runs-and-site.json']);
    design.runs[0].lengthFt = 12.4;
    expect(buildHash(design)).not.toBe(hashes['runs-and-site.json']);
  });
});
