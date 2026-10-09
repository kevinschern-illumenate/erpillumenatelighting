import type { FontBytes } from '@ill/serializers/pdf/fonts';

/**
 * Fetch the drawing fonts served with the app. Lives in the app, not in @ill/serializers, so the
 * serializer stays free of network code (plan H1 rule 4). The fonts are published with the app in
 * WP-3.7; until then nothing calls this.
 */
export async function loadFontBytes(
  family: 'Arimo' | 'RobotoCondensed' = 'Arimo',
  base = import.meta.env.BASE_URL,
): Promise<FontBytes> {
  const read = async (style: string) => {
    const response = await fetch(`${base}fonts/${family}-${style}.ttf`);
    if (!response.ok) throw new Error('The local font could not be loaded.');
    return new Uint8Array(await response.arrayBuffer());
  };
  return { regular: await read('Regular'), bold: await read('Bold'), name: family };
}
