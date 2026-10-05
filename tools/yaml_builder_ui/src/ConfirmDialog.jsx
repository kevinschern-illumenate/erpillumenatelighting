import { useEffect, useId, useRef } from 'react';

export default function ConfirmDialog({ confirm, onClose }) {
  const dialog = useRef(null);
  const title = useId();
  useEffect(() => { dialog.current.showModal(); }, []);
  return <dialog ref={dialog} className="catalog-modal" aria-labelledby={title} onCancel={onClose}>
    <h2 id={title}>{confirm.title}</h2>
    {confirm.body || <p>Download your current draft first if you want to keep a copy.</p>}
    <button autoFocus onClick={onClose}>Cancel</button>
    <button className="catalog-primary" onClick={() => { onClose(); confirm.run(); }}>{confirm.label || 'Replace draft'}</button>
  </dialog>;
}
