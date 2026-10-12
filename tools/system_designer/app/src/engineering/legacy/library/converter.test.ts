import { describe, expect, it } from 'vitest';
import { seedLibrary } from '@ill/data/library';
import { createDraft } from '@ill/core-schemas/workspace';
import { ProjectSchema } from '@ill/core-schemas/project';
import { CatalogItemSchema } from '@ill/core-schemas/catalog';
import { calculate } from '@ill/engine/calculate';
import { controlPortOptions, powerPortOptions } from '@ill/engine/ports';
import { buildDrawing } from '@ill/drawing/build';
import { exportCsv, readCsv, autoMap, fieldsFor, previewImport } from './import';

function example() {
  const library = seedLibrary();
  const equipment = (id: string, catalogId: string, ref: string, port?: string) => ({
    id,
    tag: id,
    catalogId,
    category: library.products.find((p) => p.id === catalogId)!.category,
    qty: 1,
    location: id,
    fedFrom: { ref, port },
    feedLengthFt: 10,
    env: 'raceway',
  });
  const project = ProjectSchema.parse({
    ...createDraft(),
    sources: [
      {
        id: 'source',
        tag: 'LP-1/1',
        panel: 'LP-1',
        circuit: '1',
        voltage: 120,
        phase: '1PH',
        breakerA: 20,
        poles: 1,
      },
    ],
    equipment: [
      equipment('PS-CONTROL', 'psu-24v-96w', 'source'),
      equipment('PS-LIGHTS', 'psu-24v-96w', 'source'),
      equipment('CONSOLE', 'dmx-controller', 'PS-LIGHTS', 'OUT1'),
      {
        ...equipment('CONVERTER', 'dmx-0-10v-converter', 'PS-CONTROL', 'OUT1'),
        controlFrom: { ref: 'CONSOLE', port: 'DATA-OUT' },
        controlLengthFt: 20,
        dmx: { universe: 1, startAddress: 'auto', terminatorPresent: true },
      },
    ],
    loads: [
      {
        id: 'fixtures',
        typeTag: 'DL1',
        zone: 'Test',
        catalogId: 'downlight-line',
        qty: 3,
        fedFrom: { ref: 'source' },
        homeRunLengthFt: 30,
        feedMethod: 'end',
        env: 'raceway',
      },
      {
        id: 'tape',
        typeTag: 'T1',
        zone: 'Test',
        catalogId: 'tape-white',
        lengthFt: 1,
        fedFrom: { ref: 'PS-LIGHTS', port: 'OUT1' },
        homeRunLengthFt: 10,
        feedMethod: 'end',
        env: 'riser',
      },
    ],
    controlLinks: [
      {
        id: 'dim-fixtures',
        from: { ref: 'CONVERTER', port: 'DIM1' },
        to: { ref: 'fixtures' },
        protocol: '0-10V',
        lengthFt: 30,
        env: 'riser',
      },
      {
        id: 'dim-driver',
        from: { ref: 'CONVERTER', port: 'DIM2' },
        to: { ref: 'PS-LIGHTS' },
        protocol: '0-10V',
        lengthFt: 15,
        env: 'riser',
      },
    ],
  });
  const item = library.products.find((p) => p.id === 'dmx-0-10v-converter')!;
  if (item.specs.kind !== 'controller') throw new Error('Expected controller');
  return { project, library, item, spec: item.specs };
}

