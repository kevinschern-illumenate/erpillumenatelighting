import { z } from 'zod';
import {
  AWG_SMALL_TO_LARGE,
  AwgSchema,
  CatalogCategorySchema,
  CountSchema,
  IdSchema,
  NonnegativeSchema,
  PositiveSchema,
  ProtocolSchema,
  ProvenanceSchema,
  TextSchema,
  uniqueList,
} from './common';

const protocols = z.array(ProtocolSchema);
const TerminalShape = { terminalMinAwg: AwgSchema.optional(), terminalMaxAwg: AwgSchema };
const InputShape = {
  inputType: z.enum(['AC', 'DC']),
  inputPhase: z.enum(['1PH', '3PH']).optional(),
  inputVMin: PositiveSchema,
  inputVMax: PositiveSchema,
};
const PowerShape = {
  ...InputShape,
  outputType: z.enum(['CV', 'CC']),
  outputCurrent: z.enum(['AC', 'DC']).optional(),
  outputV: PositiveSchema.optional(),
  outputmA: PositiveSchema.optional(),
  outputVMin: PositiveSchema.optional(),
  outputVMax: PositiveSchema.optional(),
  ratedW: PositiveSchema,
  outputs: uniqueList(
    z.object({ name: IdSchema, maxW: PositiveSchema, class2: z.boolean() }).strict(),
    (v) => v.name,
  ).min(1),
  efficiency: PositiveSchema.max(1),
  powerFactor: PositiveSchema.max(1),
  maxInputA: PositiveSchema.optional(),
  maxInputAAtV: PositiveSchema.optional(),
  inrushA: NonnegativeSchema.optional(),
  maxUnitsPer20ABreaker: CountSchema.optional(),
  dimming: protocols,
  terminalMinAwg: AwgSchema,
  terminalMaxAwg: AwgSchema,
  listings: z.array(IdSchema),
  // ERP derate (A.2): the share of ratedW the designer may load.
  usableLoadFactor: PositiveSchema.max(1).optional(),
};
const PsuObject = z.object({ kind: z.literal('psu'), ...PowerShape }).strict();
const DriverObject = z.object({ kind: z.literal('driver'), ...PowerShape }).strict();
const DecoderObject = z
  .object({
    kind: z.literal('decoder'),
    dmxThru: z.boolean().default(true),
    // Older catalog decoders were DC-only; preserve that meaning on load/import.
    powerType: z.enum(['DC', 'AC']).default('DC'),
    inputVMin: PositiveSchema,
    inputVMax: PositiveSchema,
    channels: CountSchema.max(512),
    maxAPerChannel: PositiveSchema,
    maxATotal: PositiveSchema,
    maxWPerChannel: PositiveSchema.optional(),
    maxWTotal: PositiveSchema.optional(),
    outputDimming: z.enum(['phase-forward', 'phase-reverse']).optional(),
    dmxFootprint: CountSchema.max(512),
    protocolIn: protocols.min(1),
    protocolOut: protocols.optional(),
    ...TerminalShape,
    unitLoad: PositiveSchema.default(1),
  })
  .strict();
const ControllerObject = z
  .object({
    kind: z.literal('controller'),
    ...InputShape,
    inputType: z.enum(['AC', 'DC', 'AC/DC']),
    acInputVMin: PositiveSchema.optional(),
    acInputVMax: PositiveSchema.optional(),
    dcInputVMin: PositiveSchema.optional(),
    dcInputVMax: PositiveSchema.optional(),
    ownPowerW: NonnegativeSchema,
    powerFactor: PositiveSchema.max(1).optional(),
    maxInputA: PositiveSchema.optional(),
    maxInputAAtV: PositiveSchema.optional(),
    maxInputAType: z.enum(['AC', 'DC']).optional(),
    protocolIn: protocols,
    protocolOut: protocols,
    ports: uniqueList(
      z
        .object({
          name: IdSchema,
          direction: z.enum(['in', 'out', 'bidirectional']),
          protocol: ProtocolSchema,
          maxDevices: CountSchema.optional(),
        })
        .strict(),
      (p) => p.name,
    ),
    dmxFootprint: z.number().int().min(0).max(512).optional(),
    unitLoad: NonnegativeSchema.optional(),
    maxUniverses: CountSchema.optional(),
    maxPixels: CountSchema.optional(),
    maxDataLengthFt: PositiveSchema.optional(),
    maxBusDevices: CountSchema.optional(),
    startsNewSegment: z.boolean().default(false),
    ...TerminalShape,
  })
  .strict();
