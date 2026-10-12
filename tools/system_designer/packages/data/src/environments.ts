import type { EnvChoice } from '@ill/core-schemas/design';
import type { Environment } from '@ill/core-schemas/common';

export interface EnvironmentOption {
  id: EnvChoice;
  label: string;
  /** Engine `EnvironmentSchema` value used for wire selection. */
  engine: Environment;
  /** Supply location rating for a cabinet in this environment. */
  locationRating: 'Dry' | 'Damp' | 'Wet';
  /** In-wall cable needs a CL2/CL3 or better listing (Appendix B.2; applied in wire selection). */
  needsInWallListing?: true;
}

/** Plan §8 and Appendix B.2: the dealer's environment choices and their engine values. */
export const ENVIRONMENTS: readonly EnvironmentOption[] = [
  { id: 'dry-concealed', label: 'Dry concealed', engine: 'dry-concealed', locationRating: 'Dry' },
  { id: 'in-wall', label: 'In-wall', engine: 'dry-concealed', locationRating: 'Dry', needsInWallListing: true },
  { id: 'plenum', label: 'Plenum', engine: 'plenum', locationRating: 'Dry' },
  { id: 'riser', label: 'Riser', engine: 'riser', locationRating: 'Dry' },
  { id: 'raceway', label: 'Raceway', engine: 'raceway', locationRating: 'Dry' },
  // Damp is wet for wire selection (conservative) but Damp for the supply location rating.
  { id: 'damp', label: 'Damp', engine: 'wet', locationRating: 'Damp' },
  { id: 'wet', label: 'Wet', engine: 'wet', locationRating: 'Wet' },
  { id: 'outdoor-exposed', label: 'Outdoor exposed', engine: 'outdoor-exposed', locationRating: 'Wet' },
  { id: 'direct-burial', label: 'Direct burial', engine: 'direct-burial', locationRating: 'Wet' },
];

const BY_ID = new Map(ENVIRONMENTS.map((option) => [option.id, option]));

export function environmentOption(id: EnvChoice): EnvironmentOption {
  return BY_ID.get(id)!;
}

/** The choice shown for a record: what the dealer picked, else its engine value (every one is a choice). */
export function choiceOf(record: { env: Environment; envChoice?: EnvChoice }): EnvChoice {
  return record.envChoice ?? record.env;
}
