// Writes the design JSON Schema the server validates against (plan H5). CI fails if it is stale.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { runnerImport } from 'vite';

const target = resolve(import.meta.dirname, '../../../illumenate_lighting/public/system_designer/schema/design.schema.json');
const { module } = await runnerImport(resolve(import.meta.dirname, '../packages/core-schemas/scripts/export-schema.ts'));
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, module.exportSchemaText());
console.log(`Wrote ${target}`);
