import type { FontBytes } from '@ill/serializers/pdf/fonts';
import arimoBold from '../../../packages/serializers/fonts/Arimo-Bold.ttf?url';
import arimoRegular from '../../../packages/serializers/fonts/Arimo-Regular.ttf?url';
import robotoBold from '../../../packages/serializers/fonts/RobotoCondensed-Bold.ttf?url';
import robotoRegular from '../../../packages/serializers/fonts/RobotoCondensed-Regular.ttf?url';

/** Font files the build publishes with the app (WP-3.7); PDF and DXF exports embed or ship them. */
export const FONT_URLS = {
  Arimo: { regular: arimoRegular, bold: arimoBold },
  RobotoCondensed: { regular: robotoRegular, bold: robotoBold },
} as const;

/**
 * Fetch the drawing fonts served with the app. Lives in the app, not in @ill/serializers, so the
 * serializer stays free of network code (plan H1 rule 4).
 */
export async function loadFontBytes(family: 'Arimo' | 'RobotoCondensed' = 'Arimo'): Promise<FontBytes> {
  const read = async (url: string) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error('The drawing font could not be loaded.');
    return new Uint8Array(await response.arrayBuffer());
  };
  const urls = FONT_URLS[family];
  return { regular: await read(urls.regular), bold: await read(urls.bold), name: family };
}
