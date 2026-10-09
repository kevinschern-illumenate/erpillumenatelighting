import { useEffect, useState, type MouseEvent } from 'react';
import type { CommentAnchor, CommentView, DesignApi, DesignComment } from '../design/api';

/** Comments on a saved design, shared by the reviewer and the dealer (plan §14.2, WP-4.3). */
export function useComments(api: DesignApi, design: string | undefined) {
  const [comments, setComments] = useState<DesignComment[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!design || !api.listComments) return;
    let cancelled = false;
    api.listComments(design).then(
      (rows) => {
        if (cancelled) return;
        setComments(rows);
        setError('');
      },
      (e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'The comments could not be loaded');
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, design]);

  async function add(body: string, view: CommentView, anchor?: CommentAnchor) {
    if (!design) return false;
    try {
      const row = await api.addComment({ design, body, view, anchor });
      setComments((rows) => [...rows, row]);
      setError('');
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The comment could not be added');
      return false;
    }
  }

  async function resolve(commentId: string, resolved: boolean) {
    if (!design) return;
    try {
      const row = await api.resolveComment(design, commentId, resolved);
      setComments((rows) => rows.map((item) => (item.comment_id === row.comment_id ? row : item)));
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The comment could not be changed');
    }
  }

  return { comments, error, add, resolve };
}

export type Comments = ReturnType<typeof useComments>;

/** Where a pin goes on the sheet image: fractions of its width and height, kept to four places. */
export function pinAt(event: MouseEvent<HTMLElement>, sheet: string): CommentAnchor {
  const box = event.currentTarget.getBoundingClientRect();
  const fraction = (value: number, size: number) =>
    size > 0 ? Math.round(Math.min(1, Math.max(0, value / size)) * 10000) / 10000 : 0;
  return {
    sheet,
    x: fraction(event.clientX - box.left, box.width),
    y: fraction(event.clientY - box.top, box.height),
  };
}

/** The comments of one view, with a box to add one (and an optional pin). */
export function CommentThread({
  comments,
  view,
  canComment,
  anchor,
  onClearAnchor,
  title = 'Comments',
}: {
  comments: Comments;
  view: CommentView;
  canComment: boolean;
  anchor?: CommentAnchor | null;
  onClearAnchor?: () => void;
  title?: string;
}) {
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const rows = comments.comments.filter((item) => item.view === view);
  const pins = rows.filter((item) => item.anchor?.x !== undefined);

  async function send() {
    setBusy(true);
    if (await comments.add(body.trim(), view, anchor ?? undefined)) {
      setBody('');
      onClearAnchor?.();
    }
    setBusy(false);
  }

  return (
    <div className="ill-sd__card" data-testid={`comments-${view}`}>
      <h3>{title}</h3>
      {rows.length ? (
        <ol className="ill-sd__comments">
          {rows.map((item) => (
            <li key={item.comment_id} className={item.resolved ? 'ill-sd__comment--resolved' : undefined}>
              <p>
                {item.anchor?.x !== undefined ? <strong>Pin {pins.indexOf(item) + 1}. </strong> : null}
                {item.body}
              </p>
              <p className="ill-sd__muted">
                {item.author_name ?? item.author} · {item.created_on.slice(0, 16)}
                {item.resolved ? ' · Resolved' : ''}
              </p>
              {canComment ? (
                <button
                  type="button"
                  className="ill-sd__button ill-sd__button--quiet"
                  onClick={() => void comments.resolve(item.comment_id, !item.resolved)}
                >
                  {item.resolved ? 'Reopen' : 'Resolve'}
                </button>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <p className="ill-sd__muted">No comments yet.</p>
      )}
      {canComment ? (
        <>
          <label className="ill-sd__pick">
            <span>{anchor?.x !== undefined ? `Comment on the pin on sheet ${anchor.sheet}` : 'Add a comment'}</span>
            <textarea
              aria-label="Comment"
              value={body}
              maxLength={2000}
              onChange={(event) => setBody(event.target.value)}
            />
          </label>
          <div className="ill-sd__row">
            <button
              type="button"
              className="ill-sd__button"
              disabled={!body.trim() || busy}
              onClick={() => void send()}
            >
              Add comment
            </button>
            {anchor && onClearAnchor ? (
              <button type="button" className="ill-sd__button ill-sd__button--quiet" onClick={onClearAnchor}>
                Remove the pin
              </button>
            ) : null}
          </div>
        </>
      ) : null}
      {comments.error ? (
        <p className="ill-sd__error" role="alert">
          {comments.error}
        </p>
      ) : null}
    </div>
  );
}

/** Numbered pins over a sheet image; numbering matches the comment list of that view. */
export function SheetPins({
  comments,
  view,
  sheet,
  pending,
}: {
  comments: DesignComment[];
  view: CommentView;
  sheet: string;
  pending?: CommentAnchor | null;
}) {
  const pins = comments.filter((item) => item.view === view && item.anchor?.x !== undefined);
  return (
    <>
      {pins.map((item, index) =>
        item.anchor?.sheet === sheet ? (
          <span
            key={item.comment_id}
            className={`ill-sd__pin${item.resolved ? ' ill-sd__pin--resolved' : ''}`}
            style={{ left: `${item.anchor.x! * 100}%`, top: `${item.anchor.y! * 100}%` }}
            title={item.body}
            data-testid="comment-pin"
          >
            {index + 1}
          </span>
        ) : null,
      )}
      {pending?.x !== undefined && pending.sheet === sheet ? (
        <span
          className="ill-sd__pin ill-sd__pin--pending"
          style={{ left: `${pending.x * 100}%`, top: `${pending.y! * 100}%` }}
          aria-label="New pin"
        >
          +
        </span>
      ) : null}
    </>
  );
}
