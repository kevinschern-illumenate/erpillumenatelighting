import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from 'zustand';
import type { Project } from '@ill/core-schemas/project';
import type { Drawing } from '@ill/drawing/model';
import type { DrawingOptions } from '@ill/drawing/options';
import {
  allowedStamps,
  DEFAULT_STAMP,
  RISER_SHEETS,
  riserProject,
  type RiserSheet,
  type RiserStamp,
} from '@ill/engine/riser';
import type { FontBytes } from '@ill/serializers/pdf/fonts';
import { track, type CommentAnchor, type Deliverable, type DeliverableKind, type DesignApi } from '../design/api';
import type { CheckState } from '../design/engine';
import { createDrawingRunner, logoDataUrl, sha256Hex, type DrawingInput } from '../design/drawing';
import type { DesignStore } from '../design/store';
import { loadFontBytes } from '../lib/fonts';
import { CommentThread, pinAt, SheetPins, useComments } from './Comments';
import { FeedbackPrompt } from './FeedbackPrompt';
import type { OpenDesign } from './open';

/** Export formats on the Views step; each is generated in the browser (plan §12.1). */
const FORMATS: { kind: DeliverableKind; label: string; extension: string; mime: string }[] = [
  { kind: 'Riser PDF', label: 'PDF', extension: 'pdf', mime: 'application/pdf' },
  { kind: 'Riser DXF ZIP', label: 'DXF (ZIP)', extension: 'zip', mime: 'application/zip' },
  { kind: 'Riser SVG', label: 'SVG (this sheet)', extension: 'svg', mime: 'image/svg+xml' },
];

export interface ViewsDeps {
  draw(input: DrawingInput): Promise<Drawing>;
  fonts(family: 'Arimo' | 'RobotoCondensed'): Promise<FontBytes>;
  logo(url: string): Promise<DrawingOptions['dealerLogo'] | null>;
  /** Hand a file to the browser's download. */
  save(blob: Blob, filename: string): void;
}

function browserSave(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const today = () => new Date().toISOString().slice(0, 10);
const safe = (value: string) => value.replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '');
const sheetLabel = (size: RiserSheet) => RISER_SHEETS.find((item) => item.size === size)!.label.split(' (')[0]!;

