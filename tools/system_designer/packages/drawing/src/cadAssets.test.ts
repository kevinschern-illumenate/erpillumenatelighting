import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { seedLayers } from '@ill/data/seeds';
import { cadAssets, cadAssetsLisp, PLAN_FROM_RISER } from './cadAssets';

describe('CAD toolkit assets (draw-to-quote 1.6, 3.4)', () => {
  it('matches the committed il-assets.lsp the toolkit loads', () => {
    const committed = readFileSync(resolve(import.meta.dirname, '../../../../cad_toolkit/lisp/il-assets.lsp'), 'utf8');
    expect(committed).toBe(cadAssetsLisp());
  });

  it('carries every riser and plan layer, with the issue layer never plotted', () => {
    const { layers } = cadAssets();
    expect(layers.map((layer) => layer.name)).toEqual([
      ...seedLayers.layers.map((layer) => layer.name),
      ...seedLayers.planLayers.map((layer) => layer.name),
    ]);
    expect(layers.find((layer) => layer.name === 'E-ANNO-ISSU')?.plot).toBe(false);
    expect(layers.find((layer) => layer.name === 'E-ANNO-QAFL')?.plot).toBe(false);
  });

  it('reuses the riser symbols so the plan and the riser read the same', () => {
    const { riser } = cadAssets();
    expect(riser.map((block) => block.name).sort()).toEqual(Object.values(PLAN_FROM_RISER).sort());
    const psu = riser.find((block) => block.name === 'IL-PSU')!;
    expect(psu.items.filter((item) => item[0] === 'ATTDEF').map((item) => item[1])).toContain('TAG');
  });

  it('builds a title block per sheet size with one attribute per field', () => {
    const { titleBlocks } = cadAssets();
    expect(titleBlocks.map((block) => block.name)).toEqual(['IL-TB-ARCH-C', 'IL-TB-ARCH-D', 'IL-TB-ANSI-A', 'IL-TB-ANSI-B', 'IL-TB-ANSI-D']);
    const tags = titleBlocks[1]!.items.filter((item) => item[0] === 'ATTDEF').map((item) => item[1]);
    expect(tags).toContain('PROJECT');
    expect(tags).toContain('SHEET_NUMBER');
  });

  it('only writes ASCII', () => {
    const text = cadAssetsLisp();
    expect([...text].every((char) => char === '\n' || (char >= ' ' && char <= '~'))).toBe(true);
  });
});
