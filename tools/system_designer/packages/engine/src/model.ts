import { z } from 'zod';
import { AwgSchema, EnvironmentSchema, RunTypeSchema, ProtocolSchema } from '@ill/core-schemas/common';
import { ValidationMessageSchema } from '@ill/core-schemas/project';

const EndpointSchema = z.object({ id: z.string(), tag: z.string(), port: z.string().optional() });
export const RunInputSchema = z.object({
  runId: z.string(),
  type: RunTypeSchema,
  protocol: ProtocolSchema.optional(),
  from: EndpointSchema,
  to: EndpointSchema,
  entityRef: z.string(),
  lengthFt: z.number().nonnegative(),
  currentA: z.number().nonnegative(),
  voltageV: z.number().nonnegative(),
  wattsW: z.number().nonnegative(),
  channelCurrentsA: z.array(z.number().nonnegative()),
  phase: z.enum(['1PH', '3PH']),
  env: EnvironmentSchema,
  breakerA: z.number().optional(),
  terminalMaxAwg: z.array(AwgSchema),
  minOperatingV: z.number().optional(),
  required: z.object({
    power: z.number(),
    ground: z.number(),
    channel: z.number(),
    signal: z.number(),
    dataPair: z.number(),
  }),
  distributed: z
    .object({ qty: z.number(), homeRunFt: z.number(), interFixtureFt: z.number() })
    .optional(),
  maxDataLengthFt: z.number().optional(),
});
export type RunInput = z.infer<typeof RunInputSchema>;
export const WireCandidateSchema = z.object({
  wireTypeId: z.string(),
  awg: AwgSchema.optional(),
  eligible: z.boolean(),
  reasons: z.array(z.string()),
  ampacityA: z.number().nullable(),
  vdV: z.number().nullable(),
  vdPct: z.number().nullable(),
  endV: z.number().nullable(),
  maxLengthFt: z.number().nullable(),
  terminalOk: z.boolean(),
});
export type WireCandidate = z.infer<typeof WireCandidateSchema>;
export const RunResultSchema = RunInputSchema.extend({
  tag: z.string(),
  wireTypeId: z.string().nullable(),
  parallelSets: z.number(),
  parallelCommonConductors: z.number(),
  overridden: z.boolean(),
  vdV: z.number().nullable(),
  vdPct: z.number().nullable(),
  endV: z.number().nullable(),
  ampacityA: z.number().nullable(),
  checks: z.object({
    ampacity: z.boolean().nullable(),
    terminal: z.boolean().nullable(),
    voltageDrop: z.boolean().nullable(),
  }),
  candidates: z.array(WireCandidateSchema),
  messages: z.array(ValidationMessageSchema),
});
export type RunResult = z.infer<typeof RunResultSchema>;
export const LoadingSchema = z.object({
  entityId: z.string(),
  tag: z.string(),
  kind: z.enum(['psu', 'decoder', 'circuit']),
  port: z.string(),
  wattsW: z.number(),
  currentA: z.number(),
  capacity: z.number(),
  percent: z.number(),
  units: z.enum(['W', 'A']),
  count: z.number(),
});
export const DmxPatchSchema = z.object({
  entityId: z.string(),
  tag: z.string(),
  universe: z.number(),
  startAddress: z.number().nullable(),
  footprint: z.number(),
  endAddress: z.number().nullable(),
  auto: z.boolean(),
});
export const DmxSegmentSchema = z.object({
  id: z.string(),
  root: z.string(),
  members: z.array(z.string()),
  lengthFt: z.number(),
  unitLoads: z.number(),
  ends: z.array(z.string()),
});
export const BomItemSchema = z.object({
  key: z.string(),
  sku: z.string(),
  description: z.string(),
  quantity: z.number(),
  unit: z.enum(['ea', 'ft']),
  reels: z.number().optional(),
  isExample: z.boolean(),
});
export const EngineResultSchema = z.object({
  runs: z.array(RunResultSchema),
  loading: z.array(LoadingSchema),
  patch: z.array(DmxPatchSchema),
  segments: z.array(DmxSegmentSchema),
  messages: z.array(ValidationMessageSchema),
  bom: z.array(BomItemSchema),
  wireTagMap: z.record(z.string(), z.string()),
  loadWatts: z.record(z.string(), z.number()),
  splits: z.array(z.object({ loadId: z.string(), feeds: z.number() })),
});
export type EngineResult = z.infer<typeof EngineResultSchema>;
export type Loading = z.infer<typeof LoadingSchema>;
export type DmxPatch = z.infer<typeof DmxPatchSchema>;
export type DmxSegment = z.infer<typeof DmxSegmentSchema>;
export type BomItem = z.infer<typeof BomItemSchema>;
