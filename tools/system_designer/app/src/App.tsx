import type { MountOptions } from './mount';

export const PRODUCT_NAME = 'ilLumenate System Designer';

export function App({ options }: { options: MountOptions }) {
  return (
    <div className="ill-sd" data-testid="system-designer">
      <header className="ill-sd__header">
        <h1 className="ill-sd__title">{PRODUCT_NAME}</h1>
        {options.schedule ? (
          <p className="ill-sd__subtitle" data-testid="schedule-name">
            Schedule {options.schedule}
          </p>
        ) : null}
      </header>
      <main className="ill-sd__body">
        <p>
          {options.schedule
            ? 'The designer is being built. Soon you will plan power, check every run and export a riser from this schedule here.'
            : 'Open a fixture schedule and choose “Design system” to start a design.'}
        </p>
      </main>
    </div>
  );
}
