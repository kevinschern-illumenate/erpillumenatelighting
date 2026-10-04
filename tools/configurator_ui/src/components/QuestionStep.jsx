import {visibleOptions} from '../lib/engine.js';
import FamilyChooser from './FamilyChooser.jsx';
import GlossaryTerm from './GlossaryTerm.jsx';

export default function QuestionStep({question,answers,onChange,counts={},glossary={}}) {
  const value=answers[question.id];
  const options=visibleOptions(question,answers);
  const disabled=new Map((counts.disabled||[]).map(o=>[o.value,o.reason]));
  const toggle=(v)=>onChange(question.type==='multi' ? (value||[]).includes(v) ? value.filter(x=>x!==v) : [...(value||[]),v] : v);
  return <div>
    <h2 tabIndex={-1} className="font-display text-2xl font-semibold outline-none">{question.label}{question.draft && <span className="ml-2 text-sm">Draft</span>}</h2>
    {question.tooltip && <p className="mt-2 text-sm">{question.tooltip}</p>}
    {question.glossaryKey && <GlossaryTerm termKey={question.glossaryKey} glossary={glossary}/>}
    <div className="mt-5">
      {question.type==='family' ? <FamilyChooser options={options} value={value} onChange={onChange}/> :
      ['single','multi'].includes(question.type) ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" role={question.type==='multi'?'group':'radiogroup'} aria-label={question.label}>
        {options.map(o=>{const selected=question.type==='multi'?(value||[]).includes(o.value):value===o.value;const why=!o.noPreference && disabled.get(o.value);const count=counts.options?.[o.value];return <div key={o.value}>
          <button type="button" role={question.type==='multi'?'checkbox':'radio'} aria-checked={selected} disabled={!!why && !selected} title={why||undefined} onClick={()=>toggle(o.value)} className={'h-full w-full rounded-xl border p-3 text-left focus-visible:ring-2 focus-visible:ring-ill-accent disabled:opacity-50 '+(selected?'border-ill-accent bg-ill-accentBg':'border-ill-border bg-white')}>
            {o.image && <img src={o.image} alt="" loading="lazy" className="mb-2 h-28 w-full rounded-lg object-cover"/>}
            {o.color && <span className="mb-2 block h-16 rounded-lg" style={{background:o.color}}/>}
            <strong className="block">{o.label}</strong>{o.description && <span className="block text-sm">{o.description}</span>}
            {count && <span className="mt-2 block text-xs">{count.match} products · {count.verify} need a check</span>}
            {why && <span className="block text-xs">{why}</span>}
          </button>
        </div>})}
      </div> : question.type==='number' ? <label className="block">{question.unit||'Value'} <input type="number" min={question.min} max={question.max} step={question.step||1} value={value??''} placeholder={question.placeholder} onChange={e=>onChange(e.target.value===''?undefined:Number(e.target.value))}/></label> : question.type==='range' ?
      <div className="flex gap-4">{['low','high'].map((key,i)=><label key={key}>{i?'Maximum':'Minimum'} {question.unit}<input type="number" min={question.min} max={question.max} step={question.step||1} value={value?.[key]??''} onChange={e=>onChange({...value,[key]:e.target.value===''?undefined:Number(e.target.value)})}/></label>)}</div> : <p>{question.learnMore?.replace(/<[^>]*>/g,'')}</p>}
    </div>
  </div>;
}
