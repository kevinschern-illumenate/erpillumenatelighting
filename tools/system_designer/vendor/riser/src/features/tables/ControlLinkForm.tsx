import { useState } from 'react';
import type { Project } from '../../schemas/project';
import { ControlLinkSchema } from '../../schemas/project';
import type { CatalogItem } from '../../schemas/catalog';
import { EnvironmentSchema, ProtocolSchema, type Protocol } from '../../schemas/common';
import { controlPortOptions, parsePort } from '../../engine/ports';
import { Button } from '../../components/ui/button';

type Link = Project['controlLinks'][number];
export function ControlLinkForm({
  project,
  products,
  initial,
  onSave,
  onCancel,
}: {
  project: Project;
  products: CatalogItem[];
  initial: Link | Protocol;
  onSave: (link: Link) => void;
  onCancel: () => void;
}) {
  const editing = typeof initial === 'object' ? initial : undefined;
  const reference = (ref?: Link['from']) =>
    ref ? `${ref.ref}${ref.port ? `::${ref.port}` : ''}` : '';
  const initialProtocol = editing?.protocol ?? (initial as Protocol);
  function existingValue(ref: Link['from'] | undefined, direction: 'in' | 'out') {
    if (!ref) return '';
    const equipment = project.equipment.find((e) => e.id === ref.ref || e.tag === ref.ref);
    const normalized = { ...ref, ref: equipment?.tag ?? ref.ref };
    const value = reference(normalized);
    const options = controlPortOptions(project, products, direction, initialProtocol);
    if (options.some((o) => o.value === value)) return value;
    const choices = options.filter((o) => parsePort(o.value).ref === normalized.ref);
    return !ref.port && choices.length === 1 ? choices[0]!.value : value;
  }
  const [protocol, setProtocol] = useState<Protocol>(editing?.protocol ?? (initial as Protocol));
  const [from, setFrom] = useState(existingValue(editing?.from, 'out'));
  const [to, setTo] = useState(existingValue(editing?.to, 'in'));
  const [length, setLength] = useState(
    editing ? String(editing.lengthFt * (project.settings.units === 'm' ? 0.3048 : 1)) : '',
  );
  const [env, setEnv] = useState<Link['env']>(editing?.env ?? 'riser');
  const [universe, setUniverse] = useState(editing?.universe ? String(editing.universe) : '');
  const [notes, setNotes] = useState(editing?.notes ?? '');
  const [error, setError] = useState('');
  // Exclude the edited edge when testing cycle-safe endpoint choices.
  const context = editing
    ? { ...project, controlLinks: project.controlLinks.filter((l) => l.id !== editing.id) }
    : project;
  const sources = controlPortOptions(
    context,
    products,
    'out',
    protocol,
    to ? parsePort(to).ref : undefined,
  );
  const receivers = controlPortOptions(
    context,
    products,
    'in',
    protocol,
    from ? parsePort(from).ref : undefined,
  );
  const source = sources.find((o) => o.value === from);
  const receiver = receivers.find((o) => o.value === to);
  const isDmx = protocol === 'DMX512' || protocol === 'RDM';
  const valid =
    !!source &&
    !!receiver &&
    length.trim() !== '' &&
    Number.isFinite(Number(length)) &&
    Number(length) >= 0;
  return (
    <section className="editor-section" aria-label="Control link form">
      <h3>{editing ? 'Edit control link' : 'Add control link'}</h3>
      <p className="editor-help">
        Choose the signal first, then the actual source output and receiving device. A 0–10 V link
        is a separate two-conductor dimming cable; keep the fixture’s power feed in Loads.
      </p>
      <div className="form-grid">
        <label>
          Signal protocol
          <select
            value={protocol}
            onChange={(e) => {
              setProtocol(e.target.value as Protocol);
              setFrom('');
              setTo('');
              setError('');
            }}
          >
            {ProtocolSchema.options
              .filter((p) => !['none', 'phase-forward', 'phase-reverse', 'PWM'].includes(p))
              .map((p) => (
                <option key={p}>{p}</option>
              ))}
          </select>
        </label>
        <label>
          Source device / output
          <select value={from} onChange={(e) => setFrom(e.target.value)}>
            <option value="">Choose source output…</option>
            {sources.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Receiving device / input
          <select value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">Choose receiving device…</option>
            {receivers.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Cable length ({project.settings.units})
          <input
            type="number"
            min="0"
            step="any"
            value={length}
            onChange={(e) => setLength(e.target.value)}
            placeholder="Enter physical cable length"
          />
        </label>
        <label>
          Cable environment
          <select value={env} onChange={(e) => setEnv(e.target.value as Link['env'])}>
            {EnvironmentSchema.options.map((e) => (
              <option key={e}>{e}</option>
            ))}
          </select>
        </label>
        {isDmx && (
          <label>
            DMX universe (optional)
            <input
              type="number"
              min="1"
              step="1"
              value={universe}
              onChange={(e) => setUniverse(e.target.value)}
              placeholder="Use receiver configuration"
            />
          </label>
        )}
        <label>
          Control link notes
          <input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      </div>
      {!sources.length && (
        <p className="editor-help">
          No compatible {protocol} output is available. Add its controller or converter in Equipment
          and configure its output ports in Libraries.
        </p>
      )}
      {!receivers.length && (
        <p className="editor-help">
          No compatible {protocol} receiver is available. Check the fixture or driver’s dimming
          protocols in Libraries.
        </p>
      )}
      {source && receiver && (
        <p className="editor-help">
          {protocol}: {source.label} → {receiver.label}.{' '}
          {length !== ''
            ? `${length} ${project.settings.units} of cable, ${env}.`
            : 'Enter the cable length to finish.'}
        </p>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <div className="action-bar">
        <Button
          disabled={!valid}
          onClick={() => {
            try {
              const link = ControlLinkSchema.parse({
                id: editing?.id ?? crypto.randomUUID(),
                protocol,
                from: parsePort(from),
                to: parsePort(to),
                lengthFt: Number(length) / (project.settings.units === 'm' ? 0.3048 : 1),
                env,
                notes,
                ...(isDmx && universe !== '' ? { universe: Number(universe) } : {}),
              });
              const duplicate = context.controlLinks.some(
                (l) =>
                  l.protocol === protocol && reference(l.from) === from && reference(l.to) === to,
              );
              if (duplicate)
                throw new Error('This control link already exists. Edit its row instead.');
              onSave(link);
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e));
            }
          }}
        >
          {editing ? 'Save control link' : 'Add control cable'}
        </Button>
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
