import Tooltip from './Tooltip.jsx';
import glossary from '../content/glossary.json';

/**
 * Renders a glossary-backed term with an accessible tooltip.
 * All copy comes from content/glossary.json (non-engineer editable).
 *
 * @param {object} props
 * @param {string} props.termKey  Key into glossary.json.
 * @param {React.ReactNode} [props.children]  Override the displayed text.
 */
export default function GlossaryTerm({ termKey, children }) {
  const entry = glossary[termKey];
  if (!entry) {
    // Unknown key: render plain text so missing glossary copy never breaks UI.
    return <span>{children}</span>;
  }
  return (
    <Tooltip label={entry.label} tooltip={entry.tooltip} learnMore={entry.learnMore}>
      {children || entry.label}
    </Tooltip>
  );
}