const TapeObject = z
  .object({
    kind: z.literal('tape'),
    voltage: z.union([z.literal(12), z.literal(24), z.literal(48)]),
    drive: z.enum(['CV', 'CV-CC-IC']),
    wPerFtMax: PositiveSchema,
    powerBasis: z.enum(['all-channel-max', 'max-operating']),
    channelWPerFtMax: z.array(PositiveSchema).optional(),
    channels: CountSchema.max(512),
    channelMap: z.array(IdSchema).min(1),
    maxSimultaneousPct: PositiveSchema,
    maxRunFtSingleFeed: PositiveSchema,
    maxRunFtDoubleFeed: PositiveSchema,
    freeCutting: z.boolean().default(false),
    cutIntervalIn: PositiveSchema.optional(),
    minOperatingV: PositiveSchema,
    reelLengthFt: PositiveSchema.optional(),
    pixel: z
      .object({
        protocol: z.enum(['WS2811', 'WS2815', 'SK6812', 'SPI-other']),
        pixelsPerFt: PositiveSchema,
        ampsPerPixelMax: PositiveSchema,
      })
      .strict()
      .optional(),
  })
  .strict();
const FixtureObject = z
  .object({
    kind: z.literal('fixture'),
    voltageClass: z.enum(['line', 'low']),
    inputV: z.union([PositiveSchema, z.tuple([PositiveSchema, PositiveSchema])]),
    watts: PositiveSchema,
    inputType: z.enum(['AC', 'DC']).optional(),
    inputPhase: z.enum(['1PH', '3PH']).optional(),
    powerFactor: PositiveSchema.max(1).optional(),
    maxInputA: PositiveSchema.optional(),
    maxInputAAtV: PositiveSchema.optional(),
    drive: z.enum(['CV', 'CC']).optional(),
    mA: PositiveSchema.optional(),
    dimming: protocols,
    integralDriver: z.boolean(),
  })
  .strict();
const AccessoryObject = z
  .object({
    kind: z.literal('accessory'),
    function: z.enum(['junction', 'enclosure', 'distribution', 'termination', 'other']),
    ratedV: PositiveSchema.optional(),
    ratedA: PositiveSchema.optional(),
    ports: z.array(IdSchema),
    listings: z.array(IdSchema),
    notes: TextSchema.optional(),
    terminalMinAwg: AwgSchema.optional(),
    terminalMaxAwg: AwgSchema.optional(),
  })
  .strict();

// Imported records may preserve known facts without pretending that missing ratings are valid.
const IncompleteObject = z
  .object({
    kind: z.literal('incomplete'),
    intendedKind: z.enum([
      'psu',
      'driver',
      'decoder',
      'controller',
      'tape',
      'fixture',
      'accessory',
    ]),
    available: z.record(z.string(), z.json()),
    missingFields: z.array(IdSchema).min(1),
    notes: z.array(TextSchema).default([]),
  })
  .strict();

