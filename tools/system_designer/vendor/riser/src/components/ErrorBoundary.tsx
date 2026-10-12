import { Component, type ReactNode } from 'react';
import { useProjectStore } from '../state/project-store';
import { downloadFile } from '../lib/files';

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: '' };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="panel" style={{ margin: 32, padding: 32 }}>
        <h1>The workspace needs to reload</h1>
        <p>
          Your saved local projects remain in this browser. Download the current project before
          reloading if you have unsaved edits.
        </p>
        <pre className="inline-error">{this.state.error}</pre>
        <div className="action-bar">
          <button
            onClick={() =>
              downloadFile(
                'recovery.riser.json',
                JSON.stringify(useProjectStore.getState().draft, null, 2),
              )
            }
          >
            Download current project
          </button>
          <button onClick={() => window.location.reload()}>Reload workspace</button>
        </div>
      </main>
    );
  }
}
