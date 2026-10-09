import { useState } from 'react';

const KEY = 'ill-sd:feedback:';

/** The prompt shows once per design in this browser (WP-3.9). */
export function feedbackGiven(name: string): boolean {
  try {
    return globalThis.localStorage?.getItem(KEY + name) === '1';
  } catch {
    return false;
  }
}
function remember(name: string) {
  try {
    globalThis.localStorage?.setItem(KEY + name, '1');
  } catch {
    // Storage may be refused; the prompt then shows again on the next visit.
  }
}

/** A short rating after the first riser export (plan §23: dealer satisfaction). */
export function FeedbackPrompt({ name, onSend }: { name: string; onSend(rating: number, comment: string): void }) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [state, setState] = useState<'asking' | 'sent' | 'closed'>(feedbackGiven(name) ? 'closed' : 'asking');
  if (state === 'closed') return null;
  if (state === 'sent')
    return (
      <p className="ill-sd__muted" role="status" data-testid="feedback">
        Thank you. Your ilLumenate team reads every answer.
      </p>
    );
  return (
    <div className="ill-sd__card" data-testid="feedback">
      <h3>How well did the System Designer work for this design?</h3>
      <div className="ill-sd__toggle" role="group" aria-label="Rating from 1 to 5">
        {[1, 2, 3, 4, 5].map((value) => (
          <button key={value} type="button" aria-pressed={rating === value} onClick={() => setRating(value)}>
            {value}
          </button>
        ))}
      </div>
      <label className="ill-sd__pick">
        <span>Anything we should change? (optional)</span>
        <textarea value={comment} maxLength={500} rows={2} onChange={(event) => setComment(event.target.value)} />
      </label>
      <div className="ill-sd__row">
        <button
          type="button"
          className="ill-sd__button"
          disabled={!rating}
          onClick={() => {
            onSend(rating, comment.trim());
            remember(name);
            setState('sent');
          }}
        >
          Send
        </button>
        <button
          type="button"
          className="ill-sd__button ill-sd__button--quiet"
          onClick={() => {
            remember(name);
            setState('closed');
          }}
        >
          Not now
        </button>
      </div>
    </div>
  );
}
