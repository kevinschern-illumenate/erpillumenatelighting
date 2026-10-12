import type { CatalogItem } from '@ill/core-schemas/catalog';
import { DATA_BY_DEALER_NOTE } from '@ill/engine/derive';

/** The tag on every symbol and schedule row whose numbers the dealer entered (plan D8, §12.1). */
export const DATA_BY_DEALER_TAG = 'DATA BY DEALER';

export const isDealerData = (item: CatalogItem | undefined) =>
  item?.source?.reference === DATA_BY_DEALER_NOTE;

/** The SKU and model line on a symbol; dealer items show their maker and the dealer tag instead of an id. */
export function modelLabel(item: CatalogItem, separator = ' · '): string {
  return isDealerData(item)
    ? `${item.brand}${separator}${item.model} · ${DATA_BY_DEALER_TAG}`
    : `${item.sku}${separator}${item.model}`;
}
