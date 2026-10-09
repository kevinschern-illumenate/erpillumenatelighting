/** Inputs to a drawing that are not part of the project file. */
export interface DrawingOptions {
  /** The dealer's logo for the title block (plan §12.1, `Customer.dealer_logo`): a PNG or JPEG data URL. */
  dealerLogo?: { src: string; widthPx: number; heightPx: number };
}
