import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from 'zustand';
import type { Project } from '@ill/core-schemas/project';
import type { Drawing } from '@ill/drawing/model';
import {
  CLIENT_SECTIONS,
  RISER_SECTIONS,
  type DrawingOptions,
  type DrawingStyle,
  type DrawingView,
} from '@ill/drawing/options';
import {
  allowedStamps,
  DEFAULT_STAMP,
  RISER_SHEETS,
  riserProject,
  type RiserLayout,
  type RiserSheet,
  type RiserStamp,
} from '@ill/engine/riser';
import type { FontBytes } from '@ill/serializers/pdf/fonts';
import { track, type CommentAnchor, type Deliverable, type DeliverableKind, type DesignApi } from '../design/api';
import { clientOptions } from '../design/client';
import type { CheckState } from '../design/engine';
import { createDrawingRunner, logoDataUrl, sha256Hex, type DrawingInput } from '../design/drawing';
import type { DesignStore } from '../design/store';
import { loadFontBytes } from '../lib/fonts';
import { CommentThread, pinAt, SheetPins, useComments } from './Comments';
import { FeedbackPrompt } from './FeedbackPrompt';
import type { OpenDesign } from './open';

type Format = { kind: DeliverableKind; label: string; extension: string; mime: string };

/** Export formats on the Views step, per drawing style; each is generated in the browser (plan §12.1). */
const FORMATS: Record<DrawingStyle, Format[]> = {
  riser: [
    { kind: 'Riser PDF', label: 'PDF', extension: 'pdf', mime: 'application/pdf' },
    { kind: 'Riser DXF ZIP', label: 'DXF (ZIP)', extension: 'zip', mime: 'application/zip' },
    { kind: 'Riser SVG', label: 'SVG (this sheet)', extension: 'svg', mime: 'image/svg+xml' },
  ],
  // The client diagram is for a homeowner: no CAD file.
  client: [
    { kind: 'Presentation PDF', label: 'PDF', extension: 'pdf', mime: 'application/pdf' },
    { kind: 'Presentation SVG', label: 'SVG (this sheet)', extension: 'svg', mime: 'image/svg+xml' },
  ],
};

const STYLES: { style: DrawingStyle; label: string; noun: string }[] = [
  { style: 'riser', label: 'Riser diagram (installer)', noun: 'riser' },
  { style: 'client', label: 'Client diagram (homeowner)', noun: 'client diagram' },
];

/** What a dealer chose to show on one drawing style; carried over from the standalone riser. */
export interface ViewChoice {
  layout: RiserLayout;
  view: DrawingView;
}

const NO_CHOICE: ViewChoice = { layout: {}, view: {} };
const VIEWS_KEY = 'ill-sd:views';

/** The dealer's last choices, kept in this browser; nothing breaks when storage is unavailable. */
function loadViews(): Record<DrawingStyle, ViewChoice> {
  const fresh = { riser: NO_CHOICE, client: NO_CHOICE };
  try {
    const saved = JSON.parse(localStorage.getItem(VIEWS_KEY) ?? 'null') as Partial<
      Record<DrawingStyle, Partial<ViewChoice>>
    > | null;
    if (!saved || typeof saved !== 'object') return fresh;
    const read = (choice?: Partial<ViewChoice>): ViewChoice => ({
      layout: choice?.layout && typeof choice.layout === 'object' ? choice.layout : {},
      view: choice?.view && typeof choice.view === 'object' ? choice.view : {},
    });
    return { riser: read(saved.riser), client: read(saved.client) };
  } catch {
    return fresh;
  }
}

function saveViews(views: Record<DrawingStyle, ViewChoice>) {
  try {
    localStorage.setItem(VIEWS_KEY, JSON.stringify(views));
  } catch {
    // Private windows and blocked storage only lose the remembered choice.
  }
}

