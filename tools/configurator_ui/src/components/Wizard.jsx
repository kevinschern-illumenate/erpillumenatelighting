import {useEffect,useMemo,useRef,useState} from 'react';
import {createClient} from '../lib/api.js';
import {loadDefinition} from '../lib/definition.js';
import {visibleQuestions,pruneHiddenAnswers,isAnswered,progress} from '../lib/engine.js';
import QuestionStep from './QuestionStep.jsx';
import Results from './Results.jsx';

export default function Wizard({config={}}) {
  const client=useMemo(()=>config.client||createClient(config),[config]);
  const [definition,setDefinition]=useState(null),[token,setToken]=useState(null),[answers,setAnswers]=useState({}),[counts,setCounts]=useState({}),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const refs=useRef({}),saveTimer=useRef(),saves=useRef(Promise.resolve()),boot=useRef(),evaluateSequence=useRef(0);
  const navigate=(url)=>(config.navigate||((path)=>window.location.assign(path)))(url);
  useEffect(()=>{
    let active=true;
    if(!boot.current) boot.current=(async()=>{
      const def=await loadDefinition(client);
      let claim=config.claimToken;
      if(config.mode!=='public' && !claim) { try { claim=localStorage.getItem('ill-finder-claim'); } catch {} }
      if(claim) {const claimed=await client.claim(claim);try{localStorage.removeItem('ill-finder-claim');}catch{}navigate(claimed.catalog_url);return {def};}
      const session=config.sessionToken ? {token:config.sessionToken} : await client.start();
      const previous=config.sessionToken ? await client.getSession(session.token) : {answers:{}};
      return {def,token:session.token,answers:previous.answers,stale:previous.stale};
    })();
    boot.current.then(data=>{if(active){setDefinition(data.def);setToken(data.token);setAnswers(pruneHiddenAnswers(data.answers||{}));if(data.stale)setNotice('The catalog has changed. Your answers will be checked against the latest products.');}}).catch(e=>active&&setError(e.message));
    return ()=>{active=false;};
  },[client]);
  const visible=definition?visibleQuestions(answers):[];
  const unanswered=visible.findIndex(q=>q.required&&!isAnswered(q,answers));
  const count=unanswered<0?visible.length:unanswered+1;
  const current=visible[Math.max(0,count-1)];
  function validAnswers(next) {
    const clean={...next};
    visibleQuestions(next).forEach(q=>{if(['number','range'].includes(q.type)&&!isAnswered({...q,required:true},next))delete clean[q.id];});
    return clean;
  }
  function queueSave(next) {
    saves.current=saves.current.catch(()=>{}).then(()=>client.saveAnswers(token,validAnswers(next)));
    return saves.current;
  }
  useEffect(()=>{
    if(!definition||config.mode==='public'||!token||busy) return;
    saveTimer.current=setTimeout(()=>queueSave(answers).catch(e=>setError(e.message)),500);
    return ()=>clearTimeout(saveTimer.current);
  },[answers,token,definition,busy]);
  useEffect(()=>{
    if(!current) return;
    const sequence=++evaluateSequence.current;
    const timer=setTimeout(()=>client.evaluate(validAnswers(answers),current.id).then(data=>{if(sequence===evaluateSequence.current)setCounts(old=>({...old,[current.id]:data}));}).catch(e=>{if(sequence===evaluateSequence.current)setError(e.message);}),150);
    return ()=>{clearTimeout(timer);evaluateSequence.current++;};
  },[answers,current?.id]);
  useEffect(()=>{if(current){const node=refs.current[current.id];node?.querySelector('h2')?.focus({preventScroll:true});node?.scrollIntoView?.({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}},[current?.id]);
  async function finish(next=answers) {
    clearTimeout(saveTimer.current);setBusy(true);setError('');
    try {if(config.mode!=='public')await queueSave(next);const data=await client.complete(token,next);if(data.route==='catalog')navigate(data.catalog_url||'/portal/products?type=Accessory%2CComponent');else setResult(data);}catch(e){setError(e.message);}finally{setBusy(false);}
  }
  function change(question,value) {
    const next=pruneHiddenAnswers({...answers,[question.id]:value});setAnswers(next);setResult(null);
    if(question.options?.some(o=>o.value===value&&o.routesTo==='catalog'))finish(next);
  }
  async function restart(){setBusy(true);try{await saves.current.catch(()=>{});const session=await client.start();setToken(session.token);setAnswers({});setResult(null);setCounts({});}catch(e){setError(e.message);}finally{setBusy(false);}}
  async function ask(){try{const response=await client.requestVerification(token);setNotice(`Request ${response.request} sent. Our team will help you find a product.`);}catch(e){setError(e.message);}}
  if(!definition)return <div role="status" className="p-6">{error||'Loading the Product Finder…'}</div>;
  return <div className="min-h-screen bg-ill-bg p-4 sm:p-8"><div className="mx-auto max-w-4xl">
    <header className="sticky z-10 mb-6 rounded-xl bg-white p-4 shadow-sm" style={{top:'var(--ill-finder-top, 80px)'}}><h1 className="font-display text-xl font-semibold">Find the right light for your project</h1><p className="text-sm" aria-live="polite">{progress(answers).percent}% complete{config.preview?' · Staff preview':''}</p></header>
    {error&&<p role="alert" className="mb-4 rounded bg-ill-dangerBg p-4">{error}</p>}{notice&&<p role="status" className="mb-4 rounded bg-ill-accentBg p-4">{notice}</p>}
    {result ? <Results result={result} token={token} config={config} settings={definition.settings} onRestart={restart} onAsk={ask} onEdit={id=>{setResult(null);setTimeout(()=>refs.current[id]?.scrollIntoView?.(),0);}}/> : <>
      {visible.slice(0,count).map(q=><section id={q.id} key={q.id} ref={el=>{refs.current[q.id]=el;}} className="mb-6 rounded-2xl border border-ill-border bg-white p-5 sm:p-7" style={{scrollMarginTop:'calc(var(--ill-finder-top, 80px) + 100px)'}}><QuestionStep question={q} answers={answers} onChange={v=>change(q,v)} counts={counts[q.id]} glossary={definition.glossary}/></section>)}
      {unanswered<0&&visible.length>0&&<button disabled={busy} type="button" onClick={()=>finish()} className="rounded-lg bg-ill-accent px-6 py-3 font-semibold text-white disabled:opacity-50">{busy?'Finding products…':'See matching products'}</button>}
    </>}
  </div></div>;
}
