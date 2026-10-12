// Writes the design JSON Schema the server validates against (plan H5). CI fails if it is stale.
import { copyFileSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { runnerImport } from 'vite';

const target = resolve(
  import.meta.dirname,
  '../../../illumenate_lighting/public/system_designer/schema/design.schema.json',
);
const { module } = await runnerImport(
  resolve(import.meta.dirname, '../packages/core-schemas/scripts/export-schema.ts'),
);
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, module.exportSchemaText());
console.log(`Wrote ${target}`);

// The NEC tables the Python verification mirror reads (plan §18.2); a parity test keeps them identical.
const tables = resolve(
  import.meta.dirname,
  '../../../illumenate_lighting/illumenate_lighting/system_design/code_tables',
);
mkdirSync(tables, { recursive: true });
for (const name of readdirSync(resolve(import.meta.dirname, '../packages/data/src/nec')))
  if (name.endsWith('.json'))
    copyFileSync(resolve(import.meta.dirname, '../packages/data/src/nec', name), resolve(tables, name));
console.log(`Wrote ${tables}`);
