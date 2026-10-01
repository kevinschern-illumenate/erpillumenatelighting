import Tooltip from './Tooltip.jsx';


/**
 * Renders a glossary-backed term with an accessible tooltip.
 * All copy comes from the Desk-managed server definition.
 *
 * @param {object} props
 * @param {string} props.termKey  Key into the live glossary.
 * @param {React.ReactNode} [props.children]  Override the displayed text.
 */
export default function GlossaryTerm({ termKey, children, glossary = {} }) {
  const entry = glossary[termKey];
  if (!entry) {
    // Unknown key: render plain text so missing glossary copy never breaks UI.
    return <span>{children}</span>;
  }
  return (
    <Tooltip label={entry.label} tooltip={entry.tooltip} learnMore={entry.learnMore?.replace(/<[^>]*>/g, '')}>
      {children || entry.label}
    </Tooltip>
  );
}
