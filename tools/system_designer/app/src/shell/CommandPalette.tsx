import { Search } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import { Dialog, SeverityIcon } from '../ui';
import type { Check } from './open';
import { GRIDS_TAB, STEPS, type Mode, type StepId } from './steps';

export interface PaletteCommand {
  id: string;
  label: string;
  hint?: string;
  severity?: Check['severity'];
  run(): void;
}

/** Ctrl+K (SD-2.2): type to jump to a step or to the item a check is about. */
export function CommandPalette({
  open,
  onOpenChange,
  mode,
  checks,
  onStep,
  onCheck,
  extra = [],
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  mode: Mode;
  checks: Check[];
  onStep(step: StepId): void;
  onCheck(check: Check): void;
  extra?: PaletteCommand[];
}) {
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const commands = useMemo<PaletteCommand[]>(() => {
    const steps = (mode === 'engineering' ? [...STEPS, GRIDS_TAB] : STEPS).map((step) => ({
      id: `step:${step.id}`,
      label: `Go to ${step.label}`,
      hint: 'Step',
      run: () => onStep(step.id),
    }));
    const items = checks.map((check) => ({
      id: `check:${check.id}`,
      label: `${check.title}: ${check.detail}`,
      hint: 'Check',
      severity: check.severity,
      run: () => onCheck(check),
    }));
    return [...steps, ...extra, ...items];
  }, [mode, checks, onStep, onCheck, extra]);
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = commands.filter((command) => words.every((word) => command.label.toLowerCase().includes(word))).slice(0, 50);
  const close = () => {
    onOpenChange(false);
    setQuery('');
    setActive(0);
  };
  const choose = (command: PaletteCommand | undefined) => {
    if (!command) return;
    close();
    command.run();
  };
  const selected = Math.min(active, Math.max(shown.length - 1, 0));
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => (value ? onOpenChange(true) : close())}
      title="Find a step or check"
      size="md"
      initialFocus={input}
      className="sd-palette"
      data-testid="palette"
    >
      <div className="sd-palette__search">
        <Search size={16} aria-hidden />
        <input
          ref={input}
          className="sd-input"
          role="combobox"
          aria-expanded
          aria-controls="sd-palette-list"
          aria-activedescendant={shown[selected] ? `sd-palette-${selected}` : undefined}
          aria-label="Search steps and checks"
          placeholder="Type a step, a run, a supply…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setActive((selected + 1) % Math.max(shown.length, 1));
            } else if (event.key === 'ArrowUp') {
              event.preventDefault();
              setActive((selected - 1 + shown.length) % Math.max(shown.length, 1));
            } else if (event.key === 'Enter') {
              event.preventDefault();
              choose(shown[selected]);
            }
          }}
        />
      </div>
      <ul id="sd-palette-list" role="listbox" aria-label="Results" className="sd-palette__list">
        {shown.map((command, index) => (
          <li
            key={command.id}
            id={`sd-palette-${index}`}
            role="option"
            aria-selected={index === selected}
            className="sd-palette__item"
            onMouseEnter={() => setActive(index)}
            onClick={() => choose(command)}
          >
            {command.severity ? <SeverityIcon severity={command.severity} label /> : null}
            <span className="sd-palette__label">{command.label}</span>
            {command.hint ? <span className="sd-palette__hint">{command.hint}</span> : null}
          </li>
        ))}
        {!shown.length ? <li className="sd-palette__empty">Nothing matches “{query}”.</li> : null}
      </ul>
    </Dialog>
  );
}
