import type { ValidationMessage } from '../schemas/project';
export function message(
  code: ValidationMessage['code'],
  severity: ValidationMessage['severity'],
  entityRef: string,
  text: string,
): ValidationMessage {
  return { code, severity, entityRef, text };
}
export const round = (v: number, digits = 3) => Number(v.toFixed(digits));
export function uniqueMessages(messages: ValidationMessage[]): ValidationMessage[] {
  return [...new Map(messages.map((m) => [`${m.code}|${m.entityRef}|${m.text}`, m])).values()];
}