describe('DMX to 0-10 V converters', () => {
  it('keeps fixture/driver power separate, patches DMX, sizes signal wires and includes the converter in the BOM', () => {
    const { project, library } = example();
    const result = calculate(project, library);
    expect(result.messages.filter((m) => m.severity === 'error')).toEqual([]);
    expect(
      result.runs.find((r) => r.to.id === 'CONVERTER' && r.type === 'class2-dc'),
    ).toMatchObject({ wattsW: 2, voltageV: 24 });
    expect(
      result.runs.find((r) => r.to.id === 'CONVERTER' && r.type === 'class2-dc')!.currentA,
    ).toBeCloseTo(2 / 24);
    expect(
      result.loading.find((r) => r.entityId === 'PS-CONTROL' && r.kind === 'psu')!.wattsW,
    ).toBe(2);
    expect(result.runs.find((r) => r.to.id === 'fixtures' && r.type === 'lv-branch')!.wattsW).toBe(
      45,
    );
    const signals = result.runs.filter((r) => r.type === '0-10v');
    expect(signals).toHaveLength(2);
    for (const run of signals) {
      expect(run.required.signal).toBe(2);
      expect(run.wattsW).toBe(0);
      expect(run.wireTypeId).not.toBeNull();
    }
    expect(result.patch).toEqual([
      expect.objectContaining({
        entityId: 'CONVERTER',
        footprint: 2,
        startAddress: 1,
        endAddress: 2,
      }),
    ]);
    expect(result.segments[0]!.unitLoads).toBe(1);
    expect(result.bom.some((row) => row.sku === 'EX-DMX-010-CONVERTER' && row.quantity === 1)).toBe(
      true,
    );
    expect(
      controlPortOptions(project, library.products, 'out', '0-10V').map((p) => p.value),
    ).toContain('CONVERTER::DIM1');
    expect(
      powerPortOptions(project, library.products, 'fixtures').some((p) =>
        p.value.startsWith('CONVERTER'),
      ),
    ).toBe(false);
    expect(
      powerPortOptions(project, library.products, 'CONVERTER').some((p) => p.value === 'LP-1/1'),
    ).toBe(false);
  });

  it('accepts low-voltage AC or DC, applies AC power factor only to AC, and honors type-specific voltage/current ratings', () => {
    const { project, library, spec } = example();
    spec.maxInputA = 0.2;
    spec.maxInputAAtV = 24;
    spec.maxInputAType = 'DC';
    const feed = () =>
      calculate(project, library).runs.find(
        (r) => r.to.id === 'CONVERTER' && ['class2-dc', 'landscape-ac'].includes(r.type),
      )!;
    expect(feed().currentA).toBe(0.2);
    project.equipment[0]!.specOverrides = { kind: 'psu', outputCurrent: 'AC' };
    expect(feed().type).toBe('landscape-ac');
    expect(feed().currentA).toBeCloseTo(2 / (24 * 0.9));
    expect(
      powerPortOptions(project, library.products, 'CONVERTER').some(
        (p) => p.value === 'PS-CONTROL::OUT1',
      ),
    ).toBe(true);
    spec.acInputVMin = 12;
    spec.acInputVMax = 12;
    spec.dcInputVMin = 12;
    spec.dcInputVMax = 24;
    expect(
      calculate(project, library).messages.some(
        (m) => m.entityRef === 'CONVERTER' && m.code === 'INPUT_V_OUT_OF_RANGE',
      ),
    ).toBe(true);
    expect(
      powerPortOptions(project, library.products, 'CONVERTER').some(
        (p) => p.value === 'PS-CONTROL::OUT1',
      ),
    ).toBe(false);
  });

  it('checks named output channels, actual receiver quantities and protocol compatibility', () => {
    const { project, library, spec } = example();
    spec.ports.find((p) => p.name === 'DIM1')!.maxDevices = 2;
    expect(
      calculate(project, library).messages.some(
        (m) => m.code === 'DEVICE_CAPACITY' && m.text.includes('3 controlled devices'),
      ),
    ).toBe(true);
    project.controlLinks[0]!.from.port = 'DIM99';
    expect(calculate(project, library).messages.some((m) => m.code === 'INVALID_PORT')).toBe(true);
    delete project.controlLinks[0]!.from.port;
    expect(calculate(project, library).messages.some((m) => m.code === 'INVALID_PORT')).toBe(true);
    project.controlLinks[0]!.from.port = 'DIM1';
    project.controlLinks[0]!.protocol = 'DALI-2';
    expect(calculate(project, library).messages.some((m) => m.code === 'PROTOCOL_MISMATCH')).toBe(
      true,
    );
  });

  it('rejects a manually assigned fixture power feed from the converter without sizing fictitious power outputs', () => {
    const { project, library } = example();
    project.loads[0]!.fedFrom = { ref: 'CONVERTER', port: 'DIM1' };
    const result = calculate(project, library);
    expect(result.messages).toContainEqual(
      expect.objectContaining({ code: 'INVALID_PORT', entityRef: 'fixtures' }),
    );
    expect(result.runs).toEqual([]);
  });

  it('round-trips converter CSVs including separate supply ranges and enforces required converter specs', () => {
    const { item, spec } = example();
    spec.acInputVMin = 12;
    spec.acInputVMax = 12;
    const csv = readCsv(exportCsv([item]));
    const imported = previewImport(
      'products',
      csv.rows,
      autoMap(csv.headers, fieldsFor('products')),
      [],
    );
    expect(imported[0]!.action).toBe('new');
    expect(imported[0]!.value).toEqual(item);
    expect(
      CatalogItemSchema.safeParse({ ...item, specs: { ...spec, dmxFootprint: 0 } }).success,
    ).toBe(false);
    expect(
      CatalogItemSchema.safeParse({ ...item, specs: { ...spec, protocolOut: ['PWM'] } }).success,
    ).toBe(false);
  });

  it('draws the converter with separate supply, DMX and 0-10 V connections', async () => {
    const { project, library } = example();
    const drawing = await buildDrawing(project, library, calculate(project, library));
    const block = drawing.sheets
      .flatMap((s) => s.prims)
      .find((p) => p.kind === 'block' && p.entityId === 'CONVERTER');
    expect(block).toMatchObject({
      symbolId: expect.stringContaining('converter'),
      attributes: { VIN: '24 V DC IN', VOUT: '0-10 V CTRL', WATTS: '2.0 W / UNIT' },
    });
    expect(
      drawing.sheets
        .flatMap((s) => s.prims)
        .some((p) => p.layer === 'E-LITE-CTRL-SIGL' && p.kind === 'polyline'),
    ).toBe(true);
  });
});
