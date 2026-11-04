/**
 * Lengths as people type them on a job site: 12.5, 12.5 ft, 12' 6", 12ft 6in, 150", 3.8 m.
 * Everything is returned in feet, the unit the design stores.
 */
const NUMBER = String.raw`(\d+(?:\.\d+)?|\.\d+)`;
const FEET = String.raw`(?:'|ft\.?|feet|foot)`;
const INCHES = String.raw`(?:"|''|in\.?|inch|inches)`;
const FEET_INCHES = new RegExp(String.raw`^${NUMBER}\s*${FEET}\s*-?\s*(?:${NUMBER}\s*${INCHES}?)?$`);
const INCHES_ONLY = new RegExp(String.raw`^${NUMBER}\s*${INCHES}$`);
const METRES = new RegExp(String.raw`^${NUMBER}\s*(?:m|metres?|meters?)$`);
const CENTIMETRES = new RegExp(String.raw`^${NUMBER}\s*cm$`);
const PLAIN = new RegExp(String.raw`^${NUMBER}$`);

const FEET_PER_METRE = 3.280839895;

/** Feet from typed text, or null when the text is not a length (negative, empty or garbled). */
export function parseLength(text: string): number | null {
  const value = text
    .trim()
    .toLowerCase()
    .replace(/[′’]/g, "'")
    .replace(/[″”“]/g, '"')
    .replace(/,/g, '');
  if (!value) return null;
  let match = value.match(FEET_INCHES);
  if (match) {
    const inches = match[2] ? Number(match[2]) : 0;
    return inches >= 12 && match[2] ? null : Number(match[1]) + inches / 12;
  }
  match = value.match(INCHES_ONLY);
  if (match) return Number(match[1]) / 12;
  match = value.match(METRES);
  if (match) return Number(match[1]) * FEET_PER_METRE;
  match = value.match(CENTIMETRES);
  if (match) return (Number(match[1]) / 100) * FEET_PER_METRE;
  match = value.match(PLAIN);
  return match ? Number(match[1]) : null;
}

/** "12.5" for an input; trailing zeros dropped, at most `digits` decimals. */
export function formatFeet(feet: number | null | undefined, digits = 2): string {
  if (feet == null || !Number.isFinite(feet)) return '';
  return String(Number(feet.toFixed(digits)));
}

/** 12' 6" for reading, rounded to the nearest inch. */
export function formatFeetInches(feet: number): string {
  const total = Math.round(feet * 12);
  const whole = Math.floor(total / 12);
  const inches = total - whole * 12;
  return inches ? `${whole}' ${inches}"` : `${whole}'`;
}
