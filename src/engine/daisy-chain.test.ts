import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { seedLibrary } from '../state/library-store';
import { CatalogItemSchema } from '../schemas/catalog';
import { buildGraph } from './graph';
import { calculate } from './calculate';
import { controlPortOptions } from './ports';
import { exportCsv, readCsv, autoMap, fieldsFor, previewImport } from '../features/library/import';

describe('DMX decoder daisy chains', () => {
  it('offers imported input-only DMX decoders as THRU sources and keeps explicit chains on one segment', () => {
    const project = demoProject(),
      library = seedLibrary();
    const decoder = library.products.find((p) => p.id === 'decoder-4ch')!;
    library.products[library.products.indexOf(decoder)] = CatalogItemSchema.parse({
      ...decoder,
      specs: { ...decoder.specs, dmxThru: undefined, protocolOut: ['PWM'] },
    });
    project.equipment.find((e) => e.id === 'dec-2')!.controlFrom = {
      ref: 'CON-1',
      port: 'DATA-OUT',
    };
    expect(
      controlPortOptions(project, library.products, 'out', 'DMX512', 'dec-2').map((o) => o.value),
    ).toContain('DEC-1::DATA-OUT');
    project.controlLinks = [
      {
        id: 'chain12',
        from: { ref: 'DEC-1', port: 'DATA-OUT' },
        to: { ref: 'dec-2', port: 'DATA-IN' },
        protocol: 'DMX512',
        lengthFt: 17,
        env: 'riser',
      },
    ];
    const graph = buildGraph(project, library.products);
    expect(graph.control.filter((e) => e.to === 'dec-2')).toEqual([
      expect.objectContaining({ from: 'dec-1', lengthFt: 17 }),
    ]);
    expect(
      controlPortOptions(project, library.products, 'out', 'DMX512', 'dec-1').some((o) =>
        o.value.startsWith('DEC-2'),
      ),
    ).toBe(false);
    const result = calculate(project, library);
    expect(result.messages.some((m) => m.code === 'PROTOCOL_MISMATCH')).toBe(false);
    expect(result.segments).toEqual([
      expect.objectContaining({
        members: ['dec-1', 'dec-2'],
        lengthFt: 67,
        unitLoads: 2,
        ends: ['dec-2'],
      }),
    ]);
    expect(result.runs.filter((r) => r.type === 'dmx')).toHaveLength(2);
    expect(result.patch).toHaveLength(2);
  });

  it('respects a disabled THRU and preserves it in CSV imports', () => {
    const project = demoProject(),
      library = seedLibrary();
    const decoder = library.products.find((p) => p.id === 'decoder-4ch')!;
    if (decoder.specs.kind !== 'decoder') throw new Error('Decoder required');
    decoder.specs.dmxThru = false;
    expect(
      controlPortOptions(project, library.products, 'out', 'DMX512').some((o) =>
        o.value.startsWith('DEC-'),
      ),
    ).toBe(false);
    expect(calculate(project, library).messages.some((m) => m.code === 'PROTOCOL_MISMATCH')).toBe(
      true,
    );
    const csv = readCsv(exportCsv([decoder]));
    const imported = previewImport(
      'products',
      csv.rows,
      autoMap(csv.headers, fieldsFor('products')),
      [],
    );
    expect(imported[0]!.value).toEqual(decoder);
  });

  it('flags two explicit DMX inputs to a receiver', () => {
    const project = demoProject(),
      library = seedLibrary();
    project.controlLinks = [
      {
        id: 'a',
        from: { ref: 'CON-1', port: 'DATA-OUT' },
        to: { ref: 'DEC-2' },
        protocol: 'DMX512',
        lengthFt: 5,
        env: 'riser',
      },
      {
        id: 'b',
        from: { ref: 'DEC-1', port: 'DATA-OUT' },
        to: { ref: 'DEC-2' },
        protocol: 'DMX512',
        lengthFt: 5,
        env: 'riser',
      },
    ];
    expect(calculate(project, library).messages).toContainEqual(
      expect.objectContaining({ code: 'DMX_TOPOLOGY', severity: 'error', entityRef: 'dec-2' }),
    );
  });
});
