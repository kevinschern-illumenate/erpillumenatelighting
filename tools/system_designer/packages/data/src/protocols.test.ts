import { describe, expect, it } from 'vitest';
import { ProtocolSchema } from '@ill/core-schemas/common';
import { ATTRIBUTE_PROTOCOLS, DMX_PROTOCOLS, ENGINE_PROTOCOLS, PHASE_PROTOCOLS } from './protocols';

describe('protocol vocabulary (Appendix B.1)', () => {
  it('is exactly the engine enum, in order', () => {
    expect([...ENGINE_PROTOCOLS]).toEqual(ProtocolSchema.options);
  });
  it('maps the ERP attribute choices', () => {
    expect(ATTRIBUTE_PROTOCOLS.TRIAC).toBe('phase-forward');
    expect(ATTRIBUTE_PROTOCOLS.ELV).toBe('phase-reverse');
    expect(ATTRIBUTE_PROTOCOLS['DMX/RDM']).toBe('DMX512');
    expect(PHASE_PROTOCOLS.has('phase-reverse')).toBe(true);
    expect(DMX_PROTOCOLS.has('DMX512')).toBe(true);
  });
});
