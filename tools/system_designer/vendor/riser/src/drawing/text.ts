import metrics from '../data/font-metrics.json';
import { text, type LayerName, type TextPrim } from './model';

const widths = metrics as { regular: Record<string, number>; bold: Record<string, number> };
// heightIn is the plotted capital height, matching CAD TEXT, not the font's em square.
export const capHeightRatio = (family = 'Arimo') =>
  family === 'RobotoCondensed' ? 1456 / 2048 : 1409 / 2048;
export const fontEmSize = (height: number, family = 'Arimo') => height / capHeightRatio(family);
export function textWidth(value: string, height = 3 / 32, font: 'main' | 'bold' = 'main'): number {
  const table = font === 'bold' ? widths.bold : widths.regular;
  return Math.max(
    0,
    ...value
      .split('\n')
      .map((line) => [...line].reduce((sum, c) => sum + (table[c] ?? 1), 0) * fontEmSize(height)),
  );
}
export function wrapText(
  value: string,
  width: number,
  height = 3 / 32,
  font: 'main' | 'bold' = 'main',
): string[] {
  const lines: string[] = [];
  for (const paragraph of value.split('\n')) {
    let line = '';
    for (const word of paragraph.split(/\s+/)) {
      if (textWidth(line ? `${line} ${word}` : word, height, font) <= width) {
        line += `${line ? ' ' : ''}${word}`;
        continue;
      }
      if (line) {
        lines.push(line);
        line = '';
      }
      for (const c of [...word]) {
        if (line && textWidth(line + c, height, font) > width) {
          lines.push(line);
          line = '';
        }
        line += c;
      }
    }
    lines.push(line);
  }
  return lines;
}
export function paragraph(
  value: string,
  x: number,
  y: number,
  width: number,
  height = 3 / 32,
  layer: LayerName = 'E-ANNO-TEXT',
  font: 'main' | 'bold' = 'main',
): TextPrim {
  return {
    ...text(wrapText(value, width, height, font).join('\n'), x, y, height, layer, font),
    multiline: true,
  };
}
export function textBounds(p: TextPrim) {
  const width = textWidth(p.value, p.heightIn, p.font);
  const lines = p.value.split('\n').length;
  const x = p.x - (p.hAlign === 'center' ? width / 2 : p.hAlign === 'right' ? width : 0);
  return { x, y: p.y - (lines - 1) * p.heightIn * 1.45, width, height: lines * p.heightIn * 1.45 };
}
