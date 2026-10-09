import { designJsonSchema } from '../src/design';

/** Pretty, stable JSON Schema text for the committed server copy. */
export function exportSchemaText(): string {
  return `${JSON.stringify(designJsonSchema(), null, 1)}\n`;
}
