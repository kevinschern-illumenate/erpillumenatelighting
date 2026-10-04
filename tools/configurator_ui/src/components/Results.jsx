import VerificationNotice from './VerificationNotice.jsx';

export default function Results({result,config,token,settings,onEdit,onRestart,onAsk}) {
  const isPublic=config.mode==='public';
  const top=(result.top||result.matches||[]).slice(0,3);
  const reasons=[...new Set(top.flatMap(m=>m.verify||[]))];
  return <section aria-label="Product matches">
    <h2 className="font-display text-2xl font-semibold">{result.counts?.match||0} products fit your answers</h2>
    <p>{Object.entries(result.counts?.by_family||{}).map(([family,n])=>`${family}: ${n}`).join(' · ')}</p>
    {!!result.relaxed?.length && <p role="status" className="my-4 rounded-lg bg-ill-accentBg p-3">We broadened these preferences: {result.relaxed.join(', ')}. Review each product's trade-offs.</p>}
    {result.no_hard_match && <div className="my-4"><p>No products match these answers{result.eliminated_by ? ` (${result.eliminated_by.answer})` : ''}.</p><button type="button" onClick={()=>onEdit(result.eliminated_by?.question)}>Change that answer</button>{!isPublic && <button type="button" onClick={onAsk} className="ml-4">Ask our team</button>}</div>}
    <VerificationNotice reasons={reasons} settings={settings}/>
    <div className="my-5 grid gap-4 sm:grid-cols-3">{top.map(m=><article key={m.name||m.url} className="rounded-xl border border-ill-border bg-white p-4">
      {m.image && <img src={m.image} alt="" className="mb-3 h-36 w-full object-contain"/>}{m.best && <span className="text-xs font-semibold text-ill-accent">Best match</span>}
      <h3 className="text-lg font-semibold">{m.title}</h3>{(m.reasons||[]).map(r=><p key={r} className="mt-2 text-sm text-ill-success">{r}</p>)}
      {!!m.verify?.length && <span className="mt-2 block rounded bg-ill-goldBg p-2 text-sm">Verify with our team</span>}
      <a className="mt-3 inline-block text-ill-accent underline" href={isPublic ? m.url : `/portal/products/${encodeURIComponent(m.slug)}?finder=${encodeURIComponent(token)}`}>View product</a>
    </article>)}</div>
    <div className="flex flex-wrap gap-4">
      {isPublic ? result.claim_url && <a href={result.claim_url} className="rounded-lg bg-ill-accent px-4 py-3 text-white">Configure &amp; add to a project (dealers)</a> : <>
        <a href={result.catalog_url} className="rounded-lg bg-ill-accent px-4 py-3 text-white">See matching products</a>
        {top[0] && <a href={`/portal/products/${encodeURIComponent(top[0].slug)}?finder=${encodeURIComponent(token)}#configure`} className="rounded-lg border border-ill-accent px-4 py-3">Configure the top match now</a>}
      </>}
      <button type="button" onClick={()=>onEdit()}>Edit answers</button><button type="button" onClick={onRestart}>Start over</button>
    </div>
  </section>;
}
