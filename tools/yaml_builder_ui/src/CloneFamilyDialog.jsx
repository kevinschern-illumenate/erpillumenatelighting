import { useEffect, useId, useMemo, useRef, useState } from 'react';
import schema from './catalog-schema.json';
import { emptyCatalog, referenceSummary } from './catalog-model.js';
import { cloneFamily, discoverFamily, rootTypes, ruleRenamer } from './clone-model.js';

const SHOWN = 400;
const FETCHES = 4;
const shortName = name => name.replace(/^ilL-/, '');
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const key = (doctype, name) => JSON.stringify([doctype, name]);
const MODE_LABELS = { copy: 'Copy as new', link: 'Keep original', existing: 'Use existing' };

/**
 * Copy an existing ERPNext family into the draft under new names. In ERPNext, records to
 * copy are fetched in full (`api.record`) so their child rows come along; on Vercel the
 * exported reference already holds them.
 */
export default function CloneFamilyDialog({ catalog, product, reference, api, onApply, onClose }) {
  const dialog = useRef(null);
  const title = useId();
  const types = useMemo(() => rootTypes(schema).filter(doctype => Object.keys(reference?.doctypes?.[doctype]?.records || {}).length), [reference]);
  const [rootType, setRootType] = useState(() => (types.includes(product.template) ? product.template : types[0]) || '');
  const [query, setQuery] = useState('');
  const [root, setRoot] = useState(null);
  const [rules, setRules] = useState([{ find: '', replace: '' }]);
  const [matchCase, setMatchCase] = useState(false);
  const [modes, setModes] = useState(() => new Map());
  const [show, setShow] = useState('copy');
  const [replaceDraft, setReplaceDraft] = useState(false);
  const [fetched, setFetched] = useState(() => new Map());
  const [failed, setFailed] = useState(() => new Map());
  const inflight = useRef(new Set());
  const alive = useRef(true);
  useEffect(() => { dialog.current.showModal(); return () => { alive.current = false; }; }, []);

  const full = useMemo(() => api
    ? (doctype, name) => fetched.get(key(doctype, name))
    : (doctype, name) => reference?.doctypes?.[doctype]?.records?.[name], [api, fetched, reference]);
  const discovery = useMemo(() => root && reference
    ? discoverFamily({ root, reference, schema, full, modes, rename: ruleRenamer(rules, { matchCase }) })
    : { nodes: [], needed: [], truncated: false }, [root, reference, full, modes, rules, matchCase]);
  const waiting = discovery.needed.filter(node => !failed.has(key(node.doctype, node.name)));
  // Fetch records to copy a few at a time; each arrival can reveal more links to follow.
  useEffect(() => {
    if (!api) return;
    for (const node of waiting) {
      const id = key(node.doctype, node.name);
      if (inflight.current.size >= FETCHES) break;
      if (inflight.current.has(id)) continue;
      inflight.current.add(id);
      api.record(node.doctype, node.name).then(record => {
        inflight.current.delete(id);
        if (alive.current) setFetched(previous => new Map(previous).set(id, record));
      }, error => {
        inflight.current.delete(id);
        if (alive.current) setFailed(previous => new Map(previous).set(id, error?.message || String(error)));
      });
    }
  }); // eslint-disable-line react-hooks/exhaustive-deps

  const needle = query.trim().toLowerCase();
  const candidates = useMemo(() => {
    const records = reference?.doctypes?.[rootType]?.records || {};
    return Object.keys(records).filter(name => !needle || `${name} ${referenceSummary(rootType, records[name], schema)}`.toLowerCase().includes(needle));
  }, [reference, rootType, needle]);
  const copies = discovery.nodes.filter(node => node.mode === 'copy');
  const broken = copies.filter(node => failed.has(key(node.doctype, node.name)));
  const counts = Object.fromEntries(['copy', 'link', 'existing'].map(mode => [mode, discovery.nodes.filter(node => node.mode === mode).length]));
  const listed = discovery.nodes.filter(node => show === 'all' || (show === 'copy' ? node.mode !== 'link' : node.mode === 'link'));
  const rootNode = discovery.nodes[0];
  const otherProduct = root && Object.values(schema.products).some(item => item.template === root.doctype) && root.doctype !== product.template;
  const ready = root && copies.length > 0 && !waiting.length && !broken.length;
  const choose = name => { setRoot({ doctype: rootType, name }); setModes(new Map()); setShow('copy'); };
  const setMode = (node, mode) => setModes(previous => new Map(previous).set(key(node.doctype, node.name), mode));
  const setRule = (index, field, value) => setRules(previous => previous.map((rule, i) => i === index ? { ...rule, [field]: value } : rule));
  const apply = () => {
    const result = cloneFamily(replaceDraft ? { ...emptyCatalog(catalog.product_type), series_name: catalog.series_name } : catalog, schema, discovery, full);
    onClose();
    onApply({ ...result, root, newRoot: rootNode?.newName });
  };

  return <dialog ref={dialog} className="catalog-modal catalog-modal-wide catalog-clone" aria-labelledby={title} onCancel={onClose}>
    <h2 id={title}>Clone an existing family</h2>
    <p>Pick a family in ERPNext and give it new names. Every record whose name the rules change is copied, along with the maps,
      offerings and submittal mappings that belong to it. Records whose names stay the same are linked, not copied.</p>
    {!reference ? <p className="catalog-run-errors">Existing ERPNext records have not loaded yet.</p> : <>
      <section className="catalog-clone-step" aria-label="Family to copy">
        <h3>1. Family to copy</h3>
        <div className="catalog-clone-pick">
          <label>Start from <select value={rootType} onChange={e => { setRootType(e.target.value); setQuery(''); }}>
            {types.map(doctype => <option key={doctype} value={doctype}>{shortName(doctype)}</option>)}</select></label>
          <label>Search <input value={query} onChange={e => setQuery(e.target.value)} placeholder={`Find a ${shortName(rootType)}…`} /></label>
        </div>
        <div className="catalog-clone-candidates" role="listbox" aria-label={`${shortName(rootType)} records`}>
          {candidates.slice(0, 60).map(name => <button key={name} type="button" role="option" aria-selected={root?.doctype === rootType && root.name === name}
            onClick={() => choose(name)}><strong>{name}</strong><small>{referenceSummary(rootType, reference.doctypes[rootType].records[name], schema, 3)}</small></button>)}
          {!candidates.length && <p>No {shortName(rootType)} records match.</p>}
        </div>
        {candidates.length > 60 && <p>Showing 60 of {candidates.length}. Refine the search to see more.</p>}
      </section>
      {root && <section className="catalog-clone-step" aria-label="Rename rules">
        <h3>2. Rename rules for {root.name}</h3>
        <p>Each rule replaces text in every name, in order: <code>CA01</code> → <code>CA03</code> turns <code>ILL-CA01-SW</code> into <code>ILL-CA03-SW</code>.
          {!matchCase && ' Lowercase and uppercase matches keep their case (ill-ca01-sw → ill-ca03-sw).'}</p>
        {rules.map((rule, i) => <div className="catalog-clone-rule" key={i}>
          <input aria-label={`Rule ${i + 1}: find`} value={rule.find} onChange={e => setRule(i, 'find', e.target.value)} placeholder="Find, e.g. CA01" autoFocus={i === 0} />
          <span aria-hidden="true">→</span>
          <input aria-label={`Rule ${i + 1}: replace with`} value={rule.replace} onChange={e => setRule(i, 'replace', e.target.value)} placeholder="Replace with, e.g. CA03" />
          {rules.length > 1 && <button type="button" aria-label={`Remove rule ${i + 1}`} onClick={() => setRules(rules.filter((_, at) => at !== i))}>×</button>}
        </div>)}
        <button type="button" onClick={() => setRules([...rules, { find: '', replace: '' }])}>+ Add rule</button>
        <label className="catalog-clone-option"><input type="checkbox" checked={matchCase} onChange={e => setMatchCase(e.target.checked)} /> Match case exactly</label>
      </section>}
      {root && <section className="catalog-clone-step" aria-label="Review">
        <h3>3. Review</h3>
        <p role="status">{rootNode?.mode === 'link' ? <span className="catalog-replace-conflict">{rootNode.reason}.</span>
          : `${plural(counts.copy, 'record')} to copy · ${plural(counts.link, 'link')} to existing records${counts.existing ? ` · ${counts.existing} new ${counts.existing === 1 ? 'name already exists' : 'names already exist'} in ERPNext and will be linked` : ''}`}
          {waiting.length > 0 && <span className="catalog-progress"><span className="catalog-spinner" aria-hidden="true" /> Loading {plural(waiting.length, 'record')} from ERPNext…</span>}</p>
        {discovery.truncated && <p className="catalog-replace-conflict">Stopped at {copies.length} records to copy. Narrow the rename rules, or keep some records as originals.</p>}
        {broken.length > 0 && <p className="catalog-run-errors">{plural(broken.length, 'record')} could not be loaded: {broken.slice(0, 5).map(node => `${shortName(node.doctype)} ${node.name} (${failed.get(key(node.doctype, node.name))})`).join('; ')}. Keep them as originals to continue.</p>}
        {otherProduct && <p className="catalog-replace-conflict">This {shortName(root.doctype)} belongs to another product family than the {product.label} draft. Switch the product first to keep its draft separate.</p>}
        <div className="catalog-segmented" role="group" aria-label="Show">
          <button type="button" aria-pressed={show === 'copy'} onClick={() => setShow('copy')}>New ({counts.copy + counts.existing})</button>
          <button type="button" aria-pressed={show === 'link'} onClick={() => setShow('link')}>Linked ({counts.link})</button>
          <button type="button" aria-pressed={show === 'all'} onClick={() => setShow('all')}>All ({discovery.nodes.length})</button>
        </div>
        <div className="catalog-result-table catalog-clone-review"><table>
          <thead><tr><th scope="col">Action</th><th scope="col">Record</th><th scope="col">New name</th><th scope="col">Why</th></tr></thead>
          <tbody>{listed.slice(0, SHOWN).map(node => <tr key={key(node.doctype, node.name)}>
            <td>{node.modes.length > 1
              ? <select aria-label={`Action for ${shortName(node.doctype)} ${node.name}`} value={node.mode} onChange={e => setMode(node, e.target.value)}>
                {node.modes.map(mode => <option key={mode} value={mode}>{mode === 'existing' ? `Use existing ${node.newName}` : MODE_LABELS[mode]}</option>)}</select>
              : MODE_LABELS[node.mode]}</td>
            <td><small>{shortName(node.doctype)}</small><br />{node.name}</td>
            <td>{node.mode === 'link' ? <small>—</small> : <ins>{node.newName}</ins>}</td>
            <td><small>{node.reason}{node.via === 'owned' ? ` · belongs to ${node.owner}` : node.via === 'link' ? ` · linked from ${node.owner}` : ''}</small></td>
          </tr>)}</tbody>
        </table></div>
        {listed.length > SHOWN && <p>Showing {SHOWN} of {listed.length}.</p>}
        <p><small>Copies keep the original's values, including attachment URLs, so replace spec sheets and images for the new family.
          {api ? '' : ' The export holds only short fields for Webflow products.'} A copied template's link to its copied Webflow product is cleared to avoid a circular import; set it in ERPNext afterwards.</small></p>
        <label className="catalog-clone-option"><input type="checkbox" checked={replaceDraft} onChange={e => setReplaceDraft(e.target.checked)} /> Replace the current draft instead of adding to it</label>
      </section>}
    </>}
    <div className="catalog-modal-actions">
      <button onClick={onClose}>Cancel</button>
      <button className="catalog-primary" disabled={!ready} onClick={apply}>{replaceDraft ? 'Replace draft with' : 'Add'} {plural(copies.length, 'record')}</button>
    </div>
  </dialog>;
}
