export default function VerificationNotice({reasons=[],settings={}}) {
  if (!reasons.length) return null;
  return <aside role="note" className="my-4 rounded-xl border border-ill-gold bg-ill-goldBg p-4">
    <strong>{settings.verification_title || 'Most likely a fit — our team will confirm'}</strong>
    <p className="mt-2 text-sm">{(settings.verification_text || 'Our team needs to verify {reasons}. You can keep configuring.').replace('{reasons}', reasons.join(', '))}</p>
  </aside>;
}
