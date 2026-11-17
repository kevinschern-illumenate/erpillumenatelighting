import type { Design } from '@ill/core-schemas/design';
import type { CheckState } from '../design/engine';

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

/** The design's size at a glance (SD-1.3): runs, connected watts, supplies and home-run wire. No cost (D6). */
export function designTotals(design: Design | null, engine: CheckState) {
  const runs = design?.runs.length ?? 0;
  if (engine.state !== 'ready') return { runs, watts: null, supplies: null, wireFt: null };
  const result = engine.check.result;
  const watts = result.runs.reduce((sum, run) => sum + run.wattsW, 0);
  const wireFt = result.runs.reduce((sum, run) => sum + run.lengthFt * Math.max(1, run.parallelSets), 0);
  const supplies = new Set(result.loading.filter((item) => item.kind === 'psu').map((item) => item.entityId)).size;
  return { runs, watts, supplies, wireFt };
}

export function StatusStrip({ design, engine }: { design: Design | null; engine: CheckState }) {
  const totals = designTotals(design, engine);
  const value = (amount: number | null) => (amount === null ? '–' : number.format(amount));
  return (
    <footer className="sd-status" aria-label="Design totals">
      <dl>
        <div>
          <dt>Runs</dt>
          <dd>{totals.runs}</dd>
        </div>
        <div>
          <dt>Connected load</dt>
          <dd>{totals.watts === null ? '–' : `${value(totals.watts)} W`}</dd>
        </div>
        <div>
          <dt>Supplies</dt>
          <dd>{value(totals.supplies)}</dd>
        </div>
        <div>
          <dt>Home-run wire</dt>
          <dd>{totals.wireFt === null ? '–' : `${value(totals.wireFt)} ft`}</dd>
        </div>
      </dl>
      {engine.state === 'waiting' ? <span className="sd-status__note">Checking…</span> : null}
    </footer>
  );
}