/** Card details a dealer can hide, per style: the client card names protocols, not DMX addresses. */
const DETAILS: Record<DrawingStyle, { key: Exclude<keyof DrawingView, 'hide'>; label: string }[]> = {
  riser: [
    { key: 'wireLabels', label: 'Wire labels' },
    { key: 'dmx', label: 'DMX addresses' },
    { key: 'ratings', label: 'Volts, watts and loading' },
    { key: 'models', label: 'Model numbers' },
    { key: 'lengths', label: 'Tape lengths and locations' },
  ],
  client: [
    { key: 'wireLabels', label: 'Wire labels' },
    { key: 'dmx', label: 'Control protocols' },
    { key: 'ratings', label: 'Voltages' },
    { key: 'models', label: 'Part numbers' },
    { key: 'lengths', label: 'Tape lengths and locations' },
  ],
};

const SECTION_LABELS: Record<string, string> = {
  'EQUIPMENT SCHEDULE': 'Equipment schedule',
  'LOAD SCHEDULE': 'Load schedule',
  'WIRE SCHEDULE': 'Wire schedule',
  'CONTINUATION INDEX': 'Continuation index',
  'LOADING / CAPACITY': 'Loading and capacity',
  'DMX PATCH': 'DMX patch',
  'BILL OF MATERIALS': 'Bill of materials',
  'GENERAL NOTES': 'General notes',
  'KEY NOTES': 'Key notes',
  REVISIONS: 'Revisions',
  'PROJECT RECORD': 'Project record',
  'SYMBOL LEGEND': 'Symbol legend',
  'LINE LEGEND': 'Line legend',
  'COLOR KEY': 'Color key',
  'FIXTURE SCHEDULE': 'Fixture schedule',
  'POWER SUPPLIES AND CONTROLS': 'Power supplies and controls',
  WIRE: 'Wire',
  NOTES: 'Notes',
};
const SECTIONS: Record<DrawingStyle, readonly string[]> = { riser: RISER_SECTIONS, client: CLIENT_SECTIONS };

