import { X } from 'lucide-react';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { SeverityIcon, type Severity } from './SeverityIcon';

export interface ToastOptions {
  title: string;
  description?: string;
  tone?: Severity;
  /** An undo or follow-up; the toast stays longer when there is one. */
  action?: { label: string; onClick(): void };
  durationMs?: number;
}

interface ToastItem extends ToastOptions {
  id: number;
}

type Push = (toast: ToastOptions) => void;

// Without a provider (step tests) toasts are dropped rather than crashing the caller.
const ToastContext = createContext<Push>(() => {});

export const useToast = () => useContext(ToastContext);

const MAX_TOASTS = 3;

/** Non-blocking notices in a polite live region, newest last, at most three at a time. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((item) => item.id !== id)), []);
  const push = useCallback<Push>((toast) => {
    const id = next.current++;
    setToasts((list) => [...list, { ...toast, id }].slice(-MAX_TOASTS));
  }, []);
  const value = useMemo(() => push, [push]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ill-sd-layer sd-toasts" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((toast) => (
          <ToastView key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastView({ toast, onDismiss }: { toast: ToastItem; onDismiss(): void }) {
  const [paused, setPaused] = useState(false);
  const duration = toast.durationMs ?? (toast.action ? 10_000 : 5_000);
  useEffect(() => {
    if (paused) return;
    const timer = setTimeout(onDismiss, duration);
    return () => clearTimeout(timer);
  }, [paused, duration, onDismiss]);
  return (
    <div
      className={`sd-toast sd-toast--${toast.tone ?? 'info'}`}
      data-testid="toast"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <SeverityIcon severity={toast.tone ?? 'info'} label />
      <div className="sd-toast__body">
        <p className="sd-toast__title">{toast.title}</p>
        {toast.description ? <p className="sd-toast__text">{toast.description}</p> : null}
      </div>
      {toast.action ? (
        <button
          type="button"
          className="sd-toast__action"
          onClick={() => {
            toast.action!.onClick();
            onDismiss();
          }}
        >
          {toast.action.label}
        </button>
      ) : null}
      <button type="button" className="sd-toast__close" onClick={onDismiss}>
        <X aria-hidden size={14} />
        <span className="sd-sr-only">Dismiss</span>
      </button>
    </div>
  );
}
