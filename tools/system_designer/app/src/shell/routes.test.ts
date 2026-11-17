import { describe, expect, it } from 'vitest';
import { hashFor, itemFromHash, stepFromHash } from './routes';

describe('step routes (SD-2.7)', () => {
  it('reads the step and the item from the address', () => {
    expect(hashFor('power')).toBe('#/power');
    expect(stepFromHash('#/power')).toBe('power');
    expect(stepFromHash('#power')).toBe('power');
    expect(stepFromHash('#/check?item=PS-1')).toBe('check');
    expect(stepFromHash('#/nowhere')).toBeNull();
    expect(stepFromHash('')).toBeNull();
    expect(itemFromHash('#/check?item=load%3Aa1linear%3A1%3A1')).toBe('load:a1linear:1:1');
    expect(itemFromHash('#/check?x=1&item=PS-1')).toBe('PS-1');
    expect(itemFromHash('#/check')).toBeNull();
    expect(itemFromHash('#/check?item=%E0%A4%A')).toBeNull();
  });
});
