import { describe, expect, it } from 'vitest';
import { demoProject } from '../data/demo';
import { buildDrawing } from '../drawing/build';
import { seedLibrary } from '../state/library-store';
import { CatalogItemSchema } from '../schemas/catalog';
import { calculate } from './calculate';
import { loadProfile, inputCurrent } from './loads';
import { powerPortOptions } from './ports';

describe('incomplete product isolation', () => {
  it.each(['load', 'equipment'] as const)(
    'blocks calculation and drawing for an imported %s, including overrides',
    async (kind) => {
      const project = demoProject(),
        library = seedLibrary();
      const entity = kind === 'load' ? project.loads[0]! : project.equipment[0]!;
      const original = library.products.find((p) => p.id === entity.catalogId)!;
      const pending = CatalogItemSchema.parse({
        ...original,
        specs: {
          kind: 'incomplete',
          intendedKind: original.specs.kind,
          available: {},
          missingFields: ['verified ratings'],
        },
      });
      library.products = library.products.map((p) => (p.id === pending.id ? pending : p));
      for (const withOverride of kind === 'equipment' ? [false, true] : [false]) {
        if (withOverride && 'tag' in entity && original.specs.kind !== 'incomplete')
          entity.specOverrides = original.specs;
        const result = calculate(project, library);
        expect(
          result.messages.some((m) => m.code === 'INCOMPLETE_SPEC' && m.severity === 'error'),
        ).toBe(true);
        expect(result.runs).toEqual([]);
        expect(result.loading).toEqual([]);
        expect(result.bom).toEqual([]);
        expect(result.loadWatts).toEqual({});
        expect(powerPortOptions(project, library.products, entity.id)).toEqual([]);
        await expect(buildDrawing(project, library, result)).rejects.toThrow(
          'Needs specifications',
        );
      }
      expect(() => loadProfile(project.loads[0]!, pending.specs, project.settings)).toThrow(
        'Complete product',
      );
      expect(() => inputCurrent(100, 24, pending.specs)).toThrow('Complete product');
    },
  );
  it('leaves an existing project unchanged when unused pending products are added', () => {
    const project = demoProject(),
      library = seedLibrary();
    const before = calculate(project, library);
    library.products.push(
      CatalogItemSchema.parse({
        ...library.products[0],
        id: 'unused',
        sku: 'EX-UNUSED',
        specs: {
          kind: 'incomplete',
          intendedKind: 'psu',
          available: {},
          missingFields: ['efficiency'],
        },
      }),
    );
    expect(calculate(project, library)).toEqual(before);
  });
});
