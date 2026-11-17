import { Component, type ErrorInfo, type ReactNode } from 'react';
import { ErrorState } from '../ui';

/**
 * Keeps a failing step from taking the whole designer down (SD-1.5): the rail, the save button and
 * the other steps keep working, and the designer can retry the step.
 */
export class StepBoundary extends Component<{ step: string; children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`ilLumenate System Designer: the ${this.props.step} step failed`, error, info.componentStack);
  }

  componentDidUpdate(previous: { step: string }) {
    if (previous.step !== this.props.step && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <ErrorState
        title="This step could not be shown"
        message="Something went wrong on this step. Your design is safe; your changes are kept in this browser."
        code={`STEP_${this.props.step.toUpperCase()}`}
        onRetry={() => this.setState({ error: null })}
      />
    );
  }
}
