import { Lightbulb, X } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../ui';
import { TOUR } from './help';

/** A first-run tour (SD-1.7) that sits above the step instead of blocking it. */
export function TourCard({ onDone }: { onDone(): void }) {
  const [index, setIndex] = useState(0);
  const tip = TOUR[index]!;
  const last = index === TOUR.length - 1;
  return (
    <div className="sd-tour" role="region" aria-label="Tour" data-testid="tour">
      <Lightbulb size={20} aria-hidden className="sd-tour__icon" />
      <div className="sd-tour__body">
        <p className="sd-tour__title">
          {tip.title}{' '}
          <span className="sd-tour__progress">
            {index + 1} of {TOUR.length}
          </span>
        </p>
        <p>{tip.text}</p>
      </div>
      <div className="sd-tour__actions">
        {last ? (
          <Button size="sm" variant="primary" onClick={onDone}>
            Got it
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setIndex(index + 1)}>
            Next tip
          </Button>
        )}
        <button type="button" className="sd-tour__close" onClick={onDone}>
          <X size={16} aria-hidden />
          <span className="sd-sr-only">Close the tour</span>
        </button>
      </div>
    </div>
  );
}
