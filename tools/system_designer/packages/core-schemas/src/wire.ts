import { z } from 'zod';
import {
  AwgSchema,
  CountSchema,
  IdSchema,
  ManufacturerRefSchema,
  NonnegativeSchema,
  PositiveSchema,
  ProvenanceSchema,
  RunTypeSchema,
  TextSchema,
  uniqueList,
} from './common';

export const ConductorSchema = z
  .object({
    count: CountSchema,
    awg: AwgSchema,
    material: z.enum(['Cu', 'Al']),
    stranding: z.enum(['solid', 'stranded']),
    role: z.enum(['power', 'ground', 'signal', 'data-pair', 'channel']),
    colors: z.array(IdSchema).optional(),
    resistanceOhmPerKft: PositiveSchema.optional(),
    ampacityA: PositiveSchema.optional(),
  })
  .strict()
  .superRefine((group, ctx) => {
    if (group.role === 'data-pair' && group.count % 2 !== 0)
      ctx.addIssue({
        code: 'custom',
        path: ['count'],
        message: 'Count is individual conductors; twisted pairs require an even count',
      });
    if (group.colors && group.colors.length !== group.count)
      ctx.addIssue({
        code: 'custom',
        path: ['colors'],
        message: 'Colors must match conductor count',
      });
  });
export const WireTypeSchema = z
  .object({
    id: IdSchema,
    name: IdSchema,
    manufacturerRefs: z.array(IdSchema),
    manufacturerRefChecks: z.array(ManufacturerRefSchema),
    category: z.enum([
      'building-wire',
      'cable-assembly',
      'class2-power',
      'data',
      'control',
      'landscape',
      'flex-cord',
    ]),
    applications: z.array(RunTypeSchema).min(1),
    conductors: z.array(ConductorSchema),
    listing: IdSchema,
    ratedV: NonnegativeSchema,
    tempRatingC: z.union([z.literal(60), z.literal(75), z.literal(90), z.literal(105)]),
    plenum: z.boolean(),
    riser: z.boolean(),
    wet: z.boolean(),
    directBurial: z.boolean(),
    sunlightResistant: z.boolean(),
    shielded: z.boolean(),
    impedanceOhm: PositiveSchema.optional(),
    resistanceOhmPerKft: PositiveSchema.optional(),
    ampacityA: PositiveSchema.optional(),
    odIn: PositiveSchema.optional(),
    riserLabel: IdSchema,
    costPerFt: NonnegativeSchema.optional(),
    isExample: z.boolean(),
    verify: z.boolean(),
    source: ProvenanceSchema,
    notes: TextSchema,
    ampacityBasis: z.enum([
      '310.16',
      '402.5-fallback',
      'manufacturer',
      'example',
      'not-applicable',
    ]),
    ampacityTempLimitC: z.union([z.literal(60), z.literal(75), z.literal(90)]).optional(),
    resistanceReferenceTempC: z.number().finite().optional(),
    // ERP catalog (A.6, D7): the Item the designer writes back and how it is sold.
    erpItemCode: IdSchema.optional(),
    salesUom: z.enum(['foot', 'spool']).optional(),
    spoolLengthFt: PositiveSchema.optional(),
  })
  .strict()
  .superRefine((wire, ctx) => {
    const issue = (path: (string | number)[], message: string) =>
      ctx.addIssue({ code: 'custom', path, message });
    const wireless = wire.applications.includes('wireless');
    if (
      wireless &&
      (wire.applications.length !== 1 || wire.conductors.length !== 0 || wire.ratedV !== 0)
    )
      issue(['conductors'], 'Wireless is a no-cable pseudo-type: no conductors or voltage rating');
    if (!wireless && (!wire.conductors.length || wire.ratedV <= 0))
      issue(['conductors'], 'A physical cable needs conductors and a voltage rating');
    if (wire.directBurial && !wire.wet)
      issue(['wet'], 'Direct-burial entries must also be wet rated');
    if (new Set(wire.applications).size !== wire.applications.length)
      issue(['applications'], 'Duplicate application');
    wire.conductors.forEach((c, i) => {
      if (
        ['22', '24'].includes(c.awg) &&
        c.resistanceOhmPerKft === undefined &&
        wire.resistanceOhmPerKft === undefined
      )
        issue(
          ['conductors', i, 'resistanceOhmPerKft'],
          '22/24 AWG require an explicit wire/group resistance; no Table 8 fallback',
        );
    });
    const refs = new Set(wire.manufacturerRefs);
    const checked = new Set(wire.manufacturerRefChecks.map((r) => r.reference));
    if (
      refs.size !== wire.manufacturerRefs.length ||
      checked.size !== wire.manufacturerRefChecks.length ||
      refs.size !== checked.size ||
      [...refs].some((r) => !checked.has(r))
    )
      issue(
        ['manufacturerRefChecks'],
        'Every manufacturer reference must have exactly one verify:true record',
      );
    if (wire.isExample && !wire.verify)
      issue(['verify'], 'Example wire templates require verification');
    if (wire.category === 'building-wire' && wire.ampacityBasis !== '310.16')
      issue(['ampacityBasis'], 'Building-wire ampacity uses the code table');
  });
export type WireType = z.infer<typeof WireTypeSchema>;
export const WireLibrarySchema = uniqueList(WireTypeSchema, (wire) => wire.id);
