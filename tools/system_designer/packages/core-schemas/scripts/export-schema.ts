import { designJsonSchema } from '../src/design';
import { ilqJsonSchema } from '../src/ilq';

/** Pretty, stable JSON Schema text for the committed server copy. */
export function exportSchemaText(): string {
  return `${JSON.stringify(designJsonSchema(), null, 1)}\n`;
}

/** The draw-to-quote package schema (`ilq/2`) the portal drawing import validates with. */
export function exportIlqSchemaText(): string {
  return `${JSON.stringify(ilqJsonSchema(), null, 1)}\n`;
}
