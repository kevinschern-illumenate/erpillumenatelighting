import productsJson from './products.example.json';
import wiresJson from './wires.seed.json';
import layersJson from './layers.json';
import notesJson from './general-notes.seed.json';
import resistanceJson from './nec/table8_conductor_resistance.json';
import ampacityJson from './nec/table310_16_ampacity.json';
import fixtureJson from './nec/table402_5_fixture_wire.json';
import effectiveZJson from './nec/table9_effective_z.json';
import ansiB from './titleblocks/ansi-b.json';
import archC from './titleblocks/arch-c.json';
import archD from './titleblocks/arch-d.json';
import ansiD from './titleblocks/ansi-d.json';
import { ProductLibrarySchema } from '../schemas/catalog';
import { WireLibrarySchema } from '../schemas/wire';
import {
  CodeTableLibrarySchema,
  LayerLibrarySchema,
  NotesLibrarySchema,
  TitleBlockSchema,
} from '../schemas/reference-data';

export const seedProducts = ProductLibrarySchema.parse(productsJson);
export const seedWires = WireLibrarySchema.parse(wiresJson);
export const seedLayers = LayerLibrarySchema.parse(layersJson);
export const seedNotes = NotesLibrarySchema.parse(notesJson);
export const seedCodeTables = CodeTableLibrarySchema.parse([
  resistanceJson,
  ampacityJson,
  fixtureJson,
  effectiveZJson,
]);
export const seedTitleBlocks = [ansiB, archC, archD, ansiD].map((template) =>
  TitleBlockSchema.parse(template),
);
