import resistanceJson from './nec/table8_conductor_resistance.json';
import ampacityJson from './nec/table310_16_ampacity.json';
import fixtureJson from './nec/table402_5_fixture_wire.json';
import effectiveZJson from './nec/table9_effective_z.json';
import { CodeTableLibrarySchema } from '@ill/core-schemas/reference-data';

/** The NEC code tables alone, so the designer bundle never pulls in the example product seeds. */
export const codeTables = CodeTableLibrarySchema.parse([resistanceJson, ampacityJson, fixtureJson, effectiveZJson]);
