import { describe, expect, it } from 'vitest';
import { formatFeet, formatFeetInches, parseLength } from './length';

describe('parseLength', () => {
  it.each([
    ['12', 12],
    ['12.5', 12.5],
    ['12.5 ft', 12.5],
    ['12.5ft', 12.5],
    ["12'", 12],
    ['12\'6"', 12.5],
    ['12\' 6"', 12.5],
    ['12 ft 6 in', 12.5],
    ['12ft6in', 12.5],
    ["12' 6", 12.5],
    ['12′ 6″', 12.5],
    ['150"', 12.5],
    ['150 in', 12.5],
    ['.5', 0.5],
    ['1,200', 1200],
  ])('reads %s as %s ft', (text, feet) => {
    expect(parseLength(text)).toBeCloseTo(feet, 6);
  });

  it('converts metric', () => {
    expect(parseLength('3 m')).toBeCloseTo(9.8425, 3);
    expect(parseLength('300 cm')).toBeCloseTo(9.8425, 3);
  });

  it.each(['', '  ', '-3', 'abc', '12 ft 14 in', '1..2', '12 yd'])('refuses %j', (text) => {
    expect(parseLength(text)).toBeNull();
  });
});

describe('formatting', () => {
  it('drops trailing zeros', () => {
    expect(formatFeet(12.5)).toBe('12.5');
    expect(formatFeet(12)).toBe('12');
    expect(formatFeet(1 / 3)).toBe('0.33');
    expect(formatFeet(undefined)).toBe('');
  });

  it('reads as feet and inches', () => {
    expect(formatFeetInches(12.5)).toBe("12' 6\"");
    expect(formatFeetInches(12)).toBe("12'");
    expect(formatFeetInches(11.99)).toBe("12'");
  });
});