/** The Views step (WP-3.7): the riser drawn from this design, exported as PDF, DXF or SVG and kept on it. */
export function ViewsStep({
  open,
  store,
  engine,
  api,
  deps: injected,
}: {
  open: OpenDesign;
  store: DesignStore;
  engine: CheckState;
  api: DesignApi;
  deps?: Partial<ViewsDeps>;
}) {
  const design = useStore(store, (s) => s.design);
  const meta = useStore(store, (s) => s.meta);
  const dirty = useStore(store, (s) => s.dirty);
  const approved = meta?.status === 'Approved';
  const [sheet, setSheet] = useState<RiserSheet>('ANSI_B');
  const [stamp, setStamp] = useState<RiserStamp>(DEFAULT_STAMP);
  const [drawn, setDrawn] = useState<{ drawing: Drawing; project: Project } | null>(null);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [stored, setStored] = useState<Deliverable[]>(open.deliverables);
  const [exported, setExported] = useState(false);
  const [pinning, setPinning] = useState(false);
  const [pin, setPin] = useState<CommentAnchor | null>(null);
  const comments = useComments(api, meta?.name);
  const runner = useRef<ReturnType<typeof createDrawingRunner> | null>(null);
  const deps = useMemo<ViewsDeps>(
    () => ({
      draw: (input) => (runner.current ??= createDrawingRunner()).run(input),
      fonts: loadFontBytes,
      logo: logoDataUrl,
      save: browserSave,
      ...injected,
    }),
    [injected],
  );
  useEffect(() => () => runner.current?.close(), []);

  const ready = engine.state === 'ready' && engine.design === design;
  const block = open.title_block;
  const project = useMemo(() => {
    if (!ready || engine.state !== 'ready') return null;
    return riserProject(engine.check, {
      projectName: block?.project_name || open.schedule.schedule_name || open.schedule.name,
      projectNumber: block?.project_number || open.schedule.project || '',
      client: block?.customer ?? '',
      siteAddress: block?.site_address ?? '',
      designer: open.user ?? '',
      checker: meta?.approved_by ?? '',
      date: today(),
      revision: meta?.revision ?? '—',
      stamp,
      sheet,
      approved,
    });
  }, [ready, engine, block, open, meta, stamp, sheet, approved]);
  // A drawing made for another design, sheet or stamp is not what the buttons would export.
  const drawing = drawn && drawn.project === project ? drawn.drawing : null;
  const current = drawing?.sheets[page];
  const [preview, setPreview] = useState<{ sheet: unknown; url: string } | null>(null);
  useEffect(() => {
    if (!current || typeof URL.createObjectURL !== 'function') return;
    let url: string | null = null;
    let cancelled = false;
    void import('@ill/serializers/svg').then(({ serializeSvg }) => {
      if (cancelled) return;
      url = URL.createObjectURL(new Blob([serializeSvg(current)], { type: 'image/svg+xml' }));
      setPreview({ sheet: current, url });
    });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [current]);
  const previewUrl = preview && current && preview.sheet === current ? preview.url : null;

  if (!design) return null;
  const incomplete =
    engine.state === 'ready' && engine.check.result.messages.some((item) => item.code === 'INCOMPLETE_SPEC');
  // Applications Engineers keep the riser they review on the design, too (WP-4.3).
  const canStore = Boolean(meta?.name) && !dirty && (open.permissions.can_edit || open.permissions.can_review);
  const canComment = Boolean(meta?.name) && (open.permissions.can_edit || open.permissions.can_review);
  const shownSheet = drawing?.sheets[page]?.number ?? '';
  const base = `ilLumenate-System-Designer_${safe(open.schedule.name)}_rev${meta?.revision ?? 'draft'}_${safe(sheetLabel(sheet))}`;

  async function draw() {
    if (!project || engine.state !== 'ready') return;
    setBusy('Drawing the riser…');
    setError('');
    setNotice('');
    try {
      const logo = block?.dealer_logo ? await deps.logo(block.dealer_logo) : null;
      const options: DrawingOptions = logo ? { dealerLogo: logo } : {};
      const made = await deps.draw({ project, library: engine.check.library, result: engine.check.result, options });
      setDrawn({ drawing: made, project });
      setPage(0);
      if (block?.dealer_logo && !logo) setNotice('Your logo could not be read, so the riser shows only ours.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The riser could not be drawn');
    } finally {
      setBusy('');
    }
  }

  async function exportAs(format: (typeof FORMATS)[number]) {
    if (!drawing || !project) return;
    setBusy(`Preparing the ${format.label}…`);
    setError('');
    setNotice('');
    try {
      const { DESIGNER_CREATOR } = await import('@ill/serializers/pdf/pdf');
      let bytes: Uint8Array;
      let filename = `${base}.${format.extension}`;
      if (format.kind === 'Riser PDF') {
        const { serializePdf } = await import('@ill/serializers/pdf/pdf');
        bytes = await serializePdf(drawing, project, await deps.fonts(project.settings.drawingFont), {
          creator: DESIGNER_CREATOR,
          keywords: [
            `schedule:${open.schedule.name}`,
            ...(meta ? [`design:${meta.name}`, `revision:${meta.revision}`] : []),
          ],
        });
      } else if (format.kind === 'Riser DXF ZIP') {
        const { serializeDxfZip } = await import('@ill/serializers/dxf/dxf');
        const fonts = await deps.fonts(project.settings.drawingFont);
        bytes = await serializeDxfZip(
          drawing,
          { [`${fonts.name}-Regular.ttf`]: fonts.regular, [`${fonts.name}-Bold.ttf`]: fonts.bold },
          { creator: DESIGNER_CREATOR },
        );
      } else {
        const { serializeSvg } = await import('@ill/serializers/svg');
        const shown = drawing.sheets[page]!;
        filename = `${base}_${safe(shown.number)}.svg`;
        bytes = new TextEncoder().encode(serializeSvg(shown, { creator: DESIGNER_CREATOR }));
      }
      const blob = new Blob([bytes as BlobPart], { type: format.mime });
      deps.save(blob, filename);
      setExported(true);
      if (!canStore) {
        // A stored file is recorded by the server; a download alone is reported here (WP-3.9).
        track(api, {
          schedule: open.schedule.name,
          event: 'riser_exported',
          design: meta?.name,
          details: { kind: format.kind, sheet: sheetLabel(sheet), stored: false },
        });
        setNotice(
          open.permissions.can_edit ? 'Downloaded. Save the design to keep its drawings on it.' : 'Downloaded.',
        );
        return;
      }
      const variant =
        format.kind === 'Riser SVG' ? `${sheetLabel(sheet)} ${drawing.sheets[page]!.number}` : sheetLabel(sheet);
      const result = await api.uploadDeliverable({
        design: meta!.name,
        kind: format.kind,
        variant: variant.slice(0, 40),
        file: blob,
        filename,
        sha256: await sha256Hex(bytes),
      });
      setStored((rows) => [...rows.filter((row) => row.name !== result.row.name), result.row]);
      setNotice(`Downloaded and kept on revision ${meta!.revision}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The file could not be prepared');
    } finally {
      setBusy('');
    }
  }

  return (
    <section aria-labelledby="ill-sd-step-title" className="ill-sd__views-step">
      <h2 id="ill-sd-step-title">Views</h2>
      <p className="ill-sd__muted">
        Draw the riser for this design, then download it. Drawings of a saved design are kept on its revision.
      </p>
      <div className="ill-sd__card" data-testid="riser-options">
        <h3>Riser</h3>
        <div className="ill-sd__row">
          <label className="ill-sd__pick">
            <span>Sheet</span>
            <select value={sheet} onChange={(event) => setSheet(event.target.value as RiserSheet)}>
              {RISER_SHEETS.map((item) => (
                <option key={item.size} value={item.size}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="ill-sd__pick">
            <span>Stamp</span>
            <select value={stamp} onChange={(event) => setStamp(event.target.value as RiserStamp)}>
              {allowedStamps(approved).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ill-sd__button"
            disabled={!project || incomplete || Boolean(busy)}
            onClick={() => void draw()}
          >
            {drawing ? 'Draw again' : 'Draw riser'}
          </button>
        </div>
        {!approved ? (
          <p className="ill-sd__muted">REVIEWED BY ILLUMENATE is available once ilLumenate approves this revision.</p>
        ) : null}
        {incomplete ? (
          <p className="ill-sd__error" role="alert">
            Some products need specifications before the riser can be drawn. Open the Check step to see which.
          </p>
        ) : !ready ? (
          <p className="ill-sd__muted" role="status">
            {engine.state === 'error' ? engine.message : 'Running the checks…'}
          </p>
        ) : null}
      </div>
      {busy ? (
        <p className="ill-sd__muted" role="status">
          {busy}
        </p>
      ) : null}
      {error ? (
        <p className="ill-sd__error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="ill-sd__muted" role="status" data-testid="views-notice">
          {notice}
        </p>
      ) : null}
      {drawing ? (
        <div className="ill-sd__card" data-testid="riser-preview">
          <div className="ill-sd__row">
            <label className="ill-sd__pick">
              <span>
                Sheet {page + 1} of {drawing.sheets.length}
              </span>
              <select value={page} onChange={(event) => setPage(Number(event.target.value))}>
                {drawing.sheets.map((item, index) => (
                  <option key={item.id} value={index}>
                    {item.number} · {item.title}
                  </option>
                ))}
              </select>
            </label>
            {FORMATS.map((format) => (
              <button
                key={format.kind}
                type="button"
                className="ill-sd__button ill-sd__button--quiet"
                disabled={Boolean(busy)}
                onClick={() => void exportAs(format)}
              >
                Download {format.label}
              </button>
            ))}
          </div>
          {drawing.warnings.length ? (
            <ul className="ill-sd__muted">
              {drawing.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          {canComment ? (
            <label className="ill-sd__pick">
              <input type="checkbox" checked={pinning} onChange={(event) => setPinning(event.target.checked)} />
              <span>Pin a comment: click the drawing where it applies</span>
            </label>
          ) : null}
          {previewUrl ? (
            <div
              className={`ill-sd__riser-wrap${pinning ? ' ill-sd__riser-wrap--pinning' : ''}`}
              data-testid="riser-sheet"
              onClick={(event) => {
                if (pinning) setPin(pinAt(event, shownSheet));
              }}
            >
              <img className="ill-sd__riser" src={previewUrl} alt={`Riser sheet ${shownSheet}`} />
              <SheetPins comments={comments.comments} view="Riser" sheet={shownSheet} pending={pin} />
            </div>
          ) : null}
        </div>
      ) : null}
      {meta?.name ? (
        <CommentThread
          comments={comments}
          view="Riser"
          canComment={canComment}
          anchor={pin}
          onClearAnchor={() => setPin(null)}
          title="Comments on the riser"
        />
      ) : null}
      {exported ? (
        <FeedbackPrompt
          name={meta?.name ?? open.schedule.name}
          onSend={(rating, comment) =>
            track(api, {
              schedule: open.schedule.name,
              event: 'feedback',
              design: meta?.name,
              details: { rating, ...(comment ? { comment } : {}) },
            })
          }
        />
      ) : null}
      {stored.length ? (
        <div className="ill-sd__card" data-testid="deliverables">
          <h3>Kept on this design</h3>
          <ul>
            {stored.map((row) => (
              <li key={row.name}>
                <a href={row.file} target="_blank" rel="noreferrer">
                  {row.kind}
                  {row.variant ? ` · ${row.variant}` : ''}
                </a>{' '}
                <span className="ill-sd__muted">
                  revision {row.revision} · {row.created_on.slice(0, 16)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
