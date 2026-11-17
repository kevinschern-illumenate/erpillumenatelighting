import { Fragment, useEffect, useRef } from 'react';
import { Button, Dialog, Kbd, SUPPORT_URL } from '../ui';
import { SHORTCUTS, STEP_TIPS } from './help';
import { GRIDS_TAB, STEPS, type StepId } from './steps';

/** Help that knows where you are (SD-1.7): this step, the shortcuts, and who to ask. */
export function HelpDrawer({
  open,
  onOpenChange,
  step,
  section,
  onTour,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  step: StepId;
  section: 'step' | 'shortcuts';
  onTour(): void;
}) {
  const shortcuts = useRef<HTMLHeadingElement>(null);
  const current = [...STEPS, GRIDS_TAB].find((item) => item.id === step)!;
  useEffect(() => {
    if (open && section === 'shortcuts') requestAnimationFrame(() => shortcuts.current?.scrollIntoView?.());
  }, [open, section]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} variant="drawer" title="Help" data-testid="help-drawer">
      <section className="sd-help__section">
        <h3>This step: {current.label}</h3>
        <p>{STEP_TIPS[step]}</p>
      </section>
      <section className="sd-help__section">
        <h3>The steps</h3>
        <ol className="sd-help__steps">
          {STEPS.map((item) => (
            <li key={item.id}>
              <strong>{item.label}</strong> — {item.summary}
            </li>
          ))}
        </ol>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            onOpenChange(false);
            onTour();
          }}
        >
          Show the tour again
        </Button>
      </section>
      <section className="sd-help__section">
        <h3 ref={shortcuts} tabIndex={-1}>
          Keyboard shortcuts
        </h3>
        <dl className="sd-help__keys">
          {SHORTCUTS.map((item) => (
            <Fragment key={item.action}>
              <dt>
                {item.keys.map((key, index) => (
                  <Fragment key={key}>
                    {index ? ' + ' : null}
                    <Kbd>{key}</Kbd>
                  </Fragment>
                ))}
              </dt>
              <dd>{item.action}</dd>
            </Fragment>
          ))}
        </dl>
      </section>
      <section className="sd-help__section">
        <h3>Need a hand?</h3>
        <p>
          Your ilLumenate representative can review a design with you, or{' '}
          <a href={SUPPORT_URL} target="_blank" rel="noreferrer">
            contact ilLumenate support
          </a>
          .
        </p>
      </section>
    </Dialog>
  );
}