export const CatalogSpecsSchema = z
  .discriminatedUnion('kind', [
    PsuObject,
    DriverObject,
    DecoderObject,
    ControllerObject,
    TapeObject,
    FixtureObject,
    AccessoryObject,
    IncompleteObject,
  ])
  .superRefine((spec, ctx) => {
    const issue = (path: string, message: string) =>
      ctx.addIssue({ code: 'custom', path: [path], message });
    if (
      'inputType' in spec &&
      spec.inputType === 'DC' &&
      'inputPhase' in spec &&
      spec.inputPhase === '3PH'
    )
      issue('inputPhase', 'DC equipment cannot have three-phase input');
    if (
      (spec.kind === 'psu' || spec.kind === 'driver') &&
      spec.outputType === 'CC' &&
      spec.outputCurrent === 'AC'
    )
      issue('outputCurrent', 'Constant-current LED driver output must be DC');
    if ('inputVMin' in spec && spec.inputVMin > spec.inputVMax)
      issue('inputVMax', 'Input voltage maximum must be at least the minimum');
    if ('terminalMinAwg' in spec && spec.terminalMinAwg && spec.terminalMaxAwg) {
      if (
        AWG_SMALL_TO_LARGE.indexOf(spec.terminalMinAwg) >
        AWG_SMALL_TO_LARGE.indexOf(spec.terminalMaxAwg)
      )
        issue(
          'terminalMaxAwg',
          'Maximum terminal size must accept at least the minimum conductor size',
        );
    }
    if (spec.kind === 'psu' || spec.kind === 'driver') {
      if (spec.outputType === 'CV' && spec.outputV === undefined)
        issue('outputV', 'CV outputs require an output voltage');
      if (spec.outputType === 'CC' && (!spec.outputmA || !spec.outputVMin || !spec.outputVMax))
        issue('outputmA', 'CC outputs require current and compliance voltage range');
      if (spec.outputVMin && spec.outputVMax && spec.outputVMin > spec.outputVMax)
        issue('outputVMax', 'Invalid output compliance range');
      if (spec.maxInputA !== undefined && spec.maxInputAAtV === undefined)
        issue('maxInputAAtV', 'Record the voltage at which maximum input current is specified');
      if (
        spec.maxInputAAtV !== undefined &&
        (spec.maxInputAAtV < spec.inputVMin || spec.maxInputAAtV > spec.inputVMax)
      )
        issue('maxInputAAtV', 'Rated input current voltage is outside the input range');
    }
    if (spec.kind === 'decoder') {
      if (spec.powerType === 'AC' && spec.outputDimming === undefined)
        issue('outputDimming', 'AC primary-side dimming requires the configured phase-cut method');
      if (spec.powerType === 'DC' && spec.outputDimming !== undefined)
        issue('outputDimming', 'Phase-cut output applies only to AC decoders');
    }
    if (spec.kind === 'controller') {
      for (const [min, max, key] of [
        [spec.acInputVMin, spec.acInputVMax, 'acInputVMax'],
        [spec.dcInputVMin, spec.dcInputVMax, 'dcInputVMax'],
      ] as const) {
        if ((min === undefined) !== (max === undefined))
          issue(key, 'Enter both ends of the supply voltage range');
        if (min !== undefined && max !== undefined && min > max)
          issue(key, 'Input voltage range is reversed');
        if (min !== undefined && spec.inputType !== 'AC/DC')
          issue(key, 'Separate AC/DC ranges apply only to dual-supply controllers');
      }
      if (spec.maxInputA !== undefined && spec.maxInputAAtV === undefined)
        issue('maxInputAAtV', 'Record the voltage for the maximum input current rating');
      if (spec.inputType === 'AC/DC' && spec.maxInputA !== undefined && !spec.maxInputAType)
        issue('maxInputAType', 'Identify AC or DC for a dual-supply input current rating');
      if (spec.inputType !== 'AC/DC' && spec.maxInputAType && spec.maxInputAType !== spec.inputType)
        issue('maxInputAType', 'Current rating supply type must match the device input');
      if (spec.maxInputAAtV !== undefined) {
        const currentType = spec.inputType === 'AC/DC' ? spec.maxInputAType : spec.inputType;
        const min =
          spec.inputType === 'AC/DC'
            ? ((currentType === 'AC' ? spec.acInputVMin : spec.dcInputVMin) ?? spec.inputVMin)
            : spec.inputVMin;
        const max =
          spec.inputType === 'AC/DC'
            ? ((currentType === 'AC' ? spec.acInputVMax : spec.dcInputVMax) ?? spec.inputVMax)
            : spec.inputVMax;
        if (spec.maxInputAAtV < min || spec.maxInputAAtV > max)
          issue(
            'maxInputAAtV',
            'Rated input current voltage is outside the applicable input range',
          );
      }
      if (spec.ports.some((p) => p.direction === 'in' && p.maxDevices !== undefined))
        issue('ports', 'Maximum controlled devices applies to output ports');
      if (spec.inputType === 'AC/DC' && spec.inputPhase === '3PH')
        issue('inputPhase', 'Dual AC/DC controllers use a single-phase AC supply');
    }
    if (spec.kind === 'tape') {
      if (spec.freeCutting && spec.cutIntervalIn !== undefined)
        issue(
          'cutIntervalIn',
          'Free-cutting tape has no fixed cut interval. Remove cutIntervalIn.',
        );
      if (!spec.freeCutting && spec.cutIntervalIn === undefined)
        issue(
          'cutIntervalIn',
          'Enter a positive cut interval or explicitly select free-cutting tape.',
        );
      if (
        spec.channelMap.length !== spec.channels ||
        new Set(spec.channelMap).size !== spec.channels
      )
        issue('channelMap', 'Provide one unique name per channel');
      if (spec.channelWPerFtMax && spec.channelWPerFtMax.length !== spec.channels)
        issue('channelWPerFtMax', 'Provide one maximum per channel');
      if (spec.maxSimultaneousPct > spec.channels * 100)
        issue('maxSimultaneousPct', 'Simultaneous percentage cannot exceed channel count × 100');
      if (
        spec.powerBasis === 'max-operating' &&
        spec.maxSimultaneousPct < spec.channels * 100 &&
        !spec.channelWPerFtMax
      )
        issue(
          'channelWPerFtMax',
          'Limited simultaneous operation needs explicit conductor/channel maxima',
        );
      if (spec.minOperatingV > spec.voltage)
        issue('minOperatingV', 'Minimum operating voltage exceeds nominal voltage');
      if (spec.maxRunFtDoubleFeed < spec.maxRunFtSingleFeed)
        issue(
          'maxRunFtDoubleFeed',
          'Double-feed maximum cannot be shorter than single-feed maximum',
        );
    }
    if (spec.kind === 'fixture') {
      if (Array.isArray(spec.inputV) && spec.inputV[0] > spec.inputV[1])
        issue('inputV', 'Input voltage range is reversed');
      if (spec.drive === 'CC' && spec.mA === undefined)
        issue('mA', 'CC fixtures require drive current');
    }
  });
