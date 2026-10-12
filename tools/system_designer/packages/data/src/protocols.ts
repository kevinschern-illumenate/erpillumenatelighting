import { ProtocolSchema, type Protocol } from '@ill/core-schemas/common';
import table from './protocols.json';

/** Appendix B.1, shared with illumenate_lighting/.../system_design/protocols.py through protocols.json. */
export const ENGINE_PROTOCOLS = ProtocolSchema.array().parse(table.engineProtocols) as readonly Protocol[];
export const ATTRIBUTE_PROTOCOLS: Readonly<Record<string, Protocol>> = Object.fromEntries(
  Object.entries(table.attributeProtocols).map(([key, value]) => [key, ProtocolSchema.parse(value)]),
);
export const PHASE_PROTOCOLS: ReadonlySet<Protocol> = new Set(ProtocolSchema.array().parse(table.phaseProtocols));
export const DMX_PROTOCOLS: ReadonlySet<Protocol> = new Set(ProtocolSchema.array().parse(table.dmxProtocols));
