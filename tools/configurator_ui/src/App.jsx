import Wizard from './components/Wizard.jsx';

/**
 * App shell. The mount target (see main.jsx) carries id="ill-configurator-root",
 * which is what Tailwind's `important` scope and the scoped reset in index.css
 * key off of, keeping the widget self-contained when embedded in Webflow.
 *
 * @param {object} props
 * @param {object} [props.config]  Reserved for future host configuration.
 */
export default function App({ config = {} }) {
  return (
    <div className="ill-configurator-app" data-config-keys={Object.keys(config).join(',')}>
      <Wizard />
    </div>
  );
}
