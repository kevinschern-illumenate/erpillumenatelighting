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
  /** What the dealer chose to leave off the sheets; everything is shown when omitted. */
  view?: DrawingView;
}

/**
 * Sheet content a dealer can hide, as on the standalone riser's Drawing page. Each flag is shown
 * unless it is `false`; hiding a detail leaves the layout as it is, so the drawing does not move.
 */
export interface DrawingView {
  /** Cable callouts on the wires (tag, cable, length, voltage drop). */
  wireLabels?: boolean;
  /** DMX addresses on the riser; the control protocols on a client card. */
  dmx?: boolean;
  /** Volts in and out, watts and loading on a card. */
  ratings?: boolean;
  /** The model or part number on a card. */
  models?: boolean;
  /** The length and location under a tape run. */
  lengths?: boolean;
  /** Schedule, legend and key sections to leave off, by title (`RISER_SECTIONS`, `CLIENT_SECTIONS`). */
  hide?: string[];
}

/** The sections of the riser's schedule pages, in the order they are drawn. */
export const RISER_SECTIONS = [
  'EQUIPMENT SCHEDULE',
  'LOAD SCHEDULE',
  'WIRE SCHEDULE',
  'CONTINUATION INDEX',
  'LOADING / CAPACITY',
  'DMX PATCH',
  'BILL OF MATERIALS',
  'GENERAL NOTES',
  'KEY NOTES',
  'REVISIONS',
  'PROJECT RECORD',
  'SYMBOL LEGEND',
  'LINE LEGEND',
] as const;

/** The sections of the client diagram's schedule page, in the order they are drawn. */
export const CLIENT_SECTIONS = [
  'COLOR KEY',
  'FIXTURE SCHEDULE',
  'POWER SUPPLIES AND CONTROLS',
  'WIRE',
  'NOTES',
] as const;
