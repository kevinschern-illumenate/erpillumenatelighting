import { useId } from 'react';
import schema from './catalog-schema.json';
import { blankRecord, recordName, inReference, referenceSummary } from './catalog-model.js';

export function RecordFields({ doctype, row, onChange, catalog, reference = null, filter = '', depth = 0 }) {
  const id = useId();
  const meta = schema.doctypes[doctype];
  const edit = (key, value) => {
    const next = { ...row };
    if (value === '') delete next[key]; else next[key] = value;
    onChange(next);
  };
  const fields = meta.fields.filter(field => !field.read_only || Object.hasOwn(row, field.fieldname));
  if (!depth && (!meta.autoname || meta.autoname === 'prompt')) {
    fields.unshift({ fieldname: 'name', label: 'Record ID', fieldtype: 'Data', reqd: meta.autoname === 'prompt' });
  }
  return <div className="catalog-fields">
    {fields.filter(field => !filter || `${field.label} ${field.fieldname}`.toLowerCase().includes(filter.toLowerCase())).map(field => {
      const key = field.fieldname;
      const value = row[key] ?? '';
      const inputId = `${id}-${key}`;
      if (['Table', 'Table MultiSelect'].includes(field.fieldtype)) {
        const children = Array.isArray(value) ? value : [];
        return <details className="catalog-table" key={key} open={children.length > 0 || undefined}>
          <summary>{field.label} {field.reqd ? '*' : ''} <span>{children.length} rows</span></summary>
          {value && !Array.isArray(value) && <p role="alert">Invalid child table. Replace it with rows below.</p>}
          {children.map((child, i) => <fieldset key={i}>
            <legend>{field.label} · {i + 1}</legend>
            <RecordFields doctype={field.options} row={child && typeof child === 'object' ? child : {}} catalog={catalog} reference={reference} depth={depth + 1}
              onChange={next => edit(key, children.map((item, index) => index === i ? next : item))} />
            <button className="catalog-danger" onClick={() => edit(key, children.filter((_, index) => index !== i))}>Remove row {i + 1}</button>
          </fieldset>)}
          <button onClick={() => edit(key, [...children, blankRecord(field.options, schema)])}>+ Add {field.label} row</button>
        </details>;
      }
      const target = field.fieldtype === 'Dynamic Link' ? row[field.options] : field.options;
      const isLink = ['Link', 'Dynamic Link'].includes(field.fieldtype);
      const existing = isLink ? reference?.doctypes?.[target]?.records || {} : {};
      const suggestions = isLink
        ? [...new Set([...(catalog.records[target] || []).map(item => recordName(target, item, schema)), ...(catalog.external_links[target] || []),
          ...Object.keys(existing)])].filter(Boolean) : [];
      const numeric = ['Int', 'Float', 'Currency', 'Percent'].includes(field.fieldtype);
      let input;
      if (field.fieldtype === 'Check') {
        input = <input id={inputId} type="checkbox" checked={Boolean(value)} onChange={e => edit(key, e.target.checked ? 1 : 0)} />;
      } else if (field.fieldtype === 'Select') {
        input = <select id={inputId} value={value} onChange={e => edit(key, e.target.value)}>
          <option value="">Select…</option>
          {(field.options || '').split('\n').filter(Boolean).map(option => <option key={option}>{option}</option>)}
        </select>;
      } else if (['Small Text', 'Text', 'Long Text', 'Text Editor', 'JSON', 'Code'].includes(field.fieldtype)) {
        input = <textarea id={inputId} rows={3} value={typeof value === 'object' ? JSON.stringify(value, null, 2) : value} onChange={e => edit(key, e.target.value)} />;
      } else {
        input = <><input id={inputId} type={numeric ? 'number' : 'text'} step={field.fieldtype === 'Int' ? '1' : 'any'} value={value}
          list={suggestions.length ? `${inputId}-choices` : undefined}
          onChange={e => edit(key, numeric && e.target.value !== '' ? Number(e.target.value) : e.target.value)} />
          {suggestions.length > 0 && <datalist id={`${inputId}-choices`}>{suggestions.map(option => <option key={option} value={option}
            label={Object.hasOwn(existing, option) ? `ERPNext · ${referenceSummary(target, existing[option], schema, 3)}` : undefined} />)}</datalist>}</>;
      }
      return <div className={`catalog-field ${field.fieldtype === 'Check' ? 'catalog-check' : ''}`} key={key}>
        <label htmlFor={inputId}>{field.label || key}{field.reqd ? ' *' : ''}</label>
        {input}
        {isLink && <small>Links to {target || 'the selected attribute DocType'}</small>}
        {isLink && value !== '' && inReference(reference, target, String(value)) && <small className="catalog-ok">
          Existing ERPNext record{referenceSummary(target, existing[String(value)], schema) ? ` · ${referenceSummary(target, existing[String(value)], schema)}` : ''}</small>}
        {field.description && <small>{field.description.replace(/<[^>]*>/g, '')}</small>}
      </div>;
    })}
  </div>;
}
