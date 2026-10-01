export default function FamilyChooser({options, value, onChange}) {
  const ordered = [...options].sort((a,b) => Number(!!b.featured)-Number(!!a.featured));
  const featured = ordered.find(o => o.featured);
  return <div>
    <div role="radiogroup" aria-label="Product type" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {ordered.map(option => <button key={option.value} type="button" role="radio" aria-checked={value===option.value} aria-pressed={value===option.value} onClick={() => onChange(option.value)}
        className={'rounded-xl border p-4 text-left focus-visible:ring-2 focus-visible:ring-ill-accent ' + (option.featured ? 'sm:col-span-2 ' : '') + (value===option.value ? 'border-ill-accent bg-ill-accentBg' : 'border-ill-border bg-white')}>
        {option.image && <img src={option.image} alt="" className="mb-3 h-32 w-full rounded-lg object-cover"/>}
        {option.badge && <span className="mb-2 inline-block rounded-full bg-ill-goldBg px-2 py-1 text-xs">{option.badge}</span>}
        <strong className="block text-lg">{option.label}</strong><span className="text-sm">{option.description}</span>
      </button>)}
    </div>
    {featured && <button type="button" className="mt-4 text-ill-accent underline" onClick={() => onChange(featured.value)}>I'm not sure</button>}
  </div>;
}