/** The drawing options a choice makes: the client page leaves every section off when it is turned off. */
function viewFor(style: DrawingStyle, choice: ViewChoice): DrawingView {
  if (style === 'client' && choice.layout.schedules === false) return { ...choice.view, hide: [...CLIENT_SECTIONS] };
  return choice.view;
}

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
  const [style, setStyle] = useState<DrawingStyle>('riser');
  const [views, setViews] = useState(loadViews);
  const [flags, setFlags] = useState(false);
  const [drawn, setDrawn] = useState<{
    drawing: Drawing;
    project: Project;
    style: DrawingStyle;
    view: string;
    design: unknown;
  } | null>(null);
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
      // The client diagram's schedule page is a section list, not the riser's schedules setting.
      layout: { ...views[style].layout, ...(style === 'client' ? { schedules: undefined, units: undefined } : {}) },
    });
  }, [ready, engine, block, open, meta, stamp, sheet, approved, views, style]);
  const choice = views[style];
  const view = viewFor(style, choice);
  const viewKey = JSON.stringify(view);
  // A drawing made for another design, sheet, stamp, style or view is not what the buttons would export.
  const drawing =
    drawn && drawn.project === project && drawn.style === style && drawn.view === viewKey ? drawn.drawing : null;
  const noun = STYLES.find((item) => item.style === style)!.noun;
  const commentView = style === 'client' ? 'Presentation' : 'Riser';
  const current = drawing?.sheets[page];
  const [preview, setPreview] = useState<{ sheet: unknown; url: string; flags: boolean } | null>(null);
  useEffect(() => {
    if (!current || typeof URL.createObjectURL !== 'function') return;
    let url: string | null = null;
    let cancelled = false;
    void import('@ill/serializers/svg').then(({ serializeSvg }) => {
      if (cancelled) return;
      // Check flags are a preview aid, as in the standalone riser: exports never carry them.
      url = URL.createObjectURL(new Blob([serializeSvg(current, { qa: flags })], { type: 'image/svg+xml' }));
      setPreview({ sheet: current, url, flags });
    });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [current, flags]);
  const previewUrl = preview && current && preview.sheet === current && preview.flags === flags ? preview.url : null;
  // Once a drawing is up, a changed sheet, stamp or view redraws it; a changed design still waits for Draw again.
  const redraw = useRef<() => Promise<void>>(async () => undefined);
  useEffect(() => {
    redraw.current = draw;
  });
  const stale = Boolean(drawn && !drawing && drawn.style === style && drawn.design === design && project);
  useEffect(() => {
    if (stale && !busy && !error) void redraw.current();
  }, [stale, busy, error, project, viewKey]);

  if (!design) return null;
  const incomplete =
    engine.state === 'ready' && engine.check.result.messages.some((item) => item.code === 'INCOMPLETE_SPEC');
  // Applications Engineers keep the riser they review on the design, too (WP-4.3).
  const canStore = Boolean(meta?.name) && !dirty && (open.permissions.can_edit || open.permissions.can_review);
  const canComment = Boolean(meta?.name) && (open.permissions.can_edit || open.permissions.can_review);
  const shownSheet = drawing?.sheets[page]?.number ?? '';
  const base = `ilLumenate-System-Designer_${safe(open.schedule.name)}_rev${meta?.revision ?? 'draft'}${style === 'client' ? '_Client' : ''}_${safe(sheetLabel(sheet))}`;

  async function draw() {
    if (!project || engine.state !== 'ready') return;
    setBusy(`Drawing the ${noun}…`);
    setError('');
    setNotice('');
    try {
      const logo = block?.dealer_logo ? await deps.logo(block.dealer_logo) : null;
      const options: DrawingOptions = {
        ...(logo ? { dealerLogo: logo } : {}),
        ...(style === 'client' ? clientOptions(open.lines, open.builds, design!, project) : {}),
        view,
      };
      const made = await deps.draw({ project, library: engine.check.library, result: engine.check.result, options });
      setDrawn({ drawing: made, project, style, view: viewKey, design });
      setPage(0);
      if (block?.dealer_logo && !logo) setNotice(`Your logo could not be read, so the ${noun} shows only ours.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : `The ${noun} could not be drawn`);
    } finally {
      setBusy('');
    }
  }


  function choose(change: (current: ViewChoice) => ViewChoice) {
    setViews((all) => {
      const next = { ...all, [style]: change(all[style]) };
      saveViews(next);
      return next;
    });
    setError('');
  }
  const shown = (key: Exclude<keyof DrawingView, 'hide'>) => choice.view[key] !== false;
  const sectionShown = (title: string) => !choice.view.hide?.includes(title);
  const settings = engine.state === 'ready' ? engine.check.project.settings : null;
  const schedulesOn = choice.layout.schedules ?? (style === 'client' || (settings?.showSchedules ?? true));

  async function exportAs(format: Format) {
    if (!drawing || !project) return;
    setBusy(`Preparing the ${format.label}…`);
    setError('');
    setNotice('');
    try {
      const { DESIGNER_CREATOR } = await import('@ill/serializers/pdf/pdf');
      let bytes: Uint8Array;
      let filename = `${base}.${format.extension}`;
      if (format.extension === 'pdf') {
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
          details: { kind: format.kind, sheet: sheetLabel(sheet), style, stored: false },
        });
        setNotice(
          open.permissions.can_edit ? 'Downloaded. Save the design to keep its drawings on it.' : 'Downloaded.',
        );
        return;
      }
      const variant =
        format.extension === 'svg' ? `${sheetLabel(sheet)} ${drawing.sheets[page]!.number}` : sheetLabel(sheet);
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
        Draw the riser for this design, then download it. Drawings of a saved design are kept on its revision. The
        client diagram is a simpler, colour-coded version with your fixture schedule, to hand to a homeowner.
      </p>
      <div className="ill-sd__card" data-testid="riser-options">
        <h3>Drawing</h3>
        <div className="ill-sd__row">
          <label className="ill-sd__pick">
            <span>Style</span>
            <select
              value={style}
              onChange={(event) => {
                setStyle(event.target.value as DrawingStyle);
                setPin(null);
              }}
            >
              {STYLES.map((item) => (
                <option key={item.style} value={item.style}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
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
            {drawing ? 'Draw again' : style === 'client' ? 'Draw client diagram' : 'Draw riser'}
          </button>
        </div>
        {!approved ? (
          <p className="ill-sd__muted">REVIEWED BY ILLUMENATE is available once ilLumenate approves this revision.</p>
        ) : null}
        {incomplete ? (
          <p className="ill-sd__error" role="alert">
            Some products need specifications before the {noun} can be drawn. Open the Check step to see which.
          </p>
        ) : !ready ? (
          <p className="ill-sd__muted" role="status">
            {engine.state === 'error' ? engine.message : 'Running the checks…'}
          </p>
        ) : null}
      </div>
      <div className="ill-sd__card" data-testid="view-options">
        <h3>Show on the {noun}</h3>
        <div className="ill-sd__row">
          <label className="ill-sd__pick">
            <span>Power flow</span>
            <select
              value={choice.layout.flow ?? settings?.sheet.flow ?? 'LR'}
              onChange={(event) =>
                choose((c) => ({ ...c, layout: { ...c.layout, flow: event.target.value as 'LR' | 'TB' } }))
              }
            >
              <option value="LR">Left to right</option>
              <option value="TB">Top to bottom</option>
            </select>
          </label>
          {style === 'riser' ? (
            <label className="ill-sd__pick">
              <span>Units</span>
              <select
                value={choice.layout.units ?? settings?.units ?? 'ft'}
                onChange={(event) =>
                  choose((c) => ({ ...c, layout: { ...c.layout, units: event.target.value as 'ft' | 'm' } }))
                }
              >
                <option value="ft">Feet</option>
                <option value="m">Metres</option>
              </select>
            </label>
          ) : null}
          <label className="ill-sd__pick">
            <span>Font</span>
            <select
              value={choice.layout.font ?? settings?.drawingFont ?? 'Arimo'}
              onChange={(event) =>
                choose((c) => ({
                  ...c,
                  layout: { ...c.layout, font: event.target.value as 'Arimo' | 'RobotoCondensed' },
                }))
              }
            >
              <option value="Arimo">Arimo (Arial widths)</option>
              <option value="RobotoCondensed">Roboto Condensed (narrow)</option>
            </select>
          </label>
        </div>
        <fieldset className="ill-sd__fieldset ill-sd__toggles">
          <legend>On the diagram</legend>
          {DETAILS[style].map((item) => (
            <label key={item.key}>
              <input
                type="checkbox"
                checked={shown(item.key)}
                onChange={(event) =>
                  choose((c) => ({ ...c, view: { ...c.view, [item.key]: event.target.checked } }))
                }
              />
              <span>{item.label}</span>
            </label>
          ))}
          <label>
            <input type="checkbox" checked={flags} onChange={(event) => setFlags(event.target.checked)} />
            <span>Check flags (preview only)</span>
          </label>
        </fieldset>
        <fieldset className="ill-sd__fieldset ill-sd__toggles">
          <legend>
            <label>
              <input
                type="checkbox"
                checked={schedulesOn}
                onChange={(event) =>
                  choose((c) => ({ ...c, layout: { ...c.layout, schedules: event.target.checked } }))
                }
              />
              <span>{style === 'client' ? 'Fixture schedule page' : 'Schedules, legends and notes'}</span>
            </label>
          </legend>
          {schedulesOn
            ? SECTIONS[style].map((title) => (
                <label key={title}>
                  <input
                    type="checkbox"
                    checked={sectionShown(title)}
                    onChange={(event) =>
                      choose((c) => {
                        const hide = (c.view.hide ?? []).filter((item) => item !== title);
                        return { ...c, view: { ...c.view, hide: event.target.checked ? hide : [...hide, title] } };
                      })
                    }
                  />
                  <span>{SECTION_LABELS[title] ?? title}</span>
                </label>
              ))
            : null}
        </fieldset>
        <p className="ill-sd__muted">
          {style === 'riser' && !schedulesOn
            ? 'Without schedules the diagrams use the whole sheet. '
            : ''}
          Downloads match the preview.
        </p>
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
            {FORMATS[style].map((format) => (
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
              <img
                className="ill-sd__riser"
                src={previewUrl}
                alt={`${style === 'client' ? 'Client diagram' : 'Riser'} sheet ${shownSheet}`}
              />
              <SheetPins comments={comments.comments} view={commentView} sheet={shownSheet} pending={pin} />
            </div>
          ) : null}
        </div>
      ) : null}
      {meta?.name ? (
        <CommentThread
          comments={comments}
          view={commentView}
          canComment={canComment}
          anchor={pin}
          onClearAnchor={() => setPin(null)}
          title={`Comments on the ${noun}`}
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
