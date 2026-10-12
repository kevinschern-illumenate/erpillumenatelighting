import { useRef, useState, type PointerEvent } from 'react';
import { Button } from '../../components/ui/button';
import { useDrawing } from '../../hooks/use-drawing';
import { escapeXml, serializeSvg } from '../../serializers/svg';
import { useProjectStore } from '../../state/project-store';
import { symbols } from '../../drawing/symbols';
import { symbolPort, text, type Sheet } from '../../drawing/model';

export function MiniDrawing() {
  const { drawing, busy, error } = useDrawing();
  const sheet = drawing?.sheets[0];
  return (
    <div className="mini-drawing">
      <p className="editor-help">
        {busy
          ? 'Updating drawing…'
          : error || `${drawing?.sheets.length ?? 0} sheets · open Drawing for pan, zoom and pins`}
      </p>
      {sheet && <div dangerouslySetInnerHTML={{ __html: serializeSvg(sheet, { qa: true }) }} />}
    </div>
  );
}
function gallery(): Sheet {
  const sheet: Sheet = {
    id: 'gallery',
    number: 'SYMBOLS',
    title: 'SYMBOL GALLERY',
    size: 'ARCH_D',
    widthIn: 36,
    heightIn: 24,
    prims: [],
    blocks: symbols,
    nodes: [],
    layoutWarnings: [],
  };
  symbols.forEach((symbol, i) => {
    const x = 1 + (i % 6) * 5.7,
      y = 21 - Math.floor(i / 6) * 5;
    sheet.prims.push({
      kind: 'block',
      symbolId: symbol.id,
      x,
      y,
      rotation: 0,
      scale: 1,
      layer: symbol.prims[0]!.layer,
      attributes: {
        TAG: 'TAG-01',
        MODEL: 'MODEL',
        VIN: '120 V IN',
        VOUT: '24 V OUT',
        WATTS: '76.8 W',
        LOAD_PCT: '80%',
        DMX_ADDR: 'U1 / 1–4',
        LOCATION: 'EXAMPLE',
      },
    });
    for (const port of symbol.ports) {
      const p = symbolPort(symbol, port.name);
      sheet.prims.push(
        { kind: 'circle', x: x + p.x, y: y + p.y, radius: 0.04, layer: 'E-ANNO-QAFL' },
        text(
          port.name,
          x + p.x + (port.side === 'W' ? -0.7 : 0.06),
          y + p.y + 0.14,
          0.09375,
          'E-ANNO-QAFL',
        ),
      );
    }
    sheet.prims.push(
      text(symbol.label, x, y - 0.4, 0.125, 'E-ANNO-TEXT', 'bold'),
      text(
        'ATTR: ' +
          symbol.attributes
            .map((a) => a.tag)
            .slice(0, 4)
            .join(', '),
        x,
        y - 0.65,
      ),
      text(
        symbol.attributes
          .map((a) => a.tag)
          .slice(4)
          .join(', '),
        x,
        y - 0.82,
      ),
    );
  });
  return sheet;
}
const gallerySheet = gallery();
export function DrawingPage() {
  const { drawing, busy, error, project, retry } = useDrawing();
  const update = useProjectStore((s) => s.updateProject);
  const [index, setIndex] = useState(0),
    [zoom, setZoom] = useState(1),
    [qa, setQa] = useState(true),
    [wireTags, setWireTags] = useState(true),
    [dmx, setDmx] = useState(true),
    [showGallery, setGallery] = useState(false);
  const [drag, setDrag] = useState<{
    id: string;
    startX: number;
    startY: number;
    x: number;
    y: number;
    width: number;
    height: number;
    dx: number;
    dy: number;
  } | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const pan = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const sheet = showGallery
    ? gallerySheet
    : drawing?.sheets[Math.min(index, (drawing?.sheets.length ?? 1) - 1)];
  function point(e: PointerEvent<HTMLDivElement>) {
    const svg = e.currentTarget.querySelector('svg');
    if (!svg) return null;
    const matrix = svg.getScreenCTM();
    if (!matrix) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse());
    return { x: p.x, y: (sheet?.heightIn ?? 0) - p.y };
  }
  function down(e: PointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return;
    const id = (e.target as Element).closest('[data-node]')?.getAttribute('data-node');
    const node = sheet?.nodes.find((n) => n.id === id);
    const p = point(e);
    if (node && p && !showGallery) setDrag({ ...node, startX: p.x, startY: p.y, dx: 0, dy: 0 });
    else if (viewport.current)
      pan.current = {
        x: e.clientX,
        y: e.clientY,
        left: viewport.current.scrollLeft,
        top: viewport.current.scrollTop,
      };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent<HTMLDivElement>) {
    if (drag) {
      const p = point(e);
      if (p) setDrag({ ...drag, dx: p.x - drag.startX, dy: p.y - drag.startY });
    } else if (pan.current && viewport.current) {
      viewport.current.scrollLeft = pan.current.left - (e.clientX - pan.current.x);
      viewport.current.scrollTop = pan.current.top - (e.clientY - pan.current.y);
    }
  }
  function up() {
    if (drag && (Math.abs(drag.dx) > 0.01 || Math.abs(drag.dy) > 0.01))
      update({
        layoutOverrides: {
          ...project.layoutOverrides,
          [drag.id]: {
            x: Math.round((drag.x + drag.dx) * 100) / 100,
            y: Math.round((drag.y + drag.dy) * 100) / 100,
            pinned: true,
          },
        },
      });
    setDrag(null);
    pan.current = null;
  }
  let svg = sheet ? serializeSvg(sheet, { qa, wireTags, dmx, interactive: true }) : '';
  if (sheet && !showGallery)
    svg = svg.replace(
      '</svg>',
      sheet.nodes
        .map(
          (n) =>
            `<rect data-node="${escapeXml(n.id)}" x="${n.x}" y="${sheet.heightIn - n.y - n.height}" width="${n.width}" height="${n.height}" fill="transparent" stroke="${n.pinned && qa ? '#b3630b' : 'none'}" stroke-width=".012" stroke-dasharray=".08 .04" style="cursor:move"><title>${escapeXml(n.id)}${n.pinned ? ' · pinned' : ''} · drag to move</title></rect>`,
        )
        .join('') +
        (drag
          ? `<rect x="${drag.x + drag.dx}" y="${sheet.heightIn - drag.y - drag.dy - drag.height}" width="${drag.width}" height="${drag.height}" fill="none" stroke="#00588c" stroke-width=".03"/>`
          : '') +
        '</svg>',
    );
  return (
    <div className="drawing-workspace">
      <div className="action-bar">
        <Button variant="outline" onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}>
          −
        </Button>
        <span>{Math.round(zoom * 100)}%</span>
        <Button variant="outline" onClick={() => setZoom(Math.min(6, zoom + 0.25))}>
          +
        </Button>
        <Button variant="ghost" onClick={() => setZoom(1)}>
          Fit sheet
        </Button>
        <label>
          <input type="checkbox" checked={qa} onChange={(e) => setQa(e.target.checked)} /> QA
          overlay
        </label>
        <label>
          <input
            type="checkbox"
            checked={project.settings.showSchedules}
            onChange={(e) => {
              setIndex(0);
              update({ settings: { ...project.settings, showSchedules: e.target.checked } });
            }}
          />{' '}
          Show schedules
        </label>
        <label>
          <input
            type="checkbox"
            checked={wireTags}
            onChange={(e) => setWireTags(e.target.checked)}
          />{' '}
          Wire labels
        </label>
        <label>
          <input type="checkbox" checked={dmx} onChange={(e) => setDmx(e.target.checked)} /> DMX
          labels
        </label>
        <Button variant="outline" onClick={() => setGallery(!showGallery)}>
          {showGallery ? 'Project drawing' : 'Symbol gallery'}
        </Button>
        <Button
          variant="outline"
          disabled={!Object.keys(project.layoutOverrides).length}
          onClick={() => update({ layoutOverrides: {} })}
        >
          Reset all pins
        </Button>
      </div>
      <div className="action-bar">
        <label>
          Power flow{' '}
          <select
            value={project.settings.sheet.flow}
            onChange={(e) =>
              update({
                settings: {
                  ...project.settings,
                  sheet: { ...project.settings.sheet, flow: e.target.value as 'LR' | 'TB' },
                },
              })
            }
          >
            <option value="LR">Left to right</option>
            <option value="TB">Top to bottom</option>
          </select>
        </label>
        <span role="status">
          {busy
            ? 'Laying out…'
            : error
              ? 'Layout needs attention'
              : `${drawing?.sheets.length ?? 0} sheets · ${Math.round(drawing?.elapsedMs ?? 0)} ms`}
        </span>
        <span className="editor-help">
          Drag a device to pin it. Drag blank paper to pan. Undo restores layout edits.
        </span>
      </div>
      {error && (
        <div className="inline-error" role="alert">
          {error}
          <Button variant="outline" onClick={retry}>
            Retry layout
          </Button>
        </div>
      )}
      {!showGallery && (
        <div className="sheet-tabs" role="tablist" aria-label="Drawing sheets">
          {drawing?.sheets.map((s, i) => (
            <button role="tab" aria-selected={index === i} key={s.id} onClick={() => setIndex(i)}>
              {s.number} · {s.title}
            </button>
          ))}
        </div>
      )}
      <div className="drawing-viewport" ref={viewport}>
        <div
          className="drawing-paper"
          style={{ width: `${zoom * 100}%` }}
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={() => {
            setDrag(null);
            pan.current = null;
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
      {!!drawing?.warnings.length && (
        <details className="panel layout-warnings">
          <summary>{drawing.warnings.length} layout notes</summary>
          <ul>
            {drawing.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
