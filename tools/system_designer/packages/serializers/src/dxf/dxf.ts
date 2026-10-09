import JSZip from 'jszip';
import { seedLayers } from '@ill/data/seeds';
import {
  translate,
  type BlockRef,
  type Drawing,
  type Primitive,
  type Sheet,
  type SymbolDef,
} from '@ill/drawing/model';
import { textWidth } from '@ill/drawing/text';
import { flattenContour } from '@ill/drawing/brand';

const clean = (value: string) =>
  value
    .replace(/[\r\n]/g, ' ')
    .replace(
      /[\u0080-\uffff]/g,
      (c) => `\\U+${c.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')}`,
    );
const mtext = (value: string) =>
  clean(value.replaceAll('\\', '\\\\').replaceAll('{', '\\{').replaceAll('}', '\\}')).replaceAll(
    '\\\\P',
    '\\P',
  );
type Pair = [number, string | number];
class Writer {
  parts: string[] = [];
  counter = 256;
  handle() {
    return (this.counter++).toString(16).toUpperCase();
  }
  add(...pairs: Pair[]) {
    for (const [code, value] of pairs)
      this.parts.push(
        String(code),
        typeof value === 'number' ? String(Number(value.toFixed(8))) : value,
      );
  }
  section(name: string) {
    this.add([0, 'SECTION'], [2, name]);
  }
  end() {
    this.add([0, 'ENDSEC']);
  }
  entity(type: string, layer: string, owner: string, subclass: string, handle = this.handle()) {
    this.add(
      [0, type],
      [5, handle],
      [330, owner],
      [100, 'AcDbEntity'],
      [8, layer],
      [100, subclass],
    );
    return handle;
  }
}
function writePrimitive(w: Writer, p: Primitive, owner: string) {
  if (p.layer === 'E-ANNO-QAFL') return;
  const style = () => {
    const subclass = w.parts.splice(-2);
    if (p.lineweightMm) w.add([370, Math.round(p.lineweightMm * 100)]);
    if (p.linetype) w.add([6, p.linetype]);
    w.parts.push(...subclass);
  };
  if (p.kind === 'line') {
    w.entity('LINE', p.layer, owner, 'AcDbLine');
    style();
    w.add([10, p.from.x], [20, p.from.y], [30, 0], [11, p.to.x], [21, p.to.y], [31, 0]);
  } else if (p.kind === 'polyline' || p.kind === 'rect') {
    const points =
      p.kind === 'polyline'
        ? p.points
        : [
            { x: p.x, y: p.y },
            { x: p.x + p.width, y: p.y },
            { x: p.x + p.width, y: p.y + p.height },
            { x: p.x, y: p.y + p.height },
          ];
    w.entity('LWPOLYLINE', p.layer, owner, 'AcDbPolyline');
    style();
    w.add([90, points.length], [70, p.kind === 'rect' || p.closed ? 1 : 0]);
    for (const point of points) w.add([10, point.x], [20, point.y]);
  } else if (p.kind === 'circle' || p.kind === 'arc') {
    w.entity(p.kind === 'circle' ? 'CIRCLE' : 'ARC', p.layer, owner, 'AcDbCircle');
    style();
    w.add([10, p.x], [20, p.y], [30, 0], [40, p.radius]);
    if (p.kind === 'arc') w.add([100, 'AcDbArc'], [50, p.startDeg], [51, p.endDeg]);
  } else if (p.kind === 'hatch' || p.kind === 'filledPath') {
    const loops = p.kind === 'hatch' ? [p.points] : p.contours.map((c) => flattenContour(c));
    w.entity('HATCH', p.layer, owner, 'AcDbHatch');
    w.add(
      [10, 0],
      [20, 0],
      [30, 0],
      [210, 0],
      [220, 0],
      [230, 1],
      [2, 'SOLID'],
      [70, 1],
      [71, 0],
      [91, loops.length],
    );
    for (const loop of loops) {
      w.add([92, 2], [72, 0], [73, 1], [93, loop.length]);
      for (const point of loop) w.add([10, point.x], [20, point.y]);
      w.add([97, 0]);
    }
    w.add([75, 0], [76, 1], [98, 0]);
  } else if (p.multiline || p.value.includes('\n')) {
    w.entity('MTEXT', p.layer, owner, 'AcDbMText');
    w.add(
      [10, p.x],
      [20, p.y + p.heightIn],
      [30, 0],
      [40, p.heightIn],
      [41, textWidth(p.value, p.heightIn, p.font) + 0.03],
      [71, p.hAlign === 'center' ? 2 : p.hAlign === 'right' ? 3 : 1],
      [72, 1],
      [7, p.font === 'bold' ? 'BOLD' : 'MAIN'],
      [50, (p.rotation * Math.PI) / 180],
      [73, 2],
      [44, 1.45],
    );
    const content = p.value.split('\n').map(mtext).join('\\P');
    let pos = 0;
    while (content.length - pos > 240) {
      w.add([3, content.slice(pos, pos + 240)]);
      pos += 240;
    }
    w.add([1, content.slice(pos)]);
  } else {
    w.entity('TEXT', p.layer, owner, 'AcDbText');
    textFields(
      w,
      p.x,
      p.y,
      p.value,
      p.heightIn,
      p.font === 'bold' ? 'BOLD' : 'MAIN',
      p.rotation,
      p.hAlign,
    );
    w.add([100, 'AcDbText'], [73, 0]);
  }
}
function textFields(
  w: Writer,
  x: number,
  y: number,
  value: string,
  height: number,
  style: string,
  rotation = 0,
  align = 'left',
) {
  w.add(
    [10, x],
    [20, y],
    [30, 0],
    [40, height],
    [1, clean(value)],
    [50, rotation],
    [41, 1],
    [7, style],
    [72, align === 'center' ? 1 : align === 'right' ? 2 : 0],
    [11, x],
    [21, y],
    [31, 0],
  );
}
function block(w: Writer, s: SymbolDef, owner: string) {
  w.entity('BLOCK', '0', owner, 'AcDbBlockBegin');
  w.add([2, s.id], [70, 2], [10, 0], [20, 0], [30, 0], [3, s.id], [1, '']);
  s.prims.forEach((p) => writePrimitive(w, p, owner));
  for (const a of s.attributes) {
    w.entity('ATTDEF', 'E-ANNO-TAGS', owner, 'AcDbText');
    textFields(w, a.x, a.y, a.default, a.height, a.tag === 'TAG' ? 'BOLD' : 'MAIN', 0, a.hAlign);
    w.add(
      [100, 'AcDbAttributeDefinition'],
      [280, 0],
      [3, a.tag],
      [2, a.tag],
      [70, a.visible ? 0 : 1],
      [73, 0],
      [74, 0],
      [280, 1],
    );
  }
  w.entity('ENDBLK', '0', owner, 'AcDbBlockEnd');
}
function insert(w: Writer, p: BlockRef, s: SymbolDef, owner: string, offset: number) {
  const handle = w.entity('INSERT', p.layer, owner, 'AcDbBlockReference');
  w.add(
    [66, 1],
    [2, p.symbolId],
    [10, p.x + offset],
    [20, p.y],
    [30, 0],
    [41, 1],
    [42, 1],
    [43, 1],
    [50, p.rotation],
  );
  for (const a of s.attributes) {
    const at = translate(
      {
        kind: 'text',
        layer: 'E-ANNO-TAGS',
        font: 'main',
        heightIn: a.height,
        value: '',
        x: a.x,
        y: a.y,
        rotation: 0,
        hAlign: a.hAlign,
        vAlign: 'bottom',
      },
      p.x + offset,
      p.y,
      p.rotation,
    );
    if (at.kind !== 'text') throw new Error('Invalid attribute geometry');
    w.entity('ATTRIB', 'E-ANNO-TAGS', handle, 'AcDbText');
    textFields(
      w,
      at.x,
      at.y,
      p.attributes[a.tag] ?? a.default,
      a.height,
      a.tag === 'TAG' ? 'BOLD' : 'MAIN',
      p.rotation,
      a.hAlign,
    );
    w.add(
      [100, 'AcDbAttribute'],
      [280, 0],
      [2, a.tag],
      [70, a.visible ? 0 : 1],
      [73, 0],
      [74, 0],
      [280, 1],
    );
  }
  w.entity('SEQEND', p.layer, handle, 'AcDbSequenceEnd');
  // SEQEND has only the AcDbEntity subclass; AcDbSequenceEnd is not a DXF subclass.
  w.parts.splice(-2);
}
export function serializeDxf(sheets: Sheet[]): string {
  if (!sheets.length) throw new Error('No sheets selected');
  const w = new Writer();
  const blocks = [
    ...new Map(
      sheets.flatMap((s) =>
        s.prims
          .filter((p) => p.kind === 'block')
          .map((p) => [p.symbolId, s.blocks.find((b) => b.id === p.symbolId)!] as const),
      ),
    ).values(),
  ];
  const layerHandle = w.handle(),
    ltypeHandle = w.handle(),
    styleHandle = w.handle(),
    recordHandle = w.handle();
  const model = w.handle(),
    paper = w.handle();
  const records = new Map(blocks.map((b) => [b.id, w.handle()]));
  const root = w.handle();
  const plotDictionary = w.handle(),
    normalPlot = w.handle();
  w.section('HEADER');
  w.add(
    [9, '$ACADVER'],
    [1, 'AC1021'],
    [9, '$DWGCODEPAGE'],
    [3, 'ANSI_1252'],
    [9, '$INSUNITS'],
    [70, 1],
    [9, '$MEASUREMENT'],
    [70, 0],
    [9, '$LTSCALE'],
    [40, 1],
    [9, '$TEXTSTYLE'],
    [7, 'MAIN'],
    [9, '$HANDSEED'],
    [5, '__HANDSEED__'],
  );
  w.end();
  w.section('TABLES');
  for (const table of ['VIEW', 'UCS', 'VPORT', 'DIMSTYLE']) {
    w.add([0, 'TABLE'], [2, table], [5, w.handle()], [330, '0'], [100, 'AcDbSymbolTable']);
    if (table === 'DIMSTYLE') w.add([100, 'AcDbDimStyleTable']);
    w.add([70, 0], [0, 'ENDTAB']);
  }
  w.add(
    [0, 'TABLE'],
    [2, 'LTYPE'],
    [5, ltypeHandle],
    [330, '0'],
    [100, 'AcDbSymbolTable'],
    [70, seedLayers.linetypes.length + 2],
  );
  for (const l of [
    { name: 'ByLayer', description: 'ByLayer', patternIn: [] },
    { name: 'ByBlock', description: 'ByBlock', patternIn: [] },
    ...seedLayers.linetypes,
  ]) {
    w.add(
      [0, 'LTYPE'],
      [5, w.handle()],
      [330, ltypeHandle],
      [100, 'AcDbSymbolTableRecord'],
      [100, 'AcDbLinetypeTableRecord'],
      [2, l.name],
      [70, 0],
      [3, l.description],
      [72, 65],
      [73, l.patternIn.length],
      [40, l.patternIn.reduce((a, b) => a + Math.abs(b), 0)],
    );
    for (const p of l.patternIn) w.add([49, p], [74, 0]);
  }
  w.add([0, 'ENDTAB']);
  const layers = [
    { name: '0', aciColor: 7, linetype: 'Continuous', lineweightMm: 0.18 },
    ...seedLayers.layers.filter((l) => l.export),
  ];
  w.add(
    [0, 'TABLE'],
    [2, 'LAYER'],
    [5, layerHandle],
    [330, '0'],
    [100, 'AcDbSymbolTable'],
    [70, layers.length],
  );
  for (const l of layers)
    w.add(
      [0, 'LAYER'],
      [5, w.handle()],
      [330, layerHandle],
      [100, 'AcDbSymbolTableRecord'],
      [100, 'AcDbLayerTableRecord'],
      [2, l.name],
      [70, 0],
      [62, l.aciColor],
      [6, l.linetype],
      [370, Math.round(l.lineweightMm * 100)],
      [290, 1],
      [390, normalPlot],
    );
  w.add([0, 'ENDTAB']);
  w.add(
    [0, 'TABLE'],
    [2, 'STYLE'],
    [5, styleHandle],
    [330, '0'],
    [100, 'AcDbSymbolTable'],
    [70, 3],
  );
  for (const [name, file] of [
    ['Standard', 'arial.ttf'],
    [
      'MAIN',
      sheets[0]?.fontFamily === 'RobotoCondensed' ? 'RobotoCondensed-Regular.ttf' : 'arial.ttf',
    ],
    [
      'BOLD',
      sheets[0]?.fontFamily === 'RobotoCondensed' ? 'RobotoCondensed-Bold.ttf' : 'arialbd.ttf',
    ],
  ])
    w.add(
      [0, 'STYLE'],
      [5, w.handle()],
      [330, styleHandle],
      [100, 'AcDbSymbolTableRecord'],
      [100, 'AcDbTextStyleTableRecord'],
      [2, name!],
      [70, 0],
      [40, 0],
      [41, 1],
      [50, 0],
      [71, 0],
      [42, 0.09375],
      [3, file!],
      [4, ''],
    );
  w.add([0, 'ENDTAB']);
  const appTable = w.handle();
  w.add([0, 'TABLE'], [2, 'APPID'], [5, appTable], [330, '0'], [100, 'AcDbSymbolTable'], [70, 1]);
  w.add(
    [0, 'APPID'],
    [5, w.handle()],
    [330, appTable],
    [100, 'AcDbSymbolTableRecord'],
    [100, 'AcDbRegAppTableRecord'],
    [2, 'ACAD'],
    [70, 0],
    [0, 'ENDTAB'],
  );
  w.add(
    [0, 'TABLE'],
    [2, 'BLOCK_RECORD'],
    [5, recordHandle],
    [330, '0'],
    [100, 'AcDbSymbolTable'],
    [70, blocks.length + 2],
  );
  for (const [name, handle] of [['*Model_Space', model], ['*Paper_Space', paper], ...records])
    w.add(
      [0, 'BLOCK_RECORD'],
      [5, handle!],
      [330, recordHandle],
      [100, 'AcDbSymbolTableRecord'],
      [100, 'AcDbBlockTableRecord'],
      [2, name!],
      [70, 1],
      [280, 1],
      [281, 0],
    );
  w.add([0, 'ENDTAB']);
  w.end();
  w.section('BLOCKS');
  for (const [name, handle] of [
    ['*Model_Space', model],
    ['*Paper_Space', paper],
  ]) {
    w.entity('BLOCK', '0', handle!, 'AcDbBlockBegin');
    w.add([2, name!], [70, 0], [10, 0], [20, 0], [30, 0], [3, name!], [1, '']);
    w.entity('ENDBLK', '0', handle!, 'AcDbBlockEnd');
  }
  for (const b of blocks) block(w, b, records.get(b.id)!);
  w.end();
  w.section('ENTITIES');
  let offset = 0;
  for (const sheet of sheets) {
    for (const p of sheet.prims) {
      if (p.layer === 'E-ANNO-QAFL') continue;
      if (p.kind === 'block')
        insert(
          w,
          p,
          sheet.blocks.find((b) => b.id === p.symbolId)!,
          model,
          offset,
        );
      else writePrimitive(w, translate(p, offset, 0), model);
    }
    offset += sheet.widthIn + 2;
  }
  w.end();
  w.section('OBJECTS');
  w.add(
    [0, 'DICTIONARY'],
    [5, root],
    [330, '0'],
    [100, 'AcDbDictionary'],
    [281, 1],
    [3, 'ACAD_PLOTSTYLENAME'],
    [350, plotDictionary],
  );
  w.add(
    [0, 'ACDBDICTIONARYWDFLT'],
    [5, plotDictionary],
    [330, root],
    [100, 'AcDbDictionary'],
    [281, 1],
    [3, 'Normal'],
    [350, normalPlot],
    [100, 'AcDbDictionaryWithDefault'],
    [340, normalPlot],
  );
  w.add([0, 'ACDBPLACEHOLDER'], [5, normalPlot], [330, plotDictionary]);
  w.end();
  w.add([0, 'EOF']);
  return w.parts.join('\r\n').replace('__HANDSEED__', w.handle()) + '\r\n';
}
export async function serializeDxfZip(
  drawing: Drawing,
  fontFiles: Record<string, Uint8Array | string> = {},
): Promise<Uint8Array> {
  const zip = new JSZip();
  for (const sheet of drawing.sheets)
    zip.file(`${sheet.number.replace(/[^\w.-]/g, '_')}.dxf`, serializeDxf([sheet]), {
      date: new Date('2000-01-01T00:00:00Z'),
    });
  for (const [name, bytes] of Object.entries(fontFiles))
    zip.file(`fonts/${name}`, bytes, { date: new Date('2000-01-01T00:00:00Z') });
  return zip.generateAsync({
    type: 'uint8array',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 },
    platform: 'DOS',
  });
}
