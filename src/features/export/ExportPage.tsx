import { useState } from 'react';
import { Link } from 'react-router-dom';
import Papa from 'papaparse';
import JSZip from 'jszip';
import { Button } from '../../components/ui/button';
import { useDrawing } from '../../hooks/use-drawing';
import { downloadFile, filename } from '../../lib/files';
import { serializeSvg } from '../../serializers/svg';
import { saveProjectFile } from '../../storage/project-file';
import { useProjectStore } from '../../state/project-store';

export function ExportPage() {
  const update = useProjectStore((s) => s.updateProject);
  const {
    project,
    library,
    result,
    drawing,
    current,
    busy,
    error: layoutError,
    retry,
  } = useDrawing();
  const [working, setWorking] = useState(''),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const errors = result.messages.filter((m) => m.severity === 'error').length;
  const name = filename(project.meta.number || project.meta.name);
  async function run(label: string, task: () => Promise<void>) {
    setWorking(label);
    setError('');
    setMessage('');
    try {
      await task();
      setMessage(`${label} downloaded.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    } finally {
      setWorking('');
    }
  }
  const ready = current && !!drawing && !working;
  return (
    <div className="export-workspace">
      <section className="panel library-panel">
        <div className="library-panel-top">
          <div>
            <h2>Drawing exports</h2>
            <p>
              {drawing?.sheets.length ?? 0} sheets · {project.settings.sheet.size.replace('_', ' ')}{' '}
              · {project.meta.stamp}
            </p>
          </div>
          <span className="data-badge">Vector geometry</span>
        </div>
        <p className="editor-help">
          PDF and DXF use the same paper geometry as Drawing. QA overlays are omitted. PDF text
          remains searchable; DXF devices carry extractable attributes. Each sheet includes a
          1.000-inch reference square.
        </p>
        {errors > 0 && (
          <p className="inline-error">
            Review contains {errors} engineering errors. These exports preserve the current design
            and issue stamp. <Link to="/review">Review errors</Link>
          </p>
        )}
        {busy && <p role="status">Preparing drawing sheets…</p>}
        <label>
          <input
            type="checkbox"
            checked={project.settings.showSchedules}
            onChange={(e) =>
              update({ settings: { ...project.settings, showSchedules: e.target.checked } })
            }
          />{' '}
          Include schedules, legends and notes on drawing sheets
        </label>
        {layoutError && (
          <p role="alert" className="inline-error">
            {layoutError}
            <Button onClick={retry}>Retry layout</Button>
          </p>
        )}
        <div className="export-cards">
          <article>
            <h3>Layered vector PDF</h3>
            <p>
              All sheets, full embedded {project.settings.drawingFont} fonts, monochrome lineweights
              and named PDF layers.
            </p>
            <Button
              disabled={!ready}
              onClick={() =>
                void run('PDF', async () => {
                  const [{ serializePdf }, { loadFontBytes }] = await Promise.all([
                    import('../../serializers/pdf/pdf'),
                    import('../../serializers/pdf/fonts'),
                  ]);
                  downloadFile(
                    `${name}.pdf`,
                    await serializePdf(
                      drawing!,
                      project,
                      await loadFontBytes(project.settings.drawingFont),
                    ),
                    'application/pdf',
                  );
                })
              }
            >
              Download PDF
            </Button>
          </article>
          <article>
            <h3>Native DXF</h3>
            <p>
              One file per sheet, inches, editable blocks and attributes. Default text references
              Arial; the condensed option includes its fonts in the ZIP.
            </p>
            <Button
              disabled={!ready}
              onClick={() =>
                void run('DXF ZIP', async () => {
                  const { serializeDxfZip } = await import('../../serializers/dxf/dxf');
                  const fontFiles: Record<string, Uint8Array | string> = {};
                  if (project.settings.drawingFont === 'RobotoCondensed') {
                    const { loadFontBytes } = await import('../../serializers/pdf/fonts');
                    const fonts = await loadFontBytes('RobotoCondensed');
                    fontFiles['RobotoCondensed-Regular.ttf'] = fonts.regular;
                    fontFiles['RobotoCondensed-Bold.ttf'] = fonts.bold;
                    const license = await fetch(
                      `${import.meta.env.BASE_URL}fonts/OFL-RobotoCondensed.txt`,
                    );
                    if (!license.ok) throw new Error('Font license could not be loaded.');
                    fontFiles['OFL-RobotoCondensed.txt'] = await license.text();
                  }
                  downloadFile(
                    `${name}-dxf.zip`,
                    await serializeDxfZip(drawing!, fontFiles),
                    'application/zip',
                  );
                })
              }
            >
              Download DXF ZIP
            </Button>
            <Button
              variant="outline"
              disabled={!ready}
              onClick={() =>
                void run('Tiled DXF', async () => {
                  const { serializeDxf } = await import('../../serializers/dxf/dxf');
                  downloadFile(
                    `${name}-tiled.dxf`,
                    serializeDxf(drawing!.sheets),
                    'application/dxf',
                  );
                })
              }
            >
              Download tiled DXF
            </Button>
          </article>
          <article>
            <h3>SVG sheets</h3>
            <p>Vector previews for review and publishing, one file per sheet in a ZIP.</p>
            <Button
              disabled={!ready}
              onClick={() =>
                void run('SVG ZIP', async () => {
                  const zip = new JSZip();
                  const { loadFontBytes } = await import('../../serializers/pdf/fonts');
                  const fonts = await loadFontBytes(project.settings.drawingFont);
                  const family =
                    project.settings.drawingFont === 'RobotoCondensed'
                      ? 'Roboto Condensed'
                      : 'Arimo';
                  const encode = (bytes: Uint8Array) =>
                    btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(''));
                  const fontCss = `@font-face{font-family:'${family}';font-weight:400;src:url(data:font/ttf;base64,${encode(fonts.regular)})}@font-face{font-family:'${family}';font-weight:700;src:url(data:font/ttf;base64,${encode(fonts.bold)})}`;
                  const licenseName = `OFL-${project.settings.drawingFont}.txt`;
                  const license = await fetch(`${import.meta.env.BASE_URL}fonts/${licenseName}`);
                  if (!license.ok) throw new Error('Font license could not be loaded.');
                  zip.file(licenseName, await license.text(), {
                    date: new Date('2000-01-01T00:00:00Z'),
                  });
                  for (const sheet of drawing!.sheets)
                    zip.file(
                      `${filename(sheet.number)}.svg`,
                      serializeSvg(sheet, { monochrome: true, fontCss }),
                      { date: new Date('2000-01-01T00:00:00Z') },
                    );
                  downloadFile(
                    `${name}-svg.zip`,
                    await zip.generateAsync({ type: 'uint8array' }),
                    'application/zip',
                  );
                })
              }
            >
              Download SVG ZIP
            </Button>
          </article>
        </div>
      </section>
      <section className="panel library-panel">
        <h2>Schedules and editable data</h2>
        <div className="action-bar">
          <Button
            disabled={!!working}
            onClick={() =>
              void run('CSV schedules', async () => {
                const zip = new JSZip();
                const csv = (file: string, rows: unknown[]) =>
                  zip.file(file, Papa.unparse(rows, { escapeFormulae: true }), {
                    date: new Date('2000-01-01T00:00:00Z'),
                  });
                csv(
                  'wire-schedule.csv',
                  result.runs.map((r) => ({
                    tag: r.tag,
                    runId: r.runId,
                    wire:
                      library.wires.find((w) => w.id === r.wireTypeId)?.riserLabel ??
                      'NO VALID WIRE',
                    from: r.from.tag,
                    fromPort: r.from.port,
                    to: r.to.tag,
                    toPort: r.to.port,
                    lengthFt: r.lengthFt,
                    currentA: r.currentA,
                    voltageV: r.voltageV,
                    vdV: r.vdV,
                    vdPct: r.vdPct,
                    endV: r.endV,
                    parallelSets: r.parallelSets,
                    commonConductors: r.parallelCommonConductors,
                    overridden: r.overridden,
                  })),
                );
                csv(
                  'equipment-schedule.csv',
                  project.equipment.map((e) => ({
                    tag: e.tag,
                    sku: library.products.find((p) => p.id === e.catalogId)?.sku ?? '',
                    qty: e.qty,
                    location: e.location,
                    enclosure: e.enclosure,
                    fedFrom: e.fedFrom.ref,
                    port: e.fedFrom.port,
                    feedLengthFt: e.feedLengthFt,
                  })),
                );
                csv(
                  'load-schedule.csv',
                  project.loads.map((l) => ({
                    id: l.id,
                    typeTag: l.typeTag,
                    zone: l.zone,
                    sku: library.products.find((p) => p.id === l.catalogId)?.sku ?? '',
                    qty: l.qty,
                    lengthFt: l.lengthFt,
                    wattsW: result.loadWatts[l.id],
                    fedFrom: l.fedFrom.ref,
                    port: l.fedFrom.port,
                    homeRunLengthFt: l.homeRunLengthFt,
                  })),
                );
                csv('loading.csv', result.loading);
                csv('dmx-patch.csv', result.patch);
                csv('bom.csv', result.bom);
                csv('issues.csv', result.messages);
                downloadFile(
                  `${name}-schedules.zip`,
                  await zip.generateAsync({ type: 'uint8array' }),
                  'application/zip',
                );
              })
            }
          >
            Download CSV schedules
          </Button>
          <Button
            variant="outline"
            onClick={() => void saveProjectFile(project).catch((e) => setError(String(e)))}
          >
            Save .riser.json
          </Button>
          <Button
            variant="outline"
            onClick={() => downloadFile(`${name}-library.json`, JSON.stringify(library, null, 2))}
          >
            Download library backup
          </Button>
        </div>
        <p className="editor-help">
          CSV and project JSON retain canonical feet. Save both the project and library when
          transferring a design to another computer.
        </p>
      </section>
      {working && <p role="status">Creating {working}…</p>}
      {message && (
        <p role="status" className="inline-success">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
    </div>
  );
}
