import { z } from 'zod';

export const IdSchema = z.string().trim().min(1).max(160);
export const TextSchema = z.string().max(4000);
export const PositiveSchema = z.number().finite().positive();
export const NonnegativeSchema = z.number().finite().nonnegative();
export const CountSchema = z.number().int().positive();
export const PercentSchema = z.number().finite().min(0).max(100);
export const AWG_SMALL_TO_LARGE = [
  '24',
  '22',
  '20',
  '18',
  '16',
  '14',
  '12',
  '10',
  '8',
  '6',
  '4',
  '3',
  '2',
  '1',
  '1/0',
  '2/0',
  '3/0',
  '4/0',
] as const;
export const AwgSchema = z.enum(AWG_SMALL_TO_LARGE);
export type AWG = z.infer<typeof AwgSchema>;
export const ProtocolSchema = z.enum([
  'none',
  'phase-forward',
  'phase-reverse',
  '0-10V',
  '1-10V',
  'DALI-2',
  'DMX512',
  'RDM',
  'sACN',
  'Art-Net',
  'CRMX-wireless',
  'Lutron-QS',
  'Lutron-EcoSystem',
  'PWM',
  'SPI',
]);
export type Protocol = z.infer<typeof ProtocolSchema>;
export const EnvironmentSchema = z.enum([
  'dry-concealed',
  'plenum',
  'riser',
  'raceway',
  'wet',
  'direct-burial',
  'outdoor-exposed',
]);
export type Environment = z.infer<typeof EnvironmentSchema>;
export const RunTypeSchema = z.enum([
  'lv-branch',
  'lv-fixture-whip',
  'class2-dc',
  'class2-dc-multichannel',
  'landscape-ac',
  'dmx',
  'ethernet',
  'spi-data',
  '0-10v',
  'dali',
  'lutron-qs',
  'lutron-ecosystem',
  'wireless',
]);
export type RunType = z.infer<typeof RunTypeSchema>;
export const EquipmentCategorySchema = z.enum([
  'psu',
  'driver',
  'dmx-decoder',
  'dmx-controller',
  'dmx-0-10v-converter',
  'wireless-tx',
  'wireless-rx',
  'pixel-controller',
  'opto-splitter',
  'sacn-gateway',
  'network-switch',
  'lutron-module',
  '0-10v-dimmer',
  'keypad',
  'relay',
  'junction-box',
  'enclosure',
  'distribution-block',
]);
export const CatalogCategorySchema = z.enum([...EquipmentCategorySchema.options, 'tape', 'fixture']);
export const SheetSizeSchema = z.enum(['ANSI_B', 'ARCH_C', 'ARCH_D', 'ANSI_D']);
export const EditionSchema = z.enum(['2020', '2023', '2026']);
export const PortRefSchema = z.object({ ref: IdSchema, port: IdSchema.optional() }).strict();
export const ProvenanceSchema = z
  .object({
    kind: z.enum(['example', 'user-supplied', 'manufacturer', 'code-reference', 'authored-draft']),
    reference: z.string().min(1),
    url: z.url().optional(),
    checkedOn: z.iso.date().optional(),
    note: TextSchema.optional(),
  })
  .strict();
export const ManufacturerRefSchema = z
  .object({ reference: IdSchema, verify: z.literal(true), sourceUrl: z.url().optional() })
  .strict();

export function uniqueList<T extends z.ZodType>(schema: T, key: (value: z.output<T>) => string) {
  return z.array(schema).superRefine((items, ctx) => {
    const seen = new Set<string>();
    items.forEach((item, index) => {
      const value = key(item);
      if (seen.has(value)) ctx.addIssue({ code: 'custom', path: [index], message: `Duplicate key: ${value}` });
      seen.add(value);
    });
  });
}
