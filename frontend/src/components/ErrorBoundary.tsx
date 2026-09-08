import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
  /** Changing this value resets the boundary — pass the route path so navigation clears a crash. */
  resetKey?: string;
  /** Where the failure happened, shown to the user so a report is actionable. */
  label?: string;
}

interface State {
  error: Error | null;
  info: string | null;
}

/**
 * Catches render-time exceptions so one bad component cannot blank the application.
 *
 * Without this, a single unrenderable value (for example an object passed where text is
 * expected) unmounts the whole tree and the user is left looking at a permanent skeleton
 * with the cause only visible in the browser console.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null, info: null });
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info: info.componentStack ?? null });
    // eslint-disable-next-line no-console
    console.error('[ESG Nexus] render error', error, info.componentStack);
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="card p-6 max-w-3xl">
        <div className="flex items-start gap-3">
          <AlertTriangle size={18} className="text-sev-critical shrink-0 mt-0.5" />
          <div className="min-w-0">
            <div className="font-semibold text-navy">This screen could not be displayed</div>
            <p className="text-sm text-gray-600 mt-1">
              {this.props.label ? `${this.props.label} failed to render. ` : ''}
              The rest of the application is unaffected. Nothing was saved or changed.
            </p>
            <pre className="mt-3 text-xs bg-gray-50 border border-gray-200 rounded p-3 overflow-x-auto whitespace-pre-wrap break-words">{error.message}</pre>
            {info && (
              <details className="mt-2">
                <summary className="text-xs text-gray-500 cursor-pointer">Component stack</summary>
                <pre className="mt-1 text-xxs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto">{info.trim()}</pre>
              </details>
            )}
            <div className="mt-4 flex gap-2">
              <button type="button" className="btn-secondary btn-sm" onClick={() => this.setState({ error: null, info: null })}>
                <RotateCcw size={14} /> Try again
              </button>
              <button type="button" className="btn-ghost btn-sm" onClick={() => window.location.reload()}>
                Reload the page
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
