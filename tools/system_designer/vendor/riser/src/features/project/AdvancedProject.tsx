import { useState } from 'react';
import { Button } from '../../components/ui/button';
import { useProjectStore } from '../../state/project-store';
import { ProjectSettingsSchema, type ProjectSettings } from '../../schemas/project';
import { AWG_SMALL_TO_LARGE } from '../../schemas/common';
import { parseProjectFile, saveProjectFile } from '../../storage/project-file';

const help: Record<Exclude<keyof ProjectSettings, 'sheet' | 'showSchedules'>, string> = {
  necEdition:
    'Select the adopted code edition. Missing reference data produces errors; editions are never silently substituted.',
  terminationTempC:
    'Use the lowest applicable equipment-terminal, conductor and wiring-method temperature limit.',
  vdTargetLineVoltagePct: 'Line-voltage cable voltage-drop target in percent.',
  vdTargetLowVoltagePct: 'DC feed cable voltage-drop target in percent.',
  vdTargetLandscapePct: 'Landscape AC cable voltage-drop target in percent.',
  vdMethod:
    'Lumped puts all load at the cable end. Distributed sums feeder and inter-fixture segment drops.',
  acVdMethod:
    'Effective-Z requires populated Table 9 values at PF 0.85. Missing data never falls back to DC resistance.',
  psuDeratePct: 'Operating-load warning target, separate from rated output capacity.',
  continuousLoadFactor: 'Multiplier for continuous-current and conductor checks.',
  breakerLoadLimitPct: 'Operating-current warning threshold as percent of breaker rating.',
  tapeLengthMarginPct:
    'Extra tape length used for power and material allowance, expressed in percent.',
  minAwgLineVoltage: 'Smallest allowed line-voltage conductor before other checks.',
  dmxMaxUnitLoads: 'Maximum RS-485 unit loads per physical wired segment.',
  dmxMaxLengthFt: 'Maximum total wired DMX segment length in feet.',
  spiMaxDataFt: 'Maximum single-ended SPI link length before a differential link is recommended.',
  drawingFont:
    'Arimo matches Arial metrics. Roboto Condensed is the optional narrow face; its TTF files accompany the DXF ZIP.',
  units: 'Preferred length display. Project JSON length fields remain canonical feet.',
  wireWastePct: 'Cable procurement allowance in percent; does not increase voltage-drop length.',
  dmxAutoPatchRoundTo:
    'Start addresses on 1 + multiples of this increment. Existing manual addresses are reserved.',
  wireLabelTemplate:
    'Available fields: {tag}, {wireLabel}, {lengthFt}, {vdPct}. Printed labels use engine results.',
  parallelConductorPolicy:
    'Parallel cable or common-conductor overrides always require installation and termination review.',
};
const choices: Partial<Record<keyof ProjectSettings, string[]>> = {
  necEdition: ['2020', '2023', '2026'],
  terminationTempC: ['60', '75', '90'],
  vdMethod: ['lumped-at-end', 'distributed'],
  acVdMethod: ['dc-resistance', 'effective-z'],
  minAwgLineVoltage: [...AWG_SMALL_TO_LARGE],
  units: ['ft', 'm'],
  drawingFont: ['Arimo', 'RobotoCondensed'],
  parallelConductorPolicy: ['manual-review-required'],
};
export function AdvancedProject() {
  const project = useProjectStore((s) => s.draft);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const update = useProjectStore((s) => s.updateProject);
  function setting(key: keyof ProjectSettings, raw: string) {
    try {
      const previous = project.settings[key];
      const value = typeof previous === 'number' ? Number(raw) : raw;
      update({ settings: ProjectSettingsSchema.parse({ ...project.settings, [key]: value }) });
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid setting');
    }
  }
  return (
    <div className="advanced-project">
      <section className="panel library-panel">
        <div className="library-panel-top">
          <h2>Project files</h2>
          <span className="data-badge">Local files</span>
        </div>
        <div className="action-bar">
          <Button
            onClick={() =>
              void saveProjectFile(project)
                .then((saved) => {
                  if (saved) setMessage('Project file saved.');
                })
                .catch((e) => setError(String(e)))
            }
          >
            Save .riser.json
          </Button>
          <label className="file-button">
            Open project file
            <input
              aria-label="Open project file"
              type="file"
              accept=".json,.riser.json"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f)
                  void f.text().then((s) => {
                    try {
                      const imported = parseProjectFile(s);
                      update(imported);
                      setMessage(
                        'Project file opened. Undo restores the previous project content.',
                      );
                      setError('');
                    } catch (err) {
                      setError(String(err));
                    }
                  });
                e.target.value = '';
              }}
            />
          </label>
        </div>
        <p className="editor-help">
          Library items are referenced by stable ID. Save a library JSON backup from Libraries when
          moving projects to another browser or device.
        </p>
        {message && (
          <p className="inline-success" role="status">
            {message}
          </p>
        )}
      </section>
      <section className="panel library-panel">
        <h2>Engineering settings</h2>
        <div className="settings-grid">
          {Object.entries(help).map(([name, description]) => {
            const key = name as Exclude<keyof ProjectSettings, 'sheet' | 'showSchedules'>;
            const value = project.settings[key];
            return (
              <label key={`${key}:${value}`}>
                <strong>{key.replace(/([A-Z])/g, ' $1')}</strong>
                {choices[key] ? (
                  <select
                    aria-label={key}
                    defaultValue={String(value)}
                    onChange={(e) => setting(key, e.target.value)}
                  >
                    {choices[key]!.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    aria-label={key}
                    type={typeof value === 'number' ? 'number' : 'text'}
                    step="any"
                    defaultValue={String(value)}
                    onBlur={(e) => setting(key, e.target.value)}
                  />
                )}
                <small>{description}</small>
              </label>
            );
          })}
        </div>
        {error && (
          <pre className="inline-error" role="alert">
            {error}
          </pre>
        )}
      </section>
      <section className="panel library-panel">
        <div className="library-panel-top">
          <h2>General notes</h2>
          <Button
            variant="outline"
            onClick={() => update({ generalNotes: [...project.generalNotes, 'New note'] })}
          >
            Add note
          </Button>
        </div>
        <div className="editable-notes">
          {project.generalNotes.map((note, i) => (
            <div key={i}>
              <span>{i + 1}</span>
              <textarea
                aria-label={`General note ${i + 1}`}
                value={note}
                onChange={(e) =>
                  update({
                    generalNotes: project.generalNotes.map((n, j) =>
                      i === j ? e.target.value : n,
                    ),
                  })
                }
              />
              <Button
                variant="ghost"
                onClick={() =>
                  update({ generalNotes: project.generalNotes.filter((_, j) => j !== i) })
                }
              >
                Remove
              </Button>
            </div>
          ))}
        </div>
      </section>
      <section className="panel library-panel">
        <div className="library-panel-top">
          <h2>Key notes</h2>
          <Button
            variant="outline"
            onClick={() => {
              let n = 1;
              while (project.keyNotes.some((k) => k.id === `K-${n}`)) n++;
              update({ keyNotes: [...project.keyNotes, { id: `K-${n}`, text: 'New key note' }] });
            }}
          >
            Add key note
          </Button>
        </div>
        {project.keyNotes.map((note, i) => (
          <div className="action-bar" key={note.id}>
            <input
              aria-label={`Key note ${i + 1} ID`}
              defaultValue={note.id}
              onBlur={(e) => {
                try {
                  update({
                    keyNotes: project.keyNotes.map((n, j) =>
                      i === j ? { ...n, id: e.target.value } : n,
                    ),
                  });
                } catch (err) {
                  setError(String(err));
                }
              }}
            />
            <input
              aria-label={`Key note ${i + 1} text`}
              value={note.text}
              onChange={(e) =>
                update({
                  keyNotes: project.keyNotes.map((n, j) =>
                    i === j ? { ...n, text: e.target.value } : n,
                  ),
                })
              }
            />
            <Button
              variant="ghost"
              onClick={() => update({ keyNotes: project.keyNotes.filter((_, j) => j !== i) })}
            >
              Remove
            </Button>
          </div>
        ))}
      </section>
      <section className="panel library-panel">
        <div className="library-panel-top">
          <h2>Revision history</h2>
          <Button
            variant="outline"
            onClick={() =>
              update({
                revisions: [
                  ...project.revisions,
                  {
                    rev: String(project.revisions.length + 1),
                    date: project.meta.date,
                    description: 'Revision',
                    by: project.meta.designer,
                  },
                ],
              })
            }
          >
            Add revision
          </Button>
        </div>
        <div className="wide-table">
          <table>
            <thead>
              <tr>
                <th>Rev</th>
                <th>Date</th>
                <th>Description</th>
                <th>By</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {project.revisions.map((r, i) => (
                <tr key={i}>
                  {(['rev', 'date', 'description', 'by'] as const).map((k) => (
                    <td key={k}>
                      <input
                        aria-label={`Revision ${i + 1} ${k}`}
                        type={k === 'date' ? 'date' : 'text'}
                        defaultValue={r[k]}
                        onBlur={(e) => {
                          try {
                            update({
                              revisions: project.revisions.map((old, j) =>
                                j === i ? { ...old, [k]: e.target.value } : old,
                              ),
                            });
                          } catch (err) {
                            setError(String(err));
                          }
                        }}
                      />
                    </td>
                  ))}
                  <td>
                    <Button
                      variant="ghost"
                      onClick={() =>
                        update({ revisions: project.revisions.filter((_, j) => j !== i) })
                      }
                    >
                      Remove
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
