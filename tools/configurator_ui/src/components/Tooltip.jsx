import { useState, useRef, useEffect, useId } from 'react';
import { Info, X } from 'lucide-react';

/**
 * Accessible tooltip with two-tier progressive disclosure.
 *
 * - Opens on hover AND keyboard focus; tap toggles on touch.
 * - role="tooltip" + aria-describedby wiring.
 * - Esc closes; focus-visible ring on the trigger.
 * - Tier 1: short `tooltip` text (always shown when open).
 * - Tier 2: inline "Learn more" disclosure expands `learnMore` (not a modal).
 *
 * @param {object} props
 * @param {string} props.label       Accessible label / heading for the term.
 * @param {string} props.tooltip     Short explanation (tier 1).
 * @param {string} [props.learnMore] Longer explanation (tier 2, optional).
 * @param {React.ReactNode} props.children  The trigger content (the term text).
 */
export default function Tooltip({ label, tooltip, learnMore, children }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const wrapRef = useRef(null);
  const tipId = useId();
  const hideTimer = useRef(null);

  // Clear pending hide timer on unmount.
  useEffect(() => () => clearTimeout(hideTimer.current), []);

  // Close on Escape and on outside click/touch.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setOpen(false);
        setExpanded(false);
      }
    };
    const onDocPointer = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
        setExpanded(false);
      }
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onDocPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onDocPointer);
    };
  }, [open]);

  const show = () => {
    clearTimeout(hideTimer.current);
    setOpen(true);
  };
  const hide = () => {
    // Delay closing so the mouse can travel from the trigger into the popup
    // (the popup is absolutely positioned below the trigger with a gap).
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      // Keep open if the user expanded "Learn more" so they can read it.
      if (!expanded) setOpen(false);
    }, 150);
  };

  return (
    <span
      ref={wrapRef}
      className="ill-tt-wrap relative inline-flex items-center"
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <button
        type="button"
        aria-label={`About ${label}`}
        aria-describedby={open ? tipId : undefined}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded text-ill-accent underline decoration-dotted underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-ill-accent focus-visible:ring-offset-1"
        onFocus={show}
        onBlur={hide}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
          if (open) setExpanded(false);
        }}
      >
        {children}
        <Info size={14} aria-hidden="true" />
      </button>

      {open && (
        <span
          role="tooltip"
          id={tipId}
          className="absolute left-0 top-full z-50 mt-2 block w-72 rounded-lg border border-ill-borderStr bg-ill-paper p-3 text-left text-sm font-normal text-ill-ink shadow-lg"
        >
          <span className="mb-1 flex items-center justify-between">
            <span className="font-semibold text-ill-ink">{label}</span>
            <button
              type="button"
              aria-label="Close"
              className="rounded p-0.5 text-ill-subtle outline-none hover:text-ill-ink focus-visible:ring-2 focus-visible:ring-ill-accent"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                setExpanded(false);
              }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </span>
          <span className="block text-ill-muted">{tooltip}</span>

          {learnMore && (
            <span className="mt-2 block">
              <button
                type="button"
                aria-expanded={expanded}
                className="rounded text-xs font-semibold text-ill-accent outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ill-accent"
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded((v) => !v);
                }}
              >
                {expanded ? 'Show less' : 'Learn more'}
              </button>
              {expanded && (
                <span className="mt-1 block border-t border-ill-border pt-2 text-ill-muted">
                  {learnMore}
                </span>
              )}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