export type CatalogSpecs = z.infer<typeof CatalogSpecsSchema>;

// Partial spec edits retain a discriminator. Validate the merged full catalog item before use.
export const CatalogSpecOverridesSchema = z.discriminatedUnion('kind', [
  PsuObject.partial().required({ kind: true }),
  DriverObject.partial().required({ kind: true }),
  DecoderObject.partial().required({ kind: true }),
  ControllerObject.partial().required({ kind: true }),
  TapeObject.partial().extend({ freeCutting: z.boolean().optional() }).required({ kind: true }),
  FixtureObject.partial().required({ kind: true }),
  AccessoryObject.partial().required({ kind: true }),
]);

export const CatalogItemSchema = z
  .object({
    id: IdSchema,
    sku: IdSchema,
    brand: IdSchema,
    model: IdSchema,
    category: CatalogCategorySchema,
    description: z.string().min(1),
    datasheetUrl: z.url().optional(),
    erpItemCode: IdSchema.optional(),
    isExample: z.boolean(),
    specs: CatalogSpecsSchema,
    source: ProvenanceSchema.optional(),
    sourceData: z.record(z.string(), z.json()).optional(),
    localOverrides: z.array(IdSchema).default([]),
    // D6: supply preference order from the ERP catalog; reveals order, never cost.
    rank: CountSchema.optional(),
  })
  .strict()
  .superRefine((item, ctx) => {
    const category = item.category;
    const kind = ['psu', 'driver', 'tape', 'fixture'].includes(category)
      ? category
      : category === 'dmx-decoder'
        ? 'decoder'
        : ['junction-box', 'enclosure', 'distribution-block'].includes(category)
          ? 'accessory'
          : 'controller';
    if (kind !== (item.specs.kind === 'incomplete' ? item.specs.intendedKind : item.specs.kind))
      ctx.addIssue({
        code: 'custom',
        path: ['specs', 'kind'],
        message: `Category ${category} requires ${kind} specs`,
      });
    if (category === 'dmx-0-10v-converter' && item.specs.kind === 'controller') {
      const spec = item.specs;
      const require = (condition: boolean, path: string, message: string) => {
        if (!condition) ctx.addIssue({ code: 'custom', path: ['specs', path], message });
      };
      require(spec.protocolIn.includes(
        'DMX512',
      ), 'protocolIn', 'Select DMX512 as an input protocol');
      require(spec.protocolOut.includes(
        '0-10V',
      ), 'protocolOut', 'Select 0-10V as an output protocol');
      require((spec.dmxFootprint ?? 0) >
        0, 'dmxFootprint', 'Enter the converter’s DMX address footprint');
      require((spec.unitLoad ?? 0) > 0, 'unitLoad', 'Enter the converter’s DMX unit load');
      require(spec.ports.some(
        (p) => p.protocol === 'DMX512' && p.direction !== 'out',
      ), 'ports', 'Add a DMX512 input port');
      require(spec.ports.some(
        (p) => p.protocol === '0-10V' && p.direction === 'out',
      ), 'ports', 'Add a named 0-10V output for each dimming channel');
    }
    if (
      item.isExample &&
      (!item.description.includes('EXAMPLE – replace with real data') ||
        !item.model.includes('EXAMPLE'))
    )
      ctx.addIssue({
        code: 'custom',
        path: ['description'],
        message: 'Example products must be visibly labelled EXAMPLE – replace with real data',
      });
  })
  .transform((item) => {
    const specs = item.specs;
    if (specs.kind !== 'incomplete' || specs.intendedKind !== 'tape') return item;
    const fields = item.sourceData?.fields;
    const sourceFlag =
      fields && typeof fields === 'object' && !Array.isArray(fields)
        ? fields.is_free_cutting
        : undefined;
    // Upgrade the earlier ERP import from its explicit flag, never from a missing/zero interval.
    // Preserve an explicit local choice or an entered positive interval for the user to resolve.
    const explicitFree = specs.available.freeCutting === true;
    const legacyFree =
      specs.available.freeCutting === undefined &&
      ['1', 1, true].includes(sourceFlag as string | number | boolean);
    if (
      (!explicitFree && !legacyFree) ||
      (specs.available.cutIntervalIn !== undefined && specs.available.cutIntervalIn !== 0)
    )
      return item;
    const available: typeof specs.available = { ...specs.available, freeCutting: true };
    delete available.cutIntervalIn;
    const missing = specs.missingFields.filter((field) => field !== 'cutIntervalIn');
    return {
      ...item,
      specs: {
        ...specs,
        available,
        missingFields: missing.length ? missing : ['Specification review'],
        notes: specs.notes.map((note) =>
          note ===
          'ERP marks this product free-cutting and cut increment is zero. The current tape calculation model requires a positive cut interval; confirm how this product should be represented before activation.'
            ? 'ERP marks this product free-cutting. No fixed cut interval is required.'
            : note,
        ),
      },
    };
  });
