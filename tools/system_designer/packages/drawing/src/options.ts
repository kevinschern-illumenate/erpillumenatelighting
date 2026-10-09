/**
 * The two drawing styles: the engineering riser for installers, and the client diagram a dealer can
 * hand a homeowner. The client diagram uses the same layout, colour-codes products and wires, and
 * replaces the engineering schedules with the fixture schedule and ordering information.
 */
export type DrawingStyle = 'riser' | 'client';

/** Product families the client diagram colours apart. */
export type ClientProductType = 'linear' | 'tape' | 'neon' | 'sheet' | 'fixture';

/** What the client diagram shows on a load, by load id (`load:<run key>`). */
export interface ClientLoad {
  type: ClientProductType;
  /** The part number to show: a configured fixture's own part number, not its tape's. */
  partNumber?: string;
}

/** One fixture schedule line on the client page; every value is already display text. */
export interface ClientFixtureRow {
  type: string;
  product: string;
  partNumber: string;
  qty: string;
  location: string;
}

/** Inputs to a drawing that are not part of the project file. */
export interface DrawingOptions {
  /** The dealer's logo for the title block (plan §12.1, `Customer.dealer_logo`): a PNG or JPEG data URL. */
  dealerLogo?: { src: string; widthPx: number; heightPx: number };
  /** `riser` when omitted. */
  style?: DrawingStyle;
  /** Client style: per-load product family and part number. */
  loads?: Record<string, ClientLoad>;
  /** Client style: the schedule lines the dealer made. */
  fixtureSchedule?: ClientFixtureRow[];
}
