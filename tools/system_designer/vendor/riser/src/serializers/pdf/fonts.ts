import fontkit from '@cantoo/fontkit';
import type { PDFDocument } from '@cantoo/pdf-lib';

export type FontBytes = { regular: Uint8Array; bold: Uint8Array; name?: string };
export async function loadFontBytes(
  family: 'Arimo' | 'RobotoCondensed' = 'Arimo',
): Promise<FontBytes> {
  const read = async (style: string) => {
    const response = await fetch(`${import.meta.env.BASE_URL}fonts/${family}-${style}.ttf`);
    if (!response.ok) throw new Error('The local font could not be loaded.');
    return new Uint8Array(await response.arrayBuffer());
  };
  return { regular: await read('Regular'), bold: await read('Bold'), name: family };
}
export async function embedFonts(document: PDFDocument, bytes: FontBytes) {
  document.registerFontkit(fontkit);
  const features = { kern: false, liga: false, clig: false, calt: false };
  return {
    main: await document.embedFont(bytes.regular, {
      subset: false,
      customName: `${bytes.name ?? 'Arimo'}-Regular`,
      features,
    }),
    bold: await document.embedFont(bytes.bold, {
      subset: false,
      customName: `${bytes.name ?? 'Arimo'}-Bold`,
      features,
    }),
  };
}