export type CatalogItem = z.infer<typeof CatalogItemSchema>;
export const ProductLibrarySchema = uniqueList(CatalogItemSchema, (v) => v.id).superRefine(
  (items, ctx) => {
    const seen = new Set<string>();
    items.forEach((item, i) => {
      if (seen.has(item.sku))
        ctx.addIssue({ code: 'custom', path: [i, 'sku'], message: `Duplicate SKU ${item.sku}` });
      seen.add(item.sku);
    });
  },
);

export function mergeSpecOverrides(
  item: CatalogItem,
  overrides: z.infer<typeof CatalogSpecOverridesSchema>,
): CatalogItem {
  if (item.specs.kind !== overrides.kind)
    throw new Error('Spec override kind does not match catalog item');
  const specs = { ...item.specs, ...overrides };
  if (
    specs.kind === 'tape' &&
    overrides.kind === 'tape' &&
    overrides.freeCutting === true &&
    overrides.cutIntervalIn === undefined
  )
    delete specs.cutIntervalIn;
  return CatalogItemSchema.parse({ ...item, specs });
}

export type PsuSpecs = Extract<CatalogSpecs, { kind: 'psu' }>;
export type DriverSpecs = Extract<CatalogSpecs, { kind: 'driver' }>;
export type DecoderSpecs = Extract<CatalogSpecs, { kind: 'decoder' }>;
export type ControllerSpecs = Extract<CatalogSpecs, { kind: 'controller' }>;
export type TapeSpecs = Extract<CatalogSpecs, { kind: 'tape' }>;
export type FixtureSpecs = Extract<CatalogSpecs, { kind: 'fixture' }>;
export type AccessorySpecs = Extract<CatalogSpecs, { kind: 'accessory' }>;
