import { useState } from 'react';
import { useEngine } from '../../hooks/use-engine';
import { useProjectStore } from '../../state/project-store';
import { Button } from '../../components/ui/button';
import type { RunResult } from '../../engine/model';

const num = (v: number | null, digits = 2) => (v === null ? '—' : v.toFixed(digits));
export function ReviewPage() {
  const { project, library, result } = useEngine();
  const length = (ft: number | null) =>
    ft === null
      ? '—'
      : `${(project.settings.units === 'm' ? ft * 0.3048 : ft).toFixed(1)} ${project.settings.units}`;
  const [severity, setSeverity] = useState('all');
  const [tab, setTab] = useState('runs');
  function override(
    run: RunResult,
    patch: Partial<NonNullable<(typeof project.wireOverrides)[string]>>,
  ) {
    const wireTypeId = patch.wireTypeId ?? run.wireTypeId;
    const overrides = { ...project.wireOverrides };
    if (!wireTypeId) delete overrides[run.runId];
    else
      overrides[run.runId] = {
        wireTypeId,
        parallelSets: run.parallelSets,
        parallelCommonConductors: run.parallelCommonConductors,
        ...patch,
      };
    useProjectStore.getState().updateProject({ wireOverrides: overrides });
  }
  return (
    <div>
      <div className="library-stats">
        <div>
          <strong>{result.runs.length}</strong>
          <span>Derived runs</span>
        </div>
        <div>
          <strong>{result.messages.filter((m) => m.severity === 'error').length}</strong>
          <span>Errors</span>
        </div>
        <div>
          <strong>{result.messages.filter((m) => m.severity === 'warning').length}</strong>
          <span>Warnings</span>
        </div>
        <div>
          <strong>{result.bom.length}</strong>
          <span>BOM lines</span>
        </div>
      </div>
      <div className="library-tabs" role="tablist" aria-label="Engineering review">
        {[
          ['runs', 'Derived runs'],
          ['loading', 'Loading'],
          ['dmx', 'DMX patch'],
          ['issues', 'Issues'],
          ['bom', 'BOM'],
        ].map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            data-state={tab === value ? 'active' : 'inactive'}
            onClick={() => setTab(value!)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'runs' && (
        <section className="panel library-panel">
          <h2>Derived runs</h2>
          <p className="editor-help">
            One-way lengths, operating current and wire checks come from the calculation engine.
            Candidate maximum lengths use the conservative lumped method.
          </p>
          <div className="wide-table">
            <table>
              <thead>
                <tr>
                  {[
                    'Wire',
                    'Type / route',
                    'Length',
                    'A / V',
                    'Conductors',
                    'Selected wire',
                    'VD / end V',
                    'Ampacity / terminal',
                    'Override / parallel',
                    'Max length',
                  ].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.runs.map((r) => (
                  <tr key={r.runId}>
                    <td>
                      <strong>{r.tag}</strong>
                      {r.overridden && <small>overridden</small>}
                    </td>
                    <td>
                      {r.type}
                      <small>
                        {r.from.tag} {r.from.port} → {r.to.tag} {r.to.port}
                      </small>
                    </td>
                    <td>{length(r.lengthFt)}</td>
                    <td>
                      {num(r.currentA)} A<br />
                      {num(r.voltageV, 1)} V
                    </td>
                    <td>
                      {r.required.power} power, {r.required.channel} channel, {r.required.ground}{' '}
                      ground, {r.required.signal} signal, {r.required.dataPair} data
                    </td>
                    <td>
                      {library.wires.find((w) => w.id === r.wireTypeId)?.riserLabel ??
                        'No valid wire'}
                      {r.messages.map((m) => (
                        <small
                          key={m.code + m.text}
                          className={m.severity === 'error' ? 'error-text' : ''}
                          title={m.text}
                        >
                          {m.code}
                        </small>
                      ))}
                    </td>
                    <td>
                      {num(r.vdV)} V / {num(r.vdPct)}%<small>End {num(r.endV)} V</small>
                    </td>
                    <td>
                      {num(r.ampacityA)} A
                      <small>
                        Terminal:{' '}
                        {r.checks.terminal === null ? '—' : r.checks.terminal ? 'Pass' : 'Oversize'}
                      </small>
                    </td>
                    <td>
                      <select
                        aria-label={`${r.tag} wire override`}
                        value={project.wireOverrides[r.runId]?.wireTypeId ?? ''}
                        onChange={(e) => override(r, { wireTypeId: e.target.value })}
                      >
                        <option value="">Automatic</option>
                        {r.candidates.map((c) => (
                          <option key={c.wireTypeId} value={c.wireTypeId}>
                            {library.wires.find((w) => w.id === c.wireTypeId)?.riserLabel}
                            {c.eligible ? '' : ' · check limits'}
                          </option>
                        ))}
                      </select>
                      <label>
                        Sets
                        <input
                          type="number"
                          min={1}
                          max={20}
                          aria-label={`${r.tag} parallel sets`}
                          value={r.parallelSets}
                          onChange={(e) => {
                            const n = Number(e.target.value);
                            if (Number.isInteger(n) && n > 0 && n <= 20)
                              override(r, { parallelSets: n });
                          }}
                        />
                      </label>
                      {r.type === 'class2-dc-multichannel' && (
                        <label>
                          Common conductors
                          <input
                            type="number"
                            min={1}
                            max={10}
                            aria-label={`${r.tag} common conductors`}
                            value={r.parallelCommonConductors}
                            onChange={(e) => {
                              const n = Number(e.target.value);
                              if (Number.isInteger(n) && n > 0 && n <= 10)
                                override(r, { parallelCommonConductors: n });
                            }}
                          />
                        </label>
                      )}
                    </td>
                    <td>
                      <details>
                        <summary>By gauge</summary>
                        {r.candidates.map((c) => (
                          <p key={c.wireTypeId}>
                            #{c.awg ?? '—'}: {length(c.maxLengthFt)} ·{' '}
                            {c.reasons.join('; ') || 'Pass'}
                          </p>
                        ))}
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!result.runs.length && (
              <p className="empty-search">
                Enter equipment and loads in Tables to derive cable runs.
              </p>
            )}
          </div>
        </section>
      )}
      {tab === 'loading' && (
        <section className="panel library-panel">
          <h2>Loading by output, channel and circuit</h2>
          <div className="wide-table">
            <table>
              <thead>
                <tr>
                  {['Tag / port', 'Kind', 'Load', 'Current', 'Capacity', 'Loading'].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.loading.map((l) => (
                  <tr key={l.entityId + l.port}>
                    <td>
                      {l.tag} / {l.port}
                    </td>
                    <td>{l.kind}</td>
                    <td>{num(l.wattsW)} W</td>
                    <td>{num(l.currentA)} A</td>
                    <td>
                      {num(l.capacity)} {l.units}
                    </td>
                    <td>{num(l.percent, 1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {tab === 'dmx' && (
        <section className="panel library-panel">
          <div className="library-panel-top">
            <h2>DMX patch and physical segments</h2>
            <Button
              onClick={() =>
                useProjectStore.getState().updateProject({
                  equipment: project.equipment.map((e) => {
                    const p = result.patch.find((p) => p.entityId === e.id);
                    return e.dmx && p?.auto && p.startAddress !== null
                      ? { ...e, dmx: { ...e.dmx, startAddress: p.startAddress } }
                      : e;
                  }),
                })
              }
            >
              Auto-patch
            </Button>
          </div>
          <div className="wide-table">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Universe</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Footprint</th>
                </tr>
              </thead>
              <tbody>
                {result.patch.map((p) => (
                  <tr key={p.entityId}>
                    <td>{p.tag}</td>
                    <td>{p.universe}</td>
                    <td>
                      {p.startAddress ?? 'No space'} {p.auto ? '(proposed)' : ''}
                    </td>
                    <td>{p.endAddress}</td>
                    <td>{p.footprint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.segments.map((s) => (
            <p className="library-notice" key={s.id}>
              {s.id}: {s.unitLoads} unit loads · {length(s.lengthFt)} · {s.ends.length} end(s)
              requiring termination
            </p>
          ))}
        </section>
      )}
      {tab === 'issues' && (
        <section className="panel library-panel">
          <div className="library-panel-top">
            <h2>Issues</h2>
            <select
              aria-label="Issue severity"
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              {['all', 'error', 'warning', 'info'].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </div>
          <div className="issue-list">
            {result.messages
              .filter((m) => severity === 'all' || m.severity === severity)
              .map((m, i) => (
                <article key={i} className={`issue ${m.severity}`}>
                  <a href={`#/tables?row=${encodeURIComponent(m.entityRef)}`}>
                    <strong>{m.code}</strong>
                    <p>{m.text}</p>
                  </a>
                </article>
              ))}
            {!result.messages.length && <p>No issues.</p>}
          </div>
          {result.splits.map((s) => (
            <Button
              key={s.loadId}
              variant="outline"
              onClick={() =>
                useProjectStore.getState().updateProject({
                  loads: project.loads.map((l) =>
                    l.id === s.loadId ? { ...l, feedMethod: 'multi-feed', feeds: s.feeds } : l,
                  ),
                })
              }
            >
              Accept {s.feeds} feeds for {project.loads.find((l) => l.id === s.loadId)?.typeTag}
            </Button>
          ))}
        </section>
      )}
      {tab === 'bom' && (
        <section className="panel library-panel">
          <h2>Bill of materials</h2>
          <div className="wide-table">
            <table>
              <thead>
                <tr>
                  <th>SKU / wire</th>
                  <th>Description</th>
                  <th>Quantity</th>
                  <th>Unit</th>
                  <th>Reels</th>
                </tr>
              </thead>
              <tbody>
                {result.bom.map((b) => (
                  <tr key={b.key}>
                    <td>
                      {b.sku}
                      {b.isExample && <small>EXAMPLE / VERIFY</small>}
                    </td>
                    <td>{b.description}</td>
                    <td>{num(b.quantity, 2)}</td>
                    <td>{b.unit}</td>
                    <td>{b.reels ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
